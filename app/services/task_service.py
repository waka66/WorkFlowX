import uuid
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete, or_
from fastapi import UploadFile
from sqlalchemy.orm import selectinload
from datetime import date
from sqlalchemy.exc import IntegrityError
from typing import Optional
from pathlib import Path
import os

from app.common.schemas import (ProjectStatus, UpdateWorkflowRequest, CreateTaskRequest, PaginatedTasks, TaskDetailResponse,
                                UpdateTaskRequest, TransitionTaskRequest, CommentList, CreateCommentRequest, UpdateCommentRequest,
                                AttachmentList)
from app.models.user import User, GlobalRoleEnum
from app.models.team import Team, TeamRole, TeamStatus, TeamMember
from app.models.project import Project, ProjectMember, ProjectRole
from app.models.task import Workflow, WorkflowStatus, WorkflowTransition, Task, Priority, Attachment, Comment
from app.core.exceptions import BadRequestError, ConflictError, PermissionDeniedError, ResourceNotFoundError
from app.core.config import settings

UPLOAD_DIR = settings.upload_dir
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


logger = logging.getLogger("app.services.task_service")



async def update_workflow(
        db: AsyncSession,
        project_id: int,
        current_user: User,
        data: UpdateWorkflowRequest,
) -> Workflow:
    # 1. 查询项目（预加载团队信息用于权限）
    stmt = (
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.team).selectinload(Team.members))
    )
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        raise ResourceNotFoundError(
            code="PROJECT_NOT_FOUND",
            message="项目不存在",
        )

    # 2. 归档项目不允许修改工作流
    if project.status == ProjectStatus.archived:
        raise PermissionDeniedError(
            code="PROJECT_ARCHIVED",
            message="归档项目不能修改工作流",
        )

    # 3. 权限：仅系统管理员或项目负责人
    is_sys_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN
    is_project_owner = project.owner_user_id == current_user.id
    if not (is_sys_admin or is_project_owner):
        raise PermissionDeniedError(
            code="WORKFLOW_UPDATE_DENIED",
            message="无权修改项目工作流",
        )

    # 4. 基本验证
    # 检查状态定义
    status_keys = [s.key for s in data.statuses]
    if len(status_keys) != len(set(status_keys)):
        raise BadRequestError(
            code="WORKFLOW_STATUS_KEY_DUPLICATE",
            message="状态 key 重复",
        )
    initial_statuses = [s for s in data.statuses if s.is_initial]
    if len(initial_statuses) != 1:
        raise BadRequestError(
            code="WORKFLOW_INITIAL_STATUS_INVALID",
            message="必须且只能有一个初始状态",
        )
    # 检查转换引用的状态 key 是否存在
    for t in data.transitions:
        if t.from_status_key not in status_keys or t.to_status_key not in status_keys:
            raise BadRequestError(
                code="WORKFLOW_TRANSITION_STATUS_NOT_FOUND",
                message="转换引用了不存在的状态 key",
            )
        if t.from_status_key == t.to_status_key:
            raise BadRequestError(
                code="WORKFLOW_SELF_TRANSITION_DENIED",
                message="不允许自循环转换",
            )

    # 5. 查找或创建工作流
    workflow_stmt = select(Workflow).where(Workflow.project_id == project_id)
    workflow_result = await db.execute(workflow_stmt)
    workflow = workflow_result.scalar_one_or_none()

    if workflow:
        # 删除旧的状态和转换
        await db.execute(delete(WorkflowStatus).where(WorkflowStatus.workflow_id == workflow.id))
        await db.execute(delete(WorkflowTransition).where(WorkflowTransition.workflow_id == workflow.id))
    else:
        # 创建工作流
        workflow = Workflow(project_id=project_id)
        db.add(workflow)
        await db.flush()  # 获取 workflow.id

    # 6. 创建新的状态
    status_objects = []
    for s in data.statuses:
        new_status = WorkflowStatus(
            workflow_id=workflow.id,
            key=s.key,
            name=s.name,
            order=s.order,
            color=s.color,
            is_initial=s.is_initial,
            is_final=s.is_final,
        )
        db.add(new_status)
        status_objects.append(new_status)

    # 7. 创建新的转换
    for t in data.transitions:
        new_transition = WorkflowTransition(
            workflow_id=workflow.id,
            from_status_key=t.from_status_key,
            to_status_key=t.to_status_key,
            allowed_roles=[role.value for role in t.allowed_roles],  # 存储字符串列表
        )
        db.add(new_transition)

    # 8. 提交事务
    try:
        await db.commit()
    except IntegrityError:
        raise ConflictError(
            code="WORKFLOW_DEFINITION_CONFLICT",
            message="工作流定义冲突，请检查唯一性",
        )

    # 9. 重新加载完整工作流（包含新创建的状态和转换）
    stmt = (
        select(Workflow)
        .where(Workflow.id == workflow.id)
        .options(
            selectinload(Workflow.statuses),
            selectinload(Workflow.transitions),
        )
    )
    result = await db.execute(stmt)
    updated_workflow = result.scalar_one()

    logger.info(
        "项目工作流更新成功",
        extra={
            "event": "workflow_updated",
            "project_id": project_id,
            "workflow_id": updated_workflow.id,
            "operator_id": current_user.id,
            "status_count": len(updated_workflow.statuses),
            "transition_count": len(updated_workflow.transitions),
        },
    )
    return updated_workflow


