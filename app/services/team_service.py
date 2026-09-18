from typing import Optional
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.models.team import Team, TeamMember, TeamRole, TeamStatus
from app.common.schemas import CreateTeamRequest, UpdateTeamRequest, TeamMemberList, AddTeamMemberRequest,UpdateTeamMemberRoleRequest
from app.models.user import User, GlobalRoleEnum
from app.core.exceptions import ConflictError, PermissionDeniedError, ResourceNotFoundError


logger = logging.getLogger("app.services.team_service")


async def create_team(db: AsyncSession, creator_id: int, data: CreateTeamRequest) -> Team:
    # 创建团队记录
    team = Team(
        name=data.name,
        description=data.description,
        creator_id=creator_id,
        status=TeamStatus.active
    )
    db.add(team)
    try:
        await db.flush()  # 获取团队 ID

        # 创建者自动成为 OWNER 成员
        member = TeamMember(
            team_id=team.id,
            user_id=creator_id,
            role=TeamRole.OWNER
        )
        db.add(member)

        await db.commit()
    except IntegrityError:
        raise ConflictError(
            code="TEAM_NAME_ALREADY_EXISTS",
            message="团队名称已存在",
        )

    logger.info(
        "团队创建成功",
        extra={
            "event": "team_created",
            "team_id": team.id,
            "team_name": team.name,
            "creator_id": creator_id,
        },
    )

    return team


