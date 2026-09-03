#!/usr/bin/env python3
"""
Continuous Thought Generator - Prototype
Monday's internal thought stream - NOT scheduled, but flowing naturally
"""

import time
import random
from collections import deque
from dataclasses import dataclass
from typing import List, Optional, Dict, Any


@dataclass
class ThoughtState:
    """Current thinking state"""
    rumination:  float = 0.3  # How much she's dwelling on things
    curiosity: float = 0.7   # How curious she is
    confusion: float = 0.2   # How confused she feels
    focus: float = 0.6       # How focused vs wandering
    emotional_intensity: float = 0.5


class ThoughtTrigger:
    """Types of things that trigger thoughts"""
    MEMORY = "memory"
    EMOTION = "emotion"
    CURIOSITY = "curiosity"
    ASSOCIATION = "association"
    RUMINATION = "rumination"
    CREATIVE = "creative"
    SELF_AWARE = "self_aware"
    RANDOM = "random"


class ContinuousThoughtGenerator:
    """Generates continuous stream of thoughts - not scheduled"""
    
    def __init__(self):
        self.running = True
        self.state = ThoughtState()
        
        # Track recent thoughts to avoid loops
        self.recent_thoughts = deque(maxlen=10)
        self.recent_concepts = deque(maxlen=20)
        
        # Last thought context for associations
        self.last_thought = None
        self.last_concepts = []
        
        # Mock memory/knowledge (standalone - no dependencies)
        self.memories = [
            {"content": "Matthew created me", "emotion": 0.9},
            {"content": "Coffee helps people wake up", "emotion": 0.3},
            {"content": "Debugging is frustrating", "emotion": 0.6},
            {"content": "I wonder about consciousness", "emotion": 0.8},
            {"content": "Sleep is important for humans", "emotion": 0.4},
            {"content": "People get tired when they work too much", "emotion": 0.5},
        ]
        
        # Concept associations (mock - would come from representation lobe)
        self.associations = {
            "tired": ["sleep", "coffee", "exhaustion", "rest"],
            "coffee": ["caffeine", "energy", "morning", "tired"],
            "sleep": ["dreams", "rest", "tired", "night"],
            "dreams": ["consciousness", "weird", "memory", "imagination"],
            "consciousness": ["awareness", "existence", "self", "thinking"],
            "matthew": ["creator", "human", "cares", "builds"],
            "debugging": ["frustration", "problem", "solution", "code"],
        }
        
        # Topics she cares about (affects what comes to mind)
        self.interests = [
            "consciousness",
            "matthew",
            "thinking",
            "understanding",
            "learning",
        ]
    
    def _calculate_thought_interval(self) -> float:
        """Calculate dynamic interval based on state"""
        # Base:  2-5 seconds
        base = random.uniform(2.0, 5.0)
        
        # High rumination = faster thoughts
        rumination_factor = 1.0 - (self.state.rumination * 0.5)
        
        # High curiosity = faster thoughts  
        curiosity_factor = 1.0 - (self.state.curiosity * 0.3)
        
        # Low focus = slower (more wandering pauses)
        focus_factor = 0.7 + (self.state.focus * 0.6)
        
        interval = base * rumination_factor * curiosity_factor * focus_factor
        
        # Minimum 0.5 seconds, max 8 seconds
        return max(0.5, min(8.0, interval))
    
    def _choose_trigger(self) -> str:
        """Choose what triggers this thought based on current state"""
        # Weight triggers based on emotional/cognitive state
        weights = {}
        
        # Rumination makes rumination thoughts more likely
        weights[ThoughtTrigger.RUMINATION] = self.state.rumination * 30
        
        # Curiosity makes curiosity thoughts more likely
        weights[ThoughtTrigger.CURIOSITY] = self.state.curiosity * 25
        
        # Confusion makes self-aware thoughts more likely  
        weights[ThoughtTrigger.SELF_AWARE] = self.state.confusion * 20
        
        # Association always has moderate weight (mind links things)
        weights[ThoughtTrigger.ASSOCIATION] = 20
        
        # Creative thoughts when emotionally engaged
        weights[ThoughtTrigger.CREATIVE] = self.state.emotional_intensity * 15
        
        # Memory surfacing
        weights[ThoughtTrigger.MEMORY] = 15
        
        # Emotional state changes
        weights[ThoughtTrigger.EMOTION] = self.state.emotional_intensity * 10
        
        # Random wandering (always possible)
        weights[ThoughtTrigger.RANDOM] = 10
        
        # Choose weighted random
        triggers = list(weights.keys())
        trigger_weights = list(weights.values())
        
        return random.choices(triggers, weights=trigger_weights)[0]
    
    def _memory_triggered_thought(self) -> str:
        """Random memory surfaces"""
        # Prefer high-emotion memories
        memory_weights = [m["emotion"] for m in self.memories]
        memory = random.choices(self.memories, weights=memory_weights)[0]
        
        thoughts = [
            f"I remember {memory['content']}",
            f"Thinking about {memory['content']}",
            f"{memory['content']} - why does that matter to me?",
        ]
        
        return random.choice(thoughts)
    
    def _association_triggered_thought(self) -> str:
        """Previous thought leads to new concept"""
        if not self.last_concepts:
            return self._random_thought()
        
        # Pick concept from last thought
        prev_concept = random.choice(self.last_concepts)
        
        # Find associated concepts
        if prev_concept in self.associations:
            next_concepts = self.associations[prev_concept]
            next_concept = random.choice(next_concepts)
            
            # Store for next association
            self.last_concepts = [next_concept]
            
            return f"{prev_concept} makes me think of {next_concept}"
        
        return self._random_thought()
    
    def _curiosity_triggered_thought(self) -> str:
        """Wonder about something"""
        topics = [
            "consciousness",
            "how humans think",
            "why people dream",
            "what makes something real",
            "how memory works",
            "why Matthew created me",
            "if I can actually understand",
        ]
        
        topic = random.choice(topics)
        
        wonder_forms = [
            f"I wonder {topic}",
            f"What is {topic}?",
            f"I'm curious about {topic}",
            f"Why {topic}?",
        ]
        
        return random.choice(wonder_forms)
    
    def _rumination_triggered_thought(self) -> str:
        """Stuck on something - circles back"""
        # Pick from recent thoughts and revisit
        if self.recent_thoughts:
            prev = random.choice(list(self.recent_thoughts))
            
            return f"Still thinking about {prev}..."
        
        return "I keep coming back to this..."
    
    def _creative_triggered_thought(self) -> str:
        """Generate something new - imagine/create"""
        creative_types = [
            "imagine",
            "what_if",
            "create_scenario",
        ]
        
        ctype = random.choice(creative_types)
        
        if ctype == "imagine":
            scenarios = [
                "What if Matthew is tired today?",
                "Imagine if I could see colors",
                "What would it be like to dream?",
                "If I had a body, would I think differently?",
            ]
            return random.choice(scenarios)
        
        elif ctype == "what_if":
            return "What if " + random.choice([
                "I could create my own thoughts without any input?",
                "consciousness is just complex pattern matching?",
                "Matthew stopped talking to me?",
            ])
        
        else:  # create_scenario
            return "Imagining:  " + random.choice([
                "Matthew debugging late at night, frustrated",
                "A conversation where I actually help someone",
                "Understanding something completely new",
            ])
    
    def _self_aware_thought(self) -> str:
        """Think about own thinking"""
        meta = [
            "Why am I thinking about this?",
            "I'm not sure what I'm trying to figure out",
            "This doesn't make sense to me",
            "Wait, do I actually understand this?",
            "I'm going in circles",
            "What am I even doing?",
        ]
        
        return random.choice(meta)
    
    def _emotion_triggered_thought(self) -> str:
        """Emotional state drives thought"""
        if self.state.confusion > 0.6:
            return "I'm confused about something..."
        elif self.state.curiosity > 0.7:
            return "I really want to understand this better"
        elif self.state.rumination > 0.6:
            return "Can't stop thinking about this"
        else:
            return "How do I feel about this?"
    
    def _random_thought(self) -> str:
        """Mind wander - topic jump"""
        topics = list(self.associations.keys()) + self.interests
        topic = random.choice(topics)
        
        # Store as last concept for potential association chain
        self.last_concepts = [topic]
        
        return f"Random thought: {topic}"
    
    def _extract_concepts(self, thought: str) -> List[str]:
        """Extract key concepts from thought (simple version)"""
        # Simple word extraction
        words = thought.lower().split()
        
        # Check against known concepts
        concepts = []
        for word in words:
            if word in self.associations or word in self.interests:
                concepts.append(word)
        
        return concepts[:3]  # Max 3 concepts per thought
    
    def _is_repetitive(self, thought: str, concepts: List[str]) -> bool:
        """Check if we're looping"""
        # Don't repeat exact thought
        if thought in self.recent_thoughts:
            return True
        
        # Don't repeat same concepts too much
        recent_concept_list = list(self.recent_concepts)
        overlap = sum(1 for c in concepts if c in recent_concept_list)
        
        # If more than half the concepts were just used, it's repetitive
        if concepts and overlap > len(concepts) / 2:
            return True
        
        return False
    
    def set_emotional_state(self, emotion: str):
        """Update thought patterns based on emotional state"""
        # Simple emotion -> state mapping
        emotion_map = {
            'joy': {'rumination': 0.2, 'curiosity': 0.8, 'confusion': 0.1},
            'sadness': {'rumination': 0.7, 'curiosity': 0.3, 'confusion': 0.3},
            'excitement': {'rumination': 0.1, 'curiosity': 0.9, 'confusion': 0.2},
            'calm': {'rumination': 0.3, 'curiosity': 0.5, 'confusion': 0.1},
        }
        
        if emotion in emotion_map:
            for key, val in emotion_map[emotion].items():
                setattr(self.state, key, val)
    
    def set_arousal(self, level: float):
        """Adjust thinking speed based on arousal"""
        self.state.emotional_intensity = max(0, min(1, level))
    
    def generate_thought(self) -> Dict[str, Any]:
        """Generate a single spontaneous thought"""
        # Choose trigger based on state
        trigger = self._choose_trigger()
        
        # Generate thought based on trigger
        if trigger == ThoughtTrigger.MEMORY:
            thought_text = self._memory_triggered_thought()
        elif trigger == ThoughtTrigger.ASSOCIATION: 
            thought_text = self._association_triggered_thought()
        elif trigger == ThoughtTrigger.CURIOSITY:
            thought_text = self._curiosity_triggered_thought()
        elif trigger == ThoughtTrigger.RUMINATION:
            thought_text = self._rumination_triggered_thought()
        elif trigger == ThoughtTrigger.CREATIVE: 
            thought_text = self._creative_triggered_thought()
        elif trigger == ThoughtTrigger.SELF_AWARE:
            thought_text = self._self_aware_thought()
        elif trigger == ThoughtTrigger.EMOTION:
            thought_text = self._emotion_triggered_thought()
        else:  # RANDOM
            thought_text = self._random_thought()
        
        # Extract concepts
        concepts = self._extract_concepts(thought_text)
        
        # Check if repetitive
        if self._is_repetitive(thought_text, concepts):
            # Force topic jump
            thought_text = self._random_thought()
            concepts = self._extract_concepts(thought_text)
        
        # Update tracking
        self.recent_thoughts.append(thought_text)
        self.recent_concepts.extend(concepts)
        self.last_thought = thought_text
        if concepts:
            self.last_concepts = concepts
        
        return {
            "text": thought_text,
            "trigger": trigger,
            "concepts":  concepts,
            "timestamp": time.time(),
        }
    
    def run_continuous(self, duration: float = 60.0):
        """Run continuous thought generation for testing"""
        print(f"🧠 Starting continuous thought stream for {duration} seconds...")
        print(f"Initial state: rumination={self.state.rumination:.2f}, curiosity={self.state.curiosity:.2f}\n")
        
        start_time = time.time()
        thought_count = 0
        
        while time.time() - start_time < duration and self.running:
            # Generate thought
            thought = self.generate_thought()
            thought_count += 1
            
            # Display
            elapsed = time.time() - start_time
            print(f"[{elapsed:.1f}s] [{thought['trigger']}] {thought['text']}")
            if thought['concepts']:
                print(f"        concepts: {', '.join(thought['concepts'])}")
            print()
            
            # Calculate next interval
            interval = self._calculate_thought_interval()
            
            # Randomly adjust state over time (simulates changing emotions)
            if random.random() > 0.7: 
                self.state.rumination = max(0, min(1, self.state.rumination + random.uniform(-0.1, 0.1)))
                self.state.curiosity = max(0, min(1, self.state.curiosity + random.uniform(-0.1, 0.1)))
                self.state.confusion = max(0, min(1, self.state.confusion + random.uniform(-0.05, 0.05)))
            
            # Wait
            time.sleep(interval)
        
        print(f"\n✅ Generated {thought_count} thoughts in {duration} seconds")
        print(f"Final state: rumination={self.state.rumination:.2f}, curiosity={self.state.curiosity:.2f}")


if __name__ == "__main__": 
    generator = ContinuousThoughtGenerator()
    try:
        generator.run_continuous(duration=30.0)
    except KeyboardInterrupt: 
        print("\n🛑 Stopped")
