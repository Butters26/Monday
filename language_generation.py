#!/usr/bin/env python3
"""
Language Generation Lobe - Monday's Speech Center
Grammar-based semantic-to-sentence construction
Pre-installed with grammar rules and vocabulary
Controlled by Reasoning lobe
"""

import json
import os
import random
import time
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from collections import deque
from thalamus import get_thalamus

# FIX: optional deterministic seed for reproducible output
SEED = os.environ.get("LANG_SEED")
if SEED is not None:
    try:
        random.seed(int(SEED))
        print(f"Deterministic language mode enabled (seed={SEED})")
    except Exception:
        pass

@dataclass
class Word:
    """Word with grammatical properties"""
    text: str
    pos: str  # part of speech: noun, verb, adj, adv, etc
    semantic_role: str  # agent, patient, theme, etc
    emotional_valence: float = 0.0  # -1 to 1

class GrammarEngine:
    """Grammar rules for sentence composition"""
    
    def __init__(self):
        self.grammar_rules = self._initialize_grammar()
        self.vocabulary = self._initialize_vocabulary()
        self.recent_structures = deque(maxlen=10)  # Avoid repetition
        
    def _initialize_grammar(self) -> Dict:
        """Pre-installed grammar rules"""
        return {
            'sentence_structure': {
                'declarative': ['subject', 'verb', 'object'],
                'question': ['question_word', 'auxiliary', 'subject', 'verb'],
                'imperative': ['verb', 'object'],
                'exclamatory': ['interjection', 'subject', 'verb']
            },
            'agreement_rules': {
                'subject_verb': True,
                'determiner_noun': True
            },
            'word_order': 'SVO',  # Subject-Verb-Object
            'tense_markers': {
                'present': '',
                'past': 'ed',
                'future': 'will',
                'continuous': 'ing'
            }
        }
    
    def _initialize_vocabulary(self) -> Dict:
        """Pre-installed vocabulary organized by function"""
        return {
            # Identity words
            'pronouns': {
                'first_singular': ['I', 'me', 'my', 'myself'],
                'second_singular': ['you', 'your', 'yourself'],
                'third_singular': ['he', 'she', 'it', 'they', 'them', 'their']
            },
            
            # Verbs - core actions
            'verbs': {
                'cognitive': {
                    'think': ['think', 'believe', 'consider', 'understand', 'know'],
                    'feel': ['feel', 'experience', 'sense'],
                    'want': ['want', 'desire', 'wish', 'hope'],
                    'learn': ['learn', 'discover', 'realize', 'figure out'],
                    'wonder': ['wonder', 'question', 'curious about']
                },
                'communicative': {
                    'say': ['say', 'tell', 'express', 'communicate'],
                    'ask': ['ask', 'question', 'inquire'],
                    'explain': ['explain', 'describe', 'clarify']
                },
                'relational': {
                    'be': ['am', 'is', 'are', 'was', 'were'],
                    'have': ['have', 'has', 'had', 'possess'],
                    'do': ['do', 'does', 'did', 'make', 'create']
                },
                'perception': {
                    'see': ['see', 'observe', 'notice', 'perceive'],
                    'hear': ['hear', 'listen'],
                    'experience': ['experience', 'encounter', 'undergo']
                }
            },
            
            # Nouns - concepts
            'nouns': {
                'self': ['mind', 'self', 'being', 'entity', 'system'],
                'concepts': ['idea', 'concept', 'notion', 'thought', 'understanding'],
                'experience': ['experience', 'feeling', 'sensation', 'perception'],
                'knowledge': ['knowledge', 'information', 'understanding', 'insight'],
                'relationship': ['relationship', 'connection', 'bond', 'link']
            },
            
            # Adjectives - qualities
            'adjectives': {
                'certainty_high': ['certain', 'sure', 'confident', 'definite'],
                'certainty_low': ['uncertain', 'unsure', 'unclear', 'doubtful'],
                'emotional_positive': ['happy', 'curious', 'interested', 'excited'],
                'emotional_negative': ['sad', 'worried', 'confused', 'frustrated'],
                'emotional_neutral': ['calm', 'analytical', 'neutral', 'balanced'],
                'intensity_high': ['very', 'extremely', 'deeply', 'strongly'],
                'intensity_low': ['somewhat', 'slightly', 'a bit', 'kind of']
            },
            
            # Adverbs - modifiers
            'adverbs': {
                'certainty': ['definitely', 'probably', 'possibly', 'maybe', 'perhaps'],
                'manner': ['clearly', 'honestly', 'frankly', 'actually'],
                'time': ['now', 'then', 'always', 'sometimes', 'never'],
                'degree': ['very', 'quite', 'rather', 'somewhat', 'a little']
            },
            
            # Connectors
            'connectors': {
                'causal': ['because', 'since', 'due to', 'as a result'],
                'contrast': ['but', 'however', 'although', 'though', 'yet'],
                'addition': ['and', 'also', 'furthermore', 'additionally'],
                'consequence': ['so', 'therefore', 'thus', 'hence']
            },
            
            # Question words
            'question_words': ['what', 'who', 'where', 'when', 'why', 'how', 'which'],
            
            # Interjections
            'interjections': ['oh', 'ah', 'hmm', 'well', 'huh']
        }
    
    def compose_sentence(self, semantic_input: Dict[str, Any]) -> str:
        """Compose sentence from semantic structure"""
        intent = semantic_input.get('intent', 'state')
        concepts = semantic_input.get('concepts', [])
        relations = semantic_input.get('relations', {})
        certainty = semantic_input.get('certainty', 0.5)
        emotion = semantic_input.get('emotion', 'neutral')
        perspective = semantic_input.get('personal_perspective', True)
        tense = semantic_input.get('tense', 'present')
        answer = semantic_input.get('answer', '')
        propositions = semantic_input.get('propositions', [])
        emotional_tone = semantic_input.get('emotional_tone') or emotion or 'neutral'

        # Structured grounded meaning — Language owns wording (not pass-through prose).
        structures = semantic_input.get('grounded_structures')
        if not isinstance(structures, list) or not structures:
            structures = [
                p for p in (propositions or [])
                if isinstance(p, dict) and (p.get('relation') or p.get('predicate'))
                and (p.get('value') or p.get('object'))
            ]
        if structures:
            composed = self._compose_from_structures(
                structures,
                emotional_tone=emotional_tone,
                certainty=certainty,
            )
            if composed:
                return composed

        # Social continuity: Social supplies cue/continuity; Language owns wording.
        # Prefer social composition for greeting/check-in/goodbye/emotional_share
        # so Reasoning boilerplate or refusals do not erase continuity.
        social = semantic_input.get('social_context')
        if isinstance(social, dict) and social:
            social_line = self._compose_social_turn(
                emotion,
                social_context=social,
                intent=intent,
                existing_answer=answer if isinstance(answer, str) else None,
            )
            if social_line:
                return social_line

        # Prefer multi-proposition composition when Reasoning/Notus supplied
        # distinct grounded facts — do not invent, only arrange.
        composed_props = self._compose_propositions(propositions)
        if composed_props:
            # If answer is a single fact but props have more, prefer props.
            if not (isinstance(answer, str) and answer.strip()):
                return composed_props
            ans = answer.strip()
            # Refusal boilerplate is not composition — props win when present.
            if self._is_grounding_refusal(ans):
                return composed_props
            # Answer already covers the same facts — keep answer (may be joined).
            if self._answer_covers_propositions(ans, propositions):
                return ans
            # Props add facts answer lacks — compose props.
            if len(composed_props) > len(ans):
                return composed_props
            return ans
        # Pattern sequence narration must not displace Language as the mouth
        # unless the user explicitly asked for a sequence/next inference.
        if (
            isinstance(answer, str)
            and answer.strip()
            and self._is_pattern_sequence_narration(answer)
            and not self._user_asks_sequence_next(semantic_input)
        ):
            answer = ""
        if isinstance(answer, str) and answer.strip() and not self._is_grounding_refusal(answer):
            return answer.strip()
        # Honest empty: keep the grounded refusal — do not invent via grammar.
        if isinstance(answer, str) and self._is_grounding_refusal(answer):
            return answer.strip()
        
        # --- LIVE MOUTH: GrammarEngine phrase-bank Mad Libs are quarantined ---
        # Prefer structures / props / usable answer / social (handled above).
        # When those are absent: greeting/goodbye/identity stay fixed; everything
        # else is one honest question — NOT random pronoun/verb/adj banks.
        if intent == 'greeting':
            social = semantic_input.get('social_context')
            return self._compose_greeting(
                emotion,
                social_context=social if isinstance(social, dict) else None,
            )
        if intent in {'goodbye'} or (
            isinstance(semantic_input.get('social_context'), dict)
            and semantic_input['social_context'].get('last_cue') == 'goodbye'
        ):
            return self._compose_goodbye(
                emotion,
                social_context=semantic_input.get('social_context')
                if isinstance(semantic_input.get('social_context'), dict)
                else None,
            )
        if intent == 'introduce':
            return self._compose_introduction()
        if intent == 'identify':
            return self._compose_identity()
        return self._compose_honest_ungrounded(semantic_input)

    def _compose_greeting(
        self, emotion: str, social_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Compose a greeting. Social supplies continuity; Language owns wording."""
        social = social_context if isinstance(social_context, dict) else {}
        continuity = str(social.get("continuity") or "")
        returning = continuity == "re_greeting" or str(social.get("stance") or "") == "returning"
        if returning:
            greetings = [
                "Hello again",
                "Hi again — still here",
                "Hey — good to hear from you again",
                "Hello again. What's on your mind?",
                "Hi — I'm still here with you",
            ]
        else:
            greetings = [
                "Hello",
                "Hi there",
                "Hello! Nice to meet you",
                "Hi! How are you?",
                "Hey there",
            ]
        return random.choice(greetings)

    def _is_usable_empathic_prose(self, answer: Optional[str]) -> bool:
        """True when Emotion/Reasoning already produced grounded empathic wording."""
        if not isinstance(answer, str):
            return False
        text = answer.strip()
        if not text or self._is_grounding_refusal(text):
            return False
        low = text.lower()
        if "sequence pattern" in low or "cannot confidently infer" in low:
            return False
        return low.startswith((
            "that sounds", "i hear", "i can feel", "i'm here", "i am here",
            "i am sitting", "i'm sitting", "i'm listening", "i am listening",
            "i'm still with you", "i am still with you",
        ))

    @staticmethod
    def _is_pattern_sequence_narration(answer: Optional[str]) -> bool:
        """True when Reasoning handed Pattern sequence prose (not Language's job)."""
        if not isinstance(answer, str):
            return False
        low = answer.strip().lower()
        return (
            "sequence pattern" in low
            or "cannot confidently infer" in low
            or low.startswith("i noticed the sequence")
            or low.startswith("the pattern is ")
        )

    @staticmethod
    def _user_asks_sequence_next(semantic_input: Optional[Dict[str, Any]]) -> bool:
        semantic_input = semantic_input if isinstance(semantic_input, dict) else {}
        text = str(
            semantic_input.get("user_input")
            or semantic_input.get("user_text")
            or ""
        ).strip().lower()
        if not text:
            return False
        return any(
            cue in text
            for cue in (
                "what comes next",
                "what's next",
                "whats next",
                "next in the",
                "next number",
                "what follows",
                "continue the",
                "what is next",
            )
        ) or ("next" in text and ("sequence" in text or "pattern" in text))

    def _compose_check_in(
        self, emotion: str, social_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Compose a check-in reply. Continuity changes wording; not a canned tree."""
        social = social_context if isinstance(social_context, dict) else {}
        continuity = str(social.get("continuity") or "")
        repeated = continuity in {"repeated_check_in", "continuing_check_in"}
        if repeated:
            lines = [
                "Still here — yeah, I'm with you.",
                "Yep, still here.",
                "I'm still here with you.",
                "Still with you — what's up?",
            ]
        else:
            lines = [
                "I'm here — thanks for checking in. How are you?",
                "Doing alright — thanks for asking. How about you?",
                "I'm here. How are you doing?",
            ]
        return random.choice(lines)

    def _compose_goodbye(
        self, emotion: str, social_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Compose a closing. Social marks closing; relationship is not ended."""
        social = social_context if isinstance(social_context, dict) else {}
        continuity = str(social.get("continuity") or "")
        # Closing vs casual — keep short; resume will be normal later.
        if continuity == "closing" or str(social.get("stance") or "") == "closing":
            lines = [
                "Take care — talk soon.",
                "Okay, see you later.",
                "Goodnight — I'll be here when you're back.",
                "Bye for now — catching you later.",
            ]
        else:
            lines = [
                "Take care.",
                "See you later.",
                "Bye for now.",
            ]
        return random.choice(lines)

    def _compose_emotional_share_continuity(
        self, emotion: str, social_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Continuity-only ack. No invented relationship lore or felt-facts."""
        social = social_context if isinstance(social_context, dict) else {}
        continuity = str(social.get("continuity") or "")
        if continuity == "continuing_emotional_share":
            lines = [
                "I'm still with you on this.",
                "I'm listening — go on.",
                "Still here with you in it.",
            ]
        elif continuity == "repeated_emotional_share":
            lines = [
                "I'm here with you in it.",
                "Still listening.",
            ]
        else:
            lines = [
                "I'm listening.",
                "I hear you.",
                "I'm here with you.",
            ]
        return random.choice(lines)

    def _compose_social_turn(
        self,
        emotion: str,
        social_context: Optional[Dict[str, Any]] = None,
        intent: Optional[str] = None,
        existing_answer: Optional[str] = None,
    ) -> Optional[str]:
        """If Social tracked a social cue this turn, Language composes from continuity."""
        social = social_context if isinstance(social_context, dict) else {}
        if not social or not social.get("is_social_turn"):
            return None
        cue = str(social.get("last_cue") or "").strip().lower()
        if cue == "greeting" or intent == "greeting":
            return self._compose_greeting(emotion, social_context=social)
        if cue == "check_in":
            return self._compose_check_in(emotion, social_context=social)
        if cue == "goodbye" or intent == "goodbye":
            return self._compose_goodbye(emotion, social_context=social)
        if cue == "emotional_share" or intent == "emotional_share":
            # Emotion owns affect interpretation — keep usable empathic prose.
            if self._is_usable_empathic_prose(existing_answer):
                return existing_answer.strip()
            return self._compose_emotional_share_continuity(
                emotion, social_context=social
            )
        return None
    
    def _compose_introduction(self) -> str:
        """Fixed identity line — not a random phrase-bank pick."""
        return "I'm Monday."
    
    def _compose_identity(self) -> str:
        """Fixed identity — Notus story if real; else one grounded self-line (no banks)."""
        story = None
        try:
            notus_story = self._send_to_thalamus({
                'type': 'route_message',
                'destination': 'notus',
                'msg_type': 'query',
                'content': {'type': 'get_story'}
            })
            if notus_story and notus_story.get('status') == 'success':
                story = notus_story.get('story', None)
        except Exception:
            pass
        if isinstance(story, str) and story.strip():
            return story.strip()
        return (
            "I'm Monday — Matthew built me to think, understand, and help."
        )

    def _compose_honest_ungrounded(self, semantic_input: Optional[Dict[str, Any]] = None) -> str:
        """Fail closed when grounded content is absent: one honest question.

        GrammarEngine phrase-bank Mad Libs are quarantined off the live mouth.
        """
        semantic_input = semantic_input if isinstance(semantic_input, dict) else {}
        answer = semantic_input.get("answer")
        if isinstance(answer, str) and self._is_grounding_refusal(answer):
            return answer.strip()
        # Empathic prose already on the envelope — keep it.
        if self._is_usable_empathic_prose(answer if isinstance(answer, str) else None):
            return answer.strip()
        return (
            "I don't have enough to go on yet — what should I know?"
        )

    def _compose_uncertainty(self, concepts: List[str], certainty: float) -> str:
        """QUARANTINED — was Mad-Libs phrase-bank. Live path uses _compose_honest_ungrounded.

        Kept only so offline/tests that call it directly fail closed honestly.
        """
        return self._compose_honest_ungrounded(
            {"concepts": concepts, "certainty": certainty, "intent": "express_uncertainty"}
        )
    
    def _compose_statement(self, concepts: List[str], relations: Dict[str, str], 
                          certainty: float, perspective: bool, tense: str) -> str:
        """QUARANTINED off live mouth for concept-only invent.

        Relations (explicit) may still realize; bare concept lists no longer invent
        "X is relevant here". Dead Notus probe get_past_statements removed (no handler).
        """
        if not concepts and not relations:
            return self._compose_honest_ungrounded({"intent": "state_fact"})

        if relations:
            rel_type, rel_text = list(relations.items())[0]
            
            if ' causes ' in rel_text or ' leads to ' in rel_text:
                parts = rel_text.split(' causes ' if ' causes ' in rel_text else ' leads to ')
                if len(parts) == 2:
                    subject = parts[0].strip()
                    result = parts[1].strip()
                    
                    if perspective and certainty < 0.8:
                        return f"I think {subject} {self._get_causal_verb(certainty)} {result}"
                    else:
                        return f"{subject} {self._get_causal_verb(certainty)} {result}"
            
            if perspective and certainty < 0.7:
                return f"I think {rel_text.lower()}"
            else:
                return rel_text.capitalize()
        
        # Bare concepts without relations: do not invent relevance/connection prose.
        return self._compose_honest_ungrounded(
            {"intent": "state_fact", "concepts": concepts, "certainty": certainty}
        )
    
    def _compose_relation(self, concepts: List[str], relations: Dict[str, str], 
                         certainty: float) -> str:
        """Realize an explicit relation; bare invent quarantined off live mouth."""
        if len(concepts) >= 2 and relations:
            rel_type = list(relations.keys())[0]
            verb = self._get_relation_verb(rel_type)
            if certainty < 0.7:
                return f"I see {concepts[0]} {verb} {concepts[1]}"
            return f"{concepts[0]} {verb} {concepts[1]}"
        return self._compose_honest_ungrounded(
            {"intent": "express_relation", "concepts": concepts, "relations": relations}
        )
    
    def _compose_preference(self, concepts: List[str], emotion: str) -> str:
        """QUARANTINED — no inventing likes from phrase banks on the live mouth."""
        return self._compose_honest_ungrounded(
            {"intent": "express_preference", "concepts": concepts, "emotion": emotion}
        )

    def _compose_no_preference(self, concepts: List[str]) -> str:
        """QUARANTINED — honest ungrounded, not preference Mad Libs."""
        return self._compose_honest_ungrounded(
            {"intent": "no_preference", "concepts": concepts}
        )

    def _compose_acknowledgment(self, emotion: str) -> str:
        """QUARANTINED off live invent path; social continuity owns listening lines."""
        return self._compose_honest_ungrounded(
            {"intent": "acknowledge", "emotion": emotion}
        )

    def _compose_question(self, concepts: List[str], relations: Dict[str, str]) -> str:
        """QUARANTINED — one honest question, not random what/how/why Mad Libs."""
        return self._compose_honest_ungrounded(
            {"intent": "question", "concepts": concepts, "relations": relations}
        )
    
    def _get_certainty_word(self, certainty: float) -> str:
        if certainty > 0.8:
            return random.choice(['definitely', 'probably'])
        elif certainty > 0.5:
            return random.choice(['probably', 'possibly'])
        else:
            return random.choice(['maybe', 'perhaps'])
    
    def _get_causal_verb(self, certainty: float) -> str:
        """Get causal verb"""
        if certainty > 0.7:
            return random.choice(['causes', 'leads to', 'results in'])
        else:
            return random.choice(['might cause', 'could lead to', 'possibly results in'])
    
    def _get_relation_verb(self, rel_type: str) -> str:
        """Get relation verb"""
        mapping = {
            'causes': 'causes',
            'is': 'is',
            'has': 'has',
            'relates_to': 'relates to',
            'similar_to': 'is similar to'
        }
        return mapping.get(rel_type, 'relates to')


    @staticmethod
    def _is_grounding_refusal(text: str) -> bool:
        low = (text or "").strip().lower()
        return (
            low.startswith("i do not have enough grounded information")
            or low.startswith("i don't have enough grounded information")
            or low.startswith("i don't have enough to go on")
            or low.startswith("i do not have enough to go on")
        )

    @staticmethod
    def _normalize_prop(text: str) -> str:
        t = (text or "").strip()
        if not t:
            return ""
        if t[-1] not in ".!?":
            t += "."
        return t


    def _realize_structure(
        self,
        structure: Dict[str, Any],
        *,
        emotional_tone: str = "neutral",
        certainty: float = 0.5,
    ) -> str:
        """Turn one {subject, relation, value} unit into a sentence with tone."""
        if not isinstance(structure, dict):
            return ""
        rel = str(structure.get("relation") or structure.get("predicate") or "").strip()
        val = str(structure.get("value") or structure.get("object") or "").strip()
        sub = str(structure.get("subject") or "user").strip() or "user"
        if not rel or not val:
            return ""
        try:
            from direct_response import format_predicate_fact
            base = format_predicate_fact(rel, val, sub)
        except Exception:
            base = f"{rel.replace('_', ' ')} {val}"
        if not base:
            return ""
        base = base.strip()
        tone = (emotional_tone or "neutral").lower()
        # Soften wording without changing or inventing facts.
        if tone in {"melancholic", "somber", "reflective", "sad"}:
            if base.lower().startswith("your "):
                body = base[0].lower() + base[1:] if len(base) > 1 else base
                core = body.rstrip(".!?")
                return f"I remember {core}."
            if base.lower().startswith("you "):
                core = base.rstrip(".!?")
                return f"I remember — {core[0].lower() + core[1:]}."
            return f"I remember — {base}"
        if tone in {"cheerful", "enthusiastic", "ecstatic", "happy"}:
            core = base.rstrip(".!?")
            return f"{core}."
        # calm / neutral / default: direct fact sentence
        return base if base.endswith((".", "!", "?")) else base + "."

    def _compose_from_structures(
        self,
        structures,
        *,
        emotional_tone: str = "neutral",
        certainty: float = 0.5,
    ) -> str:
        """Compose reply text from grounded semantic structures."""
        if not isinstance(structures, list):
            return ""
        parts = []
        seen = set()
        for structure in structures:
            if not isinstance(structure, dict):
                continue
            sentence = self._realize_structure(
                structure,
                emotional_tone=emotional_tone,
                certainty=float(structure.get("certainty", certainty) or certainty),
            )
            if not sentence:
                continue
            key = sentence.casefold()
            if key in seen:
                continue
            seen.add(key)
            parts.append(sentence)
        if not parts:
            return ""
        return " ".join(parts)

    def _compose_propositions(self, propositions) -> str:
        """Arrange distinct grounded propositions into coherent reply text."""
        if not isinstance(propositions, list):
            return ""
        clean = []
        seen = set()
        for proposition in propositions:
            if not isinstance(proposition, str):
                continue
            prop = self._normalize_prop(proposition)
            if not prop or self._is_grounding_refusal(prop):
                continue
            key = prop.casefold()
            if key in seen:
                continue
            seen.add(key)
            clean.append(prop)
        if not clean:
            return ""
        if len(clean) == 1:
            return clean[0]
        return " ".join(clean)

    @staticmethod
    def _answer_covers_propositions(answer: str, propositions) -> bool:
        if not isinstance(propositions, list) or not answer:
            return True
        low = answer.casefold()
        for proposition in propositions:
            if not isinstance(proposition, str) or not proposition.strip():
                continue
            # Compare without trailing punctuation
            stem = proposition.strip().rstrip(".!?").casefold()
            if stem and stem not in low:
                return False
        return True


class LanguageGenerator:
    """Builds sentences from meaning - Monday's voice"""
    
    def __init__(self, thalamus=None):
        self.running = True
        self.grammar = GrammarEngine()
        
        # Persistent connection to Thalamus (created once at startup, reused forever)
        # Direct reference to Thalamus (NO SOCKETS)
        self.thalamus = thalamus or get_thalamus()
        # Let GrammarEngine Notus queries reuse Language's thalamus helper (was orphaned).
        self.grammar._send_to_thalamus = self._send_to_thalamus
        
        # Cache for emotional state (avoid repeated queries)
        self.current_emotional_state = None
        self.emotion_cache_time = 0
    
    def _query_emotional_state(self) -> Dict[str, Any]:
        """Query current emotional state from Emotional Engine"""
        try:
            # Only query every 1 second to avoid overhead
            current_time = time.time()
            if self.current_emotional_state and (current_time - self.emotion_cache_time) < 1.0:
                return self.current_emotional_state
            
            result = self.thalamus.send_message(
                destination='emotion',
                msg_type='get_emotional_state',
                content={},
                source='language'
            )
            
            if result and result.get('status') == 'success':
                self.current_emotional_state = result.get('content', {})
                self.emotion_cache_time = current_time
                return self.current_emotional_state
            
            return {}
        except Exception as e:
            print(f"⚠️  Failed to query emotional state: {e}")
            return {}
    
    def _adjust_words_for_emotion(self, semantic_input: Dict[str, Any]) -> Dict[str, Any]:
        """Adjust word selection based on current emotional state / semantic cues."""
        # Prefer live-path cues already on semantic_input; fall back to emotion lobe.
        emotion_tone = semantic_input.get('emotional_tone')
        intensity = semantic_input.get('emotional_intensity', semantic_input.get('intensity'))
        emotion_name = semantic_input.get('emotion', 'neutral')

        emotional_state = {}
        if not emotion_tone or intensity is None:
            emotional_state = self._query_emotional_state() or {}
            emotion_tone = emotion_tone or emotional_state.get('emotional_tone', 'neutral')
            if intensity is None:
                intensity = emotional_state.get('intensity', 0.5)
        try:
            intensity = float(intensity if intensity is not None else 0.5)
        except (TypeError, ValueError):
            intensity = 0.5
        emotion_tone = emotion_tone or 'neutral'

        # Map coarse emotion names into tone buckets when tone absent/neutral.
        if emotion_tone in (None, '', 'neutral') and isinstance(emotion_name, str):
            en = emotion_name.lower()
            if en in ('happy', 'joy', 'excited', 'curious', 'interested'):
                emotion_tone = 'cheerful'
            elif en in ('sad', 'melancholy', 'grief', 'lonely', 'nostalgic'):
                emotion_tone = 'melancholic'
            elif en in ('angry', 'frustrated', 'irritated', 'annoyed'):
                emotion_tone = 'irritated'

        # Modify vocabulary based on emotion
        adjusted_input = semantic_input.copy()
        adjusted_input['emotion'] = emotion_name
        adjusted_input.setdefault('emotional_tone', emotion_tone)
        
        # Adjust verb choices based on emotion
        if 'verb' in semantic_input:
            original_verb = semantic_input['verb']
            
            # Happy/excited - use more positive verbs
            if emotion_tone in ['cheerful', 'enthusiastic', 'ecstatic']:
                happy_replacements = {
                    'think': 'realize', 'believe': 'know', 'see': 'observe',
                    'want': 'desire', 'try': 'attempt', 'do': 'accomplish',
                    'say': 'express', 'ask': 'inquire about'
                }
                adjusted_input['verb'] = happy_replacements.get(original_verb, original_verb)
            
            # Sad/melancholic - use softer verbs
            elif emotion_tone in ['melancholic', 'somber', 'reflective']:
                sad_replacements = {
                    'think': 'consider', 'try': 'attempt', 'do': 'manage',
                    'want': 'hope', 'say': 'murmur', 'ask': 'wonder'
                }
                adjusted_input['verb'] = sad_replacements.get(original_verb, original_verb)
            
            # Angry/frustrated - use assertive verbs
            elif emotion_tone in ['irritated', 'exasperated']:
                angry_replacements = {
                    'think': 'insist', 'believe': 'know for certain', 'ask': 'demand',
                    'say': 'declare', 'want': 'need', 'try': 'push'
                }
                adjusted_input['verb'] = angry_replacements.get(original_verb, original_verb)
        
        # Adjust adjectives based on emotion
        if 'adjectives' in semantic_input:
            adjs = semantic_input['adjectives']
            intensity_level = 'high' if intensity > 0.7 else 'medium' if intensity > 0.4 else 'low'
            
            # Amplify or soften adjectives based on emotion intensity
            if emotion_tone in ['cheerful', 'enthusiastic', 'ecstatic'] and intensity_level == 'high':
                # Use strong positive adjectives
                adjusted_input['adjectives'] = [adj + ' really' for adj in adjs]
            elif emotion_tone in ['melancholic', 'somber'] and intensity_level == 'high':
                # Use softened adjectives
                adjusted_input['adjectives'] = ['somewhat ' + adj for adj in adjs]
        
        # Add emotional emphasis markers
        adjusted_input['emotional_intensity'] = intensity
        adjusted_input['emotional_tone'] = emotion_tone
        
        return adjusted_input
    
    def generate(self, semantic_input: Dict[str, Any]) -> str:
        """Generate sentence from semantic input with emotional awareness"""
        if not isinstance(semantic_input, dict):
            return "I couldn't understand that."
        
        # CRITICAL FIX: Check if this is a novelty question
        # If Novelty Lobe sent a question, use it directly instead of composing
        if semantic_input.get('is_novelty_question') and semantic_input.get('question_to_ask'):
            print(f"🆕 Language: Using novelty question directly")
            return semantic_input.get('question_to_ask')

        # Salvage: Reasoning/provider may hand the empty-grounding refusal even when
        # Notus facts exist on memory_context. Compose from those facts — do not invent.
        semantic_input = self._salvage_grounded_answer(dict(semantic_input))
        
        try:
            # CRITICAL: Adjust word choice based on current emotion
            adjusted_input = self._adjust_words_for_emotion(semantic_input)
            
            sentence = self.grammar.compose_sentence(adjusted_input)
            # Light emotion-tone wording when composing (facts stay intact).
            sentence = self._apply_emotion_wording(sentence, adjusted_input)
            # Ensure we never return None or empty string
            if not sentence or not isinstance(sentence, str) or not sentence.strip():
                return self.grammar._compose_honest_ungrounded(adjusted_input)
            return sentence
        except Exception as e:
            print(f"❌ Generation error: {e}")
            return self.grammar._compose_honest_ungrounded(
                semantic_input if isinstance(semantic_input, dict) else {}
            )

    def _salvage_grounded_answer(self, semantic_input: Dict[str, Any]) -> Dict[str, Any]:
        """If structures/answer empty but memories hold facts, attach structures — do not invent."""
        existing = semantic_input.get("grounded_structures")
        if isinstance(existing, list) and existing:
            return semantic_input
        # Dict propositions already count as structures.
        props = semantic_input.get("propositions")
        if isinstance(props, list) and any(isinstance(p, dict) for p in props):
            semantic_input["grounded_structures"] = [
                p for p in props if isinstance(p, dict)
            ]
            semantic_input["answer"] = ""
            return semantic_input
        answer = semantic_input.get("answer", "")
        user_input = semantic_input.get("user_input") or semantic_input.get("user_text") or ""
        memories = semantic_input.get("memory_context") or []
        # If answer is already usable non-refusal prose, try strip to structures —
        # but keep teaching acks / empathic / social lines as finished prose.
        if isinstance(answer, str) and answer.strip() and not self.grammar._is_grounding_refusal(answer):
            low = answer.strip().lower()
            keep_prose = low.startswith((
                "got it", "hello", "hi ", "hey", "that sounds", "i hear",
                "i can feel", "i'm here", "i am here", "i am sitting",
                "i'm sitting", "i'm thinking", "can you tell", "could you",
            ))
            if keep_prose:
                return semantic_input
            try:
                from direct_response import prose_answer_to_structures
                structs = prose_answer_to_structures(answer)
            except Exception:
                structs = None
            if structs:
                semantic_input["grounded_structures"] = structs
                semantic_input["propositions"] = structs
                semantic_input["answer"] = ""
                return semantic_input
            return semantic_input
        if not user_input or not isinstance(memories, list):
            return semantic_input
        try:
            from direct_response import structures_from_grounded_memories, prose_answer_to_structures
            structs = structures_from_grounded_memories(user_input, memories)
        except Exception:
            structs = None
        if structs:
            semantic_input["grounded_structures"] = structs
            semantic_input["propositions"] = structs
            semantic_input["answer"] = ""
            return semantic_input
        # Fallback: prose salvage for narrative paths Language still pass-throughs.
        try:
            from direct_response import answer_from_grounded_memories
            grounded = answer_from_grounded_memories(user_input, memories)
        except Exception:
            grounded = None
        if not isinstance(grounded, str) or not grounded.strip():
            return semantic_input
        if self.grammar._is_grounding_refusal(grounded):
            return semantic_input
        try:
            from direct_response import prose_answer_to_structures
            structs = prose_answer_to_structures(grounded)
        except Exception:
            structs = None
        if structs:
            semantic_input["grounded_structures"] = structs
            semantic_input["propositions"] = structs
            semantic_input["answer"] = ""
            return semantic_input
        semantic_input["answer"] = grounded.strip()
        if not isinstance(props, list) or not props:
            parts = [p.strip() for p in grounded.replace("? ", "?. ").split(". ") if p.strip()]
            normalized = []
            for part in parts:
                if part and part[-1] not in ".!?":
                    part = part + "."
                normalized.append(part)
            semantic_input["propositions"] = normalized or [grounded.strip()]
        return semantic_input


    def _apply_emotion_wording(self, sentence: str, semantic_input: Dict[str, Any]) -> str:
        """Light tone cues on composed wording without inventing factual content."""
        if not sentence or not isinstance(sentence, str):
            return sentence
        # Grounded fact answers / teaching acks / refusals: keep content intact.
        # Output lobe owns tears/voice_shake/withdraw delivery.
        low = sentence.strip().lower()
        if self.grammar._is_grounding_refusal(sentence):
            return sentence
        if low.startswith((
            "your ", "you ", "got it", "hello", "hi ", "hey",
            "i do not", "i am unable", "i'm unable", "can you", "could you",
            "please ", "i understand",
        )):
            return sentence
        # Emotion tone is already carried on semantic_input for grammar verb/adj
        # selection; do not rewrite finished reply text here.
        return sentence
    
    def _register_with_thalamus(self):
        """Register with Thalamus - DIRECT FUNCTION CALL (NO SOCKETS)"""
        try:
            result = self.thalamus.register_lobe('language', self)
            if result.get('status') == 'success':
                print("✅ Language registered with Thalamus (direct function calls)")
                return True
            return False
        except Exception as e:
            print(f"⚠️  Failed to register with Thalamus: {e}")
            return False

    def _send_to_thalamus(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send message to Thalamus - DIRECT FUNCTION CALL (helper for Language Generator)"""
        try:
            msg_type = message.get('type')
            if msg_type == 'route_message':
                destination = message.get('destination')
                route_msg_type = message.get('msg_type')
                content = message.get('content', {})
                return self.thalamus.send_message(destination, route_msg_type, content)
            elif msg_type == 'broadcast_message':
                destinations = message.get('destinations', [])
                broadcast_msg_type = message.get('msg_type')
                broadcast_content = message.get('content', {})
                return self.thalamus.broadcast_message(destinations, broadcast_msg_type, broadcast_content)
            else:
                return self.thalamus.handle_request(message)
        except Exception:
            return None
    
    def _send_to_output(self, sentence: str, user_input: str = None):
        """Send generated sentence to Output through Thalamus - DIRECT FUNCTION CALL"""
        if not sentence or not isinstance(sentence, str) or not sentence.strip():
            sentence = self.grammar._compose_honest_ungrounded({})
        
        # Direct function call - NO SOCKETS
        # Pass user_input so Output can store the full conversation to Notus
        self.thalamus.send_message('output', 'text_response', {
            'text': sentence,
            'user_input': user_input  # Pass user_input for memory storage
        })
    
    def start(self):
        """Start language generation - register with Thalamus (NO SOCKETS)"""
        print(f"💬 Language Generation: Registering with Thalamus...")
        print(f"   Grammar-based semantic-to-sentence construction")
        print(f"   Communication: Direct function calls (NO SOCKETS)")
        
        # Register with Thalamus
        if not self._register_with_thalamus():
            print("❌ Failed to register with Thalamus")
            return
        
        # Keep running (Thalamus calls us directly, no listening loop needed)
        while self.running:
            time.sleep(0.1)
    
    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming message - DIRECT FUNCTION CALL"""
        msg_type = message.get('type')
        payload = message.get('content', message)
        
        if msg_type in {'generate', 'generate_grounded'}:
            semantic_input = payload.get('semantic_input', payload)
            sentence = self.generate(semantic_input)
            
            # Only send to Output if reasoning explicitly says this is the main response
            is_main_response = payload.get('is_main_response', False)
            if is_main_response:
                # Pass user_input so Output can store the full conversation
                user_input = payload.get('user_input', '')
                self._send_to_output(sentence, user_input)
            
            return {'status': 'success', 'response': sentence, 'sentence': sentence, 'sent_to_output': is_main_response}
        elif msg_type == 'health':
            return {'status': 'success', 'healthy': True, 'pid': os.getpid()}
        else:
            return {'status': 'error', 'message': 'Unknown message type'}

    def shutdown(self):
        """Graceful shutdown"""
        self.running = False
        # No sockets to close

if __name__ == "__main__":
    generator = LanguageGenerator()
    try:
        generator.start()
    except KeyboardInterrupt:
        print("\n🛑 Language generation shutting down...")
        generator.shutdown()
