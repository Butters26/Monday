#!/usr/bin/env python3
"""
Autonomous Speech System - Decides which thoughts to say out loud
Takes autonomous thoughts and filters them based on social awareness.
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
    
    def __init__(self):
        self.thalamus = get_thalamus()
        self.running = True
        self.lock = threading.RLock()
        
        # Speech queue
        self.pending_speech: List[Dict[str, Any]] = []
        
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
        
        # Register with Thalamus
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
        """Handle incoming messages"""
        msg_type = message.get('type')
        
        if msg_type == 'evaluate_thought':
            return self._evaluate_thought(message)
        
        elif msg_type == 'get_pending_speech':
            return self._get_pending_speech()
        
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

        elif msg_type == 'delivery_failed':
            speech = message.get('speech')
            if not isinstance(speech, dict):
                return {'status': 'error', 'message': 'Speech item is required'}
            with self.lock:
                self.pending_speech.append(speech)
                self.pending_speech.sort(key=lambda item: item['priority'], reverse=True)
            return {'status': 'success'}
        
        elif msg_type == 'user_spoke':
            self.last_user_input_time = time.time()
            self.user_present = True
            return {'status': 'success'}
        
        elif msg_type == 'health':
            return {'status': 'success', 'healthy': True}
        
        else:
            return {'status': 'error', 'message': f'Unknown message type: {msg_type}'}
    
    def _evaluate_thought(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate whether a thought should be spoken.
        This is the social awareness filter.
        """
        thought = message.get('thought', {})
        if not isinstance(thought, dict):
            return {'status': 'error', 'message': 'Thought must be a dictionary'}
        content = thought.get('content', '')
        thought_type = thought.get('thought_type', '')
        try:
            intensity = max(0.0, min(1.0, float(thought.get('intensity', 0.5))))
        except (TypeError, ValueError):
            return {'status': 'error', 'message': 'Thought intensity must be numeric'}
        thought_id = thought.get('id', '')
        
        # Check social context
        # Check content appropriateness
        is_appropriate, content_reason = self._check_content_appropriate(content, thought_type)
        
        if not is_appropriate:
            decision = SpeechDecision(
                thought_id=thought_id,
                content=content,
                should_speak=False,
                reason=content_reason,
                timing='never',
                priority=intensity
            )
            return {
                'status': 'success',
                'decision': asdict(decision)
            }
        
        timing, reason = self._decide_timing(intensity)
        
        decision = SpeechDecision(
            thought_id=thought_id,
            content=content,
            should_speak=timing != 'never',
            reason=reason,
            timing=timing,
            priority=intensity
        )
        
        # Add to queue if should speak
        if timing in ['now', 'wait']:
            with self.lock:
                self.pending_speech.append({
                    'thought_id': thought_id,
                    'content': content,
                    'priority': intensity,
                    'timing': timing,
                    'queued_at': time.time()
                })
                # Sort by priority
                self.pending_speech.sort(key=lambda x: x['priority'], reverse=True)
        
        return {
            'status': 'success',
            'decision': asdict(decision)
        }
    
    def _decide_timing(self, intensity: float) -> tuple[str, str]:
        """Return NOW, WAIT, or DROP without inventing new content."""
        if intensity <= 0.5:
            return 'never', 'Insufficient priority'
        if self.user_is_typing and intensity <= self.interruption_threshold:
            return 'wait', 'User is typing'
        if self.user_is_busy and intensity < 0.9:
            return 'wait', 'User is busy'
        time_since_speech = time.time() - self.last_speech_time
        if time_since_speech < self.min_speech_interval and intensity < 0.7:
            return 'wait', f"Spoke {time_since_speech:.0f}s ago"
        if self.conversation_active and intensity < 0.9:
            return 'wait', 'Conversation active, letting user lead'
        return 'now', 'Social context allows'
    
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
    
    def _get_pending_speech(self) -> Dict[str, Any]:
        """Get speech items ready to deliver"""
        with self.lock:
            if not self.pending_speech:
                return {
                    'status': 'success',
                    'speech': None,
                    'reason': 'No pending speech'
                }
            speech = self.pending_speech[0]
            timing, reason = self._decide_timing(speech['priority'])
            if timing != 'now':
                return {'status': 'success', 'speech': None, 'reason': reason}
            self.pending_speech.pop(0)
            return {
                'status': 'success',
                'speech': speech
            }
    
    def get_next_speech(self) -> Optional[Dict[str, Any]]:
        """Public method to get next speech item"""
        result = self._get_pending_speech()
        return result.get('speech')
    
    def start(self):
        """Start the speech system"""
        print("🗣️ Autonomous Speech System running...")
        while self.running:
            time.sleep(1)
    
    def shutdown(self):
        """Graceful shutdown"""
        self.running = False
        print("🛑 Autonomous Speech System shutdown")


if __name__ == "__main__":
    print("🗣️ Autonomous Speech System starting...")
    system = AutonomousSpeechSystem()
    
    try:
        system.start()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down")
        system.shutdown()
