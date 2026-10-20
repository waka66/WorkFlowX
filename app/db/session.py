from app.core.config import settings

from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker,AsyncSession


async_engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,                        # 调试模式输出 SQL 日志
    pool_size=settings.db_pool_size,            # 设置连接池活跃的连接数
    max_overflow=settings.db_max_overflow,      # 允许额外的连接数
    pool_recycle=settings.db_pool_recycle,      # 连接回收秒数，避免复用到已被 DB 断开的连接
    pool_pre_ping=settings.db_pool_pre_ping,    # 取连接前先探活，规避偶发 500
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
        