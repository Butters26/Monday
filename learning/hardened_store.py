"""Hardened per-lobe learning store for the copied learning branch."""
from __future__ import annotations

from typing import Any, Dict

from learning.lobe_learning_store import LobeLearningStore


_TRUSTED_VALIDATORS = {
    "thalamus:auto_behavior_verifier",
    "teach_monday_validation",
    "runtime_integration",
}


class HardenedLobeLearningStore(LobeLearningStore):
    """Keep the original store format while tightening unsafe transitions."""

    @staticmethod
    def _semantic_vector(text: str, dims: int = 256):
        # The old implementation hashed character trigrams/tokens and called the
        # result semantic similarity. That is lexical similarity, not semantic
        # meaning. Disable that fallback rather than returning misleading scores.
        return [0.0] * dims

    def recall(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        safe = dict(payload) if isinstance(payload, dict) else {}
        # Runtime behavior may only consume active learning. Callers that need
        # inspection of provisional records can explicitly set inspect_all=True.
        if not safe.pop("inspect_all", False):
            safe["include_only_active"] = True
        return super().recall(safe)

    @staticmethod
    def _trusted_validator(payload: Dict[str, Any]) -> bool:
        validator = payload.get("validator")
        if not isinstance(validator, str):
            return False
        return validator.strip() in _TRUSTED_VALIDATORS

    @classmethod
    def _runtime_validation_is_real(cls, payload: Dict[str, Any]) -> bool:
        if not cls._trusted_validator(payload):
            return False
        before_output = payload.get("before_output")
        after_output = payload.get("after_output")
        expected_difference = payload.get("expected_difference")
        observed_difference = payload.get("observed_difference")
        test_input = payload.get("test_input")
        if not all(isinstance(value, str) for value in (
            before_output,
            after_output,
            expected_difference,
            observed_difference,
            test_input,
        )):
            return False
        if not test_input.strip() or not expected_difference.strip():
            return False
        if before_output.strip() == after_output.strip():
            return False
        expected = expected_difference.strip().casefold()
        if expected not in after_output.casefold():
            return False
        if expected in before_output.casefold():
            return False
        return True

    def promote(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Evidence strings alone are not proof. Promotion requires a trusted
        # runtime verifier plus an observed before/after behavior change.
        if not self._runtime_validation_is_real(payload):
            return {
                "status": "error",
                "message": "Cannot promote without trusted runtime behavior validation",
                "content": {"status": "provisional", "action": "promotion_rejected"},
            }
        return super().promote(payload)

    def adjust(self, payload: Dict[str, Any], mode: str) -> Dict[str, Any]:
        if mode != "contradict":
            return super().adjust(payload, mode)

        # A contradiction must come from the runtime verifier or an explicitly
        # trusted correction path. Plain strings such as before:/after:/validated:
        # are no longer accepted as independent proof.
        if not self._trusted_validator(payload):
            return {
                "status": "error",
                "message": "Contradiction rejected: trusted validator required",
                "content": {"action": "contradiction_rejected"},
            }

        correction_fact = payload.get("correction_fact")
        before_fact = payload.get("before_fact", payload.get("previous_fact"))
        after_fact = payload.get("after_fact", payload.get("proposed_fact", correction_fact))
        validation_note = payload.get("validation_note", payload.get("validation_source"))
        if not all(isinstance(value, str) and value.strip() for value in (
            correction_fact,
            before_fact,
            after_fact,
            validation_note,
        )):
            return {
                "status": "error",
                "message": "Contradiction rejected: structured correction evidence required",
                "content": {"action": "contradiction_rejected"},
            }

        safe = dict(payload)
        safe["correction_evidence"] = [
            f"before:{before_fact.strip()}",
            f"after:{after_fact.strip()}",
            f"validated:{validation_note.strip()}",
        ]
        return super().adjust(safe, mode)
