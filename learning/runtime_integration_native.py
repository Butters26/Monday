"""Minimal runtime integration for native lobe-owned learning.

Runtime integration only coordinates cross-lobe flow. Lesson relevance,
activation policy, and learned-behavior application live inside the lobe
classes themselves.
"""

from __future__ import annotations

from types import MethodType
from typing import Any, Dict

from learning.contract_router import install_contract_router


def install_learning_integration(systems: Dict[str, Any]) -> None:
    thalamus = systems["thalamus"]
    install_contract_router(thalamus)
    thalamus._latest_pattern_by_user = {}
    original_send_message = thalamus.send_message

    def send_message(
        self: Any,
        destination: str,
        msg_type: str,
        content=None,
        source: str = "thalamus",
    ):
        payload = dict(content) if isinstance(content, dict) else content

        # Pattern is a normal cognitive predecessor of Reasoning. This is
        # pipeline coordination, not learning application.
        if destination == "reasoning" and msg_type == "think" and isinstance(payload, dict):
            user_id = self._normalised_user_id(payload)
            nested = payload.get("input")
            nested = dict(nested) if isinstance(nested, dict) else {}
            user_input = nested.get("user_input", payload.get("user_input", ""))
            pattern = original_send_message(
                "pattern",
                "process_input",
                {
                    "user_id": user_id,
                    "data": {
                        "user_input": user_input,
                        "understanding": nested.get("understanding", {}),
                        "memory_context": nested.get("memory_context", {}),
                        "emotion_result": nested.get("emotion_result", {}),
                    },
                },
                "thalamus:prompted_path",
            )
            if isinstance(pattern, dict) and pattern.get("status") == "success":
                pattern_content = self._content(pattern)
                self._latest_pattern_by_user[user_id] = pattern_content
                payload["pattern_result"] = pattern_content
                nested["pattern_result"] = pattern_content
                payload["input"] = nested

        result = original_send_message(destination, msg_type, payload, source)

        # A lobe may choose to stage a directly saved rule for runtime
        # validation. The lobe owns the decision and touches only its own store.
        if (
            msg_type == "learn"
            and isinstance(payload, dict)
            and isinstance(result, dict)
            and result.get("status") == "success"
        ):
            lobe = systems.get(destination)
            hook = getattr(lobe, "on_learning_saved", None)
            if callable(hook):
                try:
                    result = hook(payload, result)
                except Exception as exc:
                    result["staged_for_validation"] = False
                    result["staging_error"] = str(exc)

        return result

    thalamus.send_message = MethodType(send_message, thalamus)
