#!/usr/bin/env python3
"""
Language Generation Lobe - Monday's Speech Center
Grammar-based semantic-to-sentence construction
Pre-installed with grammar rules and vocabulary
Controlled by Reasoning lobe
"""

import socket
import struct
import json
import os
import random
import time
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from collections import deque

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
        if not concepts:
            return "I'm not sure about that"
        
        topic = concepts[0]
        
        if certainty < 0.3:
            patterns = [
                f"I'm not sure about {topic}",
                f"I don't know enough about {topic} yet",
                f"{topic} - that's something I'm still learning about",
                f"I haven't figured out {topic} yet"
            ]
        elif certainty < 0.6:
            patterns = [
                f"I think {topic} might be related to something, but I'm not certain",
                f"Possibly {topic} connects to other concepts, though I could be wrong",
                f"I'm exploring {topic} but don't have a clear answer yet"
            ]
        else:
            patterns = [
                f"I think I understand {topic}, but I'm not completely certain",
                f"{topic} seems to work a certain way, though I could be wrong"
            ]
        
        return random.choice(patterns)
    
    def _compose_statement(self, concepts: List[str], relations: Dict[str, str], 
                          certainty: float, perspective: bool, tense: str) -> str:
        if not concepts and not relations:
            return "I'm thinking about that"
        
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
        physical_words = ['food', 'pancake', 'color', 'outfit', 'clothes', 'taste', 'smell']
        if any(word in thing.lower() for word in physical_words):
            return f"I don't have a body, so I don't experience {thing} physically. But I'm curious why you like what you like"
        
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
            return None  # Can't construct without concepts
        
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
        
        q_word = random.choice(['what', 'how', 'why'])
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
    
    def __init__(self, socket_path="/tmp/language.sock"):
        self.socket_path = socket_path
        self.running = True
        self.grammar = GrammarEngine()
        
    def generate(self, semantic_input: Dict[str, Any]) -> str:
        """Generate sentence from semantic input with defensive checks (FIX)"""
        if not isinstance(semantic_input, dict):
            return "I couldn't understand that."
        try:
            return self.grammar.compose_sentence(semantic_input)
        except Exception as e:
            print(f"❌ Generation error: {e}")
            return "I'm thinking about that."
    
    def start(self):
        """Start language generation lobe with hardened socket handling (FIX)"""
        try:
            if os.path.exists(self.socket_path):
                os.remove(self.socket_path)
        except Exception:
            pass
        
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(self.socket_path)
        sock.listen(5)
        sock.settimeout(1.0)  # FIX: accept timeout
        
        print(f"💬 Language Generation: Online at {self.socket_path}")
        print(f"   Grammar-based semantic-to-sentence construction")
        
        while self.running:
            try:
                try:
                    conn, _ = sock.accept()
                except socket.timeout:
                    continue  # FIX: allow loop to check self.running
                
                # FIX: per-connection timeout + recv safety
                try:
                    conn.settimeout(5.0)
                    
                    # Read length header
                    length_data = b''
                    while len(length_data) < 4:
                        chunk = conn.recv(4 - len(length_data))
                        if not chunk:
                            raise IOError("EOF while reading length")
                        length_data += chunk
                    msg_length = struct.unpack('!I', length_data)[0]
                    
                    # FIX: validate message length
                    if msg_length <= 0 or msg_length > 10_000_000:
                        raise ValueError(f"Invalid message length: {msg_length}")
                    
                    # Read full message
                    data = b''
                    while len(data) < msg_length:
                        chunk = conn.recv(min(msg_length - len(data), 4096))
                        if not chunk:
                            break
                        data += chunk
                    
                    message = json.loads(data.decode('utf-8'))
                    
                    # Handle message types
                    if message.get('type') == 'generate':
                        semantic_input = message.get('semantic_input', {})
                        sentence = self.generate(semantic_input)
                        result = {'status': 'success', 'sentence': sentence}
                    elif message.get('type') == 'health':  # FIX: add health probe
                        result = {'status': 'success', 'healthy': True, 'pid': os.getpid()}
                    else:
                        result = {'status': 'error', 'message': 'Unknown message type'}
                    
                    # Send response
                    response_data = json.dumps(result).encode('utf-8')
                    response_length = struct.pack('!I', len(response_data))
                    conn.sendall(response_length + response_data)
                    
                except Exception as e:
                    # FIX: try to send error before close
                    try:
                        err = {'status': 'error', 'message': str(e)}
                        conn.sendall(struct.pack('!I', len(json.dumps(err).encode('utf-8'))) + json.dumps(err).encode('utf-8'))
                    except Exception:
                        pass
                finally:
                    # FIX: always close
                    try:
                        conn.close()
                    except Exception:
                        pass
                        
            except Exception as e:
                print(f"❌ Language generation error: {e}")
                time.sleep(0.2)
        
        try:
            sock.close()
        except Exception:
            pass

    def shutdown(self):
        """Graceful shutdown"""
        self.running = False
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)

if __name__ == "__main__":
    generator = LanguageGenerator()
    try:
        generator.start()
    except KeyboardInterrupt:
        print("\n🛑 Language generation shutting down...")
        generator.shutdown()
