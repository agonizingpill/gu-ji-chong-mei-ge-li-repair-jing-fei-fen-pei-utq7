from sqlalchemy import select,func
from .models import Accession,Cabinet,Isolation,Relocation,RelocationItem,now
from .common import get,reject,finish,audit
from .catalog_service import latest_observation
from .algorithm import classify
def folio_level(db,accession_id,cache):
    # 复用现有决策树，按各册最新一次病害测量分级；结果在一次业务内缓存，避免重复训练。
    if accession_id in cache:return cache[accession_id]
    obs=latest_observation(db,accession_id)
    level=classify(obs.humidity,obs.holes,obs.mold)[0] if obs else 'medium'
    cache[accession_id]=level
    return level
def cabinet_snapshot(db,cache):
    cabinets=db.scalars(select(Cabinet).order_by(Cabinet.id)).all()
    counts={c.id:0 for c in cabinets};risks={c.id:set() for c in cabinets}
    rows=db.scalars(select(Isolation).where(Isolation.active==True)).all()
    for iso in rows:
        counts[iso.cabinet_id]+=1
        level=folio_level(db,iso.accession_id,cache)
        risks[iso.cabinet_id].add('high' if level=='high' else 'normal')
    return cabinets,counts,risks
def choose_cabinet(kind,cabinets,counts,risks,exclude):
    # 高风险只进空柜或已有高风险的柜；其余册只进空柜或无高风险的柜。
    # 优先并入同类柜、再开空柜；同档先占余位最少的柜，尽量保住空柜给另一类。
    ranked=[]
    for c in cabinets:
        if not c.active or c.id in exclude or counts[c.id]>=c.capacity:continue
        present=risks[c.id]
        if kind=='high' and 'normal' in present:continue
        if kind=='normal' and 'high' in present:continue
        tier=0 if present else 1
        ranked.append((tier,c.capacity-counts[c.id],c.id,c))
    if not ranked:return None
    ranked.sort(key=lambda x:(x[0],x[1],x[2]))
    return ranked[0][3]
def occupy(target,kind,counts,risks):
    counts[target.id]+=1;risks[target.id].add(kind)
def cabinet(db,data,user):
    reject(db.scalar(select(Cabinet).where(Cabinet.code==data.code)) is not None,'柜号已存在')
    row=Cabinet(**data.model_dump());db.add(row);db.flush();return finish(db,user,'设置隔离柜',row)
def admit(db,data,user):
    folio=get(db,Accession,data.accession_id,True)
    cabinet=get(db,Cabinet,data.cabinet_id,True)
    reject(not cabinet.active,'该隔离柜已登记漏水停用，不再接收新册，请改选在用柜')
    reject(db.scalar(select(Isolation).where(Isolation.accession_id==folio.id,Isolation.active==True)) is not None,'该卷册已在柜')
    reject(not latest_observation(db,folio.id),'请先登记病害')
    occupied=db.scalar(select(func.count()).select_from(Isolation).where(Isolation.cabinet_id==cabinet.id,Isolation.active==True))
    reject(occupied>=cabinet.capacity,'隔离柜已满，改选空柜后重试')
    row=Isolation(**data.model_dump());db.add(row);folio.status='isolated';db.flush();return finish(db,user,'隔离入柜',row)
def decommission(db,cabinet_id,user):
    source=get(db,Cabinet,cabinet_id,True)
    reject(not source.active,'该隔离柜已登记停用')
    source.active=False;source.decommissioned_at=now()
    cache={}
    cabinets,counts,risks=cabinet_snapshot(db,cache)
    folios=[iso.accession_id for iso in db.scalars(select(Isolation).where(Isolation.cabinet_id==source.id,Isolation.active==True).order_by(Isolation.id)).all()]
    plan=Relocation(source_cabinet_id=source.id,status='open');db.add(plan);db.flush()
    # 先尽量多搬高风险册，再尽量多搬其余册；同级按入柜登记顺序保证可复现。
    ordered=sorted(folios,key=lambda aid:(folio_level(db,aid,cache)!='high',aid))
    waiting=0
    for aid in ordered:
        level=folio_level(db,aid,cache);kind='high' if level=='high' else 'normal'
        target=choose_cabinet(kind,cabinets,counts,risks,exclude=set())
        item=RelocationItem(relocation_id=plan.id,accession_id=aid,risk_level=level)
        if target:
            item.target_cabinet_id=target.id;item.status='waiting';item.reason='等待确认搬柜'
            occupy(target,kind,counts,risks)
        else:
            item.status='waiting';item.reason='无合适柜位，留在原柜待搬';waiting+=1
        db.add(item)
    if not folios:plan.status='completed';plan.executed_at=now()
    db.flush();result=finish(db,user,'登记隔离柜停用并编排搬柜',plan)
    return {'relocation':result,'waiting':waiting,'total':len(folios)}
def execute_relocation(db,relocation_id,user):
    plan=get(db,Relocation,relocation_id,True)
    if plan.status=='completed':
        items=db.scalars(select(RelocationItem).where(RelocationItem.relocation_id==plan.id).order_by(RelocationItem.id)).all()
        return {'relocation':plan.id,'status':'completed','moved':sum(i.status=='moved' for i in items),'waiting':sum(i.status=='waiting' for i in items),'retried':True}
    lock_ids=sorted({plan.source_cabinet_id}|{i.target_cabinet_id for i in db.scalars(select(RelocationItem).where(RelocationItem.relocation_id==plan.id)).all() if i.target_cabinet_id})
    for cid in lock_ids:get(db,Cabinet,cid,True)
    cache={}
    cabinets,counts,risks=cabinet_snapshot(db,cache)
    items=db.scalars(select(RelocationItem).where(RelocationItem.relocation_id==plan.id).order_by(RelocationItem.id)).all()
    moved=waiting=0
    for item in items:
        if item.status=='moved':moved+=1;continue  # 重试不重复搬同一册
        iso=db.scalar(select(Isolation).where(Isolation.accession_id==item.accession_id,Isolation.active==True).with_for_update())
        if not iso:
            item.status='cancelled';item.reason='卷册已不在隔离柜，无需搬柜';continue
        level=folio_level(db,item.accession_id,cache);item.risk_level=level
        kind='high' if level=='high' else 'normal'
        target=db.get(Cabinet,item.target_cabinet_id) if item.target_cabinet_id else None
        valid=target is not None and target.active and counts[target.id]<target.capacity and not (('normal' in risks[target.id]) if kind=='high' else ('high' in risks[target.id]))
        if not valid:
            # 并发入柜占了空位或风险混装：按当前柜位重新安排。
            target=choose_cabinet(kind,cabinets,counts,risks,exclude={plan.source_cabinet_id})
            item.target_cabinet_id=target.id if target else None
        if target:
            iso.active=False;iso.exited=now()
            db.add(Isolation(accession_id=item.accession_id,cabinet_id=target.id))
            occupy(target,kind,counts,risks)
            item.status='moved';item.moved_at=now();item.reason=''
            audit(db,user,'执行卷册搬柜',{'item':item.id,'cabinet':target.id});moved+=1
        else:
            item.status='waiting';item.reason='无合适柜位，留在原柜待搬';waiting+=1
    if waiting==0:plan.status='completed';plan.executed_at=now()
    db.flush();finish(db,user,'确认搬柜方案',plan)
    return {'relocation':plan.id,'status':plan.status,'moved':moved,'waiting':waiting}