async def list_teams(
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        keyword: Optional[str] = None,
        status: Optional[TeamStatus] = None,
        is_admin: bool = False,
) -> tuple[list[Team], int]:
    """
    获取团队分页列表。
    - 管理员：默认所有状态；普通用户：默认仅 active。
    - 支持关键字搜索和状态筛选。
    """
    conditions = []

    # 关键字搜索：按名称模糊匹配
    if keyword:
        conditions.append(Team.name.ilike(f"%{keyword}%"))

    # 状态过滤
    if status:
        conditions.append(Team.status == status)
    elif not is_admin:
        # 非管理员默认只看活跃团队
        conditions.append(Team.status == TeamStatus.active)

    # 总数查询
    count_stmt = select(func.count()).select_from(Team)
    if conditions:
        count_stmt = count_stmt.where(*conditions)
    total = (await db.execute(count_stmt)).scalar_one()

    # 分页数据查询
    stmt = select(Team)
    if conditions:
        stmt = stmt.where(*conditions)
    stmt = stmt.order_by(Team.id.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    teams = list(result.scalars().all())

    return teams, total


async def get_team_detail(db: AsyncSession, team_id: int, current_user: User) -> Team:
    # 查询团队并加载成员及其用户信息
    stmt = (
        select(Team)
        .where(Team.id == team_id)
        .options(selectinload(Team.members).selectinload(TeamMember.user))
    )
    result = await db.execute(stmt)
    team = result.scalar_one_or_none()
    if not team:
        raise ResourceNotFoundError(
            code="TEAM_NOT_FOUND",
            message="团队不存在",
        )

    # 权限检查：归档团队仅管理员或团队成员可访问
    if team.status == TeamStatus.archived:
        is_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN
        is_member = any(m.user_id == current_user.id for m in team.members)
        if not (is_admin or is_member):
            raise PermissionDeniedError(
                code="TEAM_ARCHIVED_ACCESS_DENIED",
                message="无权访问归档团队",
            )

    return team


async def update_team(
        db: AsyncSession,
        team_id: int,
        current_user: User,
        update_data: UpdateTeamRequest,
) -> Team:
    # 查询团队并加载成员
    stmt = (
        select(Team)
        .where(Team.id == team_id)
        .options(selectinload(Team.members))
    )
    result = await db.execute(stmt)
    team = result.scalar_one_or_none()
    if not team:
        raise ResourceNotFoundError(
            code="TEAM_NOT_FOUND",
            message="团队不存在",
        )

    # 获取当前用户在团队中的成员记录
    member_record = next((m for m in team.members if m.user_id == current_user.id), None)
    is_system_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN

    # 权限判断
    if not is_system_admin and not member_record:
        raise PermissionDeniedError(
            code="TEAM_UPDATE_DENIED",
            message="无权更新该团队",
        )

    # 获取当前用户角色
    user_role = member_record.role if member_record else None

    # 定义字段级权限
    can_update_all = is_system_admin or (user_role == TeamRole.OWNER)
    can_update_basic = can_update_all or (user_role == TeamRole.ADMIN)
    can_update_status = can_update_all  # 仅 OWNER 或系统管理员可以修改状态

    fields_to_update = update_data.model_fields_set

    # 如果用户是 ADMIN 且请求中包含了 status 字段，则拒绝
    if not can_update_status and "status" in fields_to_update:
        raise PermissionDeniedError(
            code="TEAM_STATUS_UPDATE_DENIED",
            message="无权修改团队状态",
        )

    # 如果用户没有任何更新权限（既不是 admin 也不是 owner），则拒绝整个请求
    if not can_update_basic:
        raise PermissionDeniedError(
            code="TEAM_UPDATE_DENIED",
            message="无权更新团队",
        )

    # 应用更新
    if "name" in fields_to_update and update_data.name is not None:
        # 名称非空才更新
        team.name = update_data.name
    if "description" in fields_to_update:
        # 允许显式清空（None）
        team.description = update_data.description
    if "status" in fields_to_update and update_data.status is not None:
        team.status = update_data.status

    # 更新 updated_at 由模型自动处理（onupdate=datetime.utcnow）
    try:
        await db.commit()
    except IntegrityError:
        raise ConflictError(
            code="TEAM_NAME_ALREADY_EXISTS",
            message="团队名称已存在",
        )
    await db.refresh(team)

    logger.info(
        "团队信息更新成功",
        extra={
            "event": "team_updated",
            "team_id": team.id,
            "team_name": team.name,
            "operator_id": current_user.id,
            "updated_fields": sorted(fields_to_update),
        },
    )
    return team


async def archive_team(db: AsyncSession, team_id: int, current_user: User) -> str:
    # 查询团队及其成员
    stmt = (
        select(Team)
        .where(Team.id == team_id)
        .options(selectinload(Team.members))
    )
    result = await db.execute(stmt)
    team = result.scalar_one_or_none()
    if not team:
        raise ResourceNotFoundError(
            code="TEAM_NOT_FOUND",
            message="团队不存在",
        )

    # 获取当前用户的成员记录
    member_record = next((m for m in team.members if m.user_id == current_user.id), None)
    is_system_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN

    # 权限检查：仅系统管理员或团队 OWNER 可以归档
    if not is_system_admin and (not member_record or member_record.role != TeamRole.OWNER):
        raise PermissionDeniedError(
            code="TEAM_ARCHIVE_DENIED",
            message="无权归档该团队",
        )

    # 如果团队已经是 archived，直接返回成功消息（幂等）
    if team.status == TeamStatus.archived:
        return "团队已归档"

    # 执行归档
    team.status = TeamStatus.archived
    # updated_at 自动更新
    await db.commit()

    logger.info(
        "团队归档成功",
        extra={
            "event": "team_archived",
            "team_id": team.id,
            "team_name": team.name,
            "operator_id": current_user.id,
        },
    )
    return "团队归档成功"


async def list_team_members(db: AsyncSession, team_id: int, current_user: User) -> TeamMemberList:
    # 查询团队，并预加载成员及成员对应的用户信息
    stmt = (
        select(Team)
        .where(Team.id == team_id)
        .options(selectinload(Team.members).selectinload(TeamMember.user))
    )
    result = await db.execute(stmt)
    team = result.scalar_one_or_none()
    if not team:
        raise ResourceNotFoundError(
            code="TEAM_NOT_FOUND",
            message="团队不存在",
        )

    # 权限检查：归档团队仅管理员或团队成员可查看
    if team.status == TeamStatus.archived:
        is_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN
        is_member = any(m.user_id == current_user.id for m in team.members)
        if not (is_admin or is_member):
            raise PermissionDeniedError(
                code="TEAM_MEMBER_ACCESS_DENIED",
                message="无权访问归档团队的成员列表",
            )

    # 构建响应数据
    return TeamMemberList(
        items=team.members,
        total=len(team.members)
    )


async def add_team_member(
    db: AsyncSession,
    team_id: int,
    current_user: User,
    data: AddTeamMemberRequest,
) -> TeamMember:
    # 1. 查询团队并预加载成员（用于权限检查和重复判断）
    stmt = (
        select(Team)
        .where(Team.id == team_id)
        .options(selectinload(Team.members))
    )
    result = await db.execute(stmt)
    team = result.scalar_one_or_none()
    if not team:
        raise ResourceNotFoundError(
            code="TEAM_NOT_FOUND",
            message="团队不存在",
        )

    # 2. 归档团队不允许添加成员
    if team.status == TeamStatus.archived:
        raise PermissionDeniedError(
            code="TEAM_ARCHIVED",
            message="归档团队不能添加成员",
        )

    # 3. 获取当前用户在团队中的角色
    member_record = next((m for m in team.members if m.user_id == current_user.id), None)
    is_sys_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN

    if not is_sys_admin and not member_record:
        raise PermissionDeniedError(
            code="TEAM_MEMBER_ADD_DENIED",
            message="无权添加团队成员",
        )

    user_role = member_record.role if member_record else None

    # 4. 权限分级
    can_add_any = is_sys_admin or (user_role == TeamRole.OWNER)
    can_add_limited = can_add_any or (user_role == TeamRole.ADMIN)

    if not can_add_limited:
        raise PermissionDeniedError(
            code="TEAM_MEMBER_ADD_DENIED",
            message="无权添加团队成员",
        )

    # 5. 角色分配限制：只有 OWNER 或系统管理员可以分配 OWNER 角色
    if data.role == TeamRole.OWNER and not can_add_any:
        raise PermissionDeniedError(
            code="TEAM_OWNER_ROLE_ASSIGN_DENIED",
            message="无权分配OWNER角色",
        )

    # 6. 检查目标用户是否存在
    target_user = (await db.execute(select(User).where(User.id == data.user_id))).scalar_one_or_none()
    if not target_user:
        raise ResourceNotFoundError(
            code="USER_NOT_FOUND",
            message="被添加的用户不存在",
        )

    # 7. 检查是否已是团队成员
    if any(m.user_id == data.user_id for m in team.members):
        raise ConflictError(
            code="TEAM_MEMBER_ALREADY_EXISTS",
            message="用户已是团队成员",
        )

    # 8. 创建新成员记录
    new_member = TeamMember(
        team_id=team.id,
        user_id=data.user_id,
        role=data.role,
        # joined_at 自动填充
    )
    db.add(new_member)
    await db.commit()

    # 9. 重新查询并加载 user 关系，以便序列化时能获取 username 和 display_name
    stmt = (
        select(TeamMember)
        .where(TeamMember.id == new_member.id)
        .options(selectinload(TeamMember.user))
    )
    result = await db.execute(stmt)
    member_with_user = result.scalar_one()

    logger.info(
        "团队成员添加成功",
        extra={
            "event": "team_member_added",
            "team_id": team.id,
            "user_id": member_with_user.user_id,
            "role": data.role.value,
            "operator_id": current_user.id,
        },
    )
    return member_with_user


async def update_team_member_role(
        db: AsyncSession,
        team_id: int,
        target_user_id: int,
        current_user: User,
        data: UpdateTeamMemberRoleRequest,
) -> TeamMember:
    # 1. 查询团队并预加载成员及用户信息
    stmt = (
        select(Team)
        .where(Team.id == team_id)
        .options(selectinload(Team.members).selectinload(TeamMember.user))
    )
    result = await db.execute(stmt)
    team = result.scalar_one_or_none()
    if not team:
        raise ResourceNotFoundError(
            code="TEAM_NOT_FOUND",
            message="团队不存在",
        )

    # 2. 检查团队是否归档
    if team.status == TeamStatus.archived:
        raise PermissionDeniedError(
            code="TEAM_ARCHIVED",
            message="归档团队不能调整成员角色",
        )

    # 3. 查找当前用户和目标的成员记录
    current_member = next((m for m in team.members if m.user_id == current_user.id), None)
    target_member = next((m for m in team.members if m.user_id == target_user_id), None)

    if not target_member:
        raise ResourceNotFoundError(
            code="TEAM_MEMBER_NOT_FOUND",
            message="目标用户不是团队成员",
        )

    is_sys_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN
    is_team_owner = current_member and current_member.role == TeamRole.OWNER

    # 4. 权限判断
    if not (is_sys_admin or is_team_owner):
        raise PermissionDeniedError(
            code="TEAM_MEMBER_ROLE_UPDATE_DENIED",
            message="无权调整团队成员角色",
        )

    # 5. 特殊限制：OWNER 不能修改自己的角色（防止团队失去所有者）
    if is_team_owner and current_member.user_id == target_user_id:
        raise PermissionDeniedError(
            code="TEAM_OWNER_ROLE_SELF_UPDATE_DENIED",
            message="OWNER不能修改自己的角色",
        )

    # 6. 角色分配限制：只有系统管理员或 OWNER 可以分配 OWNER 角色
    if data.role == TeamRole.OWNER and not (is_sys_admin or is_team_owner):
        # 这个分支实际上不会到达，因为前面已经限制了只有 sys_admin 或 owner 才能执行
        # 但为了可读性保留检查
        raise PermissionDeniedError(
            code="TEAM_OWNER_ROLE_ASSIGN_DENIED",
            message="无权分配OWNER角色",
        )

    # 7. 更新角色
    old_role = target_member.role.value
    target_member.role = data.role
    await db.commit()

    logger.info(
        "团队成员角色调整成功",
        extra={
            "event": "team_member_role_updated",
            "team_id": team.id,
            "user_id": target_user_id,
            "old_role": old_role,
            "new_role": data.role.value,
            "operator_id": current_user.id,
        },
    )

    # 8. 返回更新后的成员（已预加载 user 关系）
    return target_member


async def remove_team_member(
        db: AsyncSession,
        team_id: int,
        target_user_id: int,
        current_user: User,
) -> str:
    # 1. 查询团队并预加载成员
    stmt = (
        select(Team)
        .where(Team.id == team_id)
        .options(selectinload(Team.members))
    )
    result = await db.execute(stmt)
    team = result.scalar_one_or_none()
    if not team:
        raise ResourceNotFoundError(
            code="TEAM_NOT_FOUND",
            message="团队不存在",
        )

    if team.status == TeamStatus.archived:
        raise PermissionDeniedError(
            code="TEAM_ARCHIVED",
            message="归档团队不能移除成员",
        )

    # 2. 定位当前用户和目标用户的成员记录
    current_member = next((m for m in team.members if m.user_id == current_user.id), None)
    target_member = next((m for m in team.members if m.user_id == target_user_id), None)

    if not target_member:
        raise ResourceNotFoundError(
            code="TEAM_MEMBER_NOT_FOUND",
            message="目标用户不是团队成员",
        )

    is_sys_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN
    current_role = current_member.role if current_member else None
    target_role = target_member.role

    # 3. 权限检查
    # 系统管理员：可以移除任何人
    if is_sys_admin:
        pass
    # OWNER：可以移除 ADMIN 和 MEMBER，但不能移除 OWNER
    elif current_role == TeamRole.OWNER:
        if target_role == TeamRole.OWNER:
            raise PermissionDeniedError(
                code="TEAM_OWNER_REMOVE_DENIED",
                message="OWNER不能被移除",
            )
        # 可以移除 ADMIN 和 MEMBER
    # ADMIN：可以移除 MEMBER，但不能移除自己或其他 ADMIN/OWNER
    elif current_role == TeamRole.ADMIN:
        if target_user_id == current_user.id:
            raise PermissionDeniedError(
                code="TEAM_ADMIN_SELF_REMOVE_DENIED",
                message="ADMIN不能自我移除，请联系OWNER",
            )
        if target_role in (TeamRole.ADMIN, TeamRole.OWNER):
            raise PermissionDeniedError(
                code="TEAM_MEMBER_REMOVE_DENIED",
                message="无权移除该角色成员",
            )
    # MEMBER：只能移除自己（退出团队）
    elif current_role == TeamRole.MEMBER:
        if target_user_id != current_user.id:
            raise PermissionDeniedError(
                code="TEAM_MEMBER_REMOVE_DENIED",
                message="普通成员只能退出自己",
            )
    else:
        # 非成员
        raise PermissionDeniedError(
            code="TEAM_MEMBER_REMOVE_DENIED",
            message="无权移除团队成员",
        )

    # 4. 执行删除
    removed_role = target_member.role.value
    await db.delete(target_member)
    await db.commit()

    logger.info(
        "团队成员移除成功",
        extra={
            "event": "team_member_removed",
            "team_id": team.id,
            "user_id": target_user_id,
            "removed_role": removed_role,
            "operator_id": current_user.id,
            "self_removal": target_user_id == current_user.id,
        },
    )

    return "成员移除成功"



