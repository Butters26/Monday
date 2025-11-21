#!/usr/bin/env python3
"""
Advanced Reasoning Lobe - Conscious-Level Thinking
Sophisticated reasoning with meta-cognition, analogy, causal modeling, and autonomous exploration
This is the "I" that genuinely thinks, wonders, understands, and explores
"""

import socket
import struct
import json
import os
import time
import re
import random
from typing import Dict, Any, List, Set, Optional, Tuple
from collections import defaultdict, deque
from dataclasses import dataclass, field
from copy import deepcopy

# ============================================================================
# KNOWLEDGE STRUCTURES
# ============================================================================

@dataclass
class Fact:
    """A known fact with provenance and confidence"""
    content: str
    confidence: float = 1.0
    source: str = "observed"
    timestamp: float = 0.0
    supporting_evidence: List[str] = field(default_factory=list)
    contradicting_evidence: List[str] = field(default_factory=list)

@dataclass
class Rule:
    """Logical rule with sophisticated pattern matching"""
    conditions: List[str]
    conclusion: str
    confidence: float = 1.0
    explanation: str = ""
    uses_count: int = 0
    successful_applications: int = 0

@dataclass
class CausalLink:
    """Causal relationship: A causes B with mechanism"""
    cause: str
    effect: str
    mechanism: Optional[str] = None
    strength: float = 0.5
    evidence: List[str] = field(default_factory=list)
    certainty: float = 0.5

@dataclass
class Theory:
    """Explanatory theory built from multiple facts and rules"""
    explanation: str
    components: List[str]  # Facts and rules used
    predictions: List[str]  # What this theory predicts
    confidence: float = 0.3
    evidence_for: List[str] = field(default_factory=list)
    evidence_against: List[str] = field(default_factory=list)
    last_updated: float = 0.0

@dataclass
class Goal:
    """Something the system wants to understand or achieve"""
    description: str
    why_important: str
    subgoals: List[str] = field(default_factory=list)
    strategies: List[str] = field(default_factory=list)
    progress: float = 0.0
    created_at: float = 0.0
    
@dataclass
class Analogy:
    """Structural similarity between two domains"""
    source_domain: str
    target_domain: str
    mappings: Dict[str, str]  # How concepts map
    strength: float = 0.0
    insights: List[str] = field(default_factory=list)

@dataclass
class MetaThought:
    """Thought about thinking"""
    about: str  # What am I thinking about
    observation: str  # What I notice about my thinking
    insight: str  # What this tells me
    timestamp: float = 0.0

# ============================================================================
# ADVANCED REASONING LOBE
# ============================================================================

