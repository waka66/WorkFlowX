from fastapi import APIRouter, Depends, FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import auth, users, teams, projects, tasks, systems
from app.core.config import settings
from app.core.exceptions import AppException
from app.core.exception_handlers import (app_exception_handler, http_exception_handler,
                                        unhandled_exception_handler, validation_exception_handler)
from app.core.middlewares import register_middleware
from app.db.session import get_db
from app.services.task_service import UPLOAD_DIR
import app.models


def create_app() -> FastAPI:
    """应用工厂：便于测试用例各自创建隔离的 app 实例"""
    app = FastAPI()

    # CORS 中间件：必须显式列出来源
    # 注意：allow_origins=["*"] 与 allow_credentials=True 同时使用会被浏览器拒绝
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    app.add_exception_handler(
        AppException,
        app_exception_handler,
    )

    app.add_exception_handler(
        Exception,
        unhandled_exception_handler,
    )

    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    # 框架层异常（未带 token、路由不存在等）也返回统一信封
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)

    register_middleware(app)

    # ---------------- 探针 ----------------
    # 存活探针：不查数据库。若在这里查库，数据库抖动会导致容器被反复重启
    @app.get("/healthz", include_in_schema=False)
    async def healthz():
        return {"status": "ok"}

    # 就绪探针：包含数据库连通性，失败返回 503，由负载均衡决定是否接流量
    @app.get("/readyz", include_in_schema=False)
    async def readyz(db: AsyncSession = Depends(get_db)):
        try:
            await db.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse(status_code=503, content={"status": "unavailable"})
        return {"status": "ready"}

    # ---------------- 业务路由 ----------------
    # 所有业务路由统一挂在 /api/v1 下：
    # 真实路径、OpenAPI 中展示的路径、OAuth2PasswordBearer 的 tokenUrl 三者保持一致
    api_router = APIRouter(prefix="/api/v1")
    api_router.include_router(auth.router)
    api_router.include_router(users.router)
    api_router.include_router(teams.router)
    api_router.include_router(projects.team_projects_router)
    api_router.include_router(projects.projects_router)
    api_router.include_router(tasks.workflows_router)
    api_router.include_router(tasks.tasks_router)
    api_router.include_router(tasks.router)
    api_router.include_router(tasks.projects_router)
    api_router.include_router(tasks.comments_router)
    api_router.include_router(systems.router)
    api_router.include_router(systems.activities_router)
    api_router.include_router(systems.logs_router)
    api_router.include_router(systems.dashboard_router)
    api_router.include_router(systems.search_router)
    app.include_router(api_router)

    # 附件下载：task_service 生成的 download_url 形如 /static/uploads/<filename>，
    # 因此挂载点必须是 /static/uploads，且目录指向真实存储目录（否则会去找 uploads/uploads/xxx → 404）
    app.mount("/static/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="static")

    return app


app = create_app()
