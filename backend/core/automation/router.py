from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.auth.dependencies import get_current_user
from core.automation.dsl import validate_spec

router = APIRouter(prefix="/api/automations", tags=["automations"])


class ValidateRequest(BaseModel):
    spec: dict


@router.post("/validate")
async def validate_automation(
    req: ValidateRequest,
    user: dict = Depends(get_current_user),
):
    return validate_spec(req.spec)
