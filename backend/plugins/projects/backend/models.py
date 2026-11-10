from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    func,
)

from core.database.base import Base


class Project(Base):
    """A workspace folder. It has no git semantics of its own."""

    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("user_id", "path", name="uq_projects_user_path"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    path = Column(String(500), nullable=False, index=True)
    description = Column(Text, nullable=True)
    status = Column(String(20), default="active", index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Project id={self.id} name={self.name}>"


class GitProject(Base):
    """An independent git repository inside a project workspace."""

    __tablename__ = "git_projects"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "relative_path", name="uq_git_projects_project_path"
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(
        Integer, ForeignKey("projects.id"), nullable=False, index=True
    )
    name = Column(String(120), nullable=False)
    url = Column(String(500), nullable=False)
    relative_path = Column(String(300), nullable=False)
    default_branch = Column(String(120), default="master")
    status = Column(String(20), default="pending", index=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return (
            f"<GitProject id={self.id} project_id={self.project_id} "
            f"path={self.relative_path}>"
        )
