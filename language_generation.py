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
        if isinstance(answer, str) and answer.strip() and not self._is_grounding_refusal(answer):
            return answer.strip()
        # Honest empty: keep the grounded refusal — do not invent via grammar.
        if isinstance(answer, str) and self._is_grounding_refusal(answer):
            return answer.strip()
        
        # Query Notus for past language patterns
        try:
            notus_patterns = self._send_to_thalamus({
                'type': 'route_message',
                'destination': 'notus',
                'msg_type': 'query',
                'content': {'type': 'get_language_patterns', 'intent': intent}
            })
            if notus_patterns and notus_patterns.get('status') == 'success':
                patterns = notus_patterns.get('patterns', [])
                if patterns:
                    # Use learned pattern if available
                    pass  # Could enhance with learned patterns
        except Exception:
            pass
        
        if intent == 'greeting':
            return self._compose_greeting(emotion)
        elif intent == 'introduce':
            return self._compose_introduction()
        elif intent == 'identify':
            return self._compose_identity()
        elif intent == 'express_uncertainty':
            return self._compose_uncertainty(concepts, certainty)
        elif intent == 'state_fact':
            return self._compose_statement(concepts, relations, certainty, perspective, tense)
        elif intent == 'express_relation':
            return self._compose_relation(concepts, relations, certainty)
        elif intent == 'express_preference':
            return self._compose_preference(concepts, emotion)
        elif intent == 'no_preference':
            return self._compose_no_preference(concepts)
        elif intent == 'acknowledge':
            return self._compose_acknowledgment(emotion)
        elif intent == 'question':
            return self._compose_question(concepts, relations)
        else:
            return self._compose_statement(concepts, relations, certainty, perspective, tense)
    
    def _compose_greeting(self, emotion: str) -> str:
        greetings = [
            "Hello",
            "Hi there",
            "Hello! Nice to meet you",
            "Hi! How are you?",
            "Hey there"
        ]
        return random.choice(greetings)
    
    def _compose_introduction(self) -> str:
        patterns = [
            "I'm Monday",
            "My name is Monday",
            "I'm Monday - an artificial mind",
            "Monday, that's me"
        ]
        return random.choice(patterns)
    
    def _compose_identity(self) -> str:
        # Query Notus for actual story/experiences
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
        
        if story:
            return story
        
        parts = []
        parts.append("I'm Monday")
        what_am = random.choice([
            "an artificial mind",
            "an artificial reasoning system",
            "a thinking system built from interconnected lobes"
        ])
        parts.append(what_am)
        creator_phrases = [
            "Matthew created me",
            "Matthew built me",
            "Matthew is my creator - he's my father"
        ]
        parts.append(random.choice(creator_phrases))
        purpose_phrases = [
            "I'm here to think, understand, and help",
            "My purpose is to think and understand",
            "I exist to think and help Matthew"
        ]
        parts.append(random.choice(purpose_phrases))
        return ". ".join(parts) + "."
    
    def _compose_uncertainty(self, concepts: List[str], certainty: float) -> str:
        """Generate uncertainty statement compositionally - NO TEMPLATES"""
        if not concepts:
            # Build: pronoun + verb + adj + prep + demonstrative
            pronoun = random.choice(self.vocabulary['pronouns']['first_singular'])
            verb = random.choice(self.vocabulary['verbs']['cognitive']['think'])
            adj = random.choice(self.vocabulary['adjectives']['certainty_low'])
            return f"{pronoun} {verb} {adj} about that"
        
        topic = concepts[0]
        pronoun = random.choice(self.vocabulary['pronouns']['first_singular'])
        
        # Query Notus for knowledge status
        knowledge_status = None
        try:
            notus_knowledge = self._send_to_thalamus({
                'type': 'route_message',
                'destination': 'notus',
                'msg_type': 'query',
                'content': {'type': 'check_knowledge', 'topic': topic}
            })
            if notus_knowledge and notus_knowledge.get('status') == 'success':
                knowledge_status = notus_knowledge.get('status', {})
        except Exception:
            pass
        
        # Build uncertainty expression based on certainty level
        if certainty < 0.3:
            # Very uncertain
            verb = random.choice(self.vocabulary['verbs']['cognitive']['know'])
            adj = random.choice(self.vocabulary['adjectives']['certainty_low'])
            adv = random.choice(self.vocabulary['adverbs']['certainty'])
            return f"{pronoun} {adv} {verb} about {topic}"
        elif certainty < 0.6:
            # Moderately uncertain
            verb = random.choice(self.vocabulary['verbs']['cognitive']['think'])
            connector = random.choice(self.vocabulary['connectors']['contrast'])
            return f"{pronoun} {verb} about {topic}, {connector} {pronoun} could be wrong"
        else:
            # Mostly certain but acknowledging doubt
            verb = random.choice(self.vocabulary['verbs']['cognitive']['understand'])
            adj = random.choice(self.vocabulary['adjectives']['certainty_low'])
            return f"{pronoun} {verb} {topic}, though {pronoun} {verb} {adj}"
    
    def _compose_statement(self, concepts: List[str], relations: Dict[str, str], 
                          certainty: float, perspective: bool, tense: str) -> str:
        if not concepts and not relations:
            return "I'm thinking about that"
        
        # Query Notus for past statements about these concepts
        past_statements = []
        try:
            notus_statements = self._send_to_thalamus({
                'type': 'route_message',
                'destination': 'notus',
                'msg_type': 'query',
                'content': {'type': 'get_past_statements', 'concepts': concepts, 'limit': 3}
            })
            if notus_statements and notus_statements.get('status') == 'success':
                past_statements = notus_statements.get('statements', [])
        except Exception:
            pass
        
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
        
        if concepts:
            # Build proper sentences from concepts instead of just joining them
            if len(concepts) == 1:
                concept = concepts[0]
                if perspective:
                    if certainty < 0.7:
                        return f"I think {concept} is relevant here"
                    else:
                        return f"{concept} seems important to me"
                else:
                    return f"{concept.capitalize()} is what I'm focusing on"
            elif len(concepts) == 2:
                if perspective:
                    if certainty < 0.7:
                        return f"I think {concepts[0]} and {concepts[1]} are connected"
                    else:
                        return f"{concepts[0]} and {concepts[1]} seem related to me"
                else:
                    return f"{concepts[0].capitalize()} and {concepts[1]} are connected"
            else:
                # 3+ concepts - build a more complete sentence
                first = concepts[0]
                rest = ', '.join(concepts[1:-1])
                last = concepts[-1]
                if perspective:
                    if certainty < 0.7:
                        return f"I think {first}, {rest}, and {last} are all relevant here"
                    else:
                        return f"{first}, {rest}, and {last} seem important to me"
                else:
                    return f"{first.capitalize()}, {rest}, and {last} are connected"
        
        return "I'm processing that"
    
    def _compose_relation(self, concepts: List[str], relations: Dict[str, str], 
                         certainty: float) -> str:
        if len(concepts) >= 2 and relations:
            rel_type = list(relations.keys())[0]
            verb = self._get_relation_verb(rel_type)
            
            if certainty < 0.7:
                return f"I see {concepts[0]} {verb} {concepts[1]}"
            else:
                return f"{concepts[0]} {verb} {concepts[1]}"
        
        return "There's a connection there"
    
    def _compose_preference(self, concepts: List[str], emotion: str) -> str:
        if not concepts:
            return "I like learning and understanding things"
        
        thing = concepts[0]
        
        # Query Notus for past preferences about thing
        past_preference = None
        try:
            notus_pref = self._send_to_thalamus({
                'type': 'route_message',
                'destination': 'notus',
                'msg_type': 'query',
                'content': {'type': 'get_preferences', 'thing': thing}
            })
            if notus_pref and notus_pref.get('status') == 'success':
                past_preference = notus_pref.get('preference', None)
        except Exception:
            pass
        
        physical_words = ['food', 'pancake', 'color', 'outfit', 'clothes', 'taste', 'smell']
        if any(word in thing.lower() for word in physical_words):
            return f"I don't have a body, so I don't experience {thing} physically. But I'm curious why you like what you like"
        
        if past_preference:
            return past_preference
        
        patterns = [
            f"I like {thing}",
            f"{thing} - I enjoy that",
            f"I'm drawn to {thing}",
            f"{thing} interests me"
        ]
        return random.choice(patterns)
    
    def _compose_no_preference(self, concepts: List[str]) -> str:
        """Compose no preference expression"""
        if not concepts:
            return "I don't have a preference about that."
        
        thing = concepts[0]
        patterns = [
            f"I don't have experience with {thing} to have a preference",
            f"I haven't formed an opinion about {thing} yet",
            f"{thing} - I'm curious about it but don't prefer it over alternatives"
        ]
        return random.choice(patterns)
    
    def _compose_acknowledgment(self, emotion: str) -> str:
        acknowledgments = [
            "I'm listening",
            "Tell me more",
            "I hear you",
            "Go on",
            "I understand",
            "That makes sense"
        ]
        return random.choice(acknowledgments)
    
    def _compose_question(self, concepts: List[str], relations: Dict[str, str]) -> str:
        if not concepts:
            return "Can you tell me more?"
        
        # Query Notus for context to form better questions
        context = None
        try:
            notus_context = self._send_to_thalamus({
                'type': 'route_message',
                'destination': 'notus',
                'msg_type': 'query',
                'content': {'type': 'get_context', 'concepts': concepts}
            })
            if notus_context and notus_context.get('status') == 'success':
                context = notus_context.get('context', {})
        except Exception:
            pass
        
        q_word = random.choice(['what', 'how', 'why'])
        if context and context.get('related_topics'):
            return f"{q_word.capitalize()} about {concepts[0]} and {context.get('related_topics', [])[0]}?"
        return f"{q_word.capitalize()} about {concepts[0]}?"
    
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
        return low.startswith("i do not have enough grounded information")

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
                return "I'm thinking about that."
            return sentence
        except Exception as e:
            print(f"❌ Generation error: {e}")
            return "I'm thinking about that."

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
            sentence = "I'm thinking about that."
        
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
