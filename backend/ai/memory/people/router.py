from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.auth.dependencies import get_current_user
from ai.memory.people import service

router = APIRouter(prefix="/api/people", tags=["people"])


class PersonUpdate(BaseModel):
    display_name: str | None = None
    company: str | None = None
    notes: str | None = None
    aliases: list[str] | None = None


class MergeRequest(BaseModel):
    primary_id: int
    duplicate_id: int


@router.get("")
async def list_people(user: dict = Depends(get_current_user)):
    return {"items": await service.list_people(user["id"])}


@router.get("/follow-ups")
async def follow_ups(user: dict = Depends(get_current_user)):
    return await service.follow_ups(user["id"])


@router.post("/backfill")
async def backfill(user: dict = Depends(get_current_user)):
    return await service.backfill_user(user["id"])


@router.get("/{person_id}")
async def get_person(person_id: int, user: dict = Depends(get_current_user)):
    person = await service.get_person(user["id"], person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    return {
        "id": person.id,
        "display_name": person.display_name,
        "emails": person.emails or [],
        "aliases": person.aliases or [],
        "company": person.company,
        "notes": person.notes,
    }


@router.patch("/{person_id}")
async def update_person(
    person_id: int, req: PersonUpdate, user: dict = Depends(get_current_user)
):
    person = await service.update_person(
        user["id"], person_id, req.model_dump(exclude_unset=True)
    )
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    return {"id": person.id, "display_name": person.display_name}


@router.get("/{person_id}/timeline")
async def person_timeline(
    person_id: int,
    limit: int = Query(100, ge=1, le=300),
    user: dict = Depends(get_current_user),
):
    person = await service.get_person(user["id"], person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    return {"items": await service.timeline(user["id"], person_id, limit)}


@router.get("/{person_id}/commitments")
async def person_commitments(
    person_id: int, user: dict = Depends(get_current_user)
):
    person = await service.get_person(user["id"], person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    return {"items": await service.commitments(user["id"], person_id)}


@router.post("/merge")
async def merge_people(req: MergeRequest, user: dict = Depends(get_current_user)):
    ok = await service.merge_people(user["id"], req.primary_id, req.duplicate_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Merge failed")
    return {"message": "Merged"}
