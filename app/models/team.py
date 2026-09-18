from datetime import datetime
from sqlalchemy import BigInteger, String, Text, DateTime, ForeignKey, Enum as SQLEnum, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, BaseTimeMixin
from enum import Enum



from app.models.user import User


# 团队状态枚举
class TeamStatus(str, Enum):
    active = "active"
    archived = "archived"

# 团队角色枚举
class TeamRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"

class Team(Base, BaseTimeMixin):
    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("name", name="uq_team_name"),  # 可选：团队名称全局唯一
        {"comment": "团队表"}
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="团队名称")
    description: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="团队描述")
    creator_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        comment="创建者用户ID"
    )
    status: Mapped[TeamStatus] = mapped_column(
        SQLEnum(TeamStatus, name="team_status"),
        nullable=False,
        default=TeamStatus.active,
        comment="团队状态"
    )

    # 关系
    creator: Mapped[User] = relationship("User", foreign_keys=[creator_id])
    members: Mapped[list["TeamMember"]] = relationship(
        "TeamMember", back_populates="team", cascade="all, delete-orphan"
    )
    projects: Mapped[list["Project"]] = relationship("Project", back_populates="team", cascade="all, delete-orphan")
    activities: Mapped[list["Activity"]] = relationship(
        back_populates="team",
        cascade="all, delete-orphan"
    )



class TeamMember(Base, BaseTimeMixin):
    __tablename__ = "team_members"
    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_team_member_team_user"),
        {"comment": "团队成员表"}
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    role: Mapped[TeamRole] = mapped_column(
        SQLEnum(TeamRole, name="team_role"),
        nullable=False,
        default=TeamRole.MEMBER,
        comment="成员角色"
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    @property
    def username(self) -> str:
        return self.user.username if self.user else ""

    @property
    def display_name(self) -> str | None:
        return self.user.display_name if self.user else None

    # 关系
    team: Mapped[Team] = relationship("Team", back_populates="members")
    user: Mapped[User] = relationship("User")