from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, Path, Query
from typing import Optional
from fastapi.responses import FileResponse

from app.common.schemas import (PaginatedNotifications, MessageResponse, NotificationResponse, ActivityList,
                                PaginatedAuditLogs, PersonalDashboard, ProjectDashboard, TeamDashboard, SearchResponse, SearchType)
from app.db.session import get_db
from app.models.user import User
from app.api.deps import get_current_user
from app.services import system_service


router = APIRouter(prefix="/notifications", tags=["Notifications"])
activities_router = APIRouter(prefix="", tags=["Activities"])
logs_router = APIRouter(prefix="/audit-logs", tags=["Audit"])
dashboard_router = APIRouter(prefix="", tags=["Dashboard"])
search_router = APIRouter(prefix="/search", tags=["Search"])


@router.get(
    "/",
    response_model=PaginatedNotifications,
    summary="通知列表",
    operation_id="listNotifications"
)
async def list_notifications(
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    read: bool | None = Query(None, description="按已读/未读筛选"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await system_service.list_notifications(
        db,
        current_user=current_user,
        page=page,
        page_size=page_size,
        read=read,
    )


@router.post(
    "/read-all",
    response_model=MessageResponse,
    summary="全部标记已读",
    operation_id="markAllNotificationsRead"
)
async def mark_all_notifications_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    message = await system_service.mark_all_read(db, current_user)
    return {"message": message}

@router.post(
    "/{notification_id}/read",
    response_model=NotificationResponse,
    summary="标记单条通知已读",
    operation_id="markNotificationRead"
)
async def mark_notification_read(
    notification_id: int = Path(..., ge=1, description="通知 ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notification = await system_service.mark_read(db, notification_id, current_user)
    return notification


@activities_router.get(
    "/teams/{team_id}/activities",
    response_model=ActivityList,
    summary="团队活动记录",
    operation_id="listTeamActivities"
)
async def list_team_activities(
    team_id: int = Path(..., ge=1, description="团队 ID"),
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await system_service.list_team_activities(
        db,
        team_id=team_id,
        current_user=current_user,
        page=page,
        page_size=page_size,
    )

@activities_router.get(
    "/projects/{project_id}/activities",
    response_model=ActivityList,
    summary="项目活动记录",
    operation_id="listProjectActivities"
)
async def list_project_activities(
    project_id: int = Path(..., ge=1, description="项目 ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await system_service.list_project_activities(db, project_id, current_user, page, page_size)

@activities_router.get(
    "/tasks/{task_id}/activities",
    response_model=ActivityList,
    summary="任务活动记录",
    operation_id="listTaskActivities"
)
async def list_task_activities(
    task_id: int = Path(..., ge=1, description="任务 ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await system_service.list_task_activities(db, task_id, current_user, page, page_size)


@logs_router.get(
    "",
    response_model=PaginatedAuditLogs,
    summary="审计日志",
    operation_id="listAuditLogs"
)
async def list_audit_logs(
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    user_id: int | None = Query(None, ge=1, description="按用户筛选"),
    action: str | None = Query(None, max_length=100, description="按操作筛选"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await system_service.list_audit_logs(
        db,
        current_user=current_user,
        page=page,
        page_size=page_size,
        user_id=user_id,
        action=action,
    )

@dashboard_router.get(
    "/dashboard/personal",
    response_model=PersonalDashboard,
    summary="个人仪表盘",
    operation_id="getPersonalDashboard"
)
async def get_personal_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await system_service.get_personal_dashboard(db, current_user)

@dashboard_router.get(
    "/projects/{project_id}/dashboard",
    response_model=ProjectDashboard,
    summary="项目仪表盘",
    operation_id="getProjectDashboard"
)
async def get_project_dashboard(
    project_id: int = Path(..., ge=1, description="项目 ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await system_service.get_project_dashboard(db, project_id, current_user)

@dashboard_router.get(
    "/teams/{team_id}/dashboard",
    response_model=TeamDashboard,
    summary="团队仪表盘",
    operation_id="getTeamDashboard"
)
async def get_team_dashboard(
    team_id: int = Path(..., ge=1, description="团队 ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await system_service.get_team_dashboard(db, team_id, current_user)

@search_router.get(
    "/",
    response_model=SearchResponse,
    summary="全局搜索",
    operation_id="globalSearch"
)
async def global_search(
    q: str = Query(..., min_length=1, max_length=200, description="搜索关键词"),
    type: SearchType | None = Query(None, description="搜索对象类型"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await system_service.global_search(db, current_user, q, type)

