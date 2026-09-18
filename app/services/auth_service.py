from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from fastapi import HTTPException
from starlette import status
from datetime import datetime, timezone
import hashlib
import logging

from app.common.schemas import RegisterRequest,GlobalRole,LoginRequest,RefreshTokenRequest, ChangePasswordRequest
from app.models.user import User,UserSession
from app.core.security import get_password_hash,verify_password
from app.core.security import create_refresh_token_hash,create_user_access_token
from app.core.exceptions import UnauthorizedError, PermissionDeniedError, ResourceNotFoundError, BadRequestError


# 获取当前时间
now = datetime.now(timezone.utc)

logger = logging.getLogger("app.services.auth_service")


async def get_user_by_username(db: AsyncSession, username: str):  # 根据用户名查询是否存在
    query = select(User).where(User.username == username)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str):  # 根据邮箱查询是否存在
    query = select(User).where(User.email == email)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, user_data: RegisterRequest):  # 创建用户

    hashed_password = get_password_hash(user_data.password)
    user = User(
        username=user_data.username,
        hashed_password=hashed_password,
        display_name=user_data.display_name or user_data.username,
        email=user_data.email,
        global_role=GlobalRole.USER,
    )
    db.add(user)

    await db.commit()
    await db.refresh(user)

    logger.info(
        "用户创建成功",
        extra={
            "event": "user_created",
            "user_id": user.id,
            "username": user.username,
        },
    )

    return user


