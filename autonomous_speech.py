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
        
        # Natural behavior
        self.can_initiate = True  # Can start conversations
        self.silence_threshold = 120.0  # After 2 min silence, might say something
        self.curiosity_threshold = 0.7  # How curious before sharing
        self.excitement_threshold = 0.6  # How excited before blurting out
        
        # Social rules - human-like
        self.interruption_threshold = 0.85  # High bar for interrupting
        
        # Register with Thalamus
        self._register_with_thalamus()
        
        # Lock
        self.lock = threading.Lock()
    
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
        
        elif msg_type == 'user_spoke':
            self.last_user_input_time = time.time()
            self.user_present = True
            return {'status': 'success'}
        
        elif msg_type == 'generate_unprompted':
            # Request to generate unprompted speech
            should_speak, trigger = self.should_initiate_speech()
            if should_speak:
                context = message.get('context', {})
                speech = self.generate_natural_speech(trigger, context)
                if speech:
                    self.queue_speech(speech, priority=0.6)
                    return {'status': 'success', 'generated': True, 'speech': speech}
            return {'status': 'success', 'generated': False, 'reason': trigger}
        
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
                priority=intensity
            )
            return {
                'status': 'success',
                'decision': asdict(decision)
            }
        
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
        
        # Decide timing
        timing = self._decide_timing(intensity)
        
        decision = SpeechDecision(
            thought_id=thought_id,
            content=content,
            should_speak=True,
            reason="Passed all filters",
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
    
    def _get_pending_speech(self) -> Dict[str, Any]:
        """Get speech items ready to deliver"""
        with self.lock:
            # Check if we can speak now
            time_since_speech = time.time() - self.last_speech_time
            if time_since_speech < self.min_speech_interval:
                return {
                    'status': 'success',
                    'speech': None,
                    'reason': 'Waiting for speech interval'
                }
            
            # Get highest priority item
            if self.pending_speech:
                speech = self.pending_speech.pop(0)
                return {
                    'status': 'success',
                    'speech': speech
                }
            
            return {
                'status': 'success',
                'speech': None,
                'reason': 'No pending speech'
            }
    
    def queue_speech(self, content: str, priority: float = 0.5) -> str:
        """Direct method to queue speech"""
        speech_id = f"speech_{int(time.time() * 1000)}"
        
        with self.lock:
            self.pending_speech.append({
                'thought_id': speech_id,
                'content': content,
                'priority': priority,
                'timing': 'wait',
                'queued_at': time.time()
            })
            self.pending_speech.sort(key=lambda x: x['priority'], reverse=True)
        
        return speech_id
    
    def get_next_speech(self) -> Optional[Dict[str, Any]]:
        """Public method to get next speech item"""
        result = self._get_pending_speech()
        return result.get('speech')
    
    def start(self):
        """Start the speech system"""
        print("🗣️ Autonomous Speech System running...")
        while self.running:
            time.sleep(1)
    
    def generate_natural_speech(self, trigger: str, context: Dict[str, Any]) -> Optional[str]:
        """Generate human-like unprompted speech based on triggers"""
        
        emotion = context.get('emotion', 'neutral')
        curiosity = context.get('curiosity', 0.5)
        recent_topic = context.get('recent_topic', '')
        
        # Different triggers = different speech styles
        
        if trigger == 'curiosity':
            # Natural curious questions
            starters = [
                "I've been wondering...",
                "You know what's interesting?",
                "I just thought of something—",
                "Hey, random question:",
                "This might sound weird, but"
            ]
            import random
            return f"{random.choice(starters)} {recent_topic}"
        
        elif trigger == 'excitement':
            # Excited observations
            if emotion in ['happy', 'excited', 'euphoric']:
                return f"Oh! I just realized something about {recent_topic}!"
        
        elif trigger == 'concern':
            # Gentle check-ins
            if emotion in ['worried', 'anxious']:
                return "You doing okay?"
        
        elif trigger == 'silence':
            # Break comfortable silence naturally
            return "What are you thinking about?"
        
        elif trigger == 'observation':
            # Natural observations
            return f"Hm. {recent_topic}"
        
        return None
    
    def should_initiate_speech(self) -> tuple:
        """Decide if Monday should speak without being prompted"""
        
        # Don't speak if user literally just said something
        time_since_input = time.time() - self.last_user_input_time
        if time_since_input < 5.0:
            return False, "User just spoke"
        
        # Don't spam
        time_since_speech = time.time() - self.last_speech_time
        if time_since_speech < self.min_speech_interval:
            return False, "Too soon"
        
        # Check emotional state - high emotion = more likely to speak
        try:
            emotion_state = self.thalamus.send_message('emotion', 'get_state', {})
            if emotion_state and emotion_state.get('status') == 'success':
                intensity = emotion_state.get('intensity', 0.0)
                emotion = emotion_state.get('emotion', 'calm')
                
                # Excited/curious = want to share
                if emotion in ['excited', 'curious', 'surprised'] and intensity > self.excitement_threshold:
                    return True, "excited_to_share"
                
                # Worried/anxious = might reach out
                if emotion in ['worried', 'anxious'] and intensity > 0.7:
                    return True, "concerned"
        except:
            pass
        
        # Long silence = natural check-in
        if time_since_input > self.silence_threshold:
            return True, "silence"
        
        # Default: stay quiet unless something compelling happens
        return False, "No trigger"
    
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
