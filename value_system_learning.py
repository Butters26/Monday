"""Compatibility value-learning lobe used by the single-process launcher."""

from __future__ import annotations

from typing import Any, Dict

from thalamus import get_thalamus


class ValueSystemLearning:
    def __init__(self) -> None:
        self.running = True
        self.thalamus = get_thalamus()
        self.learned_values: Dict[str, float] = {}

    def start(self) -> None:
        self.thalamus.register_lobe("value_learning", self)

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        content = message.get("content", {})
        if message.get("type") == "learn_values":
            values = content.get("values", {})
            self.learned_values.update(values)
            return {"status": "success", "values": dict(self.learned_values)}
        if message.get("type") == "health":
            return {"status": "success", "healthy": True}
        return {"status": "error", "message": f"Unknown message type: {message.get('type')}"}

    def shutdown(self) -> None:
        self.running = False