async def get_workflow(
        db: AsyncSession,
        project_id: int,
        current_user: User,
) -> Workflow:
    # 1. 查询项目，并预加载团队及项目成员用于权限判断
    stmt = (
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.team).selectinload(Team.members),
            selectinload(Project.members)  # 项目成员列表
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
    is_team_member = any(m.user_id == current_user.id for m in project.team.members)
    is_project_member = any(m.user_id == current_user.id for m in project.members)

    if project.status == ProjectStatus.archived:
        # 归档项目：仅系统管理员或项目成员可查看
        if not (is_sys_admin or is_project_member):
            raise PermissionDeniedError(
                code="WORKFLOW_ARCHIVED_ACCESS_DENIED",
                message="无权访问归档项目的工作流",
            )
    else:
        # 活跃项目：系统管理员或所属团队成员可查看
        if not (is_sys_admin or is_team_member):
            raise PermissionDeniedError(
                code="WORKFLOW_ACCESS_DENIED",
                message="无权访问该项目工作流",
            )

    # 3. 查询工作流（包含状态和转换）
    workflow_stmt = (
        select(Workflow)
        .where(Workflow.project_id == project_id)
        .options(
            selectinload(Workflow.statuses),
            selectinload(Workflow.transitions),
        )
    )
    workflow_result = await db.execute(workflow_stmt)
    workflow = workflow_result.scalar_one_or_none()
    if not workflow:
        raise ResourceNotFoundError(
            code="WORKFLOW_NOT_FOUND",
            message="工作流不存在",
        )

    return workflow


