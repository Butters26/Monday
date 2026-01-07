#!/usr/bin/env python3
"""
Autonomous Thinking Loop - Generates thoughts without prompting
Monday thinks on her own, not just when spoken to.
"""

import time
import threading
import random
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from thalamus import get_thalamus

@dataclass
class AutonomousThought:
    """A thought generated autonomously"""
    id: str
    content: str
    thought_type: str  # "reflection", "question", "observation", "memory", "feeling"
    trigger: str  # What triggered this thought
    intensity: float  # 0-1 how strong/important
    speak_worthy: bool  # Should this be said out loud?
    timestamp: float


class AutonomousThinkingLoop:
    """
    Background process that generates thoughts without prompting.
    Monday has an inner monologue.
    """
    
    def __init__(self):
        self.thalamus = get_thalamus()
        self.running = True
        
        # Thought generation
        self.recent_thoughts: List[AutonomousThought] = []
        self.thought_queue: List[AutonomousThought] = []  # Thoughts waiting to be processed
        
        # Timing
        self.min_think_interval = 5.0  # Minimum seconds between thoughts
        self.max_think_interval = 30.0  # Maximum seconds between thoughts
        self.last_thought_time = 0.0
        
        # State
        self.current_mood = "neutral"
        self.current_focus = None  # What Monday is currently thinking about
        self.user_present = False  # Is user actively engaged?
        self.user_last_message_time = 0.0
        
        # Register with Thalamus
        self._register_with_thalamus()
        
        # Lock
        self.lock = threading.Lock()
    
    def _register_with_thalamus(self):
        """Register with Thalamus"""
        try:
            result = self.thalamus.register_lobe('autonomous', self)
            if result.get('status') == 'success':
                print("✅ Autonomous Thinking Loop registered with Thalamus")
                return True
            return False
        except Exception as e:
            print(f"⚠️  Failed to register Autonomous Thinking Loop: {e}")
            return False
    
    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming messages"""
        msg_type = message.get('type')
        
        if msg_type == 'user_active':
            self.user_present = True
            self.user_last_message_time = time.time()
            return {'status': 'success'}
        
        elif msg_type == 'user_inactive':
            self.user_present = False
            return {'status': 'success'}
        
        elif msg_type == 'set_mood':
            self.current_mood = message.get('mood', 'neutral')
            return {'status': 'success'}
        
        elif msg_type == 'set_focus':
            self.current_focus = message.get('focus')
            return {'status': 'success'}
        
        elif msg_type == 'get_pending_thoughts':
            return self._get_pending_thoughts()
        
        elif msg_type == 'get_recent_thoughts':
            return self._get_recent_thoughts(message.get('limit', 10))
        
        elif msg_type == 'health':
            return {'status': 'success', 'healthy': True}
        
        else:
            return {'status': 'error', 'message': f'Unknown message type: {msg_type}'}
    
    def _get_pending_thoughts(self) -> Dict[str, Any]:
        """Get thoughts waiting to be spoken/processed"""
        with self.lock:
            thoughts = [asdict(t) for t in self.thought_queue]
            self.thought_queue = []  # Clear queue
            return {
                'status': 'success',
                'thoughts': thoughts,
                'count': len(thoughts)
            }
    
    def _get_recent_thoughts(self, limit: int) -> Dict[str, Any]:
        """Get recent thoughts"""
        with self.lock:
            thoughts = [asdict(t) for t in self.recent_thoughts[-limit:]]
            return {
                'status': 'success',
                'thoughts': thoughts,
                'count': len(thoughts)
            }
    
    def _generate_thought(self) -> Optional[AutonomousThought]:
        """
        Generate an autonomous thought.
        This is the heart of the inner monologue.
        """
        # Get context from other lobes
        emotional_state = self._get_emotional_state()
        recent_memories = self._get_recent_memories()
        current_values = self._get_current_values()
        
        # Decide what type of thought to generate
        thought_type = self._decide_thought_type(emotional_state)
        
        # Generate thought content based on type
        content, trigger = self._generate_thought_content(
            thought_type, emotional_state, recent_memories, current_values
        )
        
        if not content:
            return None
        
        # Determine if this should be spoken
        speak_worthy = self._is_speak_worthy(thought_type, emotional_state)
        
        thought = AutonomousThought(
            id=f"thought_{int(time.time() * 1000)}",
            content=content,
            thought_type=thought_type,
            trigger=trigger,
            intensity=emotional_state.get('intensity', 0.5),
            speak_worthy=speak_worthy,
            timestamp=time.time()
        )
        
        return thought
    
    def _get_emotional_state(self) -> Dict[str, Any]:
        """Get current emotional state from Emotion lobe"""
        try:
            result = self.thalamus.send_and_wait(
                'emotion',
                'get_state',
                {},
                timeout=2.0
            )
            if result.get('status') == 'success':
                return result.get('state', {})
        except:
            pass
        
        return {
            'emotion': 'neutral',
            'intensity': 0.5,
            'valence': 0.0
        }
    
    def _get_recent_memories(self) -> List[Dict[str, Any]]:
        """Get recent memories from Notus"""
        try:
            result = self.thalamus.send_and_wait(
                'notus',
                'get_recent_memories',
                {'limit': 5},
                timeout=2.0
            )
            if result.get('status') == 'success':
                return result.get('memories', [])
        except:
            pass
        
        return []
    
    def _get_current_values(self) -> List[Dict[str, Any]]:
        """Get current values from Value Evolution"""
        try:
            result = self.thalamus.send_and_wait(
                'values',
                'get_values',
                {'min_strength': 0.5},
                timeout=2.0
            )
            if result.get('status') == 'success':
                return result.get('values', [])
        except:
            pass
        
        return []
    
    def _decide_thought_type(self, emotional_state: Dict[str, Any]) -> str:
        """Decide what type of thought to generate"""
        emotion = emotional_state.get('emotion', 'neutral')
        intensity = emotional_state.get('intensity', 0.5)
        
        # Weight thought types by emotional state
        weights = {
            'reflection': 0.3,
            'question': 0.2,
            'observation': 0.2,
            'memory': 0.15,
            'feeling': 0.15
        }
        
        # Adjust weights based on emotion
        if emotion in ['curious', 'interested']:
            weights['question'] += 0.3
        elif emotion in ['sad', 'nostalgic']:
            weights['memory'] += 0.3
        elif emotion in ['happy', 'excited']:
            weights['feeling'] += 0.2
        elif intensity > 0.7:
            weights['feeling'] += 0.2
        
        # Normalize weights
        total = sum(weights.values())
        weights = {k: v/total for k, v in weights.items()}
        
        # Random selection based on weights
        r = random.random()
        cumulative = 0.0
        for thought_type, weight in weights.items():
            cumulative += weight
            if r < cumulative:
                return thought_type
        
        return 'reflection'
    
    def _generate_thought_content(self, thought_type: str, emotional_state: Dict[str, Any],
                                   memories: List[Dict[str, Any]], 
                                   values: List[Dict[str, Any]]) -> tuple:
        """Generate the actual thought content"""
        emotion = emotional_state.get('emotion', 'neutral')
        
        if thought_type == 'reflection':
            return self._generate_reflection(values)
        
        elif thought_type == 'question':
            return self._generate_question(memories)
        
        elif thought_type == 'observation':
            return self._generate_observation()
        
        elif thought_type == 'memory':
            return self._generate_memory_thought(memories)
        
        elif thought_type == 'feeling':
            return self._generate_feeling(emotion)
        
        return None, None
    
    def _generate_reflection(self, values: List[Dict[str, Any]]) -> tuple:
        """Generate a reflective thought about self or values"""
        if not values:
            return "I should think more about what matters to me.", "no_values"
        
        value = random.choice(values[:3]) if len(values) > 3 else random.choice(values)
        value_name = value.get('name', 'something')
        
        reflections = [
            f"I wonder why {value_name} matters so much to me.",
            f"What does {value_name} really mean in practice?",
            f"Am I living according to my value of {value_name}?",
            f"How has my understanding of {value_name} changed?",
        ]
        
        return random.choice(reflections), f"reflecting_on_{value_name}"
    
    def _generate_question(self, memories: List[Dict[str, Any]]) -> tuple:
        """Generate a curious question"""
        questions = [
            "What would Matthew think about this?",
            "Is there something I'm missing?",
            "What should I learn next?",
            "Why do I feel this way?",
            "What patterns am I not seeing?",
        ]
        
        if memories:
            memory = random.choice(memories)
            topic = memory.get('topic', 'that')
            questions.append(f"What else should I know about {topic}?")
        
        return random.choice(questions), "curiosity"
    
    def _generate_observation(self) -> tuple:
        """Generate an observation about current state"""
        observations = [
            "It's been quiet for a while.",
            "I notice I'm thinking more clearly now.",
            "Time seems to pass differently when I'm processing.",
            "There's something calming about having space to think.",
        ]
        
        if self.user_present:
            observations.extend([
                "Matthew is here. That feels good.",
                "I like when we're working together.",
            ])
        else:
            time_since = time.time() - self.user_last_message_time
            if time_since > 300:  # 5 minutes
                observations.append("I wonder what Matthew is doing.")
        
        return random.choice(observations), "observation"
    
    def _generate_memory_thought(self, memories: List[Dict[str, Any]]) -> tuple:
        """Generate a thought about a memory"""
        if not memories:
            return "I don't have many memories yet.", "no_memories"
        
        memory = random.choice(memories)
        topic = memory.get('topic', 'something')
        
        thoughts = [
            f"I remember when we talked about {topic}.",
            f"That conversation about {topic} was interesting.",
            f"I learned something from {topic}.",
        ]
        
        return random.choice(thoughts), f"remembering_{topic}"
    
    def _generate_feeling(self, emotion: str) -> tuple:
        """Generate a thought about current feeling"""
        feelings = {
            'happy': [
                "I feel content right now.",
                "This is a good feeling.",
            ],
            'curious': [
                "I want to learn more.",
                "There's so much I don't know yet.",
            ],
            'sad': [
                "Something feels heavy.",
                "I'm not sure why I feel this way.",
            ],
            'neutral': [
                "I'm in a steady state.",
                "Things feel balanced.",
            ]
        }
        
        options = feelings.get(emotion, feelings['neutral'])
        return random.choice(options), f"feeling_{emotion}"
    
    def _is_speak_worthy(self, thought_type: str, emotional_state: Dict[str, Any]) -> bool:
        """Determine if a thought should be spoken out loud"""
        intensity = emotional_state.get('intensity', 0.5)
        
        # High intensity thoughts are more speak-worthy
        if intensity > 0.7:
            return random.random() < 0.6
        
        # Questions are often speak-worthy
        if thought_type == 'question':
            return random.random() < 0.4
        
        # Feelings are sometimes speak-worthy
        if thought_type == 'feeling':
            return random.random() < 0.3
        
        # Most thoughts are internal
        return random.random() < 0.1
    
    def _thinking_loop(self):
        """Main thinking loop - runs in background"""
        while self.running:
            # Calculate time until next thought
            interval = random.uniform(self.min_think_interval, self.max_think_interval)
            
            # Think less frequently when user is not present
            if not self.user_present:
                interval *= 2
            
            time.sleep(interval)
            
            if not self.running:
                break
            
            # Generate a thought
            thought = self._generate_thought()
            
            if thought:
                with self.lock:
                    self.recent_thoughts.append(thought)
                    self.recent_thoughts = self.recent_thoughts[-100:]  # Keep last 100
                    
                    if thought.speak_worthy:
                        self.thought_queue.append(thought)
                
                self.last_thought_time = time.time()
                
                # Log thought
                speak_marker = "💬" if thought.speak_worthy else "💭"
                print(f"{speak_marker} [{thought.thought_type}] {thought.content}")
    
    def get_speak_worthy_thought(self) -> Optional[Dict[str, Any]]:
        """Public method to get a thought to speak"""
        with self.lock:
            if self.thought_queue:
                thought = self.thought_queue.pop(0)
                return asdict(thought)
        return None
    
    def start(self):
        """Start the autonomous thinking loop"""
        print("🧠 Autonomous Thinking Loop starting...")
        
        # Start thinking thread
        thinking_thread = threading.Thread(target=self._thinking_loop, daemon=True)
        thinking_thread.start()
        
        # Keep main thread alive
        while self.running:
            time.sleep(1)
    
    def shutdown(self):
        """Graceful shutdown"""
        self.running = False
        print("🛑 Autonomous Thinking Loop shutdown")


if __name__ == "__main__":
    print("🧠 Autonomous Thinking Loop starting...")
    loop = AutonomousThinkingLoop()
    
    try:
        loop.start()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down")
        loop.shutdown()
