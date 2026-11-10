from datetime import datetime

from pydantic import BaseModel, Field


class GitProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=500)
    relative_path: str = Field(min_length=1, max_length=300)
    default_branch: str | None = "master"
    clone: bool = True


class GitProjectUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    relative_path: str | None = None
    default_branch: str | None = None


class GitProjectOut(BaseModel):
    id: int
    project_id: int
    name: str
    url: str
    relative_path: str
    default_branch: str | None = None
    status: str = "pending"
    error: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    path: str = ""
    description: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    path: str | None = None
    description: str | None = None
    status: str | None = None


class ProjectOut(BaseModel):
    id: int
    user_id: int
    name: str
    path: str
    description: str | None = None
    status: str
    git_projects: list[GitProjectOut] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ProjectRunOut(BaseModel):
    id: int
    session_id: str | None = None
    status: str
    input: str | None = None
    output: str | None = None
    error: str | None = None
    created_at: datetime | None = None
    finished_at: datetime | None = None
    branch: str | None = None
    engine: str | None = None
    project_path: str | None = None


class ProjectRunCreate(BaseModel):
    instruction: str = Field(min_length=1, max_length=20000)
    branch: str | None = None
    engine: str | None = None
    session_id: str | None = None
