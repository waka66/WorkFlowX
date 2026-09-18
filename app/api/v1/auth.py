from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, Request, Path
from starlette import status
from typing import List

from app.common.schemas import (RegisterRequest, UserResponse, LoginRequest, AuthTokensResponse,
                                RefreshTokenRequest, ChangePasswordRequest, MessageResponse,
                                LogoutRequest, UserSessionResponse)
from app.services import auth_service
from app.db.session import get_db
from app.models.user import User
from app.api.deps import get_current_user
from app.core.exceptions import ConflictError, UnauthorizedError



router = APIRouter(prefix="/auth", tags=["Auth"])

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=201
)  # 用户注册
async def register_user(
        user_data : RegisterRequest,
        db: AsyncSession = Depends(get_db)
):
    existing_user = await auth_service.get_user_by_username(db, user_data.username)
    if existing_user:
        raise ConflictError(code="USERNAME_ALREADY_EXISTS", message="用户名已存在")
    if user_data.email:
        existing_email = await auth_service.get_user_by_email(db, user_data.email)
        if existing_email:
            raise ConflictError(code="EMAIL_ALREADY_EXISTS", message="邮箱已存在")

    user_obj = await auth_service.create_user(db, user_data)

    return user_obj


@router.post(
    "/login",
    response_model=AuthTokensResponse,
    status_code=200
)     # 登录
async def login_user(
        user_data: LoginRequest,
        request: Request,
        db: AsyncSession = Depends(get_db)
):
    user = await auth_service.authenticate_user(db, user_data.username, user_data.password)
    if not user:
        raise UnauthorizedError(code="INVALID_CREDENTIALS", message="用户名或密码错误")

    ip_address = request.client.host

    (user_session,access_token,refresh_token,expires_in) = await auth_service.create_user_token(db, user, user_data, ip_address)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": expires_in,
        "session_id": user_session.id,
        "user": user
    }


@router.post(
    "/refresh",
    response_model=AuthTokensResponse,
    status_code=200
)  # 刷新token
async def refresh_token(
        token_data: RefreshTokenRequest,
        db: AsyncSession = Depends(get_db)
):
    (user_session,access_token,refresh_token,expires_in,user) = await auth_service.refresh_user_token(db, token_data)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": expires_in,
        "session_id": user_session.id,
        "user": user
    }


# 注销指定设备
@router.post(
    "/logout",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK
)
async def logout(
    logout_data: LogoutRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    message = await auth_service.logout(db, current_user, logout_data.device_id)
    return {"message": message}


# 注销所有设备
@router.post(
    "/logout-all",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK
)
async def logout_all(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    message = await auth_service.logout_all(db, current_user)
    return {"message": message}


@router.get(
    "/sessions",
    response_model=List[UserSessionResponse],
    status_code=200,
    summary="获取当前用户登录会话"
)
async def get_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    sessions = await auth_service.get_active_sessions(db, current_user)
    return sessions


@router.delete(
    "/sessions/{device_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="指定设备登出"
)
async def revoke_session_by_device(
    device_id: str = Path(..., description="设备ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    message = await auth_service.logout(db, current_user, device_id)
    return {"message": message}


@router.post(
    "/change-password",
    response_model=MessageResponse,
    status_code=200
)  # 修改密码
async def change_password(
        user_data: ChangePasswordRequest,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    message = await auth_service.update_password(db, current_user, user_data)

    return {"message": message}


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=200,
    summary="获取当前用户信息"
)
async def get_user(
        current_user: User = Depends(get_current_user)
):

    return current_user

