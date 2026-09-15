"""Minimal runtime integration for native lobe-owned learning.

Runtime integration now only coordinates cross-lobe flow.  Lesson relevance and
learned-behavior application live inside the lobe classes themselves.
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

        # Pattern is a normal cognitive predecessor of Reasoning.  This is
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

        return original_send_message(destination, msg_type, payload, source)

    thalamus.send_message = MethodType(send_message, thalamus)
