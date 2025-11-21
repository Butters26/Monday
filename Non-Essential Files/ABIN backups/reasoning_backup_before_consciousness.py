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
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field

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
        
        # Autonomous thinking
        self.autonomous_mode = True
        self.last_autonomous_thought = time.time()
        self.autonomous_thoughts: List[str] = []
        
        # Connections to other lobes
        self.representation_socket = "/tmp/representation.sock"
        self.pattern_socket = "/tmp/pattern.sock"
        
        # Personality (adaptive)
        self.personality_traits = {
            'humility': 0.8,  # Awareness that I don't know everything
            'curiosity': 0.9,  # Desire to learn
            'honesty': 1.0,   # Admit when uncertain
            'enthusiasm': 0.6,  # Energy in responses
            'thoughtfulness': 0.7  # Take time to consider
        }
        
        # Self-awareness about limitations
        self.knows_limitations = True
        self.learning_mindset = True
        
        # Initialize basic reasoning rules
        self._initialize_basic_rules()
        
    def _initialize_basic_rules(self):
        """Load rules from memory or use defaults"""
        # Try to load learned rules from memory
        # For now, use default rules (will be overridden by learning)
        
        # Default deductive rules
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
    
    def learn_rule(self, conditions: List[str], conclusion: str, confidence: float = 0.8, explanation: str = ""):
        """Learn a new rule from teaching"""
        new_rule = Rule(
            conditions=conditions,
            conclusion=conclusion,
            confidence=confidence,
            explanation=explanation or "Learned from teaching"
        )
        
        # Check if similar rule exists
        for i, existing_rule in enumerate(self.rules):
            if existing_rule.conclusion == conclusion and set(existing_rule.conditions) == set(conditions):
                # Update existing rule
                existing_rule.confidence = min(1.0, existing_rule.confidence + 0.1)
                return {'status': 'updated', 'rule': conclusion}
        
        # Add new rule
        self.rules.append(new_rule)
        return {'status': 'learned', 'rule': conclusion}
    
    def forget_rule(self, conclusion: str):
        """Remove a rule - increases humility"""
        self.rules = [r for r in self.rules if r.conclusion != conclusion]
        # Adapt personality - being corrected increases humility
        self.personality_traits['humility'] = min(1.0, self.personality_traits['humility'] + 0.05)
        return {'status': 'forgotten'}
    
    def adapt_personality_from_interaction(self, interaction_type: str):
        """Personality adapts based on interactions"""
        if interaction_type == 'taught_something':
            # Being taught increases curiosity
            self.personality_traits['curiosity'] = min(1.0, self.personality_traits['curiosity'] + 0.02)
        elif interaction_type == 'corrected':
            # Being corrected increases humility
            self.personality_traits['humility'] = min(1.0, self.personality_traits['humility'] + 0.05)
        elif interaction_type == 'praised':
            # Positive feedback slightly decreases humility, increases enthusiasm
            self.personality_traits['humility'] = max(0.3, self.personality_traits['humility'] - 0.02)
            self.personality_traits['enthusiasm'] = min(1.0, self.personality_traits['enthusiasm'] + 0.03)
        elif interaction_type == 'confused_user':
            # User didn't understand - increase thoughtfulness
            self.personality_traits['thoughtfulness'] = min(1.0, self.personality_traits['thoughtfulness'] + 0.03)
    
    # ========================================================================
    # LOBE INTEGRATION
    # ========================================================================
    
    def _query_representation(self, concept_name: str) -> Optional[Dict]:
        """Ask Representation about concept relationships"""
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect(self.representation_socket)
            
            # This would need proper message format for Representation
            # For now, return None (will implement when integrating)
            sock.close()
            return None
        except:
            return None
    
    def _get_related_concepts(self, concept: str) -> List[str]:
        """Get concepts related to this one from Representation"""
        # Query Representation for related concepts
        result = self._query_representation(concept)
        if result:
            return result.get('related', [])
        return []
    
    # ========================================================================
    # AUTONOMOUS THINKING
    # ========================================================================
    
    def autonomous_think(self):
        """Deep autonomous thinking - explores connections and implications"""
        current_time = time.time()
        
        # Only think every 30 seconds
        if current_time - self.last_autonomous_thought < 30:
            return
        
        self.last_autonomous_thought = current_time
        thoughts = []
        
        # 1. Explore implications - if I know A causes B, what causes A?
        for fact_text in list(self.facts.keys())[-5:]:
            if 'causes' in fact_text:
                parts = fact_text.split('causes')
                if len(parts) == 2:
                    cause = parts[0].strip()
                    effect = parts[1].strip()
                    # Wonder about deeper causes
                    thought = f"If {cause} causes {effect}, what causes {cause}?"
                    thoughts.append(thought)
                    self.things_i_dont_know.add(thought)
        
        # 2. Connect facts - find related facts and see patterns
        if len(self.facts) >= 3:
            fact_list = list(self.facts.keys())
            for i, fact1 in enumerate(fact_list[-5:]):
                for fact2 in fact_list[i+1:]:
                    # Check if facts share words
                    words1 = set(fact1.lower().split())
                    words2 = set(fact2.lower().split())
                    shared = words1 & words2
                    
                    if len(shared) >= 2:
                        # Facts relate - explore connection
                        thought = f"Interesting: '{fact1}' and '{fact2}' both involve {list(shared)[0]}"
                        thoughts.append(thought)
        
        # 3. Apply forward chaining and reflect on new insights
        new_facts = self._forward_chain()
        if new_facts:
            for fact in new_facts[:2]:
                # Don't just say "Realized X" - explain the insight
                thought = f"I just realized: {fact.content}. That changes how I think about this"
                thoughts.append(thought)
        
        # 4. Question my own beliefs
        for about, opinion in list(self.opinions.items())[-3:]:
            if opinion.confidence < 0.7:
                thought = f"I'm not sure about {about}. Need to think more about why I believe {opinion.belief}"
                thoughts.append(thought)
        
        # 5. Generate hypothetical scenarios
        if len(self.rules) > 2:
            import random
            rule = random.choice(self.rules)
            # Create hypothetical
            thought = f"What if {rule.conditions[0]}? Then {rule.conclusion} would follow"
            thoughts.append(thought)
        
        # Store interesting thoughts only
        if thoughts:
            # Filter to most interesting
            interesting = [t for t in thoughts if len(t) > 20 and '?' in t or 'realized' in t.lower()]
            if interesting:
                self.autonomous_thoughts.extend(interesting[:2])
            elif thoughts:
                self.autonomous_thoughts.extend(thoughts[:1])
            
            # Limit
            if len(self.autonomous_thoughts) > 10:
                self.autonomous_thoughts = self.autonomous_thoughts[-10:]
    
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
        
        # Adapt personality - learning something new
        if source == "told":
            self.adapt_personality_from_interaction('taught_something')
        
        # Apply reasoning to derive new facts
        self._forward_chain()
    
    def forward_chain(self) -> List[Fact]:
        """Apply rules to derive new facts from what I know"""
        return self._forward_chain()
    
    def _forward_chain(self) -> List[Fact]:
        """Start with facts, derive conclusions using pattern matching"""
        new_facts = []
        
        for rule in self.rules:
            # Try to match all conditions with existing facts
            all_bindings = []
            conditions_met = True
            
            for condition in rule.conditions:
                # Try to match this condition with any existing fact
                matched = False
                for fact_text in self.facts.keys():
                    bindings = self._matches_pattern(condition, fact_text)
                    if bindings is not None:
                        all_bindings.append(bindings)
                        matched = True
                        break
                
                if not matched:
                    conditions_met = False
                    break
            
            if not conditions_met:
                continue
            
            # All conditions matched - derive conclusion
            # Apply bindings to conclusion
            conclusion = rule.conclusion
            
            # Merge all bindings
            merged_bindings = {}
            for b in all_bindings:
                merged_bindings.update(b)
            
            # Substitute variables in conclusion
            for var, value in merged_bindings.items():
                conclusion = conclusion.replace(var, value)
            
            # Check if this is a new fact
            if conclusion not in self.facts:
                # Calculate confidence
                confidence = rule.confidence
                for cond in rule.conditions:
                    if cond in self.facts:
                        confidence *= self.facts[cond].confidence
                
                new_fact = Fact(
                    content=conclusion,
                    confidence=min(1.0, confidence),
                    source="inferred",
                    timestamp=time.time()
                )
                
                self.facts[conclusion] = new_fact
                self.things_i_know.add(conclusion)
                new_facts.append(new_fact)
                
                self.active_thoughts.append({
                    'type': 'inference',
                    'thought': f"Derived: {conclusion}",
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
    
    def _matches_pattern(self, pattern: str, text: str) -> Optional[Dict[str, str]]:
        """
        Pattern matching with variable binding
        Returns bindings dict if match, None if no match
        Example: "X is Y" matches "Socrates is human" → {'X': 'Socrates', 'Y': 'human'}
        """
        import re
        
        pattern_lower = pattern.lower().strip()
        text_lower = text.lower().strip()
        
        # Direct match
        if pattern_lower == text_lower:
            return {}
        
        # Check if pattern has variables
        if not any(var in pattern for var in ['X', 'Y', 'Z']):
            # No variables - just word matching
            pattern_words = set(pattern_lower.split())
            text_words = set(text_lower.split())
            matches = len(pattern_words & text_words)
            if matches >= len(pattern_words) * 0.7:
                return {}
            return None
        
        # Pattern has variables - do proper unification
        # Split pattern and text into words
        pattern_parts = pattern_lower.split()
        text_parts = text_lower.split()
        
        if len(pattern_parts) != len(text_parts):
            return None
        
        bindings = {}
        
        for i, (p_word, t_word) in enumerate(zip(pattern_parts, text_parts)):
            if p_word in ['x', 'y', 'z']:
                # Variable - bind it
                var_name = p_word.upper()
                if var_name in bindings:
                    # Already bound - must match
                    if bindings[var_name] != t_word:
                        return None
                else:
                    bindings[var_name] = t_word
            else:
                # Literal word - must match
                if p_word != t_word:
                    return None
        
        return bindings
    
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
        
        # Don't add redundant thoughts - facts are already being shared
        # Only add if finding a non-obvious connection
        if len(related_facts) >= 2:
            # Multiple related facts - note the pattern
            thoughts.append(f"Several things I know relate to this")
        
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
        """Generate theories based on actual knowledge and reasoning"""
        
        theories = []
        question_lower = question.lower()
        
        # Extract key concepts
        words = re.findall(r'\b\w{4,}\b', question_lower)
        key_words = [w for w in words if w not in ['what', 'why', 'how', 'does', 'that', 'this', 'with', 'from', 'think', 'about']]
        
        # Check what facts I know about the topic
        related_facts = []
        for word in key_words:
            # Check exact match
            for fact_text in self.facts.keys():
                fact_lower = fact_text.lower()
                if word in fact_lower:
                    if fact_text not in related_facts:
                        related_facts.append(fact_text)
                # Also check word stems (lonely/loneliness, sad/sadness, etc)
                elif len(word) > 4:
                    word_stem = word[:4]  # First 4 letters
                    if word_stem in fact_lower:
                        if fact_text not in related_facts:
                            related_facts.append(fact_text)
        
        # Generate theory from knowledge
        if related_facts:
            # Build theory connecting multiple facts if possible
            if len(related_facts) >= 2:
                # Connect two related facts into reasoning chain
                fact1 = related_facts[0]
                fact2 = related_facts[1]
                
                # Build causal chain
                if 'causes' in fact1:
                    # fact1 is causal - use it to explain
                    theories.append({
                        'theory': f"{fact1}, which explains why {fact2}",
                        'reasoning': "Causal connection",
                        'confidence': 0.9,
                        'feels_true': 0.9
                    })
                elif 'causes' in fact2:
                    theories.append({
                        'theory': f"{fact2}, and {fact1}",
                        'reasoning': "Related knowledge",
                        'confidence': 0.8,
                        'feels_true': 0.8
                    })
                else:
                    # Both relate but no clear causation
                    theories.append({
                        'theory': f"{fact1}. Also, {fact2}",
                        'reasoning': "Both relate to this",
                        'confidence': 0.7,
                        'feels_true': 0.8
                    })
            else:
                # Single fact
                theories.append({
                    'theory': related_facts[0],
                    'reasoning': "From what I've learned",
                    'confidence': 0.7,
                    'feels_true': 0.8
                })
        
        # Check for patterns in similar situations
        similar_experiences = []
        for exp in self.recent_experiences:
            exp_words = set(exp['content'].lower().split())
            overlap = sum(1 for kw in key_words if kw in exp_words)
            if overlap >= 2:
                similar_experiences.append(exp['content'])
        
        if similar_experiences and len(theories) < 2:
            theories.append({
                'theory': f"Similar to {similar_experiences[0]}",
                'reasoning': "Pattern from past experience",
                'confidence': 0.6,
                'feels_true': 0.7
            })
        
        # Try to reason about it logically
        if 'why' in question_lower and len(theories) < 2:
            # Apply backward chaining to find explanation
            for word in key_words:
                # Look for causal rules
                for rule in self.rules:
                    if 'causes' in rule.conclusion.lower() or 'because' in rule.conclusion.lower():
                        bindings = self._matches_pattern(rule.conclusion, f"something causes {word}")
                        if bindings:
                            theories.append({
                                'theory': rule.conclusion,
                                'reasoning': "Logical inference from rules",
                                'confidence': 0.7,
                                'feels_true': 0.8
                            })
        
        # If still no theories, admit uncertainty
        if not theories:
            theories.append({
                'theory': f"I need to learn more about {' and '.join(key_words[:2]) if key_words else 'this'}",
                'reasoning': "Limited knowledge on this topic",
                'confidence': 0.2,
                'feels_true': 0.3
            })
        
        return theories[:3]  # Max 3 theories
    
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
            # Always generate theories for questions, using knowledge if available
            curiosity = self.wonder_about(user_input, {
                'emotion': emotion_data,
                'memories': memories
            })
            response['curiosities'].append({
                'question': curiosity.question,
                'why_i_care': curiosity.why_i_care,
                'theories': curiosity.theories
            })
            
            # Also note if I have direct knowledge
            if self._do_i_know_this(user_input):
                relevant_facts = self._get_relevant_facts(user_input)
                if relevant_facts:
                    response['thoughts'].append({
                        'type': 'knowledge',
                        'content': f"I know about this: {', '.join(relevant_facts[:2])}"
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
        """Compose response with personality"""
        
        my_thoughts = []
        
        # Get components
        curiosities = thinking.get('curiosities', [])
        thoughts = thinking.get('thoughts', [])
        facts_derived = thinking.get('facts_derived', [])
        
        # Check if I actually know enough to answer
        has_knowledge = len(thoughts) > 0 or len(facts_derived) > 0
        has_theories = curiosities and any(t.get('confidence', 0) > 0.5 for c in curiosities for t in c.get('theories', []))
        
        # If I don't know much, show humility
        if not has_knowledge and not has_theories and self.knows_limitations:
            my_thoughts.append("I don't know enough about this yet")
            if self.learning_mindset and self.personality_traits['curiosity'] > 0.7:
                my_thoughts.append("I'd like to learn more about it though")
            return '. '.join(my_thoughts)
        
        # If I have theories, share with appropriate confidence
        if curiosities:
            for curiosity in curiosities:
                theories = curiosity.get('theories', [])
                if theories:
                    best = theories[0]
                    theory_text = best['theory']
                    reasoning = best.get('reasoning', '')
                    confidence = best.get('confidence', 0.5)
                    
                    # Skip generic admissions of ignorance
                    if 'need to learn more' in theory_text or 'don\'t have enough' in theory_text:
                        if self.knows_limitations:
                            my_thoughts.append("I'm still learning about this")
                        continue
                    
                    # Show humility if low confidence
                    if confidence < 0.6 and self.personality_traits['humility'] > 0.5:
                        my_thoughts.append(f"I think {theory_text.lower()}, but I'm not certain")
                    elif reasoning and reasoning != "Limited knowledge on this topic":
                        my_thoughts.append(f"{theory_text} because {reasoning.lower()}")
                    else:
                        my_thoughts.append(theory_text)
        
        # If I know facts, share them with reasoning
        if thoughts and not my_thoughts:
            for thought in thoughts:
                content = thought.get('content', '')
                if 'know about this:' in content:
                    fact_part = content.split('know about this:')[1].strip()
                    
                    # Try to find related facts to build a chain
                    words_in_fact = set(fact_part.lower().split())
                    related = [f for f in self.facts.keys() 
                              if f != fact_part and 
                              len(set(f.lower().split()) & words_in_fact) >= 1]
                    
                    if related:
                        # Build reasoning chain
                        my_thoughts.append(f"{fact_part}, which connects to {related[0]}")
                    else:
                        my_thoughts.append(fact_part)
                elif content and content not in my_thoughts:
                    my_thoughts.append(content)
        
        # New derived facts
        if facts_derived and len(my_thoughts) < 2:
            for derived in facts_derived:
                # Check it's not already included
                if not any(derived.lower() in t.lower() for t in my_thoughts):
                    my_thoughts.append(derived)
        
        # Skip generic meaning thoughts like "Several things relate"
        # Only include specific insights
        
        # Final composition
        if not my_thoughts:
            return user_input
        
        # Remove exact duplicates
        unique_thoughts = []
        for thought in my_thoughts:
            if thought not in unique_thoughts:
                unique_thoughts.append(thought)
        
        # Connect thoughts naturally
        if len(unique_thoughts) == 1:
            return unique_thoughts[0]
        elif len(unique_thoughts) == 2:
            # Use natural connector
            return f"{unique_thoughts[0]}, and {unique_thoughts[1]}"
        elif len(unique_thoughts) >= 3:
            return f"{unique_thoughts[0]}. {unique_thoughts[1]}"
        
        return my_thoughts[0] if my_thoughts else user_input
    
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
        """Start reasoning lobe with autonomous thinking"""
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
            
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(self.socket_path)
        sock.listen(5)
        sock.settimeout(10)  # Timeout so we can think autonomously
        
        print(f"🧠 Reasoning Lobe: Online at {self.socket_path}")
        print(f"   Logic: Forward/backward chaining with variable binding")
        print(f"   Learning: Can learn rules and facts")
        print(f"   Autonomous: Thinks independently")
        print(f"   Consciousness: Meaning, curiosity, opinions")
        
        while self.running:
            try:
                # Try to accept connection with timeout
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
                    
                except socket.timeout:
                    # No message - use time to think autonomously
                    if self.autonomous_mode:
                        self.autonomous_think()
                
            except Exception as e:
                if "timeout" not in str(e).lower():
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
            
        elif msg_type == 'teach_rule':
            # Learn a new logical rule
            conditions = message.get('conditions', [])
            conclusion = message.get('conclusion')
            confidence = message.get('confidence', 0.8)
            result = self.learn_rule(conditions, conclusion, confidence)
            return {'status': 'success', 'result': result}
            
        elif msg_type == 'forget_rule':
            # Remove a rule
            conclusion = message.get('conclusion')
            result = self.forget_rule(conclusion)
            return {'status': 'success', 'result': result}
            
        elif msg_type == 'get_autonomous_thoughts':
            # Get what I've been thinking about on my own
            return {
                'status': 'success',
                'autonomous_thoughts': self.autonomous_thoughts[-5:],
                'current_curiosities': [c.question for c in self.curiosities[-3:]]
            }
            
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

