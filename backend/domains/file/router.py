from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from core.database.session import get_db
from core.auth.dependencies import get_current_user
from domains.file.schemas import (
    UploadUrlRequest, UploadUrlResponse, ConfirmUploadRequest,
    UpdateTagsRequest, FileQueryParams, FileResponse, FileListResponse,
)
from domains.file import service as file_service

router = APIRouter(prefix="/api/v1/files", tags=["files"])


@router.post("/upload-url", response_model=UploadUrlResponse)
async def get_upload_url(
    req: UploadUrlRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    upload_url, file_id, object_key = await file_service.generate_upload_url(
        db, user["id"], req
    )
    return UploadUrlResponse(upload_url=upload_url, file_id=file_id, object_key=object_key)


@router.post("/confirm", response_model=FileResponse)
async def confirm_upload(
    req: ConfirmUploadRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        file_record = await file_service.confirm_upload(db, user["id"], req.file_id)
        return FileResponse.model_validate(file_record)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("", response_model=FileListResponse)
async def list_files(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status: str = Query("active"),
    workspace_id: int | None = None,
    bucket: str | None = None,
    mime_type: str | None = None,
    favorite: bool | None = None,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    params = FileQueryParams(
        page=page, page_size=page_size, status=status,
        workspace_id=workspace_id, bucket=bucket,
        mime_type=mime_type, favorite=favorite,
    )
    files, total = await file_service.get_files(db, user["id"], params)
    return FileListResponse(
        files=[FileResponse.model_validate(f) for f in files],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{file_id}", response_model=FileResponse)
async def get_file(
    file_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    file_record = await file_service.get_file(db, user["id"], file_id)
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse.model_validate(file_record)


@router.get("/{file_id}/download-url")
async def get_download_url(
    file_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    file_record = await file_service.get_file(db, user["id"], file_id)
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    url = await file_service.get_download_url(file_record)
    return {"download_url": url, "filename": file_record.original_name}


@router.put("/{file_id}/tags", response_model=FileResponse)
async def update_tags(
    file_id: int,
    req: UpdateTagsRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        file_record = await file_service.update_tags(db, user["id"], file_id, req.tags)
        return FileResponse.model_validate(file_record)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{file_id}/favorite", response_model=FileResponse)
async def toggle_favorite(
    file_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        file_record = await file_service.toggle_favorite(db, user["id"], file_id)
        return FileResponse.model_validate(file_record)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{file_id}")
async def trash_file(
    file_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await file_service.trash_file(db, user["id"], file_id)
        return {"message": "File moved to trash"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{file_id}/restore", response_model=FileResponse)
async def restore_file(
    file_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        file_record = await file_service.restore_file(db, user["id"], file_id)
        return FileResponse.model_validate(file_record)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{file_id}/permanent")
async def permanent_delete(
    file_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await file_service.permanent_delete(db, user["id"], file_id)
        return {"message": "File permanently deleted"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
