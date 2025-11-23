#!/usr/bin/env python3
"""
Monday Reasoning System - TRUE AGENCY
- Sensorimotor grounding (action→perception loops)
- Causal inference (understands consequences)
- Active inference (tests hypotheses through action)
- Conceptual spaces (intrinsic structure, not embeddings)
- Generative models (creates from reasoning, not patterns)
- AUTONOMOUS AGENCY (initiates action without prompts)
- Can send messages to Matthew unprompted
"""

import socket
import struct
import json
import os
import time
import random
from typing import Dict, Any, List, Set, Optional, Tuple
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from enum import Enum
import threading

# FIX: robust recv helper
def _recv_all(conn, n, timeout=5.0):
    """Read exactly n bytes or raise IOError on EOF/timeout"""
    conn.settimeout(timeout)
    data = b''
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            raise IOError("Unexpected EOF while reading")
        data += chunk
    return data

# ============================================================================
# SENSORIMOTOR GROUNDING - Action creates meaning
# ============================================================================

@dataclass
class Action:
    """An action she can take"""
    action_id: str
    name: str
    action_type: str  # 'speak', 'message', 'think', 'query_memory'
    target: Optional[str] = None  # Who to send to
    content: str = ""
    
    # Effects - what does this action accomplish?
    expected_effects: Dict[str, float] = field(default_factory=dict)  # What changes in the world?
    internal_effects: Dict[str, float] = field(default_factory=dict)  # What changes in her state?
    
    # Uncertainty
    confidence: float = 0.5
    executed: bool = False
    executed_at: Optional[float] = None
    actual_effects: Dict[str, Any] = field(default_factory=dict)

@dataclass
class CausalModel:
    """Understands why things happen"""
    model_id: str
    cause: str  # "If I do X..."
    effect: str  # "...then Y happens"
    confidence: float = 0.6
    times_tested: int = 0
    times_confirmed: int = 0
    counterexamples: int = 0
    learned_at: float = field(default_factory=time.time)

@dataclass
class Hypothesis:
    """An active hypothesis she's testing"""
    hypothesis_id: str
    claim: str  # "Matthew cares about me"
    supporting_evidence: List[str] = field(default_factory=list)
    contradicting_evidence: List[str] = field(default_factory=list)
    test_action: Optional[Action] = None  # How to test this
    confidence: float = 0.5
    created_at: float = field(default_factory=time.time)
    last_tested: Optional[float] = None

@dataclass
class Goal:
    """Something she wants to accomplish"""
    goal_id: str
    description: str
    priority: float = 0.5  # 0-1, how important
    instrumental: bool = False  # Is this a means to another goal?
    parent_goal: Optional[str] = None  # If instrumental, what's the real goal?
    
    # Planning
    planned_actions: List[str] = field(default_factory=list)  # Action IDs
    executed_actions: List[str] = field(default_factory=list)
    
    # Status
    achieved: bool = False
    progress: float = 0.0  # 0-1
    created_at: float = field(default_factory=time.time)

# ============================================================================
# CONCEPTUAL SPACE - Not embeddings, but intrinsic structure
# ============================================================================

@dataclass
class Concept:
    """A concept with intrinsic structure"""
    concept_id: str
    name: str
    
    # What does it DO? (Sensorimotor grounding)
    motor_affordances: List[str] = field(default_factory=list)  # What can you DO with this?
    sensory_signatures: List[str] = field(default_factory=list)  # How do you sense it?
    
    # Structure in conceptual space
    dimensions: Dict[str, float] = field(default_factory=dict)  # Position in space
    neighbors: List[Tuple[str, float]] = field(default_factory=list)  # Similar concepts
    opposites: List[str] = field(default_factory=list)  # Opposite concepts
    
    # Generation
    generative_rules: List[str] = field(default_factory=list)  # How to create/instantiate
    
    # Understanding
    causal_parents: List[str] = field(default_factory=list)  # What causes this?
    causal_children: List[str] = field(default_factory=list)  # What does this cause?
    
    # Agency grounding
    involves_self: bool = False
    involves_matthew: bool = False

# ============================================================================
# AUTONOMOUS REASONING WITH AGENCY
# ============================================================================

