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
        thought_type = thought.get('thought_type', '')
        intensity = thought.get('intensity', 0.5)
        thought_id = thought.get('id', '')

        # Check social context
        can_speak, reason = self._check_social_context(intensity)

        if not can_speak:
            decision = SpeechDecision(
                thought_id=thought_id,
                content=content,
                should_speak=False,
                reason=reason,
                timing='never',
                priority=intensity,
            )
            payload = asdict(decision)
            self.last_decision = dict(payload)
            return {'status': 'success', 'decision': payload}

        # Check content appropriateness
        is_appropriate, content_reason = self._check_content_appropriate(
            content, thought_type
        )

        if not is_appropriate:
            decision = SpeechDecision(
                thought_id=thought_id,
                content=content,
                should_speak=False,
                reason=content_reason,
                timing='never',
                priority=intensity,
            )
            payload = asdict(decision)
            self.last_decision = dict(payload)
            return {'status': 'success', 'decision': payload}

        # Decide timing
        timing = self._decide_timing(intensity)

        decision = SpeechDecision(
            thought_id=thought_id,
            content=content,
            should_speak=True,
            reason="Passed all filters",
            timing=timing,
            priority=intensity,
        )

        # Decision-only: Thalamus delivers allowed asides; no pending queue.

        payload = asdict(decision)
        self.last_decision = dict(payload)
        return {'status': 'success', 'decision': payload}
    
    def _check_social_context(self, intensity: float) -> tuple:
        """Check if social context allows speaking"""
        
        # User is typing - don't interrupt unless very important
        if self.user_is_typing:
            if intensity < self.interruption_threshold:
                return False, "User is typing"
        
        # User is busy - don't interrupt
        if self.user_is_busy:
            if intensity < 0.9:  # Only critical thoughts
                return False, "User is busy"
        
        # Spoke too recently
        time_since_speech = time.time() - self.last_speech_time
        if time_since_speech < self.min_speech_interval:
            if intensity < 0.7:
                return False, f"Spoke {time_since_speech:.0f}s ago, waiting"
        
        # In active conversation - let user lead
        if self.conversation_active:
            if intensity < 0.6:
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
    
    def _decide_timing(self, intensity: float) -> str:
        """Decide when to speak"""
        if intensity > 0.8:
            return 'now'
        elif intensity > 0.5:
            return 'wait'  # Wait for a natural pause
        else:
            return 'never'  # Keep internal
    
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
