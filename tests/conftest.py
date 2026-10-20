"""pytest 公共夹具。

测试库与开发库隔离：
- 默认从 settings.database_url 推导出 workflowx_test（只替换库名，复用同一实例）
- 可通过 TEST_DATABASE_URL 覆盖
- 若推导出的库名不含 "test" 则拒绝执行，防止误删开发数据
"""

import os

# 必须在导入 app.core.config 之前设置，确保日志里 env=test
os.environ.setdefault("APP_ENV", "test")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401  确保所有表注册到 Base.metadata
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app


def _test_database_url() -> str:
    override = os.environ.get("TEST_DATABASE_URL")
    url = make_url(override) if override else make_url(settings.database_url).set(database="workflowx_test")
    database = (url.database or "").lower()
    if "test" not in database:
        raise RuntimeError(
            f"拒绝在非测试库上执行测试：database={database!r}。"
            "请设置 TEST_DATABASE_URL 或将库名包含 test。"
        )
    return url.render_as_string(hide_password=False)


TEST_DATABASE_URL = _test_database_url()


@pytest_asyncio.fixture
async def engine():
    """每个用例一套干净表结构，避免用例之间互相污染。

    选择 function 作用域而非 session：让所有夹具与用例处在同一个事件循环里，
    避免跨循环复用 asyncpg 连接（pytest-asyncio 各版本行为差异较大）。
    """
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db(engine):
    """会话绑定到外层事务，用例结束整体回滚。"""
    conn = await engine.connect()
    trans = await conn.begin()
    session = async_sessionmaker(
        bind=conn,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )()
    try:
        yield session
    finally:
        await session.close()
        await trans.rollback()
        await conn.close()


@pytest_asyncio.fixture
async def client(db):
    application = create_app()

    async def _override_get_db():
        yield db

    application.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client
