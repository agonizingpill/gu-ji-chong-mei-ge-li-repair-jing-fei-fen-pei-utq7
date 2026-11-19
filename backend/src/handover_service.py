from sqlalchemy import select
from .models import Accession,Isolation,Cabinet,Treatment,Step,Handover,now
from .common import get,reject,finish
from .catalog_service import latest_observation,reviewed_risk
def handover(db,data,user):
    folio=get(db,Accession,data.accession_id,True)
    obs=latest_observation(db,folio.id)
    reject(not obs or obs.mold>0 or obs.humidity>60,'霉斑未清除或含水率过高，复测合格后再交接')
    risk=reviewed_risk(db,folio.id)
    reject(not risk or risk.approved!='low','最新病害需经主管复核为低风险')
    reject(db.scalar(select(Treatment).where(Treatment.accession_id==folio.id,Treatment.status.in_(['draft','funded']))) is not None,'修复工序或经费核销未完成')
    reject(not db.scalar(select(Treatment).where(Treatment.accession_id==folio.id,Treatment.status=='completed')),'尚无完成核销的修复方案')
    isolation=db.scalar(select(Isolation).where(Isolation.accession_id==folio.id,Isolation.active==True))
    if data.kind=='storage':
        reject(not isolation,'卷册已出柜，无需重复交接')
        get(db,Cabinet,isolation.cabinet_id,True);isolation.active=False;isolation.exited=now();folio.status='released'
    else:
        reject(folio.status!='released' or isolation is not None,'借展需先验收出柜移交库房')
        reject(db.scalar(select(Handover).where(Handover.accession_id==folio.id,Handover.kind=='exhibition')) is not None,'已办理借展交接')
    row=Handover(**data.model_dump());db.add(row);db.flush();return finish(db,user,'验收出柜' if data.kind=='storage' else '借展交接',row)