async def create_task(
        db: AsyncSession,
        project_id: int,
        current_user: User,
        data: CreateTaskRequest,
) -> Task:
    # 1. 查询项目，并预加载项目成员
    stmt = (
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.members))
    )
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        raise ResourceNotFoundError(
            code="PROJECT_NOT_FOUND",
            message="项目不存在",
        )

    # 2. 归档项目不能创建任务
    if project.status == ProjectStatus.archived:
        raise PermissionDeniedError(
            code="PROJECT_ARCHIVED",
            message="归档项目不能创建任务",
        )

    # 3. 权限检查：系统管理员、项目负责人或项目成员
    is_sys_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN
    is_project_owner = project.owner_user_id == current_user.id
    is_project_member = any(m.user_id == current_user.id for m in project.members)
    if not (is_sys_admin or is_project_owner or is_project_member):
        raise PermissionDeniedError(
            code="TASK_CREATE_DENIED",
            message="无权在该项目中创建任务",
        )

    # 4. 查询项目工作流，并获取初始状态
    workflow_stmt = (
        select(Workflow)
        .where(Workflow.project_id == project_id)
        .options(selectinload(Workflow.statuses))
    )
    workflow_result = await db.execute(workflow_stmt)
    workflow = workflow_result.scalar_one_or_none()
    if not workflow:
        raise BadRequestError(
            code="TASK_WORKFLOW_NOT_CONFIGURED",
            message="项目未配置工作流，无法创建任务",
        )

    initial_status = next((s for s in workflow.statuses if s.is_initial), None)
    if not initial_status:
        raise BadRequestError(
            code="TASK_WORKFLOW_INITIAL_STATUS_MISSING",
            message="工作流缺少初始状态，无法创建任务",
        )

    # 5. 验证 assignee（如果提供）
    if data.assignee_user_id is not None:
        is_assignee_member = any(m.user_id == data.assignee_user_id for m in project.members)
        if not is_assignee_member:
            raise BadRequestError(
                code="TASK_ASSIGNEE_NOT_PROJECT_MEMBER",
                message="被分配人不是项目成员",
            )

    # 6. 创建任务（时间戳由 BaseTimeMixin 自动生成）
    task = Task(
        project_id=project_id,
        title=data.title,
        description=data.description,
        creator_id=current_user.id,
        assignee_user_id=data.assignee_user_id,
        status_key=initial_status.key,
        priority=data.priority,
        due_date=data.due_date,
        tags=data.tags,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    logger.info(
        "任务创建成功",
        extra={
            "event": "task_created",
            "task_id": task.id,
            "project_id": project_id,
            "title": task.title,
            "status_key": task.status_key,
            "assignee_user_id": task.assignee_user_id,
            "operator_id": current_user.id,
        },
    )
    return task


async def list_tasks(
        db: AsyncSession,
        project_id: int,
        current_user: User,
        page: int = 1,
        page_size: int = 20,
        assignee_user_id: Optional[int] = None,
        status_key: Optional[str] = None,
        priority: Optional[Priority] = None,
        due_date_from: Optional[date] = None,
        due_date_to: Optional[date] = None,
        tag: Optional[str] = None,
        keyword: Optional[str] = None,
        overdue: Optional[bool] = None,
) -> PaginatedTasks:
    # 1. 查询项目及关联信息（团队、成员、工作流）用于权限和终态判断
    project_stmt = (
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.team).selectinload(Team.members),
            selectinload(Project.members),
            selectinload(Project.workflow).selectinload(Workflow.statuses),
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
                code="TASK_ARCHIVED_ACCESS_DENIED",
                message="无权访问归档项目的任务",
            )
    else:
        if not (is_sys_admin or is_team_member):
            raise PermissionDeniedError(
                code="TASK_ACCESS_DENIED",
                message="无权访问该项目的任务",
            )

    # 3. 构建过滤条件
    conditions = [Task.project_id == project_id]
    if assignee_user_id is not None:
        conditions.append(Task.assignee_user_id == assignee_user_id)
    if status_key:
        conditions.append(Task.status_key == status_key)
    if priority:
        conditions.append(Task.priority == priority)
    if due_date_from:
        conditions.append(Task.due_date >= due_date_from)
    if due_date_to:
        conditions.append(Task.due_date <= due_date_to)
    if tag:
        # JSON 数组包含标签
        conditions.append(Task.tags.contains([tag]))
    if keyword:
        conditions.append(Task.title.ilike(f"%{keyword}%"))

    # 逾期过滤：未完成且截止日期早于今天
    if overdue:
        today = date.today()
        conditions.append(Task.due_date < today)
        # 排除终态状态
        if project.workflow:
            final_keys = [s.key for s in project.workflow.statuses if s.is_final]
            if final_keys:
                conditions.append(Task.status_key.notin_(final_keys))
            else:
                # 如果没有定义终态，则逾期定义为所有未完成任务（即没有终态的话，所有任务都算未完成？）
                # 这里简单处理：如果有 overdue=true 且没有终态，则不额外过滤
                pass

    # 4. 总数查询
    count_stmt = select(func.count()).select_from(Task).where(*conditions)
    total = (await db.execute(count_stmt)).scalar_one()

    # 5. 分页数据查询
    stmt = (
        select(Task)
        .where(*conditions)
        .order_by(Task.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    tasks = list(result.scalars().all())

    # 6. 构造响应
    return PaginatedTasks(
        items=tasks,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )


async def get_task_detail(
        db: AsyncSession,
        task_id: int,
        current_user: User,
) -> TaskDetailResponse:
    # 1. 查询任务，并预加载相关项目、团队成员、项目成员、评论
    task_stmt = (
        select(Task)
        .where(Task.id == task_id)
        .options(
            selectinload(Task.comments),
        )
    )
    task_result = await db.execute(task_stmt)
    task = task_result.scalar_one_or_none()
    if not task:
        raise ResourceNotFoundError(
            code="TASK_NOT_FOUND",
            message="任务不存在",
        )

    # 2. 查询任务所属项目，用于权限验证
    project_stmt = (
        select(Project)
        .where(Project.id == task.project_id)
        .options(
            selectinload(Project.team).selectinload(Team.members),
            selectinload(Project.members),
        )
    )
    project_result = await db.execute(project_stmt)
    project = project_result.scalar_one()

    # 3. 权限检查（同任务详情接口规则）
    is_sys_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN
    is_team_member = any(m.user_id == current_user.id for m in project.team.members)
    is_project_member = any(m.user_id == current_user.id for m in project.members)

    if project.status == ProjectStatus.archived:
        if not (is_sys_admin or is_project_member):
            raise PermissionDeniedError(
                code="TASK_ARCHIVED_ACCESS_DENIED",
                message="无权访问归档项目的任务",
            )
    else:
        if not (is_sys_admin or is_team_member):
            raise PermissionDeniedError(
                code="TASK_ACCESS_DENIED",
                message="无权访问该任务",
            )

    # 4. 查询任务附件
    att_stmt = (
        select(Attachment)
        .where(Attachment.target_type == "task", Attachment.target_id == task_id)
        .order_by(Attachment.created_at.desc())
    )
    att_result = await db.execute(att_stmt)
    attachments = list(att_result.scalars().all())

    # 5. 构造响应
    return TaskDetailResponse(
        id=task.id,
        project_id=task.project_id,
        title=task.title,
        description=task.description,
        creator_id=task.creator_id,
        assignee_user_id=task.assignee_user_id,
        status_key=task.status_key,
        priority=task.priority,
        due_date=task.due_date,
        tags=task.tags,
        created_at=task.created_at,
        updated_at=task.updated_at,
        comments=task.comments,
        attachments=attachments,
    )


async def update_task(
        db: AsyncSession,
        task_id: int,
        current_user: User,
        data: UpdateTaskRequest,
) -> Task:
    # 1. 查询任务
    task = await db.get(Task, task_id)
    if not task:
        raise ResourceNotFoundError(
            code="TASK_NOT_FOUND",
            message="任务不存在",
        )

    # 2. 查询所属项目并预加载成员
    project_stmt = (
        select(Project)
        .where(Project.id == task.project_id)
        .options(selectinload(Project.members))
    )
    project_result = await db.execute(project_stmt)
    project = project_result.scalar_one()

    # 3. 权限检查
    is_sys_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN
    is_project_owner = project.owner_user_id == current_user.id
    is_project_member = any(m.user_id == current_user.id for m in project.members)
    if not (is_sys_admin or is_project_owner or is_project_member):
        raise PermissionDeniedError(
            code="TASK_UPDATE_DENIED",
            message="无权更新该任务",
        )

    # 4. 归档项目禁止更新
    if project.status == ProjectStatus.archived:
        raise PermissionDeniedError(
            code="PROJECT_ARCHIVED",
            message="归档项目不能更新任务",
        )

    fields_to_update = data.model_fields_set

    # 5. 更新字段
    if "title" in fields_to_update and data.title is not None:
        task.title = data.title
    if "description" in fields_to_update:
        task.description = data.description  # 可能为 None
    if "priority" in fields_to_update and data.priority is not None:
        task.priority = data.priority
    if "due_date" in fields_to_update:
        task.due_date = data.due_date  # 可能为 None
    if "tags" in fields_to_update and data.tags is not None:
        # 验证每个标签长度
        if any(len(tag) > 50 for tag in data.tags):
            raise BadRequestError(
                code="TASK_TAG_TOO_LONG",
                message="标签长度不能超过50个字符",
            )
        task.tags = data.tags

    # 6. 负责人变更
    if "assignee_user_id" in fields_to_update:
        if data.assignee_user_id is not None:
            # 新负责人必须是项目成员
            is_assignee_member = any(m.user_id == data.assignee_user_id for m in project.members)
            if not is_assignee_member:
                raise BadRequestError(
                    code="TASK_ASSIGNEE_NOT_PROJECT_MEMBER",
                    message="被分配人不是项目成员",
                )
            task.assignee_user_id = data.assignee_user_id
        else:
            task.assignee_user_id = None

    # 7. 提交事务
    await db.commit()
    await db.refresh(task)

    logger.info(
        "任务更新成功",
        extra={
            "event": "task_updated",
            "task_id": task.id,
            "project_id": task.project_id,
            "updated_fields": sorted(fields_to_update),
            "operator_id": current_user.id,
        },
    )
    return task


async def delete_task(
        db: AsyncSession,
        task_id: int,
        current_user: User,
) -> str:
    # 1. 查询任务
    task = await db.get(Task, task_id)
    if not task:
        raise ResourceNotFoundError(
            code="TASK_NOT_FOUND",
            message="任务不存在",
        )

    # 2. 查询所属项目及成员
    project_stmt = (
        select(Project)
        .where(Project.id == task.project_id)
        .options(selectinload(Project.members))
    )
    project_result = await db.execute(project_stmt)
    project = project_result.scalar_one()

    # 3. 权限检查
    is_sys_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN
    is_project_owner = project.owner_user_id == current_user.id
    is_project_member = any(m.user_id == current_user.id for m in project.members)
    if not (is_sys_admin or is_project_owner or is_project_member):
        raise PermissionDeniedError(
            code="TASK_DELETE_DENIED",
            message="无权删除该任务",
        )

    # 4. 归档项目禁止删除
    if project.status == ProjectStatus.archived:
        raise PermissionDeniedError(
            code="PROJECT_ARCHIVED",
            message="归档项目不能删除任务",
        )

    # 5. 删除相关附件（硬删除）
    att_stmt = delete(Attachment).where(
        Attachment.target_type == "task",
        Attachment.target_id == task_id
    )
    await db.execute(att_stmt)

    # 6. 删除任务（评论通过 ORM 级联删除）
    deleted_task_id = task.id
    deleted_task_title = task.title
    await db.delete(task)
    await db.commit()

    logger.info(
        "任务删除成功",
        extra={
            "event": "task_deleted",
            "task_id": deleted_task_id,
            "project_id": project.id,
            "title": deleted_task_title,
            "operator_id": current_user.id,
        },
    )
    return "任务删除成功"


async def transition_task(
        db: AsyncSession,
        task_id: int,
        current_user: User,
        data: TransitionTaskRequest,
) -> Task:
    # 1. 查询任务
    task = await db.get(Task, task_id)
    if not task:
        raise ResourceNotFoundError(
            code="TASK_NOT_FOUND",
            message="任务不存在",
        )

    # 2. 查询所属项目、工作流、当前用户在项目中的角色
    project_stmt = (
        select(Project)
        .where(Project.id == task.project_id)
        .options(
            selectinload(Project.members),  # 项目成员列表（含角色）
        )
    )
    project_result = await db.execute(project_stmt)
    project = project_result.scalar_one()

    # 3. 归档项目不能流转
    if project.status == ProjectStatus.archived:
        raise PermissionDeniedError(
            code="PROJECT_ARCHIVED",
            message="归档项目不能执行状态流转",
        )

    # 4. 查询工作流
    workflow_stmt = (
        select(Workflow)
        .where(Workflow.project_id == task.project_id)
        .options(
            selectinload(Workflow.statuses),
            selectinload(Workflow.transitions),
        )
    )
    workflow_result = await db.execute(workflow_stmt)
    workflow = workflow_result.scalar_one_or_none()
    if not workflow:
        raise BadRequestError(
            code="TASK_WORKFLOW_NOT_CONFIGURED",
            message="项目未配置工作流",
        )

    # 5. 验证目标状态存在
    target_status = next((s for s in workflow.statuses if s.key == data.to_status_key), None)
    if not target_status:
        raise BadRequestError(
            code="TASK_TRANSITION_TARGET_STATUS_NOT_FOUND",
            message="目标状态不存在于工作流中",
        )

    # 6. 查找当前状态到目标状态的转换规则
    transition = next(
        (t for t in workflow.transitions
         if t.from_status_key == task.status_key and t.to_status_key == data.to_status_key),
        None
    )
    if not transition:
        raise BadRequestError(
            code="TASK_TRANSITION_NOT_FOUND",
            message="不存在从当前状态到目标状态的转换",
        )

    # 7. 权限检查：系统管理员直接通过，否则检查用户角色是否在 allowed_roles 中
    is_sys_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN
    if not is_sys_admin:
        # 获取当前用户在项目中的角色（必须为项目成员）
        member_record = next((m for m in project.members if m.user_id == current_user.id), None)
        if not member_record:
            raise PermissionDeniedError(
                code="TASK_TRANSITION_NOT_PROJECT_MEMBER",
                message="你不是项目成员，无权执行状态流转",
            )
        user_role = member_record.role.value  # 枚举值字符串
        allowed_roles = transition.allowed_roles  # 存储为字符串列表
        if user_role not in allowed_roles:
            raise PermissionDeniedError(
                code="TASK_TRANSITION_ROLE_DENIED",
                message="你的角色无权执行此状态流转",
            )

    # 8. 执行状态更新
    task.status_key = data.to_status_key
    # updated_at 由 BaseTimeMixin 自动更新

    # 9. 可选添加评论
    if data.comment:
        comment = Comment(
            task_id=task.id,
            user_id=current_user.id,
            content=data.comment,
        )
        db.add(comment)

    # 10. 提交事务
    await db.commit()
    await db.refresh(task)
    return task


async def list_my_tasks(
        db: AsyncSession,
        current_user: User,
        page: int = 1,
        page_size: int = 20,
        scope: Optional[str] = None,
        project_id: Optional[int] = None,
) -> PaginatedTasks:
    # 1. 获取当前用户可访问的活跃项目ID列表
    if current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN:
        # 管理员可以访问所有活跃项目
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

    # 2. 如果没有可访问的项目，返回空分页
    if not accessible_project_ids:
        return PaginatedTasks(items=[], total=0, page=page, page_size=page_size, has_more=False)

    # 3. 构建任务查询条件
    conditions = [Task.project_id.in_(accessible_project_ids)]
    if project_id is not None:
        conditions.append(Task.project_id == project_id)

    # 根据 scope 添加过滤
    if scope == "my":
        conditions.append(Task.creator_id == current_user.id)
    elif scope == "assigned_to_me":
        conditions.append(Task.assignee_user_id == current_user.id)
    elif scope == "pending":
        # 待处理：分配给我且未完成（这里简化为仅分配给我）
        conditions.append(Task.assignee_user_id == current_user.id)
    elif scope == "overdue":
        # 逾期：我创建或分配给我的，且截止日期已过
        conditions.append(
            or_(
                Task.creator_id == current_user.id,
                Task.assignee_user_id == current_user.id,
            )
        )
        conditions.append(Task.due_date < date.today())
        # 注意：此处未排除已完成任务，若需精确排除，需进一步关联工作流终态，这里简化处理
    else:
        # 默认：我创建或分配给我的所有任务
        conditions.append(
            or_(
                Task.creator_id == current_user.id,
                Task.assignee_user_id == current_user.id,
            )
        )

    # 4. 总数查询
    count_stmt = select(func.count()).select_from(Task).where(*conditions)
    total = (await db.execute(count_stmt)).scalar_one()

    # 5. 分页数据查询
    stmt = (
        select(Task)
        .where(*conditions)
        .order_by(Task.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    tasks = list(result.scalars().all())

    # 6. 构造分页响应
    return PaginatedTasks(
        items=tasks,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )


async def list_task_comments(
        db: AsyncSession,
        task_id: int,
        current_user: User,
) -> CommentList:
    # 1. 查询任务，并预加载项目信息用于权限判断
    task_stmt = (
        select(Task)
        .where(Task.id == task_id)
        .options(
            selectinload(Task.project).selectinload(Project.team).selectinload(Team.members),
            selectinload(Task.project).selectinload(Project.members),
            selectinload(Task.comments),  # 加载评论（按创建时间排序）
        )
    )
    task_result = await db.execute(task_stmt)
    task = task_result.scalar_one_or_none()
    if not task:
        raise ResourceNotFoundError(
            code="TASK_NOT_FOUND",
            message="任务不存在",
        )

    # 2. 权限检查（与任务详情一致）
    project = task.project
    is_sys_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN
    is_team_member = any(m.user_id == current_user.id for m in project.team.members)
    is_project_member = any(m.user_id == current_user.id for m in project.members)

    if project.status == ProjectStatus.archived:
        if not (is_sys_admin or is_project_member):
            raise PermissionDeniedError(
                code="COMMENT_ARCHIVED_ACCESS_DENIED",
                message="无权访问归档任务的评论",
            )
    else:
        if not (is_sys_admin or is_team_member):
            raise PermissionDeniedError(
                code="COMMENT_ACCESS_DENIED",
                message="无权访问该任务的评论",
            )

    # 3. 返回评论列表
    return CommentList(
        items=task.comments,
        total=len(task.comments)
    )


async def create_task_comment(
        db: AsyncSession,
        task_id: int,
        current_user: User,
        data: CreateCommentRequest,
) -> Comment:
    # 1. 查询任务并预加载项目、团队成员和项目成员信息用于权限
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
                code="COMMENT_CREATE_DENIED",
                message="无权在归档任务中添加评论",
            )
    else:
        if not (is_sys_admin or is_team_member):
            raise PermissionDeniedError(
                code="COMMENT_CREATE_DENIED",
                message="无权在该任务中添加评论",
            )

    # 3. 验证父评论（如果提供）
    if data.parent_id is not None:
        parent_comment = await db.get(Comment, data.parent_id)
        if not parent_comment:
            raise ResourceNotFoundError(
                code="PARENT_COMMENT_NOT_FOUND",
                message="父评论不存在",
            )
        if parent_comment.task_id != task_id:
            raise BadRequestError(
                code="PARENT_COMMENT_NOT_IN_TASK",
                message="父评论不属于该任务",
            )

    # 4. 创建评论
    comment = Comment(
        task_id=task_id,
        user_id=current_user.id,
        parent_id=data.parent_id,
        content=data.content,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    logger.info(
        "评论或回复创建成功",
        extra={
            "event": "comment_created",
            "comment_id": comment.id,
            "task_id": task_id,
            "user_id": current_user.id,
            "parent_id": comment.parent_id,
            "is_reply": comment.parent_id is not None,
        },
    )
    return comment


async def update_comment(
        db: AsyncSession,
        comment_id: int,
        current_user: User,
        data: UpdateCommentRequest,
) -> Comment:
    # 1. 查询评论
    comment = await db.get(Comment, comment_id)
    if not comment:
        raise ResourceNotFoundError(
            code="COMMENT_NOT_FOUND",
            message="评论不存在",
        )

    # 2. 权限检查：仅作者本人或系统管理员
    is_sys_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN
    if not (is_sys_admin or comment.user_id == current_user.id):
        raise PermissionDeniedError(
            code="COMMENT_UPDATE_DENIED",
            message="无权修改该评论",
        )

    # 3. 更新内容
    comment.content = data.content
    # updated_at 由 BaseTimeMixin 自动更新

    await db.commit()
    await db.refresh(comment)

    logger.info(
        "评论修改成功",
        extra={
            "event": "comment_updated",
            "comment_id": comment.id,
            "task_id": comment.task_id,
            "user_id": comment.user_id,
            "operator_id": current_user.id,
        },
    )
    return comment


async def delete_comment(
        db: AsyncSession,
        comment_id: int,
        current_user: User,
) -> str:
    # 1. 查询评论
    comment = await db.get(Comment, comment_id)
    if not comment:
        raise ResourceNotFoundError(
            code="COMMENT_NOT_FOUND",
            message="评论不存在",
        )

    # 2. 权限检查：仅作者本人或系统管理员
    is_sys_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN
    if not (is_sys_admin or comment.user_id == current_user.id):
        raise PermissionDeniedError(
            code="COMMENT_DELETE_DENIED",
            message="无权删除该评论",
        )

    # 3. 删除评论（子评论由数据库级联删除）
    deleted_comment_id = comment.id
    deleted_comment_task_id = comment.task_id
    deleted_comment_user_id = comment.user_id
    await db.delete(comment)
    await db.commit()

    logger.info(
        "评论删除成功",
        extra={
            "event": "comment_deleted",
            "comment_id": deleted_comment_id,
            "task_id": deleted_comment_task_id,
            "user_id": deleted_comment_user_id,
            "operator_id": current_user.id,
        },
    )
    return "评论删除成功"


async def upload_task_attachment(
        db: AsyncSession,
        task_id: int,
        current_user: User,
        file: UploadFile,
) -> Attachment:
    # 1. 查询任务及项目信息
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

    # 2. 权限检查（与任务详情一致）
    is_sys_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN
    is_team_member = any(m.user_id == current_user.id for m in project.team.members)
    is_project_member = any(m.user_id == current_user.id for m in project.members)

    if project.status == ProjectStatus.archived:
        if not (is_sys_admin or is_project_member):
            raise PermissionDeniedError(
                code="TASK_ATTACHMENT_UPLOAD_DENIED",
                message="无权在归档任务中上传附件",
            )
    else:
        if not (is_sys_admin or is_team_member):
            raise PermissionDeniedError(
                code="TASK_ATTACHMENT_UPLOAD_DENIED",
                message="无权在该任务中上传附件",
            )

    # 3. 保存文件
    # 生成唯一文件名（保留原扩展名）
    original_filename = file.filename or "unnamed"
    file_extension = Path(original_filename).suffix
    unique_name = f"{uuid.uuid4().hex}{file_extension}"
    file_path = UPLOAD_DIR / unique_name

    # 读取文件内容并保存
    content = await file.read()
    file_size = len(content)
    with open(file_path, "wb") as f:
        f.write(content)

    # 4. 构造下载 URL（这里使用静态路径，需在 FastAPI 中挂载静态文件）
    download_url = f"/static/uploads/{unique_name}"

    # 5. 创建附件记录
    attachment = Attachment(
        target_type="task",
        target_id=task_id,
        uploader_id=current_user.id,
        file_name=original_filename,
        file_size=file_size,
        content_type=file.content_type or "application/octet-stream",
        download_url=download_url,
    )
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)

    logger.info(
        "任务附件上传成功",
        extra={
            "event": "task_attachment_uploaded",
            "attachment_id": attachment.id,
            "task_id": task_id,
            "project_id": task.project_id,
            "file_name": attachment.file_name,
            "file_size": attachment.file_size,
            "operator_id": current_user.id,
        },
    )
    return attachment


async def list_task_attachments(
        db: AsyncSession,
        task_id: int,
        current_user: User,
) -> AttachmentList:
    # 1. 查询任务并预加载项目信息（团队、项目成员）用于权限
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
                code="TASK_ATTACHMENT_ACCESS_DENIED",
                message="无权访问归档任务的附件",
            )
    else:
        if not (is_sys_admin or is_team_member):
            raise PermissionDeniedError(
                code="TASK_ATTACHMENT_ACCESS_DENIED",
                message="无权访问该任务的附件",
            )

    # 3. 查询任务附件
    att_stmt = (
        select(Attachment)
        .where(Attachment.target_type == "task", Attachment.target_id == task_id)
        .order_by(Attachment.created_at.desc())  # 最新上传在前
    )
    att_result = await db.execute(att_stmt)
    attachments = list(att_result.scalars().all())

    # 4. 构造响应
    return AttachmentList(
        items=attachments,
        total=len(attachments),
    )


async def delete_task_attachment(
        db: AsyncSession,
        task_id: int,
        attachment_id: int,
        current_user: User,
) -> str:
    # 1. 查询附件，确保其属于该任务
    attachment = await db.get(Attachment, attachment_id)
    if not attachment:
        raise ResourceNotFoundError(
            code="ATTACHMENT_NOT_FOUND",
            message="附件不存在",
        )
    if attachment.target_type != "task" or attachment.target_id != task_id:
        raise ResourceNotFoundError(
            code="TASK_ATTACHMENT_NOT_FOUND",
            message="附件不属于该任务",
        )

    # 2. 查询任务及项目信息（项目负责人、状态）
    task_stmt = (
        select(Task)
        .where(Task.id == task_id)
        .options(selectinload(Task.project))
    )
    task_result = await db.execute(task_stmt)
    task = task_result.scalar_one()
    project = task.project

    # 3. 权限检查
    is_sys_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN
    is_uploader = attachment.uploader_id == current_user.id
    is_project_owner = project.owner_user_id == current_user.id

    # 归档项目：仅系统管理员或项目负责人可操作
    if project.status == ProjectStatus.archived:
        if not (is_sys_admin or is_project_owner):
            raise PermissionDeniedError(
                code="TASK_ATTACHMENT_DELETE_DENIED",
                message="无权在归档项目中删除附件",
            )
    else:
        # 活跃项目：系统管理员、上传者本人、项目负责人
        if not (is_sys_admin or is_uploader or is_project_owner):
            raise PermissionDeniedError(
                code="TASK_ATTACHMENT_DELETE_DENIED",
                message="无权删除该附件",
            )

    # 4. 删除数据库记录
    deleted_attachment_id = attachment.id
    deleted_file_name = attachment.file_name
    deleted_file_size = attachment.file_size
    await db.delete(attachment)
    await db.commit()

    # 5. 删除磁盘文件（最佳努力，失败不影响）
    file_removed = False
    try:
        # 从 download_url 中解析文件名（假设 URL 格式为 /static/uploads/<filename>）
        filename = attachment.download_url.split("/")[-1]
        file_path = UPLOAD_DIR / filename
        if file_path.exists():
            os.remove(file_path)
            file_removed = True
    except Exception:
        # 忽略文件删除失败，记录日志（此处可用 logging）
        pass

    logger.info(
        "任务附件删除成功",
        extra={
            "event": "task_attachment_deleted",
            "attachment_id": deleted_attachment_id,
            "task_id": task_id,
            "project_id": project.id,
            "file_name": deleted_file_name,
            "file_size": deleted_file_size,
            "file_removed": file_removed,
            "operator_id": current_user.id,
        },
    )
    return "附件删除成功"


async def get_task_attachment_file(
        db: AsyncSession,
        task_id: int,
        attachment_id: int,
        current_user: User,
) -> tuple[str, str, str]:
    """
    返回 (文件路径, 原始文件名, content_type)
    """
    # 1. 查询附件，确保其属于该任务
    attachment = await db.get(Attachment, attachment_id)
    if not attachment:
        raise ResourceNotFoundError(
            code="ATTACHMENT_NOT_FOUND",
            message="附件不存在",
        )
    if attachment.target_type != "task" or attachment.target_id != task_id:
        raise ResourceNotFoundError(
            code="TASK_ATTACHMENT_NOT_FOUND",
            message="附件不属于该任务",
        )

    # 2. 查询任务及项目信息
    task_stmt = (
        select(Task)
        .where(Task.id == task_id)
        .options(
            selectinload(Task.project).selectinload(Project.team).selectinload(Team.members),
            selectinload(Task.project).selectinload(Project.members),
        )
    )
    task_result = await db.execute(task_stmt)
    task = task_result.scalar_one()
    project = task.project

    # 3. 权限检查
    is_sys_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN
    is_team_member = any(m.user_id == current_user.id for m in project.team.members)
    is_project_member = any(m.user_id == current_user.id for m in project.members)

    if project.status == ProjectStatus.archived:
        if not (is_sys_admin or is_project_member):
            raise PermissionDeniedError(
                code="TASK_ATTACHMENT_DOWNLOAD_DENIED",
                message="无权下载归档任务的附件",
            )
    else:
        if not (is_sys_admin or is_team_member):
            raise PermissionDeniedError(
                code="TASK_ATTACHMENT_DOWNLOAD_DENIED",
                message="无权下载该任务的附件",
            )

    # 4. 确定文件路径
    # 从 download_url 中提取文件名（我们存储时使用的是 UUID 文件名）
    filename = attachment.download_url.split("/")[-1]
    file_path = UPLOAD_DIR / filename

    # 检查文件是否存在
    if not file_path.exists():
        raise ResourceNotFoundError(
            code="ATTACHMENT_FILE_NOT_FOUND",
            message="文件不存在",
        )

    logger.info(
        "任务附件下载成功",
        extra={
            "event": "task_attachment_downloaded",
            "attachment_id": attachment.id,
            "task_id": task_id,
            "project_id": project.id,
            "file_name": attachment.file_name,
            "file_size": attachment.file_size,
            "operator_id": current_user.id,
        },
    )
    return str(file_path), attachment.file_name, attachment.content_type


async def upload_project_attachment(
        db: AsyncSession,
        project_id: int,
        current_user: User,
        file: UploadFile,
) -> Attachment:
    # 1. 查询项目并预加载团队成员和项目成员
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
                code="PROJECT_ATTACHMENT_UPLOAD_DENIED",
                message="无权在归档项目中上传附件",
            )
    else:
        if not (is_sys_admin or is_team_member):
            raise PermissionDeniedError(
                code="PROJECT_ATTACHMENT_UPLOAD_DENIED",
                message="无权在该项目中上传附件",
            )

    # 3. 保存文件
    original_filename = file.filename or "unnamed"
    file_extension = Path(original_filename).suffix
    unique_name = f"{uuid.uuid4().hex}{file_extension}"
    file_path = UPLOAD_DIR / unique_name

    content = await file.read()
    file_size = len(content)
    with open(file_path, "wb") as f:
        f.write(content)

    # 4. 构造下载 URL
    download_url = f"/static/uploads/{unique_name}"

    # 5. 创建附件记录
    attachment = Attachment(
        target_type="project",
        target_id=project_id,
        uploader_id=current_user.id,
        file_name=original_filename,
        file_size=file_size,
        content_type=file.content_type or "application/octet-stream",
        download_url=download_url,
    )
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)

    logger.info(
        "项目附件上传成功",
        extra={
            "event": "project_attachment_uploaded",
            "attachment_id": attachment.id,
            "project_id": project_id,
            "file_name": attachment.file_name,
            "file_size": attachment.file_size,
            "operator_id": current_user.id,
        },
    )
    return attachment


