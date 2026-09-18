from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
import logging
from typing import Optional

from app.common.schemas import  UserUpdateRequest, UserStatus
from app.models.user import User, GlobalRoleEnum
from app.core.exceptions import ResourceNotFoundError, PermissionDeniedError


logger = logging.getLogger("app.services.user_service")


async def list_users(
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        keyword: Optional[str] = None,  #Optional[int] 翻译成人话就是：“这个值要么是一个整数（int），要么是空（None）”
        status: Optional[UserStatus] = None,
) -> tuple[list[User], int]:
    """
    查询用户列表（带分页和过滤）
    返回 (用户列表, 总数量)
    """
    # 构建基础条件
    conditions = []
    if keyword:
        # 按用户名或邮箱模糊匹配（不区分大小写）
        like_pattern = f"%{keyword}%"
        conditions.append(
            or_(
                User.username.ilike(like_pattern),
                User.email.ilike(like_pattern),
            )
        )
    if status:
        if status == UserStatus.active:
            conditions.append(User.is_active == True)
        elif status == UserStatus.disabled:
            conditions.append(User.is_active == False)

    # 查询总数
    count_stmt = select(func.count()).select_from(User)
    if conditions:
        count_stmt = count_stmt.where(*conditions)
    total = (await db.execute(count_stmt)).scalar_one()

    # 查询分页数据
    stmt = select(User)
    if conditions:
        stmt = stmt.where(*conditions)
    stmt = stmt.order_by(User.id.desc())  # 按 ID 倒序
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    users = list(result.scalars().all())

    return users, total


async def get_user_by_id(db: AsyncSession, user_id: int) -> User:
    """根据用户 ID 获取用户，不存在则抛出 404"""
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise ResourceNotFoundError(
            code="USER_NOT_FOUND",
            message="用户不存在",
        )
    return user


async def update_user(
    db: AsyncSession,
    user_id: int,
    update_data: UserUpdateRequest,
    operator: User,
) -> User:
    # 1. 查询目标用户
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise ResourceNotFoundError(code="USER_NOT_FOUND",message="用户不存在")

    is_admin = operator.global_role == GlobalRoleEnum.SYSTEM_ADMIN
    is_self = operator.id == user.id

    # 2. 普通用户只能修改自己
    if not is_admin and not is_self:
        raise PermissionDeniedError(code="CANNOT_MODIFY_OTHER_USER",message="无权修改其他用户的信息")

    fields_to_update = update_data.model_fields_set

    # 3. 权限字段仅管理员可改
    if not is_admin:
        if "global_role" in fields_to_update:
            raise PermissionDeniedError(code="CANNOT_MODIFY_ROLE", message="无权修改用户角色")
        if "status" in fields_to_update:
            raise PermissionDeniedError(code="CANNOT_MODIFY_STATUS", message="无权修改用户状态")

    # 4. 执行更新
    if "display_name" in fields_to_update:
        user.display_name = update_data.display_name  # 可能为 None，表示清空

    if "status" in fields_to_update and update_data.status is not None:
        user.is_active = (update_data.status == UserStatus.active)

    if "global_role" in fields_to_update and update_data.global_role is not None:
        user.global_role = update_data.global_role.value

    await db.commit()
    await db.refresh(user)

    logger.info(
        "用户信息更新成功",
        extra={
            "event": "user_updated",
            "user_id": user.id,
            "operator_id": operator.id,
            "is_admin": is_admin,
            "updated_fields": sorted(fields_to_update),
        },
    )
    return user
