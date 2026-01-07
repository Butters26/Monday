"""
SensoryIntegrationLobe: Sensory integration and preprocessing module for the AI brain architecture.
Handles multi-modal input fusion, preprocessing, and signal normalization.
"""

class SensoryIntegrationLobe:
    def __init__(self, thalamus=None):
        self.thalamus = thalamus
        self.sensory_buffer = []
        self.normalized_signals = []

    def integrate_inputs(self, inputs):
        """Integrate and preprocess sensory inputs."""
        self.sensory_buffer.extend(inputs)
        self.normalized_signals = self._normalize(inputs)
        # TODO: Route normalized signals to relevant lobes
        if self.thalamus:
            try:
                # Send normalized signals to perception for further processing
                self.thalamus.send_message('perception', 'sensory_data', {'signals': self.normalized_signals}, source='sensory_integration')
            except Exception as e:
                print(f"[SensoryIntegrationLobe] Error routing to perception: {e}")
        print(f"[SensoryIntegrationLobe] Integrated inputs: {self.normalized_signals}")

    def _normalize(self, inputs):
        """Placeholder for normalization logic."""
        # Basic normalization example: lowercase strings and strip whitespace
        normalized = []
        for item in inputs:
            if isinstance(item, str):
                normalized.append(item.strip().lower())
            else:
                normalized.append(item)
        return normalized

    def reset(self):
        self.sensory_buffer.clear()
        self.normalized_signals.clear()

    def process_message(self, message):
        msg_type = message.get('type')
        if 'content' in message:
            content = message.get('content', {})
        else:
            content = {k: v for k, v in message.items() if k not in ('type', '_message_id', 'message_id')}
        if msg_type == 'ingest':
            inputs = content.get('inputs', [])
            self.integrate_inputs(inputs)
            return {'status': 'success', 'signals': self.normalized_signals}
        elif msg_type == 'reset':
            self.reset()
            return {'status': 'success', 'message': 'SensoryIntegrationLobe reset'}
        else:
            return {'status': 'error', 'message': f'Unknown message type: {msg_type}'}

# TODO: Integrate with Thalamus and other lobes
# TODO: Add error handling, logging, and configuration