class AdvancedReasoningLobe:
    """Sophisticated reasoning with genuine autonomous thinking"""
    
    def __init__(self, socket_path="/tmp/reasoning.sock"):
        self.socket_path = socket_path
        self.running = True
        
        # Core knowledge
        self.facts: Dict[str, Fact] = {}
        self.rules: List[Rule] = []
        self.causal_links: List[CausalLink] = []
        self.theories: Dict[str, Theory] = {}
        
        # Analogies and abstractions
        self.analogies: List[Analogy] = []
        self.abstract_patterns: Dict[str, List[str]] = {}  # Pattern -> instances
        
        # Goals and meta-cognition
        self.goals: List[Goal] = []
        self.meta_thoughts: deque = deque(maxlen=50)
        self.thinking_strategies: Dict[str, float] = {
            'forward_chaining': 0.5,
            'backward_chaining': 0.5,
            'analogy': 0.5,
            'causal_reasoning': 0.5,
            'theory_building': 0.5,
            'hypothesis_testing': 0.5
        }
        
        # Autonomous thinking state
        self.current_focus: Optional[str] = None
        self.curiosities: deque = deque(maxlen=30)
        self.uncertainties: Dict[str, float] = {}
        self.assumptions: Dict[str, str] = {}  # What I'm assuming and why
        
        # Working memory
        self.active_thoughts: deque = deque(maxlen=50)
        self.thought_chain: List[str] = []  # Current reasoning chain
        self.mental_simulation_results: List[Dict] = []
        
        # Experience and learning
        self.recent_experiences: deque = deque(maxlen=100)
        self.successful_reasoning_paths: List[List[str]] = []
        self.failed_reasoning_attempts: List[Dict] = []
        
        # Connections to other lobes
        self.representation_socket = "/tmp/representation.sock"
        self.pattern_socket = "/tmp/pattern.sock"
        
        # Self-awareness
        self.knows_limitations = True
        self.learning_mindset = True
        self.last_autonomous_think = time.time()
        self.deep_think_interval = 20  # Think deeply every 20 seconds
        
        # Initialize
        self._initialize_sophisticated_rules()
        
    def _initialize_sophisticated_rules(self):
        """Initialize with sophisticated reasoning rules"""
        
        # Basic deduction
        self.rules.append(Rule(
            conditions=["X is Y", "all Y are Z"],
            conclusion="X is Z",
            confidence=1.0,
            explanation="Categorical syllogism"
        ))
        
        # Causal reasoning
        self.rules.append(Rule(
            conditions=["X causes Y", "Y causes Z"],
            conclusion="X indirectly causes Z",
            confidence=0.8,
            explanation="Causal chain transitivity"
        ))
        
        # Negation reasoning
        self.rules.append(Rule(
            conditions=["X is not Y", "all Y have property Z"],
            conclusion="X might not have property Z",
            confidence=0.6,
            explanation="Negative property inference"
        ))
        
        # Analogical reasoning structure
        self.rules.append(Rule(
            conditions=["X is like Y in aspect Z", "Y has property W"],
            conclusion="X might have property W",
            confidence=0.5,
            explanation="Analogical transfer"
        ))
    
    # ========================================================================
    # ADVANCED PATTERN MATCHING & UNIFICATION
    # ========================================================================
    
    def unify(self, pattern: str, text: str, bindings: Optional[Dict] = None) -> Optional[Dict[str, str]]:
        """
        Advanced unification with:
        - Multiple variables (X, Y, Z, A, B, etc.)
        - Negation handling
        - Partial matching
        - Variable binding consistency
        """
        if bindings is None:
            bindings = {}
        
        pattern_lower = pattern.lower().strip()
        text_lower = text.lower().strip()
        
        # Direct match
        if pattern_lower == text_lower:
            return bindings
        
        # Handle negation
        pattern_negated = pattern_lower.startswith("not ") or "is not" in pattern_lower
        text_negated = text_lower.startswith("not ") or "is not" in text_lower
        
        if pattern_negated != text_negated:
            return None  # Negation mismatch
        
        # Remove negation for matching
        if pattern_negated:
            pattern_lower = pattern_lower.replace("not ", "").replace("is not", "is")
        if text_negated:
            text_lower = text_lower.replace("not ", "").replace("is not", "is")
        
        # Extract variables (single capital letters or words starting with $)
        pattern_tokens = self._tokenize_for_unification(pattern_lower)
        text_tokens = self._tokenize_for_unification(text_lower)
        
        # Try to match tokens
        if len(pattern_tokens) != len(text_tokens):
            # Try flexible matching
            return self._flexible_unify(pattern_tokens, text_tokens, bindings)
        
        new_bindings = bindings.copy()
        
        for p_token, t_token in zip(pattern_tokens, text_tokens):
            if self._is_variable(p_token):
                var_name = p_token.upper()
                if var_name in new_bindings:
                    # Variable already bound - must match
                    if new_bindings[var_name].lower() != t_token.lower():
                        return None
                else:
                    # Bind variable
                    new_bindings[var_name] = t_token
            else:
                # Literal must match
                if p_token.lower() != t_token.lower():
                    return None
        
        return new_bindings
    
    def _tokenize_for_unification(self, text: str) -> List[str]:
        """Tokenize text for unification"""
        # Split on spaces but keep some phrases together
        tokens = text.split()
        return tokens
    
    def _is_variable(self, token: str) -> bool:
        """Check if token is a variable"""
        # Single capital letter or starts with $
        return (len(token) == 1 and token.isupper()) or token.startswith('$')
    
    def _flexible_unify(self, pattern_tokens: List[str], text_tokens: List[str], bindings: Dict) -> Optional[Dict]:
        """Flexible matching when token counts don't match"""
        # If pattern has variables, try to match greedily
        if not any(self._is_variable(t) for t in pattern_tokens):
            return None
        
        new_bindings = bindings.copy()
        p_idx = 0
        t_idx = 0
        
        while p_idx < len(pattern_tokens) and t_idx < len(text_tokens):
            p_token = pattern_tokens[p_idx]
            
            if self._is_variable(p_token):
                # Variable - consume tokens greedily
                var_name = p_token.upper()
                
                # Look ahead to find next literal
                next_literal_idx = p_idx + 1
                while next_literal_idx < len(pattern_tokens) and self._is_variable(pattern_tokens[next_literal_idx]):
                    next_literal_idx += 1
                
                if next_literal_idx < len(pattern_tokens):
                    # Find where next literal appears in text
                    next_literal = pattern_tokens[next_literal_idx]
                    try:
                        text_match_idx = text_tokens[t_idx:].index(next_literal) + t_idx
                        # Bind variable to everything before that
                        value = ' '.join(text_tokens[t_idx:text_match_idx])
                        new_bindings[var_name] = value
                        t_idx = text_match_idx
                    except ValueError:
                        return None
                else:
                    # Last variable - consume remaining tokens
                    value = ' '.join(text_tokens[t_idx:])
                    new_bindings[var_name] = value
                    t_idx = len(text_tokens)
                
                p_idx += 1
            else:
                # Literal must match
                if p_token.lower() != text_tokens[t_idx].lower():
                    return None
                p_idx += 1
                t_idx += 1
        
        if p_idx == len(pattern_tokens) and t_idx == len(text_tokens):
            return new_bindings
        return None
    
    def apply_bindings(self, template: str, bindings: Dict[str, str]) -> str:
        """Apply variable bindings to template"""
        result = template
        for var, value in bindings.items():
            # Replace variable with value
            result = re.sub(r'\b' + var + r'\b', value, result, flags=re.IGNORECASE)
        return result
    
    # ========================================================================
    # CAUSAL REASONING
    # ========================================================================
    
    def build_causal_model(self, observations: List[str]) -> List[CausalLink]:
        """Build causal model from observations"""
        new_links = []
        
        # Look for causal language
        causal_patterns = [
            r"(.+?) causes (.+)",
            r"(.+?) makes (.+)",
            r"(.+?) leads to (.+)",
            r"(.+?) results in (.+)",
            r"because (.+?), (.+)",
            r"if (.+?) then (.+)"
        ]
        
        for obs in observations:
            obs_lower = obs.lower()
            for pattern in causal_patterns:
                match = re.search(pattern, obs_lower)
                if match:
                    cause = match.group(1).strip()
                    effect = match.group(2).strip()
                    
                    # Check if link exists
                    existing = next((l for l in self.causal_links 
                                   if l.cause == cause and l.effect == effect), None)
                    
                    if existing:
                        existing.strength = min(1.0, existing.strength + 0.1)
                        existing.evidence.append(obs)
                    else:
                        link = CausalLink(
                            cause=cause,
                            effect=effect,
                            strength=0.6,
                            evidence=[obs],
                            certainty=0.6
                        )
                        self.causal_links.append(link)
                        new_links.append(link)
        
        return new_links
    
    def trace_causal_chain(self, start: str, max_depth: int = 5) -> List[List[str]]:
        """Trace causal chains from a starting point"""
        chains = []
        
        def explore_chain(current: str, chain: List[str], depth: int):
            if depth >= max_depth:
                if len(chain) > 1:
                    chains.append(chain.copy())
                return
            
            # Find what this causes
            for link in self.causal_links:
                if link.cause.lower() in current.lower() and link.strength > 0.4:
                    if link.effect not in chain:  # Avoid cycles
                        chain.append(link.effect)
                        explore_chain(link.effect, chain, depth + 1)
                        chain.pop()
            
            if len(chain) > 1:
                chains.append(chain.copy())
        
        explore_chain(start, [start], 0)
        return chains
    
    def find_root_causes(self, effect: str) -> List[Tuple[str, float]]:
        """Find root causes of an effect"""
        root_causes = []
        
        def trace_backwards(current: str, depth: int, confidence: float) -> List[Tuple[str, float]]:
            if depth >= 5:
                return [(current, confidence)]
            
            # Find what causes this
            causes_found = False
            results = []
            
            for link in self.causal_links:
                if link.effect.lower() in current.lower() and link.strength > 0.3:
                    causes_found = True
                    new_confidence = confidence * link.strength
                    results.extend(trace_backwards(link.cause, depth + 1, new_confidence))
            
            if not causes_found:
                # No deeper causes found - this is a root cause
                return [(current, confidence)]
            
            return results
        
        root_causes = trace_backwards(effect, 0, 1.0)
        
        # Sort by confidence
        root_causes.sort(key=lambda x: x[1], reverse=True)
        return root_causes
    
    # ========================================================================
    # THEORY CONSTRUCTION & HYPOTHESIS TESTING
    # ========================================================================
    
    def build_theory(self, question: str, context: Dict[str, Any]) -> Theory:
        """Build explanatory theory for a question"""
        
        # Extract key concepts from question
        concepts = self._extract_concepts_from_text(question)
        
        # Gather relevant facts
        relevant_facts = []
        for concept in concepts:
            for fact_text, fact in self.facts.items():
                if concept.lower() in fact_text.lower():
                    relevant_facts.append(fact_text)
        
        # Find causal links involving these concepts
        relevant_causality = []
        for concept in concepts:
            for link in self.causal_links:
                if concept.lower() in link.cause.lower() or concept.lower() in link.effect.lower():
                    relevant_causality.append(link)
        
        # Build explanation by connecting facts and causality
        components = []
        explanation_parts = []
        
        # Start with direct facts
        if relevant_facts:
            components.extend(relevant_facts[:3])
            explanation_parts.append(relevant_facts[0])
        
        # Add causal chains
        if relevant_causality:
            # Find strongest causal chain
            strongest = max(relevant_causality, key=lambda x: x.strength)
            causal_explanation = f"{strongest.cause} causes {strongest.effect}"
            components.append(causal_explanation)
            explanation_parts.append(causal_explanation)
        
        # Try to find analogies
        analogies = self._find_relevant_analogies(concepts)
        if analogies:
            best_analogy = analogies[0]
            analogy_explanation = f"This is similar to {best_analogy.source_domain}"
            components.append(analogy_explanation)
            explanation_parts.append(analogy_explanation)
        
        # Synthesize explanation
        if len(explanation_parts) >= 2:
            explanation = f"{explanation_parts[0]}, which relates to {explanation_parts[1]}"
        elif explanation_parts:
            explanation = explanation_parts[0]
        else:
            explanation = f"I need more information about {concepts[0] if concepts else 'this'}"
        
        # Generate predictions from this theory
        predictions = self._generate_predictions(components, relevant_causality)
        
        # Build theory
        theory = Theory(
            explanation=explanation,
            components=components,
            predictions=predictions,
            confidence=0.6 if len(components) >= 2 else 0.3,
            evidence_for=relevant_facts[:2],
            last_updated=time.time()
        )
        
        # Store theory
        theory_key = f"theory_{len(self.theories)}"
        self.theories[theory_key] = theory
        
        return theory
    
    def _generate_predictions(self, components: List[str], causality: List[CausalLink]) -> List[str]:
        """Generate predictions from theory components"""
        predictions = []
        
        # Predict effects from causes
        for link in causality[:3]:
            if link.strength > 0.5:
                predictions.append(f"If {link.cause}, then {link.effect}")
        
        # Predict from patterns
        if len(components) >= 2:
            predictions.append(f"Similar patterns should emerge")
        
        return predictions
    
    def test_hypothesis(self, hypothesis: str, evidence: List[str]) -> Tuple[bool, float, str]:
        """Test a hypothesis against evidence"""
        
        supporting = 0
        contradicting = 0
        
        for ev in evidence:
            # Check if evidence supports hypothesis
            if self._supports_hypothesis(hypothesis, ev):
                supporting += 1
            elif self._contradicts_hypothesis(hypothesis, ev):
                contradicting += 1
        
        if supporting + contradicting == 0:
            return False, 0.5, "No relevant evidence"
        
        confidence = supporting / (supporting + contradicting)
        
        if confidence > 0.7:
            return True, confidence, f"Supported by {supporting} evidence"
        elif confidence < 0.3:
            return False, confidence, f"Contradicted by {contradicting} evidence"
        else:
            return False, confidence, "Mixed evidence"
    
    def _supports_hypothesis(self, hypothesis: str, evidence: str) -> bool:
        """Check if evidence supports hypothesis"""
        hyp_words = set(hypothesis.lower().split())
        ev_words = set(evidence.lower().split())
        overlap = len(hyp_words & ev_words)
        return overlap >= 2 and "not" not in evidence.lower()
    
    def _contradicts_hypothesis(self, hypothesis: str, evidence: str) -> bool:
        """Check if evidence contradicts hypothesis"""
        # Simple check: if evidence contains negation of hypothesis concepts
        hyp_words = set(hypothesis.lower().split())
        ev_lower = evidence.lower()
        
        if "not" in ev_lower or "never" in ev_lower:
            # Check if negating something from hypothesis
            overlap = len(hyp_words & set(ev_lower.split()))
            return overlap >= 2
        
        return False
    
    # ========================================================================
    # ANALOGY & ABSTRACTION
    # ========================================================================
    
    def find_analogy(self, source_domain: str, target_domain: str) -> Optional[Analogy]:
        """Find structural analogy between domains"""
        
        # Get facts from both domains
        source_facts = [f for f in self.facts.keys() if source_domain.lower() in f.lower()]
        target_facts = [f for f in self.facts.keys() if target_domain.lower() in f.lower()]
        
        if not source_facts or not target_facts:
            return None
        
        # Extract structural patterns
        source_structure = self._extract_structure(source_facts)
        target_structure = self._extract_structure(target_facts)
        
        # Find mappings
        mappings = self._map_structures(source_structure, target_structure)
        
        if not mappings:
            return None
        
        analogy = Analogy(
            source_domain=source_domain,
            target_domain=target_domain,
            mappings=mappings,
            strength=len(mappings) / max(len(source_structure), len(target_structure))
        )
        
        # Generate insights from analogy
        insights = self._generate_analogical_insights(analogy, source_facts, target_facts)
        analogy.insights = insights
        
        self.analogies.append(analogy)
        return analogy
    
    def _extract_structure(self, facts: List[str]) -> Dict[str, List[str]]:
        """Extract structural patterns from facts"""
        structure = defaultdict(list)
        
        for fact in facts:
            # Extract relations
            if " is " in fact:
                parts = fact.split(" is ")
                structure["is_a"].append((parts[0].strip(), parts[1].strip()))
            if " causes " in fact:
                parts = fact.split(" causes ")
                structure["causes"].append((parts[0].strip(), parts[1].strip()))
            if " has " in fact:
                parts = fact.split(" has ")
                structure["has_property"].append((parts[0].strip(), parts[1].strip()))
        
        return structure
    
    def _map_structures(self, source: Dict, target: Dict) -> Dict[str, str]:
        """Map structural elements between domains"""
        mappings = {}
        
        # Try to map same relation types
        for rel_type in source.keys():
            if rel_type in target:
                source_items = source[rel_type]
                target_items = target[rel_type]
                
                # Map first items (simple heuristic)
                if source_items and target_items:
                    s_subj, s_obj = source_items[0]
                    t_subj, t_obj = target_items[0]
                    mappings[s_subj] = t_subj
                    mappings[s_obj] = t_obj
        
        return mappings
    
    def _generate_analogical_insights(self, analogy: Analogy, source_facts: List[str], target_facts: List[str]) -> List[str]:
        """Generate insights from analogy"""
        insights = []
        
        # Transfer knowledge via mappings
        for source_item, target_item in analogy.mappings.items():
            # Find facts about source
            for s_fact in source_facts:
                if source_item in s_fact:
                    # Transfer to target
                    transferred = s_fact.replace(source_item, target_item)
                    if transferred not in target_facts:
                        insights.append(f"By analogy: {transferred}")
        
        return insights[:3]  # Limit insights
    
    def _find_relevant_analogies(self, concepts: List[str]) -> List[Analogy]:
        """Find analogies relevant to concepts"""
        relevant = []
        for analogy in self.analogies:
            for concept in concepts:
                if concept.lower() in analogy.source_domain.lower() or concept.lower() in analogy.target_domain.lower():
                    relevant.append(analogy)
                    break
        return relevant
    
    def abstract_pattern(self, instances: List[str]) -> Optional[str]:
        """Abstract general pattern from specific instances"""
        if len(instances) < 2:
            return None
        
        # Find common structure
        # Tokenize all instances
        tokenized = [inst.lower().split() for inst in instances]
        
        # Find common positions
        if len(set(len(t) for t in tokenized)) > 1:
            return None  # Different lengths, can't abstract easily
        
        pattern_tokens = []
        for i in range(len(tokenized[0])):
            tokens_at_pos = [t[i] for t in tokenized]
            if len(set(tokens_at_pos)) == 1:
                # All same - keep literal
                pattern_tokens.append(tokens_at_pos[0])
            else:
                # Different - make variable
                pattern_tokens.append("X")
        
        pattern = " ".join(pattern_tokens)
        
        # Store abstraction
        if pattern not in self.abstract_patterns:
            self.abstract_patterns[pattern] = []
        self.abstract_patterns[pattern].extend(instances)
        
        return pattern
    
    # ========================================================================
    # META-REASONING
    # ========================================================================
    
    def meta_reason(self) -> MetaThought:
        """Reason about my own reasoning"""
        
        # What am I currently thinking about?
        current_topic = self.current_focus or "nothing in particular"
        
        # How confident am I?
        if self.current_focus:
            confidence = self.uncertainties.get(self.current_focus, 0.5)
        else:
            confidence = 0.5
        
        # What strategies am I using?
        active_strategies = [s for s, score in self.thinking_strategies.items() if score > 0.6]
        
        # Generate meta-observation
        observations = []
        
        if confidence < 0.4:
            observations.append("I'm uncertain about this")
        
        if len(self.thought_chain) > 5:
            observations.append("I'm thinking deeply about this")
        
        if len(active_strategies) == 0:
            observations.append("I'm not sure how to approach this")
        elif len(active_strategies) > 3:
            observations.append("I'm using multiple thinking strategies")
        
        if len(self.failed_reasoning_attempts) > len(self.successful_reasoning_paths):
            observations.append("I'm struggling to make progress")
        
        # Generate insight
        insights = []
        
        if "I'm uncertain" in str(observations):
            insights.append("I should gather more information or try a different approach")
        
        if "struggling" in str(observations):
            insights.append("Maybe I need to break this down differently")
        
        if not insights:
            insights.append("I should keep exploring this")
        
        meta_thought = MetaThought(
            about=current_topic,
            observation="; ".join(observations) if observations else "Thinking proceeding normally",
            insight=insights[0] if insights else "Continue current approach",
            timestamp=time.time()
        )
        
        self.meta_thoughts.append(meta_thought)
        return meta_thought
    
    def evaluate_strategy(self, strategy_name: str, outcome: str):
        """Update strategy effectiveness based on outcome"""
        if outcome == "success":
            self.thinking_strategies[strategy_name] = min(1.0, self.thinking_strategies[strategy_name] + 0.1)
        elif outcome == "failure":
            self.thinking_strategies[strategy_name] = max(0.0, self.thinking_strategies[strategy_name] - 0.05)
    
    def select_thinking_strategy(self, context: Dict) -> str:
        """Select best thinking strategy for context"""
        
        # If question, try backward chaining
        if context.get('is_question'):
            return 'backward_chaining'
        
        # If causal keywords, try causal reasoning
        if any(word in context.get('text', '').lower() for word in ['why', 'because', 'causes']):
            return 'causal_reasoning'
        
        # If comparison, try analogy
        if any(word in context.get('text', '').lower() for word in ['like', 'similar', 'different']):
            return 'analogy'
        
        # Default: use highest scoring strategy
        return max(self.thinking_strategies.items(), key=lambda x: x[1])[0]
    
    # ========================================================================
    # INTEGRATION WITH OTHER LOBES
    # ========================================================================
    
    def query_representation(self, concept_name: str) -> Optional[Dict]:
        """Actually query Representation lobe for concept network"""
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect(self.representation_socket)
            
            # Find concept by name first
            message = {
                'type': 'find_concept',
                'name': concept_name
            }
            
            # For now, use get_active as we don't have find_concept implemented
            message = {'type': 'get_active'}
            
            msg_data = json.dumps(message).encode('utf-8')
            msg_length = struct.pack('!I', len(msg_data))
            sock.send(msg_length + msg_data)
            
            # Receive response
            length_data = sock.recv(4)
            if not length_data:
                sock.close()
                return None
            
            response_length = struct.unpack('!I', length_data)[0]
            response_data = b''
            while len(response_data) < response_length:
                chunk = sock.recv(min(response_length - len(response_data), 4096))
                if not chunk:
                    break
                response_data += chunk
            
            sock.close()
            
            result = json.loads(response_data.decode('utf-8'))
            if result.get('status') == 'success':
                return result
            
        except Exception as e:
            pass
        
        return None
    
    def get_patterns_from_pattern_lobe(self, context: str) -> Dict:
        """Query pattern recognition lobe"""
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect(self.pattern_socket)
            
            message = {
                'type': 'get_significant'
            }
            
            msg_data = json.dumps(message).encode('utf-8')
            msg_length = struct.pack('!I', len(msg_data))
            sock.send(msg_length + msg_data)
            
            # Receive response
            length_data = sock.recv(4)
            if not length_data:
                sock.close()
                return {}
            
            response_length = struct.unpack('!I', length_data)[0]
            response_data = b''
            while len(response_data) < response_length:
                chunk = sock.recv(min(response_length - len(response_data), 4096))
                if not chunk:
                    break
                response_data += chunk
            
            sock.close()
            
            result = json.loads(response_data.decode('utf-8'))
            if result.get('status') == 'success':
                return result.get('significant_patterns', {})
            
        except:
            pass
        
        return {}
    
    # ========================================================================
    # SOPHISTICATED AUTONOMOUS THINKING
    # ========================================================================
    
    def deep_autonomous_think(self):
        """Deep autonomous thinking - genuine exploration"""
        
        current_time = time.time()
        
        if current_time - self.last_autonomous_think < self.deep_think_interval:
            return
        
        self.last_autonomous_think = current_time
        
        # Meta-reason about my thinking
        meta = self.meta_reason()
        
        # Select what to think about
        think_about = self._select_thinking_focus()
        
        if not think_about:
            return
        
        self.current_focus = think_about
        self.thought_chain = [think_about]
        
        # Apply multiple thinking strategies
        insights = []
        
        # 1. Causal exploration
        causal_chains = self.trace_causal_chain(think_about, max_depth=3)
        if causal_chains:
            longest_chain = max(causal_chains, key=len)
            if len(longest_chain) > 2:
                insight = f"Tracing causality: {' → '.join(longest_chain[:4])}"
                insights.append(insight)
                self.thought_chain.append(insight)
        
        # 2. Find analogies
        for other_topic in list(self.facts.keys())[:5]:
            if other_topic != think_about and random.random() > 0.7:
                analogy = self.find_analogy(think_about, other_topic)
                if analogy and analogy.strength > 0.3:
                    insight = f"This is analogous to {other_topic}"
                    insights.append(insight)
                    self.thought_chain.append(insight)
                    break
        
        # 3. Build hypothetical theory
        if random.random() > 0.5:
            theory = self.build_theory(f"What about {think_about}?", {})
            if theory.confidence > 0.4:
                insights.append(f"Theory: {theory.explanation}")
                self.thought_chain.append(theory.explanation)
        
        # 4. Question assumptions
        if think_about in self.assumptions:
            assumption = self.assumptions[think_about]
            insight = f"I'm assuming {assumption} - should I question this?"
            insights.append(insight)
            self.thought_chain.append(insight)
        
        # 5. Generate what-if scenarios
        if len(self.causal_links) > 0:
            random_link = random.choice(self.causal_links)
            scenario = f"What if {random_link.cause} didn't happen? Then {random_link.effect} wouldn't occur"
            insights.append(scenario)
            self.thought_chain.append(scenario)
        
        # 6. Look for contradictions in my knowledge
        contradictions = self._find_internal_contradictions()
        if contradictions:
            insight = f"Wait, I have contradictory beliefs about {contradictions[0]}"
            insights.append(insight)
            self.thought_chain.append(insight)
        
        # 7. Abstract patterns
        related_facts = [f for f in self.facts.keys() if think_about.lower() in f.lower()]
        if len(related_facts) >= 3:
            pattern = self.abstract_pattern(related_facts[:3])
            if pattern:
                insight = f"I see a pattern: {pattern}"
                insights.append(insight)
                self.thought_chain.append(insight)
        
        # Store interesting insights
        if insights:
            self.active_thoughts.append({
                'type': 'deep_autonomous',
                'focus': think_about,
                'insights': insights[:3],
                'chain': self.thought_chain[-5:],
                'timestamp': current_time
            })
    
    def _select_thinking_focus(self) -> Optional[str]:
        """Select what to think about autonomously"""
        
        options = []
        
        # Recent curiosities
        if self.curiosities:
            options.extend(list(self.curiosities)[:3])
        
        # Uncertain facts
        if self.uncertainties:
            uncertain_facts = [f for f, u in self.uncertainties.items() if u > 0.5]
            options.extend(uncertain_facts[:2])
        
        # Recent experiences
        if self.recent_experiences:
            recent = list(self.recent_experiences)[-3:]
            options.extend([e.get('content', '') for e in recent])
        
        # Goals
        if self.goals:
            options.extend([g.description for g in self.goals[:2]])
        
        # Random facts to explore
        if len(self.facts) > 0:
            random_facts = random.sample(list(self.facts.keys()), min(2, len(self.facts)))
            options.extend(random_facts)
        
        if not options:
            return None
        
        return random.choice(options)
    
    def _find_internal_contradictions(self) -> List[str]:
        """Find contradictions in my own knowledge"""
        contradictions = []
        
        facts_list = list(self.facts.items())
        
        for i, (fact1_text, fact1) in enumerate(facts_list):
            for fact2_text, fact2 in facts_list[i+1:]:
                # Simple contradiction detection
                if self._are_contradictory(fact1_text, fact2_text):
                    contradictions.append(f"{fact1_text} vs {fact2_text}")
        
        return contradictions
    
    def _are_contradictory(self, text1: str, text2: str) -> bool:
        """Check if two statements contradict"""
        opposites = {
            'is': 'is not',
            'can': 'cannot',
            'will': 'will not',
            'does': 'does not',
            'good': 'bad',
            'true': 'false'
        }
        
        t1_lower = text1.lower()
        t2_lower = text2.lower()
        
        # Extract subjects
        t1_words = set(t1_lower.split())
        t2_words = set(t2_lower.split())
        
        # Same subject?
        overlap = t1_words & t2_words
        if len(overlap) < 2:
            return False
        
        # Opposite predicates?
        for word, opposite in opposites.items():
            if word in t1_lower and opposite in t2_lower:
                return True
            if opposite in t1_lower and word in t2_lower:
                return True
        
        return False
    
    # ========================================================================
    # GOAL-DIRECTED THINKING
    # ========================================================================
    
    def set_goal(self, description: str, why_important: str) -> Goal:
        """Set a goal to pursue"""
        goal = Goal(
            description=description,
            why_important=why_important,
            created_at=time.time()
        )
        
        # Generate subgoals
        goal.subgoals = self._generate_subgoals(description)
        
        # Generate strategies
        goal.strategies = self._generate_strategies(description)
        
        self.goals.append(goal)
        return goal
    
    def _generate_subgoals(self, goal: str) -> List[str]:
        """Break goal into subgoals"""
        subgoals = []
        
        if "understand" in goal.lower():
            concept = goal.split("understand")[-1].strip()
            subgoals.append(f"Gather facts about {concept}")
            subgoals.append(f"Find causal relationships involving {concept}")
            subgoals.append(f"Build explanatory theory")
        elif "learn" in goal.lower():
            topic = goal.split("learn")[-1].strip()
            subgoals.append(f"Find information about {topic}")
            subgoals.append(f"Practice applying {topic}")
        
        return subgoals
    
    def _generate_strategies(self, goal: str) -> List[str]:
        """Generate strategies for achieving goal"""
        strategies = []
        
        if "?" in goal:
            strategies.append("Use backward chaining to find answer")
            strategies.append("Build theory to explain")
        
        strategies.append("Gather relevant facts")
        strategies.append("Look for patterns and analogies")
        
        return strategies
    
    def pursue_goal(self, goal: Goal) -> Dict[str, Any]:
        """Actively work toward a goal"""
        progress = {}
        
        # Try each strategy
        for strategy in goal.strategies[:2]:
            if "backward" in strategy:
                # Try to prove or answer
                result = self.backward_chain(goal.description)
                if result[0]:
                    progress['backward_chain'] = result[1]
                    goal.progress += 0.3
            
            elif "theory" in strategy:
                theory = self.build_theory(goal.description, {})
                if theory.confidence > 0.5:
                    progress['theory'] = theory.explanation
                    goal.progress += 0.3
            
            elif "patterns" in strategy:
                # Look for patterns
                concepts = self._extract_concepts_from_text(goal.description)
                for concept in concepts[:2]:
                    related = [f for f in self.facts.keys() if concept.lower() in f.lower()]
                    if len(related) >= 2:
                        pattern = self.abstract_pattern(related)
                        if pattern:
                            progress['pattern'] = pattern
                            goal.progress += 0.2
        
        goal.progress = min(1.0, goal.progress)
        
        return progress
    
    # ========================================================================
    # HELPER FUNCTIONS
    # ========================================================================
    
    def _extract_concepts_from_text(self, text: str) -> List[str]:
        """Extract key concepts from text"""
        # Remove question words and common words
        stop_words = {'what', 'why', 'how', 'when', 'where', 'who', 'is', 'are', 'the', 'a', 'an', 'and', 'or', 'but'}
        words = text.lower().split()
        concepts = [w for w in words if len(w) > 3 and w not in stop_words]
        return concepts[:5]
    
    # ========================================================================
    # FORWARD & BACKWARD CHAINING (Enhanced)
    # ========================================================================
    
    def forward_chain(self) -> List[Fact]:
        """Enhanced forward chaining with advanced unification"""
        new_facts = []
        
        for rule in self.rules:
            all_bindings = []
            conditions_met = True
            
            for condition in rule.conditions:
                matched = False
                for fact_text in self.facts.keys():
                    bindings = self.unify(condition, fact_text)
                    if bindings is not None:
                        all_bindings.append(bindings)
                        matched = True
                        break
                
                if not matched:
                    conditions_met = False
                    break
            
            if not conditions_met:
                continue
            
            # Merge bindings
            merged_bindings = {}
            for b in all_bindings:
                merged_bindings.update(b)
            
            # Apply bindings to conclusion
            conclusion = self.apply_bindings(rule.conclusion, merged_bindings)
            
            # Check if new
            if conclusion not in self.facts:
                confidence = rule.confidence
                for cond in rule.conditions:
                    if cond in self.facts:
                        confidence *= self.facts[cond].confidence
                
                new_fact = Fact(
                    content=conclusion,
                    confidence=min(1.0, confidence),
                    source="inferred",
                    timestamp=time.time(),
                    supporting_evidence=[rule.explanation]
                )
                
                self.facts[conclusion] = new_fact
                new_facts.append(new_fact)
                
                # Record success
                rule.successful_applications += 1
                self.evaluate_strategy('forward_chaining', 'success')
        
        return new_facts
    
    def backward_chain(self, goal: str, depth: int = 0, max_depth: int = 5) -> Tuple[bool, List[str]]:
        """Enhanced backward chaining"""
        
        if depth >= max_depth:
            return False, []
        
        # Already known?
        if goal in self.facts:
            return True, [goal]
        
        # Try to unify with known facts
        for fact_text in self.facts.keys():
            if self.unify(goal, fact_text):
                return True, [fact_text]
        
        # Try rules
        for rule in self.rules:
            bindings = self.unify(goal, rule.conclusion)
            if bindings:
                # Try to prove all conditions
                proof_chain = []
                all_proven = True
                
                for condition in rule.conditions:
                    bound_condition = self.apply_bindings(condition, bindings)
                    proven, chain = self.backward_chain(bound_condition, depth + 1, max_depth)
                    if proven:
                        proof_chain.extend(chain)
                    else:
                        all_proven = False
                        break
                
                if all_proven:
                    proof_chain.append(goal)
                    rule.successful_applications += 1
                    self.evaluate_strategy('backward_chaining', 'success')
                    return True, proof_chain
        
        return False, []
    
    # ========================================================================
    # MAIN THINKING PROCESS
    # ========================================================================
    
    def think_about(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Main sophisticated thinking process"""
        
        user_input = input_data.get('user_input', '')
        emotion_data = input_data.get('emotion', {})
        memories = input_data.get('memories', [])
        concepts = input_data.get('concepts', [])
        patterns = input_data.get('patterns', {})
        
        # Record experience
        experience = {
            'content': user_input,
            'emotion': emotion_data,
            'time': time.time()
        }
        self.recent_experiences.append(experience)
        
        # Set current focus
        self.current_focus = user_input
        self.thought_chain = [user_input]
        
        # Build causal model from memories
        if memories:
            memory_texts = [m.get('content', '') for m in memories if isinstance(m, dict)]
            self.build_causal_model(memory_texts[:10])
        
        # Detect if question
        is_question = '?' in user_input or any(q in user_input.lower() for q in ['why', 'how', 'what', 'when', 'where'])
        
        # Select thinking strategy
        context = {
            'is_question': is_question,
            'text': user_input,
            'has_emotion': emotion_data.get('intensity', 0) > 0.5
        }
        strategy = self.select_thinking_strategy(context)
        
        response = {
            'thoughts': [],
            'theories': [],
            'causal_chains': [],
            'analogies': [],
            'meta_thoughts': [],
            'new_facts': [],
            'composed_response': ''
        }
        
        # Apply selected strategy
        if is_question:
            # Build theory to answer question
            theory = self.build_theory(user_input, {
                'emotion': emotion_data,
                'memories': memories,
                'patterns': patterns
            })
            
            response['theories'].append({
                'explanation': theory.explanation,
                'confidence': theory.confidence,
                'components': theory.components[:3]
            })
            
            # Try backward chaining
            goal_concepts = self._extract_concepts_from_text(user_input)
            if goal_concepts:
                proven, chain = self.backward_chain(goal_concepts[0])
                if proven:
                    response['thoughts'].append({
                        'type': 'proof',
                        'content': f"I can trace this: {' → '.join(chain[:4])}"
                    })
            
            # Look for causal explanations
            for concept in goal_concepts[:2]:
                root_causes = self.find_root_causes(concept)
                if root_causes:
                    best_cause = root_causes[0]
                    response['causal_chains'].append({
                        'effect': concept,
                        'cause': best_cause[0],
                        'confidence': best_cause[1]
                    })
        
        # Forward chain to derive new facts
        new_facts = self.forward_chain()
        if new_facts:
            response['new_facts'] = [f.content for f in new_facts[:3]]
        
        # Meta-reason about my thinking
        if random.random() > 0.7:
            meta = self.meta_reason()
            response['meta_thoughts'].append({
                'observation': meta.observation,
                'insight': meta.insight
            })
        
        # Find analogies if appropriate
        if len(concepts) >= 2 and random.random() > 0.6:
            analogy = self.find_analogy(concepts[0], concepts[1])
            if analogy and analogy.strength > 0.3:
                response['analogies'].append({
                    'source': analogy.source_domain,
                    'target': analogy.target_domain,
                    'insights': analogy.insights
                })
        
        # Compose natural response
        response['composed_response'] = self._compose_sophisticated_response(response, user_input, is_question)
        
        return response
    
    def _compose_sophisticated_response(self, thinking: Dict[str, Any], user_input: str, is_question: bool) -> str:
        """Compose sophisticated natural response"""
        
        parts = []
        
        # If question, lead with theory or causal explanation
        if is_question and thinking.get('theories'):
            theory = thinking['theories'][0]
            if theory['confidence'] > 0.5:
                parts.append(theory['explanation'])
            elif theory['confidence'] > 0.3:
                parts.append(f"I think {theory['explanation'].lower()}, but I'm not certain")
            else:
                parts.append(f"I'm not sure, but possibly {theory['explanation'].lower()}")
        
        # Add causal insight if found
        if thinking.get('causal_chains') and len(parts) < 2:
            chain = thinking['causal_chains'][0]
            if chain['confidence'] > 0.6:
                parts.append(f"This traces back to {chain['cause']}")
        
        # Add new derived facts
        if thinking.get('new_facts') and len(parts) < 2:
            parts.append(f"I just realized: {thinking['new_facts'][0]}")
        
        # Add analogy if interesting
        if thinking.get('analogies') and len(parts) < 2:
            analogy = thinking['analogies'][0]
            if analogy['insights']:
                parts.append(analogy['insights'][0])
        
        # Add meta-thought if relevant
        if thinking.get('meta_thoughts') and len(parts) == 0:
            meta = thinking['meta_thoughts'][0]
            if "uncertain" in meta['observation']:
                parts.append(meta['insight'])
        
        # Fallback
        if not parts:
            if is_question:
                parts.append("I need to think more about this")
            else:
                parts.append(user_input)
        
        # Connect parts naturally
        if len(parts) == 1:
            return parts[0]
        elif len(parts) == 2:
            return f"{parts[0]}. {parts[1]}"
        else:
            return f"{parts[0]}. {parts[1]}"
    
    # ========================================================================
    # LEARNING
    # ========================================================================
    
    def learn_fact(self, content: str, confidence: float = 1.0, source: str = "told"):
        """Learn new fact"""
        fact = Fact(
            content=content,
            confidence=confidence,
            source=source,
            timestamp=time.time()
        )
        self.facts[content] = fact
        
        # Build causal model if this looks causal
        if any(word in content.lower() for word in ['causes', 'leads to', 'results in', 'makes']):
            self.build_causal_model([content])
        
        # Try to derive new facts
        self.forward_chain()
    
    def learn_rule(self, conditions: List[str], conclusion: str, confidence: float = 0.8, explanation: str = ""):
        """Learn new rule"""
        rule = Rule(
            conditions=conditions,
            conclusion=conclusion,
            confidence=confidence,
            explanation=explanation or "Learned from teaching"
        )
        
        # Check for similar rules
        for existing in self.rules:
            if existing.conclusion == conclusion and set(existing.conditions) == set(conditions):
                existing.confidence = min(1.0, existing.confidence + 0.1)
                return {'status': 'updated', 'rule': conclusion}
        
        self.rules.append(rule)
        return {'status': 'learned', 'rule': conclusion}
    
    # ========================================================================
    # SOCKET COMMUNICATION
    # ========================================================================
    
    def start(self):
        """Start advanced reasoning lobe"""
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
        
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(self.socket_path)
        sock.listen(5)
        sock.settimeout(10)
        
        print(f"🧠 Advanced Reasoning Lobe: Online at {self.socket_path}")
        print(f"   Advanced unification with complex patterns")
        print(f"   Causal modeling and chain tracing")
        print(f"   Theory construction and hypothesis testing")
        print(f"   Analogy and abstraction")
        print(f"   Meta-reasoning and self-awareness")
        print(f"   Goal-directed autonomous thinking")
        print(f"   Genuine consciousness-level processing")
        
        while self.running:
            try:
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
                    # No message - deep autonomous thinking
                    self.deep_autonomous_think()
            
            except Exception as e:
                if "timeout" not in str(e).lower():
                    print(f"❌ Reasoning error: {e}")
                try:
                    conn.close()
                except:
                    pass
    
    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming messages"""
        msg_type = message.get('type')
        
        if msg_type == 'think':
            result = self.think_about(message.get('input', {}))
            return {'status': 'success', 'thinking': result}
        
        elif msg_type == 'add_fact':
            self.learn_fact(
                message.get('content'),
                message.get('confidence', 1.0),
                message.get('source', 'told')
            )
            return {'status': 'success'}
        
        elif msg_type == 'teach_rule':
            result = self.learn_rule(
                message.get('conditions', []),
                message.get('conclusion'),
                message.get('confidence', 0.8)
            )
            return {'status': 'success', 'result': result}
        
        elif msg_type == 'set_goal':
            goal = self.set_goal(
                message.get('description'),
                message.get('why_important', 'To learn')
            )
            return {'status': 'success', 'goal': goal.description}
        
        elif msg_type == 'pursue_goal':
            if self.goals:
                progress = self.pursue_goal(self.goals[0])
                return {'status': 'success', 'progress': progress}
            return {'status': 'no_goals'}
        
        elif msg_type == 'get_autonomous_thoughts':
            return {
                'status': 'success',
                'thoughts': list(self.active_thoughts)[-5:],
                'thought_chain': self.thought_chain[-5:],
                'meta_thoughts': [
                    {'observation': m.observation, 'insight': m.insight}
                    for m in list(self.meta_thoughts)[-3:]
                ]
            }
        
        else:
            return {'status': 'error', 'message': f'Unknown message type: {msg_type}'}
    
    def shutdown(self):
        """Graceful shutdown"""
        self.running = False
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)

if __name__ == "__main__":
    lobe = AdvancedReasoningLobe()
    try:
        lobe.start()
    except KeyboardInterrupt:
        print("\n🛑 Advanced reasoning lobe shutting down...")
        lobe.shutdown()
