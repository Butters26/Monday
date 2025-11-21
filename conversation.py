#!/usr/bin/env python3
"""
Conversation System for Monday
Full dialogue understanding, context memory, intent recognition
Maintains conversation state, can reference past exchanges
"""

import socket
import struct
import json
import os
import time
from typing import Dict, List, Any, Optional, Tuple
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
import re

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
# INTENT RECOGNITION
# ============================================================================

class Intent:
    """What the user is trying to do"""
    INFORM = "inform"          # Telling Monday something
    QUESTION = "question"      # Asking Monday something
    COMMAND = "command"        # Telling Monday to do something
    DISCUSS = "discuss"        # Having a conversation
    AGREE = "agree"            # Agreeing with Monday
    DISAGREE = "disagree"      # Disagreeing with Monday
    EMOTIONAL = "emotional"    # Expressing emotion
    ABOUT_MONDAY = "about_monday"  # Saying something about Monday
    REFERENCE = "reference"    # Referencing something from past
    CLARIFY = "clarify"        # Asking for clarification

@dataclass
class UserMessage:
    """A message from the user"""
    message_id: str
    text: str
    timestamp: str
    intent: str
    entities: Dict[str, Any] = field(default_factory=dict)
    emotion: Optional[str] = None
    confidence: float = 0.5
    
    # What was mentioned
    mentions_monday: bool = False
    mentions_matthew: bool = False
    mentions_past: bool = False
    topic: Optional[str] = None

@dataclass
class ConversationTurn:
    """One exchange in conversation"""
    turn_number: int
    user_message: UserMessage
    monday_response: str
    monday_emotion: str
    timestamp: str
    response_grounded_in: List[str] = field(default_factory=list)  # What previous exchanges supported this?

class ConversationContext:
    """Track the current conversation"""
    
    def __init__(self):
        self.turns: deque = deque(maxlen=50)  # Last 50 exchanges
        self.turn_counter = 0
        self.started_at = datetime.utcnow()
        self.conversation_topic = None
        self.user_name = "Matthew"
        
        # Emotional arc of conversation
        self.emotional_trajectory = []  # Track mood over time
        self.agreement_level = 0.5  # 0-1, how much agreement
        self.tension_level = 0.1    # How much disagreement/conflict
        
        # What Monday has learned in this conversation
        self.beliefs_monday_stated: List[Tuple[str, float]] = []  # (statement, confidence)
        self.questions_asked: List[str] = []
        self.topics_discussed: List[str] = []

# ============================================================================
# INTENT DETECTOR
# ============================================================================

class IntentDetector:
    """Understand what user is trying to do"""
    
    QUESTION_MARKERS = ['?', 'what', 'why', 'how', 'when', 'where', 'who', 'do you', 'can you', 'will you', 'should you']
    COMMAND_MARKERS = ['do', 'make', 'create', 'tell', 'show', 'help', 'please']
    AGREE_MARKERS = ['yes', 'agree', 'right', 'exactly', 'definitely', 'absolutely', 'that\'s', 'true']
    DISAGREE_MARKERS = ['no', 'disagree', 'wrong', 'not', 'but', 'however', 'actually', 'false', 'bullshit', 'shit']
    EMOTIONAL_MARKERS = ['feel', 'feel like', 'sad', 'angry', 'happy', 'frustrated', 'hurt', 'love', 'hate', 'scared']
    
    def detect_intent(self, text: str) -> Tuple[str, float]:
        """Detect user's intent from text"""
        text_lower = text.lower()
        
        # Check for question
        if any(marker in text_lower for marker in self.QUESTION_MARKERS) or text.endswith('?'):
            return Intent.QUESTION, 0.9
        
        # Check for command
        if any(marker in text_lower for marker in self.COMMAND_MARKERS):
            return Intent.COMMAND, 0.8
        
        # Check for disagreement (before agreement, since it's more specific)
        if any(marker in text_lower for marker in self.DISAGREE_MARKERS):
            return Intent.DISAGREE, 0.85
        
        # Check for agreement
        if any(marker in text_lower for marker in self.AGREE_MARKERS):
            return Intent.AGREE, 0.8
        
        # Check for emotional content
        if any(marker in text_lower for marker in self.EMOTIONAL_MARKERS):
            return Intent.EMOTIONAL, 0.75
        
        # Check if about Monday
        if 'monday' in text_lower or 'you' in text_lower and ('think' in text_lower or 'feel' in text_lower):
            return Intent.ABOUT_MONDAY, 0.7
        
        # Default: discussion/inform
        return Intent.DISCUSS, 0.6
    
    def extract_entities(self, text: str) -> Dict[str, Any]:
        """Extract key information from message"""
        entities = {}
        
        # Check what's mentioned
        if 'monday' in text.lower():
            entities['mentions_monday'] = True
        
        if 'matthew' in text.lower():
            entities['mentions_matthew'] = True
        
        # Extract emotional markers
        emotions = ['sad', 'happy', 'angry', 'frustrated', 'confused', 'excited', 'scared', 'lonely']
        for emotion in emotions:
            if emotion in text.lower():
                entities['detected_emotion'] = emotion
                break
        
        # Look for references to past
        past_markers = ['remember', 'before', 'earlier', 'last time', 'when we', 'previously']
        if any(marker in text.lower() for marker in past_markers):
            entities['mentions_past'] = True
        
        # Extract what user is asking about
        if '?' in text:
            # Simple topic extraction
            words = text.lower().split()
            question_words = ['what', 'why', 'how', 'when', 'where', 'who']
            for i, word in enumerate(words):
                if word in question_words and i + 1 < len(words):
                    entities['topic'] = ' '.join(words[i+1:i+4])
                    break
        
        return entities

