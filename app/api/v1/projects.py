from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, Path, Query
from starlette import status

from app.common.schemas import (ProjectResponse, CreateProjectRequest, PaginatedProjects, ProjectStatus,
                                ProjectDetailResponse, UpdateProjectRequest, MessageResponse,
                                ProjectMemberList, ProjectMemberResponse, AddProjectMemberRequest,
                                UpdateProjectMemberRoleRequest)
from app.db.session import get_db
from app.models.user import User
from app.api.deps import get_current_user
from app.services import project_service


team_projects_router = APIRouter(prefix="/teams/{team_id}/projects", tags=["Projects"])
projects_router = APIRouter(prefix="/projects", tags=["Projects"])

@team_projects_router.post(
    "/",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建项目",
    operation_id="createProject"
)
async def create_project(
    team_id: int = Path(..., ge=1, description="团队 ID"),
    data: CreateProjectRequest = ...,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    project = await project_service.create_project(db, team_id, current_user, data)
    return project


@team_projects_router.get(
    "/",
    response_model=PaginatedProjects,
    summary="团队项目列表",
    operation_id="listProjects"
)
async def list_team_projects(
    team_id: int = Path(..., ge=1, description="团队 ID"),
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    keyword: str | None = Query(None, max_length=100, description="按名称搜索"),
    status: ProjectStatus | None = Query(None, description="按状态筛选"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    projects, total = await project_service.list_projects(
        db,
        team_id=team_id,
        current_user=current_user,
        page=page,
        page_size=page_size,
        keyword=keyword,
        status=status,
    )
    return PaginatedProjects(
        items=projects,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )


@projects_router.get(
    "/{project_id}",
    response_model=ProjectDetailResponse,
    summary="项目详情",
    operation_id="getProject"
)
async def get_project(
    project_id: int = Path(..., ge=1, description="项目 ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    project = await project_service.get_project_detail(db, project_id, current_user)
    return project


@projects_router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="更新项目",
    operation_id="updateProject"
)
async def update_project(
    project_id: int = Path(..., ge=1, description="项目 ID"),
    data: UpdateProjectRequest = ...,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    project = await project_service.update_project(db, project_id, current_user, data)
    return project


@projects_router.delete(
    "/{project_id}",
    response_model=MessageResponse,
    summary="归档或删除项目",
    operation_id="deleteProject"
)
async def delete_project(
    project_id: int = Path(..., ge=1, description="项目 ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    message = await project_service.archive_project(db, project_id, current_user)
    return {"message": message}


@projects_router.get(
    "/{project_id}/members",
    response_model=ProjectMemberList,
    summary="项目成员列表",
    operation_id="listProjectMembers"
)
async def list_project_members(
    project_id: int = Path(..., ge=1, description="项目 ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await project_service.list_project_members(db, project_id, current_user)


@projects_router.post(
    "/{project_id}/members",
    response_model=ProjectMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="添加项目成员",
    operation_id="addProjectMember"
)
async def add_project_member(
    project_id: int = Path(..., ge=1, description="项目 ID"),
    data: AddProjectMemberRequest = ...,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    member = await project_service.add_project_member(db, project_id, current_user, data)
    return member


@projects_router.patch(
    "/{project_id}/members/{user_id}",
    response_model=ProjectMemberResponse,
    summary="调整项目成员角色",
    operation_id="updateProjectMemberRole"
)
async def update_project_member_role(
    project_id: int = Path(..., ge=1, description="项目 ID"),
    user_id: int = Path(..., ge=1, description="用户 ID"),
    data: UpdateProjectMemberRoleRequest = ...,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    member = await project_service.update_project_member_role(
        db, project_id, user_id, current_user, data
    )
    return member


@projects_router.delete(
    "/{project_id}/members/{user_id}",
    response_model=MessageResponse,
    summary="移除项目成员",
    operation_id="removeProjectMember"
)
async def remove_project_member(
    project_id: int = Path(..., ge=1, description="项目 ID"),
    user_id: int = Path(..., ge=1, description="用户 ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    message = await project_service.remove_project_member(db, project_id, user_id, current_user)
    return {"message": message}


