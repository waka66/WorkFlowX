import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, delete, or_, and_
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone, date
from sqlalchemy.exc import IntegrityError
from typing import Optional, List



from app.common.schemas import (PaginatedNotifications, ActivityList, PaginatedAuditLogs, PersonalDashboard,
                                MemberWorkload, ProjectDashboard, TeamDashboard, ProjectProgressItem,
                                SearchType, SearchResult, SearchResponse)
from app.models.user import User, GlobalRoleEnum
from app.models.system import Notification, Activity, AuditLog
from app.models.project import ProjectStatus
from app.models.team import Team, TeamRole, TeamStatus, TeamMember
from app.models.project import Project, ProjectMember, ProjectRole
from app.models.task import Workflow, WorkflowStatus, WorkflowTransition, Task, Priority, Attachment, Comment
from app.core.exceptions import PermissionDeniedError, ResourceNotFoundError



async def list_notifications(
        db: AsyncSession,
        current_user: User,
        page: int = 1,
        page_size: int = 20,
        read: Optional[bool] = None,
) -> PaginatedNotifications:
    # 构建基础条件：只查询当前用户的通知
    conditions = [Notification.user_id == current_user.id]
    if read is not None:
        if read:
            conditions.append(Notification.read_at.is_not(None))
        else:
            conditions.append(Notification.read_at.is_(None))

    # 查询总数
    count_stmt = select(func.count()).select_from(Notification).where(*conditions)
    total = (await db.execute(count_stmt)).scalar_one()

    # 分页查询，按创建时间倒序
    stmt = (
        select(Notification)
        .where(*conditions)
        .order_by(Notification.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    notifications = list(result.scalars().all())

    return PaginatedNotifications(
        items=notifications,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )

async def mark_all_read(db: AsyncSession, current_user: User) -> str:
    # 更新当前用户所有未读通知的 read_at 为当前时间
    stmt = (
        update(Notification)
        .where(
            Notification.user_id == current_user.id,
            Notification.read_at.is_(None)
        )
        .values(read_at=datetime.now(timezone.utc))
    )
    await db.execute(stmt)
    await db.commit()
    return "所有通知已标记为已读"

async def mark_read(
        db: AsyncSession,
        notification_id: int,
        current_user: User,
) -> Notification:
    # 查询通知
    notification = await db.get(Notification, notification_id)
    if not notification:
        raise ResourceNotFoundError(
            code="NOTIFICATION_NOT_FOUND",
            message="通知不存在",
        )

    # 权限：只能操作自己的通知
    if notification.user_id != current_user.id:
        raise ResourceNotFoundError(
            code="NOTIFICATION_NOT_FOUND",
            message="通知不存在",
        )

    # 如果尚未已读，设置已读时间
    if notification.read_at is None:
        notification.read_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(notification)

    return notification

async def list_team_activities(
        db: AsyncSession,
        team_id: int,
        current_user: User,
        page: int = 1,
        page_size: int = 20,
) -> ActivityList:
    # 1. 查询团队及成员（用于权限）
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

    # 2. 权限检查：系统管理员或团队成员
    is_sys_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN
    is_team_member = any(m.user_id == current_user.id for m in team.members)
    if not (is_sys_admin or is_team_member):
        raise PermissionDeniedError(
            code="TEAM_ACTIVITY_ACCESS_DENIED",
            message="无权查看团队活动",
        )

    # 3. 查询活动
    conditions = [Activity.team_id == team_id]
    count_stmt = select(func.count()).select_from(Activity).where(*conditions)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(Activity)
        .where(*conditions)
        .order_by(Activity.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    activities = list(result.scalars().all())

    return ActivityList(
        items=activities,
        total=total,
    )

async def list_project_activities(
        db: AsyncSession,
        project_id: int,
        current_user: User,
        page: int = 1,
        page_size: int = 20,
) -> ActivityList:
    # 1. 查询项目及关联信息（团队、项目成员）
    project_stmt = (
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.team).selectinload(Team.members),
            selectinload(Project.members),
        )
    )
    project_result = await db.execute(project_stmt)
    project = project_result.scalar_one_or_none()
    if not project:
        raise ResourceNotFoundError(
            code="PROJECT_NOT_FOUND",
            message="项目不存在",
        )

    # 2. 权限检查
    is_sys_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN
    is_team_member = any(m.user_id == current_user.id for m in project.team.members)
    is_project_member = any(m.user_id == current_user.id for m in project.members)

    if project.status == ProjectStatus.archived:
        if not (is_sys_admin or is_project_member):
            raise PermissionDeniedError(
                code="PROJECT_ARCHIVED_ACTIVITY_ACCESS_DENIED",
                message="无权访问归档项目的活动",
            )
    else:
        if not (is_sys_admin or is_team_member):
            raise PermissionDeniedError(
                code="PROJECT_ACTIVITY_ACCESS_DENIED",
                message="无权访问该项目的活动",
            )

    # 3. 查询活动记录
    conditions = [Activity.project_id == project_id]
    count_stmt = select(func.count()).select_from(Activity).where(*conditions)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(Activity)
        .where(*conditions)
        .order_by(Activity.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    activities = list(result.scalars().all())

    return ActivityList(
        items=activities,
        total=total,
    )

async def list_task_activities(
        db: AsyncSession,
        task_id: int,
        current_user: User,
        page: int = 1,
        page_size: int = 20,
) -> ActivityList:
    # 1. 查询任务及关联项目、团队、项目成员
    task_stmt = (
        select(Task)
        .where(Task.id == task_id)
        .options(
            selectinload(Task.project).selectinload(Project.team).selectinload(Team.members),
            selectinload(Task.project).selectinload(Project.members),
        )
    )
    task_result = await db.execute(task_stmt)
    task = task_result.scalar_one_or_none()
    if not task:
        raise ResourceNotFoundError(
            code="TASK_NOT_FOUND",
            message="任务不存在",
        )

    project = task.project

    # 2. 权限检查
    is_sys_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN
    is_team_member = any(m.user_id == current_user.id for m in project.team.members)
    is_project_member = any(m.user_id == current_user.id for m in project.members)

    if project.status == ProjectStatus.archived:
        if not (is_sys_admin or is_project_member):
            raise PermissionDeniedError(
                code="TASK_ARCHIVED_ACTIVITY_ACCESS_DENIED",
                message="无权访问归档任务的活动",
            )
    else:
        if not (is_sys_admin or is_team_member):
            raise PermissionDeniedError(
                code="TASK_ACTIVITY_ACCESS_DENIED",
                message="无权访问该任务的活动",
            )

    # 3. 查询活动记录
    conditions = [Activity.task_id == task_id]
    count_stmt = select(func.count()).select_from(Activity).where(*conditions)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(Activity)
        .where(*conditions)
        .order_by(Activity.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    activities = list(result.scalars().all())

    return ActivityList(
        items=activities,
        total=total,
    )

async def list_audit_logs(
        db: AsyncSession,
        current_user: User,
        page: int = 1,
        page_size: int = 20,
        user_id: Optional[int] = None,
        action: Optional[str] = None,
) -> PaginatedAuditLogs:
    # 权限检查：仅系统管理员
    if current_user.global_role != GlobalRoleEnum.SYSTEM_ADMIN:
        raise PermissionDeniedError(
            code="ADMIN_REQUIRED",
            message="需要管理员权限",
        )

    conditions = []
    if user_id is not None:
        conditions.append(AuditLog.user_id == user_id)
    if action:
        conditions.append(AuditLog.action == action)

    count_stmt = select(func.count()).select_from(AuditLog).where(*conditions)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(AuditLog)
        .where(*conditions)
        .order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    logs = list(result.scalars().all())

    return PaginatedAuditLogs(
        items=logs,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )

async def get_personal_dashboard(
        db: AsyncSession,
        current_user: User,
) -> PersonalDashboard:
    # 1. 获取当前用户可访问的活跃项目 ID 列表
    if current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN:
        # 管理员可访问所有活跃项目
        proj_stmt = select(Project.id).where(Project.status == ProjectStatus.active)
    else:
        # 普通用户：通过团队成员或项目成员关系获取活跃项目
        team_member_proj = (
            select(Project.id)
            .join(Team, Team.id == Project.team_id)
            .join(TeamMember, TeamMember.team_id == Team.id)
            .where(TeamMember.user_id == current_user.id, Project.status == ProjectStatus.active)
        )
        project_member_proj = (
            select(Project.id)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .where(ProjectMember.user_id == current_user.id, Project.status == ProjectStatus.active)
        )
        proj_stmt = team_member_proj.union(project_member_proj)

    result = await db.execute(proj_stmt)
    accessible_project_ids = [row[0] for row in result.fetchall()]

    # 2. 如果没有可访问的项目，返回空统计
    if not accessible_project_ids:
        return PersonalDashboard(
            my_task_count=0,
            overdue_task_count=0,
            pending_task_count=0,
            recent_activities=[],
            notifications=[],
        )

    # 3. 获取所有终态状态的 key（用于判断任务是否完成）
    final_keys_stmt = (
        select(WorkflowStatus.key)
        .join(Workflow, Workflow.id == WorkflowStatus.workflow_id)
        .where(Workflow.project_id.in_(accessible_project_ids), WorkflowStatus.is_final == True)
    )
    final_result = await db.execute(final_keys_stmt)
    final_keys = [row[0] for row in final_result.fetchall()]

    # 构建“未完成”条件（如果没有任何终态，则所有状态都视为未完成）
    if final_keys:
        incomplete_condition = Task.status_key.notin_(final_keys)
    else:
        incomplete_condition = True  # 始终为真

    today = date.today()

    # 4. 统计 my_task_count：我创建或分配给我的任务总数
    my_task_count_stmt = (
        select(func.count())
        .select_from(Task)
        .where(
            Task.project_id.in_(accessible_project_ids),
            or_(Task.creator_id == current_user.id, Task.assignee_user_id == current_user.id)
        )
    )
    my_task_count = (await db.execute(my_task_count_stmt)).scalar_one()

    # 5. 统计 pending_task_count：分配给我且未完成的任务数
    pending_stmt = (
        select(func.count())
        .select_from(Task)
        .where(
            Task.project_id.in_(accessible_project_ids),
            Task.assignee_user_id == current_user.id,
            incomplete_condition
        )
    )
    pending_count = (await db.execute(pending_stmt)).scalar_one()

    # 6. 统计 overdue_task_count：我创建或分配的逾期未完成任务数
    overdue_stmt = (
        select(func.count())
        .select_from(Task)
        .where(
            Task.project_id.in_(accessible_project_ids),
            or_(Task.creator_id == current_user.id, Task.assignee_user_id == current_user.id),
            Task.due_date.isnot(None),
            Task.due_date < today,
            incomplete_condition
        )
    )
    overdue_count = (await db.execute(overdue_stmt)).scalar_one()

    # 7. 查询最近 10 条活动（当前用户作为操作者）
    recent_activities_stmt = (
        select(Activity)
        .where(Activity.actor_user_id == current_user.id)
        .order_by(Activity.created_at.desc())
        .limit(10)
    )
    activities_result = await db.execute(recent_activities_stmt)
    recent_activities = list(activities_result.scalars().all())

    # 8. 查询最近 10 条通知
    notifications_stmt = (
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(10)
    )
    notifications_result = await db.execute(notifications_stmt)
    notifications = list(notifications_result.scalars().all())

    return PersonalDashboard(
        my_task_count=my_task_count,
        overdue_task_count=overdue_count,
        pending_task_count=pending_count,
        recent_activities=recent_activities,
        notifications=notifications,
    )

async def get_project_dashboard(
        db: AsyncSession,
        project_id: int,
        current_user: User,
) -> ProjectDashboard:
    # 1. 查询项目，预加载工作流、成员（项目成员和团队成员）
    project_stmt = (
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.workflow).selectinload(Workflow.statuses),
            selectinload(Project.members),
            selectinload(Project.team).selectinload(Team.members),
        )
    )
    project_result = await db.execute(project_stmt)
    project = project_result.scalar_one_or_none()
    if not project:
        raise ResourceNotFoundError(
            code="PROJECT_NOT_FOUND",
            message="项目不存在",
        )

    # 2. 权限检查
    is_sys_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN
    is_team_member = any(m.user_id == current_user.id for m in project.team.members)
    is_project_member = any(m.user_id == current_user.id for m in project.members)

    if project.status == ProjectStatus.archived:
        if not (is_sys_admin or is_project_member):
            raise PermissionDeniedError(
                code="PROJECT_ARCHIVED_DASHBOARD_ACCESS_DENIED",
                message="无权访问归档项目的仪表盘",
            )
    else:
        if not (is_sys_admin or is_team_member):
            raise PermissionDeniedError(
                code="PROJECT_DASHBOARD_ACCESS_DENIED",
                message="无权访问该项目的仪表盘",
            )

    # 3. 获取工作流终态 key 集合
    final_keys = {s.key for s in project.workflow.statuses if s.is_final} if project.workflow else set()

    # 构建“未完成”条件
    if final_keys:
        incomplete_cond = Task.status_key.notin_(final_keys)
    else:
        incomplete_cond = True  # 没有终态，所有任务都算未完成

    today = date.today()

    # 4. 任务总数
    total_stmt = (
        select(func.count())
        .select_from(Task)
        .where(Task.project_id == project_id)
    )
    task_total = (await db.execute(total_stmt)).scalar_one()

    # 5. 已完成任务数
    if final_keys:
        completed_stmt = (
            select(func.count())
            .select_from(Task)
            .where(Task.project_id == project_id, Task.status_key.in_(final_keys))
        )
        completed_count = (await db.execute(completed_stmt)).scalar_one()
    else:
        completed_count = 0

    # 6. 完成率（百分比，四舍五入）
    completion_rate = round((completed_count / task_total) * 100) if task_total > 0 else 0

    # 7. 进行中任务数（非终态）
    in_progress_stmt = (
        select(func.count())
        .select_from(Task)
        .where(Task.project_id == project_id)
    )
    if final_keys:
        in_progress_stmt = in_progress_stmt.where(Task.status_key.notin_(final_keys))
    in_progress_count = (await db.execute(in_progress_stmt)).scalar_one()

    # 8. 逾期任务数（未完成且 due_date < today）
    overdue_stmt = (
        select(func.count())
        .select_from(Task)
        .where(
            Task.project_id == project_id,
            Task.due_date.isnot(None),
            Task.due_date < today,
        )
    )
    if final_keys:
        overdue_stmt = overdue_stmt.where(Task.status_key.notin_(final_keys))
    overdue_count = (await db.execute(overdue_stmt)).scalar_one()

    # 9. 成员工作量（未完成任务数）
    member_ids = [m.user_id for m in project.members]
    workload_data = []
    if member_ids:
        workload_stmt = (
            select(Task.assignee_user_id, func.count())
            .where(
                Task.project_id == project_id,
                Task.assignee_user_id.in_(member_ids),
            )
            .group_by(Task.assignee_user_id)
        )
        if final_keys:
            workload_stmt = workload_stmt.where(Task.status_key.notin_(final_keys))
        workload_result = await db.execute(workload_stmt)
        workload_map = {row[0]: row[1] for row in workload_result.fetchall()}
        # 确保所有项目成员都出现在结果中，即使任务数为0
        for member in project.members:
            workload_data.append(MemberWorkload(
                user_id=member.user_id,
                task_count=workload_map.get(member.user_id, 0)
            ))

    return ProjectDashboard(
        task_total=task_total,
        completion_rate=completion_rate,
        in_progress_count=in_progress_count,
        overdue_count=overdue_count,
        member_workload=workload_data,
    )

async def get_team_dashboard(
        db: AsyncSession,
        team_id: int,
        current_user: User,
) -> TeamDashboard:
    # 1. 查询团队，预加载成员和项目
    team_stmt = (
        select(Team)
        .where(Team.id == team_id)
        .options(
            selectinload(Team.members),
            selectinload(Team.projects),  # 需要确保 Team 模型有 projects 关系
        )
    )
    team_result = await db.execute(team_stmt)
    team = team_result.scalar_one_or_none()
    if not team:
        raise ResourceNotFoundError(
            code="TEAM_NOT_FOUND",
            message="团队不存在",
        )

    # 2. 权限检查：系统管理员或团队成员
    is_sys_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN
    is_team_member = any(m.user_id == current_user.id for m in team.members)
    if not (is_sys_admin or is_team_member):
        raise PermissionDeniedError(
            code="TEAM_DASHBOARD_ACCESS_DENIED",
            message="无权查看团队仪表盘",
        )

    # 3. 基础计数
    project_count = len(team.projects)
    active_project_count = sum(1 for p in team.projects if p.status == ProjectStatus.active)
    member_count = len(team.members)

    # 4. 获取所有项目ID列表
    project_ids = [p.id for p in team.projects]

    if not project_ids:
        return TeamDashboard(
            project_count=0,
            active_project_count=0,
            task_count=0,
            member_count=member_count,
            project_progress=[],
        )

    # 5. 获取所有项目的工作流终态 key
    final_keys = set()
    workflow_stmt = (
        select(WorkflowStatus.key)
        .join(Workflow, Workflow.id == WorkflowStatus.workflow_id)
        .where(Workflow.project_id.in_(project_ids), WorkflowStatus.is_final == True)
    )
    workflow_result = await db.execute(workflow_stmt)
    final_keys = set(workflow_result.scalars().all())

    # 6. 统计任务总数
    task_count_stmt = (
        select(func.count())
        .select_from(Task)
        .where(Task.project_id.in_(project_ids))
    )
    task_count = (await db.execute(task_count_stmt)).scalar_one()

    # 7. 按项目统计任务总数和已完成数
    progress_data = {}
    # 先统计每个项目的任务总数
    total_by_project_stmt = (
        select(Task.project_id, func.count())
        .where(Task.project_id.in_(project_ids))
        .group_by(Task.project_id)
    )
    total_result = await db.execute(total_by_project_stmt)
    total_map = {row[0]: row[1] for row in total_result.fetchall()}

    # 统计每个项目的已完成任务数（如果有终态）
    if final_keys:
        completed_by_project_stmt = (
            select(Task.project_id, func.count())
            .where(
                Task.project_id.in_(project_ids),
                Task.status_key.in_(final_keys)
            )
            .group_by(Task.project_id)
        )
        completed_result = await db.execute(completed_by_project_stmt)
        completed_map = {row[0]: row[1] for row in completed_result.fetchall()}
    else:
        completed_map = {}

    # 8. 构建项目进度列表
    project_progress = []
    for project in team.projects:
        total = total_map.get(project.id, 0)
        completed = completed_map.get(project.id, 0)
        progress = round((completed / total) * 100) if total > 0 else 0
        project_progress.append(ProjectProgressItem(
            project_id=project.id,
            name=project.name,
            progress=progress,
        ))

    return TeamDashboard(
        project_count=project_count,
        active_project_count=active_project_count,
        task_count=task_count,
        member_count=member_count,
        project_progress=project_progress,
    )

async def global_search(
        db: AsyncSession,
        current_user: User,
        query: str,
        search_type: Optional[SearchType] = None,
) -> SearchResponse:
    # 1. 获取当前用户可访问的项目 ID 列表
    if current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN:
        # 管理员可访问所有项目
        project_ids_stmt = select(Project.id)
    else:
        # 通过团队成员或项目成员获取活跃项目
        team_proj = (
            select(Project.id)
            .join(Team, Team.id == Project.team_id)
            .join(TeamMember, TeamMember.team_id == Team.id)
            .where(TeamMember.user_id == current_user.id, Project.status == ProjectStatus.active)
        )
        proj_member = (
            select(Project.id)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .where(ProjectMember.user_id == current_user.id, Project.status == ProjectStatus.active)
        )
        project_ids_stmt = team_proj.union(proj_member)
    result = await db.execute(project_ids_stmt)
    accessible_project_ids = [row[0] for row in result.fetchall()]

    # 2. 搜索模式
    pattern = f"%{query}%"
    results: List[SearchResult] = []

    # 搜索项目
    if search_type is None or search_type == SearchType.project:
        proj_conditions = [
            Project.name.ilike(pattern)
        ]
        if current_user.global_role != GlobalRoleEnum.SYSTEM_ADMIN:
            # 限制在可访问项目内
            proj_conditions.append(Project.id.in_(accessible_project_ids))
        stmt = (
            select(Project)
            .where(and_(*proj_conditions))
            .limit(20)
        )
        proj_result = await db.execute(stmt)
        projects = proj_result.scalars().all()
        for p in projects:
            results.append(SearchResult(
                type=SearchType.project,
                id=p.id,
                title=p.name,
                summary=p.description[:200] if p.description else None
            ))

    # 搜索任务
    if search_type is None or search_type == SearchType.task:
        task_conditions = [
            Task.title.ilike(pattern)
        ]
        if current_user.global_role != GlobalRoleEnum.SYSTEM_ADMIN:
            task_conditions.append(Task.project_id.in_(accessible_project_ids))
        stmt = (
            select(Task)
            .where(and_(*task_conditions))
            .limit(20)
        )
        task_result = await db.execute(stmt)
        tasks = task_result.scalars().all()
        for t in tasks:
            results.append(SearchResult(
                type=SearchType.task,
                id=t.id,
                title=t.title,
                summary=t.description[:200] if t.description else None
            ))

    # 搜索用户
    if search_type is None or search_type == SearchType.user:
        user_conditions = [
            or_(
                User.username.ilike(pattern),
                User.email.ilike(pattern)
            )
        ]
        if current_user.global_role != GlobalRoleEnum.SYSTEM_ADMIN:
            # 获取可访问的用户ID：团队成员 + 项目成员
            team_user_ids_stmt = (
                select(TeamMember.user_id)
                .join(Team, Team.id == TeamMember.team_id)
                .join(Project, Project.team_id == Team.id)
                .where(Project.id.in_(accessible_project_ids))
            )
            project_user_ids_stmt = (
                select(ProjectMember.user_id)
                .where(ProjectMember.project_id.in_(accessible_project_ids))
            )
            combined_user_ids = team_user_ids_stmt.union(project_user_ids_stmt)
            user_result = await db.execute(combined_user_ids)
            allowed_user_ids = [row[0] for row in user_result.fetchall()]
            if allowed_user_ids:
                user_conditions.append(User.id.in_(allowed_user_ids))
            else:
                # 没有可访问用户，直接跳过
                user_conditions.append(User.id == -1)  # 不匹配任何
        stmt = (
            select(User)
            .where(and_(*user_conditions))
            .limit(20)
        )
        users_result = await db.execute(stmt)
        users = users_result.scalars().all()
        for u in users:
            results.append(SearchResult(
                type=SearchType.user,
                id=u.id,
                title=u.username,
                summary=u.email
            ))

    # 搜索评论
    if search_type is None or search_type == SearchType.comment:
        comment_conditions = [
            Comment.content.ilike(pattern)
        ]
        if current_user.global_role != GlobalRoleEnum.SYSTEM_ADMIN:
            # 评论必须在可访问项目的任务中
            comment_conditions.append(
                Comment.task_id.in_(
                    select(Task.id).where(Task.project_id.in_(accessible_project_ids))
                )
            )
        stmt = (
            select(Comment)
            .where(and_(*comment_conditions))
            .limit(20)
        )
        comment_result = await db.execute(stmt)
        comments = comment_result.scalars().all()
        for c in comments:
            # 获取任务标题作为 title
            task_title = None
            if c.task_id:
                task = await db.get(Task, c.task_id)
                if task:
                    task_title = task.title
            title = f"评论于任务: {task_title}" if task_title else "评论"
            results.append(SearchResult(
                type=SearchType.comment,
                id=c.id,
                title=title,
                summary=c.content[:200]
            ))

    return SearchResponse(
        query=query,
        results=results
    )
