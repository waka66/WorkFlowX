from enum import Enum
from datetime import datetime
from sqlalchemy import BigInteger, String, Text, DateTime, ForeignKey, Enum as SQLEnum, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, BaseTimeMixin



# 通知类型枚举
class NotificationType(str, Enum):
    task_assigned = "task_assigned"
    task_status_changed = "task_status_changed"
    comment = "comment"
    task_due = "task_due"
    project_invitation = "project_invitation"
    team_invitation = "team_invitation"
    review_result = "review_result"
    system = "system"

class Notification(Base, BaseTimeMixin):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_id", "user_id"),
        Index("ix_notifications_read_at", "read_at"),
        {"comment": "用户通知表"}
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="接收通知的用户ID"
    )
    type: Mapped[NotificationType] = mapped_column(
        SQLEnum(NotificationType,
        name="notification_type"),
        nullable=False,
        comment="通知类型"
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_entity_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    related_entity_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="阅读时间，未读为NULL")

    # 关系（可选，用于后续方便）
    user: Mapped["User"] = relationship(back_populates="notifications")

class Activity(Base, BaseTimeMixin):
    __tablename__ = "activities"
    __table_args__ = (
        Index("ix_activities_team_id", "team_id"),
        Index("ix_activities_actor_user_id", "actor_user_id"),
        {"comment": "团队活动记录表"}
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    team_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=True,
        comment="所属团队ID，可为空表示全局活动"
    )
    project_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        comment="关联项目ID"
    )
    task_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=True,
        comment="关联任务ID"
    )
    actor_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="操作者用户ID"
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, comment="动作标识，如 create_task, update_team")
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="目标类型")
    target_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="目标ID")
    content: Mapped[str] = mapped_column(String(1000), nullable=False, comment="活动描述内容")

    # 关系（可选，便于查询用户/团队等）
    actor: Mapped["User"] = relationship("User", foreign_keys=[actor_user_id])
    team: Mapped["Team"] = relationship("Team", back_populates="activities")
    project: Mapped["Project"] = relationship("Project", back_populates="activities")
    task: Mapped["Task"] = relationship("Task", back_populates="activities")

class AuditLog(Base, BaseTimeMixin):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_user_id", "user_id"),
        Index("ix_audit_logs_action", "action"),
        Index("ix_audit_logs_created_at", "created_at"),
        {"comment": "系统审计日志表"}
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="操作用户ID"
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, comment="操作标识，如 user.login, team.create")
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="目标类型")
    target_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="目标ID")
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True, comment="IP地址")
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="用户代理")

    # 关系（可选）
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])