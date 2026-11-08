from fastapi import APIRouter, Depends, HTTPException, Query

from core.auth.dependencies import get_current_user
from core.insights import service

router = APIRouter(prefix="/api/insights", tags=["insights"])


@router.get("/suggestions")
async def suggestions(
    limit: int = Query(20, ge=1, le=50),
    user: dict = Depends(get_current_user),
):
    return {"items": await service.list_suggestions(user["id"], limit)}


@router.post("/suggestions/{suggestion_id}/accept")
async def accept(suggestion_id: int, user: dict = Depends(get_current_user)):
    if not await service.set_status(user["id"], suggestion_id, "accepted"):
        raise HTTPException(404, detail="Suggestion not found")
    return {"status": "accepted"}


@router.post("/suggestions/{suggestion_id}/dismiss")
async def dismiss(suggestion_id: int, user: dict = Depends(get_current_user)):
    if not await service.set_status(user["id"], suggestion_id, "dismissed"):
        raise HTTPException(404, detail="Suggestion not found")
    return {"status": "dismissed"}
