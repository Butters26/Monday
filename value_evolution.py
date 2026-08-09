"""Adaptive value-state lobe for the single-process Monday launcher."""

from __future__ import annotations

from typing import Any, Dict

from thalamus import get_thalamus


class ValueEvolutionSystem:
    def __init__(self) -> None:
        self.running = True
        self.thalamus = get_thalamus()
        self.values: Dict[str, float] = {}

    def start(self) -> None:
        self.thalamus.register_lobe("value_evolution", self)

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        content = message.get("content", {})
        message_type = message.get("type")
        if message_type == "evolve_values":
            for name, delta in content.get("changes", {}).items():
                self.values[name] = self.values.get(name, 0.0) + float(delta)
            return {"status": "success", "values": dict(self.values)}
        if message_type == "get_values":
            return {"status": "success", "values": dict(self.values)}
        if message_type == "health":
            return {"status": "success", "healthy": True}
        return {"status": "error", "message": f"Unknown message type: {message_type}"}

    def shutdown(self) -> None:
        self.running = False
