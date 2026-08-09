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
        
        if intent == 'greet':
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

class LanguageGenerator:
    """Builds sentences from meaning - Monday's voice"""
    
    def __init__(self):
        self.running = True
        self.grammar = GrammarEngine()
        
        # Persistent connection to Thalamus (created once at startup, reused forever)
        # Direct reference to Thalamus (NO SOCKETS)
        self.thalamus = get_thalamus()
        
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
        """Adjust word selection based on current emotional state"""
        emotional_state = self._query_emotional_state()
        
        if not emotional_state:
            return semantic_input  # No emotion data, use defaults
        
        emotion_tone = emotional_state.get('emotional_tone', 'neutral')
        intensity = emotional_state.get('intensity', 0.5)
        
        # Modify vocabulary based on emotion
        adjusted_input = semantic_input.copy()
        
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
        
        try:
            # CRITICAL: Adjust word choice based on current emotion
            adjusted_input = self._adjust_words_for_emotion(semantic_input)
            
            sentence = self.grammar.compose_sentence(adjusted_input)
            # Ensure we never return None or empty string
            if not sentence or not isinstance(sentence, str) or not sentence.strip():
                return "I'm thinking about that."
            return sentence
        except Exception as e:
            print(f"❌ Generation error: {e}")
            return "I'm thinking about that."
    
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
        
        if msg_type == 'express':
            thought = message.get('thought', '')
            if not isinstance(thought, str) or not thought.strip():
                return {'status': 'error', 'message': 'A complete thought is required for expression'}
            return {
                'status': 'success',
                'response': thought,
                'sentence': thought,
                'preserved_thought': True,
            }
        elif msg_type == 'generate':
            semantic_input = message.get('semantic_input', {})
            sentence = self.generate(semantic_input)
            
            # Only send to Output if reasoning explicitly says this is the main response
            is_main_response = message.get('is_main_response', False)
            if is_main_response:
                # Pass user_input so Output can store the full conversation
                user_input = message.get('user_input', '')
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
