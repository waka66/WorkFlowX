from datetime import datetime, date
from sqlalchemy import (BigInteger, String, Integer, Boolean, DateTime,
                        ForeignKey, UniqueConstraint, JSON, Text, Date,Enum as SQLEnum, Index)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, BaseTimeMixin
from enum import Enum




class Priority(str, Enum):
    P0 = "P0"   # 最高优先级
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"   # 最低优先级

# ---------------- Workflow 相关模型 ----------------
class Workflow(Base, BaseTimeMixin):
    __tablename__ = "workflows"
    __table_args__ = {"comment": "项目工作流定义"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,          # 一个项目只有一个工作流
        comment="所属项目ID"
    )

    # 关系
    statuses: Mapped[list["WorkflowStatus"]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan"
    )
    transitions: Mapped[list["WorkflowTransition"]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan"
    )

    project: Mapped["Project"] = relationship(back_populates="workflow")


class WorkflowStatus(Base):
    __tablename__ = "workflow_statuses"
    __table_args__ = (
        UniqueConstraint("workflow_id", "key", name="uq_workflow_status_key"),
        {"comment": "工作流状态定义"}
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属工作流ID"
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False, comment="状态标识，如 todo、doing、done")
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="状态显示名称")
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="显示顺序")
    color: Mapped[str | None] = mapped_column(String(16), nullable=True, comment="颜色标识")
    is_initial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否为初始状态")
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否为终态")

    @property
    def project_id(self) -> int:
        return self.workflow.project_id if self.workflow else None

    # 关系
    workflow: Mapped["Workflow"] = relationship(back_populates="statuses")


class WorkflowTransition(Base):
    __tablename__ = "workflow_transitions"
    __table_args__ = (
        UniqueConstraint("workflow_id", "from_status_key", "to_status_key", name="uq_workflow_transition"),
        {"comment": "工作流状态转换规则"}
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属工作流ID"
    )
    from_status_key: Mapped[str] = mapped_column(String(64), nullable=False, comment="源状态 key")
    to_status_key: Mapped[str] = mapped_column(String(64), nullable=False, comment="目标状态 key")
    allowed_roles: Mapped[list] = mapped_column(JSON, nullable=False, default=list, comment="允许执行该转换的角色列表，如 ['OWNER','MEMBER']")

    @property
    def project_id(self) -> int:
        return self.workflow.project_id if self.workflow else None

    # 关系
    workflow: Mapped["Workflow"] = relationship(back_populates="transitions")


# ---------------- Task 模型（与 Workflow 关联） ----------------
class Task(Base, BaseTimeMixin):
    __tablename__ = "tasks"
    __table_args__ = {"comment": "项目任务"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属项目ID"
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    creator_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    assignee_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    status_key: Mapped[str] = mapped_column(String(64), nullable=False, comment="当前状态 key，需在项目工作流中存在")
    priority: Mapped[Priority] = mapped_column(
        SQLEnum(Priority, name="task_priority"),
        nullable=False,
        default=Priority.P2,
        comment="任务优先级"
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="截止日期")
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list, comment="标签列表")

    comments: Mapped[list["Comment"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="Comment.created_at"
    )
    # 所属项目（多对一）
    project: Mapped["Project"] = relationship(back_populates="tasks")

    # 创建者（多对一）
    creator: Mapped["User"] = relationship(foreign_keys=[creator_id], back_populates="created_tasks")

    # 负责人（多对一，可空）
    assignee: Mapped["User | None"] = relationship(foreign_keys=[assignee_user_id], back_populates="assigned_tasks")
    activities: Mapped[list["Activity"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan"
    )


# 新增 Comment 模型
class Comment(Base, BaseTimeMixin):
    __tablename__ = "comments"
    __table_args__ = (
        Index("ix_comments_task_id", "task_id"),
        Index("ix_comments_parent_id", "parent_id"),
        {"comment": "任务评论表"}
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属任务ID"
    )
    user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="评论用户ID"
    )
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("comments.id", ondelete="CASCADE"),
        nullable=True,
        comment="父评论ID，支持嵌套"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="评论内容")

    # 关系
    task: Mapped["Task"] = relationship(back_populates="comments")
    user: Mapped["User"] = relationship()  # 可选，便于获取用户名

# 新增 Attachment 模型（多态，无外键）
class Attachment(Base, BaseTimeMixin):
    __tablename__ = "attachments"
    __table_args__ = (
        Index("ix_attachments_target", "target_type", "target_id"),
        {"comment": "附件表，支持项目或任务附件"}
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="目标类型: project 或 task")
    target_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="目标ID")
    uploader_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        comment="上传者用户ID"
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    download_url: Mapped[str] = mapped_column(Text, nullable=False)

    uploader: Mapped["User"] = relationship()