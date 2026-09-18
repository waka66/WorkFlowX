from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, Query, Path

from app.services import user_service
from app.common.schemas import PaginatedUsers, UserStatus, UserResponse, UserUpdateRequest
from app.db.session import get_db
from app.models.user import User
from app.api.deps import get_current_user, require_admin

router = APIRouter(prefix="/users", tags=["Users"])

@router.get(
    "/",
    response_model=PaginatedUsers,
    summary="用户列表",
    status_code=200,
)
async def list_users(
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    keyword: str | None = Query(None, max_length=100, description="按用户名或邮箱搜索"),
    status: UserStatus | None = Query(None, description="按状态筛选"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    users, total = await user_service.list_users(
        db, page=page, page_size=page_size, keyword=keyword, status=status
    )

    # 计算 has_more
    has_more = (page * page_size) < total

    return PaginatedUsers(
        items=users,
        total=total,
        page=page,
        page_size=page_size,
        has_more=has_more,
    )


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    status_code=200
)
async def get_user(
    user_id: int = Path(..., ge=1, description="用户 ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),  # 仅管理员可访问，返回值忽略
):
    user = await user_service.get_user_by_id(db, user_id)
    return user


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    summary="更新用户资料或角色",
    operation_id="updateUser",
    status_code=200,
)
async def update_user(
    user_id: int = Path(..., ge=1, description="用户 ID"),
    update_data: UserUpdateRequest = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),   # 只需登录
):
    user = await user_service.update_user(
        db,
        user_id,
        update_data,
        operator=current_user,   # 传整个 operator 对象，便于判断角色
    )
    return user













