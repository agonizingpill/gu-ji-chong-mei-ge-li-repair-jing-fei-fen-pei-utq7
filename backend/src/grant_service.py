from sqlalchemy import select
from .models import Grant,Encumbrance,Treatment,Step,Accession,Isolation
from .common import get,reject,finish,lock_treatment
from .catalog_service import reviewed_risk
def create_grant(db,data,user):
    reject(db.scalar(select(Grant).where(Grant.code==data.code)) is not None,'经费编号重复')
    row=Grant(**data.model_dump());db.add(row);db.flush();return finish(db,user,'设立专项经费',row)
def fund(db,id,data,user):
    plan=lock_treatment(db,id)
    folio=get(db,Accession,plan.accession_id,True)
    grant=get(db,Grant,data.grant_id,True)
    reject(plan.status!='draft','仅草案可占用经费')
    reject(not reviewed_risk(db,folio.id),'最新病害分级未复核，不能开工')
    reject(not db.scalar(select(Isolation).where(Isolation.accession_id==folio.id,Isolation.active==True)),'卷册未在柜')
    reject(grant.budget_cents-grant.spent_cents-grant.reserved_cents<plan.estimated_cents,'专项余额不足；修订估价或改选专项后重试')
    grant.reserved_cents+=plan.estimated_cents;plan.status='funded';folio.status='repair'
    row=Encumbrance(treatment_id=id,grant_id=grant.id,amount_cents=plan.estimated_cents);db.add(row);db.flush();return finish(db,user,'专项经费占用',row)
def settle(db,id,data,user):
    plan=lock_treatment(db,id)
    reject(plan.status!='funded','方案尚未占款或已核销')
    reject(db.scalar(select(Step).where(Step.treatment_id==id,Step.done==False)) is not None,'全部依赖工序签证后才能核销')
    enc=db.scalar(select(Encumbrance).where(Encumbrance.treatment_id==id,Encumbrance.status=='held'))
    reject(enc is None,'未找到有效占款')
    grant=get(db,Grant,enc.grant_id,True)
    reject(data.actual_cents>enc.amount_cents,'核销额超过占款，需先办理追加方案')
    grant.reserved_cents-=enc.amount_cents;grant.spent_cents+=data.actual_cents
    enc.status='settled';enc.actual_cents=data.actual_cents;plan.status='completed'
    return finish(db,user,'经费核销',enc)
