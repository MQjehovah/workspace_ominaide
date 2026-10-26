from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pathlib import Path
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from core.database.session import get_db
from core.auth.dependencies import get_current_user
from core.events.recorder import record_event
from plugins.notes.backend.schemas import NoteCreate, NoteUpdate, NoteResponse
from plugins.notes.backend import service as notes_service
from plugins.notes.backend import rag as notes_rag
from plugins.notes.backend import importers

router = APIRouter(prefix="/api/plugins/notes", tags=["notes-plugin"])


class MoveNoteRequest(BaseModel):
    parent_id: int | None = None
    sort_order: int | None = None


class RagSearchRequest(BaseModel):
    q: str
    top_k: int | None = None


class RagAskRequest(BaseModel):
    question: str
    top_k: int | None = None


class RagReindexRequest(BaseModel):
    limit: int = 200


class ImportLibraryRequest(BaseModel):
    file_id: int
    parent_id: int | None = None
    title: str | None = None


class ImportUrlRequest(BaseModel):
    url: str
    parent_id: int | None = None
    title: str | None = None


@router.post("/import/file", response_model=NoteResponse, status_code=201)
async def import_file(
    file: UploadFile = File(...),
    parent_id: int | None = Form(None),
    title: str | None = Form(None),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import a PDF/Word/HTML/text/audio file as an indexed note."""
    data = await file.read()
    filename = file.filename or "imported"
    ctype = (file.content_type or "").lower()
    ext = Path(filename).suffix.lower()
    audio = ctype.startswith("audio/") or ctype.startswith("video/") or ext in {
        ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".webm", ".mp4",
    }
    try:
        if audio:
            text = await importers.transcribe_audio(filename, data, ctype)
            extracted_title = Path(filename).stem or "语音转写"
            text = f"## 语音转写\n\n{text}"
        else:
            extracted_title, text = importers.extract_document(filename, data)
    except importers.ImportFailed as e:
        raise HTTPException(400, detail=str(e))
    if not text.strip():
        raise HTTPException(400, detail="没有提取到文字")
    note = await notes_service.create_note(
        db, user["id"],
        NoteCreate(
            title=(title or extracted_title)[:200],
            content=text,
            parent_id=parent_id,
        ),
    )
    await record_event(db, user["id"], "note.imported", "note", note.id,
                       f"导入知识: {note.title}")
    return NoteResponse.model_validate(note)


@router.post("/import/library", response_model=NoteResponse, status_code=201)
async def import_library_file(
    req: ImportLibraryRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Extract an existing file-library item (PDF/Word/text/audio) into notes."""
    from core.minio.client import minio_client
    from plugins.files.backend import service as files_service

    if not minio_client:
        raise HTTPException(503, detail="MinIO unavailable")
    record = await files_service.get_file(db, user["id"], req.file_id)
    if not record:
        raise HTTPException(404, detail="File not found")
    filename = record.original_name or "imported"
    mime = (record.mime_type or "").lower()
    ext = Path(filename).suffix.lower()
    try:
        obj = minio_client.get_object(record.bucket, record.object_key)
        data = obj.read()
    except Exception as e:
        raise HTTPException(502, detail=f"读取文件失败: {e}")

    audio = mime.startswith("audio/") or mime.startswith("video/") or ext in {
        ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".webm", ".mp4",
    }
    try:
        if audio:
            text = await importers.transcribe_audio(filename, data, mime)
            extracted_title = Path(filename).stem or "语音转写"
            text = f"## 语音转写\n\n{text}"
        else:
            extracted_title, text = importers.extract_document(filename, data)
    except importers.ImportFailed as e:
        raise HTTPException(400, detail=str(e))
    if not text.strip():
        raise HTTPException(400, detail="没有提取到文字")

    note = await notes_service.create_note(
        db, user["id"],
        NoteCreate(
            title=(req.title or extracted_title)[:200],
            content=text,
            parent_id=req.parent_id,
        ),
    )
    await record_event(db, user["id"], "note.imported", "note", note.id,
                       f"文件库导入: {note.title}")
    return NoteResponse.model_validate(note)


@router.post("/import/url", response_model=NoteResponse, status_code=201)
async def import_url(
    req: ImportUrlRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch a web page (or PDF link) and save its text as an indexed note."""
    try:
        extracted_title, text = await importers.fetch_url(req.url.strip())
    except importers.ImportFailed as e:
        raise HTTPException(400, detail=str(e))
    except Exception as e:
        raise HTTPException(502, detail=f"网页抓取失败: {e}")
    if not text.strip():
        raise HTTPException(400, detail="网页没有可提取正文")
    note = await notes_service.create_note(
        db, user["id"],
        NoteCreate(
            title=(req.title or extracted_title)[:200],
            content=text,
            parent_id=req.parent_id,
        ),
    )
    await record_event(db, user["id"], "note.imported", "note", note.id,
                       f"网页导入: {note.title}")
    return NoteResponse.model_validate(note)


@router.get("/tree")
async def get_tree(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tree = await notes_service.get_tree(db, user["id"])
    return tree


@router.post("/{note_id}/move", response_model=NoteResponse)
async def move_note(
    note_id: int,
    req: MoveNoteRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        note = await notes_service.move_note(db, user["id"], note_id, req.parent_id, req.sort_order)
        return NoteResponse.model_validate(note)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("", response_model=NoteResponse, status_code=201)
async def create_note(
    req: NoteCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        note = await notes_service.create_note(db, user["id"], req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await record_event(db, user["id"], "note.created", "note", note.id, f"创建笔记: {note.title}")
    return NoteResponse.model_validate(note)


@router.get("", response_model=list[NoteResponse])
async def list_notes(
    parent_id: int | None = Query(None),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    notes = await notes_service.get_notes(db, user["id"], parent_id)
    return [NoteResponse.model_validate(n) for n in notes]


@router.get("/search", response_model=list[NoteResponse])
async def search_notes(
    q: str = Query(""),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    notes = await notes_service.search_notes(db, user["id"], q)
    return [NoteResponse.model_validate(n) for n in notes]


@router.post("/rag/search")
async def rag_search(
    req: RagSearchRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Hybrid semantic + keyword search over the note knowledge base."""
    await notes_rag.ensure_indexed(user["id"])
    results = await notes_rag.hybrid_search(
        db, user["id"], req.q, top_k=req.top_k
    )
    return {"query": req.q, "results": results}


@router.post("/rag/ask")
async def rag_ask(
    req: RagAskRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ask a question and get a cited answer grounded in the user's notes."""
    try:
        await notes_rag.ensure_indexed(user["id"])
        return await notes_rag.ask_notes(
            db, user["id"], req.question, top_k=req.top_k
        )
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/rag/reindex")
async def rag_reindex(
    req: RagReindexRequest,
    user: dict = Depends(get_current_user),
):
    """Backfill chunks/embeddings/terms for existing notes."""
    return await notes_rag.reindex_all(user["id"], limit=req.limit)


@router.get("/rag/status")
async def rag_status(
    user: dict = Depends(get_current_user),
):
    return await notes_rag.rag_status(user["id"])


@router.get("/{note_id}/similar")
async def similar_notes(
    note_id: int,
    limit: int = Query(5, ge=1, le=20),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    note = await notes_service.get_note(db, user["id"], note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"results": await notes_rag.similar_notes(
        db, user["id"], note_id, top_k=limit
    )}


@router.get("/{note_id}", response_model=NoteResponse)
async def get_note(
    note_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    note = await notes_service.get_note(db, user["id"], note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return NoteResponse.model_validate(note)


@router.put("/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: int,
    req: NoteUpdate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        note = await notes_service.update_note(db, user["id"], note_id, req)
        await record_event(db, user["id"], "note.updated", "note", note_id, f"修改笔记: {note.title}")
        return NoteResponse.model_validate(note)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{note_id}/versions")
async def get_note_versions(
    note_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        versions = await notes_service.list_versions(db, user["id"], note_id)
        return {"versions": versions}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{note_id}/versions/{version_id}")
async def get_note_version(
    note_id: int,
    version_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        v = await notes_service.get_version(db, user["id"], note_id, version_id)
        return v
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{note_id}/versions/{version_id}/restore")
async def restore_note_version(
    note_id: int,
    version_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        note = await notes_service.restore_version(db, user["id"], note_id, version_id)
        await record_event(db, user["id"], "note.restored", "note", note_id, f"恢复笔记版本: {note.title}")
        return NoteResponse.model_validate(note)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{note_id}")
async def delete_note(
    note_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        note = await notes_service.get_note(db, user["id"], note_id)
        title = note.title if note else "未知"
        await notes_service.delete_note(db, user["id"], note_id)
        await record_event(db, user["id"], "note.deleted", "note", note_id, f"删除笔记: {title}")
        return {"message": "Note deleted"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
