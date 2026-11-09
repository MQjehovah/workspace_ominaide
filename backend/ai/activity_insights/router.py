from fastapi import APIRouter, Depends, HTTPException, Query

from core.auth.dependencies import get_current_user
from ai.activity_insights import service

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


@router.post("/suggestions/{suggestion_id}/execute")
async def execute(suggestion_id: int, user: dict = Depends(get_current_user)):
    result = await service.execute_suggestion(user["id"], suggestion_id)
    if result is None:
        raise HTTPException(404, detail="Suggestion not found")
    if result.get("status") == "no_action":
        raise HTTPException(400, detail="Suggestion has no executable action")
    return result
