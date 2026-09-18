from app.core.config import settings

from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker,AsyncSession


async_engine = create_async_engine(
    settings.database_url,
    #echo=True,   # 可选，输出 SQL 日志
    pool_size=5,   # 设置连接池活跃的连接数
    max_overflow=5   # 允许额外的连接数
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,    # 绑定数据库引擎
    class_=AsyncSession,  # 指定会话类
    expire_on_commit=False  # 会话对象不过期，不重新查询数据库
)

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session    # 返回数据库会话给路由处理函数
        except Exception:
            await session.rollback()  # 有异常则回滚
            raise
        finally:
            await session.close()  # 关闭会话