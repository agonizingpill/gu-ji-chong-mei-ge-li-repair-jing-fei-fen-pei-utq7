import os,sys,pathlib
BACKEND=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BACKEND))
DB_PATH='/tmp/folio-relocation-test.db'
if os.path.exists(DB_PATH):os.remove(DB_PATH)
os.environ['DATABASE_URL']='sqlite:///'+DB_PATH
os.environ['SEED_DEMO']='false'
os.environ['JWT_SECRET']='test-secret'
os.environ['REDIS_URL']='redis://127.0.0.1:6379/15'
import pytest
from sqlalchemy import event
from src.database import Base,engine,Session
from src.models import *
from src.auth import password_hash
from src.constants import Role
# SQLite 不支持 SELECT ... FOR UPDATE：以 BEGIN IMMEDIATE 让写事务在快照前串行，
# 抢不到数据库锁的事务抛 OperationalError，由业务侧重试后读取最新柜位。
if engine.dialect.name=='sqlite':
    @event.listens_for(engine,'connect')
    def _sqlite_connect(dbapi_connection,_):
        dbapi_connection.isolation_level=None
    @event.listens_for(engine,'begin')
    def _sqlite_begin(conn):
        conn.exec_driver_sql('BEGIN IMMEDIATE')
@pytest.fixture()
def db():
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
    with Session() as session:
        for role in Role:
            session.add(User(username=role.value,password=password_hash('Folio@2026'),role=role.value))
        session.commit()
        yield session
        session.rollback()
class _User:
    def __init__(self,username='supervisor',role='supervisor'):self.username=username;self.role=role
@pytest.fixture()
def sup():return _User('supervisor','supervisor')
@pytest.fixture()
def op():return _User('operator','operator')
