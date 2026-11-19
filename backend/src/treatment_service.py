from sqlalchemy import select
from .models import Accession,Treatment,Step,Isolation,Encumbrance,Grant
from .common import get,reject,finish,lock_treatment
from .catalog_service import reviewed_risk
def propose(db,data,user):
    folio=get(db,Accession,data.accession_id,True)
    reject(not reviewed_risk(db,folio.id),'最新病害风险尚未经主管复核')
    reject(not db.scalar(select(Isolation).where(Isolation.accession_id==folio.id,Isolation.active==True)),'卷册未在隔离柜')
    reject(db.scalar(select(Treatment).where(Treatment.accession_id==folio.id,Treatment.status.in_(['draft','funded']))) is not None,'该卷册已有执行中方案')
    reject(any(len(n.strip())<2 or len(n)>80 for n in data.steps),'工序名称需2至80字')
    row=Treatment(accession_id=folio.id,name=data.name,estimated_cents=data.estimated_cents);db.add(row);db.flush()
    parent=None
    for i,name in enumerate(data.steps,1):
        step=Step(treatment_id=row.id,name=name.strip(),position=i,depends_on=parent);db.add(step);db.flush();parent=step.id
    return finish(db,user,'编制修复方案',row)
def revise(db,id,data,user):
    row=lock_treatment(db,id)
    reject(row.status not in ('draft','cancelled'),'资金占用中或完工方案不能改价')
    if row.status=='cancelled':
        reject(db.scalar(select(Treatment).where(Treatment.accession_id==row.accession_id,Treatment.id!=id,Treatment.status.in_(['draft','funded']))) is not None,'卷册已有替代方案')
    row.name=data.name;row.estimated_cents=data.estimated_cents;row.status='draft'
    return finish(db,user,'修订恢复方案',row)
def complete_step(db,id,data,user):
    step=get(db,Step,id);plan=lock_treatment(db,step.treatment_id);step=get(db,Step,id,True)
    reject(plan.status!='funded','预算未占用，不得施工')
    reject(step.done,'该工序已签证')
    reject(step.depends_on is not None and not get(db,Step,step.depends_on).done,'前置工序尚未签证')
    step.done=True;step.evidence=data.evidence
    return finish(db,user,'工序施工签证',step)
def cancel(db,id,user):
    plan=lock_treatment(db,id)
    reject(plan.status not in ('draft','funded'),'当前状态不能撤销')
    reject(db.scalar(select(Step).where(Step.treatment_id==id,Step.done==True)) is not None,'已有施工签证，不能撤销占款')
    enc=db.scalar(select(Encumbrance).where(Encumbrance.treatment_id==id,Encumbrance.status=='held'))
    if enc:
        grant=get(db,Grant,enc.grant_id,True);grant.reserved_cents-=enc.amount_cents;enc.status='released'
    plan.status='cancelled';get(db,Accession,plan.accession_id,True).status='isolated'
    return finish(db,user,'撤销并退还占用',plan)
