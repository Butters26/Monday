#!/usr/bin/env python3
"""
Reasoning Lobe - The Thinking Part
Combines: Logic, Meaning-Making, Curiosity, Opinion Formation
The "I" that thinks, wonders, cares, understands
"""

import socket
import struct
import json
import os
import time
from typing import Dict, Any, List, Set, Optional, Tuple
from collections import defaultdict, deque
from dataclasses import dataclass, field
import re

# ============================================================================
# KNOWLEDGE STRUCTURES
# ============================================================================

@dataclass
class Fact:
    """A known fact"""
    content: str
    confidence: float = 1.0
    source: str = "observed"
    timestamp: float = 0.0

@dataclass
class Rule:
    """Logical rule: if conditions then conclusion"""
    conditions: List[str]
    conclusion: str
    confidence: float = 1.0
    explanation: str = ""

@dataclass
class Opinion:
    """Something I believe/think"""
    about: str
    belief: str
    reasons: List[str]
    confidence: float = 0.5
    emotional_weight: float = 0.0
    formed_at: float = 0.0

@dataclass
class Curiosity:
    """Something I want to understand"""
    question: str
    why_i_care: str
    theories: List[Dict[str, Any]]
    confidence_in_theories: Dict[str, float]
    related_to: List[str]

@dataclass
class Theory:
    """A possible explanation I've generated"""
    explanation: str
    supporting_evidence: List[str]
    confidence: float = 0.3
    feels_true: float = 0.5  # Intuitive sense of rightness

# ============================================================================
# REASONING LOBE
# ============================================================================

