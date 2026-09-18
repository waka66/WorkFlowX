"""
异常统计：
code
USERNAME_ALREADY_EXISTS  用户名已存在
EMAIL_ALREADY_EXISTS  邮箱已存在
INVALID_CREDENTIALS  用户名或密码错误
SESSION_NOT_FOUND  会话不存在
SESSION_REVOKED  会话已撤销
SESSION_EXPIRED  会话已过期，请重新登录
USER_NOT_FOUND  用户不存在
USER_INACTIVE  用户已禁用
TOKEN_MISSING_USER_INFO  Token缺少用户信息
TOKEN_EXPIRED  Token已过期
INVALID_ACCESS_TOKEN  无效的访问令牌
ACTIVE_SESSION_NOT_FOUND  未找到该设备的活跃会话
INVALID_OLD_PASSWORD  旧密码错误
ADMIN_REQUIRED  权限不足，需要管理员权限
CANNOT_MODIFY_OTHER_USER  无权修改其他用户的信息
CANNOT_MODIFY_ROLE  无权修改用户角色
CANNOT_MODIFY_STATUS  无权修改用户状态
TEAM_NAME_ALREADY_EXISTS  团队名称已存在
TEAM_NOT_FOUND  团队不存在
TEAM_ARCHIVED_ACCESS_DENIED  无权访问归档团队
TEAM_UPDATE_DENIED  无权更新该团队
TEAM_STATUS_UPDATE_DENIED  无权修改团队状态
TEAM_ARCHIVE_DENIED  无权归档该团队
TEAM_MEMBER_ACCESS_DENIED  无权访问团队成员
TEAM_ARCHIVED  归档团队不能执行该操作
TEAM_MEMBER_ADD_DENIED  无权添加团队成员
TEAM_OWNER_ROLE_ASSIGN_DENIED  无权分配OWNER角色
TEAM_MEMBER_ALREADY_EXISTS  用户已是团队成员
TEAM_MEMBER_NOT_FOUND  目标用户不是团队成员
TEAM_MEMBER_ROLE_UPDATE_DENIED  无权调整团队成员角色
TEAM_OWNER_ROLE_SELF_UPDATE_DENIED  OWNER不能修改自己的角色
TEAM_OWNER_REMOVE_DENIED  OWNER不能被移除
TEAM_ADMIN_SELF_REMOVE_DENIED  ADMIN不能自我移除
TEAM_MEMBER_REMOVE_DENIED  无权移除团队成员
PROJECT_NAME_ALREADY_EXISTS  项目名称在该团队中已存在
PROJECT_NOT_FOUND  项目不存在
PROJECT_ACCESS_DENIED  无权访问该项目
PROJECT_ARCHIVED_ACCESS_DENIED  无权访问归档项目
PROJECT_CREATE_DENIED  无权创建项目
PROJECT_UPDATE_DENIED  无权更新该项目
PROJECT_ARCHIVE_DENIED  无权归档该项目
PROJECT_ARCHIVED  归档项目不能执行该操作
PROJECT_MEMBER_ACCESS_DENIED  无权访问项目成员
PROJECT_MEMBER_ADD_DENIED  无权添加项目成员
PROJECT_MEMBER_NOT_TEAM_MEMBER  被添加用户不是团队成员
PROJECT_MEMBER_ALREADY_EXISTS  用户已是项目成员
PROJECT_MEMBER_NOT_FOUND  目标用户不是项目成员
PROJECT_MEMBER_ROLE_UPDATE_DENIED  无权调整项目成员角色
PROJECT_MEMBER_REMOVE_DENIED  无权移除该项目成员
PROJECT_OWNER_NOT_TEAM_MEMBER  项目负责人必须是团队成员
PROJECT_OWNER_ROLE_DEMOTE_DENIED  不能降级项目负责人的角色
PROJECT_OWNER_REMOVE_DENIED  不能移除项目负责人，请先转移负责人
PROJECT_DATE_RANGE_INVALID  截止日期不能早于开始日期
WORKFLOW_UPDATE_DENIED  无权修改项目工作流
WORKFLOW_STATUS_KEY_DUPLICATE  状态 key 重复
WORKFLOW_INITIAL_STATUS_INVALID  必须且只能有一个初始状态
WORKFLOW_TRANSITION_STATUS_NOT_FOUND  转换引用了不存在的状态 key
WORKFLOW_SELF_TRANSITION_DENIED  不允许自循环转换
WORKFLOW_DEFINITION_CONFLICT  工作流定义冲突
WORKFLOW_ARCHIVED_ACCESS_DENIED  无权访问归档项目的工作流
WORKFLOW_ACCESS_DENIED  无权访问该项目工作流
WORKFLOW_NOT_FOUND  工作流不存在
TASK_NOT_FOUND  任务不存在
TASK_ACCESS_DENIED  无权访问该任务
TASK_ARCHIVED_ACCESS_DENIED  无权访问归档项目的任务
TASK_CREATE_DENIED  无权在该项目中创建任务
TASK_UPDATE_DENIED  无权更新该任务
TASK_DELETE_DENIED  无权删除该任务
TASK_WORKFLOW_NOT_CONFIGURED  项目未配置工作流
TASK_WORKFLOW_INITIAL_STATUS_MISSING  工作流缺少初始状态
TASK_ASSIGNEE_NOT_PROJECT_MEMBER  被分配人不是项目成员
TASK_TAG_TOO_LONG  标签长度不能超过50个字符
TASK_TRANSITION_TARGET_STATUS_NOT_FOUND  目标状态不存在于工作流中
TASK_TRANSITION_NOT_FOUND  不存在从当前状态到目标状态的转换
TASK_TRANSITION_NOT_PROJECT_MEMBER  你不是项目成员，无权执行状态流转
TASK_TRANSITION_ROLE_DENIED  你的角色无权执行此状态流转
COMMENT_NOT_FOUND  评论不存在
COMMENT_ACCESS_DENIED  无权访问该任务的评论
COMMENT_ARCHIVED_ACCESS_DENIED  无权访问归档任务的评论
COMMENT_CREATE_DENIED  无权在该任务中添加评论
COMMENT_UPDATE_DENIED  无权修改该评论
COMMENT_DELETE_DENIED  无权删除该评论
PARENT_COMMENT_NOT_FOUND  父评论不存在
PARENT_COMMENT_NOT_IN_TASK  父评论不属于该任务
ATTACHMENT_NOT_FOUND  附件不存在
ATTACHMENT_FILE_NOT_FOUND  附件文件不存在
TASK_ATTACHMENT_NOT_FOUND  附件不属于该任务
TASK_ATTACHMENT_UPLOAD_DENIED  无权在该任务中上传附件
TASK_ATTACHMENT_ACCESS_DENIED  无权访问该任务的附件
TASK_ATTACHMENT_DELETE_DENIED  无权删除该任务附件
TASK_ATTACHMENT_DOWNLOAD_DENIED  无权下载该任务附件
PROJECT_ATTACHMENT_NOT_FOUND  附件不属于该项目
PROJECT_ATTACHMENT_UPLOAD_DENIED  无权在该项目中上传附件
PROJECT_ATTACHMENT_ACCESS_DENIED  无权访问该项目的附件
PROJECT_ATTACHMENT_DELETE_DENIED  无权删除该项目附件
PROJECT_ATTACHMENT_DOWNLOAD_DENIED  无权下载该项目附件
NOTIFICATION_NOT_FOUND  通知不存在
TEAM_ACTIVITY_ACCESS_DENIED  无权查看团队活动
PROJECT_ACTIVITY_ACCESS_DENIED  无权访问该项目的活动
PROJECT_ARCHIVED_ACTIVITY_ACCESS_DENIED  无权访问归档项目的活动
TASK_ACTIVITY_ACCESS_DENIED  无权访问该任务的活动
TASK_ARCHIVED_ACTIVITY_ACCESS_DENIED  无权访问归档任务的活动
PROJECT_DASHBOARD_ACCESS_DENIED  无权访问该项目的仪表盘
PROJECT_ARCHIVED_DASHBOARD_ACCESS_DENIED  无权访问归档项目的仪表盘
TEAM_DASHBOARD_ACCESS_DENIED  无权查看团队仪表盘
"""




class AppException(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class BadRequestError(AppException):
    def __init__(
        self,
        code: str = "BAD_REQUEST",
        message: str = "请求参数错误",
    ):
        super().__init__(
            code=code,
            message=message,
            status_code=400,
        )


class UnauthorizedError(AppException):
    def __init__(
        self,
        code: str = "UNAUTHORIZED",
        message: str = "未认证或认证失败",
    ):
        super().__init__(
            code=code,
            message=message,
            status_code=401,
        )


class PermissionDeniedError(AppException):
    def __init__(
        self,
        code: str = "PERMISSION_DENIED",
        message: str = "权限不足",
    ):
        super().__init__(
            code=code,
            message=message,
            status_code=403,
        )


class ResourceNotFoundError(AppException):
    def __init__(self, code: str, message: str):
        super().__init__(
            code=code,
            message=message,
            status_code=404,
        )


class ConflictError(AppException):
    def __init__(self, code: str, message: str):
        super().__init__(
            code=code,
            message=message,
            status_code=409,
        )