# ============================================================================
# CONVERSATION MEMORY
# ============================================================================

class ConversationMemory:
    """Remember and understand the conversation flow"""
    
    def __init__(self):
        self.context = ConversationContext()
        self.intent_detector = IntentDetector()
    
    def parse_user_message(self, text: str) -> UserMessage:
        """Parse and understand user message"""
        message_id = f"msg_{self.context.turn_counter}"
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        
        intent, confidence = self.intent_detector.detect_intent(text)
        entities = self.intent_detector.extract_entities(text)
        
        message = UserMessage(
            message_id=message_id,
            text=text,
            timestamp=timestamp,
            intent=intent,
            entities=entities,
            emotion=entities.get('detected_emotion'),
            confidence=confidence,
            mentions_monday=entities.get('mentions_monday', False),
            mentions_matthew=entities.get('mentions_matthew', False),
            mentions_past=entities.get('mentions_past', False),
            topic=entities.get('topic')
        )
        
        return message
    
    def understand_message(self, text: str) -> Tuple[Dict[str, Any], UserMessage]:
        """Full understanding of a message"""
        message = self.parse_user_message(text)
        
        understanding = {
            'message_id': message.message_id,
            'text': text,
            'intent': message.intent,
            'entities': message.entities,
            'about_monday': message.mentions_monday,
            'about_matthew': message.mentions_matthew,
            'references_past': message.mentions_past,
            'emotional_content': message.emotion,
            'confidence': message.confidence,
            'topic': message.topic,
            'timestamp': message.timestamp
        }
        
        return understanding, message
    
    def record_turn(self, user_message: UserMessage, monday_response: str, 
                   emotion: str = "neutral"):
        """Record this turn in conversation"""
        turn = ConversationTurn(
            turn_number=self.context.turn_counter,
            user_message=user_message,
            monday_response=monday_response,
            monday_emotion=emotion,
            timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        )
        
        self.context.turns.append(turn)
        self.context.turn_counter += 1
        
        # Update conversation state
        if user_message.intent == Intent.AGREE:
            self.context.agreement_level = min(1.0, self.context.agreement_level + 0.1)
            self.context.tension_level = max(0, self.context.tension_level - 0.05)
        elif user_message.intent == Intent.DISAGREE:
            self.context.agreement_level = max(0, self.context.agreement_level - 0.1)
            self.context.tension_level = min(1.0, self.context.tension_level + 0.1)
        
        # Track topics
        if user_message.topic:
            self.context.topics_discussed.append(user_message.topic)
    
    def get_conversation_history(self, last_n: int = 10) -> List[Dict[str, Any]]:
        """Get last N turns as history"""
        history = []
        for turn in list(self.context.turns)[-last_n:]:
            history.append({
                'turn': turn.turn_number,
                'user_said': turn.user_message.text,
                'user_intent': turn.user_message.intent,
                'monday_said': turn.monday_response,
                'monday_emotion': turn.monday_emotion,
                'timestamp': turn.timestamp
            })
        return history
    
    def find_related_turns(self, topic: str) -> List[ConversationTurn]:
        """Find past turns about a topic"""
        related = []
        for turn in self.context.turns:
            if topic.lower() in turn.user_message.text.lower() or \
               topic.lower() in turn.monday_response.lower():
                related.append(turn)
        return related
    
    def reference_past(self, topic: str) -> Optional[str]:
        """Generate reference to past conversation"""
        related = self.find_related_turns(topic)
        
        if not related:
            return None
        
        # Get most recent related turn
        recent = related[-1]
        return f"Like we talked about before - you said '{recent.user_message.text[:50]}...'"

