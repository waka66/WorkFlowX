from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, Path, Query, File, UploadFile
from typing import Optional
from starlette import status
from datetime import date
from fastapi.responses import FileResponse

from app.common.schemas import (WorkflowResponse, UpdateWorkflowRequest, TaskResponse, CreateTaskRequest,
                                PaginatedTasks, Priority, TaskDetailResponse, UpdateTaskRequest, MessageResponse,
                                TransitionTaskRequest, CommentList, CommentResponse, CreateCommentRequest,
                                UpdateCommentRequest, AttachmentResponse, AttachmentList)
from app.db.session import get_db
from app.models.user import User
from app.api.deps import get_current_user
from app.services import task_service


workflows_router = APIRouter(prefix="/projects/{project_id}/workflow", tags=["Workflows"])
tasks_router = APIRouter(prefix="/projects/{project_id}/tasks", tags=["Tasks"])
router = APIRouter(prefix="/tasks", tags=["Tasks"])
comments_router = APIRouter(prefix="/comments", tags=["Comments"])
projects_router = APIRouter(prefix="/projects", tags=["Attachments"])



@workflows_router.put(
    "/",
    response_model=WorkflowResponse,
    summary="更新项目工作流",
    operation_id="updateWorkflow"
)
async def update_workflow(
    project_id: int = Path(..., ge=1, description="项目 ID"),
    data: UpdateWorkflowRequest = ...,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    workflow = await task_service.update_workflow(db, project_id, current_user, data)
    return workflow


@workflows_router.get(
    "/",
    response_model=WorkflowResponse,
    summary="获取项目工作流",
    operation_id="getWorkflow"
)
async def get_workflow(
    project_id: int = Path(..., ge=1, description="项目 ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    workflow = await task_service.get_workflow(db, project_id, current_user)
    return workflow


@tasks_router.post(
    "/",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建任务",
    operation_id="createTask"
)
async def create_task(
    project_id: int = Path(..., ge=1, description="项目 ID"),
    data: CreateTaskRequest = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = await task_service.create_task(db, project_id, current_user, data)
    return task


@tasks_router.get(
    "/",
    response_model=PaginatedTasks,
    summary="项目任务列表",
    operation_id="listTasks"
)
async def list_tasks(
    project_id: int = Path(..., ge=1, description="项目 ID"),
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    assignee_user_id: Optional[int] = Query(None, ge=1, description="按负责人筛选"),
    status_key: Optional[str] = Query(None, max_length=64, description="按工作流状态筛选"),
    priority: Optional[Priority] = Query(None, description="按优先级筛选"),
    due_date_from: Optional[date] = Query(None, description="截止时间起"),
    due_date_to: Optional[date] = Query(None, description="截止时间止"),
    tag: Optional[str] = Query(None, max_length=50, description="按标签筛选"),
    keyword: Optional[str] = Query(None, max_length=200, description="按标题搜索"),
    overdue: Optional[bool] = Query(None, description="仅逾期任务"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await task_service.list_tasks(
        db,
        project_id=project_id,
        current_user=current_user,
        page=page,
        page_size=page_size,
        assignee_user_id=assignee_user_id,
        status_key=status_key,
        priority=priority,
        due_date_from=due_date_from,
        due_date_to=due_date_to,
        tag=tag,
        keyword=keyword,
        overdue=overdue,
    )
    return result


@router.get(
    "/{task_id}",
    response_model=TaskDetailResponse,
    summary="任务详情",
    operation_id="getTask"
)
async def get_task(
    task_id: int = Path(..., ge=1, description="任务 ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await task_service.get_task_detail(db, task_id, current_user)


@router.patch(
    "/{task_id}",
    response_model=TaskResponse,
    summary="更新任务",
    operation_id="updateTask"
)
async def update_task(
    task_id: int = Path(..., ge=1, description="任务 ID"),
    data: UpdateTaskRequest = ...,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    task = await task_service.update_task(db, task_id, current_user, data)
    return task


@router.delete(
    "/{task_id}",
    response_model=MessageResponse,
    summary="删除任务",
    operation_id="deleteTask"
)
async def delete_task(
    task_id: int = Path(..., ge=1, description="任务 ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    message = await task_service.delete_task(db, task_id, current_user)
    return {"message": message}


@router.post(
    "/{task_id}/transition",
    response_model=TaskResponse,
    summary="任务状态流转",
    operation_id="transitionTask"
)
async def transition_task(
    task_id: int = Path(..., ge=1, description="任务 ID"),
    data: TransitionTaskRequest = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = await task_service.transition_task(db, task_id, current_user, data)
    return task


@router.get(
    "/",
    response_model=PaginatedTasks,
    summary="我的任务 / 跨项目任务查询",
    operation_id="listMyTasks"
)
async def list_my_tasks(
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    scope: Optional[str] = Query(None, description="任务视图范围", enum=["my", "assigned_to_me", "overdue", "pending"]),
    project_id: Optional[int] = Query(None, ge=1, description="按项目筛选"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await task_service.list_my_tasks(
        db,
        current_user=current_user,
        page=page,
        page_size=page_size,
        scope=scope,
        project_id=project_id,
    )
    return result


@router.get(
    "/{task_id}/comments",
    response_model=CommentList,
    summary="任务评论列表",
    operation_id="listComments"
)
async def list_comments(
    task_id: int = Path(..., ge=1, description="任务 ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await task_service.list_task_comments(db, task_id, current_user)


@router.post(
    "/{task_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="新增评论或回复",
    operation_id="createComment"
)
async def create_comment(
    task_id: int = Path(..., ge=1, description="任务 ID"),
    data: CreateCommentRequest = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    comment = await task_service.create_task_comment(db, task_id, current_user, data)
    return comment


@comments_router.patch(
    "/{comment_id}",
    response_model=CommentResponse,
    summary="修改评论",
    operation_id="updateComment"
)
async def update_comment(
    comment_id: int = Path(..., ge=1, description="评论 ID"),
    data: UpdateCommentRequest = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    comment = await task_service.update_comment(db, comment_id, current_user, data)
    return comment


@comments_router.delete(
    "/{comment_id}",
    response_model=MessageResponse,
    summary="删除评论",
    operation_id="deleteComment"
)
async def delete_comment(
    comment_id: int = Path(..., ge=1, description="评论 ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    message = await task_service.delete_comment(db, comment_id, current_user)
    return {"message": message}


@router.post(
    "/{task_id}/attachments",
    response_model=AttachmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="上传任务附件",
    operation_id="uploadTaskAttachment"
)
async def upload_task_attachment(
    task_id: int = Path(..., ge=1, description="任务 ID"),
    file: UploadFile = File(..., description="上传的文件"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    attachment = await task_service.upload_task_attachment(db, task_id, current_user, file)
    return attachment


@router.get(
    "/{task_id}/attachments",
    response_model=AttachmentList,
    summary="任务附件列表",
    operation_id="listTaskAttachments"
)
async def list_task_attachments(
    task_id: int = Path(..., ge=1, description="任务 ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await task_service.list_task_attachments(db, task_id, current_user)


@router.delete(
    "/{task_id}/attachments/{attachment_id}",
    response_model=MessageResponse,
    summary="删除任务附件",
    operation_id="deleteTaskAttachment"
)
async def delete_task_attachment(
    task_id: int = Path(..., ge=1, description="任务 ID"),
    attachment_id: int = Path(..., ge=1, description="附件 ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    message = await task_service.delete_task_attachment(
        db, task_id, attachment_id, current_user
    )
    return {"message": message}


@router.get(
    "/{task_id}/attachments/{attachment_id}/download",
    summary="下载任务附件",
    operation_id="downloadTaskAttachment",
    response_class=FileResponse,
    responses={
        200: {
            "content": {"application/octet-stream": {}},
            "description": "附件文件流",
        }
    },
)
async def download_task_attachment(
    task_id: int = Path(..., ge=1, description="任务 ID"),
    attachment_id: int = Path(..., ge=1, description="附件 ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    file_path, original_filename, content_type = await task_service.get_task_attachment_file(
        db, task_id, attachment_id, current_user
    )
    return FileResponse(
        path=file_path,
        media_type=content_type,
        filename=original_filename,  # 设置下载文件名
    )


@projects_router.post(
    "/{project_id}/attachments",
    response_model=AttachmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="上传项目附件",
    operation_id="uploadProjectAttachment"
)
async def upload_project_attachment(
    project_id: int = Path(..., ge=1, description="项目 ID"),
    file: UploadFile = File(..., description="上传的文件"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    attachment = await task_service.upload_project_attachment(db, project_id, current_user, file)
    return attachment


@projects_router.get(
    "/{project_id}/attachments",
    response_model=AttachmentList,
    summary="项目附件列表",
    operation_id="listProjectAttachments"
)
async def list_project_attachments(
    project_id: int = Path(..., ge=1, description="项目 ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await task_service.list_project_attachments(db, project_id, current_user)


@projects_router.delete(
    "/{project_id}/attachments/{attachment_id}",
    response_model=MessageResponse,
    summary="删除项目附件",
    operation_id="deleteProjectAttachment"
)
async def delete_project_attachment(
    project_id: int = Path(..., ge=1, description="项目 ID"),
    attachment_id: int = Path(..., ge=1, description="附件 ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    message = await task_service.delete_project_attachment(
        db, project_id, attachment_id, current_user
    )
    return {"message": message}


@projects_router.get(
    "/{project_id}/attachments/{attachment_id}/download",
    summary="下载项目附件",
    operation_id="downloadProjectAttachment",
    response_class=FileResponse,
    responses={
        200: {
            "content": {"application/octet-stream": {}},
            "description": "附件文件流",
        }
    },
)
async def download_project_attachment(
    project_id: int = Path(..., ge=1, description="项目 ID"),
    attachment_id: int = Path(..., ge=1, description="附件 ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    file_path, original_filename, content_type = await task_service.get_project_attachment_file(
        db, project_id, attachment_id, current_user
    )
    return FileResponse(
        path=file_path,
        media_type=content_type,
        filename=original_filename,
    )









