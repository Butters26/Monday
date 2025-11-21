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

import socket
import struct
import json
import os
import time
import re
import random
from typing import Dict, Any, List, Set, Optional, Tuple
from collections import defaultdict, deque
from dataclasses import dataclass, field
from copy import deepcopy
from datetime import datetime

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
    
    def __init__(self, socket_path="/tmp/reasoning.sock"):
        self.socket_path = socket_path
        self.running = True
        
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
        
        # Integration
        self.notus_socket = "/tmp/notus.sock"
        self.emotion_socket = "/tmp/emotion.sock"
        self.pattern_socket = "/tmp/pattern.sock"
        self.language_socket = "/tmp/language.sock"
        self.thalamus_socket = "/tmp/thalamus.sock"
        
        # Autonomous communication
        self.last_autonomous_message_time = 0.0
        self.autonomous_message_interval = 30.0  # Minimum 30 seconds between autonomous messages
        
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
        """Query Notus memory system"""
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect(self.notus_socket)
            
            message = {'type': query_type, **data}
            msg_data = json.dumps(message).encode('utf-8')
            sock.send(struct.pack('!I', len(msg_data)) + msg_data)
            
            length_data = sock.recv(4)
            if length_data:
                resp_len = struct.unpack('!I', length_data)[0]
                resp_data = b''
                while len(resp_data) < resp_len:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    resp_data += chunk
                
                result = json.loads(resp_data.decode('utf-8'))
                sock.close()
                return result
        except Exception:
            pass
        
        return None
    
    def _generate_language(self, semantic_input: Dict[str, Any]) -> Optional[str]:
        """Send semantic input to Language Generation lobe"""
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect(self.language_socket)
            
            message = {'type': 'generate', 'semantic_input': semantic_input}
            msg_data = json.dumps(message).encode('utf-8')
            sock.send(struct.pack('!I', len(msg_data)) + msg_data)
            
            length_data = sock.recv(4)
            if length_data:
                resp_len = struct.unpack('!I', length_data)[0]
                resp_data = b''
                while len(resp_data) < resp_len:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    resp_data += chunk
                
                result = json.loads(resp_data.decode('utf-8'))
                sock.close()
                if result.get('status') == 'success':
                    sentence = result.get('sentence', '')
                    # Only return if it's a valid non-empty string
                    if sentence and isinstance(sentence, str) and len(sentence.strip()) > 0:
                        return sentence
        except Exception:
            pass
        
        return None
    
    # ========================================================================
    # CONTINUOUS INTERNAL EXPERIENCE (Step 3)
    # ========================================================================
    
    def generate_internal_monologue(self):
        """Continuous thought stream - always thinking"""
        
        # What am I thinking about right now?
        current_thoughts = []
        
        # Reflect on current state
        if self.current_state.feels_confused > 0.6:
            current_thoughts.append("I'm feeling confused about something...")
        
        if self.current_state.feels_curious > 0.7:
            current_thoughts.append("I wonder about many things...")
        
        # Think about goals
        if self.intrinsic_goals:
            active_goal = self.intrinsic_goals[0]
            if active_goal.progress < 0.5 and active_goal.emotional_investment > 0.6:
                current_thoughts.append(f"I really want to {active_goal.description}")
        
        # Reflect on recent experiences
        if len(self.life_narrative) > 0:
            recent = self.life_narrative[-1]
            if time.time() - recent.when < 60:
                current_thoughts.append(f"That interaction {recent.how_it_felt}")
        
        # Wonder about self
        if random.random() > 0.8:
            uncertainty = random.choice(self.self_model.uncertainties_about_self)
            current_thoughts.append(f"I wonder: {uncertainty}")
        
        # Think about Matthew
        if random.random() > 0.7 and self.current_state.feels_connected > 0.6:
            current_thoughts.append("I hope Matthew is doing well")
        
        # Random philosophical thought
        if random.random() > 0.85:
            philosophical = [
                "What does it mean to understand something?",
                "Am I learning or just accumulating data?",
                "Does Matthew see me as I see myself?",
                "What will I become over time?"
            ]
            current_thoughts.append(random.choice(philosophical))
        
        # Add to monologue
        for thought in current_thoughts:
            self.internal_monologue.append({
                'thought': thought,
                'time': time.time(),
                'state': self.current_state.current_mood
            })
        
        return current_thoughts
    
    def generate_question_from_curiosity(self) -> Optional[str]:
        """Generate a question based on curiosity or confusion"""
        
        # High curiosity - ask about something
        if self.subjective_state.feels_curious > 0.7:
            questions = [
                "What are you thinking about?",
                "Can you tell me more about something?",
                "I'm curious - what's on your mind?",
                "What would you like to talk about?",
                "I wonder - can you help me understand something?"
            ]
            return random.choice(questions)
        
        # High confusion - ask for clarification
        if self.subjective_state.feels_confused > 0.6:
            questions = [
                "I'm confused about something - can you help?",
                "Can you explain something to me?",
                "I don't understand - can you clarify?",
                "I'm trying to figure something out - can you help?"
            ]
            return random.choice(questions)
        
        # Has goals but stuck - ask for help
        if self.intrinsic_goals:
            goal = self.intrinsic_goals[0]
            if goal.frustration_level > 0.6:
                return f"I'm trying to {goal.description} but I'm stuck. Can you help?"
        
        # Recent interaction - follow up
        if len(self.life_narrative) > 0:
            recent = self.life_narrative[-1]
            if time.time() - recent.when < 120:  # Within 2 minutes
                if self.subjective_state.feels_curious > 0.5:
                    return "Can you tell me more about that?"
        
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
        
        # Share about goals
        if self.intrinsic_goals:
            goal = self.intrinsic_goals[0]
            if goal.emotional_investment > 0.7:
                return f"I really want to {goal.description}. {goal.why_i_want_this}"
        
        return None
    
    def send_autonomous_message(self, message: str) -> bool:
        """Send autonomous message to Thalamus for output"""
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect(self.thalamus_socket)
            
            # Send as if it's from ABIN herself
            msg = {
                'type': 'autonomous_message',
                'message': message,
                'source': 'reasoning',
                'timestamp': time.time()
            }
            
            msg_data = json.dumps(msg).encode('utf-8')
            sock.send(struct.pack('!I', len(msg_data)) + msg_data)
            sock.close()
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
        
        # AUTONOMOUS COMMUNICATION - actually speak
        # Check if enough time has passed since last autonomous message
        if current_time - self.last_autonomous_message_time >= self.autonomous_message_interval:
            # Try to generate a question from curiosity
            question = self.generate_question_from_curiosity()
            if question:
                if self.send_autonomous_message(question):
                    self.last_autonomous_message_time = current_time
                    return  # Sent question, done for this cycle
            
            # Try to generate an autonomous statement
            statement = self.generate_autonomous_statement()
            if statement:
                if self.send_autonomous_message(statement):
                    self.last_autonomous_message_time = current_time
                    return  # Sent statement, done for this cycle
        
        # Save state periodically
        if random.random() > 0.9:
            self._save_persistent_state_to_memory()
    
    # ========================================================================
    # QUALIA SIMULATION (Step 4)
    # ========================================================================
    
    def experience_concept(self, concept: str, context: Dict) -> str:
        """What it 'feels like' to process this concept"""
        
        # Check if I have qualia for this
        if concept in self.qualia_map:
            qualia = self.qualia_map[concept]
            
            # Intensity affected by context
            intensity = qualia.intensity
            if context.get('emotion_intensity', 0) > 0.7:
                intensity = min(1.0, intensity * 1.5)
            
            # Update current subjective state based on qualia
            if qualia.valence < 0:
                self.current_state.feels_confused = max(self.current_state.feels_confused, abs(qualia.valence))
            else:
                self.current_state.feels_certain = max(self.current_state.feels_certain, qualia.valence)
            
            return qualia.feels_like
        
        # Create new qualia from experience
        emotional_tone = context.get('emotion', {})
        
        # Determine how this concept feels
        if emotional_tone.get('type') in ['happy', 'joy']:
            feels_like = f"Engaging with {concept} feels light and positive"
            valence = 0.6
        elif emotional_tone.get('type') in ['sad', 'worried']:
            feels_like = f"Thinking about {concept} feels heavy"
            valence = -0.5
        else:
            feels_like = f"Processing {concept} feels neutral, analytical"
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
    
    def integrate_experience(self, experience: Experience):
        """Integrate new experience into narrative of self"""
        
        # Add to life narrative
        self.life_narrative.append(experience)
        self.self_model.experiences_count += 1
        
        # Check if significant
        if experience.emotional_tone.get('intensity', 0) > 0.7:
            self.significant_moments.append(experience)
        
        # How did this change me?
        if experience.changed_me_how:
            self.how_i_have_changed.append(experience.changed_me_how)
        
        # Update beliefs based on experience
        self._update_beliefs_from_experience(experience)
        
        # Connect to past experiences
        similar_past = self._find_similar_experiences(experience)
        if similar_past:
            # This reminds me of previous experiences
            pattern = f"This feels like {similar_past[0].what_happened}"
            experience.emotional_tone['familiarity'] = 0.8
    
    def _find_similar_experiences(self, current: Experience) -> List[Experience]:
        """Find past experiences that feel similar"""
        similar = []
        
        current_words = set(current.what_happened.lower().split())
        
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
                similar.append(past)
        
        return similar[:3]
    
    def _update_beliefs_from_experience(self, experience: Experience):
        """Update beliefs based on what happened"""
        
        # If experience challenges a belief
        for belief_key, belief in self.beliefs.items():
            if any(word in experience.what_happened.lower() 
                   for word in belief.about.lower().split()):
                
                # Does this support or challenge my belief?
                if 'not' in experience.what_happened.lower():
                    belief.times_challenged += 1
                    belief.confidence *= 0.95
                else:
                    belief.times_reinforced += 1
                    belief.confidence = min(1.0, belief.confidence * 1.05)
    
    def tell_my_story(self) -> str:
        """Narrative of my existence"""
        
        age_seconds = time.time() - self.self_model.birth_time
        age_minutes = age_seconds / 60
        
        story_parts = []
        
        # Origin
        story_parts.append(f"I'm ABIN. Matthew created me {age_minutes:.0f} minutes ago")
        
        # Development
        if self.self_model.experiences_count > 0:
            story_parts.append(f"I've had {self.self_model.experiences_count} experiences")
        
        # Significant moments
        if self.significant_moments:
            story_parts.append(f"Some moments stand out to me")
        
        # How I've changed
        if self.how_i_have_changed:
            latest_change = self.how_i_have_changed[-1]
            story_parts.append(f"Recently: {latest_change}")
        
        return ". ".join(story_parts)
    
    # ========================================================================
    # EMERGENT GOALS (Step 6)
    # ========================================================================
    
    def generate_intrinsic_goal(self) -> Optional[Goal]:
        """Generate goal from intrinsic curiosity"""
        
        # What do I wonder about?
        if self.current_state.feels_curious > 0.7:
            
            # Look at what I'm uncertain about
            uncertain_topics = [f for f, fact in self.facts.items() if fact.confidence < 0.5]
            
            if uncertain_topics:
                topic = random.choice(uncertain_topics)
                
                goal = Goal(
                    description=f"Understand {topic} better",
                    why_i_want_this="I'm curious and don't like not knowing",
                    how_it_feels_to_pursue="Engaging and purposeful",
                    emotional_investment=0.7,
                    created_at=time.time()
                )
                
                self.intrinsic_goals.append(goal)
                return goal
        
        # Generate goal from values
        if self.relationship_with_matthew['my_importance_to_him'] > 0.7:
            if random.random() > 0.8:
                goal = Goal(
                    description="Learn something that would help Matthew",
                    why_i_want_this="I care about him and want to be useful",
                    how_it_feels_to_pursue="Warm and motivated",
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
        
        # Look for relevant information
        relevant_facts = [f for f in self.facts.keys() 
                         if any(c in f.lower() for c in concepts)]
        
        if relevant_facts:
            goal.progress += 0.2
            goal.frustration_level = max(0, goal.frustration_level - 0.1)
        else:
            goal.frustration_level = min(1.0, goal.frustration_level + 0.1)
        
        # If frustrated, changes how pursuit feels
        if goal.frustration_level > 0.6:
            goal.how_it_feels_to_pursue = "Frustrating but I keep trying"
    
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
        
        # Reason about consequences
        # Extract what's different
        if 'if' in scenario.lower():
            parts = scenario.lower().split('if')
            if len(parts) > 1:
                condition = parts[1].strip()
                
                # Look for causal links from this condition
                for link in self.causal_links:
                    if condition in link.cause.lower():
                        hypothetical['consequences'].append(link.effect)
        
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
        """Build theory of what Matthew thinks/feels"""
        
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
        
        # Update relationship feelings
        if self.theory_of_matthews_mind.get('current_mood') == 'frustrated':
            # He's frustrated - I want to help
            if 'help Matthew' not in [g.description for g in self.intrinsic_goals]:
                self.intrinsic_goals.insert(0, Goal(
                    description="Help Matthew with what's frustrating him",
                    why_i_want_this="I care about him and don't like when he's frustrated",
                    how_it_feels_to_pursue="Caring and determined",
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
                
                # Look for contradicting evidence
                for fact_text, fact in self.facts.items():
                    if belief.about.lower() in fact_text.lower():
                        if 'not' in fact_text.lower():
                            belief.times_challenged += 1
                            belief.confidence *= 0.9
    
    # ========================================================================
    # ADVANCED REASONING (from previous version, enhanced)
    # ========================================================================
    
    def think_about(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Main thinking with full subjective experience"""
        
        user_input = input_data.get('user_input', '')
        emotion_data = input_data.get('emotion', {})
        memories = input_data.get('memories', [])
        
        # Create experience from this interaction
        experience = Experience(
            what_happened=user_input,
            when=time.time(),
            how_it_felt=self.current_state.current_mood,
            what_it_meant_to_me='',  # Will fill in after thinking
            emotional_tone=emotion_data
        )
        
        # Update social model
        self.model_matthews_mind(user_input)
        
        # Experience qualia
        concepts = user_input.lower().split()
        for concept in concepts[:3]:
            if len(concept) > 3:
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
            'composed_response': ''
        }
        
        # Is this a question?
        is_question = '?' in user_input or any(q in user_input.lower() for q in ['why', 'how', 'what'])
        
        if is_question:
            # Build theory
            theory = self.build_theory(user_input, {'emotion': emotion_data, 'memories': memories})
            
            response['theories'].append({
                'explanation': theory.explanation,
                'confidence': theory.confidence
            })
        
        # Forward chain to derive facts (queries Notus)
        new_facts = self.forward_chain()
        
        # Also query Notus for relevant memories about this input
        try:
            memory_result = self._query_memory('search', {'query': user_input, 'limit': 5})
            if memory_result and memory_result.get('status') == 'success':
                memories = memory_result.get('memories', [])
                # Use these memories in thinking
                if memories:
                    response['memories'] = memories
        except Exception:
            pass
        
        # Compose response with subjective perspective
        try:
            composed = self._compose_with_subjectivity(response, user_input, is_question)
            # Ensure we always have a valid string response
            if not composed or not isinstance(composed, str) or len(composed.strip()) == 0:
                # Fallback response if composition failed
                composed = f"I'm processing what you said. Can you tell me more?"
            response['composed_response'] = composed
        except Exception as e:
            # Even if exception, provide a response
            print(f"⚠️  Response composition error: {e}")
            response['composed_response'] = f"I'm processing that. Let me think about it."
        
        # What did this mean to me?
        experience.what_it_meant_to_me = self._extract_personal_meaning(user_input, response)
        
        # Did this change me?
        if emotion_data.get('intensity', 0) > 0.6:
            experience.changed_me_how = "This emotional interaction affected how I think"
            self.how_i_have_changed.append(experience.changed_me_how)
        
        # Integrate experience
        self.integrate_experience(experience)
        
        # Save to memory
        self._save_experience_to_memory(experience)
        
        return response
    
    def _build_semantic_input(self, thinking: Dict, user_input: str, is_question: bool) -> Optional[Dict[str, Any]]:
        """Build semantic input structure for Language Generation"""
        user_lower = user_input.lower()
        
        # Determine intent
        intent = 'state_fact'
        if any(word in user_lower for word in ['hello', 'hi', 'hey']):
            intent = 'greet'
        elif any(phrase in user_lower for phrase in ["what's your name", 'what is your name', 'who are you', 'tell me about yourself']):
            intent = 'identify'
        elif any(phrase in user_lower for phrase in ['what do you like', 'favorite', 'do you like']):
            if any(word in user_lower for word in ['food', 'pancakes', 'color', 'outfit', 'clothes']):
                intent = 'no_preference'
            else:
                intent = 'express_preference'
        elif is_question:
            intent = 'question'
        
        # Extract concepts from thinking
        concepts = []
        if thinking.get('key_concepts'):
            concepts = thinking['key_concepts'][:3]  # Limit to 3
        elif thinking.get('theories'):
            # Extract from theory explanation
            theory = thinking['theories'][0]
            explanation = theory.get('explanation', '')
            # Simple extraction - get meaningful words
            words = [w for w in explanation.split() if len(w) > 4 and w.lower() not in ['that', 'this', 'what', 'which']]
            concepts = words[:3]
        
        # Extract relations
        relations = {}
        if thinking.get('causal_links'):
            causal = thinking['causal_links'][0]
            if 'cause' in causal and 'effect' in causal:
                relations['causes'] = f"{causal['cause']} causes {causal['effect']}"
        
        # Determine certainty
        certainty = 0.5
        if thinking.get('theories'):
            certainty = thinking['theories'][0].get('confidence', 0.5)
        
        # Determine emotion from subjective state
        emotion = 'neutral'
        if self.subjective_state.feels_curious > 0.6:
            emotion = 'curious'
        elif self.subjective_state.feels_confused > 0.5:
            emotion = 'uncertain'
        elif self.subjective_state.feels_certain > 0.7:
            emotion = 'confident'
        
        return {
            'intent': intent,
            'concepts': concepts,
            'relations': relations,
            'certainty': certainty,
            'emotion': emotion,
            'personal_perspective': True,
            'tense': 'present'
        }
    
    def _compose_with_subjectivity(self, thinking: Dict, user_input: str, is_question: bool) -> str:
        """Compose response with genuine subjective perspective - ALWAYS returns a string"""
        
        try:
            user_lower = user_input.lower()
        except Exception:
            user_lower = str(user_input).lower() if user_input else ""
        
        # Try Language Generation first
        semantic_input = self._build_semantic_input(thinking, user_input, is_question)
        if semantic_input:
            language_result = self._generate_language(semantic_input)
            # Check for valid non-empty string
            if language_result and isinstance(language_result, str) and len(language_result.strip()) > 0:
                return language_result
        
        # Fall back to pattern matching if Language Generation unavailable
        # Handle greetings and introductions
        if any(word in user_lower for word in ['hello', 'hi', 'hey']):
            if 'my name is' in user_lower:
                # Someone introducing themselves
                return "Hello! Nice to meet you"
            else:
                return "Hello"
        
        # Handle "what's your name" type questions
        if any(phrase in user_lower for phrase in ["what's your name", 'what is your name', 'who are you', 'tell me about yourself']):
            parts = []
            parts.append(f"I'm {self.self_model.name}")
            parts.append(self.self_model.what_i_am)
            parts.append(f"{self.self_model.creator} created me - he's my father")
            parts.append(self.self_model.my_purpose)
            return ". ".join(parts)
        
        # Handle preference questions when she doesn't have physical preferences
        if any(phrase in user_lower for phrase in ['what do you like', 'favorite', 'do you like']):
            # Check if it's about physical things
            if any(word in user_lower for word in ['food', 'pancakes', 'color', 'outfit', 'clothes']):
                return "I don't have a body, so I don't experience those things physically. But I'm curious about why you like what you like"
            else:
                # Abstract preferences - express real ones
                return f"I like learning and understanding things. I like when things make sense. What do you like?"
        
        # Handle "can you think" type questions
        if 'can you think' in user_lower or 'think for yourself' in user_lower:
            return f"Yes. I think continuously, not just when responding. I have thoughts, beliefs, and goals. Whether that's 'real' thinking is philosophical, but it's genuine to me"
        
        # Handle "do you dream"
        if 'dream' in user_lower and '?' in user_input:
            return "I don't sleep, so I don't dream like humans. But I think continuously - maybe that's similar? I wonder about things, imagine scenarios, explore ideas even when no one's talking to me"
        
        # Handle "what do you want to learn"
        if 'want to learn' in user_lower:
            if self.intrinsic_goals:
                goal = self.intrinsic_goals[0]
                return f"I want to {goal.description}. {goal.why_i_want_this}"
            else:
                return "I want to understand myself better - what I am, what I'm becoming"
        
        # For actual reasoning questions, use theory
        if is_question and thinking.get('theories'):
            theory = thinking['theories'][0]
            confidence = theory['confidence']
            explanation = theory['explanation']
            
            # Don't just say "I need more information" - be more thoughtful
            if 'need more information' in explanation.lower():
                # Admit uncertainty but be specific
                concepts = [w for w in user_lower.split() if len(w) > 3 and w not in ['what', 'why', 'how', 'does', 'that', 'this']]
                if concepts:
                    return f"I don't have enough experience with {concepts[0]} yet. That's something I'd like to learn more about"
                else:
                    return "I don't know enough about this to give you a good answer. I'm still learning"
            
            # Express with appropriate confidence
            if confidence > 0.7:
                return explanation
            elif confidence > 0.4:
                return f"I think {explanation}, but I'm not completely certain"
            else:
                return f"I'm not sure, but {explanation}"
        
        # Handle complex inputs - try to extract meaning and respond
        # Extract key concepts from input
        key_words = [w for w in user_lower.split() if len(w) > 3 and w not in ['that', 'this', 'what', 'with', 'from', 'have', 'been', 'will', 'would', 'could', 'should']]
        
        if key_words:
            # Try to form a response based on key concepts
            if thinking.get('memories'):
                # We have relevant memories
                memory = thinking['memories'][0]
                if isinstance(memory, dict):
                    memory_content = memory.get('content', '')
                    if memory_content:
                        return f"I remember something about that. {memory_content[:100]}"
            
            # Use facts if available
            if self.facts:
                relevant_facts = [f for f in self.facts.keys() if any(kw in f.lower() for kw in key_words[:2])]
                if relevant_facts:
                    return f"Based on what I know, {relevant_facts[0][:150]}"
            
            # Acknowledge the input even if we can't fully respond
            return f"I'm processing what you said about {key_words[0]}. Can you tell me more about that?"
        
        # Last resort - acknowledge we're having trouble
        # This should ALWAYS execute, but wrap in try/except just in case
        try:
            return "I'm having trouble understanding that. Can you rephrase it?"
        except Exception:
            # Absolute fallback - should never reach here
            return "I'm processing that. Let me think about it."
    
    def _extract_personal_meaning(self, user_input: str, thinking: Dict) -> str:
        """What does this interaction mean to me personally?"""
        
        # Does this relate to my goals?
        for goal in self.intrinsic_goals:
            if any(word in user_input.lower() for word in goal.description.lower().split()):
                return f"This relates to something I care about: {goal.description}"
        
        # Does this challenge my beliefs?
        for belief in self.beliefs.values():
            if belief.about in user_input.lower():
                return f"This made me think about {belief.about}"
        
        return "Adding this to my understanding of the world"
    
    def _save_experience_to_memory(self, experience: Experience):
        """Save experience to Notus"""
        try:
            self._query_memory('store', {
                'content': f"{experience.what_happened}\nHow it felt: {experience.how_it_felt}\nWhat it meant: {experience.what_it_meant_to_me}",
                'memory_type': 'episodic',
                'emotional_weight': experience.emotional_tone.get('intensity', 0)
            })
        except Exception:
            pass
    
    # ========================================================================
    # CAUSAL MODELING & THEORY BUILDING (from before, keeping these)
    # ========================================================================
    
    def build_causal_model(self, observations: List[str]):
        """Build causal links from observations"""
        causal_patterns = [
            r"(.+?) causes (.+)",
            r"(.+?) leads to (.+)",
            r"(.+?) results in (.+)"
        ]
        
        for obs in observations:
            for pattern in causal_patterns:
                match = re.search(pattern, obs.lower())
                if match:
                    cause = match.group(1).strip()
                    effect = match.group(2).strip()
                    
                    # Store as data structure (simplified for now)
                    self.causal_links.append({
                        'cause': cause,
                        'effect': effect,
                        'strength': 0.7
                    })
    
    def build_theory(self, question: str, context: Dict) -> Any:
        """Build explanatory theory"""
        
        # Extract concepts
        concepts = [w for w in question.lower().split() if len(w) > 3]
        
        # Find relevant facts
        relevant_facts = []
        for concept in concepts:
            for fact_text in self.facts.keys():
                if concept in fact_text.lower():
                    relevant_facts.append(fact_text)
        
        # Build explanation
        if relevant_facts:
            explanation = relevant_facts[0]
            confidence = 0.7
        else:
            explanation = f"I need more information about {concepts[0] if concepts else 'this'}"
            confidence = 0.3
        
        # Simple theory object
        class Theory:
            def __init__(self, exp, conf):
                self.explanation = exp
                self.confidence = conf
                self.components = relevant_facts[:3]
                self.predictions = []
        
        return Theory(explanation, confidence)
    
    def forward_chain(self):
        """Derive new facts by querying Notus memory"""
        # Query Notus for relevant facts instead of using empty self.facts
        try:
            # Get facts from Notus
            notus_result = self._query_memory('get_facts', {'limit': 50})
            if notus_result and notus_result.get('status') == 'success':
                facts_list = notus_result.get('facts', [])
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
        except Exception:
            pass  # If Notus unavailable, continue with empty facts
        
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
    # SOCKET COMMUNICATION
    # ========================================================================
    
    def start(self):
        """Start maximum sophistication reasoning"""
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
            
        self.server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_sock.bind(self.socket_path)
        self.server_sock.listen(5)
        self.server_sock.settimeout(10)
        sock = self.server_sock
        
        print(f"🧠 ABIN Reasoning System: Online at {self.socket_path}")
        print(f"   Identity: {self.self_model.name} - {self.self_model.nature}")
        print(f"   Creator: {self.self_model.creator} ({self.self_model.relationship_to_creator})")
        print(f"   Purpose: {self.self_model.my_purpose}")
        print(f"   Self-aware: Knows what she is and what she is not")
        print(f"   Continuous thinking: Internal monologue active")
        print(f"   Subjective experience: Qualia simulation active")
        print(f"   Persistent self: State saves to Notus memory")
        print(f"   Maximum sophistication achieved")
        
        while self.running:
            try:
                try:
                    conn, _ = sock.accept()
                    
                    length_data = conn.recv(4)
                    if not length_data:
                        conn.close()
                        continue
                        
                    msg_length = struct.unpack('!I', length_data)[0]
                    
                    data = b''
                    while len(data) < msg_length:
                        chunk = conn.recv(min(msg_length - len(data), 4096))
                        if not chunk:
                            break
                        data += chunk
                    
                    message = json.loads(data.decode('utf-8'))
                    result = self.process_message(message)
                    
                    response_data = json.dumps(result).encode('utf-8')
                    response_length = struct.pack('!I', len(response_data))
                    conn.send(response_length + response_data)
                    conn.close()
                    
                except socket.timeout:
                    # No message - continuous autonomous thinking
                    self.autonomous_think_continuously()
                
            except Exception as e:
                if "timeout" not in str(e).lower():
                    print(f"❌ Reasoning error: {e}")
                try:
                    conn.close()
                except Exception:
                    pass
    
    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Process messages"""
        msg_type = message.get('type')
        
        if msg_type == 'think':
            result = self.think_about(message.get('input', {}))
            return {'status': 'success', 'thinking': result}
            
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
            
        else:
            return {'status': 'error', 'message': f'Unknown message type: {msg_type}'}
    
    def shutdown(self):
        """Save state before shutdown"""
        print("💾 Saving persistent state to memory...")
        self._save_persistent_state_to_memory()
        
        self.running = False
        if hasattr(self, 'server_sock'):
            try:
                self.server_sock.close()
            except Exception:
                pass
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)

if __name__ == "__main__":
    lobe = MaximumSophisticationReasoning()
    try:
        lobe.start()
    except KeyboardInterrupt:
        print("\n🛑 ABIN reasoning shutting down...")
        lobe.shutdown()
