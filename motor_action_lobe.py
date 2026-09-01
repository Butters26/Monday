"""
MotorActionLobe: Motor/action planning and execution module for the AI brain architecture.
Handles action selection, motor output generation, and coordination with other lobes.
"""

class MotorActionLobe:
    def __init__(self, thalamus=None):
        self.thalamus = thalamus
        self.action_queue = []
        self.last_action = None

    def plan_action(self, intent):
        """Plan an action based on intent or input."""
        # TODO: Implement action planning logic
        action = self._generate_action(intent)
        self.action_queue.append(action)
        return action

    def execute_action(self):
        """Execute the next action in the queue."""
        if not self.action_queue:
            return None
        action = self.action_queue.pop(0)
        self.last_action = action
        # TODO: Integrate with output lobe or external interface
        if self.thalamus:
            # Send a motor_output message to the Output Lobe
            try:
                self.thalamus.send_message('output', 'motor_output', {'action': action}, source='motor_action')
            except Exception as e:
                print(f"[MotorActionLobe] Error routing action to output: {e}")
        print(f"[MotorActionLobe] Executed action: {action}")
        return action

    def _generate_action(self, intent):
        """Placeholder for action generation logic."""
        # Simple generator: wrap intent into an action dict
        action = {
            'id': str(uuid.uuid4()) if 'uuid' in globals() else intent,
            'type': 'motor',
            'intent': intent,
            'timestamp': time.time()
        }
        return action

    def reset(self):
        self.action_queue.clear()
        self.last_action = None

# TODO: Integrate with Thalamus and other lobes
# TODO: Add error handling, logging, and configuration
    def process_message(self, message):
        msg_type = message.get('type')
        if 'content' in message:
            content = message.get('content', {})
        else:
            content = {k: v for k, v in message.items() if k not in ('type', '_message_id', 'message_id')}
        if msg_type == 'plan_action':
            intent = content.get('intent')
            if intent is None:
                return {'status': 'error', 'message': 'Missing intent'}
            action = self.plan_action(intent)
            return {'status': 'success', 'action': action}
        elif msg_type == 'execute_next':
            action = self.execute_action()
            if action is None:
                return {'status': 'success', 'message': 'No actions to execute'}
            return {'status': 'success', 'action': action}
        elif msg_type == 'reset':
            self.reset()
            return {'status': 'success', 'message': 'MotorActionLobe reset'}
        else:
            return {'status': 'error', 'message': f'Unknown message type: {msg_type}'}

import time
import uuid
