from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, ValidationError


class Trigger(BaseModel):
    type: Literal["schedule", "event", "manual"]
    cron: str | None = None
    event_type: str | None = None


class Condition(BaseModel):
    field: str
    op: Literal["eq", "neq", "contains", "gt", "lt", "exists"]
    value: str | int | float | bool | None = None


class Action(BaseModel):
    type: Literal["notify", "todo", "event", "note", "skill", "agent"]
    params: dict = Field(default_factory=dict)


class AutomationSpec(BaseModel):
    name: str
    enabled: bool = True
    trigger: Trigger
    conditions: list[Condition] = Field(default_factory=list)
    actions: list[Action]


def validate_spec(data: dict) -> dict:
    try:
        spec = AutomationSpec.model_validate(data)
    except ValidationError as exc:
        return {"valid": False, "errors": exc.errors()}
    errors: list[str] = []
    if spec.trigger.type == "schedule" and not spec.trigger.cron:
        errors.append("schedule trigger requires cron")
    if spec.trigger.type == "event" and not spec.trigger.event_type:
        errors.append("event trigger requires event_type")
    if not spec.actions:
        errors.append("at least one action is required")
    return {"valid": not errors, "errors": errors, "spec": spec.model_dump()}
