"""
SocialContextLobe: Social/contextual awareness module for the AI brain architecture.
Handles social cues, context tracking, and interaction management.
"""

class SocialContextLobe:
    def __init__(self, thalamus=None):
        self.thalamus = thalamus
        self.context_state = {}
        self.social_cues = []

    def update_context(self, context):
        """Update context state based on input."""
        self.context_state.update(context)

    def process_social_cue(self, cue):
        """Process a social cue and update state."""
        self.social_cues.append(cue)
        # Integrate with language/output to generate responses or actions
        try:
            if cue == 'greeting':
                # Ask language to generate a friendly reply
                if self.thalamus:
                    self.thalamus.send_message('language', 'generate_reply', {'prompt': 'greeting'}, source='social_context')
            else:
                if self.thalamus:
                    self.thalamus.send_message('reasoning', 'social_cue', {'cue': cue}, source='social_context')
        except Exception as e:
            print(f"[SocialContextLobe] Error handling cue: {e}")

    def reset(self):
        self.context_state.clear()
        self.social_cues.clear()

    def process_message(self, message):
        msg_type = message.get('type')
        content = message.get('content', {})
        if msg_type == 'analyze_context':
            text = content.get('text', content.get('user_input', ''))
            cue = 'greeting' if isinstance(text, str) and text.lower().strip().split()[:1] in (['hi'], ['hello'], ['hey']) else 'conversation'
            context = {'cue': cue, 'text': text}
            self.update_context(context)
            return {'status': 'success', 'context': context}
        if msg_type == 'update_context':
            ctx = content.get('context', {})
            self.update_context(ctx)
            return {'status': 'success', 'context': self.context_state}
        elif msg_type == 'social_cue':
            cue = content.get('cue')
            if cue is None:
                return {'status': 'error', 'message': 'Missing cue'}
            self.process_social_cue(cue)
            return {'status': 'success', 'message': 'Cue processed'}
        elif msg_type == 'reset':
            self.reset()
            return {'status': 'success', 'message': 'SocialContextLobe reset'}
        else:
            return {'status': 'error', 'message': f'Unknown message type: {msg_type}'}

# TODO: Integrate with Thalamus and other lobes
# TODO: Add error handling, logging, and configuration