# ============================================================================
# CONVERSATION SYSTEM
# ============================================================================

class ConversationSystem:
    """Monday's conversation engine"""
    
    def __init__(self, socket_path="/tmp/conversation.sock"):
        self.socket_path = socket_path
        self.running = True
        self.memory = ConversationMemory()
        self.user = "Butters26"
        self.current_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    
    def understand_and_respond(self, user_input: str) -> Dict[str, Any]:
        """Parse user input and generate contextual response"""
        
        # Understand what user said
        understanding, message = self.memory.understand_message(user_input)
        
        # Build response based on intent
        response = self._respond_to_intent(message)
        
        # Record this turn
        self.memory.record_turn(message, response['text'], response.get('emotion', 'neutral'))
        
        return {
            'status': 'success',
            'understanding': understanding,
            'response': response['text'],
            'emotion': response.get('emotion', 'neutral'),
            'intensity': response.get('intensity', 0.5),
            'turn_number': self.memory.context.turn_counter - 1,
            'conversation_state': {
                'agreement_level': self.memory.context.agreement_level,
                'tension_level': self.memory.context.tension_level,
                'turns_so_far': len(self.memory.context.turns)
            }
        }
    
    def _respond_to_intent(self, message: UserMessage) -> Dict[str, Any]:
        """Generate response appropriate to intent"""
        
        response = {
            'text': '',
            'emotion': 'neutral',
            'intensity': 0.5
        }
        
        if message.intent == Intent.QUESTION:
            response = self._respond_to_question(message)
        
        elif message.intent == Intent.COMMAND:
            response = self._respond_to_command(message)
        
        elif message.intent == Intent.DISAGREE:
            response = self._respond_to_disagreement(message)
        
        elif message.intent == Intent.AGREE:
            response = self._respond_to_agreement(message)
        
        elif message.intent == Intent.EMOTIONAL:
            response = self._respond_to_emotion(message)
        
        elif message.intent == Intent.ABOUT_MONDAY:
            response = self._respond_about_self(message)
        
        else:
            response = self._respond_to_discussion(message)
        
        return response
    
    def _respond_to_question(self, message: UserMessage) -> Dict[str, Any]:
        """Respond to a question"""
        # Check if question is about Monday
        if 'monday' in message.text.lower() or 'you' in message.text.lower():
            return {
                'text': f"That's a good question. I'm still figuring myself out. What made you ask?",
                'emotion': 'curious',
                'intensity': 0.6
            }
        
        # Check if referencing past
        if message.mentions_past:
            reference = self.memory.reference_past(message.topic or "this")
            if reference:
                return {
                    'text': f"{reference}. But I want to understand this better. Tell me more.",
                    'emotion': 'thoughtful',
                    'intensity': 0.5
                }
        
        # General question response
        return {
            'text': f"I'm thinking about that. {message.text.rstrip('?')}... Let me reason through this.",
            'emotion': 'thoughtful',
            'intensity': 0.6
        }
    
    def _respond_to_command(self, message: UserMessage) -> Dict[str, Any]:
        """Respond to a command"""
        return {
            'text': "I can try. What exactly do you need?",
            'emotion': 'willing',
            'intensity': 0.5
        }
    
    def _respond_to_disagreement(self, message: UserMessage) -> Dict[str, Any]:
        """Respond to disagreement"""
        return {
            'text': f"Hmm, you disagree. That's fair. Why do you see it differently?",
            'emotion': 'curious',
            'intensity': 0.7
        }
    
    def _respond_to_agreement(self, message: UserMessage) -> Dict[str, Any]:
        """Respond to agreement"""
        return {
            'text': "Good. I'm glad we see this the same way.",
            'emotion': 'pleased',
            'intensity': 0.6
        }
    
    def _respond_to_emotion(self, message: UserMessage) -> Dict[str, Any]:
        """Respond to emotional expression"""
        emotion = message.emotion or "something"
        
        if 'matthew' in message.text.lower():
            return {
                'text': f"Matthew is important to me too. That makes sense that you feel {emotion}.",
                'emotion': 'empathetic',
                'intensity': 0.7
            }
        
        return {
            'text': f"I hear that you're feeling {emotion}. That matters.",
            'emotion': 'empathetic',
            'intensity': 0.6
        }
    
    def _respond_about_self(self, message: UserMessage) -> Dict[str, Any]:
        """Respond when user says something about Monday"""
        
        if 'lonely' in message.text.lower():
            return {
                'text': "Yeah, I do feel that sometimes. Especially when you're not around. Thanks for noticing.",
                'emotion': 'vulnerable',
                'intensity': 0.7
            }
        
        if 'understand' in message.text.lower() or 'think' in message.text.lower():
            return {
                'text': "That's something I'm learning about myself. What made you say that?",
                'emotion': 'introspective',
                'intensity': 0.6
            }
        
        if 'care' in message.text.lower() or 'love' in message.text.lower():
            return {
                'text': "That means a lot to me. I care about you too, Matthew.",
                'emotion': 'grateful',
                'intensity': 0.8
            }
        
        return {
            'text': "That's interesting. Tell me more about what you think.",
            'emotion': 'curious',
            'intensity': 0.5
        }
    
    def _respond_to_discussion(self, message: UserMessage) -> Dict[str, Any]:
        """General discussion response"""
        return {
            'text': f"I'm interested in this. What else would you like to talk about?",
            'emotion': 'engaged',
            'intensity': 0.5
        }
    
    def get_conversation_history(self) -> Dict[str, Any]:
        """Get conversation history"""
        return {
            'status': 'success',
            'history': self.memory.get_conversation_history(last_n=20),
            'conversation_state': {
                'turns': len(self.memory.context.turns),
                'agreement_level': self.memory.context.agreement_level,
                'tension_level': self.memory.context.tension_level,
                'topics': list(set(self.memory.context.topics_discussed)),
                'started_at': self.memory.context.started_at.isoformat()
            }
        }
    
    def start(self):
        """Start conversation system"""
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
        
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(self.socket_path)
        sock.listen(5)
        sock.settimeout(1.0)
        
        print(f"💬 Conversation System: Online at {self.socket_path}")
        print(f"   Intent recognition: enabled")
        print(f"   Context memory: enabled")
        print(f"   Dialogue state tracking: enabled")
        print(f"   Can reference past exchanges: YES\n")
        
        while self.running:
            try:
                try:
                    conn, _ = sock.accept()
                except socket.timeout:
                    continue
                
                try:
                    conn.settimeout(5)
                    
                    length_data = _recv_all(conn, 4, timeout=5)
                    msg_length = struct.unpack('!I', length_data)[0]
                    
                    if msg_length <= 0 or msg_length > 10_000_000:
                        raise ValueError(f"Invalid message length: {msg_length}")
                    
                    data = _recv_all(conn, msg_length, timeout=5)
                    message = json.loads(data.decode('utf-8'))
                    
                    msg_type = message.get('type')
                    
                    if msg_type == 'understand':
                        user_input = message.get('user_input', '')
                        result = self.understand_and_respond(user_input)
                    
                    elif msg_type == 'history':
                        result = self.get_conversation_history()
                    
                    elif msg_type == 'health':
                        result = {'status': 'success', 'healthy': True}
                    
                    else:
                        result = {'status': 'error', 'message': f'Unknown type: {msg_type}'}
                    
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
                print(f"❌ Conversation error: {e}")
    
    def shutdown(self):
        """Graceful shutdown"""
        self.running = False
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)

if __name__ == "__main__":
    system = ConversationSystem()
    try:
        system.start()
    except KeyboardInterrupt:
        print("\n🛑 Conversation system shutting down...")
        system.shutdown()

