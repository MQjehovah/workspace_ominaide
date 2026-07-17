from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class FileResponse(BaseModel):
    id: int
    user_id: int
    workspace_id: int | None = None
    bucket: str
    object_key: str
    original_name: str
    is_folder: bool = False
    folder_path: str | None = "/"
    size: int
    mime_type: str | None = None
    tags: list[str] | None = None
    is_favorite: bool = False
    status: str = "active"
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FileListResponse(BaseModel):
    files: list[FileResponse]
    total: int
    page: int
    page_size: int


class CreateFolderRequest(BaseModel):
    name: str
    workspace_id: int | None = None
    parent_path: str = "/"


class UploadUrlRequest(BaseModel):
    filename: str
    mime_type: str | None = None
    workspace_id: int | None = None
    folder_path: str = "/"
    bucket: str | None = None


class RenameFileRequest(BaseModel):
    new_name: str


class MoveFileRequest(BaseModel):
    new_folder_path: str


class UploadUrlResponse(BaseModel):
    upload_url: str
    file_id: int
    object_key: str


class ConfirmUploadRequest(BaseModel):
    file_id: int


class UpdateTagsRequest(BaseModel):
    tags: list[str]


class FileQueryParams(BaseModel):
    page: int = 1
    page_size: int = 50
    status: str = "active"
    workspace_id: int | None = None
    bucket: str | None = None
    mime_type: str | None = None
    search: str | None = None
    favorite: bool | None = None
    folder_path: str | None = None
    is_folder: bool | None = None
