from datetime import datetime
from sqlalchemy import BigInteger, String, DateTime, Enum as SQLEnum, ForeignKey, UniqueConstraint, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, BaseTimeMixin
from enum import Enum



class GlobalRoleEnum(str, Enum):
    SYSTEM_ADMIN = "system_admin"
    USER = "user"


# 用户表
class User(Base, BaseTimeMixin):
    __tablename__ = "users"
    __table_args__ = {"comment": "系统用户表"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="用户主键ID")
    username: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, comment="登录用户名")
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False, comment="bcrypt加密密码，不存明文")
    display_name: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="用户展示昵称")
    email: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, comment="用户邮箱，唯一")
    global_role: Mapped[GlobalRoleEnum] = mapped_column(SQLEnum(GlobalRoleEnum), nullable=False, comment="全局角色")
    is_active: Mapped[bool] = mapped_column(Boolean,nullable=False,default=True,comment="用户是否处于激活状态")
    @property
    def status(self) -> str:
        return "active" if self.is_active else "disabled"
    is_deleted: Mapped[bool] = mapped_column(Boolean,nullable=False,default=False,comment="是否已逻辑删除")

    # 一对多：用户登录令牌
    sessions: Mapped[list["UserSession"]] = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    created_teams: Mapped[list["Team"]] = relationship(
        "Team",
        foreign_keys="Team.creator_id",
        back_populates="creator"
    )
    team_memberships: Mapped[list["TeamMember"]] = relationship(
        "TeamMember",
        back_populates="user"
    )
    project_memberships: Mapped[list["ProjectMember"]] = relationship("ProjectMember", back_populates="user")
    created_tasks: Mapped[list["Task"]] = relationship(
        foreign_keys="Task.creator_id",
        back_populates="creator"
    )
    assigned_tasks: Mapped[list["Task"]] = relationship(
        foreign_keys="Task.assignee_user_id",
        back_populates="assignee"
    )
    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan"
    )

class UserSession(Base, BaseTimeMixin):
    __tablename__ = "user_sessions"
    __table_args__ = (UniqueConstraint("user_id", "device_id", name="uq_user_session_user_device"),{"comment": "用户会话记录表"})

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="Session ID")
    @property
    def session_id(self) -> int:
        return self.id
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="关联用户ID"
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(64), nullable=False,unique=True, comment="刷新令牌哈希值")
    device_id: Mapped[str] = mapped_column(String(128), nullable=False, comment="设备ID")
    device_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="设备名称")
    user_agent: Mapped[str] = mapped_column(String(512), nullable=False, comment="用户代理信息")
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False, comment="IP地址")
    expire_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True, comment="refresh_token过期时间，用于清理失效登录")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="令牌吊销时间")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="最后使用时间")

    # 多对一关联用户
    user: Mapped[User] = relationship("User", back_populates="sessions")