async def authenticate_user(db: AsyncSession, username: str, password: str):  # 验证账号密码
    user = await get_user_by_username(db, username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None

    return user


async def create_user_token(db: AsyncSession, user: User, user_data: LoginRequest, ip_address: str):  # 创建token
    access_token, expires_in = create_user_access_token(user)
    refresh_token, refresh_token_hash, expire_at = create_refresh_token_hash()

    result = await db.execute(
        select(UserSession).where(
            UserSession.user_id == user.id,
            UserSession.device_id == user_data.device_id,
        )
    )
    user_session = result.scalar_one_or_none()


    if user_session:
        # 已经登录过这个设备 → 更新
        user_session.refresh_token_hash = refresh_token_hash
        user_session.device_name = user_data.device_name
        user_session.user_agent = user_data.user_agent
        user_session.ip_address = ip_address
        user_session.expire_at = expire_at
        user_session.revoked_at = None
        user_session.last_used_at = now

    else:
        # 第一次使用这个设备 → 创建
        user_session = UserSession(
            user_id=user.id,
            refresh_token_hash=refresh_token_hash,
            device_id=user_data.device_id,
            device_name=user_data.device_name,
            user_agent=user_data.user_agent,
            ip_address=ip_address,
            expire_at=expire_at,
            last_used_at=now,
        )

        db.add(user_session)

    await db.commit()
    await db.refresh(user_session)

    logger.info(
        "用户登录成功",
        extra={
            "event": "user_login_success",
            "user_id": user.id,
            "username": user.username,
            "device_id": user_data.device_id,
            "device_name": user_data.device_name,
            "ip_address": ip_address,
            "expires_in": expires_in,
        },
    )
    return user_session, access_token, refresh_token, expires_in


async def refresh_user_token(db: AsyncSession, token_data: RefreshTokenRequest):
    refresh_token_hash = hashlib.sha256(token_data.refresh_token.encode()).hexdigest()

    result = await db.execute(select(UserSession).where(
        UserSession.refresh_token_hash == refresh_token_hash,
            UserSession.device_id == token_data.device_id,
        )
    )
    session = result.scalar_one_or_none()

    if session is None:
        raise UnauthorizedError(code="SESSION_NOT_FOUND",message="会话不存在")
    if session.revoked_at is not None:
        raise UnauthorizedError(code="SESSION_REVOKED",message="会话已撤销")
    if session.expire_at <= now:
        raise UnauthorizedError(code="SESSION_EXPIRED",message="会话已过期，请重新登录")

    result2 = await db.execute(select(User).where(User.id == session.user_id))
    user = result2.scalar_one_or_none()

    if user is None:
        raise UnauthorizedError(code="USER_NOT_FOUND",message="用户不存在")
    if not user.is_active:
        raise PermissionDeniedError(code="USER_INACTIVE",message="用户已禁用")

    access_token, expires_in = create_user_access_token(user)
    refresh_token, new_refresh_token_hash, _ = create_refresh_token_hash()

    session.refresh_token_hash = new_refresh_token_hash
    session.last_used_at = now

    await db.commit()
    await db.refresh(session)

    logger.info(
        "用户刷新令牌成功",
        extra={
            "event": "user_refresh_token_success",
            "user_id": user.id,
            "username": user.username,
            "device_id": token_data.device_id,
            "expires_in": expires_in,
            "ip_address": session.ip_address,
        },
    )

    return session, access_token, refresh_token, expires_in, user

# 注销指定设备的会话
async def logout(db: AsyncSession, user: User, device_id: str) -> str:
    # 查找该用户在该设备上的有效会话（未吊销且未过期）
    stmt = select(UserSession).where(
        UserSession.user_id == user.id,
        UserSession.device_id == device_id,
        UserSession.revoked_at.is_(None),
        UserSession.expire_at > now
    )
    result = await db.execute(stmt)
    session_record = result.scalar_one_or_none()

    if not session_record:
        all_sessions = await db.execute(
            select(UserSession).where(UserSession.user_id == user.id)
        )
        sessions_info = [
            {
                "device_id": s.device_id,
                "revoked_at": str(s.revoked_at) if s.revoked_at else None,
                "expire_at": str(s.expire_at),
            }
            for s in all_sessions.scalars().all()
        ]
        logger.warning(
            "logout未找到活跃会话",
            extra={
                "event": "logout_no_active_session",
                "user_id": user.id,
                "requested_device_id": device_id,
                "existing_sessions": sessions_info,
            },
        )
        raise ResourceNotFoundError(code="ACTIVE_SESSION_NOT_FOUND", message="未找到该设备的活跃会话")


    # 标记为已吊销
    session_record.revoked_at = now
    await db.commit()

    logger.info(
        "用户退出登录成功",
        extra={
            "event": "user_logout_success",
            "user_id": user.id,
            "username": user.username,
            "device_id": device_id,
        },
    )

    return "登出成功"

# 注销当前用户的所有会话
async def logout_all(db: AsyncSession, user: User) -> str:
    # 批量更新所有未吊销且未过期的会话
    stmt = (
        update(UserSession)
        .where(
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
            UserSession.expire_at > now
        )
        .values(revoked_at=now)
    )
    result = await db.execute(stmt)
    await db.commit()

    if result.rowcount == 0:
        # 没有需要注销的会话，但仍可返回成功（幂等）
        logger.info(
            "用户退出全部设备（无活跃会话）",
            extra={
                "event": "user_logout_all_no_active_session",
                "user_id": user.id,
                "username": user.username,
                "revoked_count": 0,
            },
        )
        return "注销成功（无活跃会话）"
    logger.info(
        "用户退出全部设备成功",
        extra={
            "event": "user_logout_all_success",
            "user_id": user.id,
            "username": user.username,
            "revoked_count": result.rowcount,
        },
    )
    return "全部设备已登出"

async def get_active_sessions(db: AsyncSession, user: User) -> list[UserSession]:
    """获取用户所有有效的会话（未吊销且未过期）"""
    stmt = select(UserSession).where(
        UserSession.user_id == user.id,
        UserSession.revoked_at.is_(None),
        UserSession.expire_at > now
    ).order_by(UserSession.last_used_at.desc())  # 最近使用的排前面
    result = await db.execute(stmt)
    return list(result.scalars().all())

async def get_user_by_id(db: AsyncSession, user_id: int):
    query = select(User).where(User.id == user_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()

async def update_password(db: AsyncSession,user: User,user_data: ChangePasswordRequest):

    if not verify_password(user_data.old_password,user.hashed_password):
        raise BadRequestError(code="INVALID_OLD_PASSWORD", message="旧密码错误")
    else:
        user.hashed_password = get_password_hash(user_data.new_password)

    await db.execute(update(UserSession).where(UserSession.user_id == user.id).values(revoked_at=datetime.now(timezone.utc)))

    await db.commit()
    return "密码修改成功"



