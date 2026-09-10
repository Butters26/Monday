#!/usr/bin/env python3
"""Basic value/goal management lobe."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from thalamus import get_thalamus


class ValueGoalManagementLobe:
    def __init__(self, thalamus: Any = None):
        self.thalamus = thalamus or get_thalamus()
        self.values: Dict[str, float] = {}
        self.goals: List[str] = []
        self.running = True

    def update_values(self, updates: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
        if isinstance(updates, dict):
            for key, value in updates.items():
                if not isinstance(key, str) or not key.strip():
                    continue
                try:
                    self.values[key.strip()] = float(value)
                except (TypeError, ValueError):
                    continue
        return dict(self.values)

    def add_goal(self, goal: str) -> List[str]:
        if isinstance(goal, str) and goal.strip() and goal not in self.goals:
            self.goals.append(goal.strip())
        return list(self.goals)

    def prioritize_goals(self) -> List[str]:
        return list(self.goals)

    def route_goals(self) -> Dict[str, Any]:
        return {"status": "success", "content": {"goals": list(self.goals), "values": dict(self.values)}}

    def reset(self) -> Dict[str, Any]:
        self.values.clear()
        self.goals.clear()
        return {"status": "success"}

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = message.get("type")
        payload = message.get("content", message)
        if msg_type == "health":
            return {"status": "success", "healthy": True}
        if msg_type == "update_values":
            return {"status": "success", "content": {"values": self.update_values(payload.get("values", {}))}}
        if msg_type == "add_goal":
            return {"status": "success", "content": {"goals": self.add_goal(payload.get("goal", ""))}}
        if msg_type == "prioritize_goals":
            return {"status": "success", "content": {"goals": self.prioritize_goals()}}
        if msg_type == "route_goals":
            return self.route_goals()
        if msg_type == "reset":
            return self.reset()
        return {"status": "error", "message": f"Unknown message type: {msg_type}"}

    def shutdown(self):
        self.running = False
