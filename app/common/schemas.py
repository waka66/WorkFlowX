from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime, date
from enum import Enum
from typing import List, Literal, Optional
from app.models.system import NotificationType


# 注册
class GlobalRole(str, Enum):
    SYSTEM_ADMIN = "system_admin"
    USER = "user"
class RegisterRequest(BaseModel):
    username: str = Field(
        min_length=3,
        max_length=32,
        pattern=r"^[a-zA-Z0-9_]+$"
    )
    password: str = Field(
        min_length=8,
        max_length=128,
        description="密码至少 8 位"
    )
    display_name: str | None = Field(
        default=None,
        max_length=64,
        description="显示名称，不传时后端默认使用 username"
    )
    email: str = Field(
        max_length=128
    )
class UserResponse(BaseModel):
    id: int = Field(
        ge=1
    )
    username: str = Field(
        min_length=3,
        max_length=32
    )
    display_name: str | None = Field(
        default=None,
        max_length=64
    )
    email: str | None = Field(
        default=None,
        max_length=128
    )
    global_role: GlobalRole
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

# 登录
class LoginRequest(BaseModel):
    username: str = Field(
        min_length=3,
        max_length=32,
        pattern=r"^[a-zA-Z0-9_]+$",
        description="登录用户名"
    )
    password: str = Field(
        min_length=8,
        max_length=128,
        description="登录密码"
    )
    device_id: str = Field(
        min_length=1,
        max_length=128,
        description="设备ID"
    )
    device_name: str = Field(
        min_length=1,
        max_length=128,
        description="设备名称"
    )
    user_agent: str = Field(
        min_length=1,
        max_length=512,
        description="用户代理信息"
    )
class AuthTokensResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = Field(
        default="Bearer"
    )
    expires_in: int = Field(
        ge=1
    )
    session_id: int = Field(
        ge=1
    )
    user: UserResponse

# 刷新令牌
class RefreshTokenRequest(BaseModel):
    refresh_token: str
    device_id: str = Field(
        min_length=1,
        max_length=128,
        description="设备ID"
    )

# 注销
class LogoutRequest(BaseModel):
    device_id: str = Field(
        min_length=1,
        max_length=128,
        description="设备ID"
    )

class UserSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(
        ge=1
    )
    user_id: int = Field(
        ge=1
    )
    device_id: str = Field(
        min_length=1,
        max_length=128,
        description="设备ID"
    )
    device_name: str = Field(
        min_length=1,
        max_length=128,
        description="设备名称"
    )
    user_agent: str = Field(
        min_length=1,
        max_length=512,
        description="用户代理信息"
    )
    ip_address: str = Field(
        min_length=1,
        max_length=45,
        description="IP地址"
    )
    expire_at: datetime
    revoked_at: datetime | None
    last_used_at: datetime | None

# 修改密码
class ChangePasswordRequest(BaseModel):
    old_password: str = Field(
        min_length=8,
        max_length=128,
        description="旧密码"
    )
    new_password: str = Field(
        min_length=8,
        max_length=128,
        description="新密码"
    )
class MessageResponse(BaseModel):
    message: str


class UserStatus(str, Enum):
    active = "active"
    disabled = "disabled"
class PaginatedUsers(BaseModel):
    items: list[UserResponse]
    total: int
    page: int
    page_size: int
    has_more: bool

class UserUpdateRequest(BaseModel):
    display_name: str | None = Field(None, max_length=64, description="显示名称，可设为 null 清空")
    status: UserStatus | None = Field(None, description="用户状态，不传则不修改")
    global_role: GlobalRole | None = Field(None, description="全局角色，不传则不修改")

    model_config = ConfigDict(extra="forbid")  # 禁止额外字段

class TeamStatus(str, Enum):
    active = "active"
    archived = "archived"
class TeamRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
# 创建团队请求
class CreateTeamRequest(BaseModel):
    name: str = Field(
        ...,
        min_length=1,
        max_length=100
    )
    description: str | None = Field(
        None,
        max_length=500
    )

    model_config = ConfigDict(extra="forbid")
