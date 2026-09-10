#!/usr/bin/env python3
"""Minimal thinking loop used by tests."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from thalamus import get_thalamus


class ThinkingLoop:
    def __init__(self, thalamus: Any = None):
        self.thalamus = thalamus or get_thalamus()
        self.running = True
        self.metrics: Dict[str, Any] = {
            "cycles": 0,
            "last_cycle_at": None,
        }
        self.executions: List[Dict[str, Any]] = []

    def _run_think_cycle(self) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        self.metrics["cycles"] += 1
        self.metrics["last_cycle_at"] = now
        record = {"timestamp": now, "status": "success"}
        self.executions.append(record)
        return {"status": "success", "execution": record}

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = message.get("type")
        if msg_type == "health":
            return {"status": "success", "healthy": True}
        if msg_type == "get_metrics":
            return {"status": "success", "metrics": dict(self.metrics)}
        if msg_type == "get_recent_executions":
            try:
                limit = int(message.get("limit", 10))
            except (TypeError, ValueError):
                limit = 10
            limit = max(1, min(limit, 100))
            return {"status": "success", "executions": list(self.executions[-limit:])}
        if msg_type == "run_cycle":
            return self._run_think_cycle()
        return {"status": "error", "message": f"Unknown message type: {msg_type}"}

    def shutdown(self):
        self.running = False
