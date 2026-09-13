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
        if not self._runtime_validation_is_real(payload):
            return {
                "status": "error",
                "message": "Cannot promote without an observed runtime behavior change",
                "content": {"status": "provisional", "action": "promotion_rejected"},
            }
        return super().promote(payload)

    def adjust(self, payload: Dict[str, Any], mode: str) -> Dict[str, Any]:
        if mode != "contradict":
            return super().adjust(payload, mode)

        correction_fact = payload.get("correction_fact")
        # Auto-adaptation failures are evidence that the previous behavior rule
        # failed, not proof that its text should be replaced by a recovery rule.
        # Preserve the original behavior record for audit/retrieval, increment
        # its contradiction count, and let the separate recovery record carry
        # the new fallback behavior.
        if isinstance(correction_fact, str) and "avoid failing behavior and prefer safe recovery" in correction_fact:
            user_id = self._clean_text(payload.get("user_id")) or "default"
            key = self._normalise_key(payload.get("key"), self._clean_text(payload.get("fact", "")))
            now = self._now()
            with self._lock:
                data = self._load()
                facts = self._user_facts(data, user_id)
                record = facts.get(key)
                if not isinstance(record, dict):
                    return {"status": "error", "message": f"No learned fact for key: {key}"}
                updated = dict(record)
                updated["contradiction_count"] = int(updated.get("contradiction_count", 0)) + 1
                updated["status"] = "disputed"
                updated["updated_at"] = now
                facts[key] = updated
                self._save(data)
            return {
                "status": "success",
                "content": {
                    "lobe": self.lobe_name,
                    "user_id": user_id,
                    "key": key,
                    "confidence": self._clamp_confidence(updated.get("confidence"), 0.0),
                    "evidence_count": int(updated.get("evidence_count", 0)),
                    "contradiction_count": int(updated.get("contradiction_count", 0)),
                    "status": updated.get("status"),
                    "action": "contradicted_preserved",
                },
            }

        return super().adjust(payload, mode)
