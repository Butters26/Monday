"""Common learning result contract for lobe-owned experiential updates."""

from __future__ import annotations

from typing import Any, Dict, Protocol


class ExperienceLearningLobe(Protocol):
    """Protocol for lobes that can interpret and update from a shared envelope."""

    supports_experience_learning: bool

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle learn_from_experience and normal processing messages."""


def normalize_learning_result(lobe: str, event_id: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize lobe response into the shared lifecycle stages."""
    response = raw if isinstance(raw, dict) else {"status": "error", "message": "non-dict response"}
    content = response.get("content", response)
    if not isinstance(content, dict):
        content = {}
    delivered = bool(content.get("delivered", response.get("status") != "error"))
    interpreted = bool(content.get("interpreted", response.get("status") == "success"))
    update_proposed = bool(content.get("update_proposed", interpreted))
    update_accepted = bool(content.get("update_accepted", response.get("status") == "success"))
    behavior_affected = bool(content.get("behavior_affected", False))
    validation_passed = bool(content.get("validation_passed", response.get("status") == "success"))
    return {
        "lobe": lobe,
        "event_id": event_id,
        "status": response.get("status", "error"),
        "delivered": delivered,
        "interpreted": interpreted,
        "update_proposed": update_proposed,
        "update_accepted": update_accepted,
        "behavior_affected": behavior_affected,
        "validation_passed": validation_passed,
        "confidence": content.get("confidence"),
        "evidence": content.get("evidence", []),
        "changes": content.get("changes", {}),
        "message": response.get("message", content.get("message")),
    }
