from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, Query, Path
from starlette import status

from app.services import team_service
from app.common.schemas import (TeamResponse, CreateTeamRequest, PaginatedTeams, TeamStatus, TeamDetailResponse,
                                UpdateTeamRequest, MessageResponse, TeamMemberList, AddTeamMemberRequest,
                                TeamMemberResponse, UpdateTeamMemberRoleRequest)
from app.db.session import get_db

from app.models.user import User, GlobalRoleEnum
from app.api.deps import get_current_user




router = APIRouter(prefix="/teams", tags=["Teams"])


@router.post(
    "/",
    response_model=TeamResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建团队",
    operation_id="createTeam"
)
async def create_team(
    data: CreateTeamRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    team = await team_service.create_team(db, creator_id=current_user.id, data=data)
    return team


@router.get(
    "/",
    response_model=PaginatedTeams,
    summary="团队列表",
    operation_id="listTeams",
    status_code=status.HTTP_200_OK
)
async def list_teams(
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    keyword: str | None = Query(None, max_length=100, description="按名称搜索"),
    status: TeamStatus | None = Query(None, description="按状态筛选"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    teams, total = await team_service.list_teams(
        db,
        page=page,
        page_size=page_size,
        keyword=keyword,
        status=status,
        is_admin=current_user.global_role == GlobalRoleEnum.SYSTEM_ADMIN  # 根据用户是否为管理员调整默认状态过滤
    )
    return PaginatedTeams(
        items=teams,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )


@router.get(
    "/{team_id}",
    response_model=TeamDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="团队详情",
    operation_id="getTeam"
)
async def get_team(
    team_id: int = Path(..., ge=1, description="团队 ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    team = await team_service.get_team_detail(db, team_id, current_user)
    return team


@router.patch(
    "/{team_id}",
    response_model=TeamResponse,
    status_code=status.HTTP_200_OK,
    summary="更新团队",
    operation_id="updateTeam"
)
async def update_team(
    team_id: int = Path(..., ge=1, description="团队 ID"),
    update_data: UpdateTeamRequest = ...,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    team = await team_service.update_team(db, team_id, current_user, update_data)
    return team


@router.delete(
    "/{team_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="归档或删除团队",
    operation_id="deleteTeam"
)
async def delete_team(
    team_id: int = Path(..., ge=1, description="团队 ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    message = await team_service.archive_team(db, team_id, current_user)
    return {"message": message}


@router.get(
    "/{team_id}/members",
    response_model=TeamMemberList,
    status_code=status.HTTP_200_OK,
    summary="团队成员列表",
    operation_id="listTeamMembers"
)
async def list_team_members(
    team_id: int = Path(..., ge=1, description="团队 ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await team_service.list_team_members(db, team_id, current_user)


@router.post(
    "/{team_id}/members",
    response_model=TeamMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="添加团队成员",
    operation_id="addTeamMember"
)
async def add_team_member(
    team_id: int = Path(..., ge=1, description="团队 ID"),
    data: AddTeamMemberRequest = ...,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    member = await team_service.add_team_member(db, team_id, current_user, data)
    return member


@router.patch(
    "/{team_id}/members/{user_id}",
    response_model=TeamMemberResponse,
    summary="调整团队成员角色",
    operation_id="updateTeamMemberRole"
)
async def update_team_member_role(
    team_id: int = Path(..., ge=1, description="团队 ID"),
    user_id: int = Path(..., ge=1, description="用户 ID"),
    data: UpdateTeamMemberRoleRequest = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    member = await team_service.update_team_member_role(
        db, team_id, user_id, current_user, data
    )
    return member


@router.delete(
    "/{team_id}/members/{user_id}",
    response_model=MessageResponse,
    summary="移除团队成员",
    operation_id="removeTeamMember"
)
async def remove_team_member(
    team_id: int = Path(..., ge=1, description="团队 ID"),
    user_id: int = Path(..., ge=1, description="用户 ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    message = await team_service.remove_team_member(db, team_id, user_id, current_user)
    return {"message": message}






