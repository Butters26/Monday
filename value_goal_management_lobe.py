"""
ValueGoalManagementLobe: Manages values and goals for the AI brain architecture.
Handles storing/updating values, adding/prioritizing goals, and routing them
to other lobes via the Thalamus.
"""

from typing import Any, Dict, List, Optional
from thalamus import get_thalamus


class ValueGoalManagementLobe:
    """
    Maintains a set of named values (with numeric strengths) and an ordered
    list of goals. Provides methods that mirror the test expectations:
    update_values, add_goal, prioritize_goals, route_goals, and reset.
    """

    def __init__(self, thalamus=None):
        self.thalamus = thalamus or self._try_get_thalamus()
        self.values: Dict[str, Any] = {}
        self.goals: List[str] = []

        # Register with Thalamus if available
        if self.thalamus:
            try:
                self.thalamus.register_lobe('value_goal_management', self)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def update_values(self, new_values: Dict[str, Any]) -> None:
        """Merge new_values into the current value store."""
        self.values.update(new_values)
        print(f"[ValueGoalManagementLobe] Values updated: {self.values}")

    def add_goal(self, goal: str) -> None:
        """Append a new goal if it is not already present."""
        if goal not in self.goals:
            self.goals.append(goal)
        print(f"[ValueGoalManagementLobe] Goal added: {goal}")

    def prioritize_goals(self) -> List[str]:
        """
        Return goals in priority order. The current implementation preserves
        insertion order (FIFO), which is the simplest meaningful policy.
        Override this method to add scoring/sorting logic.
        """
        return list(self.goals)

    def route_goals(self) -> None:
        """Send the prioritized goal list to downstream lobes via Thalamus."""
        prioritized = self.prioritize_goals()
        if self.thalamus and prioritized:
            try:
                self.thalamus.send_message(
                    'executive_control',
                    'receive_goals',
                    {'goals': prioritized},
                )
            except Exception as e:
                print(f"[ValueGoalManagementLobe] Could not route goals: {e}")
        print(f"[ValueGoalManagementLobe] Goals routed: {prioritized}")

    def reset(self) -> None:
        """Clear all values and goals."""
        self.values.clear()
        self.goals.clear()
        print("[ValueGoalManagementLobe] Reset complete.")

    # ------------------------------------------------------------------
    # Thalamus message handler
    # ------------------------------------------------------------------

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = message.get('type')
        content = message.get('content', {k: v for k, v in message.items()
                                          if k not in ('type', '_message_id', 'message_id')})

        if msg_type == 'update_values':
            self.update_values(content.get('values', {}))
            return {'status': 'success', 'values': self.values}

        elif msg_type == 'add_goal':
            goal = content.get('goal')
            if not goal:
                return {'status': 'error', 'message': 'No goal provided'}
            self.add_goal(goal)
            return {'status': 'success', 'goals': self.goals}

        elif msg_type == 'prioritize_goals':
            return {'status': 'success', 'goals': self.prioritize_goals()}

        elif msg_type == 'route_goals':
            self.route_goals()
            return {'status': 'success', 'message': 'Goals routed'}

        elif msg_type == 'get_values':
            return {'status': 'success', 'values': self.values}

        elif msg_type == 'get_goals':
            return {'status': 'success', 'goals': self.goals}

        elif msg_type == 'reset':
            self.reset()
            return {'status': 'success', 'message': 'Reset complete'}

        elif msg_type == 'health':
            return {'status': 'success', 'healthy': True}

        else:
            return {'status': 'error', 'message': f'Unknown message type: {msg_type}'}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _try_get_thalamus():
        try:
            return get_thalamus()
        except Exception:
            return None
