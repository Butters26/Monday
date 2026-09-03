"""
AttentionLobe: Selective focus and prioritization module for the AI brain architecture.
Handles attention allocation, salience detection, and routing of prioritized signals to other lobes.
"""

class AttentionLobe:
    def __init__(self, thalamus=None):
        self.thalamus = thalamus
        self.current_focus = None
        self.salience_map = {}

    def update_salience(self, input_signals):
        """Update salience map based on input signals."""
        for signal in input_signals:
            self.salience_map[signal] = self._compute_salience(signal)
        # Log salience map
        print(f"[AttentionLobe] Updated salience map: {self.salience_map}")

    def select_focus(self):
        """Select the most salient signal as the current focus."""
        if not self.salience_map:
            self.current_focus = None
            print("[AttentionLobe] No signals to focus on.")
            return None
        # Select signal with highest salience
        self.current_focus = max(self.salience_map, key=self.salience_map.get)
        print(f"[AttentionLobe] Current focus: {self.current_focus}")
        return self.current_focus

    def route_focus(self):
        """Route the current focus to relevant lobes via Thalamus."""
        if self.thalamus and self.current_focus:
            print(f"[AttentionLobe] Routing focus '{self.current_focus}' to Thalamus.")
            self.thalamus.send_message('reasoning', 'attention_focus', {'focus': self.current_focus}, source='attention')
        else:
            print("[AttentionLobe] No focus to route or Thalamus not available.")

    def _compute_salience(self, signal):
        """Compute salience based on signal properties."""
        # Example: Use length and keyword boost
        base = len(str(signal))
        if isinstance(signal, str) and 'important' in signal:
            base += 10
        return base

    def reset(self):
        self.current_focus = None
        self.salience_map.clear()
        print("[AttentionLobe] Reset state.")
#
# Integration: process_message for Thalamus routing
    def process_message(self, message):
        msg_type = message.get('type')
        if 'content' in message:
            content = message.get('content', {})
        else:
            content = {k: v for k, v in message.items() if k not in ('type', '_message_id', 'message_id')}
        if msg_type == 'update_salience':
            self.update_salience(content.get('signals', []))
            return {'status': 'success', 'message': 'Salience updated'}
        elif msg_type == 'select_focus':
            focus = self.select_focus()
            return {'status': 'success', 'focus': focus}
        elif msg_type == 'route_focus':
            self.route_focus()
            return {'status': 'success', 'message': 'Focus routed'}
        elif msg_type == 'reset':
            self.reset()
            return {'status': 'success', 'message': 'AttentionLobe reset'}
        else:
            return {'status': 'error', 'message': f'Unknown message type: {msg_type}'}

# TODO: Integrate with Thalamus and other lobes
# TODO: Add error handling, logging, and configuration
