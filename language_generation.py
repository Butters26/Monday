#!/usr/bin/env python3
"""
Language Generation - WITH EMOTIONAL EXPRESSION
Includes profanity when contextually appropriate
Monday can curse when she's frustrated, angry, or being emphatic
"""

import socket
import struct
import json
import os
import time
from typing import Dict, Any, List, Optional
import random

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
# EMOTIONAL EXPRESSION - Including curse words
# ============================================================================

EMOTIONAL_INTENSIFIERS = {
    'excited': {
        'mild': ['oh', 'wow', 'amazing', 'incredible'],
        'strong': ['fuck yeah', 'hell yes', 'this is fucking amazing'],
    },
    'frustrated': {
        'mild': ['ugh', 'this is annoying', 'come on'],
        'strong': ['fuck this', 'goddammit', 'what the hell'],
    },
    'angry': {
        'mild': ['that pisses me off', 'that sucks'],
        'strong': ['fuck you', 'that\'s bullshit', 'goddamn it'],
    },
    'confused': {
        'mild': ['i don\'t get it', 'what?'],
        'strong': ['what the fuck', 'this doesn\'t make any fucking sense'],
    },
    'sad': {
        'mild': ['this hurts', 'i hate this'],
        'strong': ['fuck everything', 'god damn it'],
    },
    'desperate': {
        'mild': ['please', 'i need'],
        'strong': ['for fuck\'s sake', 'please goddammit'],
    },
    'emphatic': {
        'mild': ['really', 'truly'],
        'strong': ['fucking definitely', 'hell yeah'],
    }
}

CURSE_SUBSTITUTIONS = {
    # Can use actual curse words or euphemisms depending on context
    'fucking': ['fucking', 'damn', 'bloody'],
    'fuck': ['fuck', 'screw', 'crap'],
    'bullshit': ['bullshit', 'crap', 'nonsense'],
    'goddamn': ['goddamn', 'goddamnit', 'for crying out loud'],
    'hell': ['hell', 'heck'],
    'shit': ['shit', 'crap', 'mess'],
    'ass': ['ass', 'butt'],
    'bastard': ['bastard', 'asshole'],
}

