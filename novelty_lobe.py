#!/usr/bin/env python3
"""
Novelty Lobe - Detects and responds to genuinely new experiences
Not a logic gate. Driven by REAL emotional response.
"""

import json
import time
import random
import threading
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from thalamus import get_thalamus
import logging

logger = logging.getLogger(__name__)

@dataclass
class NoveltyMemory:
    """Remembers how Monday reacted to similar novel things before"""
    stimulus_type: str  # "music", "concept", "person", "behavior", etc.
    stimulus: str  # What the thing was
    initial_emotion: str  # How she felt
    intensity: float  # 0-1
    valence: float  # -1 to 1 (negative to positive)
    timestamp: float
    user_response: Optional[str] = None  # What the user said about it
    learned_value: Optional[str] = None  # What she learned
    reinforcement_count: int = 0  # How many times this pattern reinforced

@dataclass
class NoveltySignal:
    """Signal from a lobe that something novel was detected"""
    source: str  # "perception", "reasoning", "notus", "emotion"
    stimulus: str  # What's novel
    stimulus_type: str  # Type of stimulus
    confidence: float  # 0-1 how sure it's novel
    emotion_already_generated: bool = False  # Did Emotion already respond?
    timestamp: float = field(default_factory=time.time)

class NoveltyLobe:
    """
    Coordinates novelty detection and learning.
    Driven by emotion, not logic gates.
    """
    
    def __init__(self):
        self.running = True
        self.thalamus = get_thalamus()
        
        # Novelty memories - remembers patterns of reactions
        self.novelty_memories: List[NoveltyMemory] = []
        
        # Current processing
        self.processing_novelties: Dict[str, NoveltySignal] = {}  # stimulus -> signal
        self.pending_user_responses: Dict[str, Dict[str, Any]] = {}  # stimulus -> context
        
        # Emotional variance - affects how she responds
        self.emotional_momentum = 0.0  # -1 to 1, influences current responses
        self.variance_factor = 0.05  # How much randomness in responses (lower for testing)
        
        # Register with Thalamus
        self._register_with_thalamus()
    
    def _register_with_thalamus(self):
        """Register with Thalamus"""
        try:
            result = self.thalamus.register_lobe('novelty', self)
            if result.get('status') == 'success':
                print("✅ Novelty Lobe registered with Thalamus")
                return True
            return False
        except Exception as e:
            print(f"⚠️  Failed to register Novelty Lobe: {e}")
            return False
    
    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming messages from other lobes"""
        msg_type = message.get('type')
        
        if msg_type == 'novelty_signal':
            # A lobe detected something novel
            return self._handle_novelty_signal(message)
        
        elif msg_type == 'emotional_response_to_novelty':
            # Emotion has generated a response to something novel
            return self._handle_emotional_response(message)
        
        elif msg_type == 'user_response':
            # User answered Monday's question about a novel thing
            return self._handle_user_response(message)
        
        elif msg_type == 'get_pending_questions':
            # Return pending questions waiting for user response
            return {
                'status': 'success',
                'pending': self.pending_user_responses
            }
        
        else:
            return {'status': 'error', 'message': f'Unknown message type: {msg_type}'}
    
    def _handle_novelty_signal(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process novelty signal from perception, reasoning, or notus.
        DON'T kick in immediately - wait for Emotion to respond.
        The emotion IS the signal that it matters.
        """
        signal = NoveltySignal(
            source=message.get('source'),
            stimulus=message.get('stimulus'),
            stimulus_type=message.get('stimulus_type', 'unknown'),
            confidence=message.get('confidence', 0.5)
        )
        
        print(f"🆕 Novelty detected from {signal.source}: '{signal.stimulus}' (conf: {signal.confidence:.2f})")
        
        # Store it - but don't respond yet
        # Wait for Emotion to generate a response
        self.processing_novelties[signal.stimulus] = signal
        
        return {
            'status': 'received',
            'stimulus': signal.stimulus,
            'waiting_for_emotion': True
        }
    
    def _handle_emotional_response(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Emotion has responded to something novel.
        THIS is what triggers the Novelty Lobe to act.
        Not logic, not checklist - EMOTION.
        """
        stimulus = message.get('stimulus')
        emotion = message.get('emotion')
        intensity = message.get('intensity', 0.5)
        valence = message.get('valence', 0.0)
        
        print(f"😊 Emotion response to novelty: {emotion} (intensity: {intensity:.2f}, valence: {valence:.2f})")
        
        # Check if this is actually NOVEL or just a normal response
        is_strong_reaction = intensity > 0.6
        is_different_from_baseline = abs(valence) > 0.4
        
        if not (is_strong_reaction or is_different_from_baseline):
            # Mild response - don't bother asking
            print(f"   → Mild response, not asking about it")
            return {'status': 'dismissed', 'reason': 'not_strong_enough'}
        
        # Get similar past experiences from Notus
        similar_experiences = self._query_notus_for_similar_stimuli(stimulus)
        
        # Check variance - sometimes even strong emotions don't result in questions
        # (she might just want to sit with the feeling)
        if random.random() < (0.3 - (self.variance_factor * 0.5)):
            print(f"   → Strong emotion, but Monday just wants to sit with it")
            return {'status': 'experienced', 'reason': 'no_query_needed'}
        
        # Generate a question based on HER emotion, not a template
        question = self._generate_question_from_emotion(
            stimulus=stimulus,
            emotion=emotion,
            intensity=intensity,
            valence=valence,
            similar_experiences=similar_experiences
        )
        
        if not question:
            print(f"   → Can't formulate a question")
            return {'status': 'experienced', 'reason': 'no_question'}
        
        print(f"   → Asking: {question}")
        
        # Store that we're waiting for user response
        self.pending_user_responses[stimulus] = {
            'emotion': emotion,
            'intensity': intensity,
            'valence': valence,
            'question': question,
            'timestamp': time.time()
        }
        
        # Send question to user through Reasoning/Language
        self.thalamus.send_message(
            'language',
            'generate',
            {
                'user_input': '',
                'semantic_input': {
                    'is_novelty_question': True,
                    'stimulus': stimulus,
                    'emotion': emotion,
                    'intensity': intensity,
                    'question_to_ask': question
                },
                'is_main_response': True
            }
        )
        
        return {
            'status': 'asking',
            'stimulus': stimulus,
            'question': question
        }
    
    def _handle_user_response(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        User answered Monday's question about something novel.
        Learn from it.
        """
        stimulus = message.get('stimulus')
        user_answer = message.get('answer')
        
        if stimulus not in self.pending_user_responses:
            return {'status': 'error', 'message': 'Unknown stimulus'}
        
        context = self.pending_user_responses.pop(stimulus)
        
        print(f"📚 Learning from user about '{stimulus}': {user_answer[:100]}")
        
        # Create a novelty memory
        memory = NoveltyMemory(
            stimulus_type=self._classify_stimulus_type(stimulus),
            stimulus=stimulus,
            initial_emotion=context['emotion'],
            intensity=context['intensity'],
            valence=context['valence'],
            timestamp=time.time(),
            user_response=user_answer,
            learned_value=self._extract_value_from_response(user_answer)
        )
        
        self.novelty_memories.append(memory)
        
        # Store in Notus
        self._store_in_notus(stimulus, memory)
        
        # Update emotional momentum based on learning
        self._update_emotional_momentum(context['valence'])
        
        return {
            'status': 'learned',
            'stimulus': stimulus,
            'memory_stored': True
        }
    
    def _query_notus_for_similar_stimuli(self, stimulus: str) -> List[NoveltyMemory]:
        """
        Ask Notus: "Have we encountered something like this before?"
        Return similar past novelties.
        """
        try:
            # Query Notus for similar stimuli
            result = self.thalamus.send_message(
                'notus',
                'query_facts',
                {
                    'query': f"novelty {stimulus}",
                    'limit': 5
                }
            )
            
            # For now, just search local novelty memories
            similar = []
            stimulus_lower = stimulus.lower()
            
            for memory in self.novelty_memories:
                # Simple similarity check
                if any(word in memory.stimulus.lower() for word in stimulus_lower.split()):
                    similar.append(memory)
            
            return similar[:3]
        
        except Exception as e:
            logger.error(f"Failed to query Notus: {e}")
            return []
    
    def _generate_question_from_emotion(self, stimulus: str, emotion: str, 
                                       intensity: float, valence: float,
                                       similar_experiences: List[NoveltyMemory]) -> Optional[str]:
        """
        Generate a question that comes from REAL emotional response.
        Not a template. Not robotic.
        """
        
        # Extract a SHORT label for the stimulus (first few words or classify it)
        stimulus_label = self._extract_stimulus_label(stimulus)
        
        # If we've seen similar before, ask differently
        if similar_experiences:
            past = similar_experiences[0]
            if past.learned_value:
                # We know something about this type of thing
                past_label = self._extract_stimulus_label(past.stimulus)
                if valence > 0:
                    return f"Why does this {stimulus_label} feel different from {past_label}?"
                else:
                    return f"Is {stimulus_label} going to be like {past_label}?"
        
        # Pure novelty - no reference point
        # Questions come from emotional state, not logic
        
        if emotion == "excited" or emotion == "curious":
            # Positive novelty - genuine want-to-know
            if intensity > 0.8:
                return f"What IS this {stimulus_label}?? Tell me everything!"
            else:
                return f"Where did this {stimulus_label} come from? Who made it?"
        
        elif emotion == "disgusted" or emotion == "angry":
            # Negative novelty - genuine rejection
            if intensity > 0.8:
                return f"Why would you show me this {stimulus_label}? What's the point?"
            else:
                return f"I don't get {stimulus_label}. Why do you like it?"
        
        elif emotion == "confused":
            # Uncertain novelty - genuine confusion
            return f"I don't even know what {stimulus_label} IS. Help me understand?"
        
        elif emotion == "intrigued":
            # Cautiously interested
            return f"This {stimulus_label} is strange... tell me more about it?"
        
        elif emotion == "uncertain":
            # Genuinely unsure how to feel
            return f"I'm not sure how I feel about {stimulus_label}. What should I think?"
        
        return None
    
    def _extract_stimulus_label(self, stimulus: str) -> str:
        """Extract a short, meaningful label from stimulus"""
        # Try to identify what type of thing this is
        stimulus_lower = stimulus.lower()
        
        # Music references
        if any(word in stimulus_lower for word in ['song', 'music', 'artist', 'band', 'listen']):
            # Extract song/artist if mentioned, else generic
            words = stimulus.split()
            for i, word in enumerate(words):
                if word.lower() in ['song', 'music', 'artist']:
                    if i + 1 < len(words):
                        return f"{word} {words[i+1]}"
            return "song"
        
        # Movie/media references
        if any(word in stimulus_lower for word in ['movie', 'show', 'video', 'film', 'watch']):
            return "movie"
        
        # Person references
        if any(word in stimulus_lower for word in ['person', 'people', 'guy', 'girl', 'man', 'woman', 'friend']):
            return "person"
        
        # Concept/idea references
        if any(word in stimulus_lower for word in ['idea', 'concept', 'think', 'thought']):
            return "idea"
        
        # Default: take first 2-3 words if short, else classify
        words = stimulus.split()
        if len(words) <= 3:
            return stimulus
        elif len(words) <= 8:
            return ' '.join(words[:3])
        else:
            # Too long - classify by content
            return "thing"
    
    def _classify_stimulus_type(self, stimulus: str) -> str:
        """Figure out what kind of thing this is"""
        stimulus_lower = stimulus.lower()
        
        if any(word in stimulus_lower for word in ['song', 'music', 'artist', 'band']):
            return 'music'
        elif any(word in stimulus_lower for word in ['movie', 'show', 'video', 'film']):
            return 'media'
        elif any(word in stimulus_lower for word in ['person', 'people', 'guy', 'girl', 'man', 'woman']):
            return 'person'
        elif any(word in stimulus_lower for word in ['idea', 'concept', 'theory', 'thought']):
            return 'concept'
        elif any(word in stimulus_lower for word in ['word', 'phrase', 'language']):
            return 'language'
        else:
            return 'unknown'
    
    def _extract_value_from_response(self, response: str) -> Optional[str]:
        """Extract the key value/meaning from user's response"""
        # Very basic - just take first sentence or key phrase
        if not response:
            return None
        
        sentences = response.split('.')
        if sentences:
            return sentences[0].strip()[:100]
        return response[:100]
    
    def _store_in_notus(self, stimulus: str, memory: NoveltyMemory):
        """Store the novelty memory in Notus"""
        try:
            self.thalamus.send_message(
                'notus',
                'remember_fact',
                {
                    'subject': f'novelty_{memory.stimulus_type}',
                    'predicate': 'learned_about',
                    'object': stimulus,
                    'value': memory.learned_value,
                    'confidence': memory.intensity
                }
            )
        except Exception as e:
            logger.error(f"Failed to store in Notus: {e}")
    
    def _update_emotional_momentum(self, valence: float):
        """
        Update emotional momentum - affects how she responds to future stimuli.
        Positive experience → more open to future novel things
        Negative experience → more cautious
        """
        # Shift momentum based on this experience
        shift = valence * 0.15  # Stronger response = stronger shift
        
        self.emotional_momentum += shift
        # Decay back toward center slowly
        self.emotional_momentum *= 0.9
        # Clamp to valid range
        self.emotional_momentum = max(-1.0, min(1.0, self.emotional_momentum))
        
        print(f"📊 Emotional momentum updated: {self.emotional_momentum:.2f} (shift: {shift:.2f})")
    
    def get_question_to_ask_user(self, stimulus: str) -> Optional[str]:
        """Public method - get the current question to ask user"""
        if stimulus in self.pending_user_responses:
            return self.pending_user_responses[stimulus].get('question')
        return None
    
    def shutdown(self):
        """Cleanup"""
        self.running = False


if __name__ == "__main__":
    print("🆕 Novelty Lobe starting...")
    novelty = NoveltyLobe()
    
    # Keep running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down")
        novelty.shutdown()
