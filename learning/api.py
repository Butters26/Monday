"""Simple wrapper helpers for Monday's learning features."""

from __future__ import annotations

from typing import Any, Dict, Optional


def _as_content(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return payload.copy() if isinstance(payload, dict) else {}


def teach_monday(thalamus: Any, lesson: str, user_id: str = "default", **kwargs: Any) -> Dict[str, Any]:
    """Teach Monday once and let Thalamus route the lesson to relevant lobes."""
    if not isinstance(lesson, str) or not lesson.strip():
        return {"status": "error", "message": "lesson must be a non-empty string", "content": {}}
    payload = {"lesson": lesson, "user_id": user_id, **kwargs}
    return thalamus.handle_request({"type": "teach_monday", "content": payload})


def learning_overview(thalamus: Any, user_id: str = "default", limit: int = 5) -> Dict[str, Any]:
    """Return per-lobe learning skills and stats."""
    payload = {"user_id": user_id, "limit": limit}
    return thalamus.handle_request({"type": "learning_overview", "content": payload})


def teach_lobe_skill(
    thalamus: Any,
    lobe: str,
    skill: str,
    behavior: str,
    user_id: str = "default",
    **kwargs: Any,
) -> Dict[str, Any]:
    """Teach one explicit lobe skill when targeted training is needed."""
    if not isinstance(lobe, str) or not lobe.strip():
        return {"status": "error", "message": "lobe must be a non-empty string", "content": {}}
    payload = {"skill": skill, "behavior": behavior, "user_id": user_id, **kwargs}
    return thalamus.send_message(lobe.strip(), "teach_skill", _as_content(payload))


def list_lobe_skills(thalamus: Any, lobe: str, user_id: str = "default", limit: int = 20) -> Dict[str, Any]:
    """List skills remembered for one lobe."""
    if not isinstance(lobe, str) or not lobe.strip():
        return {"status": "error", "message": "lobe must be a non-empty string", "content": {}}
    payload = {"user_id": user_id, "limit": limit}
    return thalamus.send_message(lobe.strip(), "list_skills", payload)
