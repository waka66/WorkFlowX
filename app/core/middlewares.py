import time
import logging
import contextvars
import uuid
from typing import Optional
from fastapi import FastAPI, Request
from pythonjsonlogger import jsonlogger
import json
import os
from logging.handlers import TimedRotatingFileHandler
from app.core.config import settings



logger = logging.getLogger("uvicorn.access")
logger.disabled = True


request_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("request_id", default=None)

def get_request_id() -> Optional[str]:
    return request_id_var.get()

def set_request_id(request_id: str):
    request_id_var.set(request_id)

def generate_request_id() -> str:
    return str(uuid.uuid4())

# ---------- 日志配置 ----------
class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        log_record['level'] = record.levelname
        log_record['logger'] = record.name
        log_record['timestamp'] = record.created
        log_record['message'] = record.getMessage()
        # 服务标识与运行环境来自配置，不能写死：
        # 同一份代码会跑在 dev / test / prod 三套环境，硬编码会让日志互相污染
        log_record['app'] = settings.app_name
        log_record['env'] = settings.app_env
        log_record['version'] = settings.app_version
        request_id = get_request_id()
        if request_id:
            log_record['request_id'] = request_id

    def serialize_log_record(self, log_record):
        return json.dumps(
            log_record,
            ensure_ascii=False,
            default=str,
        )

def setup_logging():
    root_logger = logging.getLogger()
    if getattr(root_logger, "_custom_logging_configured", False):
        return

    formatter = CustomJsonFormatter()

    # 终端 handler（始终保留）
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    handlers = [console_handler]

    # 文件 handler（根据配置决定是否启用）
    # 注意：日志写不了不应该让服务起不来（只读文件系统 / 权限配置错误 / 磁盘满）
    log_file = settings.log_file.strip()  # 去除可能的多余空格
    if log_file:
        try:
            log_dir = os.path.dirname(log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)

            file_handler = TimedRotatingFileHandler(
                log_file,
                when="midnight",
                backupCount=30,
                encoding="utf-8",
            )
            file_handler.suffix = "%Y-%m-%d"
            file_handler.setFormatter(formatter)
            handlers.append(file_handler)
        except OSError as exc:
            # 降级为仅控制台输出，不阻塞应用启动
            logging.getLogger("app.core.middlewares").warning(
                "文件日志初始化失败，已降级为仅控制台输出: %s", exc
            )

    # 设置日志级别
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root_logger.setLevel(level)

    for h in root_logger.handlers:
        root_logger.removeHandler(h)
    for h in handlers:
        root_logger.addHandler(h)

    # 配置 uvicorn 日志
    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_logger.handlers = handlers.copy()
    uvicorn_logger.propagate = False

    root_logger._custom_logging_configured = True

# ---------- 请求日志中间件 ----------
def register_middleware(app:FastAPI):
    setup_logging()

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        # 生成并设置请求ID
        request_id = generate_request_id()
        set_request_id(request_id)
        # 将 request_id 存入 request.state，供异常处理器等使用
        request.state.request_id = request_id

        start_time = time.perf_counter()
        client_ip = request.client.host if request.client else "unknown"
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()

        logger = logging.getLogger("app.request")

        try:
            response = await call_next(request)
            process_time = time.perf_counter() - start_time
            logger.info(
                "请求完成",
                extra={
                    "event": "request_completed",
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round(process_time * 1000, 2),
                    "client_ip": client_ip,
                },
            )
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            ...