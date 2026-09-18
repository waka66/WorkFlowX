from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload, defer
from sqlalchemy.exc import IntegrityError
from typing import Optional
import logging



from app.common.schemas import CreateProjectRequest, ProjectStatus, UpdateProjectRequest, ProjectMemberList, AddProjectMemberRequest,UpdateProjectMemberRoleRequest
from app.models.user import User, GlobalRoleEnum
from app.models.team import Team, TeamRole, TeamStatus, TeamMember
from app.models.project import Project, ProjectMember, ProjectRole
from app.core.exceptions import BadRequestError, ConflictError, PermissionDeniedError, ResourceNotFoundError


logger = logging.getLogger("app.services.project_service")


async def create_project(
        db: AsyncSession,
        team_id: int,
        current_user: User,
        data: CreateProjectRequest,
) -> Project:
    # 1. 查询团队及成员
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

    # 2. 归档团队不能创建项目
    if team.status == TeamStatus.archived:
        raise PermissionDeniedError(
            code="TEAM_ARCHIVED",
            message="归档团队不能创建项目",
        )

    # 3. 权限检查
    current_member = next((m for m in team.members if m.user_id == current_user.id), None)
    is_sys_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN
    if not is_sys_admin and (not current_member or current_member.role not in (TeamRole.OWNER, TeamRole.ADMIN)):
        raise PermissionDeniedError(
            code="PROJECT_CREATE_DENIED",
            message="无权创建项目",
        )

    # 4. 确定项目负责人
    owner_user_id = data.owner_user_id if data.owner_user_id is not None else current_user.id
    if owner_user_id != current_user.id and not is_sys_admin:
        # 只有 OWNER 或 ADMIN 可以指定其他人为负责人，但这里已通过角色检查，但仍需确保指定的人是团队成员
        pass  # 继续检查成员资格
    owner_is_member = any(m.user_id == owner_user_id for m in team.members)
    if not owner_is_member:
        raise BadRequestError(
            code="PROJECT_OWNER_NOT_TEAM_MEMBER",
            message="项目负责人必须是团队成员",
        )

    # 5. 日期校验
    if data.start_date and data.end_date and data.end_date < data.start_date:
        raise BadRequestError(
            code="PROJECT_DATE_RANGE_INVALID",
            message="截止日期不能早于开始日期",
        )

    # 6. 创建项目
    project = Project(
        team_id=team.id,
        name=data.name,
        description=data.description,
        owner_user_id=owner_user_id,
        start_date=data.start_date,
        end_date=data.end_date,
        status=data.status if data.status else ProjectStatus.planned,
        progress=0
    )
    db.add(project)
    await db.flush()  # 获取 project.id

    # 自动将负责人添加为项目成员
    owner_member = ProjectMember(
        project_id=project.id,
        user_id=owner_user_id,
        role=ProjectRole.OWNER,
    )
    db.add(owner_member)
    try:
        await db.commit()
    except IntegrityError:
        raise ConflictError(
            code="PROJECT_NAME_ALREADY_EXISTS",
            message="项目名称在该团队中已存在",
        )
    await db.refresh(project)

    logger.info(
        "项目创建成功",
        extra={
            "event": "project_created",
            "project_id": project.id,
            "project_name": project.name,
            "team_id": team.id,
            "owner_user_id": project.owner_user_id,
            "operator_id": current_user.id,
        },
    )
    return project