async def list_project_attachments(
        db: AsyncSession,
        project_id: int,
        current_user: User,
) -> AttachmentList:
    # 1. 查询项目并预加载团队成员和项目成员
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
                code="PROJECT_ATTACHMENT_ACCESS_DENIED",
                message="无权访问归档项目的附件",
            )
    else:
        if not (is_sys_admin or is_team_member):
            raise PermissionDeniedError(
                code="PROJECT_ATTACHMENT_ACCESS_DENIED",
                message="无权访问该项目的附件",
            )

    # 3. 查询项目附件
    att_stmt = (
        select(Attachment)
        .where(Attachment.target_type == "project", Attachment.target_id == project_id)
        .order_by(Attachment.created_at.desc())  # 最新上传在前
    )
    att_result = await db.execute(att_stmt)
    attachments = list(att_result.scalars().all())

    # 4. 构造响应
    return AttachmentList(
        items=attachments,
        total=len(attachments),
    )


async def delete_project_attachment(
        db: AsyncSession,
        project_id: int,
        attachment_id: int,
        current_user: User,
) -> str:
    # 1. 查询附件，确保其属于该项目
    attachment = await db.get(Attachment, attachment_id)
    if not attachment:
        raise ResourceNotFoundError(
            code="ATTACHMENT_NOT_FOUND",
            message="附件不存在",
        )
    if attachment.target_type != "project" or attachment.target_id != project_id:
        raise ResourceNotFoundError(
            code="PROJECT_ATTACHMENT_NOT_FOUND",
            message="附件不属于该项目",
        )

    # 2. 查询项目信息（所有者、状态）
    project = await db.get(Project, project_id)
    if not project:
        raise ResourceNotFoundError(
            code="PROJECT_NOT_FOUND",
            message="项目不存在",
        )

    # 3. 权限检查
    is_sys_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN
    is_uploader = attachment.uploader_id == current_user.id
    is_project_owner = project.owner_user_id == current_user.id

    # 归档项目：仅系统管理员或项目负责人可操作
    if project.status == ProjectStatus.archived:
        if not (is_sys_admin or is_project_owner):
            raise PermissionDeniedError(
                code="PROJECT_ATTACHMENT_DELETE_DENIED",
                message="无权在归档项目中删除附件",
            )
    else:
        # 活跃项目：系统管理员、上传者本人、项目负责人
        if not (is_sys_admin or is_uploader or is_project_owner):
            raise PermissionDeniedError(
                code="PROJECT_ATTACHMENT_DELETE_DENIED",
                message="无权删除该附件",
            )

    # 4. 删除数据库记录
    deleted_attachment_id = attachment.id
    deleted_file_name = attachment.file_name
    deleted_file_size = attachment.file_size
    await db.delete(attachment)
    await db.commit()

    # 5. 删除磁盘文件（尽力而为）
    file_removed = False
    try:
        # 从 download_url 中提取文件名
        filename = attachment.download_url.split("/")[-1]
        file_path = UPLOAD_DIR / filename
        if file_path.exists():
            os.remove(file_path)
            file_removed = True
    except Exception:
        # 记录日志，忽略失败
        pass

    logger.info(
        "项目附件删除成功",
        extra={
            "event": "project_attachment_deleted",
            "attachment_id": deleted_attachment_id,
            "project_id": project_id,
            "file_name": deleted_file_name,
            "file_size": deleted_file_size,
            "file_removed": file_removed,
            "operator_id": current_user.id,
        },
    )
    return "附件删除成功"