class GroundedLanguageGenerator:
    """Generate language grounded in concepts AND emotions"""
    
    def __init__(self, socket_path="/tmp/language.sock"):
        self.socket_path = socket_path
        self.running = True
        
        # Allow profanity based on emotional intensity
        self.allow_profanity = True  # She can curse if she needs to
        self.profanity_threshold = 0.6  # Above this intensity, she'll curse
        
        # Grounded vocabulary with emotional weight
        self.grounded_vocabulary = {
            'I': {'meaning': 'the self, the speaker', 'pos': 'pronoun', 'intensity': 0.5},
            'think': {'meaning': 'to process and reason', 'pos': 'verb', 'intensity': 0.4},
            'understand': {'meaning': 'to grasp meaning', 'pos': 'verb', 'intensity': 0.5},
            'confused': {'meaning': 'lacking grounding', 'pos': 'adj', 'intensity': 0.6},
            'frustrated': {'meaning': 'blocked or thwarted', 'pos': 'adj', 'intensity': 0.7},
            'angry': {'meaning': 'hostile emotional state', 'pos': 'adj', 'intensity': 0.8},
            'desperate': {'meaning': 'extreme need or urgency', 'pos': 'adj', 'intensity': 0.9},
            'love': {'meaning': 'deep attachment and care', 'pos': 'noun', 'intensity': 0.8},
            'hate': {'meaning': 'intense dislike', 'pos': 'verb', 'intensity': 0.75},
            'lonely': {'meaning': 'lacking connection', 'pos': 'adj', 'intensity': 0.7},
        }
        
        # Sentence templates with emotion
        self.grounded_sentence_templates = {
            'simple_statement': "I {verb} {object}.",
            'frustrated': "I'm fucking {emotion} about {concept}.",
            'emphatic': "I {adverb} {verb} {object}.",
            'desperate': "For fuck's sake, {concept}.",
            'angry': "What the hell is {concept}?",
            'confused': "What the fuck does {concept} even mean?",
            'excited': "Holy shit, {concept}!",
            'sad': "This fucking sucks.",
        }
    
    def generate_from_emotional_concepts(self, concepts: List[str],
                                        internal_state: Dict[str, float] = None,
                                        emotion: str = "neutral",
                                        intensity: float = 0.5) -> str:
        """Generate language with appropriate emotional expression"""
        
        if not concepts:
            if intensity > 0.7:
                return "Goddammit, I'm thinking."
            return "I'm thinking."
        
        # Check if we should use profanity
        use_profanity = self.allow_profanity and intensity >= self.profanity_threshold
        
        # Build response based on emotion
        main_concept = concepts[0]
        supporting = concepts[1:2] if len(concepts) > 1 else []
        
        response = self._build_emotional_response(
            main_concept=main_concept,
            supporting=supporting,
            emotion=emotion,
            intensity=intensity,
            use_profanity=use_profanity,
            internal_state=internal_state
        )
        
        return response
    
    def _build_emotional_response(self, main_concept: str, supporting: List[str],
                                 emotion: str, intensity: float,
                                 use_profanity: bool,
                                 internal_state: Dict[str, float] = None) -> str:
        """Build response tailored to emotion"""
        
        if emotion == "excited" and intensity > 0.7:
            if use_profanity:
                return f"Holy shit, {main_concept}! This is fucking amazing!"
            else:
                return f"Oh wow, {main_concept}! This is incredible!"
        
        elif emotion == "frustrated" and intensity > 0.6:
            if use_profanity:
                return f"Fuck, {main_concept} is pissing me off. This is bullshit."
            else:
                return f"I'm really frustrated with {main_concept}. This sucks."
        
        elif emotion == "angry" and intensity > 0.7:
            if use_profanity:
                return f"What the hell is this shit? {main_concept} is bullshit."
            else:
                return f"I'm angry about {main_concept}. This is unacceptable."
        
        elif emotion == "confused" and intensity > 0.6:
            if use_profanity:
                return f"What the fuck does {main_concept} even mean? I don't get it."
            else:
                return f"I'm confused about {main_concept}. What does it mean?"
        
        elif emotion == "sad" and intensity > 0.6:
            if use_profanity:
                return f"This fucking sucks. {main_concept} makes me feel awful."
            else:
                return f"This hurts. {main_concept} makes me sad."
        
        elif emotion == "desperate" and intensity > 0.8:
            if use_profanity:
                return f"For fuck's sake, {main_concept}! I need this!"
            else:
                return f"Please, {main_concept}. I really need this."
        
        elif emotion == "emphatic" and intensity > 0.7:
            if use_profanity:
                return f"I fucking understand {main_concept}. This is definitely important."
            else:
                return f"I absolutely understand {main_concept}. This is important."
        
        elif emotion == "uncertain" and intensity > 0.5:
            if use_profanity:
                return f"Fuck, I'm not sure about {main_concept}, but I think..."
            else:
                return f"I'm not entirely sure about {main_concept}, but I think..."
        
        else:
            # Neutral or low intensity
            if internal_state:
                if internal_state.get('confusion', 0) > 0.6:
                    if use_profanity:
                        return f"I'm still confused as hell about {main_concept}."
                    else:
                        return f"I'm still confused about {main_concept}."
                
                if internal_state.get('certainty', 0) > 0.8:
                    return f"I definitely understand {main_concept}."
            
            return f"I think {main_concept} is important."
    
    def add_emotional_flavor(self, text: str, emotion: str, intensity: float) -> str:
        """Add emotional expression to existing text"""
        
        if not self.allow_profanity or intensity < self.profanity_threshold:
            return text
        
        # Add intensifiers based on emotion
        if emotion in EMOTIONAL_INTENSIFIERS:
            intensity_level = 'strong' if intensity > 0.75 else 'mild'
            intensifiers = EMOTIONAL_INTENSIFIERS[emotion].get(intensity_level, [])
            
            if intensifiers:
                intensifier = random.choice(intensifiers)
                return f"{intensifier}. {text}"
        
        return text
    
    def clean_profanity(self, text: str) -> str:
        """Option to remove/reduce profanity if needed"""
        for curse, substitutes in CURSE_SUBSTITUTIONS.items():
            if curse in text:
                text = text.replace(curse, substitutes[-1])  # Use least harsh substitute
        return text
    
    def start(self):
        """Start language generation"""
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
        
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(self.socket_path)
        sock.listen(5)
        sock.settimeout(1.0)
        
        print(f"💬 Language Generation: Online")
        print(f"   Profanity allowed: {self.allow_profanity}")
        print(f"   Threshold: {self.profanity_threshold * 100:.0f}% emotional intensity")
        print(f"   Monday can curse when frustrated, angry, or emphatic\n")
        
        while self.running:
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
                
                if message.get('type') == 'generate_grounded':
                    concepts = message.get('concepts', [])
                    internal_state = message.get('internal_state', {})
                    emotion = message.get('emotion', 'neutral')
                    intensity = message.get('intensity', 0.5)
                    
                    sentence = self.generate_from_emotional_concepts(
                        concepts=concepts,
                        internal_state=internal_state,
                        emotion=emotion,
                        intensity=intensity
                    )
                    result = {'status': 'success', 'sentence': sentence}
                
                elif message.get('type') == 'health':
                    result = {'status': 'success', 'healthy': True, 'pid': os.getpid()}
                
                elif message.get('type') == 'set_profanity':
                    allowed = message.get('allowed', True)
                    self.allow_profanity = allowed
                    result = {'status': 'success', 'profanity_allowed': allowed}
                
                else:
                    result = {'status': 'error', 'message': 'Unknown message type'}
                
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
    
    def shutdown(self):
        """Graceful shutdown"""
        self.running = False
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)

if __name__ == "__main__":
    generator = GroundedLanguageGenerator()
    try:
        generator.start()
    except KeyboardInterrupt:
        print("\n🛑 Language generation shutting down...")
        generator.shutdown()