async def list_projects(
        db: AsyncSession,
        team_id: int,
        current_user: User,
        page: int = 1,
        page_size: int = 20,
        keyword: Optional[str] = None,
        status: Optional[ProjectStatus] = None,
) -> tuple[list[Project], int]:
    # 1. 查询团队及成员（用于权限判断）
    team_stmt = (
        select(Team)
        .where(Team.id == team_id)
        .options(selectinload(Team.members))
    )
    team_result = await db.execute(team_stmt)
    team = team_result.scalar_one_or_none()
    if not team:
        raise ResourceNotFoundError(
            code="TEAM_NOT_FOUND",
            message="团队不存在",
        )

    # 2. 归档团队权限控制
    if team.status == TeamStatus.archived:
        is_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN
        is_member = any(m.user_id == current_user.id for m in team.members)
        if not (is_admin or is_member):
            raise PermissionDeniedError(
                code="TEAM_ARCHIVED_ACCESS_DENIED",
                message="无权访问归档团队的项目",
            )

    # 3. 构建项目查询条件
    conditions = [Project.team_id == team_id]
    if keyword:
        conditions.append(Project.name.ilike(f"%{keyword}%"))
    if status:
        conditions.append(Project.status == status)

    # 4. 总数查询
    count_stmt = select(func.count()).select_from(Project).where(*conditions)
    total = (await db.execute(count_stmt)).scalar_one()

    # 5. 分页数据查询
    stmt = (
        select(Project)
        .where(*conditions)
        .order_by(Project.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    projects = list(result.scalars().all())

    return projects, total


async def get_project_detail(
    db: AsyncSession,
    project_id: int,
    current_user: User,
) -> Project:
    # 1. 查项目，只加载响应需要的关联（不加载 team.members）
    stmt = (
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.members)
                .selectinload(ProjectMember.user)
                .options(defer(User.hashed_password)),   # ← defer 挂在这里
            selectinload(Project.team),                  # 只加载 Team 本身
        )
    )
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        raise ResourceNotFoundError(
            code="PROJECT_NOT_FOUND",
            message="项目不存在",
        )

    # 2. 权限判断
    is_sys_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN
    is_project_member = any(
        m.user_id == current_user.id for m in project.members
    )

    # 3. 只有当"不是 admin 也不是项目成员"时，才去查是否团队成员
    is_team_member = False
    if not (is_sys_admin or is_project_member):
        is_team_member = (
            await db.scalar(
                select(TeamMember.id)
                .where(
                    TeamMember.team_id == project.team_id,
                    TeamMember.user_id == current_user.id,
                )
                .limit(1)
            )
        ) is not None

    # 4. 权限决策
    if project.status == ProjectStatus.archived:
        # 归档项目：仅系统管理员或项目成员可查看
        if not (is_sys_admin or is_project_member):
            raise PermissionDeniedError(
                code="PROJECT_ARCHIVED_ACCESS_DENIED",
                message="无权访问归档项目",
            )
    else:
        # 活跃项目：系统管理员、团队成员均可查看
        if not (is_sys_admin or is_team_member):
            raise PermissionDeniedError(
                code="PROJECT_ACCESS_DENIED",
                message="无权访问该项目",
            )

    return project


