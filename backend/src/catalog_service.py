from sqlalchemy import select
from .models import Accession,Observation,RiskAssessment
from .common import get,reject,finish
def register(db,data,user):
    reject(db.scalar(select(Accession).where(Accession.code==data.code)) is not None,'馆藏号已登记')
    row=Accession(**data.model_dump());db.add(row);db.flush();return finish(db,user,'入藏登记',row)
def observe(db,data,user):
    folio=get(db,Accession,data.accession_id,True)
    reject(folio.status=='released','出柜后不能追加隔离病害，请重新办理入柜')
    row=Observation(**data.model_dump());db.add(row);db.flush();return finish(db,user,'病害复测',row)
def latest_observation(db,accession_id):
    return db.scalar(select(Observation).where(Observation.accession_id==accession_id).order_by(Observation.id.desc()).limit(1))
def reviewed_risk(db,accession_id):
    obs=latest_observation(db,accession_id)
    return db.scalar(select(RiskAssessment).where(RiskAssessment.observation_id==obs.id,RiskAssessment.status=='reviewed').order_by(RiskAssessment.id.desc())) if obs else None
