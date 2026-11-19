import pytest,threading
from sqlalchemy import select,func
from sqlalchemy.exc import OperationalError
from fastapi import HTTPException
from fastapi.testclient import TestClient
from src.models import *
from src.models import now
from src.algorithm import classify
from src import isolation_service as iso
from src.app import app
from src.schemas import AdmitInput
SUP={'username':'supervisor','password':'Folio@2026'}
OP={'username':'operator','password':'Folio@2026'}
VIEW={'username':'viewer','password':'Folio@2026'}
def cabinet(db,code,capacity):
    row=Cabinet(code=code,capacity=capacity);db.add(row);db.flush();return row
def folio(db,code,humidity,holes,mold):
    row=Accession(code=code,title='测试册'+code,era='清代',paper='竹纸',status='isolated');db.add(row);db.flush()
    db.add(Observation(accession_id=row.id,humidity=humidity,holes=holes,mold=mold,note='测试测量'));db.flush()
    return row
def put_in(db,aid,cab_id):
    db.add(Isolation(accession_id=aid,cabinet_id=cab_id));db.flush()
def level_of(h,holes,m):return classify(h,holes,m)[0]
def active_iso(db,aid):
    return db.scalar(select(Isolation).where(Isolation.accession_id==aid,Isolation.active==True))
def items_of(db,rid):
    return {i.accession_id:i for i in db.scalars(select(RelocationItem).where(RelocationItem.relocation_id==rid)).all()}
def test_decommission_blocks_new_admission_and_cabinet_levels_match_decision_tree(db,sup,op):
    leak=cabinet(db,'Q1',3);target=cabinet(db,'Q2',2);extra=cabinet(db,'Q3',1)
    h=folio(db,'GB-T01',80,20,15);l=folio(db,'GB-T02',40,0,0)
    put_in(db,h.id,leak.id);put_in(db,l.id,leak.id)
    db.commit()
    out=iso.decommission(db,leak.id,sup)
    assert out['total']==2
    plan=db.get(Relocation,out['relocation']['id'])
    its=items_of(db,plan.id)
    assert its[h.id].risk_level==level_of(80,20,15)=='high'
    assert its[l.id].risk_level==level_of(40,0,0)=='low'
    # 高低风险不同柜：两册目标柜必须分开，且都不是漏柜
    assert its[h.id].target_cabinet_id in (target.id,extra.id)
    assert its[l.id].target_cabinet_id in (target.id,extra.id)
    assert its[h.id].target_cabinet_id!=its[l.id].target_cabinet_id
    # 停用柜拒绝新入柜
    fresh=folio(db,'GB-T03',45,1,0);db.commit()
    with pytest.raises(Exception,match='漏水停用'):
        iso.admit(db,AdmitInput(accession_id=fresh.id,cabinet_id=leak.id),op)
    db.rollback()
    # 在用柜仍可入柜
    iso.admit(db,AdmitInput(accession_id=fresh.id,cabinet_id=target.id),op)
    assert active_iso(db,fresh.id).cabinet_id==target.id
def test_high_risk_priority_and_never_share_cabinet(db,sup):
    # 漏柜 Q1 容量3，放高 H、高 H、普通 N；其余柜 Q2 容量1、Q3 容量1、Q4 容量1
    leak=cabinet(db,'Q1',3);q2=cabinet(db,'Q2',1);q3=cabinet(db,'Q3',1);q4=cabinet(db,'Q4',1)
    h1=folio(db,'GB-H1',80,20,15);h2=folio(db,'GB-H2',75,18,12);n1=folio(db,'GB-N1',40,0,0)
    for aid in (h1.id,h2.id,n1.id):put_in(db,aid,leak.id)
    db.commit()
    out=iso.decommission(db,leak.id,sup);rid=out['relocation']['id']
    its=items_of(db,rid)
    high_targets={its[h1.id].target_cabinet_id,its[h2.id].target_cabinet_id}
    # 先满足两册高风险，各占一柜且不与普通册同柜
    assert len(high_targets)==2 and all(its[i].status=='waiting' for i in (h1.id,h2.id))
    assert its[n1.id].target_cabinet_id not in high_targets
    iso.execute_relocation(db,rid,sup)
    db.expire_all()
    its=items_of(db,rid)
    assert all(its[i].status=='moved' for i in (h1.id,h2.id,n1.id))
    cabinets={c.id:c for c in db.scalars(select(Cabinet)).all()}
    for aid in (h1.id,h2.id,n1.id):
        assert active_iso(db,aid).cabinet_id==its[aid].target_cabinet_id
    for c in cabinets.values():
        occupants=[i for i in db.scalars(select(Isolation).where(Isolation.cabinet_id==c.id,Isolation.active==True)).all()]
        if len(occupants)>1:
            levels={its[o.accession_id].risk_level for o in occupants}
            assert levels=={'high'} or 'high' not in levels