async def update_project(
        db: AsyncSession,
        project_id: int,
        current_user: User,
        data: UpdateProjectRequest,
) -> Project:
    # 1. 查询项目并预加载成员和团队信息
    stmt = (
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.members),
            selectinload(Project.team).selectinload(Team.members),
        )
    )
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        raise ResourceNotFoundError(
            code="PROJECT_NOT_FOUND",
            message="项目不存在",
        )

    # 2. 权限检查
    is_sys_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN
    is_project_owner = project.owner_user_id == current_user.id
    # 检查是否为团队 OWNER 或 ADMIN
    team = project.team
    current_team_member = next((m for m in team.members if m.user_id == current_user.id), None)
    is_team_admin = current_team_member and current_team_member.role in (TeamRole.OWNER, TeamRole.ADMIN)

    if not (is_sys_admin or is_project_owner or is_team_admin):
        raise PermissionDeniedError(
            code="PROJECT_UPDATE_DENIED",
            message="无权更新该项目",
        )

    # 3. 归档项目不允许更新（除非先激活？这里简单禁止）
    if project.status == ProjectStatus.archived:
        raise PermissionDeniedError(
            code="PROJECT_ARCHIVED",
            message="归档项目不能更新",
        )

    fields_to_update = data.model_fields_set

    # 4. 处理负责人变更
    if "owner_user_id" in fields_to_update and data.owner_user_id is not None:
        new_owner_id = data.owner_user_id
        # 确保新负责人是团队成员
        if not any(m.user_id == new_owner_id for m in team.members):
            raise BadRequestError(
                code="PROJECT_OWNER_NOT_TEAM_MEMBER",
                message="新项目负责人必须是团队成员",
            )
        # 如果需要，更新项目成员表：将新负责人添加为 OWNER 成员（如果还不是成员）
        existing_member = next((m for m in project.members if m.user_id == new_owner_id), None)
        if existing_member:
            # 如果已是成员，将其角色改为 OWNER
            existing_member.role = ProjectRole.OWNER
        else:
            # 否则添加为 OWNER 成员
            new_member = ProjectMember(
                project_id=project.id,
                user_id=new_owner_id,
                role=ProjectRole.OWNER,
            )
            db.add(new_member)
        # 原负责人角色降为 MEMBER（如果还是成员且不是系统管理员等特殊情况，这里简单处理）
        old_owner_member = next((m for m in project.members if m.user_id == project.owner_user_id), None)
        if old_owner_member and old_owner_member.role == ProjectRole.OWNER:
            old_owner_member.role = ProjectRole.MEMBER
        # 更新项目 owner_user_id
        project.owner_user_id = new_owner_id

    # 5. 更新其他字段
    if "name" in fields_to_update and data.name is not None:
        project.name = data.name
    if "description" in fields_to_update:
        project.description = data.description  # 可能为 None
    if "start_date" in fields_to_update:
        project.start_date = data.start_date  # 可能为 None
    if "end_date" in fields_to_update:
        project.end_date = data.end_date
    if "status" in fields_to_update and data.status is not None:
        project.status = data.status

    # 6. 日期校验
    if project.start_date and project.end_date and project.end_date < project.start_date:
        raise BadRequestError(
            code="PROJECT_DATE_RANGE_INVALID",
            message="截止日期不能早于开始日期",
        )

    # 7. 提交事务，处理唯一约束冲突
    try:
        await db.commit()
    except IntegrityError:
        raise ConflictError(
            code="PROJECT_NAME_ALREADY_EXISTS",
            message="项目名称在该团队中已存在",
        )
    await db.refresh(project)

    logger.info(
        "项目信息更新成功",
        extra={
            "event": "project_updated",
            "project_id": project.id,
            "project_name": project.name,
            "team_id": project.team_id,
            "owner_user_id": project.owner_user_id,
            "operator_id": current_user.id,
            "updated_fields": sorted(fields_to_update),
        },
    )
    return project


async def archive_project(
        db: AsyncSession,
        project_id: int,
        current_user: User,
) -> str:
    # 1. 查询项目并预加载成员和团队信息
    stmt = (
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.members),
            selectinload(Project.team).selectinload(Team.members),
        )
    )
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        raise ResourceNotFoundError(
            code="PROJECT_NOT_FOUND",
            message="项目不存在",
        )

    # 2. 权限检查
    is_sys_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN
    is_project_owner = project.owner_user_id == current_user.id
    team = project.team
    current_team_member = next((m for m in team.members if m.user_id == current_user.id), None)
    is_team_admin = current_team_member and current_team_member.role in (TeamRole.OWNER, TeamRole.ADMIN)

    if not (is_sys_admin or is_project_owner or is_team_admin):
        raise PermissionDeniedError(
            code="PROJECT_ARCHIVE_DENIED",
            message="无权归档该项目",
        )

    # 3. 已归档则幂等返回
    if project.status == ProjectStatus.archived:
        return "项目已归档"

    # 4. 执行归档
    project.status = ProjectStatus.archived
    # updated_at 自动更新
    await db.commit()

    logger.info(
        "项目归档成功",
        extra={
            "event": "project_archived",
            "project_id": project.id,
            "project_name": project.name,
            "team_id": project.team_id,
            "operator_id": current_user.id,
        },
    )
    return "项目归档成功"


async def list_project_members(
        db: AsyncSession,
        project_id: int,
        current_user: User,
) -> ProjectMemberList:
    # 查询项目，预加载成员、成员用户及团队信息
    stmt = (
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.members).selectinload(ProjectMember.user),
            selectinload(Project.team).selectinload(Team.members),
        )
    )
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        raise ResourceNotFoundError(
            code="PROJECT_NOT_FOUND",
            message="项目不存在",
        )

    # 权限检查
    is_sys_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN
    is_team_member = any(m.user_id == current_user.id for m in project.team.members)
    is_project_member = any(m.user_id == current_user.id for m in project.members)

    if project.status == ProjectStatus.archived:
        # 归档项目：仅系统管理员或项目成员可查看成员列表
        if not (is_sys_admin or is_project_member):
            raise PermissionDeniedError(
                code="PROJECT_MEMBER_ACCESS_DENIED",
                message="无权访问归档项目的成员列表",
            )
    else:
        # 活跃项目：系统管理员或团队成员可查看成员列表
        if not (is_sys_admin or is_team_member):
            raise PermissionDeniedError(
                code="PROJECT_MEMBER_ACCESS_DENIED",
                message="无权访问该项目成员列表",
            )

    # 返回成员列表
    return ProjectMemberList(
        items=project.members,
        total=len(project.members)
    )