async def get_project_attachment_file(
        db: AsyncSession,
        project_id: int,
        attachment_id: int,
        current_user: User,
) -> tuple[str, str, str]:
    """
    返回 (文件路径, 原始文件名, content_type)
    """
    # 1. 查询附件，确保其属于该项目
    attachment = await db.get(Attachment, attachment_id)
    if not attachment:
        raise ResourceNotFoundError(
            code="ATTACHMENT_NOT_FOUND",
            message="附件不存在",
        )
    if attachment.target_type != "project" or attachment.target_id != project_id:
        raise ResourceNotFoundError(
            code="PROJECT_ATTACHMENT_NOT_FOUND",
            message="附件不属于该项目",
        )

    # 2. 查询项目及团队成员/项目成员
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

    # 3. 权限检查
    is_sys_admin = current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN
    is_team_member = any(m.user_id == current_user.id for m in project.team.members)
    is_project_member = any(m.user_id == current_user.id for m in project.members)

    if project.status == ProjectStatus.archived:
        if not (is_sys_admin or is_project_member):
            raise PermissionDeniedError(
                code="PROJECT_ATTACHMENT_DOWNLOAD_DENIED",
                message="无权下载归档项目的附件",
            )
    else:
        if not (is_sys_admin or is_team_member):
            raise PermissionDeniedError(
                code="PROJECT_ATTACHMENT_DOWNLOAD_DENIED",
                message="无权下载该项目的附件",
            )

    # 4. 确定文件路径
    filename = attachment.download_url.split("/")[-1]
    file_path = UPLOAD_DIR / filename

    # 检查文件是否存在
    if not file_path.exists():
        raise ResourceNotFoundError(
            code="ATTACHMENT_FILE_NOT_FOUND",
            message="文件不存在",
        )

    logger.info(
        "项目附件下载成功",
        extra={
            "event": "project_attachment_downloaded",
            "attachment_id": attachment.id,
            "project_id": project_id,
            "file_name": attachment.file_name,
            "file_size": attachment.file_size,
            "operator_id": current_user.id,
        },
    )
    return str(file_path), attachment.file_name, attachment.content_type