def test_scarce_slots_prioritize_high_risk_and_others_wait_in_original(db,sup):
    leak=cabinet(db,'Q1',3);q2=cabinet(db,'Q2',1)
    h1=folio(db,'GB-H1',80,20,15);n1=folio(db,'GB-N1',40,0,0);n2=folio(db,'GB-N2',50,1,1)
    for aid in (h1.id,n1.id,n2.id):put_in(db,aid,leak.id)
    db.commit()
    out=iso.decommission(db,leak.id,sup);rid=out['relocation']['id']
    assert out['waiting']==2
    its=items_of(db,rid)
    assert its[h1.id].target_cabinet_id==q2.id
    assert its[n1.id].target_cabinet_id is None and its[n2.id].target_cabinet_id is None
    result=iso.execute_relocation(db,rid,sup)
    assert result=={'relocation':rid,'status':'open','moved':1,'waiting':2}
    db.expire_all()
    its=items_of(db,rid)
    assert its[h1.id].status=='moved'
    # 没柜位的留在原柜、状态等位
    for aid in (n1.id,n2.id):
        assert its[aid].status=='waiting' and active_iso(db,aid).cabinet_id==leak.id
def test_concurrent_admit_takes_slot_then_relocation_replans_without_repeating(db,sup,op):
    leak=cabinet(db,'Q1',2);q2=cabinet(db,'Q2',1)
    n1=folio(db,'GB-N1',40,0,0);n2=folio(db,'GB-N2',42,1,0)
    put_in(db,n1.id,leak.id);put_in(db,n2.id,leak.id);db.commit()
    out=iso.decommission(db,leak.id,sup);rid=out['relocation']['id']
    # 方案先给 n1 安排 Q2；确认前并发入柜占掉 Q2 唯一空位
    other=folio(db,'GB-O1',44,0,0);db.commit()
    iso.admit(db,AdmitInput(accession_id=other.id,cabinet_id=q2.id),op)
    # 无新空位：两册都留在原柜等位，且不产生重复隔离行
    result=iso.execute_relocation(db,rid,sup)
    assert result['moved']==0 and result['waiting']==2
    its=items_of(db,rid)
    assert its[n1.id].target_cabinet_id is None
    for aid in (n1.id,n2.id):
        rows=db.scalars(select(Isolation).where(Isolation.accession_id==aid)).all()
        assert len(rows)==1 and active_iso(db,aid).cabinet_id==leak.id
    # 空出合规柜位后重试：成功搬 n1，且没有重复搬
    q3=cabinet(db,'Q3',1);db.commit()
    again=iso.execute_relocation(db,rid,sup)
    assert again['moved']==1 and again['waiting']==1
    db.expire_all()
    its=items_of(db,rid)
    assert its[n1.id].status=='moved' and its[n1.id].target_cabinet_id==q3.id
    assert its[n2.id].status=='waiting'
    # 再重试幂等：不重复搬同一册
    third=iso.execute_relocation(db,rid,sup)
    assert third['moved']==1 and third['waiting']==1
    assert len(db.scalars(select(Isolation).where(Isolation.accession_id==n1.id)).all())==2
def test_completed_plan_retry_is_idempotent(db,sup):
    leak=cabinet(db,'Q1',1);q2=cabinet(db,'Q2',1)
    n1=folio(db,'GB-N1',40,0,0);put_in(db,n1.id,leak.id);db.commit()
    rid=iso.decommission(db,leak.id,sup)['relocation']['id']
    first=iso.execute_relocation(db,rid,sup)
    assert first['status']=='completed' and first['moved']==1
    second=iso.execute_relocation(db,rid,sup)
    assert second['retried'] is True and second['moved']==1
    # 只有 旧行(已出柜)+新行(在柜) 两条
    rows=db.scalars(select(Isolation).where(Isolation.accession_id==n1.id)).all()
    assert len(rows)==2 and sum(r.active for r in rows)==1
def test_relocation_item_cancels_when_folio_already_left(db,sup):
    leak=cabinet(db,'Q1',1);q2=cabinet(db,'Q2',1)
    n1=folio(db,'GB-N1',40,0,0);put_in(db,n1.id,leak.id);db.commit()
    rid=iso.decommission(db,leak.id,sup)['relocation']['id']
    iso_row=active_iso(db,n1.id);iso_row.active=False;iso_row.exited=now();db.commit()
    result=iso.execute_relocation(db,rid,sup)
    assert result['moved']==0
    item=items_of(db,rid)[n1.id]
    assert item.status=='cancelled'
