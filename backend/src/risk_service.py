import os
import redis
from sqlalchemy import select
from .models import Accession,Isolation,RiskAssessment
from .common import get,reject,finish
from .catalog_service import latest_observation
queue=redis.Redis.from_url(os.getenv('REDIS_URL','redis://redis:6379/0'),decode_responses=True)
def request_risk(db,data,user):
    folio=get(db,Accession,data.accession_id,True);obs=latest_observation(db,folio.id)
    reject(not obs,'先录入病害测量')
    reject(not db.scalar(select(Isolation).where(Isolation.accession_id==folio.id,Isolation.active==True)),'先隔离入柜再评估')
    reject(db.scalar(select(RiskAssessment).where(RiskAssessment.observation_id==obs.id,RiskAssessment.status.in_(['queued','running']))) is not None,'该次观测仍在排队')
    row=RiskAssessment(accession_id=folio.id,observation_id=obs.id);db.add(row);db.flush();result=finish(db,user,'提交风险分级',row)
    queue.rpush('folio:risk',row.id);return result
def review(db,id,data,user):
    row=get(db,RiskAssessment,id,True)
    reject(row.status!='done','仅已完成分级可复核')
    reject(latest_observation(db,row.accession_id).id!=row.observation_id,'病害已复测，请重新运行最新分级')
    row.status='reviewed';row.approved=data.level;row.review_note=data.note
    return finish(db,user,'风险主管复核',row)
