#!/usr/bin/env python3
"""
Meta-Awareness - The system that notices and directs thinking
Monday's ability to observe her own thoughts and choose engagement
"""

from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
import random


class ThinkingMode(Enum):
    """Current mode of thinking"""
    WANDERING = "wandering"  # Spontaneous stream flowing
    FOCUSED = "focused"      # Deliberately reasoning
    TRANSITION = "transition"  # Shifting between modes


@dataclass
class MetaState:
    """Meta-cognitive awareness state"""
    mode: ThinkingMode = ThinkingMode.WANDERING
    awareness_level: float = 0.6  # How aware of own thinking (0-1)
    engagement_threshold: float = 0.65  # How interesting before engaging
    
    # Tracking
    thoughts_noticed: int = 0
    thoughts_engaged: int = 0
    thoughts_dismissed: int = 0
    mode_shifts: int = 0


class MetaAwareness:
    """
    Meta-cognitive system that observes and directs thinking
    Decides which spontaneous thoughts to engage with
    """
    
    def __init__(self):
        self.state = MetaState()
        self.spontaneous_system = None
        self.controlled_system = None
        
        # What makes a thought worth engaging
        self.engagement_factors = {
            "novelty": 0.3,
            "emotional_intensity": 0.2,
            "relevance": 0.25,
            "curiosity": 0.25,
        }
    
    def set_spontaneous_system(self, system):
        """Connect to spontaneous thought generator"""
        self.spontaneous_system = system
    
    def set_controlled_system(self, system):
        """Connect to controlled thinking system"""
        self.controlled_system = system
    
    def notice_spontaneous_thought(self, thought: Dict[str, Any]) -> Dict[str, Any]:
        """
        Meta-awareness noticing a spontaneous thought
        Decides: ignore, notice but dismiss, or engage
        """
        
        # Roll for awareness - sometimes thoughts pass by unnoticed
        if random.random() > self.state.awareness_level:
            return {
                "action": "unnoticed",
                "reason": "Passed by without conscious notice"
            }
        
        # Thought was noticed
        self.state.thoughts_noticed += 1
        
        # Evaluate if worth engaging
        engagement_score = self._evaluate_engagement(thought)
        
        # Meta-comment based on evaluation
        meta_comment = self._generate_meta_comment(thought, engagement_score)
        
        if engagement_score >= self.state.engagement_threshold:
            # Engage with this thought
            self.state.thoughts_engaged += 1
            
            # Shift to focused mode
            if self.state.mode == ThinkingMode.WANDERING:
                self.shift_to_focused(thought)
            
            return {
                "action": "engaged",
                "engagement_score": engagement_score,
                "topic": thought.get("topic"),
                "question": self._formulate_question(thought),
                "meta_comment": meta_comment,
            }
        
        else:
            # Noticed but dismissed
            self.state.thoughts_dismissed += 1
            
            return {
                "action": "dismissed",
                "engagement_score": engagement_score,
                "reason": f"Not engaging (score: {engagement_score:.2f}, threshold: {self.state.engagement_threshold:.2f})",
                "meta_comment": meta_comment,
            }
    
    def _evaluate_engagement(self, thought: Dict[str, Any]) -> float:
        """Calculate how engaging this thought is"""
        
        score = 0.0
        
        # Intensity matters
        intensity = thought.get("intensity", 0.5)
        score += intensity * self.engagement_factors["emotional_intensity"]
        
        # Question thoughts are naturally engaging
        if thought.get("trigger") == "question":
            score += self.engagement_factors["curiosity"]
        
        # Memory and association thoughts have moderate engagement
        if thought.get("trigger") in ["memory", "association"]:
            score += self.engagement_factors["relevance"] * 0.7
        
        # Random thoughts are less engaging
        if thought.get("trigger") == "random":
            score += self.engagement_factors["novelty"] * 0.3
        
        # Add some randomness (attention fluctuates)
        score += random.uniform(-0.1, 0.1)
        
        return max(0.0, min(1.0, score))
    
    def _generate_meta_comment(self, thought: Dict[str, Any], score: float) -> str:
        """Generate meta-cognitive observation about the thought"""
        
        trigger = thought.get("trigger")
        
        if score >= 0.8:
            comments = [
                "This feels important",
                "Worth thinking about",
                "I want to explore this",
                "Something here...",
            ]
        elif score >= 0.6:
            comments = [
                "Interesting...",
                "Hm, maybe",
                "Could be something",
                "Let me consider this",
            ]
        elif score >= 0.4:
            comments = [
                "Not quite grabbing me",
                "Mild interest",
                "Aware but not pulled in",
            ]
        else:
            comments = [
                "Letting that pass by",
                "Not catching my attention",
                "Just mind wandering",
            ]
        
        return random.choice(comments)
    
    def _formulate_question(self, thought: Dict[str, Any]) -> str:
        """Turn thought into focused question for controlled reasoning"""
        
        topic = thought.get("topic", "this")
        
        questions = [
            f"What exactly is going on with {topic}?",
            f"Why does {topic} keep coming up?",
            f"What am I really wondering about {topic}?",
            f"How does {topic} fit into what I understand?",
        ]
        
        return random.choice(questions)
    
    def shift_to_focused(self, thought: Dict[str, Any]):
        """Shift from wandering to focused mode"""
        
        if self.state.mode != ThinkingMode.FOCUSED:
            self.state.mode = ThinkingMode.FOCUSED
            self.state.mode_shifts += 1
    
    def shift_to_wandering(self, reason: str):
        """Shift from focused back to wandering"""
        
        if self.state.mode != ThinkingMode.WANDERING:
            self.state.mode = ThinkingMode.WANDERING
            self.state.mode_shifts += 1
    
    def get_meta_state_summary(self) -> Dict[str, Any]:
        """Get summary of meta-awareness state"""
        
        total_thoughts = self.state.thoughts_noticed
        engagement_rate = (
            self.state.thoughts_engaged / total_thoughts 
            if total_thoughts > 0 else 0.0
        )
        
        return {
            "mode": self.state.mode.value,
            "awareness_level": self.state.awareness_level,
            "thoughts_noticed": self.state.thoughts_noticed,
            "thoughts_engaged": self.state.thoughts_engaged,
            "thoughts_dismissed": self.state.thoughts_dismissed,
            "engagement_rate": engagement_rate,
            "mode_shifts": self.state.mode_shifts,
        }
