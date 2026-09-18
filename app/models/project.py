from datetime import datetime, date
from sqlalchemy import BigInteger, String, DateTime, ForeignKey, UniqueConstraint, Integer, Enum as SQLEnum, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, BaseTimeMixin
from enum import Enum






class ProjectStatus(str, Enum):
    planned = "planned"
    active = "active"
    completed = "completed"
    archived = "archived"

class Project(Base, BaseTimeMixin):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("team_id", "name", name="uq_project_team_name"),
        {"comment": "项目表"}
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属团队ID"
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="项目名称")
    description: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="项目描述")
    owner_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        comment="项目负责人用户ID"
    )
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="开始日期")
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="截止日期")
    status: Mapped[ProjectStatus] = mapped_column(
        SQLEnum(ProjectStatus, name="project_status"),
        nullable=False,
        default=ProjectStatus.planned,
        comment="项目状态"
    )
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="项目进度百分比 0-100")

    team: Mapped["Team"] = relationship("Team", back_populates="projects")
    owner: Mapped["User"] = relationship("User", foreign_keys=[owner_user_id])
    members: Mapped[list["ProjectMember"]] = relationship("ProjectMember", back_populates="project", cascade="all, delete-orphan")
    workflow: Mapped["Workflow"] = relationship(
        back_populates="project",
        uselist=False,  # 一对一，返回单个对象而非列表
        cascade="all, delete-orphan"  # 删除项目时级联删除工作流
    )
    tasks: Mapped[list["Task"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    activities: Mapped[list["Activity"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan"
    )


class ProjectRole(str, Enum):
    OWNER = "OWNER"      # 项目负责人（与 Project.owner_user_id 对应）
    MEMBER = "MEMBER"    # 普通项目成员
class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_member_project_user"),
        {"comment": "项目成员表"}
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    role: Mapped[ProjectRole] = mapped_column(
        SQLEnum(ProjectRole, name="project_role"),
        nullable=False,
        default=ProjectRole.MEMBER,
        comment="成员在项目中的角色"
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )

    @property
    def username(self) -> str:
        return self.user.username if self.user else ""

    @property
    def display_name(self) -> str | None:
        return self.user.display_name if self.user else None

    # 关系
    project: Mapped["Project"] = relationship("Project", back_populates="members")
    user: Mapped["User"] = relationship("User", back_populates="project_memberships")
