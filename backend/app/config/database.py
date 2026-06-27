from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config.settings import settings

# 1. 定义一个基础类，后续所有的数据库表模型都会继承它
class Base(DeclarativeBase):
    pass

# 2. 创建“数据库引擎”。它相当于一个连接池，负责管理和数据库的物理连接
engine = create_engine(settings.database_url, pool_pre_ping=True)

# 3. 创建“会话工厂”。它本身不连接数据库，而是负责在需要时生产“会话（Session）”对象
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


# 
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal() # 生产一个全新的会话（相当于拿一把钥匙）
    try:
        yield db # 把这个会话交给路由函数使用
    finally:
        db.close() # 无论业务是否报错，请求结束后自动关闭会话（归还钥匙）
