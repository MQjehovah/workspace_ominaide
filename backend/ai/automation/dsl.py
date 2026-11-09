"""Unified automation specification: validation, compilation and conditions.

This is the definition format used by BotRoutine. Keeping one schema avoids a
second automation engine that duplicates cron/event scheduling.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

ActionType = Literal["notify", "todo", "event", "note", "skill", "agent"]


class Trigger(BaseModel):
    type: Literal["schedule", "event", "manual"]
    cron: str | None = None
    event_type: str | None = None
    timezone: str | None = None


class Condition(BaseModel):
    field: str
    op: Literal["eq", "neq", "contains", "gt", "lt", "exists"]
    value: str | int | float | bool | None = None


class Action(BaseModel):
    type: ActionType
    params: dict[str, Any] = Field(default_factory=dict)


class AutomationSpec(BaseModel):
    version: int = 1
    name: str
    description: str | None = None
    enabled: bool = True
    trigger: Trigger
    match: Literal["all", "any"] = "all"
    conditions: list[Condition] = Field(default_factory=list)
    actions: list[Action]


def _legacy_to_spec(data: dict) -> dict:
    trigger_type = str(data.get("trigger_type") or "cron").lower()
    if trigger_type in ("cron", "schedule"):
        trigger = {"type": "schedule", "cron": data.get("cron_expr")}
    elif trigger_type == "event":
        trigger = {"type": "event", "event_type": data.get("event_type")}
    else:
        trigger = {"type": "manual"}
    actions = []
    prompt = data.get("prompt") or data.get("name")
    if prompt:
        actions.append({"type": "agent", "params": {"prompt": prompt}})
    conditions = [
        {"field": f"event.details.{key}", "op": "eq", "value": value}
        for key, value in (data.get("event_filter") or {}).items()
    ]
    return {
        "version": 1,
        "name": data.get("name") or "自动化",
        "enabled": bool(data.get("enabled", True)),
        "trigger": trigger,
        "match": "all",
        "conditions": conditions,
        "actions": actions,
    }


def compile_spec(data: dict, *, legacy: dict | None = None) -> dict:
    """Normalize/validate an automation definition.

    Accepts either ``{"spec": {...}}`` or legacy BotRoutine fields. Returns a
    normalized spec or a list of errors, never raises for user input.
    """
    raw = dict(data or {})
    if isinstance(raw.get("spec"), dict):
        raw = dict(raw["spec"])
    elif "trigger" not in raw:
        raw = _legacy_to_spec({**raw, **(legacy or {})})

    if not raw.get("actions") and raw.get("prompt"):
        raw["actions"] = [{"type": "agent", "params": {"prompt": raw["prompt"]}}]

    errors: list[str] = []
    warnings: list[str] = []
    try:
        spec = AutomationSpec.model_validate(raw)
    except ValidationError as exc:
        return {"valid": False, "errors": exc.errors(), "warnings": warnings, "spec": None}

    if spec.trigger.type == "schedule":
        if not spec.trigger.cron:
            errors.append("schedule trigger requires cron")
        else:
            try:
                from ai.bots.routines import parse_cron

                parse_cron(spec.trigger.cron)
            except Exception as exc:
                errors.append(f"invalid cron: {exc}")
    if spec.trigger.type == "event" and not spec.trigger.event_type:
        errors.append("event trigger requires event_type")
    if not spec.actions:
        errors.append("at least one action is required")
    for action in spec.actions:
        if action.type == "agent":
            prompt = str(action.params.get("prompt") or "").strip()
            if not prompt:
                errors.append("agent action requires params.prompt")
        if action.type == "skill":
            skill_key = str(action.params.get("skill_key") or "").strip()
            if not skill_key:
                errors.append("skill action requires params.skill_key")
        if not isinstance(action.params, dict):
            errors.append(f"action {action.type} params must be an object")

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "spec": spec.model_dump(),
    }


def spec_from_routine(routine) -> dict:
    """Return a normalized spec for a BotRoutine, including legacy rows."""
    stored = getattr(routine, "spec", None)
    if isinstance(stored, dict) and stored:
        result = compile_spec(stored)
        if result.get("spec"):
            return result["spec"]
    legacy = {
        "name": routine.name,
        "trigger_type": routine.trigger_type,
        "cron_expr": routine.cron_expr,
        "event_type": routine.event_type,
        "prompt": routine.prompt,
        "event_filter": routine.event_filter,
        "enabled": routine.enabled,
    }
    result = compile_spec({}, legacy=legacy)
    return result.get("spec") or _legacy_to_spec(legacy)


def spec_legacy_fields(spec: dict) -> dict:
    """Derive the old BotRoutine columns from a spec for backward compatibility."""
    trigger = spec.get("trigger") or {}
    trigger_type = "cron" if trigger.get("type") == "schedule" else trigger.get("type", "manual")
    prompt = next(
        (
            str(a.get("params", {}).get("prompt"))
            for a in spec.get("actions", [])
            if a.get("type") == "agent" and a.get("params", {}).get("prompt")
        ),
        None,
    )
    return {
        "trigger_type": trigger_type,
        "cron_expr": trigger.get("cron") if trigger_type == "cron" else None,
        "event_type": trigger.get("event_type") if trigger_type == "event" else None,
        "prompt": prompt,
    }


def _get_path(context: dict, path: str):
    current: Any = context
    for part in (path or "").split("."):
        if not part:
            continue
        if isinstance(current, dict):
            if part not in current:
                return _MISSING
            current = current[part]
        else:
            return _MISSING
    return current


class _Missing:
    pass


_MISSING = _Missing()


def _compare(actual, op: str, expected) -> bool:
    if op == "exists":
        return actual is not _MISSING and actual is not None
    if actual is _MISSING:
        return False
    if op == "eq":
        return actual == expected
    if op == "neq":
        return actual != expected
    if op == "contains":
        if isinstance(actual, (list, tuple, set, dict)):
            return expected in actual
        return str(expected) in str(actual)
    try:
        left = float(actual)
        right = float(expected)
    except (TypeError, ValueError):
        return False
    return left > right if op == "gt" else left < right


def evaluate_conditions(spec: dict, context: dict) -> tuple[bool, list[dict]]:
    """Evaluate spec conditions against a trigger context."""
    conditions = spec.get("conditions") or []
    if not conditions:
        return True, []
    results = []
    for cond in conditions:
        actual = _get_path(context, str(cond.get("field") or ""))
        ok = _compare(actual, str(cond.get("op") or "eq"), cond.get("value"))
        results.append({
            "field": cond.get("field"),
            "op": cond.get("op"),
            "expected": cond.get("value"),
            "actual": None if actual is _MISSING else actual,
            "matched": ok,
        })
    if spec.get("match") == "any":
        return any(item["matched"] for item in results), results
    return all(item["matched"] for item in results), results
