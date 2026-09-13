"""Hardened per-lobe learning store for the copied learning branch."""
from __future__ import annotations

from typing import Any, Dict

from learning.lobe_learning_store import LobeLearningStore


class HardenedLobeLearningStore(LobeLearningStore):
    """Keep the original store format while tightening unsafe activation."""

    @staticmethod
    def _semantic_vector(text: str, dims: int = 256):
        # The previous vector was lexical hashing, not semantic meaning. Runtime
        # relevance still has exact/token matching, so do not fake semantic scores.
        return [0.0] * dims

    @staticmethod
    def _runtime_validation_is_real(payload: Dict[str, Any]) -> bool:
        validator = payload.get("validator")
        before_output = payload.get("before_output")
        after_output = payload.get("after_output")
        if not isinstance(validator, str) or not validator.strip():
            return False
        if not isinstance(before_output, str) or not isinstance(after_output, str):
            return False
        if before_output.strip() == after_output.strip():
            return False
        expected = payload.get("expected_difference")
        if isinstance(expected, str) and expected.strip():
            expected_text = expected.strip().casefold()
            if expected_text not in after_output.casefold():
                return False
            if expected_text in before_output.casefold():
                return False
        return True

    def promote(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Promotion must prove an observed behavior delta. Explicit/manual recall
        # remains able to inspect proposed records; runtime guidance itself is
        # already gated by Thalamus to active records.
        if not self._runtime_validation_is_real(payload):
            return {
                "status": "error",
                "message": "Cannot promote without an observed runtime behavior change",
                "content": {"status": "provisional", "action": "promotion_rejected"},
            }
        return super().promote(payload)

    def adjust(self, payload: Dict[str, Any], mode: str) -> Dict[str, Any]:
        # Preserve explicit user/manual correction semantics. The base store
        # verifies that before matches the current fact and after matches the
        # proposed correction; automatic adaptation remains disabled by default.
        return super().adjust(payload, mode)
