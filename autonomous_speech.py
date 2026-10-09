#!/usr/bin/env python3
"""
Autonomous Speech System - Social WHEN/WHETHER filter for speak-worthy thoughts.

Takes already-formed autonomous thoughts and decides whether social context
allows saying them out loud. Does not invent wording (Language) and does not
synthesize audio (Voice). Live lobe name: "speech".
"""

import time
import threading
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from thalamus import get_thalamus

@dataclass
class SpeechDecision:
    """A decision about whether to speak"""
    thought_id: str
    content: str
    should_speak: bool
    reason: str
    timing: str  # "now", "wait", "never"
    priority: float  # 0-1
    intent_type: str = ""
    requires_user: bool = True


class AutonomousSpeechSystem:
    """
    Filters autonomous thoughts and decides which to speak.
    Social awareness - knows when to stay quiet.
    """
    
    def __init__(self, thalamus=None, auto_register: bool = False):
        """Social WHEN/WHETHER filter for speak-worthy autonomous thoughts.

        Live path: create_core_systems passes thalamus= and registers lobe
        name "speech". Decision-only: evaluate_thought → SpeechDecision.
        Does not invent wording (Language) or audio (Voice). Dead pending /
        wording-invent APIs removed from the live message surface.
        """
        # Prefer explicit thalamus from create_core_systems; avoid get_thalamus()
        # singleton (that instance is not the live core Thalamus).
        self.thalamus = thalamus if thalamus is not None else None
        self.running = True
        self.last_decision: Optional[Dict[str, Any]] = None

        # State
        self.user_is_typing = False
        self.user_is_busy = False
        self.user_present = True  # Assume user is there
        self.last_speech_time = 0.0
        self.mercy_is_speaking = False
        self.pending_intents: List[Dict[str, Any]] = []
        self.min_speech_interval = 15.0  # Natural pause between unsolicited comments
        self.conversation_active = False
        self.last_user_input_time = time.time()

        # Social rules - human-like
        self.interruption_threshold = 0.85  # High bar for interrupting

        # Lock
        self.lock = threading.Lock()

        # Legacy CLI: construct without thalamus → singleton + self-register.
        # Live path: create_core_systems passes thalamus= and registers "speech".
        if thalamus is None:
            self.thalamus = get_thalamus()
            self._register_with_thalamus()
        elif auto_register:
            self._register_with_thalamus()
    
    def _register_with_thalamus(self):
        """Register with Thalamus"""
        try:
            result = self.thalamus.register_lobe('speech', self)
            if result.get('status') == 'success':
                print("✅ Autonomous Speech System registered with Thalamus")
                return True
            return False
        except Exception as e:
            print(f"⚠️  Failed to register Autonomous Speech System: {e}")
            return False
    
    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming messages (Thalamus envelope or direct)."""
        msg_type = message.get('type')
        # Thalamus wraps payload under content={...}; flatten like Voice/Autonomous.
        if isinstance(message.get('content'), dict):
            flat = dict(message['content'])
            flat['type'] = msg_type
            message = flat
        msg_type = message.get('type')

        if msg_type == 'evaluate_thought':
            return self._evaluate_thought(message)

        elif msg_type == 'get_pending_intents':
            return {
                'status': 'success',
                'intents': [dict(item) for item in self.pending_intents],
            }

        elif msg_type in ('get_pending_speech', 'generate_unprompted', 'queue_speech'):
            return {
                'status': 'error',
                'message': (
                    f'{msg_type} removed: speech lobe is decision-only on live path; '
                    'Language owns wording; Thalamus delivers allowed asides'
                ),
                'decision_only': True,
            }
        
        elif msg_type == 'user_typing':
            self.user_is_typing = message.get('is_typing', False)
            return {'status': 'success'}
        
        elif msg_type == 'user_busy':
            self.user_is_busy = message.get('is_busy', False)
            return {'status': 'success'}
        
        elif msg_type == 'conversation_active':
            self.conversation_active = message.get('active', False)
            return {'status': 'success'}
        
        elif msg_type == 'speech_delivered':
            self.last_speech_time = time.time()
            self.mercy_is_speaking = False
            return {'status': 'success'}

        elif msg_type == 'speaking':
            self.mercy_is_speaking = bool(message.get('active', False))
            return {'status': 'success'}
        
        elif msg_type == 'user_spoke':
            self.last_user_input_time = time.time()
            self.user_present = True
            return {'status': 'success'}
        
        elif msg_type == 'health':
            return {'status': 'success', 'healthy': True}

        elif msg_type == 'get_status':
            return {'status': 'success', **self.get_status()}
        
        else:
            return {'status': 'error', 'message': f'Unknown message type: {msg_type}'}
    
    def _evaluate_thought(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate whether a thought should be spoken.
        This is the social awareness filter.
        """
        thought = message.get('thought', {})
        content = thought.get('content', '')
        thought_id = thought.get('id', '')
        intent = thought.get('communication_intent')
        if not isinstance(intent, dict):
            intent = message.get('communication_intent')
        intent = intent if isinstance(intent, dict) else {}
        intent_type = str(intent.get('type') or 'none')
        if intent_type == 'none':
            return self._record_decision(
                SpeechDecision(thought_id, content, False, "No approved communication intent",
                               "never", 0.0, intent_type, True)
            )
        try:
            priority = max(0.0, min(1.0, float(intent.get('priority', 0.0))))
        except (TypeError, ValueError):
            priority = 0.0
        requires_user = bool(intent.get('requires_user', True))

        allowed_types = {
            "inquire", "share_insight", "request_feedback", "report_discovery",
            "express_feeling", "social_initiation",
        }
        if intent_type not in allowed_types:
            return self._record_decision(
                SpeechDecision(thought_id, content, False, "Unsupported communication intent",
                               "never", priority, intent_type, requires_user)
            )

        timing, reason = self._decide_timing(priority)
        if timing != "never":
            if requires_user and not self.user_present:
                timing, reason = "wait", "Waiting for the user"
            elif self.user_is_typing and priority < 0.95:
                timing, reason = "wait", "User is typing"
            elif self.user_is_busy and priority < 0.98:
                timing, reason = "wait", "User is busy"
            elif self.mercy_is_speaking:
                timing, reason = "wait", "Mercy is already speaking"
            elif time.time() - self.last_speech_time < self.min_speech_interval and priority < 0.9:
                timing, reason = "wait", "Waiting for a natural pause"
            elif self.conversation_active and priority < 0.85:
                timing, reason = "wait", "Conversation active, letting user lead"

        decision = SpeechDecision(
            thought_id=thought_id,
            content=content,
            should_speak=timing != "never",
            reason=reason,
            timing=timing,
            priority=priority,
            intent_type=intent_type,
            requires_user=requires_user,
        )
        if timing == "wait":
            self._retain_pending(intent, thought)
        elif timing == "now":
            self.pending_intents = [
                item for item in self.pending_intents
                if item.get("thought_id") != thought_id
            ]
        return self._record_decision(decision)

    def _record_decision(self, decision: SpeechDecision) -> Dict[str, Any]:
        payload = asdict(decision)
        self.last_decision = dict(payload)
        return {'status': 'success', 'decision': payload}

    def _retain_pending(self, intent: Dict[str, Any], thought: Dict[str, Any]) -> None:
        thought_id = str(intent.get("thought_id") or thought.get("id") or "")
        if any(str(item.get("thought_id") or "") == thought_id for item in self.pending_intents):
            return
        self.pending_intents.append({
            **dict(intent),
            "thought_id": thought_id,
            "content": str(thought.get("content") or ""),
            "thought_type": str(thought.get("thought_type") or ""),
            "timestamp": float(thought.get("timestamp") or time.time()),
        })
        self.pending_intents = self.pending_intents[-32:]
    
    def _check_social_context(self, priority: float) -> tuple:
        """Check if social context allows speaking"""
        
        # User is typing - don't interrupt unless very important
        if self.user_is_typing:
            if priority < 0.95:
                return False, "User is typing"
        
        # User is busy - don't interrupt
        if self.user_is_busy:
            if priority < 0.98:  # Only critical communications
                return False, "User is busy"
        
        # Spoke too recently
        time_since_speech = time.time() - self.last_speech_time
        if time_since_speech < self.min_speech_interval:
            if priority < 0.9:
                return False, f"Spoke {time_since_speech:.0f}s ago, waiting"
        
        # In active conversation - let user lead
        if self.conversation_active:
            if priority < 0.85:
                return False, "Conversation active, letting user lead"
        
        return True, "Social context allows"
    
    def _check_content_appropriate(self, content: str, thought_type: str) -> tuple:
        """Check if content is appropriate to speak"""
        
        # Don't speak robotic meta-thoughts
        robotic_phrases = ['processing', 'computing', 'analyzing data', 'executing', 'parsing']
        for phrase in robotic_phrases:
            if phrase.lower() in content.lower():
                return False, "Too robotic, keep internal"
        
        # Don't speak incomplete thoughts
        if len(content) < 5:
            return False, "Too short"
        
        # Questions are good - natural conversation
        # Observations are good - shows she's thinking
        # Comments on things are good - feels present
        
        return True, "Content appropriate"
    
    def _decide_timing(self, priority: float) -> tuple:
        """Use intent importance for admission, with social conditions setting timing."""
        if priority >= 0.8:
            return 'now', "High-priority communication"
        elif priority >= 0.35:
            return 'wait', "Waiting for a natural pause"
        return 'never', "Communication priority too low"
    
    def start(self):
        """Start the speech system (legacy CLI loop)."""
        print("🗣️ Autonomous Speech System running...")
        while self.running:
            time.sleep(1)
    
    # generate_natural_speech / should_initiate_speech / queue_speech REMOVED —
    # Language owns wording; live speech lobe is decision-only.

if __name__ == "__main__":
    print("🗣️ Autonomous Speech System starting...")
    system = AutonomousSpeechSystem(auto_register=True)
    
    try:
        system.start()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down")
        system.shutdown()
