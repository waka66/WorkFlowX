from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.db.session import get_db
from app.core.security import get_user_access_token
from app.services import auth_service
from app.common.schemas import GlobalRole
from app.core.exceptions import UnauthorizedError, PermissionDeniedError, PermissionDeniedError


async def get_current_user(
    payload: dict = Depends(get_user_access_token),
    db: AsyncSession = Depends(get_db),
) -> User:
    user_id = payload.get("sub")

    if user_id is None:
        raise UnauthorizedError(code="TOKEN_MISSING_USER_INFO",message="Token缺少用户信息")

    user = await auth_service.get_user_by_id(db, int(user_id))

    if user is None:
        raise UnauthorizedError(code="USER_NOT_FOUND",message="用户不存在")

    if not user.is_active:
        raise PermissionDeniedError(code="USER_INACTIVE",message="用户已禁用")

    return user

async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.global_role != GlobalRole.SYSTEM_ADMIN:
        raise PermissionDeniedError(
            code="ADMIN_REQUIRED",
            message="权限不足，需要管理员权限"
        )
    return user