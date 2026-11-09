"""Quality gate for memory x situation proposals."""

from __future__ import annotations

PASS_SCORE = 0.65
ALLOWED_ACTIONS = {"create_todo", "create_goal", "open", "link"}


def evaluate(candidate) -> tuple[bool, float, list[str]]:
    """Return ``(passed, score, reasons)`` for one mining candidate.

    Hard rejections are evidence problems, not scoring problems: a proposal
    without a verbatim memory quote or a real situation reference must never
    reach the user.
    """
    reasons: list[str] = []
    evidence = candidate.evidence or {}
    action = candidate.action or {}
    quote = str(evidence.get("quote") or "").strip()
    situation = candidate.situation_ref or {}

    if not candidate.memory_id:
        reasons.append("missing memory_id")
    if not situation:
        reasons.append("missing situation_ref")
    elif not (situation.get("id") or situation.get("due_at")):
        reasons.append("situation_ref has no usable reference")
    if not quote:
        reasons.append("missing evidence quote")
    if str(evidence.get("state") or "open") != "open":
        reasons.append("memory is not open")
    if str(evidence.get("sensitivity") or "") == "secret":
        reasons.append("secret memory cannot be proposed")
    if float(candidate.confidence or 0.0) < 0.5:
        reasons.append("low confidence")
    kind = str(action.get("kind") or "")
    if kind not in ALLOWED_ACTIONS:
        reasons.append(f"unsupported action: {kind or 'none'}")
    if reasons:
        return False, 0.0, reasons

    evidence_strength = 1.0 if len(quote) >= 8 else 0.4
    actionability = 1.0 if kind in ("create_todo", "create_goal") else 0.7
    novelty = 1.0 if evidence.get("novel", True) else 0.3
    unresolved = 1.0
    timing = 1.0 if (situation.get("id") or situation.get("due_at")) else 0.5
    confidence = min(1.0, max(0.0, float(candidate.confidence or 0.0)))

    score = (
        evidence_strength * 0.25
        + actionability * 0.25
        + novelty * 0.20
        + unresolved * 0.15
        + timing * 0.10
        + confidence * 0.05
    )
    if score < PASS_SCORE:
        reasons.append(f"score below threshold: {score:.2f}")
        return False, score, reasons
    return True, round(score, 4), []
