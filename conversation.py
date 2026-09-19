#!/usr/bin/env python3
"""
Conversation System for Monday
Full dialogue understanding, context memory, intent recognition
Maintains conversation state, can reference past exchanges
"""

import json
import os
import time
import sys
from typing import Dict, List, Any, Optional, Tuple
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from thalamus import get_thalamus
from direct_response import honest_curiosity_question, is_mild_social_turn, looks_like_teaching_turn
import random

@dataclass
class ConversationState:
    """Current conversation state"""
    history: deque = field(default_factory=lambda: deque(maxlen=50))
    current_topic: Optional[str] = None
    user_name: Optional[str] = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

class ConversationSystem:
    """Conversation understanding and context management"""
    
    def __init__(self, thalamus=None):
        self.running = True
        self.state = ConversationState()
        
        # Direct reference to Thalamus (NO SOCKETS)
        self.thalamus = thalamus or get_thalamus()
        
        # novelty_lobe left unused on the live six-path (curiosity owned elsewhere)
        self.novelty_lobe = None
        
    def understand(self, user_input: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Understand user input and extract intent"""
        if context is None:
            context = {}
        
        text_lower = user_input.lower().strip()
        
        # Add to history
        self.state.history.append({
            'user': user_input,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        
        # Intent detection
        intent = self._detect_intent(text_lower)
        confidence = self._calculate_confidence(text_lower, intent)
        
        # Extract entities
        entities = self._extract_entities(user_input)
        
        # Topic detection
        topic = self._detect_topic(text_lower)
        if topic:
            self.state.current_topic = topic
        
        # Sentiment
        sentiment = self._detect_sentiment(text_lower)
        
        # Curiosity is owned by emotion/conversation/direct_response — not novelty_lobe.
        # Live six-path attaches via Thalamus after emotion; understand only notes intent.
        understanding = {
            'intent': intent,
            'confidence': confidence,
            'entities': entities,
            'topic': topic,
            'sentiment': sentiment,
            'context_length': len(self.state.history),
            'curiosity_question': None,
        }
        
        return understanding
    
    def _detect_intent(self, text: str) -> str:
        """Detect user intent from text"""
        # Question
        if text.endswith('?') or any(word in text.split()[:3] for word in ['what', 'who', 'where', 'when', 'why', 'how', 'can', 'could', 'would', 'should', 'is', 'are', 'do', 'does']):
            return 'question'
        
        # Request/Command
        if any(word in text.split()[:5] for word in ['please', 'can you', 'could you', 'would you', 'help me', 'show me', 'tell me', 'give me']):
            return 'request'

        # A greeting is social intent only when it is not paired with a request.
        if any(word in text for word in ['hello', 'hi', 'hey', 'greetings', 'good morning', 'good afternoon', 'good evening']):
            return 'greeting'
        
        # Statement
        if any(word in text for word in ['i think', 'i feel', 'i believe', 'i want', 'i need', 'i like', 'i love', 'i hate']):
            return 'statement'
        
        # Goodbye
        if any(word in text for word in ['bye', 'goodbye', 'see you', 'later', 'farewell']):
            return 'goodbye'
        
        # Default
        return 'conversation'
    
    def _calculate_confidence(self, text: str, intent: str) -> float:
        """Calculate confidence in intent detection"""
        # Base confidence
        confidence = 0.5
        
        # Increase based on clear indicators
        if intent == 'greeting' and any(word in text for word in ['hello', 'hi', 'hey']):
            confidence = 0.9
        elif intent == 'question' and text.endswith('?'):
            confidence = 0.8
        elif intent == 'request' and 'please' in text:
            confidence = 0.85
        elif intent == 'statement' and 'i' in text:
            confidence = 0.75
        
        return min(confidence, 1.0)
    
    def _extract_entities(self, text: str) -> List[str]:
        """Extract named entities from text"""
        entities = []
        words = text.split()
        
        # Capitalized words (potential proper nouns)
        for word in words:
            if len(word) > 1 and word[0].isupper() and word[1:].islower():
                entities.append(word)
        
        return entities
    
    def _detect_topic(self, text: str) -> Optional[str]:
        """Detect conversation topic"""
        topics = {
            'ai': ['ai', 'artificial intelligence', 'machine learning', 'neural network', 'algorithm'],
            'technology': ['computer', 'software', 'hardware', 'code', 'programming', 'tech'],
            'emotions': ['feel', 'feeling', 'emotion', 'happy', 'sad', 'angry', 'excited'],
            'work': ['work', 'job', 'career', 'project', 'task', 'meeting'],
            'personal': ['family', 'friend', 'home', 'life', 'personal']
        }
        
        text_lower = text.lower()
        for topic, keywords in topics.items():
            if any(keyword in text_lower for keyword in keywords):
                return topic
        
        return None
    
    def _detect_sentiment(self, text: str) -> str:
        """Detect sentiment"""
        positive_words = ['good', 'great', 'wonderful', 'amazing', 'love', 'like', 'happy', 'excellent', 'awesome', 'fantastic']
        negative_words = ['bad', 'terrible', 'awful', 'hate', 'dislike', 'sad', 'horrible', 'worst', 'hate']
        
        text_lower = text.lower()
        pos_count = sum(1 for word in positive_words if word in text_lower)
        neg_count = sum(1 for word in negative_words if word in text_lower)
        
        if pos_count > neg_count:
            return 'positive'
        elif neg_count > pos_count:
            return 'negative'
        else:
            return 'neutral'
    
    def _register_with_thalamus(self):
        """Register with Thalamus - DIRECT FUNCTION CALL (NO SOCKETS)"""
        try:
            result = self.thalamus.register_lobe('conversation', self)
            if result.get('status') == 'success':
                print("✅ Conversation registered with Thalamus (direct function calls)")
                return True
            return False
        except Exception as e:
            print(f"⚠️  Failed to register with Thalamus: {e}")
            return False
    
    def _push_intent_to_reasoning(self, user_input: str, understanding: Dict[str, Any]):
        """Push intent hints and suggested strategy to Reasoning lobe"""
        intent = understanding.get('intent', 'conversation')
        confidence = understanding.get('confidence', 0.5)
        
        # Suggest thinking strategy based on intent
        strategy_mapping = {
            'greeting': 'social_greeting',
            'question': 'information_gathering',
            'request': 'help_seeking',
            'statement': 'expression_analysis',
            'goodbye': 'social_closing',
            'conversation': 'engagement'
        }
        
        suggested_strategy = strategy_mapping.get(intent, 'engagement')
        
        try:
            # Send intent hints to Reasoning through Thalamus
            self.thalamus.send_message(
                destination='reasoning',
                msg_type='intent_hints',
                content={
                    'user_input': user_input,
                    'intent': intent,
                    'confidence': confidence,
                    'suggested_strategy': suggested_strategy,
                    'entities': understanding.get('entities', []),
                    'topic': understanding.get('topic'),
                    'sentiment': understanding.get('sentiment', 'neutral')
                },
                source='conversation'
            )
        except Exception as e:
            print(f"⚠️  Failed to push intent to Reasoning: {e}")
    
    def start(self):
        """Start conversation - register with Thalamus (NO SOCKETS)"""
        print(f"💬 Conversation Lobe: Registering with Thalamus...")
        print(f"   Intent detection, context management, topic tracking")
        print(f"   Communication: Direct function calls (NO SOCKETS)")
        
        # Register with Thalamus
        if not self._register_with_thalamus():
            print("❌ Failed to register with Thalamus")
            return
        
        # Keep running (Thalamus calls us directly, no listening loop needed)
        while self.running:
            time.sleep(0.1)
    
    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming message"""
        msg_type = message.get('type')
        payload = message.get('content', message)
        
        if msg_type == 'health':
            return {'status': 'success', 'healthy': True, 'pid': os.getpid()}
        
        elif msg_type == 'understand':
            user_input = payload.get('user_input', '')
            context = payload.get('context', {})
            if not isinstance(context, dict):
                context = {}
            # Live path may pass perception at top level or inside context.
            perception = payload.get('perception')
            if isinstance(perception, dict):
                context = dict(context)
                context['perception'] = perception

            understanding = self.understand(user_input, context)
            # Fold perception entities/concepts into understanding when present.
            perc = context.get('perception') if isinstance(context.get('perception'), dict) else {}
            if perc:
                entities = list(understanding.get('entities') or [])
                for ent in perc.get('entities') or []:
                    if ent and ent not in entities:
                        entities.append(ent)
                understanding['entities'] = entities
                understanding['perception_concepts'] = perc.get('concepts') or perc.get('words') or []
                understanding['perception_words'] = perc.get('words') or []
                if perc.get('sentiment') and understanding.get('sentiment') in (None, 'neutral'):
                    understanding['sentiment'] = perc.get('sentiment')

            return {
                'status': 'success',
                'content': {
                    'understanding': understanding,
                    'intent': understanding.get('intent'),
                    'confidence': understanding.get('confidence'),
                    'sentiment': understanding.get('sentiment'),
                    'entities': understanding.get('entities', [])
                }  # Thalamus will transform this
            }
        
        elif msg_type == 'check_unprompted_speech':
            # Check if Monday wants to say something unprompted
            try:
                speech_result = self.thalamus.send_message('speech', 'get_pending_speech', {})
                if speech_result and speech_result.get('status') == 'success':
                    speech_item = speech_result.get('speech')
                    if speech_item:
                        # Monday has something to say!
                        return {
                            'status': 'success',
                            'has_speech': True,
                            'speech': speech_item.get('content', '')
                        }
            except Exception as e:
                pass
            
            return {'status': 'success', 'has_speech': False}
        
        elif msg_type == 'get_history':
            return {
                'status': 'success',
                'history': list(self.state.history),
                'current_topic': self.state.current_topic
            }
        
        else:
            return {'status': 'error', 'message': f'Unknown message type: {msg_type}'}
    
    def maybe_curiosity_follow_up(
        self,
        user_input: str,
        emotional_context: Optional[Dict[str, Any]] = None,
        understanding: Optional[Dict[str, Any]] = None,
        *,
        force: bool = False,
    ) -> Optional[str]:
        """Maybe one honest follow-up when affect is hot or unresolved.

        Mild social turns never force a question. Does not use novelty_lobe.
        """
        emotional_context = emotional_context if isinstance(emotional_context, dict) else {}
        understanding = understanding if isinstance(understanding, dict) else {}
        intent = understanding.get("intent")

        if is_mild_social_turn(user_input, intent) and not force:
            return None
        # Clear fact-teaching turns must not get "what did you mean by …" spam.
        if looks_like_teaching_turn(user_input) and not force:
            return None

        try:
            intensity = float(emotional_context.get("intensity", 0.0) or 0.0)
        except (TypeError, ValueError):
            intensity = 0.0
        unresolved = emotional_context.get("unresolved_appraisals") or []
        if not isinstance(unresolved, list):
            unresolved = []
        max_sev = 0.0
        if unresolved:
            try:
                max_sev = max(
                    float(u.get("severity", 0.0) or 0.0)
                    for u in unresolved
                    if isinstance(u, dict)
                )
            except Exception:
                max_sev = 0.55

        eligible = bool(force) or bool(unresolved) or intensity >= 0.70
        if not eligible:
            return None

        if not force:
            # Sometimes — bias toward asking when unresolved / hot, never spam.
            if unresolved and (intensity >= 0.50 or max_sev >= 0.55):
                if random.random() >= 0.88:
                    return None
            elif intensity >= 0.70:
                if random.random() >= 0.55:
                    return None
            else:
                return None

        try:
            return honest_curiosity_question(user_input, emotional_context)
        except Exception:
            return None
    
    def shutdown(self):
        """Graceful shutdown"""
        self.running = False
        # No sockets to close

if __name__ == "__main__":
    system = ConversationSystem()
    try:
        system.start()
    except KeyboardInterrupt:
        print("\n🛑 Conversation system shutting down...")
        system.shutdown()
