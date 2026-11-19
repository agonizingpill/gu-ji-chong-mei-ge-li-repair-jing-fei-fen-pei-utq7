from fastapi import HTTPException
from sqlalchemy import select
from .models import Audit
def get(db,model,id,lock=False):
    stmt=select(model).where(model.id==id)
    if lock:stmt=stmt.with_for_update().execution_options(populate_existing=True)
    row=db.scalar(stmt)
    if not row:raise HTTPException(404,'卷宗或业务记录不存在')
    return row
def reject(condition,message):
    if condition:raise HTTPException(409,message)
def dump(row):return {c.name:getattr(row,c.name) for c in row.__table__.columns}
def audit(db,user,action,detail):db.add(Audit(actor=user.username,action=action,detail=str(detail)[:300]))
def finish(db,user,action,row):
    audit(db,user,action,getattr(row,'id',''));db.commit();return dump(row)

def lock_treatment(db,id):
    # 全部方案动作共用卷册根锁，随后锁方案，避免两条撤销方案并发恢复。
    from .models import Accession,Treatment
    initial=get(db,Treatment,id)
    get(db,Accession,initial.accession_id,True)
    return get(db,Treatment,id,True)