# 团队响应模型
class TeamResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    creator_id: int
    status: TeamStatus
    created_at: datetime
    updated_at: datetime

class PaginatedTeams(BaseModel):
    items: list[TeamResponse]
    total: int
    page: int
    page_size: int
    has_more: bool

class TeamMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    team_id: int
    user_id: int
    username: str
    display_name: str | None
    role: TeamRole
    joined_at: datetime
class TeamDetailResponse(TeamResponse):
    members: list[TeamMemberResponse]

class UpdateTeamRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    status: TeamStatus | None = Field(None)

    model_config = ConfigDict(extra="forbid")

class TeamMemberList(BaseModel):
    items: list[TeamMemberResponse]
    total: int

class AddTeamMemberRequest(BaseModel):
    user_id: int = Field(..., ge=1, description="要添加的用户ID")
    role: TeamRole = Field(..., description="分配给该成员的角色")

    model_config = ConfigDict(extra="forbid")

class UpdateTeamMemberRoleRequest(BaseModel):
    role: TeamRole = Field(..., description="新的成员角色")

    model_config = ConfigDict(extra="forbid")

class ProjectStatus(str, Enum):
    planned = "planned"
    active = "active"
    completed = "completed"
    archived = "archived"
class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    owner_user_id: int | None = Field(None, ge=1, description="项目负责人，可选，默认当前用户")
    start_date: date | None = None
    end_date: date | None = None
    status: ProjectStatus | None = None  # 可选，默认 planned

    model_config = ConfigDict(extra="forbid")
class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    team_id: int
    name: str
    description: str | None
    owner_user_id: int
    start_date: date | None
    end_date: date | None
    status: ProjectStatus
    progress: int
    created_at: datetime
    updated_at: datetime

class PaginatedProjects(BaseModel):
    items: list[ProjectResponse]
    total: int
    page: int
    page_size: int
    has_more: bool

class ProjectRole(str, Enum):
    OWNER = "OWNER"
    MEMBER = "MEMBER"
class ProjectMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    user_id: int
    username: str
    display_name: str | None
    role: ProjectRole
    joined_at: datetime
class ProjectDetailResponse(ProjectResponse):
    members: list[ProjectMemberResponse]

class UpdateProjectRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    owner_user_id: int | None = Field(None, ge=1)
    start_date: date | None = Field(None)
    end_date: date | None = Field(None)
    status: ProjectStatus | None = Field(None)

    model_config = ConfigDict(extra="forbid")

class ProjectMemberList(BaseModel):
    items: list[ProjectMemberResponse]
    total: int

class AddProjectMemberRequest(BaseModel):
    user_id: int = Field(..., ge=1, description="要添加的用户ID")
    role: ProjectRole = Field(..., description="分配的角色")

    model_config = ConfigDict(extra="forbid")

class UpdateProjectMemberRoleRequest(BaseModel):
    role: ProjectRole = Field(..., description="新的成员角色")

    model_config = ConfigDict(extra="forbid")

class WorkflowStatusInput(BaseModel):
    key: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=64)
    order: int = Field(..., ge=0)
    color: str | None = Field(None, max_length=16)
    is_initial: bool = False
    is_final: bool = False
class WorkflowTransitionInput(BaseModel):
    from_status_key: str = Field(..., min_length=1, max_length=64)
    to_status_key: str = Field(..., min_length=1, max_length=64)
    allowed_roles: List[ProjectRole] = Field(default_factory=list)
class UpdateWorkflowRequest(BaseModel):
    statuses: List[WorkflowStatusInput]
    transitions: List[WorkflowTransitionInput]

    model_config = ConfigDict(extra="forbid")
class WorkflowStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    key: str
    name: str
    order: int
    color: str | None
    is_initial: bool
    is_final: bool
class WorkflowTransitionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    from_status_key: str
    to_status_key: str
    allowed_roles: List[ProjectRole]
class WorkflowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    statuses: List[WorkflowStatusResponse]
    transitions: List[WorkflowTransitionResponse]

class Priority(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
class CreateTaskRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=5000)
    assignee_user_id: int | None = Field(None, ge=1)
    priority: Priority = Priority.P2  # 默认中等
    due_date: date | None = None
    tags: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    title: str
    description: str | None
    creator_id: int
    assignee_user_id: int | None
    status_key: str
    priority: Priority
    due_date: date | None
    tags: List[str]
    created_at: datetime
    updated_at: datetime

class PaginatedTasks(BaseModel):
    items: List[TaskResponse]
    total: int
    page: int
    page_size: int
    has_more: bool

class CommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    user_id: int
    parent_id: int | None
    content: str
    created_at: datetime
    updated_at: datetime
class AttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    target_type: Literal["project", "task"]
    target_id: int
    uploader_id: int
    file_name: str
    file_size: int
    content_type: str
    download_url: str
    created_at: datetime
class TaskDetailResponse(TaskResponse):
    comments: List[CommentResponse]
    attachments: List[AttachmentResponse]

class UpdateTaskRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=5000)
    assignee_user_id: int | None = Field(None, ge=1)
    priority: Priority | None = None
    due_date: date | None = Field(None)
    tags: List[str] | None = Field(None, max_items=20)

    model_config = ConfigDict(extra="forbid")

class TransitionTaskRequest(BaseModel):
    to_status_key: str = Field(..., min_length=1, max_length=64)
    comment: str | None = Field(None, max_length=5000)

    model_config = ConfigDict(extra="forbid")

class CommentList(BaseModel):
    items: List[CommentResponse]
    total: int

class CreateCommentRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
    parent_id: int | None = Field(None, ge=1)

    model_config = ConfigDict(extra="forbid")

class UpdateCommentRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)

    model_config = ConfigDict(extra="forbid")

class AttachmentList(BaseModel):
    items: List[AttachmentResponse]
    total: int


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    type: NotificationType
    title: str
    content: str | None
    related_entity_type: str | None
    related_entity_id: int | None
    read_at: datetime | None
    created_at: datetime
class PaginatedNotifications(BaseModel):
    items: List[NotificationResponse]
    total: int
    page: int
    page_size: int
    has_more: bool

class ActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    team_id: int | None
    project_id: int | None
    task_id: int | None
    actor_user_id: int
    action: str
    target_type: str | None
    target_id: int | None
    content: str
    created_at: datetime

class ActivityList(BaseModel):
    items: list[ActivityResponse]
    total: int

class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    action: str
    target_type: str | None
    target_id: int | None
    ip_address: str | None
    user_agent: str | None
    created_at: datetime

class PaginatedAuditLogs(BaseModel):
    items: list[AuditLogResponse]
    total: int
    page: int
    page_size: int
    has_more: bool

class PersonalDashboard(BaseModel):
    my_task_count: int
    overdue_task_count: int
    pending_task_count: int
    recent_activities: List[ActivityResponse]
    notifications: List[NotificationResponse]

class MemberWorkload(BaseModel):
    user_id: int
    task_count: int
class ProjectDashboard(BaseModel):
    task_total: int
    completion_rate: int
    in_progress_count: int
    overdue_count: int
    member_workload: List[MemberWorkload]

class ProjectProgressItem(BaseModel):
    project_id: int
    name: str
    progress: int
class TeamDashboard(BaseModel):
    project_count: int
    active_project_count: int
    task_count: int
    member_count: int
    project_progress: List[ProjectProgressItem]

class SearchType(str, Enum):
    project = "project"
    task = "task"
    user = "user"
    comment = "comment"
class SearchResult(BaseModel):
    type: SearchType
    id: int
    title: str
    summary: Optional[str] = None
class SearchResponse(BaseModel):
    query: str
    results: List[SearchResult]