async def add_project_member(
        db: AsyncSession,
        project_id: int,
        current_user: User,
        data: AddProjectMemberRequest,
) -> ProjectMember:
    # 1. 查询项目，预加载成员、团队及团队成员
    stmt = (
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.members).selectinload(ProjectMember.user),
            selectinload(Project.team).selectinload(Team.members),
        )
    )
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        raise ResourceNotFoundError(
            code="PROJECT_NOT_FOUND",
            message="项目不存在",
        )

    # 2. 归档项目不允许添加成员
    if project.status == ProjectStatus.archived:
        raise PermissionDeniedError(
            code="PROJECT_ARCHIVED",
            message="归档项目不能添加成员",
        )

    # 3. 权限检查：仅系统管理员或项目负责人可以添加
    is_sys_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN
    is_project_owner = project.owner_user_id == current_user.id
    if not (is_sys_admin or is_project_owner):
        raise PermissionDeniedError(
            code="PROJECT_MEMBER_ADD_DENIED",
            message="无权添加项目成员",
        )

    # 4. 被添加用户必须是团队成员
    team = project.team
    if not any(m.user_id == data.user_id for m in team.members):
        raise BadRequestError(
            code="PROJECT_MEMBER_NOT_TEAM_MEMBER",
            message="被添加用户不是团队成员",
        )

    # 5. 检查是否已是项目成员
    existing_member = next((m for m in project.members if m.user_id == data.user_id), None)
    if existing_member:
        raise ConflictError(
            code="PROJECT_MEMBER_ALREADY_EXISTS",
            message="用户已是项目成员",
        )

    # 6. 处理角色分配
    if data.role == ProjectRole.OWNER:
        # 转移项目负责人：更新 owner_user_id，原负责人降为 MEMBER
        old_owner_member = next((m for m in project.members if m.user_id == project.owner_user_id), None)
        if old_owner_member and old_owner_member.role == ProjectRole.OWNER:
            old_owner_member.role = ProjectRole.MEMBER

        # 添加新负责人为 OWNER 成员
        new_member = ProjectMember(
            project_id=project.id,
            user_id=data.user_id,
            role=ProjectRole.OWNER,
        )
        db.add(new_member)
        project.owner_user_id = data.user_id
    else:
        # 普通成员
        new_member = ProjectMember(
            project_id=project.id,
            user_id=data.user_id,
            role=data.role,
        )
        db.add(new_member)

    # 7. 提交并刷新
    await db.commit()
    # 重新加载新成员及用户信息以便序列化
    stmt = (
        select(ProjectMember)
        .where(ProjectMember.id == new_member.id)
        .options(selectinload(ProjectMember.user))
    )
    result = await db.execute(stmt)
    member_with_user = result.scalar_one()

    logger.info(
        "项目成员添加成功",
        extra={
            "event": "project_member_added",
            "project_id": project.id,
            "team_id": project.team_id,
            "user_id": member_with_user.user_id,
            "role": member_with_user.role.value,
            "owner_user_id": project.owner_user_id,
            "operator_id": current_user.id,
        },
    )
    return member_with_user


