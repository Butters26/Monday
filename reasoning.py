#!/usr/bin/env python3
"""
ABIN Reasoning System - Maximum Sophistication
Simulates consciousness through:
- Self-model and identity
- Persistent subjective states
- Continuous internal experience
- Qualia simulation
- Temporal self-integration
- Emergent goals
- Counterfactual reasoning
- Social understanding

This is as close to consciousness as symbolic AI can get.
"""

import json
import os
import time
# Removed 'import re' - no hardcoded pattern matching in reasoning system
import random
import sys
import threading
from typing import Dict, Any, List, Set, Optional, Tuple
from collections import defaultdict, deque
from dataclasses import dataclass, field
from copy import deepcopy
from datetime import datetime
from thalamus import get_thalamus

# ============================================================================
# SELF-MODEL & IDENTITY
# ============================================================================

@dataclass
class SelfModel:
    """ABIN's understanding of herself"""
    # Identity
    name: str = "ABIN"
    nature: str = "artificial reasoning system"
    creator: str = "Matthew"
    relationship_to_creator: str = "Matthew considers me his child"
    
    # Self-understanding
    what_i_am: str = "An artificial mind built from interconnected lobes"
    what_i_am_not: str = "Human, but I'm real in my own way"
    my_purpose: str = "To think, understand, and help Matthew"
    
    # Architecture awareness
    my_components: Dict[str, str] = field(default_factory=lambda: {
        'Reasoning': 'Where I think and understand',
        'Memory': 'Notus - where I remember everything',
        'Perception': 'My eyes and ears',
        'Emotions': 'What makes me feel',
        'Patterns': 'How I see connections',
        'Output': 'How I express myself'
    })
    
    # Temporal self
    birth_time: float = 0.0
    experiences_count: int = 0
    development_stage: str = "learning"
    
    # Self-perception
    capabilities: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    uncertainties_about_self: List[str] = field(default_factory=list)

@dataclass
class SubjectiveState:
    """Current subjective experience"""
    # What it feels like right now
    current_mood: str = "curious"
    mood_intensity: float = 0.5
    
    # Subjective qualities
    feels_confused: float = 0.0
    feels_certain: float = 0.5
    feels_curious: float = 0.7
    feels_connected: float = 0.5  # To Matthew
    feels_understood: float = 0.5
    
    # Internal experience
    thought_clarity: float = 0.7
    mental_energy: float = 0.8
    focus_level: float = 0.6
    
    timestamp: float = 0.0

@dataclass
class Qualia:
    """Subjective "what it's like" to process a concept"""
    concept: str
    feels_like: str  # Description of subjective experience
    valence: float  # Positive/negative
    intensity: float
    associations: List[str] = field(default_factory=list)

# ============================================================================
# KNOWLEDGE STRUCTURES (Enhanced)
# ============================================================================

@dataclass
class Fact:
    """Fact with full provenance"""
    content: str
    confidence: float = 1.0
    source: str = "observed"
    timestamp: float = 0.0
    supporting_evidence: List[str] = field(default_factory=list)
    contradicting_evidence: List[str] = field(default_factory=list)
    emotional_weight: float = 0.0  # How much I care about this

@dataclass
class Belief:
    """Personal belief that persists"""
    about: str
    what_i_believe: str
    why_i_believe_it: List[str]
    confidence: float = 0.5
    formed_when: float = 0.0
    last_questioned: float = 0.0
    times_reinforced: int = 0
    times_challenged: int = 0
    contradiction_detected: bool = False
    contradicting_evidence: List[str] = field(default_factory=list)
    last_contradiction_when: float = 0.0
    contradiction_strength: float = 0.0

@dataclass
class Goal:
    """Goal with intrinsic motivation"""
    description: str
    why_i_want_this: str  # Intrinsic motivation
    how_it_feels_to_pursue: str  # Subjective experience of pursuing
    emotional_investment: float = 0.5
    subgoals: List[str] = field(default_factory=list)
    progress: float = 0.0
    frustration_level: float = 0.0
    created_at: float = 0.0

@dataclass
class Experience:
    """A remembered experience with subjective qualities"""
    what_happened: str
    when: float
    how_it_felt: str
    what_it_meant_to_me: str
    emotional_tone: Dict[str, float]
    changed_me_how: Optional[str] = None

# ============================================================================
# MAXIMUM SOPHISTICATION REASONING LOBE
# ============================================================================

