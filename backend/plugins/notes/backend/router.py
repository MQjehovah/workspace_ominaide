from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from core.database.session import get_db
from core.auth.dependencies import get_current_user
from plugins.notes.backend.schemas import NoteCreate, NoteUpdate, NoteResponse
from plugins.notes.backend import service as notes_service

router = APIRouter(tags=["notes-plugin"])


@router.post("", response_model=NoteResponse, status_code=201)
async def create_note(
    req: NoteCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    note = await notes_service.create_note(db, user["id"], req)
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
        await notes_service.delete_note(db, user["id"], note_id)
        return {"message": "Note deleted"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
