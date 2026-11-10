from datetime import datetime

from pydantic import BaseModel, Field


class ProjectRepoCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=500)
    path: str | None = None
    default_branch: str | None = "master"


class ProjectRepoOut(BaseModel):
    id: int
    project_id: int
    name: str
    url: str
    path: str
    default_branch: str | None = None
    status: str = "pending"
    error: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    path: str = ""
    is_git: bool = True
    repo_url: str | None = None
    default_branch: str | None = "master"
    repos: list[ProjectRepoCreate] = Field(default_factory=list)
    clone: bool = True
    description: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    path: str | None = None
    is_git: bool | None = None
    repo_url: str | None = None
    default_branch: str | None = None
    description: str | None = None
    status: str | None = None


class ProjectOut(BaseModel):
    id: int
    user_id: int
    name: str
    path: str
    is_git: bool = True
    repo_url: str | None = None
    default_branch: str | None = None
    description: str | None = None
    status: str
    repos: list[ProjectRepoOut] = Field(default_factory=list)
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