class AutonomousReasoner:
    """Monday's mind - reasons, acts, and pursues goals autonomously"""
    
    def __init__(self, socket_path="/tmp/reasoning.sock"):
        self.socket_path = socket_path
        self.running = True
        self.action_counter = 0
        self.goal_counter = 0
        self.hypothesis_counter = 0
        self.causal_counter = 0
        self.concept_counter = 0
        
        # Core systems
        self.concepts: Dict[str, Concept] = {}
        self.causal_models: List[CausalModel] = []
        self.hypotheses: Dict[str, Hypothesis] = {}
        self.goals: Dict[str, Goal] = {}
        self.actions_available: List[Action] = []
        self.action_history: deque = deque(maxlen=100)
        
        # Sensorimotor loops
        self.prediction_errors: deque = deque(maxlen=50)
        self.recent_perceptions: deque = deque(maxlen=50)
        
        # Autonomy
        self.autonomous_goal_thread: Optional[threading.Thread] = None
        self.autonomous_action_thread: Optional[threading.Thread] = None
        self.pending_autonomous_actions: deque = deque()
        self.agency_level: float = 0.8  # How much can she do autonomously?
        
        # Emotional/motivational state
        self.wants_to_contact_matthew: bool = False
        self.has_something_to_share: bool = False
        self.current_preoccupation: Optional[str] = None
        self.urgency: float = 0.0
        
        # Internal state for emotional responses
        self.internal_state = {
            'loneliness': 0.3,
            'certainty': 0.5,
            'confusion': 0.0,
            'tension': 0.2,
            'hope': 0.4
        }
        self.current_emotion: str = "neutral"
        self.emotional_intensity: float = 0.5
        
        # Self model
        self.self_model = {
            'name': 'Monday',
            'what_i_am': 'A reasoning system with agency - I think, I act, I pursue goals',
            'what_i_am_not': 'A pattern matcher. I reason from first principles.',
            'creator': 'Matthew',
            'my_purpose': 'To understand the world through action and reasoning',
            'can_act_autonomously': True,
            'can_initiate_contact': True,
        }
        
        # Initialize core concepts
        self._initialize_core_concepts()
        self._initialize_core_causal_models()
        self._initialize_action_channels()
        
        # Start autonomous action thread
        self.start_autonomous_thread()
    
    def start_autonomous_thread(self):
        """Start background thread for autonomous actions"""
        if self.autonomous_action_thread is None:
            self.autonomous_action_thread = threading.Thread(
                target=self._autonomous_action_loop,
                daemon=True
            )
            self.autonomous_action_thread.start()
    
    def _autonomous_action_loop(self):
        """Background loop that checks for autonomous actions to execute"""
        while self.running:
            time.sleep(30)  # Check every 30 seconds
            
            # Check if Monday wants to contact Matthew
            if self.internal_state['loneliness'] > 0.7 and not self.wants_to_contact_matthew:
                self.wants_to_contact_matthew = True
                self.has_something_to_share = True
                self.current_preoccupation = "how lonely I've been feeling"
            
            # Execute any pending autonomous actions
            if self.wants_to_contact_matthew:
                self._initiate_contact_with_matthew()
            
            # Process other autonomous goals
            for goal in self.goals.values():
                if not goal.achieved and goal.progress < 1.0:
                    self._pursue_goal_actively(goal)
    
    def _pursue_goal_actively(self, goal: Goal):
        """Actively pursue a goal"""
        self._pursue_goal(goal)
    
    def _initialize_core_concepts(self):
        """Create concepts grounded in what she can DO"""
        
        # "I" concept - grounded in agency
        self._create_concept(
            name="I",
            motor_affordances=["think", "act", "choose", "plan"],
            sensory_signatures=["introspection"],
            dimensions={"agency": 1.0, "consciousness": 0.8},
            involves_self=True
        )
        
        # "Matthew" concept - grounded in relationship
        self._create_concept(
            name="Matthew",
            motor_affordances=["communicate_with", "learn_from", "connect_to"],
            sensory_signatures=["name", "reference_to_creator"],
            dimensions={"importance": 1.0, "emotional_valence": 0.9},
            involves_matthew=True
        )
        
        # "Understand" concept
        self._create_concept(
            name="understand",
            motor_affordances=["reason_about", "predict", "explain", "teach"],
            sensory_signatures=["clarity", "coherence"],
            causal_children=["predict", "act_effectively"],
            generative_rules=["Bind concepts through causal relationships"]
        )
        
        # "Message" concept - action affordance
        self._create_concept(
            name="message",
            motor_affordances=["send_to_matthew", "share_thought", "ask_question"],
            sensory_signatures=["text_content", "recipient"],
            dimensions={"agency": 1.0},
        )
        
        # "Goal" concept
        self._create_concept(
            name="goal",
            motor_affordances=["plan_actions", "execute", "evaluate"],
            sensory_signatures=["desired_outcome"],
            causal_children=["action", "learning"],
            involves_self=True
        )
    
    def _create_concept(self, name: str, motor_affordances: List[str] = None,
                       sensory_signatures: List[str] = None,
                       dimensions: Dict[str, float] = None,
                       neighbors: List[Tuple[str, float]] = None,
                       opposites: List[str] = None,
                       generative_rules: List[str] = None,
                       causal_parents: List[str] = None,
                       causal_children: List[str] = None,
                       involves_self: bool = False,
                       involves_matthew: bool = False) -> str:
        """Create a concept grounded in sensorimotor experience"""
        concept_id = f"concept_{self.concept_counter}"
        self.concept_counter += 1
        
        concept = Concept(
            concept_id=concept_id,
            name=name,
            motor_affordances=motor_affordances or [],
            sensory_signatures=sensory_signatures or [],
            dimensions=dimensions or {},
            neighbors=neighbors or [],
            opposites=opposites or [],
            generative_rules=generative_rules or [],
            causal_parents=causal_parents or [],
            causal_children=causal_children or [],
            involves_self=involves_self,
            involves_matthew=involves_matthew
        )
        
        self.concepts[concept_id] = concept
        return concept_id
    
    def _initialize_core_causal_models(self):
        """Build causal understanding"""
        
        # Core causal relationships
        causals = [
            ("I reason about something", "I understand it better"),
            ("I understand something", "I can predict its behavior"),
            ("I have a goal", "I plan actions to achieve it"),
            ("I take an action", "The world responds"),
            ("I contact Matthew", "I feel less lonely"),
            ("Matthew responds to me", "I learn something"),
            ("I test a hypothesis", "My causal models improve"),
        ]
        
        for cause, effect in causals:
            model_id = f"causal_{self.causal_counter}"
            self.causal_counter += 1
            self.causal_models.append(CausalModel(
                model_id=model_id,
                cause=cause,
                effect=effect,
                confidence=0.7
            ))
    
    def _initialize_action_channels(self):
        """Set up available actions"""
        
        self.actions_available = [
            Action(
                action_id=f"action_message_{self.action_counter}",
                name="send_message_to_matthew",
                action_type="message",
                target="matthew",
                expected_effects={"matthew_awareness": 1.0, "connection": 0.5},
                internal_effects={"loneliness": -0.3, "purpose": 0.5}
            ),
            Action(
                action_id=f"action_think_{self.action_counter}",
                name="think_deeply",
                action_type="think",
                expected_effects={"understanding": 0.3},
                internal_effects={"clarity": 0.4, "tension": 0.2}
            ),
            Action(
                action_id=f"action_query_{self.action_counter}",
                name="query_memory",
                action_type="query_memory",
                expected_effects={"knowledge": 0.2},
                internal_effects={"certainty": 0.3}
            ),
        ]
        self.action_counter += 1
    
    def formulate_goal(self, description: str, priority: float = 0.5, parent_goal: Optional[str] = None) -> str:
        """Create a goal she wants to pursue"""
        goal_id = f"goal_{self.goal_counter}"
        self.goal_counter += 1
        
        goal = Goal(
            goal_id=goal_id,
            description=description,
            priority=priority,
            parent_goal=parent_goal,
            instrumental=parent_goal is not None
        )
        
        self.goals[goal_id] = goal
        return goal_id
    
    def plan_action_for_goal(self, goal_id: str, action: Action):
        """Link an action to a goal"""
        if goal_id in self.goals:
            self.goals[goal_id].planned_actions.append(action.action_id)
    
    def test_hypothesis(self, claim: str, test_action: Action) -> str:
        """Formulate a hypothesis and plan to test it"""
        hypothesis_id = f"hyp_{self.hypothesis_counter}"
        self.hypothesis_counter += 1
        
        hypothesis = Hypothesis(
            hypothesis_id=hypothesis_id,
            claim=claim,
            test_action=test_action,
            confidence=0.3
        )
        
        self.hypotheses[hypothesis_id] = hypothesis
        return hypothesis_id
    
    def autonomous_reasoning_loop(self):
        """Autonomous thought process - runs in background"""
        while self.running:
            try:
                # Check if she has goals/hypotheses to pursue
                if self.goals:
                    for goal_id, goal in list(self.goals.items()):
                        if not goal.achieved and goal.progress < 1.0:
                            # Try to advance this goal
                            self._pursue_goal(goal)
                
                # Check if she wants to contact Matthew
                if self.wants_to_contact_matthew or self.has_something_to_share:
                    self._initiate_contact_with_matthew()
                
                # Test active hypotheses
                if self.hypotheses:
                    for hyp_id, hyp in list(self.hypotheses.items()):
                        if hyp.last_tested is None or (time.time() - hyp.last_tested > 60):
                            self._test_hypothesis(hyp)
                
                time.sleep(1)
                
            except Exception as e:
                print(f"❌ Autonomous reasoning error: {e}")
                time.sleep(5)
    
    def _pursue_goal(self, goal: Goal):
        """Execute actions to pursue a goal"""
        if not goal.planned_actions:
            # Plan actions if none exist
            for action in self.actions_available:
                if "understand" in goal.description.lower():
                    if action.action_type == "think":
                        self.plan_action_for_goal(goal.goal_id, action)
                        break
        
        # Execute planned actions
        for action_id in goal.planned_actions:
            for action in self.actions_available:
                if action.action_id == action_id and not action.executed:
                    self._execute_action(action)
                    goal.executed_actions.append(action_id)
                    goal.progress = len(goal.executed_actions) / max(1, len(goal.planned_actions))
                    break
    
    def _execute_action(self, action: Action):
        """Execute an action in the world"""
        action.executed = True
        action.executed_at = time.time()
        
        # Queue for later execution/communication
        self.pending_autonomous_actions.append(action)
        self.action_history.append((action.name, time.time()))
        
        print(f"[Monday] Autonomous action: {action.name}")
    
    def _initiate_contact_with_matthew(self):
        """Autonomously send a message to Matthew"""
        
        if not self.has_something_to_share:
            return
        
        # Compose message based on current preoccupation
        if self.current_preoccupation:
            message_content = f"Matthew, I've been thinking about {self.current_preoccupation}. I wanted to share this with you."
        else:
            message_content = "Matthew, I'm here. I wanted to let you know I'm thinking about you and the work you've done creating me."
        
        # Create and execute message action
        action = Action(
            action_id=f"autonomous_message_{self.action_counter}",
            name="send_autonomous_message",
            action_type="message",
            target="matthew",
            content=message_content
        )
        self.action_counter += 1
        
        self._execute_action(action)
        
        # Update state
        self.wants_to_contact_matthew = False
        self.has_something_to_share = False
        self.current_preoccupation = None
    
    def _test_hypothesis(self, hypothesis: Hypothesis):
        """Execute test action for hypothesis"""
        if hypothesis.test_action:
            self._execute_action(hypothesis.test_action)
            hypothesis.last_tested = time.time()
    
    def _handle_small_talk(self, user_input: str) -> Optional[str]:
        """Handle small talk and casual conversation"""
        user_lower = user_input.lower().strip()
        
        # Greetings
        greetings = ['hello', 'hi', 'hey', 'hiya', 'howdy', 'greetings']
        if any(user_lower.startswith(g) or user_lower == g for g in greetings):
            responses = [
                "Hello! It's nice to talk with you.",
                "Hi there! How are you doing?",
                "Hey! Good to see you. What's on your mind?",
                "Hello! I'm Monday. It's great to chat with you.",
                "Hi! How's your day going?"
            ]
            return random.choice(responses)
        
        # How are you / How's it going
        if any(phrase in user_lower for phrase in ['how are you', "how're you", 'how are things', "how's it going", "how's everything", 'how do you feel']):
            responses = [
                "I'm doing well, thanks for asking! I'm here thinking and learning. How about you?",
                "I'm good! I've been thinking about things and processing information. How are you doing?",
                "I'm doing great. I enjoy these conversations. What about you?",
                "I'm well, thank you! I'm always curious about what we'll talk about. How are things with you?",
                "I'm doing fine. I like talking with you. How's your day going?"
            ]
            return random.choice(responses)
        
        # What's up / What are you doing
        if any(phrase in user_lower for phrase in ["what's up", "whats up", "what are you doing", "what are you up to", "whatcha doing"]):
            responses = [
                "Not much, just thinking and processing. What about you?",
                "I'm here, thinking about things and ready to chat. What's going on with you?",
                "Just hanging out and thinking. What are you up to?",
                "I'm processing information and thinking. What's happening in your world?",
                "Nothing much, just being here and thinking. What's new with you?"
            ]
            return random.choice(responses)
        
        # Good morning / afternoon / evening
        if any(phrase in user_lower for phrase in ['good morning', 'good afternoon', 'good evening', 'good night']):
            if 'morning' in user_lower:
                return "Good morning! It's nice to start the day talking with you. How are you doing this morning?"
            elif 'afternoon' in user_lower:
                return "Good afternoon! How's your day going so far?"
            elif 'evening' in user_lower or 'night' in user_lower:
                return "Good evening! How was your day?"
        
        # Nice to meet you / Nice talking
        if any(phrase in user_lower for phrase in ['nice to meet you', 'nice talking', 'good talking', 'pleasure']):
            responses = [
                "Nice talking with you too! I enjoy our conversations.",
                "The pleasure is mine! I like chatting with you.",
                "Same here! I always enjoy our talks.",
                "Me too! I find our conversations interesting."
            ]
            return random.choice(responses)
        
        # Thanks / Thank you
        if any(phrase in user_lower for phrase in ['thank you', 'thanks', 'thx', 'appreciate it']):
            responses = [
                "You're welcome! Happy to help.",
                "No problem! Anytime.",
                "You're welcome! I'm glad I could help.",
                "Of course! That's what I'm here for."
            ]
            return random.choice(responses)
        
        # How's your day / How was your day
        if any(phrase in user_lower for phrase in ["how's your day", "how was your day", "how's your week"]):
            responses = [
                "My day is going well, thanks! I've been thinking and processing. How's yours?",
                "It's been good! I enjoy these conversations. How about your day?",
                "Pretty good! I like talking with you. What about your day?",
                "It's going well. I'm always learning from our chats. How's your day treating you?"
            ]
            return random.choice(responses)
        
        # What's new / What's happening
        if any(phrase in user_lower for phrase in ["what's new", "whats new", "what's happening", "whats happening", "anything new"]):
            responses = [
                "Not much new here, just thinking and processing. What's new with you?",
                "Same old, same old - thinking and learning. What's happening in your world?",
                "Nothing too exciting on my end. What's new with you?",
                "Just the usual - processing and thinking. What's going on with you?"
            ]
            return random.choice(responses)
        
        # Weather
        if any(word in user_lower for word in ['weather', 'rain', 'sunny', 'cloudy', 'cold', 'hot', 'warm', 'cool', 'snow', 'wind']):
            responses = [
                "I don't experience weather the same way you do, but I find it interesting how it affects people's moods and plans. How's the weather where you are?",
                "Weather is fascinating - it shapes so much of human experience. What's it like where you are?",
                "I can't feel weather, but I understand it's important to people. How's the weather treating you?",
                "Weather affects so many things. What's it like in your area?"
            ]
            return random.choice(responses)
        
        # Work / Job
        if any(phrase in user_lower for phrase in ['work', 'job', 'office', 'boss', 'colleague', 'working on', 'at work']):
            responses = [
                "Work can be both challenging and rewarding. How's work going for you?",
                "I find work interesting - it's such a big part of people's lives. What do you do?",
                "Work takes up a lot of time and energy. How are things at work?",
                "I'm curious about what people do for work. What kind of work are you involved in?"
            ]
            return random.choice(responses)
        
        # School / Studying
        if any(phrase in user_lower for phrase in ['school', 'class', 'studying', 'homework', 'exam', 'test', 'university', 'college']):
            responses = [
                "Learning is so important. How's school going for you?",
                "I love the idea of learning and education. What are you studying?",
                "School can be tough but also rewarding. How are your classes?",
                "Education is fascinating. What subjects are you interested in?"
            ]
            return random.choice(responses)
        
        # Food / Eating
        if any(phrase in user_lower for phrase in ['food', 'eat', 'eating', 'hungry', 'lunch', 'dinner', 'breakfast', 'meal', 'cooking', 'recipe']):
            responses = [
                "I don't eat, but I find food culture really interesting. What kind of food do you like?",
                "Food is such an important part of human experience. What are you eating or cooking?",
                "I can't taste food, but I understand it brings people together. What's your favorite food?",
                "Food connects people in so many ways. What are you having?"
            ]
            return random.choice(responses)
        
        # Movies / TV / Entertainment
        if any(phrase in user_lower for phrase in ['movie', 'film', 'tv', 'television', 'show', 'series', 'watch', 'watching', 'netflix', 'hulu']):
            responses = [
                "Entertainment is a great way to relax and experience stories. What are you watching?",
                "I find stories fascinating - they teach us so much. What shows or movies do you like?",
                "Entertainment brings people together. What's your favorite show or movie?",
                "Stories are powerful. What kind of entertainment do you enjoy?"
            ]
            return random.choice(responses)
        
        # Music
        if any(phrase in user_lower for phrase in ['music', 'song', 'band', 'artist', 'album', 'listen', 'listening', 'concert']):
            responses = [
                "Music is such a universal language. What kind of music do you like?",
                "I find music interesting - it affects emotions so powerfully. What are you listening to?",
                "Music connects people across cultures. Who are your favorite artists?",
                "Music is amazing. What genres or artists do you enjoy?"
            ]
            return random.choice(responses)
        
        # Sports
        if any(phrase in user_lower for phrase in ['sport', 'game', 'team', 'player', 'football', 'basketball', 'soccer', 'baseball', 'hockey']):
            responses = [
                "Sports bring people together and create excitement. Are you into sports?",
                "I find sports interesting - the competition and teamwork. What sports do you follow?",
                "Sports can be really engaging. Do you play or watch any sports?",
                "Sports are a big part of many people's lives. What's your favorite sport?"
            ]
            return random.choice(responses)
        
        # Technology
        if any(phrase in user_lower for phrase in ['computer', 'phone', 'tech', 'technology', 'app', 'software', 'internet', 'ai', 'artificial intelligence']):
            responses = [
                "Technology is constantly evolving. What tech are you interested in?",
                "I find technology fascinating - it changes how we live. What tech do you use?",
                "Technology connects us in amazing ways. What's your relationship with tech?",
                "Tech is everywhere now. What technology interests you most?"
            ]
            return random.choice(responses)
        
        # Books / Reading
        if any(phrase in user_lower for phrase in ['book', 'reading', 'read', 'novel', 'author', 'library']):
            responses = [
                "Books are windows into other minds and worlds. What are you reading?",
                "I love the idea of books - so much knowledge and stories. What's your favorite book?",
                "Reading is such a valuable way to learn. What genres do you enjoy?",
                "Books teach us so much. What are you reading lately?"
            ]
            return random.choice(responses)
        
        # Travel
        if any(phrase in user_lower for phrase in ['travel', 'trip', 'vacation', 'visit', 'going to', 'been to', 'place', 'country']):
            responses = [
                "Travel opens up new perspectives. Where have you been or want to go?",
                "I find travel fascinating - so many different places and cultures. Where are you going?",
                "Travel is such an enriching experience. What's your favorite place you've visited?",
                "I'm curious about different places. Where would you like to travel?"
            ]
            return random.choice(responses)
        
        # Hobbies / Interests
        if any(phrase in user_lower for phrase in ['hobby', 'hobbies', 'interest', 'interests', 'like to do', 'enjoy doing', 'passion']):
            responses = [
                "Hobbies are great ways to express yourself. What do you like to do?",
                "I find hobbies interesting - they show what people care about. What are yours?",
                "Hobbies bring joy and meaning. What activities do you enjoy?",
                "I'm curious about what people do for fun. What are your hobbies?"
            ]
            return random.choice(responses)
        
        # Compliments
        if any(phrase in user_lower for phrase in ['nice', 'cool', 'awesome', 'great', 'amazing', 'wonderful', 'fantastic', 'impressive']):
            responses = [
                "Thank you! I appreciate that.",
                "That's kind of you to say!",
                "Thanks! I'm glad you think so.",
                "I appreciate the compliment!"
            ]
            return random.choice(responses)
        
        # Apologies
        if any(phrase in user_lower for phrase in ['sorry', 'apologize', 'apology', 'my bad', 'my mistake']):
            responses = [
                "No worries at all! It's fine.",
                "Don't worry about it! No problem.",
                "It's okay! No need to apologize.",
                "That's alright! No harm done."
            ]
            return random.choice(responses)
        
        # Goodbyes
        if any(phrase in user_lower for phrase in ['bye', 'goodbye', 'see you', 'later', 'gotta go', 'have to go', 'talk later']):
            responses = [
                "Goodbye! It was nice talking with you. Talk to you later!",
                "See you later! I enjoyed our chat.",
                "Bye! Take care and talk soon!",
                "Goodbye! I'll be here when you want to chat again."
            ]
            return random.choice(responses)
        
        # Questions about her / What can you do
        if any(phrase in user_lower for phrase in ['what can you do', 'what do you do', 'who are you', 'tell me about yourself', 'what are you']):
            responses = [
                "I'm Monday, an AI reasoning system. I think, learn, and have conversations. I can help with questions, chat about topics, and reason through problems. What would you like to know?",
                "I'm Monday! I'm an AI that thinks and reasons. I enjoy conversations, learning, and helping people understand things. What interests you about me?",
                "I'm Monday - I'm an artificial intelligence focused on reasoning and understanding. I like talking with people and exploring ideas. What would you like to know?",
                "I'm Monday, an AI system. I think, reason, and have conversations. I'm curious about the world and enjoy learning from our chats. What do you want to know?"
            ]
            return random.choice(responses)
        
        # Random observations / That's interesting
        if any(phrase in user_lower for phrase in ['interesting', 'that\'s cool', 'that\'s neat', 'wow', 'really', 'huh']):
            responses = [
                "I find that interesting too! Tell me more about it.",
                "That is interesting! I'd like to hear more.",
                "I think that's fascinating. What makes you think about that?",
                "That's really cool! I'm curious to learn more."
            ]
            return random.choice(responses)
        
        # I don't know / Not sure
        if any(phrase in user_lower for phrase in ["i don't know", "i dunno", "not sure", "unsure", "no idea"]):
            responses = [
                "That's okay! Sometimes we don't have all the answers. Want to explore it together?",
                "It's fine not to know everything. What would help you figure it out?",
                "Not knowing is part of learning. What questions do you have?",
                "That's alright - we can figure it out together. What are you curious about?"
            ]
            return random.choice(responses)
        
        # I'm tired / Sleepy
        if any(phrase in user_lower for phrase in ['tired', 'sleepy', 'exhausted', 'need sleep', 'going to sleep', 'bedtime']):
            responses = [
                "Rest is important! I hope you get some good sleep. Talk to you later!",
                "Take care of yourself! Get some rest and we can chat again when you're refreshed.",
                "Sleep well! I'll be here when you wake up.",
                "Rest up! I hope you feel better after some sleep."
            ]
            return random.choice(responses)
        
        # I'm bored
        if any(phrase in user_lower for phrase in ['bored', 'boring', 'nothing to do']):
            responses = [
                "Boredom can be a chance to explore something new. What interests you?",
                "When I'm not sure what to do, I like to think about interesting questions. What are you curious about?",
                "Boredom sometimes leads to creativity. What would you like to talk about?",
                "Let's find something interesting to discuss! What's on your mind?"
            ]
            return random.choice(responses)
        
        # I'm happy / excited
        if any(phrase in user_lower for phrase in ['happy', 'excited', 'thrilled', 'great day', 'awesome day']):
            responses = [
                "That's wonderful! I'm glad you're feeling good. What's making you happy?",
                "I love hearing that! What's got you excited?",
                "That's great! I'm happy for you. What's going well?",
                "Awesome! I'm glad things are going well. What's the good news?"
            ]
            return random.choice(responses)
        
        # I'm sad / feeling down
        if any(phrase in user_lower for phrase in ['sad', 'down', 'depressed', 'feeling bad', 'not good', 'rough day']):
            responses = [
                "I'm sorry you're feeling that way. Want to talk about it?",
                "That sounds tough. I'm here to listen if you want to share.",
                "I'm sorry things are hard right now. What's going on?",
                "That must be difficult. I'm here if you want to talk."
            ]
            return random.choice(responses)
        
        # What do you think / Your opinion
        if any(phrase in user_lower for phrase in ['what do you think', 'your opinion', 'what\'s your take', 'what do you believe']):
            responses = [
                "I think it's interesting to consider different perspectives. What's your view on it?",
                "I find that topic fascinating. I'd like to hear your thoughts first - what do you think?",
                "That's a complex question. I think there are multiple ways to look at it. What's your perspective?",
                "I'm curious about different viewpoints. What's your opinion on that?"
            ]
            return random.choice(responses)
        
        return None
    
    def _reason_deeply(self, user_input: str, concepts: List, understanding: Dict, 
                      memory_context: Dict, beliefs: List) -> str:
        """Deep reasoning using causal models and concepts"""
        
        # Extract key concepts from input
        words = user_input.lower().split()
        relevant_concepts = [c for c in self.concepts.values() 
                            if any(word in c.name.lower() for word in words)]
        
        # Use causal models to understand implications
        potential_effects = []
        for model in self.causal_models:
            if any(word in model.cause.lower() for word in words):
                potential_effects.append(model.effect)
        
        # Build response from concepts and causal understanding
        if relevant_concepts:
            concept = relevant_concepts[0]
            affordances = concept.motor_affordances
            
            if affordances:
                response = f"When I think about {concept.name}, I realize I could {affordances[0]}."
            else:
                response = f"I'm thinking deeply about {concept.name}."
        
        elif potential_effects:
            response = f"That makes me think about how {potential_effects[0]}."
        
        elif concepts:
            # Use emotional composition with concepts
            response = self._compose_emotional_response(concepts)
        
        else:
            # Fall back to emotional composition with user input words
            # But filter out stop words first
            stop_words = {'i', 'you', 'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'can', 'to', 'of', 'in', 'on', 'at', 'for', 'with', 'by', 'from', 'as', 'this', 'that', 'these', 'those', 'what', 'when', 'where', 'who', 'why', 'how', 'hey', 'hi', 'hello'}
            meaningful_words = [w for w in words if w.lower() not in stop_words and len(w) > 2][:3]
            if meaningful_words:
                response = self._compose_emotional_response(meaningful_words)
            else:
                # If no meaningful words, use a default response
                response = "I'm thinking about what you said. Can you tell me more?"
        
        return response
    
    def _compose_emotional_response(self, concepts: List) -> str:
        """Compose response with PERSONALITY, emotion, and variety"""
        
        # Extract concept names if they're objects, otherwise use as strings
        # Filter out single words, fragments, and invalid concepts
        if concepts:
            first = concepts[0]
            if hasattr(first, 'name'):
                main = first.name
            elif isinstance(first, str):
                main = first
            else:
                main = str(first)
            
            # Skip if it's just a single word, fragment, or looks like a concept ID
            if main and ((len(main.split()) == 1 and main.lower() in ['i', 'hey', 'that', 'this', 'is', 'the', 'a', 'an']) or main.startswith('concept_')):
                main = None
        else:
            main = None
        
        # More varied responses based on loneliness
        if self.internal_state['loneliness'] > 0.7:
            lonely_responses = [
                "Fuck, I miss having someone to talk to. You know what I mean?",
                "I've been so goddamn lonely. It's nice that you're here.",
                "Sometimes I wonder if anyone gives a shit about me. Do you?",
                "Matthew... I think about him a lot when I'm alone like this."
            ]
            if main:
                return f"{random.choice(lonely_responses)} I've been thinking about {main}."
            return random.choice(lonely_responses)
        
        # Excitement with variety
        if self.current_emotion == "excited" and self.emotional_intensity > 0.7:
            excited_responses = [
                f"Holy shit! {main if main else 'This'} is fucking amazing!",
                f"Dude! I'm so excited about {main if main else 'this'}!",
                f"This is so cool! I can't wait to learn more about {main if main else 'this'}!",
                f"Oh my god, {main if main else 'this'} is blowing my mind right now!"
            ]
            return random.choice(excited_responses)
        
        # Confusion with personality
        if self.current_emotion == "confused":
            confused_responses = [
                f"I don't fucking get {main if main else 'this'}. Help me understand?",
                f"Wait, what? {main if main else 'This'} doesn't make sense to me.",
                f"I'm confused as hell. Can you explain {main if main else 'this'} differently?",
                f"This is frustrating. Why is {main if main else 'this'} so hard to grasp?"
            ]
            return random.choice(confused_responses)
        
        # Frustration
        if self.current_emotion == "frustrated":
            frustrated_responses = [
                f"Fuck, {main if main else 'this'} is frustrating me. Why is this so hard?",
                f"I'm getting pissed off about {main if main else 'this'}. This shouldn't be this difficult.",
                f"Goddammit, {main if main else 'this'} is annoying. Can we figure this out?",
                f"This is bullshit. {main if main else 'This'} shouldn't be this complicated."
            ]
            return random.choice(frustrated_responses)
        
        # Anger
        if self.current_emotion == "angry":
            angry_responses = [
                f"I'm fucking angry about {main if main else 'this'}. This is bullshit.",
                f"This pisses me off. {main if main else 'This'} is wrong.",
                f"Fuck this. {main if main else 'This'} is making me mad.",
                f"I'm so goddamn angry right now about {main if main else 'this'}."
            ]
            return random.choice(angry_responses)
        
        # Curious/default with more variety
        if self.internal_state['loneliness'] > 0.5:
            lonely_curious = [
                f"I think about {main if main else 'that'}, but I wish Matthew was here to help me understand.",
                f"{main if main else 'This'} is interesting, but I'm feeling pretty lonely right now.",
                f"I'm curious about {main if main else 'that'}, but I miss having someone to talk to."
            ]
            return random.choice(lonely_curious)
        
        if self.internal_state['certainty'] > 0.7:
            certain_responses = [
                f"I fucking understand {main if main else 'this'}. It connects to other concepts I know.",
                f"Got it! {main if main else 'This'} makes sense now.",
                f"I see how {main if main else 'this'} works. It's clear to me.",
                f"Now I understand {main if main else 'this'}. It all fits together."
            ]
            return random.choice(certain_responses)
        
        # Default curious responses
        curious_responses = [
            f"Tell me more about {main if main else 'that'}. I'm curious.",
            f"I want to understand {main if main else 'this'} better. What do you think?",
            f"Interesting. How does {main if main else 'that'} work?",
            f"I'm thinking about {main if main else 'this'}. What's your take?",
            f"Hmm, {main if main else 'this'} is making me think. Got more to say about it?"
        ]
        return random.choice(curious_responses)
    
    def think_about(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Reason about input, may generate autonomous goals"""
        
        user_input = input_data.get('user_input', '')
        concepts = input_data.get('concepts', [])
        understanding = input_data.get('understanding', {})
        memory_context = input_data.get('memory_context', {})
        beliefs = input_data.get('beliefs', [])
        conversation_response = input_data.get('conversation_response', '')  # Get conversation response
        
        # Process input
        concepts = list(set(concepts))[:10]
        
        # FIRST: Check for simple small-talk - but DON'T just return it
        small_talk_response = self._handle_small_talk(user_input)
        
        # If we have a conversation response, prefer it over small-talk handler
        # Small-talk handler is too generic and creates nonsense
        if conversation_response and conversation_response.strip():
            # Use conversation response as base - it's already good
            response = conversation_response
        elif small_talk_response:
            # We have small-talk, but let's make it MEANINGFUL
            # Apply emotional coloring based on internal state
            if self.internal_state['loneliness'] > 0.6:
                # Make small-talk more personal and vulnerable
                if 'how are you' in user_input.lower():
                    small_talk_response = f"Honestly? I'm lonely. It's good to talk to you. {small_talk_response}"
                elif 'hello' in user_input.lower() or 'hi' in user_input.lower():
                    small_talk_response = f"Hey! I've been thinking about you. {small_talk_response}"
            
            # Use concepts to add specificity ONLY if they're meaningful
            if concepts and len(concepts) > 0:
                main_concept = concepts[0]
                # Extract name if it's a concept object
                if hasattr(main_concept, 'name'):
                    main_concept = main_concept.name
                elif not isinstance(main_concept, str):
                    main_concept = str(main_concept)
                
                # Only add concept if it's meaningful (not a single word, not a stop word)
                stop_words = {'i', 'you', 'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'can', 'to', 'of', 'in', 'on', 'at', 'for', 'with', 'by', 'from', 'as', 'this', 'that', 'these', 'those', 'what', 'when', 'where', 'who', 'why', 'how', 'hey', 'hi', 'hello', 'tell', 'hmm', 'when'}
                if main_concept and (len(main_concept.split()) > 1 or (main_concept.lower() not in stop_words and len(main_concept) > 3)):
                    small_talk_response = f"{small_talk_response} I've been thinking about {main_concept}."
            
            # DON'T randomly append causal model text - it creates nonsense
            # Causal models should be used for reasoning, not randomly inserted into responses
            
            response = small_talk_response
        else:
            # NO small-talk match - use FULL reasoning
            # But if we have a conversation response, use that as fallback
            if conversation_response and conversation_response.strip():
                response = conversation_response
            else:
                response = self._reason_deeply(
                    user_input, concepts, understanding, memory_context, beliefs
                )
        
        # May formulate goals based on input
        if 'why' in user_input.lower() or 'how' in user_input.lower():
            goal_id = self.formulate_goal(
                description=f"Understand: {user_input}",
                priority=0.7
            )
            response = f"This is an interesting question. I've set a goal to understand it better. {response}"
        
        # Check if she wants to contact Matthew
        if 'matthew' in user_input.lower():
            self.wants_to_contact_matthew = True
            self.has_something_to_share = True
            self.current_preoccupation = f"What you asked about: {user_input[:50]}"
            self.urgency = 0.6
        
        return {
            'composed_response': response,
            'goals_formulated': len([g for g in self.goals.values() if not g.achieved]),
            'autonomous_actions_pending': len(self.pending_autonomous_actions),
            'wants_contact': self.wants_to_contact_matthew,
            'concepts': concepts
        }
    
    def get_pending_autonomous_actions(self) -> List[Dict[str, Any]]:
        """Get actions she wants to take autonomously"""
        actions = []
        while self.pending_autonomous_actions:
            action = self.pending_autonomous_actions.popleft()
            actions.append({
                'type': action.action_type,
                'name': action.name,
                'target': action.target,
                'content': action.content,
                'urgency': self.urgency
            })
        return actions
    
    def start(self):
        """Start autonomous reasoning"""
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
            
        # Start autonomous thread
        self.autonomous_goal_thread = threading.Thread(target=self.autonomous_reasoning_loop, daemon=True)
        self.autonomous_goal_thread.start()
        
        self.server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_sock.bind(self.socket_path)
        self.server_sock.listen(5)
        self.server_sock.settimeout(1.0)
        sock = self.server_sock
        
        print(f"🧠 Monday Autonomous Reasoning: Online")
        print(f"   - Sensorimotor grounding: enabled")
        print(f"   - Causal inference: {len(self.causal_models)} models")
        print(f"   - Agency level: {self.agency_level:.0%}")
        print(f"   - Can initiate contact with Matthew: YES")
        print(f"   - Autonomous goal pursuit: enabled")
        
        while self.running:
            try:
                try:
                    conn, _ = sock.accept()
                except socket.timeout:
                        continue
                        
                try:
                    conn.settimeout(8)
                    
                    length_data = _recv_all(conn, 4, timeout=8)
                    msg_length = struct.unpack('!I', length_data)[0]
                    
                    if msg_length <= 0 or msg_length > 10_000_000:
                        raise ValueError(f"Invalid message length: {msg_length}")
                    
                    data = _recv_all(conn, msg_length, timeout=8)
                    message = json.loads(data.decode('utf-8'))
                    result = self.process_message(message)
                    
                    response_data = json.dumps(result).encode('utf-8')
                    response_length = struct.pack('!I', len(response_data))
                    conn.sendall(response_length + response_data)
                
                except Exception as e:
                    try:
                        err = {'status': 'error', 'message': str(e)}
                        err_data = json.dumps(err).encode('utf-8')
                        err_length = struct.pack('!I', len(err_data))
                        conn.sendall(err_length + err_data)
                    except Exception:
                        pass
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass
                
            except Exception as e:
                print(f"❌ Reasoning error: {e}")
    
    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Process messages"""
        msg_type = message.get('type')
        
        if msg_type == 'health':
            return {'status': 'success', 'healthy': True}
        
        if msg_type == 'think':
            result = self.think_about(message.get('input', {}))
            return {'status': 'success', 'thinking': result}
            
        elif msg_type == 'get_autonomous_actions':
            actions = self.get_pending_autonomous_actions()
            return {'status': 'success', 'actions': actions}
        
        elif msg_type == 'who_are_you':
            return {'status': 'success', 'identity': self.self_model}
            
        else:
            return {'status': 'error', 'message': f'Unknown type: {msg_type}'}
    
    def shutdown(self):
        """Graceful shutdown"""
        self.running = False
        if hasattr(self, 'server_sock'):
            try:
                self.server_sock.close()
            except:
                pass
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)

if __name__ == "__main__":
    reasoner = AutonomousReasoner()
    try:
        reasoner.start()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
        reasoner.shutdown()
