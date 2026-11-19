from sqlalchemy import select,func
from .models import Accession,Cabinet,Isolation
from .common import get,reject,finish
from .catalog_service import latest_observation
def cabinet(db,data,user):
    reject(db.scalar(select(Cabinet).where(Cabinet.code==data.code)) is not None,'柜号已存在')
    row=Cabinet(**data.model_dump());db.add(row);db.flush();return finish(db,user,'设置隔离柜',row)
def admit(db,data,user):
    folio=get(db,Accession,data.accession_id,True)
    cabinet=get(db,Cabinet,data.cabinet_id,True)
    reject(db.scalar(select(Isolation).where(Isolation.accession_id==folio.id,Isolation.active==True)) is not None,'该卷册已在柜')
    reject(not latest_observation(db,folio.id),'请先登记病害')
    occupied=db.scalar(select(func.count()).select_from(Isolation).where(Isolation.cabinet_id==cabinet.id,Isolation.active==True))
    reject(occupied>=cabinet.capacity,'隔离柜已满，改选空柜后重试')
    row=Isolation(**data.model_dump());db.add(row);folio.status='isolated';db.flush();return finish(db,user,'隔离入柜',row)
