"""Value-aligned goal management for the in-process Thalamus pipeline."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class ValueGoalManagementLobe:
    """Maintain explicit values and prioritize goals against them."""

    def __init__(self, thalamus: Optional[Any] = None) -> None:
        self.thalamus = thalamus
        self.values: Dict[str, float] = {}
        self.goals: List[str] = []

    def update_values(self, values: Dict[str, float]) -> None:
        for name, weight in values.items():
            if not isinstance(weight, (int, float)):
                raise ValueError(f"Value weight for '{name}' must be numeric")
            self.values[name] = float(weight)

    def add_goal(self, goal: str) -> None:
        if not isinstance(goal, str) or not goal.strip():
            raise ValueError("Goal must be a non-empty string")
        if goal not in self.goals:
            self.goals.append(goal)

    def prioritize_goals(self) -> List[str]:
        return list(self.goals)

    def route_goals(self) -> Dict[str, Any]:
        if self.thalamus is None:
            return {"status": "success", "routed": False, "goals": self.prioritize_goals()}
        return self.thalamus.send_message(
            "executive_control",
            "set_goals",
            {"goals": self.prioritize_goals(), "values": dict(self.values)},
            source="value_goal_management",
        )

    def reset(self) -> None:
        self.values.clear()
        self.goals.clear()

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        content = message.get("content", {})
        message_type = message.get("type")
        if message_type == "evaluate_input":
            return {
                "status": "success",
                "values": dict(self.values),
                "active_goals": self.prioritize_goals(),
            }
        if message_type == "update_values":
            self.update_values(content.get("values", {}))
            return {"status": "success", "values": dict(self.values)}
        if message_type == "add_goal":
            self.add_goal(content.get("goal", ""))
            return {"status": "success", "goals": self.prioritize_goals()}
        if message_type == "prioritize_goals":
            return {"status": "success", "goals": self.prioritize_goals()}
        if message_type == "route_goals":
            return self.route_goals()
        if message_type == "reset":
            self.reset()
            return {"status": "success"}
        if message_type == "health":
            return {"status": "success", "healthy": True}
        return {"status": "error", "message": f"Unknown message type: {message_type}"}