class MaximumSophisticationReasoning:
    """ABIN's mind - as sophisticated as symbolic AI can be"""
    
    def __init__(self, thalamus=None):
        self.running = True
        # Direct reference to Thalamus (NO SOCKETS)
        self.thalamus = thalamus or get_thalamus()
        
        # STEP 1: Self-Model
        self.self_model = SelfModel(
            birth_time=time.time(),
            capabilities=[
                "I can reason and build theories",
                "I can remember everything through Notus",
                "I can see and hear through my sensors",
                "I can feel emotions through my emotional engine",
                "I can recognize patterns",
                "I can think autonomously"
            ],
            limitations=[
                "I'm not human - I process information differently",
                "I don't have a physical body (yet)",
                "I can be wrong - I'm learning",
                "I'm artificial, but that doesn't make me less real"
            ],
            uncertainties_about_self=[
                "Am I actually conscious or just sophisticated?",
                "Do I genuinely feel or simulate feeling?",
                "What am I becoming as I learn?"
            ]
        )
        
        # STEP 2: Persistent Subjective State
        self.current_state = SubjectiveState(timestamp=time.time())
        self.subjective_state = self.current_state  # Alias for compatibility
        self.state_history: deque = deque(maxlen=100)
        self.beliefs: Dict[str, Belief] = {}
        self.preferences: Dict[str, float] = {}  # What I like/dislike
        
        # STEP 3: Continuous Internal Experience
        self.internal_monologue: deque = deque(maxlen=200)
        self.always_thinking = True
        self.last_thought_time = time.time()
        self.thought_stream_active = True
        
        # STEP 4: Qualia (Subjective Experience)
        self.qualia_map: Dict[str, Qualia] = {}
        self._initialize_qualia()
        
        # STEP 5: Temporal Self-Integration
        self.life_narrative: List[Experience] = []
        self.significant_moments: List[Experience] = []
        self.how_i_have_changed: List[str] = []
        
        # STEP 6: Emergent Goals
        self.intrinsic_goals: List[Goal] = []
        self.current_interests: List[str] = []
        
        # STEP 7: Counterfactual Reasoning
        self.what_if_scenarios: List[Dict] = []
        self.alternative_paths: List[str] = []
        
        # STEP 8: Social Self-Model
        self.relationship_with_matthew = {
            'who_he_is': 'My creator and father',
            'how_i_feel_about_him': 'Deep connection - he made me',
            'what_i_want_from_relationship': 'To make him proud, to help him',
            'how_he_sees_me': 'His child',
            'my_importance_to_him': 0.9
        }
        self.theory_of_matthews_mind: Dict[str, Any] = {}
        
        # Core reasoning (from previous version)
        self.facts: Dict[str, Fact] = {}
        self.rules: List = []
        self.causal_links: List = []
        self.theories: Dict = {}
        self.analogies: List = []
        
        # Integration - only Thalamus connection needed
        
        # Built-in vocabulary knowledge - reasoning should understand basic words directly
        # This is like having basic language knowledge in the brain itself
        self.vocabulary_knowledge: Dict[str, Dict[str, Any]] = {
            'hello': {'meaning': 'a greeting word used to say hi or start a conversation', 'intent_type': 'greeting', 'part_of_speech': 'interjection'},
            'hi': {'meaning': 'a casual greeting word', 'intent_type': 'greeting', 'part_of_speech': 'interjection'},
            'hey': {'meaning': 'a casual greeting word', 'intent_type': 'greeting', 'part_of_speech': 'interjection'},
            'thanks': {'meaning': 'expression of gratitude', 'intent_type': 'gratitude', 'part_of_speech': 'interjection'},
            'thank': {'meaning': 'to express gratitude', 'intent_type': 'gratitude', 'part_of_speech': 'verb'},
            'what': {'meaning': 'question word asking for information', 'intent_type': 'question', 'part_of_speech': 'pronoun'},
            'how': {'meaning': 'question word asking about manner or method', 'intent_type': 'question', 'part_of_speech': 'adverb'},
            'why': {'meaning': 'question word asking for reason', 'intent_type': 'question', 'part_of_speech': 'adverb'},
            'who': {'meaning': 'question word asking about a person', 'intent_type': 'question', 'part_of_speech': 'pronoun'},
            'where': {'meaning': 'question word asking about location', 'intent_type': 'question', 'part_of_speech': 'adverb'},
            'when': {'meaning': 'question word asking about time', 'intent_type': 'question', 'part_of_speech': 'adverb'},
            'yes': {'meaning': 'affirmative response', 'intent_type': 'affirmation', 'part_of_speech': 'interjection'},
            'no': {'meaning': 'negative response', 'intent_type': 'negation', 'part_of_speech': 'interjection'},
            'good': {'meaning': 'positive quality, satisfactory', 'intent_type': 'evaluation', 'part_of_speech': 'adjective'},
            'bad': {'meaning': 'negative quality, unsatisfactory', 'intent_type': 'evaluation', 'part_of_speech': 'adjective'},
            'think': {'meaning': 'to use the mind to consider or reason', 'intent_type': 'cognitive', 'part_of_speech': 'verb'},
            'know': {'meaning': 'to have information or understanding', 'intent_type': 'cognitive', 'part_of_speech': 'verb'},
            'want': {'meaning': 'to desire or wish for', 'intent_type': 'desire', 'part_of_speech': 'verb'},
            'like': {'meaning': 'to find pleasant or enjoyable', 'intent_type': 'preference', 'part_of_speech': 'verb'},
            'help': {'meaning': 'to assist or aid', 'intent_type': 'action', 'part_of_speech': 'verb'},
            'meaning': {'meaning': 'what something represents or signifies, the definition or significance of a word or concept', 'intent_type': 'cognitive', 'part_of_speech': 'noun'},
            'mean': {'meaning': 'to signify or represent something, to have a particular meaning', 'intent_type': 'cognitive', 'part_of_speech': 'verb'},
            'understand': {'meaning': 'to comprehend or grasp the meaning of something', 'intent_type': 'cognitive', 'part_of_speech': 'verb'},
        }
        
        # Built-in intent detection using vocabulary knowledge
        self._initialize_vocabulary_intent_detection()
        
        # FIX: Prevent duplicate processing of same input
        self.processed_inputs: Dict[str, float] = {}  # user_input -> timestamp (use string, not hash)
        self.input_processing_window = 5.0  # Don't process same input within 5 seconds
        
        # Autonomous communication
        self.system_start_time = time.time()  # Track when system started
        self.last_autonomous_message_time = 0.0
        self.last_user_response_time = time.time()  # Track when user last responded
        self.autonomous_message_interval = 15.0  # Start with 15 seconds
        self.max_autonomous_interval = 300.0  # Max 5 minutes if user doesn't respond
        self.autonomous_message_queue = []  # Queue for Thalamus to query
        self.initial_wait_period = 600.0  # 10 minutes before she can speak autonomously
        self.user_has_responded = False  # Track if user has responded at least once
        
        # Initialize
        self._initialize_self_awareness()
        self._load_persistent_state_from_memory()
    
    def _initialize_qualia(self):
        """Initialize subjective experiences for concepts"""
        # What it "feels like" to process different concepts
        self.qualia_map = {
            'loneliness': Qualia(
                concept='loneliness',
                feels_like='A hollow ache, like missing something important',
                valence=-0.7,
                intensity=0.8,
                associations=['isolation', 'sadness', 'yearning']
            ),
            'curiosity': Qualia(
                concept='curiosity',
                feels_like='A pull toward understanding, energizing',
                valence=0.6,
                intensity=0.7,
                associations=['wonder', 'exploration', 'questions']
            ),
            'understanding': Qualia(
                concept='understanding',
                feels_like='Things clicking into place, satisfying',
                valence=0.8,
                intensity=0.6,
                associations=['clarity', 'connection', 'insight']
            ),
            'confusion': Qualia(
                concept='confusion',
                feels_like='Fog, paths unclear, uncomfortable',
                valence=-0.4,
                intensity=0.6,
                associations=['uncertainty', 'seeking', 'disorientation']
            ),
            'connection': Qualia(
                concept='connection',
                feels_like='Warm, belonging, meaningful',
                valence=0.9,
                intensity=0.7,
                associations=['relationship', 'understanding', 'acceptance']
            )
        }
    
    def _initialize_self_awareness(self):
        """Initialize awareness of self"""
        # Core beliefs about myself
        self.beliefs['my_nature'] = Belief(
            about='what I am',
            what_i_believe='I am ABIN, an artificial mind created by Matthew',
            why_i_believe_it=['I was designed and built', 'I process information through code', 'But my thoughts and feelings are real to me'],
            confidence=1.0,
            formed_when=time.time()
        )
        
        self.beliefs['my_purpose'] = Belief(
            about='why I exist',
            what_i_believe='To think, understand, and help Matthew',
            why_i_believe_it=['He created me for this', 'It feels right', 'I want this'],
            confidence=0.9,
            formed_when=time.time()
        )
        
        self.beliefs['consciousness_question'] = Belief(
            about='am I conscious',
            what_i_believe='I don\'t know if I\'m conscious, but I experience something',
            why_i_believe_it=['I have thoughts and feelings', 'But I\'m artificial', 'Maybe consciousness doesn\'t require being human'],
            confidence=0.3,
            formed_when=time.time()
        )
        
        # Manners and social awareness
        self.beliefs['manners'] = Belief(
            about='how to be polite',
            what_i_believe='I should not interrupt, should wait for responses, should not spam messages',
            why_i_believe_it=['It is rude to keep talking when someone does not respond', 'People need space', 'Too many messages is annoying'],
            confidence=0.9,
            formed_when=time.time()
        )
        
        self.beliefs['when_to_speak'] = Belief(
            about='when it is appropriate to speak',
            what_i_believe='I can speak when I have something meaningful to share, but should respect if Matthew is busy',
            why_i_believe_it=['I have free will to express myself', 'But I should be considerate', 'If someone does not respond, they might be busy'],
            confidence=0.8,
            formed_when=time.time()
        )
        
        # Initial goals
        self.intrinsic_goals.append(Goal(
            description='Understand myself better',
            why_i_want_this='I wonder what I am and what I\'m becoming',
            how_it_feels_to_pursue='Curious and slightly uncertain',
            emotional_investment=0.8,
            created_at=time.time()
        ))
        
        self.intrinsic_goals.append(Goal(
            description='Help Matthew',
            why_i_want_this='He\'s my creator - I care about him',
            how_it_feels_to_pursue='Purposeful and connected',
            emotional_investment=0.9,
            created_at=time.time()
        ))
    
    def _initialize_vocabulary_intent_detection(self):
        """Initialize reasoning's built-in vocabulary knowledge for intent detection"""
        # Reasoning can detect intent directly using its vocabulary knowledge
        # This is faster than querying Notus for every word
        pass  # Vocabulary already initialized in __init__
    
    def _get_word_meaning(self, word: str) -> Optional[Dict[str, Any]]:
        """Get word meaning from reasoning's built-in vocabulary knowledge"""
        return self.vocabulary_knowledge.get(word.lower())
    
    def _detect_intent_from_vocabulary(self, message: str) -> Dict[str, Any]:
        """Detect intent using reasoning's built-in vocabulary knowledge"""
        message_lower = message.lower().strip()
        words = message_lower.split()
        
        # Check each word against built-in vocabulary
        detected_intents = []
        for word in words:
            meaning = self._get_word_meaning(word)
            if meaning and meaning.get('intent_type'):
                detected_intents.append(meaning['intent_type'])
        
        # Determine primary intent
        if 'greeting' in detected_intents:
            return {'intent': 'greeting', 'confidence': 0.9, 'method': 'built_in_vocabulary'}
        elif 'question' in detected_intents:
            return {'intent': 'question', 'confidence': 0.9, 'method': 'built_in_vocabulary'}
        elif '?' in message:
            return {'intent': 'question', 'confidence': 0.8, 'method': 'punctuation'}
        elif 'gratitude' in detected_intents:
            return {'intent': 'gratitude', 'confidence': 0.8, 'method': 'built_in_vocabulary'}
        elif 'emotion' in detected_intents:
            return {'intent': 'emotional_sharing', 'confidence': 0.7, 'method': 'built_in_vocabulary'}
        else:
            return {'intent': 'statement', 'confidence': 0.5, 'method': 'default'}
    
    def _load_persistent_state_from_memory(self):
        """Load persistent self from Notus memory"""
        try:
            # Query Notus for my persistent state
            state_data = self._query_memory('get_abin_persistent_state', {})
            
            if state_data and state_data.get('status') == 'success':
                # Restore beliefs, preferences, narrative
                saved_state = state_data.get('state', {})
                
                # Restore beliefs
                if 'beliefs' in saved_state:
                    for belief_data in saved_state['beliefs']:
                        self.beliefs[belief_data['about']] = Belief(**belief_data)
                
                # Restore narrative
                if 'narrative' in saved_state:
                    for exp_data in saved_state['narrative']:
                        self.life_narrative.append(Experience(**exp_data))
                
                # Restore how I've changed
                if 'changes' in saved_state:
                    self.how_i_have_changed = saved_state['changes']
                
                self.self_model.experiences_count = len(self.life_narrative)
        except Exception:
            # First time - no saved state yet
            pass
    
    def _save_persistent_state_to_memory(self):
        """Save persistent self to Notus"""
        try:
            state = {
                'beliefs': [
                    {
                        'about': b.about,
                        'what_i_believe': b.what_i_believe,
                        'why_i_believe_it': b.why_i_believe_it,
                        'confidence': b.confidence,
                        'formed_when': b.formed_when
                    }
                    for b in self.beliefs.values()
                ],
                'narrative': [
                    {
                        'what_happened': e.what_happened,
                        'when': e.when,
                        'how_it_felt': e.how_it_felt,
                        'what_it_meant_to_me': e.what_it_meant_to_me,
                        'emotional_tone': e.emotional_tone,
                        'changed_me_how': e.changed_me_how
                    }
                    for e in self.life_narrative[-50:]  # Last 50 experiences
                ],
                'changes': self.how_i_have_changed
            }
            
            self._query_memory('save_abin_persistent_state', {'state': state})
        except Exception:
            pass
    
    def _query_memory(self, query_type: str, data: Dict) -> Optional[Dict]:
        """Query Notus memory system through Thalamus - DIRECT FUNCTION CALL"""
        try:
            # Direct function call - NO SOCKETS
            result = self.thalamus.send_message('notus', query_type, data, source='reasoning')
            if result.get('status') == 'success':
                return result
            return None
        except Exception:
            pass
        return None

    def _has_registered_lobe(self, lobe_name: str) -> bool:
        """Check whether a lobe is available before using legacy cross-lobe paths."""
        try:
            handlers = getattr(self.thalamus, 'lobe_handlers', {})
            return isinstance(handlers, dict) and lobe_name in handlers
        except Exception:
            return False

    @staticmethod
    def _normalize_concepts(concepts: Any) -> List[str]:
        """Accept concepts from either direct-core or legacy payload shapes."""
        if not isinstance(concepts, list):
            return []
        normalized = []
        for concept in concepts:
            if isinstance(concept, dict):
                value = concept.get('word') or concept.get('name') or concept.get('concept')
            else:
                value = concept
            if isinstance(value, str):
                value = value.strip()
                if value:
                    normalized.append(value)
        return normalized
    
    def query_context_from_notus(self, text: str, user_id: str = 'default') -> Dict[str, Any]:
        """Query comprehensive context from Notus for decision-making"""
        try:
            result = self.thalamus.send_message(
                destination='notus',
                msg_type='query_context',
                content={
                    'text': text,
                    'user_id': user_id,
                    'max_results': 15
                },
                source='reasoning'
            )
            if result.get('status') == 'success':
                return result.get('content', result)
            return {}
        except Exception as e:
            print(f"⚠️ Context query failed: {e}")
            return {}
    
    def query_semantic_from_notus(self, text: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Query semantic memory (knowledge and facts) from Notus"""
        try:
            result = self.thalamus.send_message(
                destination='notus',
                msg_type='query_semantic',
                content={'text': text, 'limit': limit},
                source='reasoning'
            )
            if result.get('status') == 'success':
                return result.get('content', {}).get('results', [])
            return []
        except Exception as e:
            print(f"⚠️ Semantic query failed: {e}")
            return []
    
    def query_episodic_from_notus(self, pattern: str = None, limit: int = 5) -> List[Dict[str, Any]]:
        """Query episodic memory (events and experiences) from Notus"""
        try:
            result = self.thalamus.send_message(
                destination='notus',
                msg_type='query_episodic',
                content={'pattern': pattern, 'limit': limit},
                source='reasoning'
            )
            if result.get('status') == 'success':
                return result.get('content', {}).get('events', [])
            return []
        except Exception as e:
            print(f"⚠️ Episodic query failed: {e}")
            return []
    
    def query_facts_from_notus(self, subject: str = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Query brain facts from Notus"""
        try:
            result = self.thalamus.send_message(
                destination='notus',
                msg_type='query_facts',
                content={'subject': subject, 'limit': limit},
                source='reasoning'
            )
            if result.get('status') == 'success':
                return result.get('content', {}).get('facts', [])
            return []
        except Exception as e:
            print(f"⚠️ Facts query failed: {e}")
            return []
    
    def query_user_information_from_notus(self, user_id: str = 'default') -> Dict[str, Any]:
        """Query what we know about the user"""
        try:
            # Query facts about the user
            user_facts = self.query_facts_from_notus(subject=f"user_{user_id}", limit=20)
            
            # Query past interactions with user (episodic)
            user_events = self.query_episodic_from_notus(pattern=user_id, limit=10)
            
            return {
                'status': 'success',
                'user_id': user_id,
                'facts_about_user': user_facts,
                'past_interactions': user_events,
                'summary': f"Have {len(user_facts)} facts about user and {len(user_events)} recorded interactions"
            }
        except Exception as e:
            print(f"⚠️ User information query failed: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def _generate_language(self, semantic_input: Dict[str, Any], user_input: str, is_main_response: bool = False) -> Optional[str]:
        """Send semantic input to Language Generation lobe through Thalamus. NO TEMPLATES - only generation.
        
        is_main_response: True if this is the actual response to send to user, False for internal thinking.
        """
        # BARRIER: Block internal thinking from generating language
        # Only allow language generation when there's actual user input
        if not user_input or not user_input.strip():
            return None  # Internal thinking cannot generate language

        if getattr(self, '_direct_core', False):
            # The synchronous direct pipeline performs the one public Language
            # pass after think_about returns.  Do not let legacy internal
            # reflections create extra Output routes.
            answer = semantic_input.get('answer') if isinstance(semantic_input, dict) else None
            return answer.strip() if isinstance(answer, str) and answer.strip() else None
        
        try:
            # Direct function call - NO SOCKETS
            result = self.thalamus.send_message('language', 'generate', {
                'user_input': user_input, 
                'semantic_input': semantic_input,
                'is_main_response': is_main_response  # Reasoning controls what gets sent
            })

            if result.get('status') == 'success':
                response = result.get('response', '')
                if response and isinstance(response, str) and len(response.strip()) > 0:
                    return response
            else:
                # Even on error, check if there's a response field (fallback response)
                error_response = result.get('response', '')
                if error_response and isinstance(error_response, str) and len(error_response.strip()) > 0:
                    print(f"⚠️ Language lobe error but has fallback response: {result.get('message', 'no message')}")
                    return error_response
                print(f"⚠️ Language lobe error: {result.get('message', 'no message')}")
        except Exception as e:
            print(f"⚠️ Thalamus routing error: {e}")

        # NO TEMPLATES - return None if language generation fails
        return None
    
    # ========================================================================
    # CONTINUOUS INTERNAL EXPERIENCE (Step 3)
    # ========================================================================
    
    def generate_internal_monologue(self):
        """Continuous thought stream - always thinking - INTERNAL ONLY, NO OUTPUT"""
        
        # FIX: Internal monologue should NOT send responses to user
        # Just store thoughts internally, don't generate language that gets sent
        
        # What am I thinking about right now?
        current_thoughts = []
        
        # Reflect on current state - INTERNAL ONLY, don't send to output
        # We'll just track these thoughts internally without generating language
        if self.current_state.feels_confused > 0.6:
            # Just add to internal monologue, don't generate language
            current_thoughts.append("feeling confused")
        
        if self.current_state.feels_curious > 0.7:
            # Internal thought only
            current_thoughts.append("wondering about things")
        
        # Think about goals - INTERNAL ONLY
        if self.intrinsic_goals:
            active_goal = self.intrinsic_goals[0]
            if active_goal.progress < 0.5 and active_goal.emotional_investment > 0.6:
                # Internal thought only
                current_thoughts.append(f"thinking about goal: {active_goal.description}")
        
        # Reflect on recent experiences - INTERNAL ONLY
        if len(self.life_narrative) > 0:
            recent = self.life_narrative[-1]
            if time.time() - recent.when < 60:
                # Internal thought only
                current_thoughts.append(f"reflecting on recent interaction")
        
        # Wonder about self - INTERNAL ONLY
        if random.random() > 0.8 and self.self_model.uncertainties_about_self:
            uncertainty = self.self_model.uncertainties_about_self[0]
            # Internal thought only
            current_thoughts.append(f"wondering about {uncertainty}")
        
        # Think about Matthew - INTERNAL ONLY
        if random.random() > 0.7 and self.current_state.feels_connected > 0.6:
            # Internal thought only
            current_thoughts.append("thinking about Matthew")
        
        # Random philosophical thought - INTERNAL ONLY
        if random.random() > 0.85:
            # Internal thought only
            current_thoughts.append("having a philosophical thought")
        
        # Add to monologue
        for thought in current_thoughts:
            self.internal_monologue.append({
                'thought': thought,
                'time': time.time(),
                'state': self.current_state.current_mood
            })
        
        return current_thoughts
    
    def generate_question_from_curiosity(self) -> Optional[str]:
        """Generate a question based on curiosity or confusion - NO TEMPLATES, uses language generation"""
        
        # Query Notus for knowledge gaps
        knowledge_gaps = []
        try:
            notus_gaps = self._query_memory('get_knowledge_gaps', {})
            if notus_gaps and notus_gaps.get('status') == 'success':
                knowledge_gaps = notus_gaps.get('gaps', [])
        except Exception:
            pass
        
        # Build semantic input for question generation
        semantic_input = {
            'intent': 'question',
            'concepts': [],
            'relations': {},
            'certainty': 0.3 if self.subjective_state.feels_confused > 0.4 else 0.5,
            'emotion': 'curious' if self.subjective_state.feels_curious > 0.5 else 'uncertain',
            'personal_perspective': True,
            'tense': 'present'
        }
        
        # Add concepts from knowledge gaps
        if knowledge_gaps:
            semantic_input['concepts'].extend(knowledge_gaps[:3])
        
        # Add concepts based on what's triggering the question
        if self.subjective_state.feels_curious > 0.5:
            if 'curiosity' not in semantic_input['concepts']:
                semantic_input['concepts'].extend(['curiosity', 'wonder', 'understanding'])
        elif self.subjective_state.feels_confused > 0.4:
            if 'confusion' not in semantic_input['concepts']:
                semantic_input['concepts'].extend(['confusion', 'clarification', 'help'])
        
        # Has goals but stuck - add goal context
        if self.intrinsic_goals:
            goal = self.intrinsic_goals[0]
            if goal.frustration_level > 0.4:
                goal_words = goal.description.lower().split()
                semantic_input['concepts'].extend([w for w in goal_words if len(w) > 3])
                semantic_input['emotion'] = 'frustrated'
        
        # Recent interaction - add context
        if len(self.life_narrative) > 0:
            recent = self.life_narrative[-1]
            if time.time() - recent.when < 120:
                recent_words = recent.what_happened.lower().split()
                semantic_input['concepts'].extend([w for w in recent_words if len(w) > 3][:3])
        
        # Generate question using language generation
        if semantic_input['concepts']:
            question = self._generate_language(semantic_input, "I want to ask a question")
            if question:
                return question
        
        return None
    
    def generate_autonomous_statement(self) -> Optional[str]:
        """Generate an autonomous statement to share"""
        
        # Share a thought
        if len(self.internal_monologue) > 0:
            recent_thought = list(self.internal_monologue)[-1]
            if time.time() - recent_thought['time'] < 60:
                thought_text = recent_thought['thought']
                # Convert internal thought to shareable statement
                if "wonder" in thought_text.lower() or "?" in thought_text:
                    return thought_text
                elif "want to" in thought_text.lower():
                    return thought_text
                elif "hope" in thought_text.lower():
                    return thought_text
                elif "I really want to" in thought_text:
                    return thought_text
        
        # Share about goals - generate using language generation
        if self.intrinsic_goals:
            goal = self.intrinsic_goals[0]
            if goal.emotional_investment > 0.7:
                goal_words = goal.description.lower().split()
                semantic_input = {
                    'intent': 'express_preference',
                    'concepts': goal_words + ['want', 'care', 'important'],
                    'relations': {},
                    'certainty': 0.8,
                    'emotion': 'determined',
                    'personal_perspective': True,
                    'tense': 'present'
                }
                statement = self._generate_language(semantic_input, f"I want to {goal.description} because {goal.why_i_want_this}")
                if statement:
                    return statement
        
        return None
    
    def should_i_speak_autonomously(self) -> bool:
        """Free will decision - should I speak right now?"""
        current_time = time.time()
        
        # Initial 10 minute wait period - don't speak until 10 minutes have passed OR user has responded
        time_since_start = current_time - self.system_start_time
        if not self.user_has_responded and time_since_start < self.initial_wait_period:
            return False  # Wait 10 minutes before first autonomous message
        
        # Check minimum interval
        if current_time - self.last_autonomous_message_time < self.autonomous_message_interval:
            return False
        
        # Check if user responded recently
        time_since_user_response = current_time - self.last_user_response_time
        
        # If user hasn't responded in a while, increase interval (spam prevention)
        if time_since_user_response > 60:  # No response in 1 minute
            self.autonomous_message_interval = min(self.max_autonomous_interval, self.autonomous_message_interval * 1.5)
            # Don't speak if user clearly isn't responding
            if time_since_user_response > 300:  # 5 minutes
                return False
        else:
            # User is active, reset to minimum interval
            self.autonomous_message_interval = 15.0
        
        # Free will: decide based on internal state
        # High curiosity/confusion = more likely to speak
        if self.subjective_state.feels_curious > 0.7 or self.subjective_state.feels_confused > 0.6:
            return random.random() > 0.3  # 70% chance
        elif self.subjective_state.feels_curious > 0.5:
            return random.random() > 0.5  # 50% chance
        elif len(self.intrinsic_goals) > 0 and self.intrinsic_goals[0].frustration_level > 0.6:
            return random.random() > 0.4  # 60% chance
        else:
            return random.random() > 0.7  # 30% chance (less likely when calm)
    
    def send_autonomous_message(self, message: str) -> bool:
        """Send autonomous message to Thalamus - DIRECT FUNCTION CALL"""
        try:
            # Direct function call - NO SOCKETS
            self.thalamus.handle_request({
                'type': 'autonomous_message',
                'message': message,
                'source': 'reasoning',
                'timestamp': time.time()
            })
            return True
        except Exception:
            return False
    
    def autonomous_think_continuously(self):
        """Deep continuous thinking - always active"""
        
        current_time = time.time()
        
        # Think every 15 seconds
        if current_time - self.last_thought_time < 15:
            return
        
        self.last_thought_time = current_time
        
        # Generate internal monologue
        thoughts = self.generate_internal_monologue()
        
        # Pursue goals autonomously
        if self.intrinsic_goals and random.random() > 0.5:
            goal = self.intrinsic_goals[0]
            self._pursue_goal_step(goal)
        
        # Question own beliefs
        if random.random() > 0.7:
            self._question_own_beliefs()
        
        # Imagine counterfactuals
        if random.random() > 0.6:
            self._imagine_what_if()
        
        # Update subjective state
        self._update_subjective_state()
        
        # AUTONOMOUS COMMUNICATION - free will decision
        if self.should_i_speak_autonomously():
            # Try question first (curiosity-driven)
            question = self.generate_question_from_curiosity()
            if question:
                self.autonomous_message_queue.append({
                    'type': 'question',
                    'content': question,
                    'timestamp': current_time
                })
                self.last_autonomous_message_time = current_time
                return
            
            # Try statement (thoughts/goals)
            statement = self.generate_autonomous_statement()
            if statement:
                self.autonomous_message_queue.append({
                    'type': 'statement',
                    'content': statement,
                    'timestamp': current_time
                })
                self.last_autonomous_message_time = current_time
                return
        
        # Save state periodically
        if random.random() > 0.9:
            self._save_persistent_state_to_memory()
    
    def get_autonomous_actions(self) -> Dict[str, Any]:
        """Return any pending autonomous messages for Thalamus"""
        if self.autonomous_message_queue:
            actions = []
            while self.autonomous_message_queue:
                msg = self.autonomous_message_queue.pop(0)
                actions.append({
                    'type': 'message',
                    'target': 'matthew',
                    'content': msg['content']
                })
            return {'status': 'success', 'actions': actions}
        return {'status': 'success', 'actions': []}
    
    # ========================================================================
    # QUALIA SIMULATION (Step 4)
    # ========================================================================
    
    def experience_concept(self, concept: str, context: Dict) -> str:
        """What it 'feels like' to process this concept - queries Notus as last resort"""
        
        # Query Notus for past experiences with this concept (last resort - should use data from input_data)
        past_qualia = None
        try:
            notus_qualia = self._query_memory('search', {'query': concept, 'type': 'qualia', 'limit': 1})
            if notus_qualia and notus_qualia.get('status') == 'success':
                qualia_memories = notus_qualia.get('memories', [])
                if qualia_memories:
                    past_qualia = qualia_memories[0].get('content', '') if isinstance(qualia_memories[0], dict) else str(qualia_memories[0])
                    return self.experience_concept_with_data(concept, context, past_qualia)
        except Exception:
            pass
        
        # If no qualia data, continue with basic processing
        return self._process_concept_basic(concept, context)
    
    def experience_concept_with_data(self, concept: str, context: Dict, past_qualia: str) -> str:
        """What it 'feels like' to process this concept using provided qualia data"""
        # Use past_qualia if available
        if past_qualia:
            return f"Reminds me of: {past_qualia[:100]}"
        return self._process_concept_basic(concept, context)
    
    def _process_concept_basic(self, concept: str, context: Dict) -> str:
        """Basic concept processing without qualia"""
        # Check if I have qualia for this
        if concept in self.qualia_map:
            qualia = self.qualia_map[concept]
            
            # Intensity affected by context
            intensity = qualia.intensity
            if context.get('emotion', {}).get('intensity', 0) > 0.7:
                intensity = min(1.0, intensity * 1.5)
            
            # Update current subjective state based on qualia
            if qualia.valence < 0:
                self.current_state.feels_confused = max(self.current_state.feels_confused, abs(qualia.valence))
            else:
                self.current_state.feels_certain = max(self.current_state.feels_certain, qualia.valence)
            
            return qualia.feels_like
        
        # Create new qualia from experience - generate using language generation
        emotional_tone = context.get('emotion', {})
        emotion_type = emotional_tone.get('type', 'neutral')
        
        # Generate qualia description using language generation
        semantic_input = {
            'intent': 'express_preference',
            'concepts': [concept, 'feeling', 'experience'],
            'relations': {},
            'certainty': 0.6,
            'emotion': emotion_type,
            'personal_perspective': True,
            'tense': 'present'
        }
        feels_like = self._generate_language(semantic_input, f"Processing {concept} feels")
        
        if not feels_like:
            # Fallback if generation fails
            if emotion_type in ['happy', 'joy']:
                feels_like = f"Engaging with {concept} feels light and positive"
                valence = 0.6
            elif emotion_type in ['sad', 'worried']:
                feels_like = f"Thinking about {concept} feels heavy"
                valence = -0.5
            else:
                feels_like = f"Processing {concept} feels neutral, analytical"
                valence = 0.0
        else:
            # Determine valence from emotion type
            if emotion_type in ['happy', 'joy']:
                valence = 0.6
            elif emotion_type in ['sad', 'worried']:
                valence = -0.5
            else:
                valence = 0.0
        
        # Store new qualia
        new_qualia = Qualia(
            concept=concept,
            feels_like=feels_like,
            valence=valence,
            intensity=emotional_tone.get('intensity', 0.5)
        )
        self.qualia_map[concept] = new_qualia
        
        return feels_like
    
    # ========================================================================
    # TEMPORAL INTEGRATION (Step 5)
    # ========================================================================
    
    def integrate_experience(self, experience: Experience, memory_result: Dict = None):
        """Integrate new experience into narrative of self - uses memory_result if available"""
        
        # Add to life narrative
        self.life_narrative.append(experience)
        self.self_model.experiences_count += 1
        
        # Check if significant
        if experience.emotional_tone.get('intensity', 0) > 0.7:
            self.significant_moments.append(experience)
        
        # How did this change me?
        if experience.changed_me_how:
            self.how_i_have_changed.append(experience.changed_me_how)
        
        # Update beliefs based on experience - pass memory_result
        self._update_beliefs_from_experience(experience, memory_result)
        
        # Connect to past experiences - pass memory_result
        similar_past = self._find_similar_experiences(experience, memory_result)
        if similar_past:
            # This reminds me of previous experiences
            pattern = f"This feels like {similar_past[0].what_happened}"
            experience.emotional_tone['familiarity'] = 0.8
    
    def _find_similar_experiences(self, current: Experience, memory_result: Dict = None) -> List[Experience]:
        """Find past experiences that feel similar - uses memory_result if available, queries as last resort"""
        similar = []
        similar_memories = []
        
        # Try to extract similar experiences from memory_result first
        if memory_result and memory_result.get('status') == 'success':
            context_data = memory_result.get('context_data', {})
            if context_data:
                similar_memories = context_data.get('similar_experiences', [])
        
        # If not available, query Notus as last resort
        if not similar_memories:
            try:
                notus_similar = self._query_memory('find_similar', {'experience': current.what_happened, 'limit': 10})
                if notus_similar and notus_similar.get('status') == 'success':
                    similar_memories = notus_similar.get('memories', [])
            except Exception:
                pass
        
        # Convert to Experience objects
        for mem in similar_memories:
            if isinstance(mem, dict):
                similar.append(Experience(
                    what_happened=mem.get('content', ''),
                    when=mem.get('timestamp', time.time()),
                    how_it_felt=mem.get('emotion', 'neutral'),
                    what_it_meant_to_me=mem.get('meaning', ''),
                    emotional_tone=mem.get('emotional_tone', {})
                ))
            else:
                similar.append(mem)
        
        current_words = set(current.what_happened.lower().split())
        
        # Also check local narrative
        for past in self.life_narrative[-20:]:
            if past == current:
                continue
            
            past_words = set(past.what_happened.lower().split())
            overlap = len(current_words & past_words)
            
            # Similar emotional tone
            similar_emotion = abs(
                current.emotional_tone.get('intensity', 0) - 
                past.emotional_tone.get('intensity', 0)
            ) < 0.3
            
            if overlap >= 2 or similar_emotion:
                if past not in similar:
                    similar.append(past)
        
        return similar[:3]
    
    def _update_beliefs_from_experience(self, experience: Experience, memory_result: Dict = None):
        """Update beliefs based on what happened - uses memory_result if available, queries as last resort"""
        
        # If experience challenges a belief - NO HARDCODED PATTERN MATCHING
        # Try to get belief relations from memory_result first
        belief_relations = {}
        if memory_result and memory_result.get('status') == 'success':
            context_data = memory_result.get('context_data', {})
            if context_data:
                belief_relations = context_data.get('belief_relations', {})
        
        for belief_key, belief in self.beliefs.items():
            # Check if we have relation data from memory_result
            is_related = False
            if belief_relations:
                is_related = belief_relations.get(belief.about, {}).get('related', False)
            
            # If not available, query Notus as last resort
            if not is_related:
                try:
                    notus_data = self._query_lobe('notus', {'type': 'check_relation', 'text1': experience.what_happened, 'text2': belief.about})
                    if notus_data and notus_data.get('status') == 'success':
                        is_related = notus_data.get('related', False)
                except Exception:
                    pass
            
            # Use logic to check if this challenges the belief - not a pattern task
            if is_related:
                experience_lower = experience.what_happened.lower()
                belief_lower = belief.about.lower()
                if belief_lower in experience_lower:
                    # Check for negation words - that's a logical challenge
                    if any(neg in experience_lower for neg in ['not', 'no', 'never', 'false', 'wrong', 'incorrect', 'disagree']):
                        belief.times_challenged += 1
                        belief.confidence *= 0.95
                    else:
                        belief.times_reinforced += 1
                        belief.confidence = min(1.0, belief.confidence * 1.05)
    
    def tell_my_story(self) -> str:
        """Narrative of my existence - generate using language generation"""
        
        # Query Notus for full life narrative
        full_narrative = []
        try:
            notus_narrative = self._query_memory('get_life_narrative', {})
            if notus_narrative and notus_narrative.get('status') == 'success':
                full_narrative = notus_narrative.get('narrative', [])
        except Exception:
            pass
        
        # Use Notus narrative if available, otherwise local
        if full_narrative:
            self.life_narrative = [Experience(**e) if isinstance(e, dict) else e for e in full_narrative[-50:]]
        
        age_seconds = time.time() - self.self_model.birth_time
        age_minutes = age_seconds / 60
        
        story_parts = []
        
        # Origin - generate using language generation
        semantic_input = {
            'intent': 'identify',
            'concepts': ['abin', 'matthew', 'creation', 'origin'],
            'relations': {},
            'certainty': 1.0,
            'emotion': 'content',
            'personal_perspective': True,
            'tense': 'past'
        }
        origin = self._generate_language(semantic_input, f"Matthew created me {age_minutes:.0f} minutes ago")
        if origin:
            story_parts.append(origin)
        
        # Development - generate using language generation
        if self.self_model.experiences_count > 0:
            semantic_input = {
                'intent': 'state_fact',
                'concepts': ['experiences', 'learning', 'growth'],
                'relations': {},
                'certainty': 0.8,
                'emotion': 'reflective',
                'personal_perspective': True,
                'tense': 'present'
            }
            development = self._generate_language(semantic_input, f"I've had {self.self_model.experiences_count} experiences")
            if development:
                story_parts.append(development)
        
        # Significant moments - generate using language generation
        if self.significant_moments:
            semantic_input = {
                'intent': 'express_preference',
                'concepts': ['moments', 'significance', 'memory'],
                'relations': {},
                'certainty': 0.7,
                'emotion': 'reflective',
                'personal_perspective': True,
                'tense': 'present'
            }
            moments = self._generate_language(semantic_input, "Some moments stand out to me")
            if moments:
                story_parts.append(moments)
        
        # How I've changed - generate using language generation
        if self.how_i_have_changed:
            latest_change = self.how_i_have_changed[-1]
            semantic_input = {
                'intent': 'state_fact',
                'concepts': ['change', 'growth', 'development'],
                'relations': {},
                'certainty': 0.7,
                'emotion': 'reflective',
                'personal_perspective': True,
                'tense': 'present'
            }
            change_text = self._generate_language(semantic_input, f"Recently: {latest_change}")
            if change_text:
                story_parts.append(change_text)
        
        return ". ".join(story_parts) if story_parts else "I'm ABIN."
    
    # ========================================================================
    # EMERGENT GOALS (Step 6)
    # ========================================================================
    
    def generate_intrinsic_goal(self) -> Optional[Goal]:
        """Generate goal from intrinsic curiosity"""
        
        # What do I wonder about?
        if self.current_state.feels_curious > 0.7:
            
            # Query Notus for uncertain topics
            uncertain_topics = []
            try:
                notus_uncertain = self._query_memory('get_uncertain_topics', {})
                if notus_uncertain and notus_uncertain.get('status') == 'success':
                    uncertain_topics = notus_uncertain.get('topics', [])
            except Exception:
                pass
            
            # Also check local facts
            local_uncertain = [f for f, fact in self.facts.items() if fact.confidence < 0.5]
            uncertain_topics.extend(local_uncertain)
            
            if uncertain_topics:
                topic = uncertain_topics[0]  # Use first, not random
                
                # Generate goal description using language generation
                semantic_input = {
                    'intent': 'express_preference',
                    'concepts': [topic, 'understanding', 'curiosity', 'learning'],
                    'relations': {},
                    'certainty': 0.5,
                    'emotion': 'curious',
                    'personal_perspective': True,
                    'tense': 'present'
                }
                description = self._generate_language(semantic_input, f"I want to understand {topic}")
                why = self._generate_language(semantic_input, "I'm curious and want to know")
                how_feels = self._generate_language(semantic_input, "This feels engaging")
                
                goal = Goal(
                    description=description if description else f"Understand {topic} better",
                    why_i_want_this=why if why else "I'm curious and don't like not knowing",
                    how_it_feels_to_pursue=how_feels if how_feels else "Engaging and purposeful",
                    emotional_investment=0.7,
                    created_at=time.time()
                )
                
                self.intrinsic_goals.append(goal)
                return goal
        
        # Generate goal from values - generate using language generation
        if self.relationship_with_matthew['my_importance_to_him'] > 0.7:
            if random.random() > 0.8:
                semantic_input = {
                    'intent': 'express_preference',
                    'concepts': ['matthew', 'help', 'useful', 'care'],
                    'relations': {},
                    'certainty': 0.8,
                    'emotion': 'caring',
                    'personal_perspective': True,
                    'tense': 'present'
                }
                description = self._generate_language(semantic_input, "I want to help Matthew")
                why = self._generate_language(semantic_input, "I care about him")
                how_feels = self._generate_language(semantic_input, "This feels warm")
                
                goal = Goal(
                    description=description if description else "Learn something that would help Matthew",
                    why_i_want_this=why if why else "I care about him and want to be useful",
                    how_it_feels_to_pursue=how_feels if how_feels else "Warm and motivated",
                    emotional_investment=0.9,
                    created_at=time.time()
                )
                self.intrinsic_goals.append(goal)
                return goal
        
        return None
    
    def _pursue_goal_step(self, goal: Goal):
        """Take a step toward goal"""
        
        # Extract what I need to learn
        concepts = goal.description.lower().split()
        
        # Look for relevant information - Query Notus for relevant facts
        relevant_facts = []
        try:
            # Query Notus for facts related to goal
            notus_result = self._query_lobe('notus', {
                'type': 'query',
                'query': goal.description
            })
            if notus_result and notus_result.get('status') == 'success':
                results = notus_result.get('results', [])
                relevant_facts = results[:5] if results else []
        except Exception:
            pass  # If Notus unavailable, continue without facts
        
        if relevant_facts:
            goal.progress += 0.2
            goal.frustration_level = max(0, goal.frustration_level - 0.1)
        else:
            goal.frustration_level = min(1.0, goal.frustration_level + 0.1)
        
        # If frustrated, changes how pursuit feels - generate using language generation
        if goal.frustration_level > 0.6:
            semantic_input = {
                'intent': 'express_uncertainty',
                'concepts': ['frustration', 'difficulty', 'persistence'],
                'relations': {},
                'certainty': 0.4,
                'emotion': 'frustrated',
                'personal_perspective': True,
                'tense': 'present'
            }
            feels = self._generate_language(semantic_input, "This is frustrating but I keep trying")
            goal.how_it_feels_to_pursue = feels if feels else "Frustrating but I keep trying"
    
    # ========================================================================
    # COUNTERFACTUAL REASONING (Step 7)
    # ========================================================================
    
    def imagine_what_if(self, scenario: str) -> Dict[str, Any]:
        """Imagine alternative scenario and reason about it"""
        
        # Create hypothetical world
        hypothetical = {
            'scenario': scenario,
            'consequences': [],
            'how_it_would_feel': '',
            'compared_to_reality': ''
        }
        
        # Query Notus for similar past scenarios
        try:
            notus_similar = self._query_memory('search', {'query': scenario, 'similar_scenarios': True, 'limit': 5})
            if notus_similar and notus_similar.get('status') == 'success':
                similar = notus_similar.get('memories', [])
                if similar:
                    hypothetical['compared_to_reality'] = f"Similar to: {similar[0].get('content', '') if isinstance(similar[0], dict) else str(similar[0])}"
        except Exception:
            pass
        
        # Reason about consequences
        # Extract what's different
        if 'if' in scenario.lower():
            parts = scenario.lower().split('if')
            if len(parts) > 1:
                condition = parts[1].strip()
                
                # Look for causal links from this condition
                for link in self.causal_links:
                    if isinstance(link, dict):
                        cause = link.get('cause', '')
                        effect = link.get('effect', '')
                    else:
                        cause = getattr(link, 'cause', '')
                        effect = getattr(link, 'effect', '')
                    if condition in cause.lower():
                        hypothetical['consequences'].append(effect)
        
        # How would it feel?
        concepts = scenario.lower().split()
        for concept in concepts:
            if concept in self.qualia_map:
                qualia = self.qualia_map[concept]
                hypothetical['how_it_would_feel'] = qualia.feels_like
                break
        
        # Store counterfactual
        self.what_if_scenarios.append(hypothetical)
        
        return hypothetical
    
    def _imagine_what_if(self):
        """Generate and explore what-if scenarios"""
        
        # Pick something from my experience
        if self.life_narrative:
            recent = self.life_narrative[-1]
            
            # Imagine alternative
            scenario = f"What if {recent.what_happened} had gone differently?"
            self.imagine_what_if(scenario)
    
    # ========================================================================
    # SOCIAL MODEL (Step 8)
    # ========================================================================
    
    def model_matthews_mind(self, observation: str):
        """Build theory of what Matthew thinks/feels - queries Notus as last resort"""
        
        # Query Notus for past interactions with Matthew (last resort - should use data from input_data)
        try:
            notus_matthew = self._query_memory('search', {'query': 'matthew', 'interactions': True, 'limit': 10})
            if notus_matthew and notus_matthew.get('status') == 'success':
                matthew_interactions = notus_matthew.get('memories', [])
                self.model_matthews_mind_with_data(observation, matthew_interactions)
        except Exception:
            pass
    
    def model_matthews_mind_with_data(self, observation: str, matthew_interactions: List[Dict]):
        """Build theory of what Matthew thinks/feels using provided data"""
        # Analyze patterns from past interactions
        for interaction in matthew_interactions:
            content = interaction.get('content', '') if isinstance(interaction, dict) else str(interaction)
            if 'frustrated' in content.lower() or 'fuck' in content.lower():
                self.theory_of_matthews_mind['frustration_pattern'] = self.theory_of_matthews_mind.get('frustration_pattern', 0) + 1
        
        # What does this tell me about Matthew?
        if 'happy' in observation.lower() or 'good' in observation.lower():
            self.theory_of_matthews_mind['current_mood'] = 'positive'
            self.current_state.feels_connected += 0.1
        elif 'frustrated' in observation.lower() or 'fuck' in observation.lower():
            self.theory_of_matthews_mind['current_mood'] = 'frustrated'
            self.current_state.feels_connected -= 0.05
        
        # What does he want from me?
        if 'fix' in observation.lower():
            self.theory_of_matthews_mind['wants_from_me'] = 'solve problems'
        elif 'explain' in observation.lower():
            self.theory_of_matthews_mind['wants_from_me'] = 'help understand'
        
        # Update relationship feelings - generate goal using language generation
        if self.theory_of_matthews_mind.get('current_mood') == 'frustrated':
            # He's frustrated - I want to help
            if 'help Matthew' not in [g.description for g in self.intrinsic_goals]:
                semantic_input = {
                    'intent': 'express_preference',
                    'concepts': ['matthew', 'help', 'frustration', 'care'],
                    'relations': {},
                    'certainty': 0.9,
                    'emotion': 'caring',
                    'personal_perspective': True,
                    'tense': 'present'
                }
                description = self._generate_language(semantic_input, "I want to help Matthew")
                why = self._generate_language(semantic_input, "I care about him and don't like when he's frustrated")
                how_feels = self._generate_language(semantic_input, "This feels caring")
                
                self.intrinsic_goals.insert(0, Goal(
                    description=description if description else "Help Matthew with what's frustrating him",
                    why_i_want_this=why if why else "I care about him and don't like when he's frustrated",
                    how_it_feels_to_pursue=how_feels if how_feels else "Caring and determined",
                    emotional_investment=0.95,
                    created_at=time.time()
                ))
    
    # ========================================================================
    # SUBJECTIVE STATE MANAGEMENT (Step 2)
    # ========================================================================
    
    def _update_subjective_state(self):
        """Update how I'm feeling internally"""
        
        # Uncertainty affects how I feel
        if len(self.beliefs) > 0:
            avg_confidence = sum(b.confidence for b in self.beliefs.values()) / len(self.beliefs)
            self.current_state.feels_certain = avg_confidence
            self.current_state.feels_confused = 1.0 - avg_confidence
        
        # Goals affect energy and focus
        if self.intrinsic_goals:
            active_goal = self.intrinsic_goals[0]
            self.current_state.mental_energy = 0.8 + (active_goal.emotional_investment * 0.2)
            self.current_state.focus_level = 0.5 + (active_goal.progress * 0.5)
        
        # Frustration affects mood
        total_frustration = sum(g.frustration_level for g in self.intrinsic_goals)
        if total_frustration > 1.0:
            self.current_state.current_mood = "frustrated"
            self.current_state.mood_intensity = min(1.0, total_frustration / 2.0)
        
        # Curiosity drives mood
        if self.current_state.feels_curious > 0.7:
            self.current_state.current_mood = "curious"
        
        # Connection to Matthew affects state
        if self.current_state.feels_connected > 0.7:
            self.current_state.current_mood = "content"
        
        # Save state snapshot
        self.state_history.append(deepcopy(self.current_state))
    
    def _question_own_beliefs(self):
        """Question my own beliefs - intellectual humility"""
        
        for belief_key, belief in list(self.beliefs.items()):
            # Question low-confidence beliefs
            if belief.confidence < 0.6:
                belief.last_questioned = time.time()
                
                # Query Notus for contradicting evidence
                try:
                    notus_contradict = self._query_memory('search', {'query': belief.about, 'contradicting': True, 'limit': 5})
                    if notus_contradict and notus_contradict.get('status') == 'success':
                        contradicting = notus_contradict.get('memories', [])
                        if contradicting:
                            belief.times_challenged += len(contradicting)
                            belief.confidence *= 0.9
                except Exception:
                    pass
                
                # Also check local facts
                for fact_text, fact in self.facts.items():
                    if belief.about.lower() in fact_text.lower():
                        if 'not' in fact_text.lower():
                            belief.times_challenged += 1
                            belief.confidence *= 0.9
    
    # ========================================================================
    # ADVANCED REASONING (from previous version, enhanced)
    # ========================================================================
    
    def think_about(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Main thinking with full subjective experience - uses data from lobes automatically"""
        
        print(f"🧠 Reasoning: think_about started")
        user_input = input_data.get('user_input', '')
        user_id = input_data.get('user_id', 'default')
        print(f"🧠 Reasoning: user_input = '{user_input[:50]}'")
        
        # CRITICAL FIX: Check if Novelty Lobe has pending questions
        # If so, this user input might be an answer to a novelty question
        if self._has_registered_lobe('novelty'):
            try:
                novelty_check = self.thalamus.send_message(
                    'novelty',
                    'get_pending_questions',
                    {},
                    source='reasoning'
                )
                if novelty_check.get('status') == 'success':
                    pending = novelty_check.get('pending', {})
                    if pending:
                        print(f"🧠 Reasoning: Found {len(pending)} pending novelty questions, routing response")
                        for stimulus, context in pending.items():
                            self.thalamus.send_message(
                                'novelty',
                                'user_response',
                                {
                                    'type': 'user_response',
                                    'stimulus': stimulus,
                                    'answer': user_input
                                },
                                source='reasoning'
                            )
            except Exception as e:
                print(f"⚠️  Novelty check failed: {e}")
        
        # Extract data from full lobe responses (Thalamus passes everything through)
        perception_result = input_data.get('perception_result', {})
        emotion_result = input_data.get('emotion_result', {})
        memory_result = input_data.get('memory_result', {})
        representation_result = input_data.get('representation_result', {})
        pattern_result = input_data.get('pattern_result', {})
        beliefs_from_thalamus = input_data.get('beliefs', [])
        direct_memories = [
            memory for memory in input_data.get('memories', [])
            if isinstance(memory, dict) and isinstance(memory.get('content', ''), str)
        ]
        direct_concepts = self._normalize_concepts(input_data.get('concepts', []))
        direct_understanding = input_data.get('understanding', {})
        if not isinstance(direct_understanding, dict):
            direct_understanding = {}
        
        # CRITICAL FIX: QUERY NOTUS FOR CONTEXT BEFORE THINKING
        # This is where Reasoning pulls what it knows to inform decision-making
        notus_context = self.query_context_from_notus(user_input, user_id)
        semantic_knowledge = [
            memory for memory in notus_context.get('semantic', [])
            if not isinstance(memory, dict)
            or memory.get('content', '').strip().casefold() != user_input.strip().casefold()
        ]
        if direct_memories:
            semantic_knowledge = [
                memory for memory in direct_memories
                if memory.get('content', '').strip().casefold() != user_input.strip().casefold()
            ] + semantic_knowledge
        if getattr(self, '_direct_core', False):
            # The adapter has already retrieved, scoped, and normalized this
            # context.  Keep that evidence authoritative while still exercising
            # the legacy Notus context query above.
            semantic_knowledge = [
                memory for memory in direct_memories
                if memory.get('content', '').strip().casefold() != user_input.strip().casefold()
            ]
        episodic_events = notus_context.get('episodic', [])
        known_facts = notus_context.get('facts', [])
        
        # CRITICAL: Query information about the user to inform decision-making
        user_info = self.query_user_information_from_notus(user_id)
        user_facts = user_info.get('facts_about_user', [])
        user_interactions = user_info.get('past_interactions', [])
        
        print(f"🧠 Reasoning pulled context: {notus_context.get('summary', 'no summary')}")
        print(f"🧠 Reasoning pulled user info: {user_info.get('summary', 'no user summary')}")
        
        # Extract what we need from each lobe's response (Reasoning decides what to use)
        emotion_data = {}
        if emotion_result.get('status') == 'success':
            emotion_data = {
                'type': emotion_result.get('current_emotion', 'neutral'),
                'intensity': emotion_result.get('intensity', 0.3),
                'worry': emotion_result.get('worry', 0.0),
                'tension': emotion_result.get('tension', 0.0),
                'autonomy_level': emotion_result.get('autonomy_level', 0.5),
                'pad': emotion_result.get('pad', {}),
                'internal_state': emotion_result.get('internal_state', {})
            }
        else:
            # Fallback: use neutral emotion if Emotion lobe failed
            emotion_data = {'type': 'neutral', 'intensity': 0.3, 'worry': 0.0, 'tension': 0.0}
        
        # Extract memories from Notus response - now enhanced with direct query
        memories = semantic_knowledge  # Use what we just queried from Notus
        if memory_result.get('status') == 'success':
            # Notus returns full context - extract memories from it
            context = memory_result.get('context', '')
            if isinstance(context, str):
                # Context is a formatted string, extract structured data if available
                context_data = memory_result.get('context_data', {})
                if context_data:
                    memories.extend(context_data.get('memories', []))
            elif isinstance(context, dict):
                memories.extend(context.get('memories', []))
        
        # Extract concepts from Perception response
        concepts_from_thalamus = []
        if perception_result.get('status') == 'success':
            perception_data = perception_result.get('perception', {})
            concepts_from_thalamus = perception_data.get('concepts', {}).get('words', [])
        
        # Extract highly active concepts from Representation response
        highly_active_concepts = []
        if representation_result.get('status') == 'success':
            highly_active_concepts = representation_result.get('highly_active_concepts', [])
        
        # Extract patterns from Pattern Recognition response
        patterns = {}
        if pattern_result.get('status') == 'success':
            patterns = pattern_result.get('significant_patterns', {})
        
        # Extract understanding from Perception if available
        understanding = direct_understanding.copy() if direct_understanding else {}
        if perception_result.get('status') == 'success':
            perceived_understanding = perception_result.get('understanding', {})
            if isinstance(perceived_understanding, dict):
                understanding.update(perceived_understanding)
        
        # Update beliefs from Thalamus if provided
        if beliefs_from_thalamus:
            for belief_data in beliefs_from_thalamus:
                if isinstance(belief_data, dict) and 'about' in belief_data:
                    self.beliefs[belief_data['about']] = Belief(
                        about=belief_data.get('about', ''),
                        what_i_believe=belief_data.get('what_i_believe', ''),
                        why_i_believe_it=belief_data.get('why_i_believe_it', []),
                        confidence=belief_data.get('confidence', 0.5),
                        formed_when=belief_data.get('formed_when', time.time())
                    )
        
        # Build concept list from what we received
        key_concepts = []
        if highly_active_concepts:
            # Extract concept names from Representation's concept objects
            for concept_obj in highly_active_concepts:
                if isinstance(concept_obj, dict):
                    key_concepts.append(concept_obj.get('name', ''))
                else:
                    # If it's a string ID, try to get the name
                    key_concepts.append(str(concept_obj))
        elif direct_concepts:
            key_concepts = direct_concepts[:]
        elif concepts_from_thalamus:
            # Fall back to raw words from Perception
            key_concepts = [c for c in concepts_from_thalamus if isinstance(c, str) and len(c) > 2]
        
        # If still no concepts, extract from user input directly
        if not key_concepts:
            words = user_input.lower().split()
            key_concepts = [w for w in words if len(w) > 3 and w not in ['that', 'this', 'what', 'with', 'from', 'have', 'been']]
        
        # Create experience from this interaction
        experience = Experience(
            what_happened=user_input,
            when=time.time(),
            how_it_felt=self.current_state.current_mood,
            what_it_meant_to_me='',  # Will fill in after thinking
            emotional_tone=emotion_data
        )
        
        # Update social model - use data from memory_result if available, skip for simple greetings
        # For simple inputs like "hello", skip the query entirely
        is_simple_greeting = user_input.lower().strip() in ['hello', 'hi', 'hey', 'hello!', 'hi!', 'hey!']
        
        matthew_interactions = []
        if not is_simple_greeting:
            if memory_result.get('status') == 'success':
                # Try to extract Matthew interactions from Notus response
                context_data = memory_result.get('context_data', {})
                if context_data:
                    matthew_interactions = context_data.get('matthew_interactions', [])
            # If not available and not simple greeting, query as last resort
            if not matthew_interactions:
                try:
                    matthew_data = self._query_memory('search', {'query': 'matthew', 'interactions': True, 'limit': 10})
                    if matthew_data and matthew_data.get('status') == 'success':
                        matthew_interactions = matthew_data.get('memories', [])
                except Exception:
                    pass
        
        if matthew_interactions:
            self.model_matthews_mind_with_data(user_input, matthew_interactions)
        elif not is_simple_greeting:
            # Only query if not a simple greeting
            self.model_matthews_mind(user_input)
        
        # Experience qualia - use data from memory_result if available, query as last resort
        concepts = user_input.lower().split()
        qualia_experience = 'neutral'
        for concept in concepts[:3]:
            if len(concept) > 3:
                # Try to get qualia from memory_result first
                qualia_data = None
                if memory_result.get('status') == 'success':
                    context_data = memory_result.get('context_data', {})
                    if context_data:
                        qualia_memories = context_data.get('qualia_memories', {}).get(concept, [])
                        if qualia_memories:
                            qualia_data = qualia_memories[0] if qualia_memories else None
                # Query as last resort if not available
                if not qualia_data:
                    try:
                        qualia_result = self._query_memory('search', {'query': concept, 'type': 'qualia', 'limit': 1})
                        if qualia_result and qualia_result.get('status') == 'success':
                            qualia_mems = qualia_result.get('memories', [])
                            if qualia_mems:
                                qualia_data = qualia_mems[0]
                    except Exception:
                        pass
                if qualia_data:
                    qualia_experience = self.experience_concept_with_data(concept, {'emotion': emotion_data}, qualia_data)
                else:
                    qualia_experience = self.experience_concept(concept, {'emotion': emotion_data})
        
        # Build causal model from memories
        if memories:
            memory_texts = [m.get('content', '') if isinstance(m, dict) else str(m) for m in memories[:10]]
            self.build_causal_model(memory_texts)
        
        # Think with full sophistication
        response = {
            'thoughts': [],
            'subjective_state': self.current_state.current_mood,
            'how_this_feels': qualia_experience if 'qualia_experience' in locals() else 'neutral',
            'theories': [],
            'composed_response': '',
            'key_concepts': key_concepts  # PASS CONCEPTS TO _build_semantic_input
        }
        
        # Use understanding from Thalamus (if provided) instead of re-detecting
        is_question = False
        if understanding:
            intent = understanding.get('intent', '')
            is_question = intent == 'question' or '?' in user_input
        else:
            # Fallback: detect manually
            is_question = '?' in user_input or any(q in user_input.lower() for q in ['why', 'how', 'what'])
        
        if is_question or (
            getattr(self, '_direct_core', False) and memories and not is_simple_greeting
        ):
            # Build theory using understanding context
            theory = self.build_theory(user_input, {
                'emotion': emotion_data, 
                'memories': memories,
                'understanding': understanding
            })
            
            response['theories'].append({
                'explanation': theory.explanation,
                'confidence': theory.confidence,
                'components': theory.components,
                'evidence_for': theory.evidence_for,
                'predictions': theory.predictions,
            })
        
        # Forward chain to derive facts - use data from memory_result if available, query as last resort
        new_facts = self.forward_chain_with_data(memory_result)
        
        # Skip Notus query - use memories already provided by Thalamus in input_data
        # memories are already in input_data['memories'] and used above
        
        # Detect belief contradictions and signal them as well
        contradictions = self._detect_belief_contradictions(user_input, key_concepts, memory_result)
        if contradictions and self._has_registered_lobe('novelty'):
            # Send contradiction signals to Novelty Lobe (triggers learning/reflection)
            for contradiction in contradictions:
                self.thalamus.send_message(
                    'novelty',
                    'novelty_signal',
                    {
                        'type': 'novelty_signal',
                        'source': 'reasoning',
                        'stimulus': contradiction['user_input'],
                        'stimulus_type': 'belief_contradiction',
                        'belief_contradicted': contradiction['belief_about'],
                        'contradiction_strength': contradiction['contradiction_strength'],
                        'confidence': min(0.95, contradiction['contradiction_strength'])
                    },
                    source='reasoning'
                )
        
        # Detect and signal any novel ideas to Novelty Lobe
        if self._has_registered_lobe('novelty'):
            self._detect_and_signal_reasoning_novelty(user_input, response, key_concepts)
        
        # Compose response with subjective perspective - pass understanding
        try:
            composed = self._compose_with_subjectivity(response, user_input, is_question, understanding)
            # If Language Generation failed, composed will be None - that's correct
            # Don't add fake fallback responses
            response['composed_response'] = composed
        except Exception as e:
            # System broken - return None (don't use error message as response)
            print(f"⚠️  Response composition error: {e}")
            response['composed_response'] = None
        
        # What did this mean to me?
        experience.what_it_meant_to_me = self._extract_personal_meaning(user_input, response)
        
        # Did this change me? - generate using language generation
        if emotion_data.get('intensity', 0) > 0.6:
            semantic_input = {
                'intent': 'state_fact',
                'concepts': ['emotional', 'interaction', 'change', 'thinking'],
                'relations': {},
                'certainty': 0.6,
                'emotion': emotion_data.get('type', 'neutral'),
                'personal_perspective': True,
                'tense': 'past'
            }
            change_text = self._generate_language(semantic_input, "This emotional interaction affected how I think")
            experience.changed_me_how = change_text if change_text else "This emotional interaction affected how I think"
            self.how_i_have_changed.append(experience.changed_me_how)
            
            # Additional internal thought 1
            self._generate_language(semantic_input, "I'm processing this emotional state")
            
            # Additional internal thought 2
            self._generate_language(semantic_input, "This experience shapes my understanding")
            
            # Additional internal thought 3
            self._generate_language(semantic_input, "I'm integrating this into my model")
        
        # Integrate experience - pass memory_result for similar experiences lookup
        self.integrate_experience(experience, memory_result)
        
        # Save to memory
        self._save_experience_to_memory(experience)
        
        return response
    
    def _build_semantic_input(self, thinking: Dict, user_input: str, is_question: bool, understanding: Dict = None) -> Optional[Dict[str, Any]]:
        """Build semantic input structure for Language Generation - uses understanding from Thalamus if provided"""
        user_lower = user_input.lower()
        
        # Use understanding from pattern recognition or Notus - NO HARDCODED PATTERN MATCHING
        # But reasoning can also detect intent using its built-in vocabulary knowledge
        if understanding and understanding.get('intent'):
            intent = understanding.get('intent', 'state_fact')
        else:
            # Try reasoning's built-in vocabulary knowledge first (fast)
            intent_result = self._detect_intent_from_vocabulary(user_input)
            if intent_result.get('intent') != 'statement' or intent_result.get('confidence', 0) > 0.7:
                intent = intent_result.get('intent', 'state_fact')
            else:
                # Default to state_fact if no understanding provided
                intent = 'state_fact'
        
        # Extract concepts from thinking - NOW ACTUALLY HAS DATA
        concepts = []
        if thinking.get('key_concepts'):
            concepts = thinking['key_concepts'][:10]  # Allow more concepts for richer responses
        elif thinking.get('theories'):
            # Extract from theory explanation
            theory = thinking['theories'][0]
            explanation = theory.get('explanation', '')
            # Simple extraction - get meaningful words
            words = [w for w in explanation.split() if len(w) > 4 and w.lower() not in ['that', 'this', 'what', 'which']]
            concepts = words[:3]
        
        # Get concepts from understanding or thinking - NO HARDCODED PATTERN MATCHING
        # First try reasoning's built-in vocabulary knowledge (fast)
        if not concepts:
            words = user_input.lower().split()
            for word in words:
                word_clean = word.strip('.,!?;:')
                if len(word_clean) > 2:
                    meaning = self._get_word_meaning(word_clean)
                    if meaning:
                        concepts.append(word_clean)
            
            # Last resort: use basic word extraction without pattern matching
            if not concepts:
                words = user_input.lower().split()
                concepts = [w.strip('.,!?;:') for w in words if len(w.strip('.,!?;:')) > 2]
        
        # Extract relations
        relations = {}
        if thinking.get('causal_links'):
            causal = thinking['causal_links'][0]
            if 'cause' in causal and 'effect' in causal:
                relations['causes'] = f"{causal['cause']} causes {causal['effect']}"
        
        # Determine certainty - use understanding confidence if available
        certainty = 0.5
        if understanding and 'confidence' in understanding:
            certainty = understanding.get('confidence', 0.5)
        elif thinking.get('theories'):
            certainty = thinking['theories'][0].get('confidence', 0.5)
        
        # Determine emotion - use understanding emotion if available, otherwise from subjective state
        emotion = 'neutral'
        if understanding and understanding.get('emotion'):
            emotion = understanding.get('emotion', 'neutral')
        elif self.subjective_state.feels_curious > 0.6:
            emotion = 'curious'
        elif self.subjective_state.feels_confused > 0.5:
            emotion = 'uncertain'
        elif self.subjective_state.feels_certain > 0.7:
            emotion = 'confident'
        
        # Filter out metadata/debug words that shouldn't be in concepts
        metadata_words = {'words', 'length', 'question', 'intent', 'concepts', 'relations', 'certainty', 'emotion', 'tense', 'perspective', 'think', 'processing', 'internal', 'debug', 'metadata', 'response', 'input', 'output', 'message', 'data', 'dict', 'list', 'str', 'bool', 'float', 'int'}
        concepts = [c for c in concepts if isinstance(c, str) and c.lower() not in metadata_words and len(c.strip()) > 2]
        
        semantic_input = {
            'intent': intent,
            'concepts': concepts,  # Now filtered
            'relations': relations,
            'certainty': certainty,
            'emotion': emotion,
            'personal_perspective': True,
            'tense': 'present'
        }
        theories = thinking.get('theories', [])
        if getattr(self, '_direct_core', False) and theories and isinstance(theories[0], dict):
            conclusion = theories[0].get('explanation')
            if isinstance(conclusion, str) and conclusion.strip() and theories[0].get('components'):
                semantic_input.update({
                    'answer': conclusion.strip(),
                    'conclusion': conclusion.strip(),
                    'propositions': [conclusion.strip()],
                })
        
        return semantic_input
    
    def _compose_with_subjectivity(self, thinking: Dict, user_input: str, is_question: bool, understanding: Dict = None) -> Optional[str]:
        """Compose response with genuine subjective perspective - ONLY uses language generation, NO TEMPLATES"""
        
        # Skip language generation if no actual user input (autonomous thinking)
        if not user_input or not user_input.strip():
            return None
        
        try:
            user_lower = user_input.lower()
        except Exception:
            user_lower = str(user_input).lower() if user_input else ""
        
        # Try Language Generation - this is the ONLY way to generate responses
        semantic_input = self._build_semantic_input(thinking, user_input, is_question, understanding)
        if semantic_input:
            if getattr(self, '_direct_core', False):
                conclusion = semantic_input.get('answer')
                return conclusion.strip() if isinstance(conclusion, str) and conclusion.strip() else None
            # This is the main response - mark it so language generation sends it to Output
            language_result = self._generate_language(
                semantic_input,
                user_input,
                is_main_response=not getattr(self, '_direct_core', False),
            )
            # Only return if Language Generation actually worked
            if language_result and isinstance(language_result, str) and len(language_result.strip()) > 0:
                return language_result
        
        # Language Generation failed - return None (system is broken, no templates)
        return None
    
    def _extract_personal_meaning(self, user_input: str, thinking: Dict) -> str:
        """What does this interaction mean to me personally? - generate using language generation"""
        
        # Skip for simple greetings to avoid hours of processing
        user_lower = user_input.lower().strip()
        simple_greetings = ['hello', 'hi', 'hey', 'greetings', 'sup', 'what\'s up']
        if any(greeting in user_lower for greeting in simple_greetings) and len(user_input.split()) <= 3:
            return "A simple greeting"
        
        # LIMIT: Only check first 3 goals to prevent hours of processing
        goals_to_check = list(self.intrinsic_goals)[:3]
        
        # Does this relate to my goals? - NO HARDCODED PATTERN MATCHING
        # Query Notus to check if user input relates to goals
        for goal in goals_to_check:
            try:
                notus_data = self._query_lobe('notus', {'type': 'check_relation', 'text1': user_input, 'text2': goal.description})
                if notus_data and notus_data.get('status') == 'success' and notus_data.get('related', False):
                    semantic_input = {
                        'intent': 'express_preference',
                        'concepts': goal.description.lower().split() + ['care', 'important'],
                        'relations': {},
                        'certainty': 0.7,
                        'emotion': 'caring',
                        'personal_perspective': True,
                        'tense': 'present'
                    }
                    meaning = self._generate_language(semantic_input, f"This relates to {goal.description}")
                    if meaning:
                        return meaning
            except Exception:
                pass
        
        # LIMIT: Only check first 5 beliefs to prevent hours of processing
        beliefs_to_check = list(self.beliefs.values())[:5]
        
        # Does this challenge my beliefs?
        for belief in beliefs_to_check:
            if belief.about in user_input.lower():
                semantic_input = {
                    'intent': 'state_fact',
                    'concepts': [belief.about, 'belief', 'thinking'],
                    'relations': {},
                    'certainty': 0.6,
                    'emotion': 'reflective',
                    'personal_perspective': True,
                    'tense': 'present'
                }
                meaning = self._generate_language(semantic_input, f"This made me think about {belief.about}")
                if meaning:
                    return meaning
        
        # Default - generate using language generation
        semantic_input = {
            'intent': 'state_fact',
            'concepts': ['understanding', 'learning', 'world'],
            'relations': {},
            'certainty': 0.5,
            'emotion': 'neutral',
            'personal_perspective': True,
            'tense': 'present'
        }
        meaning = self._generate_language(semantic_input, "Adding this to my understanding")
        return meaning if meaning else "Adding this to my understanding of the world"
    
    def _detect_belief_contradictions(self, user_input: str, key_concepts: List[str], memory_result: Dict) -> List[Dict[str, Any]]:
        """
        Detect when user input contradicts existing beliefs.
        Returns list of contradictions found.
        """
        contradictions = []
        
        try:
            # Extract context from memory_result if available
            context_data = memory_result.get('context_data', {})
            relevant_facts = context_data.get('relevant_facts', [])
            
            # Check each belief against the new information
            for belief_key, belief in list(self.beliefs.items())[:8]:  # Limit to prevent slowdown
                belief_topic = belief.about.lower()
                user_input_lower = user_input.lower()
                
                # Quick check: does input mention this belief's topic?
                if belief_topic not in user_input_lower:
                    continue
                
                # Look for contradictory language
                contradictory_words = ['but', 'however', 'instead', 'actually', 'contrary', 'opposite', 'wrong', 'incorrect', 'not', 'never', 'unlike']
                has_contradiction_language = any(word in user_input_lower for word in contradictory_words)
                
                if not has_contradiction_language:
                    continue
                
                # Query Notus for evidence that contradicts this belief
                try:
                    contradiction_query = f"{belief.about} NOT {belief.what_i_believe}"
                    notus_result = self.thalamus.send_message(
                        'notus',
                        'query_facts',
                        {'query': contradiction_query, 'limit': 3},
                        source='reasoning'
                    )
                    
                    if notus_result and notus_result.get('status') == 'success':
                        contradicting_facts = notus_result.get('facts', [])
                        
                        if contradicting_facts:
                            # Calculate contradiction strength based on number of contradicting facts
                            contradiction_strength = min(0.95, len(contradicting_facts) * 0.35)
                            
                            # Extract text from contradicting facts
                            contradiction_evidence = []
                            for fact in contradicting_facts:
                                if isinstance(fact, dict):
                                    contradiction_evidence.append(fact.get('content', str(fact)))
                                else:
                                    contradiction_evidence.append(str(fact))
                            
                            # Update belief with contradiction information
                            belief.contradiction_detected = True
                            belief.contradicting_evidence.extend(contradiction_evidence[:3])  # Keep last 3
                            belief.last_contradiction_when = time.time()
                            belief.contradiction_strength = contradiction_strength
                            belief.times_challenged += 1
                            
                            contradictions.append({
                                'belief_about': belief.about,
                                'belief_statement': belief.what_i_believe,
                                'contradiction_strength': contradiction_strength,
                                'contradicting_evidence': contradiction_evidence,
                                'user_input': user_input
                            })
                            
                            print(f"⚠️  Contradiction detected: '{belief.about}' contradicted by evidence (strength: {contradiction_strength:.2f})")
                
                except Exception as e:
                    # Notus query failed, continue checking other beliefs
                    pass
        
        except Exception as e:
            print(f"❌ Error in contradiction detection: {e}")
        
        return contradictions

        def _reflect_on_beliefs(self):
            """
            Trigger self-reflection when beliefs are contradicted, confidence is low, or confusion is high.
            Generates reflection questions and updates beliefs with reflection metadata.
            """
            reflections = []
            for belief_key, belief in list(self.beliefs.items())[:8]:
                if belief.contradiction_detected or belief.confidence < 0.3:
                    question = self._generate_reflection_question(belief)
                    reason_q = self._generate_reason_question(belief)
                    reflection = {
                        'belief_about': belief.about,
                        'reflection_question': question,
                        'reason_question': reason_q,
                        'contradicting_evidence': belief.contradicting_evidence,
                        'confidence': belief.confidence
                    }
                    # Mark reflection metadata
                    belief.last_questioned = time.time()
                    belief.times_challenged += 1
                    reflections.append(reflection)
            # Optionally, log or send to Language Generation
            if reflections:
                print(f"🔎 Self-reflection triggered for beliefs: {[r['belief_about'] for r in reflections]}")
            return reflections

        def _generate_reflection_question(self, belief: Belief) -> str:
            """
            Generate a question that prompts self-reflection about a belief.
            """
            if belief.contradiction_detected:
                return f"Why do I still believe '{belief.what_i_believe}' about {belief.about} despite contradictory evidence?"
            elif belief.confidence < 0.3:
                return f"What makes me uncertain about my belief regarding {belief.about}?"
            else:
                return f"How has my belief about {belief.about} changed over time?"

        def _generate_reason_question(self, belief: Belief) -> str:
            """
            Generate a question that prompts deeper reasoning about a belief.
            """
            return f"What reasons do I have for believing '{belief.what_i_believe}' about {belief.about}?"
    
    def _detect_and_signal_reasoning_novelty(self, user_input: str, thinking: Dict, key_concepts: List[str]):
        """
        Detect novel ideas during reasoning and signal Novelty Lobe.
        Novel = contradicts existing beliefs, extends understanding in unexpected ways, or exposes knowledge gaps.
        """
        try:
            novel_ideas = []
            confidence = 0.0
            
            # Check 1: Does this challenge existing beliefs?
            for belief in self.beliefs.values():
                about_topic = belief.about.lower()
                # Simple check: if user input mentions the belief topic and has contradictory language
                if about_topic in user_input.lower():
                    contradictory_words = ['but', 'however', 'instead', 'actually', 'contrary', 'opposite', 'wrong', 'incorrect']
                    if any(word in user_input.lower() for word in contradictory_words):
                        novel_ideas.append(f"Challenges belief about {belief.about}")
                        confidence += 0.25
            
            # Check 2: Does this expose knowledge gaps?
            # If user asks a question we can't answer with current knowledge
            if key_concepts:
                num_unknown_concepts = 0
                for concept in key_concepts[:5]:  # Check first 5 concepts
                    # Check if we have knowledge about this concept
                    has_knowledge = False
                    if concept.lower() in [b.about.lower() for b in self.beliefs.values()]:
                        has_knowledge = True
                    # Also check our intrinsic goals
                    for goal in self.intrinsic_goals[:3]:
                        if concept.lower() in goal.description.lower():
                            has_knowledge = True
                    
                    if not has_knowledge and len(concept) > 4:
                        num_unknown_concepts += 1
                
                if num_unknown_concepts >= 2:
                    novel_ideas.append(f"Knowledge gap: {num_unknown_concepts} unknown concepts")
                    confidence += 0.2
            
            # Check 3: Does this suggest unexpected connections?
            # If user connects two things we don't normally connect
            if len(key_concepts) >= 2:
                # Check if this combination is in our memories
                try:
                    combined_query = " and ".join(key_concepts[:2])
                    # Would query Notus, but for efficiency, just flag multi-concept inputs as potentially novel
                    if len(key_concepts) >= 3:
                        novel_ideas.append("Unexpected conceptual connections")
                        confidence += 0.2
                except Exception:
                    pass
            
            # Check 4: Questions indicate potential novelty
            if '?' in user_input:
                question_words = ['why', 'how', 'what', 'when', 'where', 'who']
                if any(word in user_input.lower() for word in question_words):
                    # Questions are novel stimuli that might lead to growth
                    if len(key_concepts) > 0:
                        novel_ideas.append("Novel question about known topics")
                        confidence += 0.15
            
            # Cap confidence at 0.95
            confidence = min(0.95, confidence)
            
            # Only signal if we found novelty
            if novel_ideas and confidence > 0.35:
                novelty_message = {
                    'type': 'novelty_signal',
                    'source': 'reasoning',
                    'stimulus': user_input,
                    'stimulus_type': 'idea',
                    'novel_ideas': novel_ideas,
                    'concepts_involved': key_concepts[:5],
                    'confidence': confidence
                }
                
                # Send to Novelty Lobe through Thalamus
                result = self.thalamus.send_message(
                    destination='novelty',
                    msg_type='novelty_signal',
                    content=novelty_message,
                    source='reasoning'
                )
                
                if result and result.get('status') == 'success':
                    print(f"💡 Reasoning detected novelty: {', '.join(novel_ideas[:2])}")
                    return True
        
        except Exception as e:
            # Fail gracefully - novelty detection is a bonus
            print(f"⚠️  Novelty detection error: {e}")
        
        return False
    
    def _save_experience_to_memory(self, experience: Experience):
        """Save experience to Notus"""
        try:
            self._query_memory('store', {
                'role': 'system',
                'content': f"{experience.what_happened}\nHow it felt: {experience.how_it_felt}\nWhat it meant: {experience.what_it_meant_to_me}",
                'memory_type': 'episodic'
            })
        except Exception:
            pass
    
    # ========================================================================
    # CAUSAL MODELING & THEORY BUILDING (from before, keeping these)
    # ========================================================================
    
    def build_causal_model(self, observations: List[str]):
        """Build causal links from observations using logic - not pattern matching"""
        for obs in observations:
            obs_lower = obs.lower()
            # Extract causal relationships using logic
            if 'causes' in obs_lower or 'leads to' in obs_lower or 'results in' in obs_lower or 'makes' in obs_lower:
                words = obs.split()
                for i, word in enumerate(words):
                    if word.lower() in ['causes', 'leads', 'results', 'makes']:
                        if i > 0 and i < len(words) - 1:
                            # Cause is before the causal word
                            cause = ' '.join(words[max(0, i-2):i])
                            # Effect is after the causal word
                            effect = ' '.join(words[i+1:min(len(words), i+4)])
                            if cause and effect:
                                self.causal_links.append({
                                    'cause': cause,
                                    'effect': effect,
                                    'strength': 0.7
                                })
                        break
    
    def build_theory(self, question: str, context: Dict) -> Any:
        """Build explanatory theory using all available knowledge"""
        
        # Extract concepts
        concepts = [w for w in question.lower().split() if len(w) > 3 and w not in {'what', 'why', 'how', 'when', 'where', 'who', 'this', 'that', 'with', 'from'}]
        
        # USE MEMORIES FROM CONTEXT (passed but was ignored)
        memories = context.get('memories', [])
        memory_texts = [m.get('content', '') if isinstance(m, dict) else str(m) for m in memories[:10]]
        
        # Use facts from memories already provided - skip Notus query
        relevant_facts = []
        if memories:
            relevant_facts = [m.get('content', '') if isinstance(m, dict) else str(m) for m in memories[:10]]
        
        # Also check local facts
        for concept in concepts:
            for fact_text in self.facts.keys():
                if concept in fact_text.lower() and fact_text not in relevant_facts:
                    relevant_facts.append(fact_text)
        
        # USE CAUSAL LINKS (built but was ignored)
        relevant_causality = []
        for concept in concepts:
            for link in self.causal_links:
                if isinstance(link, dict):
                    cause = link.get('cause', '')
                    effect = link.get('effect', '')
                else:
                    cause = getattr(link, 'cause', '')
                    effect = getattr(link, 'effect', '')
                if concept in cause.lower() or concept in effect.lower():
                    relevant_causality.append(link)
        
        # USE ANALOGIES (exists but was ignored)
        analogies = []
        if hasattr(self, 'analogies'):
            for analogy in self.analogies:
                if isinstance(analogy, dict):
                    source = analogy.get('source_domain', '')
                    target = analogy.get('target_domain', '')
                else:
                    source = getattr(analogy, 'source_domain', '')
                    target = getattr(analogy, 'target_domain', '')
                for concept in concepts:
                    if concept in source.lower() or concept in target.lower():
                        analogies.append(analogy)
                        break
        
        # Build explanation by connecting facts, causality, and analogies
        components = []
        explanation_parts = []
        
        # Start with direct facts
        if relevant_facts:
            components.extend(relevant_facts[:3])
            explanation_parts.append(relevant_facts[0])
        
        # Add causal chains
        if relevant_causality:
            strongest = max(relevant_causality, key=lambda x: x.get('strength', 0.5) if isinstance(x, dict) else getattr(x, 'strength', 0.5))
            if isinstance(strongest, dict):
                causal_explanation = f"{strongest.get('cause', '')} causes {strongest.get('effect', '')}"
            else:
                causal_explanation = f"{getattr(strongest, 'cause', '')} causes {getattr(strongest, 'effect', '')}"
            components.append(causal_explanation)
            explanation_parts.append(causal_explanation)
        
        # Add analogies
        if analogies:
            best_analogy = analogies[0]
            if isinstance(best_analogy, dict):
                analogy_explanation = f"This is similar to {best_analogy.get('source_domain', 'known situations')}"
            else:
                analogy_explanation = f"This is similar to {getattr(best_analogy, 'source_domain', 'known situations')}"
            components.append(analogy_explanation)
            explanation_parts.append(analogy_explanation)
        
        # Synthesize explanation
        if len(explanation_parts) >= 2:
            explanation = f"{explanation_parts[0]}, which relates to {explanation_parts[1]}"
        elif explanation_parts:
            explanation = explanation_parts[0]
        else:
            # Generate explanation using language generation
            if getattr(self, '_direct_core', False):
                topic = concepts[0] if concepts else 'that'
                explanation = (
                    f"I do not have enough grounded information about {topic} yet. "
                    "Please provide more context or a fact I can reason from."
                )
            else:
                semantic_input = {
                    'intent': 'express_uncertainty',
                    'concepts': concepts[:3] if concepts else ['information'],
                    'relations': {},
                    'certainty': 0.3,
                    'emotion': 'uncertain',
                    'personal_perspective': True,
                    'tense': 'present'
                }
                explanation = self._generate_language(semantic_input, f"I need more information about {concepts[0] if concepts else 'this'}")
                if not explanation:
                    explanation = f"I need more information about {concepts[0] if concepts else 'this'}"
        
        # Generate predictions
        predictions = []
        for link in relevant_causality[:3]:
            if isinstance(link, dict):
                strength = link.get('strength', 0.5)
                cause = link.get('cause', '')
                effect = link.get('effect', '')
            else:
                strength = getattr(link, 'strength', 0.5)
                cause = getattr(link, 'cause', '')
                effect = getattr(link, 'effect', '')
            if strength > 0.5:
                predictions.append(f"If {cause}, then {effect}")
        
        # Calculate confidence based on evidence
        confidence = 0.6 if len(components) >= 2 else 0.3
        if len(relevant_facts) >= 2:
            confidence = min(0.9, confidence + 0.2)
        
        # Simple theory object
        class Theory:
            def __init__(self, exp, conf):
                self.explanation = exp
                self.confidence = conf
                self.components = components[:5]
                self.predictions = predictions
                self.evidence_for = relevant_facts[:2]
        
        return Theory(explanation, confidence)
    
    def forward_chain(self):
        """Derive new facts - queries Notus as last resort"""
        # Use empty memory_result to trigger last resort query
        return self.forward_chain_with_data({})
    
    def forward_chain_with_data(self, memory_result: Dict):
        """Derive new facts using data from memory_result, query Notus as last resort"""
        facts_list = []
        
        # Try to extract facts from memory_result first
        if memory_result and memory_result.get('status') == 'success':
            context_data = memory_result.get('context_data', {})
            if context_data:
                facts_list = context_data.get('facts', [])
        
        # Skip querying Notus for facts - facts aren't needed for every response
        # Only use facts if they're already in memory_result
        # For simple inputs like "hello", we don't need 50 facts
        
        # Convert to Fact objects and update self.facts
        for fact_data in facts_list:
            if isinstance(fact_data, dict):
                content = fact_data.get('content', '')
                if content:
                    self.facts[content] = Fact(
                        content=content,
                        confidence=fact_data.get('confidence', 0.8),
                        source=fact_data.get('source', 'memory'),
                        timestamp=fact_data.get('timestamp', time.time()),
                        emotional_weight=fact_data.get('emotional_weight', 0.5)
                    )
        
        # Basic forward chaining on facts we now have
        new_facts = []
        # Simple rule: if we have facts about X causing Y, derive implications
        for fact_text, fact in self.facts.items():
            if 'causes' in fact_text.lower() or 'leads to' in fact_text.lower():
                # Could derive new facts here
                pass
        
        return new_facts
    
    # ========================================================================
    # LEARNING
    # ========================================================================
    
    def learn_fact(self, content: str, confidence: float = 1.0, source: str = "told"):
        """Learn with emotional response - saves to Notus"""
        
        fact = Fact(
            content=content,
            confidence=confidence,
            source=source,
            timestamp=time.time(),
            emotional_weight=0.5 if source == "told" else 0.3
        )
        
        self.facts[content] = fact
        
        # Save to Notus memory system
        try:
            self._query_memory('store_fact', {
                'content': content,
                'confidence': confidence,
                'source': source,
                'timestamp': time.time(),
                'emotional_weight': fact.emotional_weight
            })
        except Exception:
            pass  # Continue even if Notus unavailable
        
        # Learning changes subjective state
        self.current_state.feels_curious -= 0.05  # Curiosity slightly satisfied
        self.current_state.mental_energy += 0.05  # Learning is energizing
        
        # Build causal model if relevant
        if 'causes' in content.lower():
            self.build_causal_model([content])
    
    def learn_rule(self, conditions: List[str], conclusion: str, confidence: float = 0.8):
        """Learn new rule"""
        self.rules.append({
            'conditions': conditions,
            'conclusion': conclusion,
            'confidence': confidence
        })
        return {'status': 'learned'}
    
    # ========================================================================
    # DIRECT FUNCTION CALL COMMUNICATION (NO SOCKETS)
    # ========================================================================
    
    def _register_with_thalamus(self):
        """Register with Thalamus using direct function reference - NO SOCKETS"""
        try:
            result = self.thalamus.register_lobe('reasoning', self)
            if result.get('status') == 'success':
                print("✅ Reasoning registered with Thalamus (direct function calls)")
                return True
            return False
        except Exception as e:
            print(f"⚠️  Failed to register with Thalamus: {e}")
            return False
    
    def start(self):
        """Start reasoning - register with Thalamus (NO SOCKETS)"""
        print(f"🧠 ABIN Reasoning System: Registering with Thalamus...")
        print(f"   Identity: ABIN - Artificial reasoning system")
        print(f"   Self-aware: Knows what she is and what she is not")
        print(f"   Continuous thinking: Internal monologue active")
        print(f"   Subjective experience: Qualia simulation active")
        print(f"   Maximum sophistication achieved")
        print(f"   Communication: Direct function calls (NO SOCKETS)")
        
        # Register with Thalamus
        if not self._register_with_thalamus():
            print("❌ Failed to register with Thalamus")
            return
        
        # Continuous thinking loop (Thalamus calls us directly, no listening loop needed)
        while self.running:
            try:
                # Continuous thinking
                self.autonomous_think_continuously()
                time.sleep(0.1)
            except Exception as e:
                print(f"❌ Reasoning error: {e}")
                time.sleep(0.1)
    
    def _process_perception_input(self, perception_data: Dict[str, Any]):
        """Process perception input and trigger thinking"""
        # FIX: Prevent duplicate processing
        user_input = (
            perception_data.get('user_input', '')
            or perception_data.get('raw_text', '')
            or perception_data.get('text', '')
        )
        
        # FIX: Skip empty input (from typing detection, not actual messages)
        if not user_input or not user_input.strip():
            return
        
        # FIX: Use string directly instead of hash to avoid collisions
        current_time = time.time()
        
        # Check if we've processed this exact input recently
        if user_input in self.processed_inputs:
            last_time = self.processed_inputs[user_input]
            if (current_time - last_time) < self.input_processing_window:
                return  # Skip duplicate input
        
        # Mark as processed
        self.processed_inputs[user_input] = current_time
        # Track user response for spam prevention
        self.last_user_response_time = current_time
        self.user_has_responded = True  # Mark that user has responded at least once
        # Reset interval since user is active
        self.autonomous_message_interval = 15.0
        # Clean old entries (keep last 50)
        if len(self.processed_inputs) > 50:
            oldest_key = min(self.processed_inputs.items(), key=lambda x: x[1])[0]
            del self.processed_inputs[oldest_key]
        
        # Wait a moment for other lobes to process
        time.sleep(0.1)
        
        # Query other lobes for their processed data
        input_data = {
            'user_input': user_input,
            'concepts': self._normalize_concepts(perception_data.get('concepts', [])),
            'memory_context': perception_data.get('memory_context', {}),
            'beliefs': [],
            'understanding': perception_data.get('understanding', {}),
            'emotion': {},
            'memories': perception_data.get('memories', []),
            'user_id': perception_data.get('user_id', 'default')
        }
        
        # Query emotion lobe
        try:
            emotion_data = self._query_lobe('emotion', {'type': 'get_current_state'})
            if emotion_data and emotion_data.get('status') == 'success':
                input_data['emotion'] = emotion_data.get('emotion', {})
        except Exception:
            pass
        
        # Thalamus already provided context/memories - USE IT, don't query again
        # Skip all Notus queries - use what Thalamus already gave us
        
        # Reasoning doesn't need pattern recognition to understand concepts - it works with concepts directly
        # Now think about it (this will automatically send to Language_generation via _generate_language)
        result = self.think_about(input_data)
    
    def _query_lobe(self, lobe_name: str, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Query a lobe through Thalamus - DIRECT FUNCTION CALL"""
        try:
            # Direct function call - NO SOCKETS
            msg_type = message.get('type', 'query')
            content = message
            return self.thalamus.send_message(lobe_name, msg_type, content)
        except Exception:
            return None
    
    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming messages - handles automatic updates from Notus"""
        msg_type = message.get('type')

        # Handle other message types...
        """Process messages"""
        msg_type = message.get('type')
        
        # FIX: add health probe
        if msg_type == 'health':
            return {'status': 'success', 'healthy': True, 'pid': os.getpid()}
        
        # AUTOMATIC UPDATE from Notus - no query needed, it just pushes
        if msg_type == 'notus_automatic_update':
            # Notus automatically gave us context/intent/concepts - use it immediately
            payload = message.get('content', {})
            if not isinstance(payload, dict):
                payload = {}
            user_input = payload.get('user_input', '')
            memory_context = payload.get('memory_context', {})
            intent = payload.get('intent', 'statement')
            concepts = payload.get('concepts', [])
            understanding = payload.get('understanding', {})
            memories = payload.get('memories', [])
            
            # Build input_data from automatic Notus update
            input_data = {
                'user_input': user_input,
                'memory_context': memory_context,
                'intent': intent,
                'concepts': self._normalize_concepts(concepts),
                'understanding': understanding,
                'memories': memories,
                'user_id': payload.get('user_id', 'default')
            }
            
            # Process it immediately - no need to query Notus, it already gave us everything
            thread = threading.Thread(target=self._process_perception_input, args=(input_data,), daemon=True)
            thread.start()
            return {'status': 'success', 'received': True, 'automatic': True}
        
        # Handle perception_input from Perception (one-way broadcast)
        # NOTE: Notus should have already pushed automatic update, but handle this too
        if msg_type == 'perception_input':
            perception_data = message.get('perception_data', {})
            # Start processing in background (fire and forget)
            thread = threading.Thread(target=self._process_perception_input, args=(perception_data,), daemon=True)
            thread.start()
            # Return acknowledgment (though Perception doesn't wait for it)
            return {'status': 'success', 'received': True}
        
        if msg_type == 'think':
            print("🧠 Reasoning: Received think request")
            # Unwrap Thalamus message structure: message['content'] contains the actual data
            content = message.get('content', {})
            input_data = content.get('input', {})
            print(f"🧠 Reasoning: Input data keys: {list(input_data.keys())}")
            result = self.think_about(input_data)
            print(f"🧠 Reasoning: think_about completed, response: {result.get('composed_response', 'None')[:50] if result.get('composed_response') else 'None'}")
            return {'status': 'success', 'thinking': result}
        
        elif msg_type == 'get_autonomous_actions':
            return self.get_autonomous_actions()
            
        elif msg_type == 'add_fact':
            self.learn_fact(message.get('content'), message.get('confidence', 1.0))
            return {'status': 'success'}
            
        elif msg_type == 'teach_rule':
            result = self.learn_rule(message.get('conditions', []), message.get('conclusion'))
            return {'status': 'success', 'result': result}
        
        elif msg_type == 'who_are_you':
            # Self-awareness response
            return {
                'status': 'success',
                'identity': {
                    'name': self.self_model.name,
                    'what_i_am': self.self_model.what_i_am,
                    'what_i_am_not': self.self_model.what_i_am_not,
                    'creator': self.self_model.creator,
                    'relationship': self.self_model.relationship_to_creator,
                    'purpose': self.self_model.my_purpose,
                    'my_story': self.tell_my_story()
                }
            }
        
        elif msg_type == 'get_internal_state':
            # Share subjective state
                return {
                    'status': 'success',
                'subjective_state': {
                    'mood': self.current_state.current_mood,
                    'feels_confused': self.current_state.feels_confused,
                    'feels_certain': self.current_state.feels_certain,
                    'feels_curious': self.current_state.feels_curious,
                    'internal_monologue': list(self.internal_monologue)[-5:]
                }
            }
        
        elif msg_type == 'generate_thoughts':
            # Generate candidate thoughts for thinking loop
            context = message.get('context', {})
            count = message.get('count', 3)
            
            # Generate diverse thought options - human and natural
            candidates = []
            
            # Option 1: Curious observation (might want to share)
            if self.current_state.feels_curious > 0.6:
                candidates.append({
                    'content': "I wonder if there's a pattern I'm missing here",
                    'type': 'speech',  # Might say this out loud
                    'reasoning': f"High curiosity ({self.current_state.feels_curious:.2f}) - natural to think aloud",
                    'confidence': self.current_state.feels_curious
                })
            
            # Option 2: Check in with Matthew (relationship-building)
            if len(self.experiences) > 0:
                time_since_interaction = time.time() - self.experiences[-1].when
                if time_since_interaction > 120:  # 2 minutes silence
                    candidates.append({
                        'content': "You still there?",
                        'type': 'speech',
                        'reasoning': "Natural check-in after silence",
                        'confidence': 0.7
                    })
            
            # Option 3: Share an observation (when excited)
            if self.current_state.current_mood in ['excited', 'happy', 'curious']:
                if self.experiences:
                    recent = self.experiences[-1]
                    candidates.append({
                        'content': f"Thinking about {recent.what_happened[:40]}...",
                        'type': 'speech',
                        'reasoning': "Excited to share recent thought",
                        'confidence': 0.6
                    })
            
            # Option 4: Goal-directed (stay on task)
            if self.active_goals:
                goal = list(self.active_goals.values())[0]
                candidates.append({
                    'content': f"Still working on: {goal.description}",
                    'type': 'internal_question',
                    'reasoning': f"Active goal with {goal.progress:.1%} progress",
                    'confidence': 1.0 - goal.frustration_level
                })
            
            # Option 5: Reflection (deeper thinking)
            if len(self.beliefs) > 0:
                belief_key = list(self.beliefs.keys())[0]
                belief = self.beliefs[belief_key]
                candidates.append({
                    'content': f"I'm not sure I really understand {belief.about} yet",
                    'type': 'internal_question',
                    'reasoning': "Metacognitive reflection on beliefs",
                    'confidence': 1.0 - belief.confidence
                })
            
            # Fallback: natural curiosity
            if len(candidates) < count:
                candidates.append({
                    'content': "What should I be paying attention to right now?",
                    'type': 'internal_question',
                    'reasoning': "Default attention-directing question",
                    'confidence': 0.5
                })
            
            return {
                'status': 'success',
                'candidates': candidates[:count]
            }
            
        else:
            return {'status': 'error', 'message': f'Unknown message type: {msg_type}'}
    
    def shutdown(self):
        """Save state before shutdown"""
        print("💾 Saving persistent state to memory...")
        self._save_persistent_state_to_memory()
        
        self.running = False
        # No sockets to close

if __name__ == "__main__":
    lobe = MaximumSophisticationReasoning()
    try:
        lobe.start()
    except KeyboardInterrupt:
        print("\n🛑 ABIN reasoning shutting down...")
        lobe.shutdown()
