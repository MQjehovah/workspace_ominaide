from sqlalchemy import (
    Boolean,
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
    """A code project managed by the user (not a coding runtime)."""

    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("user_id", "path", name="uq_projects_user_path"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    path = Column(String(500), nullable=False, index=True)
    is_git = Column(Boolean, default=True, nullable=False)
    repo_url = Column(String(500), nullable=True)
    default_branch = Column(String(120), nullable=True)
    description = Column(Text, nullable=True)
    status = Column(String(20), default="active", index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Project id={self.id} name={self.name}>"


class ProjectRepo(Base):
    """A git repository inside a project workspace.

    A project is a folder. It may contain one repository at the root or several
    independent repositories in subdirectories.
    """

    __tablename__ = "project_repos"
    __table_args__ = (
        UniqueConstraint("project_id", "path", name="uq_project_repos_project_path"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(
        Integer, ForeignKey("projects.id"), nullable=False, index=True
    )
    name = Column(String(120), nullable=False)
    url = Column(String(500), nullable=False)
    path = Column(String(300), nullable=False)
    default_branch = Column(String(120), default="master")
    status = Column(String(20), default="pending", index=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<ProjectRepo id={self.id} project_id={self.project_id} path={self.path}>"