def test_concurrent_threads_preserve_capacity_and_segregation_invariants(db,sup,op):
    # 两个停用柜（各 3 册）+ 三个目标柜，多线程交错入柜与执行搬柜，最终不变量必须成立。
    leak1=cabinet(db,'Q1',3);leak2=cabinet(db,'Q2',3)
    t1=cabinet(db,'Q3',2);t2=cabinet(db,'Q4',2);t3=cabinet(db,'Q5',3)
    leak_folios=[]
    for i,(hh,ho,mo) in enumerate([(80,20,15),(75,18,12),(40,0,0)]*2):
        f=folio(db,f'GB-C{i:02d}',hh,ho,mo)
        put_in(db,f.id,leak1.id if i<3 else leak2.id);leak_folios.append(f)
    db.commit()
    r1=iso.decommission(db,leak1.id,sup);r2=iso.decommission(db,leak2.id,sup);db.commit()
    barrier=threading.Barrier(3)
    errors=[]
    def fill_cabinet(cab_id,code):
        from src.database import Session
        try:
            barrier.wait()
            with Session() as s:
                row=Accession(code=code,title='并发占位册'+code,era='清代',paper='竹纸',status='isolated');s.add(row);s.flush()
                s.add(Observation(accession_id=row.id,humidity=45,holes=1,mold=0));s.commit()
                fid=row.id
            for attempt in range(20):
                with Session() as s:
                    try:
                        iso.admit(s,AdmitInput(accession_id=fid,cabinet_id=cab_id),op);break
                    except OperationalError:
                        s.rollback()
                    except HTTPException as exc:
                        # 抢位竞争中柜位先被搬柜占满：业务拒绝即正确结果，无需再试。
                        if exc.status_code==409:break
                        raise
        except Exception as exc:errors.append(exc)
    def run_plan(rid):
        from src.database import Session
        try:
            barrier.wait()
            for _ in range(6):
                with Session() as s:
                    try:
                        out=iso.execute_relocation(s,rid,sup)
                        if out['status']=='completed':return
                    except OperationalError:s.rollback()
        except Exception as exc:errors.append(exc)
    th=[threading.Thread(target=fill_cabinet,args=(t1.id,'GB-W01')),
        threading.Thread(target=run_plan,args=(r1['relocation']['id'],)),
        threading.Thread(target=run_plan,args=(r2['relocation']['id'],))]
    for x in th:x.start()
    for x in th:x.join()
    assert not errors,errors
    db.expire_all()
    # 不变量 1：每个在柜卷册只有一条 active 隔离行
    for aid in [f.id for f in leak_folios]:
        active=db.scalars(select(Isolation).where(Isolation.accession_id==aid,Isolation.active==True)).all()
        assert len(active)==1
    # 不变量 2：柜不超容量
    for c in db.scalars(select(Cabinet)).all():
        n=db.scalar(select(func.count()).select_from(Isolation).where(Isolation.cabinet_id==c.id,Isolation.active==True))
        assert n<=c.capacity
    # 不变量 3：同柜不混装高低风险；停用柜内只剩等位册
    all_items={i.accession_id:i for i in db.scalars(select(RelocationItem)).all()}
    for c in db.scalars(select(Cabinet)).all():
        occ=db.scalars(select(Isolation).where(Isolation.cabinet_id==c.id,Isolation.active==True)).all()
        kinds=set()
        for o in occ:
            item=all_items.get(o.accession_id)
            lvl=item.risk_level if item else level_of(45,1,0)
            kinds.add('high' if lvl=='high' else 'normal')
        assert kinds<= {'high'} or kinds<= {'normal'}
        if not c.active:
            assert all(all_items[o.accession_id].status=='waiting' for o in occ)
def test_http_permissions_and_workspace_lists(db):
    leak=cabinet(db,'Q1',1);q2=cabinet(db,'Q2',1)
    n1=folio(db,'GB-N1',40,0,0);put_in(db,n1.id,leak.id);db.commit()
    with TestClient(app) as client:
        r=client.post('/auth/login',json=VIEW);token=r.json()['token'];h={'Authorization':'Bearer '+token}
        # viewer 不能停用
        assert client.post(f'/cabinets/{leak.id}/decommission',headers=h).status_code==403
        r=client.post('/auth/login',json=OP);op_h={'Authorization':'Bearer '+r.json()['token']}
        # operator 不能停用（主管动作）
        assert client.post(f'/cabinets/{leak.id}/decommission',headers=op_h).status_code==403
        r=client.post('/auth/login',json=SUP);sup_h={'Authorization':'Bearer '+r.json()['token']}
        out=client.post(f'/cabinets/{leak.id}/decommission',headers=sup_h).json()
        rid=out['relocation']['id']
        # operator 可以确认搬柜
        done=client.post('/relocations/execute',json={'relocation_id':rid},headers=op_h)
        assert done.status_code==200 and done.json()['moved']==1
        data=client.get('/workspace',headers=sup_h).json()
        assert 'relocations' in data and 'relocation_items' in data
        assert next(c for c in data['cabinets'] if c['id']==leak.id)['active'] is False
        # 入柜下拉只剩在用柜
        assert all(c['active'] for c in data['cabinets'] if c['id']!=leak.id)
        # 停用柜无法入柜
        fresh=client.post('/accessions',json={'code':'GB-T99','title':'新入藏册件','era':'清代','paper':'竹纸'},headers=op_h).json()
        client.post('/observations',json={'accession_id':fresh['id'],'humidity':40,'holes':0,'mold':0},headers=op_h)
        refused=client.post('/isolations',json={'accession_id':fresh['id'],'cabinet_id':leak.id},headers=op_h)
        assert refused.status_code==409
