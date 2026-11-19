from sqlalchemy import select
from .database import Session
from .models import *
from .auth import password_hash
from .algorithm import classify
from .constants import Role
def seed():
    with Session() as db:
        for item in Role:
            role=item.value
            if not db.scalar(select(User).where(User.username==role)):db.add(User(username=role,password=password_hash('Folio@2026'),role=role))
        for code,capacity in [('Q1',3),('Q2',2),('Q3',2)]:
            if not db.scalar(select(Cabinet).where(Cabinet.code==code)):db.add(Cabinet(code=code,capacity=capacity))
        if not db.scalar(select(Grant).where(Grant.code=='GF-2026')):db.add(Grant(code='GF-2026',name='古籍虫霉修复专项',budget_cents=1200000,reserved_cents=0,spent_cents=0))
        db.flush()
        for code,title,humidity,holes,mold in [('GB-A031','嘉庆县志',74,8,12),('GB-A032','乾隆诗稿',55,3,0),('GB-A033','水经注校本',68,14,6)]:
            if db.scalar(select(Accession).where(Accession.code==code)):continue
            folio=Accession(code=code,title=title,era='清代',paper='竹纸',status='isolated');db.add(folio);db.flush()
            obs=Observation(accession_id=folio.id,humidity=humidity,holes=holes,mold=mold,note='入藏病害普查');db.add(obs);db.flush()
            cabinet=db.scalar(select(Cabinet).where(Cabinet.code=='Q1' if code!='GB-A033' else Cabinet.code=='Q2'))
            db.add(Isolation(accession_id=folio.id,cabinet_id=cabinet.id))
            predicted,metrics=classify(humidity,holes,mold)
            db.add(RiskAssessment(accession_id=folio.id,observation_id=obs.id,status='reviewed',predicted=predicted,approved='low' if code=='GB-A032' else predicted,review_note='主管现场复核',metrics=metrics))
            plan=Treatment(accession_id=folio.id,name='缺资大修方案' if code=='GB-A031' else '待验收方案' if code=='GB-A032' else '虫孔修补方案',estimated_cents=1500000 if code=='GB-A031' else 180000,status='completed' if code=='GB-A032' else 'draft');db.add(plan);db.flush()
            parent=None
            for i,n in enumerate(['干燥除霉','虫孔补纸','平整验收'],1):
                step=Step(treatment_id=plan.id,name=n,position=i,depends_on=parent,done=code=='GB-A032',evidence='修复员签证' if code=='GB-A032' else '');db.add(step);db.flush();parent=step.id
            if code=='GB-A032':
                grant=db.scalar(select(Grant).where(Grant.code=='GF-2026'));grant.spent_cents+=160000
                db.add(Encumbrance(treatment_id=plan.id,grant_id=grant.id,amount_cents=180000,actual_cents=160000,status='settled'))
        db.commit()
if __name__=='__main__':seed()