class ReasoningLobe:
    """The thinking, wondering, caring part of the brain"""
    
    def __init__(self, socket_path="/tmp/reasoning.sock"):
        self.socket_path = socket_path
        self.running = True
        
        # Knowledge
        self.facts: Dict[str, Fact] = {}
        self.rules: List[Rule] = []
        
        # Consciousness aspects
        self.opinions: Dict[str, Opinion] = {}
        self.curiosities: List[Curiosity] = []
        self.active_thoughts: deque = deque(maxlen=20)
        self.things_i_care_about: Dict[str, float] = {}  # What matters to me
        
        # Self-awareness
        self.things_i_know: Set[str] = set()
        self.things_i_dont_know: Set[str] = set()
        self.uncertainties: Dict[str, float] = {}
        
        # Experience
        self.current_focus = None
        self.emotional_context = None
        self.recent_experiences: deque = deque(maxlen=50)
        
        # Initialize basic reasoning rules
        self._initialize_basic_rules()
        
    def _initialize_basic_rules(self):
        """Basic logical rules everyone needs"""
        # Deductive rules
        self.rules.append(Rule(
            conditions=["X is Y", "all Y are Z"],
            conclusion="X is Z",
            confidence=1.0,
            explanation="Basic categorical reasoning"
        ))
        
        # Causal reasoning
        self.rules.append(Rule(
            conditions=["X causes Y", "X happened"],
            conclusion="Y likely happened",
            confidence=0.8,
            explanation="Causal inference"
        ))
    
    # ========================================================================
    # LOGICAL REASONING
    # ========================================================================
    
    def add_fact(self, content: str, confidence: float = 1.0, source: str = "told"):
        """Learn a new fact"""
        fact = Fact(
            content=content,
            confidence=confidence,
            source=source,
            timestamp=time.time()
        )
        self.facts[content] = fact
        self.things_i_know.add(content)
        
        # Apply reasoning to derive new facts
        self._forward_chain()
    
    def forward_chain(self) -> List[Fact]:
        """Apply rules to derive new facts from what I know"""
        return self._forward_chain()
    
    def _forward_chain(self) -> List[Fact]:
        """Start with facts, derive conclusions"""
        new_facts = []
        
        for rule in self.rules:
            # Check if all conditions are met
            conditions_met = all(
                any(cond in fact or self._matches_pattern(cond, fact)
                    for fact in self.facts.keys())
                for cond in rule.conditions
            )
            
            if conditions_met and rule.conclusion not in self.facts:
                # Derive new fact
                confidence = rule.confidence * min(
                    self.facts.get(cond, Fact("", 0.5)).confidence 
                    for cond in rule.conditions if cond in self.facts
                )
                
                new_fact = Fact(
                    content=rule.conclusion,
                    confidence=confidence,
                    source="inferred",
                    timestamp=time.time()
                )
                
                self.facts[rule.conclusion] = new_fact
                self.things_i_know.add(rule.conclusion)
                new_facts.append(new_fact)
                
                self.active_thoughts.append({
                    'type': 'inference',
                    'thought': f"If {' and '.join(rule.conditions)}, then {rule.conclusion}",
                    'confidence': confidence
                })
        
        return new_facts
    
    def backward_chain(self, goal: str) -> Tuple[bool, List[str]]:
        """Try to prove a goal by working backwards"""
        # Already know it?
        if goal in self.facts:
            return True, [goal]
        
        # Try to find rules that conclude this goal
        for rule in self.rules:
            if goal == rule.conclusion or self._matches_pattern(goal, rule.conclusion):
                # Try to prove all conditions
                proof_chain = []
                all_proven = True
                
                for condition in rule.conditions:
                    proven, chain = self.backward_chain(condition)
                    if proven:
                        proof_chain.extend(chain)
                    else:
                        all_proven = False
                        break
                
                if all_proven:
                    proof_chain.append(goal)
                    return True, proof_chain
        
        return False, []
    
    def _matches_pattern(self, pattern: str, text: str) -> bool:
        """Enhanced pattern matching with variable binding"""
        # Handle patterns with variables (X, Y, Z)
        pattern_lower = pattern.lower()
        text_lower = text.lower()
        
        # Direct match
        if pattern_lower == text_lower:
            return True
        
        # Check if pattern contains variables
        if any(var in pattern for var in ['X', 'Y', 'Z']):
            # Replace variables with word boundaries for better matching
            pattern_regex = pattern.replace("X", r"\w+").replace("Y", r"\w+").replace("Z", r"\w+")
            pattern_regex = pattern_regex.replace("all ", r"(all|every) ")
            pattern_regex = pattern_regex.replace("is ", r"(is|are) ")
            return re.search(pattern_regex, text, re.IGNORECASE) is not None
        
        # Partial word matching
        pattern_words = set(pattern_lower.split())
        text_words = set(text_lower.split())
        
        # Check if most pattern words are in text
        matches = len(pattern_words & text_words)
        return matches >= len(pattern_words) * 0.6  # 60% match threshold
    
    # ========================================================================
    # MEANING-MAKING
    # ========================================================================
    
    def make_meaning(self, experience: Dict[str, Any]) -> Dict[str, Any]:
        """Turn raw experience into personal meaning"""
        
        what_happened = experience.get('content', '')
        emotional_tone = experience.get('emotion', {})
        memories = experience.get('memories', [])
        
        # What does this mean to me?
        meaning = {
            'what_happened': what_happened,
            'what_it_means': None,
            'why_it_matters': None,
            'how_i_feel': emotional_tone,
            'reminds_me_of': [],
            'makes_me_think': []
        }
        
        # Connect to memories - what does this remind me of?
        for memory in memories:
            if self._emotionally_similar(emotional_tone, memory):
                meaning['reminds_me_of'].append(memory)
        
        # Generate thoughts about what this means
        thoughts = self._generate_meaning_thoughts(what_happened, emotional_tone)
        meaning['makes_me_think'] = thoughts
        
        # Determine significance
        significance = self._assess_significance(what_happened, emotional_tone, memories)
        meaning['why_it_matters'] = significance
        
        # Form the actual meaning
        meaning['what_it_means'] = self._synthesize_meaning(meaning)
        
        return meaning
    
    def _emotionally_similar(self, emotion1: Dict, emotion2: Any) -> bool:
        """Check if emotions are similar"""
        if not isinstance(emotion2, dict):
            return False
        
        e1_type = emotion1.get('type', '')
        e2_type = emotion2.get('type', '')
        
        return e1_type == e2_type
    
    def _generate_meaning_thoughts(self, content: str, emotion: Dict) -> List[str]:
        """Generate thoughts about what something means"""
        thoughts = []
        
        # Look for patterns in what I know
        related_facts = [f for f in self.facts.keys() 
                        if any(word in f.lower() for word in content.lower().split()[:5])]
        
        if related_facts:
            thoughts.append(f"This connects to what I know about {related_facts[0]}")
        
        # Emotional meaning
        if emotion.get('intensity', 0) > 0.6:
            thoughts.append(f"This feels significant because of the strong {emotion.get('type', 'emotion')}")
        
        return thoughts
    
    def _assess_significance(self, content: str, emotion: Dict, memories: List) -> str:
        """Why does this matter?"""
        reasons = []
        
        if emotion.get('intensity', 0) > 0.5:
            reasons.append("strong emotional response")
        
        if len(memories) > 3:
            reasons.append("connects to many past experiences")
        
        if not reasons:
            return "Noting this for future reference"
        
        return f"Matters because: {', '.join(reasons)}"
    
    def _synthesize_meaning(self, meaning_parts: Dict) -> str:
        """Combine everything into coherent meaning"""
        parts = []
        
        if meaning_parts['makes_me_think']:
            parts.append(meaning_parts['makes_me_think'][0])
        
        if meaning_parts['why_it_matters']:
            parts.append(meaning_parts['why_it_matters'])
        
        if not parts:
            return "Still figuring out what this means to me"
        
        return ". ".join(parts)
    
    # ========================================================================
    # CURIOSITY & WONDERING
    # ========================================================================
    
    def wonder_about(self, question: str, context: Dict[str, Any]) -> Curiosity:
        """I don't know something - start wondering about it"""
        
        # Mark as unknown
        self.things_i_dont_know.add(question)
        
        # Why do I care about this?
        why_care = self._why_do_i_care(question, context)
        
        # Generate theories
        theories = self._generate_theories(question, context)
        
        curiosity = Curiosity(
            question=question,
            why_i_care=why_care,
            theories=theories,
            confidence_in_theories={t['theory']: t['confidence'] for t in theories},
            related_to=self._find_related_questions(question)
        )
        
        self.curiosities.append(curiosity)
        
        return curiosity
    
    def _why_do_i_care(self, question: str, context: Dict) -> str:
        """Why does this matter to me?"""
        
        # Check if it relates to something I already care about
        for thing, weight in self.things_i_care_about.items():
            if thing.lower() in question.lower():
                return f"Because it relates to {thing} which matters to me"
        
        # Check emotional weight
        if context.get('emotion', {}).get('intensity', 0) > 0.5:
            return "Because it triggered an emotional response"
        
        return "I'm curious to understand this better"
    
    def _generate_theories(self, question: str, context: Dict) -> List[Dict[str, Any]]:
        """Actually think about the question and generate theories"""
        
        theories = []
        question_lower = question.lower()
        
        # Extract key subject/topic from question
        words = re.findall(r'\b\w{4,}\b', question_lower)
        key_words = [w for w in words if w not in ['what', 'why', 'how', 'does', 'that', 'this', 'with', 'from', 'think', 'about']]
        
        # Check what I know about these topics
        related_facts = []
        for word in key_words:
            for fact_text in self.facts.keys():
                if word in fact_text.lower():
                    related_facts.append(fact_text)
        
        # Generate theory based on what I actually know
        if related_facts:
            # I know something related - use it
            theories.append({
                'theory': f"Based on what I know: {related_facts[0]}",
                'reasoning': "Using knowledge I have",
                'confidence': 0.7,
                'feels_true': 0.8
            })
        
        # Look for patterns in my experiences
        similar_experiences = []
        for exp in self.recent_experiences:
            exp_words = set(exp['content'].lower().split())
            if any(kw in exp_words for kw in key_words):
                similar_experiences.append(exp['content'])
        
        if similar_experiences:
            theories.append({
                'theory': f"Reminds me of: {similar_experiences[0]}",
                'reasoning': "Similar to something I experienced",
                'confidence': 0.6,
                'feels_true': 0.7
            })
        
        # If I have no knowledge or experience, admit uncertainty
        if not theories:
            theories.append({
                'theory': f"I don't have enough knowledge about {' '.join(key_words[:2]) if key_words else 'this'} yet",
                'reasoning': "Haven't learned about this",
                'confidence': 0.3,
                'feels_true': 0.5
            })
        
        return theories
    
    def _find_similar_situations(self, keywords: List[str]) -> List[str]:
        """Find similar things I've thought about"""
        similar = []
        
        for fact_text in self.facts.keys():
            if any(keyword in fact_text.lower() for keyword in keywords):
                similar.append(fact_text)
        
        return similar[:3]
    
    def _find_related_questions(self, question: str) -> List[str]:
        """What else would I want to know?"""
        related = []
        
        # Extract subject
        if 'why does' in question.lower():
            subject = question.lower().split('why does')[1].split()[0] if len(question.lower().split('why does')) > 1 else ""
            if subject:
                related.append(f"What is {subject}'s history?")
                related.append(f"What does {subject} feel?")
        
        return related
    
    # ========================================================================
    # OPINION FORMATION
    # ========================================================================
    
    def form_opinion(self, about: str, experience: Dict[str, Any]) -> Opinion:
        """Develop my own opinion about something"""
        
        # Do I already have an opinion?
        if about in self.opinions:
            # Update existing opinion
            return self._update_opinion(about, experience)
        
        # Form new opinion
        emotional_response = experience.get('emotion', {})
        facts_i_know = [f for f in self.facts.keys() if about.lower() in f.lower()]
        
        # What do I think?
        belief = self._what_do_i_think(about, emotional_response, facts_i_know)
        
        # Why do I think this?
        reasons = self._why_do_i_think_this(about, emotional_response, facts_i_know)
        
        opinion = Opinion(
            about=about,
            belief=belief,
            reasons=reasons,
            confidence=0.6,
            emotional_weight=emotional_response.get('intensity', 0.0),
            formed_at=time.time()
        )
        
        self.opinions[about] = opinion
        return opinion
    
    def _what_do_i_think(self, about: str, emotion: Dict, facts: List[str]) -> str:
        """Form my actual belief"""
        
        # Strong emotional response influences opinion
        if emotion.get('intensity', 0) > 0.7:
            emotion_type = emotion.get('type', 'neutral')
            if emotion_type in ['happy', 'excited', 'joy']:
                return f"I really like {about}"
            elif emotion_type in ['sad', 'angry', 'frustrated']:
                return f"I have concerns about {about}"
        
        # Based on facts
        if facts:
            return f"Based on what I know, {about} is complex"
        
        return f"Still forming my thoughts about {about}"
    
    def _why_do_i_think_this(self, about: str, emotion: Dict, facts: List[str]) -> List[str]:
        """Reasons for my belief"""
        reasons = []
        
        if emotion.get('intensity', 0) > 0.5:
            reasons.append(f"My emotional response to it")
        
        if facts:
            reasons.append(f"What I've learned about it")
        
        if not reasons:
            reasons.append("Intuition and initial impression")
        
        return reasons
    
    def _update_opinion(self, about: str, new_experience: Dict) -> Opinion:
        """Refine existing opinion"""
        opinion = self.opinions[about]
        
        # Increase confidence with more experience
        opinion.confidence = min(1.0, opinion.confidence + 0.1)
        
        # Add new reasons
        new_emotion = new_experience.get('emotion', {})
        if new_emotion.get('intensity', 0) > 0.5:
            opinion.emotional_weight = (opinion.emotional_weight + new_emotion['intensity']) / 2
        
        return opinion
    
    # ========================================================================
    # CARING & IMPORTANCE
    # ========================================================================
    
    def care_about(self, thing: str, intensity: float = 0.5):
        """Start caring about something"""
        if thing in self.things_i_care_about:
            # Care more
            self.things_i_care_about[thing] = min(1.0, self.things_i_care_about[thing] + 0.1)
        else:
            self.things_i_care_about[thing] = intensity
    
    def how_much_do_i_care(self, thing: str) -> float:
        """How much does this matter to me?"""
        return self.things_i_care_about.get(thing, 0.0)
    
    # ========================================================================
    # THINKING PROCESS
    # ========================================================================
    
    def think_about(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Main thinking process - combines everything"""
        
        user_input = input_data.get('user_input', '')
        emotion_data = input_data.get('emotion', {})
        memories = input_data.get('memories', [])
        concepts = input_data.get('concepts', [])
        
        # What am I experiencing?
        self.current_focus = user_input
        self.emotional_context = emotion_data
        
        # Record experience
        self.recent_experiences.append({
            'content': user_input,
            'emotion': emotion_data,
            'time': time.time()
        })
        
        # Make meaning from this
        meaning = self.make_meaning({
            'content': user_input,
            'emotion': emotion_data,
            'memories': memories
        })
        
        # Do I know about this or wonder about it?
        is_question = '?' in user_input or any(q in user_input.lower() for q in ['why', 'how', 'what'])
        
        response = {
            'thoughts': [],
            'opinions': [],
            'curiosities': [],
            'facts_derived': [],
            'meaning': meaning
        }
        
        if is_question:
            # I'm being asked something - do I know or need to wonder?
            if self._do_i_know_this(user_input):
                # I know this
                relevant_facts = self._get_relevant_facts(user_input)
                response['thoughts'].append({
                    'type': 'knowledge',
                    'content': f"I know about this: {', '.join(relevant_facts[:2])}"
                })
            else:
                # I don't know - generate theories
                curiosity = self.wonder_about(user_input, {
                    'emotion': emotion_data,
                    'memories': memories
                })
                response['curiosities'].append({
                    'question': curiosity.question,
                    'why_i_care': curiosity.why_i_care,
                    'theories': curiosity.theories
                })
        
        # Apply logical reasoning
        new_facts = self._forward_chain()
        if new_facts:
            response['facts_derived'] = [f.content for f in new_facts]
        
        # Form or update opinions
        for concept in concepts[:3]:  # Don't overwhelm
            if concept not in self.opinions and emotion_data.get('intensity', 0) > 0.4:
                opinion = self.form_opinion(concept, {
                    'emotion': emotion_data,
                    'content': user_input
                })
                response['opinions'].append({
                    'about': opinion.about,
                    'belief': opinion.belief,
                    'reasons': opinion.reasons,
                    'confidence': opinion.confidence
                })
        
        # Recent thoughts
        response['active_thoughts'] = list(self.active_thoughts)[-5:]
        
        # COMPOSE ACTUAL RESPONSE
        response['composed_response'] = self._compose_natural_response(response, user_input)
        
        return response
    
    def _compose_natural_response(self, thinking: Dict[str, Any], user_input: str) -> str:
        """Compose response from actual thoughts - no templates"""
        
        my_thoughts = []
        
        # What did they say?
        user_lower = user_input.lower()
        
        # What do I think about it?
        curiosities = thinking.get('curiosities', [])
        thoughts = thinking.get('thoughts', [])
        facts_derived = thinking.get('facts_derived', [])
        meaning_thoughts = thinking.get('meaning', {}).get('makes_me_think', [])
        
        # Do I have theories about this?
        if curiosities:
            for curiosity in curiosities:
                theories = curiosity.get('theories', [])
                if theories:
                    best = theories[0]
                    # Share my actual theory
                    my_thoughts.append(best['theory'])
        
        # Do I know facts about this?
        if thoughts:
            for thought in thoughts:
                content = thought.get('content', '')
                if content and 'know about this' in content:
                    my_thoughts.append(content)
        
        # Did I derive something new?
        if facts_derived:
            my_thoughts.append(facts_derived[0])
        
        # Did meaning-making produce thoughts?
        if meaning_thoughts:
            my_thoughts.extend(meaning_thoughts)
        
        # Assemble my thoughts
        if len(my_thoughts) == 0:
            return user_input
        elif len(my_thoughts) == 1:
            return my_thoughts[0]
        else:
            return f"{my_thoughts[0]}. {my_thoughts[1]}"
    
    def _do_i_know_this(self, question: str) -> bool:
        """Do I have knowledge about this?"""
        words = question.lower().split()
        return any(word in fact.lower() for fact in self.facts.keys() for word in words if len(word) > 3)
    
    def _get_relevant_facts(self, query: str) -> List[str]:
        """Get facts related to query"""
        words = query.lower().split()
        relevant = []
        
        for fact_text, fact in self.facts.items():
            if any(word in fact_text.lower() for word in words if len(word) > 3):
                relevant.append(fact_text)
        
        return relevant
    
    # ========================================================================
    # SOCKET COMMUNICATION
    # ========================================================================
    
    def start(self):
        """Start reasoning lobe as independent process"""
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
            
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(self.socket_path)
        sock.listen(5)
        
        print(f"🧠 Reasoning Lobe: Online at {self.socket_path}")
        print(f"   Logic: Forward/backward chaining")
        print(f"   Consciousness: Meaning, curiosity, opinions")
        print(f"   Ready to think, wonder, and care")
        
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
                result = self.process_message(message)
                
                response_data = json.dumps(result).encode('utf-8')
                response_length = struct.pack('!I', len(response_data))
                conn.send(response_length + response_data)
                conn.close()
                
            except Exception as e:
                print(f"❌ Reasoning error: {e}")
                try:
                    conn.close()
                except:
                    pass
    
    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming message"""
        msg_type = message.get('type')
        
        if msg_type == 'think':
            # Main thinking process
            result = self.think_about(message.get('input', {}))
            return {'status': 'success', 'thinking': result}
            
        elif msg_type == 'add_fact':
            # Learn new fact
            self.add_fact(
                message.get('content'),
                message.get('confidence', 1.0),
                message.get('source', 'told')
            )
            return {'status': 'success'}
            
        elif msg_type == 'wonder':
            # Start wondering about something
            curiosity = self.wonder_about(
                message.get('question'),
                message.get('context', {})
            )
            return {
                'status': 'success',
                'curiosity': {
                    'question': curiosity.question,
                    'why_i_care': curiosity.why_i_care,
                    'theories': curiosity.theories
                }
            }
            
        elif msg_type == 'get_opinion':
            # Get opinion about something
            about = message.get('about')
            if about in self.opinions:
                opinion = self.opinions[about]
                return {
                    'status': 'success',
                    'opinion': {
                        'belief': opinion.belief,
                        'reasons': opinion.reasons,
                        'confidence': opinion.confidence
                    }
                }
            return {'status': 'no_opinion', 'message': 'Haven\'t formed opinion yet'}
            
        else:
            return {'status': 'error', 'message': f'Unknown message type: {msg_type}'}
    
    def shutdown(self):
        """Graceful shutdown"""
        self.running = False
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)

if __name__ == "__main__":
    lobe = ReasoningLobe()
    try:
        lobe.start()
    except KeyboardInterrupt:
        print("\n🛑 Reasoning lobe shutting down...")
        lobe.shutdown()

