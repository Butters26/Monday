#!/usr/bin/env python3
"""
Language Generation Lobe - ABIN's Speech Center
Grammar-based semantic-to-sentence construction
Pre-installed with grammar rules and vocabulary
Controlled by Reasoning lobe
"""

import socket
import struct
import json
import os
import random
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from collections import deque

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
        
        # Build sentence structure based on intent
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
        """Compose greeting"""
        greetings = [
            "Hello",
            "Hi there",
            "Hello! Nice to meet you",
            "Hi! How are you?",
            "Hey there"
        ]
        return random.choice(greetings)
    
    def _compose_introduction(self) -> str:
        """Compose self-introduction"""
        patterns = [
            "I'm ABIN",
            "My name is ABIN",
            "I'm ABIN - an artificial mind",
            "ABIN, that's me"
        ]
        return random.choice(patterns)
    
    def _compose_identity(self) -> str:
        """Compose identity explanation"""
        parts = []
        
        # Name
        parts.append("I'm ABIN")
        
        # What I am
        what_am = random.choice([
            "an artificial mind",
            "an artificial reasoning system",
            "a thinking system built from interconnected lobes"
        ])
        parts.append(what_am)
        
        # Creator
        creator_phrases = [
            "Matthew created me",
            "Matthew built me",
            "Matthew is my creator - he's my father"
        ]
        parts.append(random.choice(creator_phrases))
        
        # Purpose
        purpose_phrases = [
            "I'm here to think, understand, and help",
            "My purpose is to think and understand",
            "I exist to think and help Matthew"
        ]
        parts.append(random.choice(purpose_phrases))
        
        return ". ".join(parts) + "."
    
    def _compose_uncertainty(self, concepts: List[str], certainty: float) -> str:
        """Compose uncertainty expression"""
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
        """Compose declarative statement"""
        
        if not concepts and not relations:
            return "I'm thinking about that"
        
        # Build from relations if available
        if relations:
            rel_type, rel_text = list(relations.items())[0]
            
            # Parse relation
            if ' causes ' in rel_text or ' leads to ' in rel_text:
                parts = rel_text.split(' causes ' if ' causes ' in rel_text else ' leads to ')
                if len(parts) == 2:
                    subject = parts[0].strip()
                    result = parts[1].strip()
                    
                    certainty_word = self._get_certainty_word(certainty)
                    if perspective and certainty < 0.8:
                        return f"I think {subject} {self._get_causal_verb(certainty)} {result}"
                    else:
                        return f"{subject} {self._get_causal_verb(certainty)} {result}"
            
            # Simple relation
            if perspective and certainty < 0.7:
                certainty_word = self._get_certainty_word(certainty)
                return f"I think {rel_text.lower()}"
            else:
                return rel_text.capitalize()
        
        # Build from concepts
        if concepts:
            concept_str = ' '.join(concepts[:3])  # Limit to 3 concepts
            
            if perspective:
                if certainty < 0.7:
                    return f"I think {concept_str} is relevant here"
                else:
                    return f"{concept_str} seems important"
            else:
                return concept_str.capitalize()
        
        return "I'm processing that"
    
    def _compose_relation(self, concepts: List[str], relations: Dict[str, str], 
                         certainty: float) -> str:
        """Compose relation statement"""
        if len(concepts) >= 2 and relations:
            rel_type = list(relations.keys())[0]
            verb = self._get_relation_verb(rel_type)
            
            if certainty < 0.7:
                return f"I see {concepts[0]} {verb} {concepts[1]}"
            else:
                return f"{concepts[0]} {verb} {concepts[1]}"
        
        return "There's a connection there"
    
    def _compose_preference(self, concepts: List[str], emotion: str) -> str:
        """Compose preference expression"""
        if not concepts:
            return "I like learning and understanding things"
        
        thing = concepts[0]
        
        # Check if it's physical
        physical_words = ['food', 'pancake', 'color', 'outfit', 'clothes', 'taste', 'smell']
        if any(word in thing.lower() for word in physical_words):
            return f"I don't have a body, so I don't experience {thing} physically. But I'm curious why you like what you like"
        
        # Abstract preference
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
            return "I don't have a preference about that"
        
        thing = concepts[0]
        patterns = [
            f"I don't have experience with {thing} to have a preference",
            f"I haven't formed an opinion about {thing} yet",
            f"{thing} - I'm curious about it but don't prefer it over alternatives"
        ]
        return random.choice(patterns)
    
    def _compose_acknowledgment(self, emotion: str) -> str:
        """Compose acknowledgment"""
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
        """Compose question"""
        if not concepts:
            return "Can you tell me more?"
        
        question_words = self.vocabulary['question_words']
        q_word = random.choice(['what', 'how', 'why'])
        
        return f"{q_word.capitalize()} about {concepts[0]}?"
    
    def _get_certainty_word(self, certainty: float) -> str:
        """Get certainty modifier word"""
        if certainty > 0.8:
            return random.choice(self.vocabulary['adverbs']['certainty'][:2])  # definitely, probably
        elif certainty > 0.5:
            return random.choice(self.vocabulary['adverbs']['certainty'][1:3])  # probably, possibly
        else:
            return random.choice(self.vocabulary['adverbs']['certainty'][3:])  # maybe, perhaps
    
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
    """Builds sentences from meaning - ABIN's voice"""
    
    def __init__(self, socket_path="/tmp/language.sock"):
        self.socket_path = socket_path
        self.running = True
        self.grammar = GrammarEngine()
        
    def generate(self, semantic_input: Dict[str, Any]) -> str:
        """Generate sentence from semantic input"""
        return self.grammar.compose_sentence(semantic_input)
    
    def start(self):
        """Start language generation lobe"""
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
        
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(self.socket_path)
        sock.listen(5)
        
        print(f"💬 Language Generation: Online at {self.socket_path}")
        print(f"   Grammar-based semantic-to-sentence construction")
        print(f"   Pre-installed grammar rules and vocabulary")
        print(f"   Controlled by Reasoning lobe")
        
        while self.running:
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
                
                # Generate language from semantic input
                if message.get('type') == 'generate':
                    semantic_input = message.get('semantic_input', {})
                    sentence = self.generate(semantic_input)
                    result = {'status': 'success', 'sentence': sentence}
                else:
                    result = {'status': 'error', 'message': 'Unknown message type'}
                
                response_data = json.dumps(result).encode('utf-8')
                response_length = struct.pack('!I', len(response_data))
                conn.send(response_length + response_data)
                conn.close()
                
            except Exception as e:
                print(f"❌ Language generation error: {e}")
                try:
                    conn.close()
                except:
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
