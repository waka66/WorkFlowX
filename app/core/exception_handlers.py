import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError, HTTPException
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppException

logger = logging.getLogger("app.core.exception_handlers")


# 框架层 HTTPException 的状态码 -> 业务错误码，保证响应信封与业务异常一致
_HTTP_STATUS_CODES = {
    400: "BAD_REQUEST",
    401: "NOT_AUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "UNPROCESSABLE_ENTITY",
    429: "TOO_MANY_REQUESTS",
    500: "INTERNAL_SERVER_ERROR",
}


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """统一框架抛出的 HTTPException（如未携带 token、路由不存在），
    避免出现 {"detail": ...} 与 {"code","message","request_id"} 两套格式。
    """
    request_id = getattr(request.state, "request_id", None)

    headers = dict(getattr(exc, "headers", None) or {})
    if exc.status_code == 401:
        headers.setdefault("WWW-Authenticate", "Bearer")

    logger.warning(
        "框架异常已处理",
        extra={
            "event": "http_exception",
            "request_id": request_id,
            "status_code": exc.status_code,
            "path": request.url.path,
        },
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": _HTTP_STATUS_CODES.get(exc.status_code, "HTTP_ERROR"),
            "message": str(exc.detail),
            "request_id": request_id,
        },
        headers=headers,
    )


async def app_exception_handler(
    request: Request,
    exc: AppException,
):
    """
    处理预期的业务异常（AppException 及其子类）。
    记录 INFO 级别日志，用于追踪业务规则拒绝原因。
    """
    request_id = getattr(request.state, "request_id", None)

    # 记录预期异常（级别 INFO，不会触发告警，但可追溯）
    logger.warning(
        "业务异常已处理",
        extra={
            "event": "business_exception",
            "request_id": request_id,
            "exception_type": type(exc).__name__,
            "error_code": exc.code,
            "error_message": exc.message,
            "status_code": exc.status_code,
        },
    )

    headers = {}
    if exc.status_code == 401:
        headers["WWW-Authenticate"] = "Bearer"

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "request_id": request_id,
        },
        headers=headers,
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """处理请求参数验证错误（pydantic）"""
    request_id = getattr(request.state, "request_id", None)

    errors = exc.errors()
    if errors:
        # 取第一个错误作为主要消息（也可以拼接所有错误）
        first_error = errors[0]
        # 构造字段路径，如 "body.password" 或 "query.page"
        field = ".".join(str(loc) for loc in first_error.get("loc", []))
        msg = first_error.get("msg", "Validation error")
        message = f"{field}: {msg}" if field else msg
    else:
        message = "Validation error"

    # 日志中添加 event 字段
    logger.warning(
        "请求参数验证失败",
        extra={
            "event": "request_validation_failed",
            "request_id": request_id,
            "error_count": len(errors),
            "first_error": errors[0] if errors else None,
            "path": request.url.path
        },
    )

    return JSONResponse(
        status_code=422,
        content={
            "code": "VALIDATION_ERROR",
            "message": message,
            "request_id": request_id
        },
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
):
    """
    处理未预期的异常。
    记录 ERROR 级别日志，并附带完整堆栈（通过 logger.exception 自动添加）。
    这是记录未预期异常详细信息的唯一位置，避免与中间件重复。
    """
    request_id = getattr(request.state, "request_id", None)

    # logger.exception 会在日志中自动添加 exc_info 字段，包含完整堆栈
    logger.exception(
        "未处理异常发生",
        extra={
            "event": "unhandled_exception",
            "request_id": request_id,
            "exception_type": type(exc).__name__,
            # 可选：添加异常简要消息，完整堆栈在 exc_info 中
            "exception_message": str(exc),
        },
    )

    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_SERVER_ERROR",
            "message": "Internal server error",
            "request_id": request_id,
        },
    )