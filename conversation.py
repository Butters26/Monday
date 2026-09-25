#!/usr/bin/env python3
"""
Conversation System for Monday
Live-path intent / dialogue understanding and multi-turn context.

Owns: intent classification + slots/entities for Reasoning/Language.
Does not: write final prose replies, invent facts, or ground answers in memory.
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
from direct_response import (
    is_closing_social_turn,
    honest_curiosity_question,
    is_mild_social_turn,
    looks_like_teaching_turn,
    looks_questionish,
    _asks_about_monday_own_speech,
    _attribute_asked,
)
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
        
        # Curiosity question text stays here / direct_response; Novelty supplies
        # novelty_score via perception/understanding (not question spam).
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
        
        # Intent + slots owned here (Conversation). No final prose, no fact inventing.
        intent = self._detect_intent(user_input)
        slots = self._extract_slots(user_input, intent)
        confidence = self._calculate_confidence(user_input, intent, slots)

        # Extract entities
        entities = self._extract_entities(user_input)

        # Topic detection / multi-turn topic-shift state
        previous_topic = self.state.current_topic
        topic = self._detect_topic(text_lower)
        topic_shifted = False
        if intent == 'topic_shift':
            topic_shifted = True
            # Prefer explicit "talk about X" topic when present.
            shift_topic = slots.get('new_topic') if isinstance(slots, dict) else None
            if shift_topic:
                topic = shift_topic
        if topic:
            self.state.current_topic = topic

        # Sentiment
        sentiment = self._detect_sentiment(text_lower)

        # Curiosity is owned by emotion/conversation/direct_response — not novelty_lobe.
        # Live path attaches via Thalamus after emotion; understand only notes intent.
        understanding = {
            'intent': intent,
            'confidence': confidence,
            'entities': entities,
            'slots': slots,
            'ask_kind': slots.get('ask_kind') if isinstance(slots, dict) else None,
            'topic': topic,
            'previous_topic': previous_topic,
            'topic_shifted': topic_shifted or (intent == 'topic_shift'),
            'sentiment': sentiment,
            'context_length': len(self.state.history),
            'curiosity_question': None,
        }

        return understanding
    
    # Word-boundary greetings — never substring ("hi" inside "hiking").
    _GREETING_RE = re.compile(
        r"^\s*(?:hi|hello|hey|yo|sup|hiya|howdy|greetings|"
        r"good\s+(?:morning|afternoon|evening))\b[\s!.]*$",
        re.IGNORECASE,
    )
    _TOPIC_SHIFT_RE = re.compile(
        r"(?i)\b(?:anyway|anyways|changing\s+(?:the\s+)?subject|"
        r"different\s+topic|new\s+topic|"
        r"(?:let'?s|lets)\s+(?:talk|chat|discuss)\s+about|"
        r"talk\s+about\s+.+\s+instead|"
        r"instead[,]?\s+(?:let'?s|can\s+we)\s+talk)\b"
    )
    _EMOTIONAL_SHARE_RE = re.compile(
        r"(?i)\b(?:i\s+feel(?:ing)?\b|i(?:['\u2019]m|\s+am)\s+feeling\b|"
        r"i(?:['\u2019]m|\s+am)\s+(?:sad|scared|afraid|worried|anxious|heartbroken|"
        r"alone|devastated|terrified|grieving|hurt|angry|upset)\b|"
        # Light day/work distress shares (Conversation owns intent; Social tracks continuity).
        r"today\s+(?:really\s+)?sucked\b|"
        r"everything\s+(?:just\s+)?went\s+wrong\b|"
        r"(?:my\s+)?(?:day|today)\s+(?:was|is)\s+(?:awful|terrible|rough|horrible)\b|"
        r"(?:work|it|things)\s+(?:just\s+)?(?:kept\s+)?getting\s+worse\b)"
    )
    _REMEMBER_FACT_RE = re.compile(
        r"(?i)\bremember\s+(?:that\s+)?(?:(?:the|my)\s+)?([a-z][a-z0-9_\s-]{0,40}?)\s+is\s+(\S.+)$"
    )
    _REQUEST_START_RE = re.compile(
        r"(?i)^\s*(?:please\b|can\s+you\b|could\s+you\b|would\s+you\b|"
        r"help\s+me\b|show\s+me\b|tell\s+me\b|give\s+me\b)"
    )

    def _is_fact_teach(self, text: str) -> bool:
        """Durable personal-fact teaching — not a question ask."""
        if not text or looks_questionish(text) or text.strip().endswith("?"):
            return False
        if looks_like_teaching_turn(text):
            return True
        if self._REMEMBER_FACT_RE.search(text.strip()):
            return True
        return False

    def _is_topic_shift(self, text: str) -> bool:
        return bool(self._TOPIC_SHIFT_RE.search(text or ""))

    def _is_emotional_share(self, text: str) -> bool:
        if not text or looks_questionish(text) or self._is_fact_teach(text):
            return False
        return bool(self._EMOTIONAL_SHARE_RE.search(text))

    def _detect_intent(self, text: str) -> str:
        """Detect user intent from text. Conversation owns classification.

        Returns intent labels consumed by Reasoning/Language — never final prose.
        Priority avoids known mis-intents (teaching≠question, hiking≠greeting).
        """
        raw = (text or "").strip()
        if not raw:
            return "conversation"
        lower = raw.lower()

        # Goodbye first (short closings). Keep ahead of mild-social→greeting.
        if (
            re.search(
                r"(?i)(?:"
                r"\b(?:goodbye|bye\b|farewell|good\s*night|goodnight)\b|"
                r"\bsee\s+you(?:\s+later)?\b|"
                r"\btalk\s+(?:to\s+you\s+)?later\b|"
                r"\b(?:i\s+)?(?:gotta|have\s+to|need\s+to)\s+go\b"
                r")",
                lower,
            )
            and len(raw.split()) <= 14
        ):
            return "goodbye"

        # Monday-speech ask before generic question.
        if _asks_about_monday_own_speech(raw):
            return "monday_speech_ask"

        # Questions / asks (before teaching — "what is my name" must not be fact_teach).
        if looks_questionish(raw) or raw.endswith("?"):
            return "question"

        # Fact teaching (personal durable facts).
        if self._is_fact_teach(raw):
            return "fact_teach"

        # Greeting: word-boundary / mild-social only — not substring of other words.
        if is_mild_social_turn(raw) or self._GREETING_RE.match(raw):
            return "greeting"
        # Bare greeting word at start of a short social turn (no request/ask body).
        if re.match(
            r"(?i)^\s*(?:hi|hello|hey|yo|sup|hiya|howdy|greetings)\b",
            raw,
        ) and len(raw.split()) <= 4 and not self._REQUEST_START_RE.search(raw):
            return "greeting"

        # Explicit topic shift.
        if self._is_topic_shift(raw):
            return "topic_shift"

        # Emotional share.
        if self._is_emotional_share(raw):
            return "emotional_share"

        # Request/command (non-question).
        if self._REQUEST_START_RE.search(raw):
            return "request"

        # Soft statement markers.
        if any(
            p in lower
            for p in (
                "i think", "i believe", "i want", "i need", "i like", "i love", "i hate",
            )
        ):
            return "statement"

        return "conversation"

    def _attributes_from_ask(self, text: str) -> list:
        """Collect attribute slots for single- and multi-fact asks."""
        q = (text or "").strip()
        if not q:
            return []
        attrs: list = []
        seen = set()

        def _add(a: Optional[str]) -> None:
            if not a:
                return
            key = a.strip().lower()
            if key and key not in seen:
                seen.add(key)
                attrs.append(key)

        # Primary attribute helper (first / main).
        _add(_attribute_asked(q))

        # Compound: name + where live / work / favorite …
        if re.search(r"(?i)\bwhat(?:'s|\s+is)\s+my\s+name\b", q):
            _add("name")
        if re.search(r"(?i)\bwhere\s+do\s+i\s+live\b", q):
            _add("lives_in")
        if re.search(r"(?i)\bwhere\s+do\s+i\s+work\b", q):
            _add("work")
        for m in re.finditer(
            r"(?i)\bwhat(?:'s|\s+is)\s+my\s+(favorite\s+[a-z][a-z ]{0,40}?)\b",
            q,
        ):
            _add(" ".join(m.group(1).lower().split()))
        for m in re.finditer(
            r"(?i)\bwhat(?:'s|\s+is)\s+my\s+([a-z][a-z ]{0,40}?)(?:'s|s')\s+name\b",
            q,
        ):
            _add(" ".join(m.group(1).lower().split()) + " name")

        # Split on "and" / "?" clauses for additional attribute asks.
        for part in re.split(r"\b(?:\band\b|\?|;)", q):
            part = part.strip()
            if not part:
                continue
            _add(_attribute_asked(part if part.endswith("?") else part + "?"))

        return attrs

    def _extract_slots(self, text: str, intent: str) -> Dict[str, Any]:
        """Structured slots for Reasoning/Language — not prose answers."""
        raw = (text or "").strip()
        slots: Dict[str, Any] = {}

        if intent in {"question", "monday_speech_ask"}:
            attrs = self._attributes_from_ask(raw)
            if attrs:
                slots["attributes"] = attrs
            if intent == "monday_speech_ask":
                slots["ask_kind"] = "monday_speech"
            elif len(attrs) >= 2:
                slots["ask_kind"] = "multi_fact"
            elif attrs:
                slots["ask_kind"] = "fact_ask"
            else:
                slots["ask_kind"] = "question"
            if intent == "monday_speech_ask":
                # Topic needle from "about X" when present.
                about = re.search(r"(?i)\babout\s+(.+?)$", raw)
                if about:
                    slots["speech_topic"] = about.group(1).strip(" ?.!")

        elif intent == "fact_teach":
            slots["ask_kind"] = "teach"
            taught = []
            if re.search(r"(?i)\bmy\s+name\s+is\b", raw):
                taught.append("name")
            if re.search(r"(?i)\bi\s+live\s+in\b", raw):
                taught.append("lives_in")
            if re.search(r"(?i)\bi\s+work\s+(?:as|at|in)\b", raw):
                taught.append("work")
            fav = re.search(r"(?i)\bmy\s+(favorite\s+[a-z][a-z ]{0,40}?)\s+is\b", raw)
            if fav:
                taught.append(" ".join(fav.group(1).lower().split()))
            dog = re.search(r"(?i)\bmy\s+([a-z]+)'?s?\s+name\s+is\b", raw)
            if dog:
                taught.append(dog.group(1).lower() + " name")
            rem = self._REMEMBER_FACT_RE.search(raw)
            if rem:
                taught.append(re.sub(r"\s+", " ", rem.group(1).strip().lower()))
            if taught:
                slots["taught_attributes"] = taught

        elif intent == "topic_shift":
            slots["ask_kind"] = "topic_shift"
            m = re.search(
                r"(?i)(?:talk|chat|discuss)\s+about\s+(.+?)(?:\s+instead)?\s*$",
                raw,
            )
            if m:
                slots["new_topic"] = m.group(1).strip(" .!?")
            elif self.state.current_topic:
                slots["from_topic"] = self.state.current_topic

        elif intent == "emotional_share":
            slots["ask_kind"] = "emotional_share"

        elif intent == "greeting":
            slots["ask_kind"] = "greeting"

        return slots

    def _calculate_confidence(
        self, text: str, intent: str, slots: Optional[Dict[str, Any]] = None
    ) -> float:
        """Calculate confidence in intent detection"""
        confidence = 0.5
        lower = (text or "").lower()
        slots = slots if isinstance(slots, dict) else {}

        if intent == "greeting" and (
            is_mild_social_turn(text) or self._GREETING_RE.match(text or "")
        ):
            confidence = 0.9
        elif intent == "monday_speech_ask":
            confidence = 0.9
        elif intent == "fact_teach":
            confidence = 0.88 if slots.get("taught_attributes") else 0.8
        elif intent == "question":
            if (text or "").endswith("?"):
                confidence = 0.85
            elif looks_questionish(text or ""):
                confidence = 0.8
            if slots.get("ask_kind") == "multi_fact":
                confidence = max(confidence, 0.87)
        elif intent == "topic_shift":
            confidence = 0.85
        elif intent == "emotional_share":
            confidence = 0.82
        elif intent == "request" and "please" in lower:
            confidence = 0.85
        elif intent == "statement" and re.search(r"\bi\b", lower):
            confidence = 0.75
        elif intent == "goodbye":
            confidence = 0.9

        return min(confidence, 1.0)
    
    def _extract_entities(self, text: str) -> List[str]:
        """Extract named entities from text (proper nouns — not WH/greeting shells)."""
        entities = []
        skip = {
            "what", "who", "where", "when", "why", "how", "which",
            "hello", "hi", "hey", "goodbye", "bye", "please", "thanks",
            "thank", "my", "i", "im", "anyway", "anyways", "remember",
        }
        punct = ".,!?;:" + "'" + '"' + "()[]"
        words = text.split()
        for word in words:
            cleaned = word.strip(punct)
            if len(cleaned) > 1 and cleaned[0].isupper() and cleaned[1:].islower():
                if cleaned.lower() in skip:
                    continue
                entities.append(cleaned)
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
            'fact_teach': 'fact_encoding',
            'question': 'information_gathering',
            'monday_speech_ask': 'own_speech_recall',
            'emotional_share': 'empathic_listen',
            'topic_shift': 'topic_reorient',
            'request': 'help_seeking',
            'statement': 'expression_analysis',
            'goodbye': 'social_closing',
            'conversation': 'engagement',
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
            attention = payload.get('attention')
            if isinstance(attention, dict):
                context = dict(context)
                context['attention'] = attention

            understanding = self.understand(user_input, context)
            # Fold perception entities/concepts into understanding when present.
            perc = context.get('perception') if isinstance(context.get('perception'), dict) else {}
            if perc:
                entities = list(understanding.get('entities') or [])
                for ent in perc.get('entities') or []:
                    if ent and ent not in entities:
                        entities.append(ent)
                understanding['entities'] = entities
                concepts = perc.get('concepts')
                if isinstance(concepts, dict):
                    concept_list = list(concepts.get('words') or [])
                    understanding['perception_words'] = concept_list
                else:
                    concept_list = list(concepts or perc.get('words') or [])
                    understanding['perception_words'] = list(perc.get('words') or concept_list)
                understanding['perception_concepts'] = concept_list
                understanding['perception_modality'] = perc.get('modality') or 'text'
                understanding['perception_novelty_flags'] = list(perc.get('novelty_flags') or [])
                try:
                    understanding['novelty_score'] = float(perc.get('novelty_score') or 0.0)
                except (TypeError, ValueError):
                    understanding['novelty_score'] = 0.0
                understanding['novelty_is_novel'] = bool(perc.get('novelty_is_novel'))
                if isinstance(perc.get('novelty'), dict):
                    understanding['novelty'] = dict(perc.get('novelty') or {})
                if perc.get('sentiment') and understanding.get('sentiment') in (None, 'neutral'):
                    understanding['sentiment'] = perc.get('sentiment')

            # Fold live attention ranking into understanding (priority, not theater).
            attn = context.get('attention') if isinstance(context.get('attention'), dict) else {}
            if attn:
                understanding['attention_focus'] = attn.get('focus')
                understanding['attention_focus_text'] = attn.get('focus_text')
                understanding['attention_focus_score'] = attn.get('focus_score')
                ranked = attn.get('ranked') or []
                understanding['attention_ranked'] = [
                    {
                        'id': r.get('id'),
                        'score': r.get('score'),
                        'text': r.get('text'),
                        'source': r.get('source'),
                    }
                    for r in ranked[:8]
                    if isinstance(r, dict)
                ]
                # Prefer high-salience entities first when perception listed them.
                focus_text = str(attn.get('focus_text') or '').strip()
                if focus_text and isinstance(understanding.get('entities'), list):
                    ents = list(understanding['entities'])
                    promoted = [e for e in ents if isinstance(e, str) and e and e.lower() in focus_text.lower()]
                    rest = [e for e in ents if e not in promoted]
                    if promoted:
                        understanding['entities'] = promoted + rest

            return {
                'status': 'success',
                'content': {
                    'understanding': understanding,
                    'intent': understanding.get('intent'),
                    'confidence': understanding.get('confidence'),
                    'sentiment': understanding.get('sentiment'),
                    'entities': understanding.get('entities', []),
                    'slots': understanding.get('slots', {}),
                    'ask_kind': understanding.get('ask_kind'),
                }  # Thalamus will transform this
            }
        
        elif msg_type == 'check_unprompted_speech':
            # Removed: speech pending queue is dead. Live asides are Thalamus-
            # delivered after speech.evaluate_thought; Conversation does not poll.
            return {
                'status': 'error',
                'message': 'check_unprompted_speech removed; speech lobe is decision-only',
                'has_speech': False,
            }
        
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
        """Maybe one honest follow-up when affect is hot, unresolved, or novel.

        Mild social turns never force a question. Consumes novelty_score from
        understanding (Novelty lobe signal) — does not ask Novelty to invent Qs.
        """
        emotional_context = emotional_context if isinstance(emotional_context, dict) else {}
        understanding = understanding if isinstance(understanding, dict) else {}
        intent = understanding.get("intent")

        if (
            is_mild_social_turn(user_input, intent)
            or is_closing_social_turn(user_input, intent)
            or intent == "goodbye"
        ) and not force:
            return None
        # Clear fact-teaching turns must not get "what did you mean by …" spam.
        if looks_like_teaching_turn(user_input) and not force:
            return None
        # Conversation-owned fact_teach (includes remember-X teaching helpers miss).
        if intent == "fact_teach" and not force:
            return None

        try:
            intensity = float(emotional_context.get("intensity", 0.0) or 0.0)
        except (TypeError, ValueError):
            intensity = 0.0
        try:
            novelty_score = float(understanding.get("novelty_score", 0.0) or 0.0)
        except (TypeError, ValueError):
            novelty_score = 0.0
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

        elevated_novelty = novelty_score >= 0.55
        eligible = (
            bool(force)
            or bool(unresolved)
            or intensity >= 0.70
            or elevated_novelty
        )
        if not eligible:
            return None

        if not force:
            # Sometimes — bias toward asking when unresolved / hot / novel, never spam.
            if unresolved and (intensity >= 0.50 or max_sev >= 0.55):
                if random.random() >= 0.88:
                    return None
            elif elevated_novelty and novelty_score >= 0.70:
                if random.random() >= 0.70:
                    return None
            elif elevated_novelty:
                if random.random() >= 0.45:
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