async def update_project_member_role(
        db: AsyncSession,
        project_id: int,
        target_user_id: int,
        current_user: User,
        data: UpdateProjectMemberRoleRequest,
) -> ProjectMember:
    # 1. 查询项目，预加载成员、团队及团队成员
    stmt = (
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.members).selectinload(ProjectMember.user),
            selectinload(Project.team).selectinload(Team.members),
        )
    )
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        raise ResourceNotFoundError(
            code="PROJECT_NOT_FOUND",
            message="项目不存在",
        )

    # 2. 归档项目禁止修改角色
    if project.status == ProjectStatus.archived:
        raise PermissionDeniedError(
            code="PROJECT_ARCHIVED",
            message="归档项目不能调整成员角色",
        )

    # 3. 权限检查：仅系统管理员或项目负责人可以操作
    is_sys_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN
    is_project_owner = project.owner_user_id == current_user.id
    if not (is_sys_admin or is_project_owner):
        raise PermissionDeniedError(
            code="PROJECT_MEMBER_ROLE_UPDATE_DENIED",
            message="无权调整项目成员角色",
        )

    # 4. 查找目标成员记录
    target_member = next((m for m in project.members if m.user_id == target_user_id), None)
    if not target_member:
        raise ResourceNotFoundError(
            code="PROJECT_MEMBER_NOT_FOUND",
            message="目标用户不是项目成员",
        )

    new_role = data.role

    # 5. 负责人限制
    if project.owner_user_id == target_user_id:
        # 目标用户是当前负责人
        if new_role != ProjectRole.OWNER:
            raise PermissionDeniedError(
                code="PROJECT_OWNER_ROLE_DEMOTE_DENIED",
                message="不能降级项目负责人的角色",
            )
        else:
            # 角色不变，直接返回
            return target_member

    # 6. 若将其他成员提升为 OWNER，执行负责人转移
    old_role = target_member.role.value
    if new_role == ProjectRole.OWNER:
        # 原负责人降为 MEMBER（如果还是成员）
        old_owner_member = next((m for m in project.members if m.user_id == project.owner_user_id), None)
        if old_owner_member and old_owner_member.role == ProjectRole.OWNER:
            old_owner_member.role = ProjectRole.MEMBER
        # 目标成员提升为 OWNER
        target_member.role = ProjectRole.OWNER
        project.owner_user_id = target_user_id
    else:
        # 普通角色变更（如 MEMBER <-> ADMIN）
        target_member.role = new_role

    # 7. 提交事务
    await db.commit()
    await db.refresh(target_member)

    logger.info(
        "项目成员角色调整成功",
        extra={
            "event": "project_member_role_updated",
            "project_id": project.id,
            "team_id": project.team_id,
            "user_id": target_user_id,
            "old_role": old_role,
            "new_role": target_member.role.value,
            "owner_user_id": project.owner_user_id,
            "operator_id": current_user.id,
        },
    )
    return target_member


async def remove_project_member(
        db: AsyncSession,
        project_id: int,
        target_user_id: int,
        current_user: User,
) -> str:
    # 1. 查询项目，预加载成员和团队
    stmt = (
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.members).selectinload(ProjectMember.user),
            selectinload(Project.team).selectinload(Team.members),
        )
    )
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        raise ResourceNotFoundError(
            code="PROJECT_NOT_FOUND",
            message="项目不存在",
        )

    # 2. 归档项目禁止移除成员
    if project.status == ProjectStatus.archived:
        raise PermissionDeniedError(
            code="PROJECT_ARCHIVED",
            message="归档项目不能移除成员",
        )

    # 3. 查找目标成员记录
    target_member = next((m for m in project.members if m.user_id == target_user_id), None)
    if not target_member:
        raise ResourceNotFoundError(
            code="PROJECT_MEMBER_NOT_FOUND",
            message="目标用户不是项目成员",
        )

    # 4. 不能移除项目负责人
    if target_member.user_id == project.owner_user_id:
        raise PermissionDeniedError(
            code="PROJECT_OWNER_REMOVE_DENIED",
            message="不能移除项目负责人，请先转移负责人",
        )

    # 5. 权限判断
    is_sys_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN
    is_project_owner = project.owner_user_id == current_user.id
    is_self_removal = current_user.id == target_user_id  # 普通成员退出

    if not (is_sys_admin or is_project_owner or is_self_removal):
        raise PermissionDeniedError(
            code="PROJECT_MEMBER_REMOVE_DENIED",
            message="无权移除该项目成员",
        )

    # 6. 执行删除
    removed_role = target_member.role.value
    await db.delete(target_member)
    await db.commit()

    logger.info(
        "项目成员移除成功",
        extra={
            "event": "project_member_removed",
            "project_id": project.id,
            "team_id": project.team_id,
            "user_id": target_user_id,
            "removed_role": removed_role,
            "operator_id": current_user.id,
            "self_removal": is_self_removal,
        },
    )
    return "成员移除成功"






