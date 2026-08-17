#!/usr/bin/env python3
"""
Advanced Pattern Recognition Lobe
Detects human-like patterns including behavioral, pareidolia, meta-patterns
Like how humans see patterns everywhere - including patterns that aren't there
"""

import json
import os
import threading
import time
import random
import sys
from typing import Dict, Any, List, Tuple, Set, Optional
from collections import defaultdict, deque
from dataclasses import dataclass, field
from thalamus import get_thalamus

# ============================================================================
# PATTERN DATA STRUCTURES
# ============================================================================

@dataclass
class CoOccurrence:
    """Two things appearing together"""
    item_a: str
    item_b: str
    count: int = 0
    strength: float = 0.0
    last_seen: float = 0.0
    contexts: List[str] = field(default_factory=list)
    source: str = 'user'  # 'user' or 'self'

@dataclass
class Sequence:
    """Multi-step sequence A→B→C→D"""
    steps: List[str]
    count: int = 0
    confidence: float = 0.0
    last_seen: float = 0.0
    average_time_between_steps: float = 0.0
    source: str = 'user'  # 'user' or 'self'

@dataclass
class BehavioralPattern:
    """Complex behavioral pattern combining multiple signals"""
    name: str
    signals: Dict[str, Any]  # What signals make up this pattern
    occurrences: int = 0
    confidence: float = 0.0
    examples: List[Dict] = field(default_factory=list)
    last_seen: float = 0.0
    source: str = 'user'  # 'user' or 'self'

@dataclass
class SelfMystery:
    """An internal pattern Monday notices but cannot explain"""
    description: str
    signals: List[str] = field(default_factory=list)
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    occurrence_count: int = 1
    resolved: bool = False
    resolution: str = ''

@dataclass
class Contradiction:
    """Detected contradiction"""
    statement_a: str
    statement_b: str
    timestamp_a: float
    timestamp_b: float
    severity: float = 0.5

@dataclass
class MetaPattern:
    """Pattern about patterns"""
    description: str
    patterns_involved: List[str]
    meta_confidence: float = 0.0

@dataclass
class PareidoliaPattern:
    """Speculative pattern seen in weak signals"""
    description: str
    confidence: float = 0.0
    is_speculative: bool = True
    signals: List[str] = field(default_factory=list)

# ============================================================================
# ADVANCED PATTERN RECOGNITION LOBE
# ============================================================================

class AdvancedPatternRecognition:
    """Human-like pattern recognition - sees everything"""
    
    def __init__(self):
        self.running = True
        # Direct reference to Thalamus (NO SOCKETS)
        self.thalamus = get_thalamus()
        
        # Basic patterns
        self.co_occurrences: Dict[Tuple[str, str], CoOccurrence] = {}
        self.sequences: Dict[Tuple, Sequence] = {}
        
        # Advanced patterns
        self.behavioral_patterns: Dict[str, BehavioralPattern] = {}
        self.contradictions: List[Contradiction] = []
        self.meta_patterns: List[MetaPattern] = []
        self.pareidolia_patterns: List[PareidoliaPattern] = []
        
        # Recent history
        self.recent_items = deque(maxlen=50)
        self.recent_emotions = deque(maxlen=30)
        self.recent_topics = deque(maxlen=20)
        self.recent_word_choices = deque(maxlen=100)
        self.statement_history = deque(maxlen=100)
        
        # State tracking
        self.boredom_level = 0.0
        self.last_pattern_time = time.time()
        
        # Thresholds (dynamic based on boredom)
        self.base_co_occurrence_threshold = 3
        self.base_sequence_threshold = 2
        self.base_behavioral_threshold = 3
        
        # Decay
        self.decay_rate = 0.1
        self.last_decay = time.time()
        
        # Learned knowledge from Notus
        self.learned_opposites: Dict[str, List[str]] = {}
        self.learned_behavioral_patterns: Dict[str, Dict] = {}
        
        # Self-observation: mysteries and background polling
        self.self_mysteries: List[SelfMystery] = []
        self.self_observation_interval: float = 45.0  # seconds; overridden by config
        self._self_obs_lock = threading.Lock()
        self._last_self_alert_time: float = 0.0  # throttle broadcasts
        
        # Load learned knowledge from memory
        self._load_learned_knowledge()
        
        # Initialize default templates (can be overridden by learning)
        self._initialize_default_templates()
        
    def _load_learned_knowledge(self):
        """Load learned pattern definitions from Notus memory"""
        # Try to connect to Notus and load learned knowledge
        try:
            # Query Notus for learned opposites
            # Query Notus for learned behavioral patterns
            # For now, starts empty - will be populated when taught
            pass
        except Exception:
            # Notus not available yet, that's okay
            pass
    
    def _initialize_default_templates(self):
        """Initialize templates for detecting behavioral patterns"""
        # Lying detection template
        self.behavioral_patterns['lying'] = BehavioralPattern(
            name='lying',
            signals={
                'required': ['contradiction', 'topic_avoidance', 'emotion_mismatch'],
                'optional': ['hesitation', 'defensive_language']
            }
        )
        
        # Stress pattern
        self.behavioral_patterns['stress'] = BehavioralPattern(
            name='stress',
            signals={
                'required': ['negative_emotion', 'short_responses'],
                'optional': ['topic_switching', 'avoidance']
            }
        )
        
        # Excitement pattern
        self.behavioral_patterns['excitement'] = BehavioralPattern(
            name='excitement',
            signals={
                'required': ['positive_emotion', 'increased_verbosity'],
                'optional': ['repetition', 'emphasis']
            }
        )
    
    # ========================================================================
    # LEARNING & TEACHING
    # ========================================================================
    
    def teach_opposite_words(self, word: str, opposites: List[str]):
        """Learn that these words are opposites"""
        if word not in self.learned_opposites:
            self.learned_opposites[word] = []
        
        for opp in opposites:
            if opp not in self.learned_opposites[word]:
                self.learned_opposites[word].append(opp)
    
    def teach_behavioral_pattern(self, pattern_name: str, definition: Dict[str, Any]):
        """Learn a new behavioral pattern definition"""
        self.learned_behavioral_patterns[pattern_name] = definition
        
        # Create or update pattern
        if pattern_name not in self.behavioral_patterns:
            self.behavioral_patterns[pattern_name] = BehavioralPattern(
                name=pattern_name,
                signals=definition.get('signals', {})
            )
        else:
            # Update existing pattern
            self.behavioral_patterns[pattern_name].signals = definition.get('signals', {})
    
    def update_pattern_understanding(self, pattern_name: str, additional_signals: List[str]):
        """Add new signals to understanding of a pattern"""
        if pattern_name in self.behavioral_patterns:
            current_signals = self.behavioral_patterns[pattern_name].signals
            optional = current_signals.get('optional', [])
            optional.extend(additional_signals)
            current_signals['optional'] = list(set(optional))  # Remove duplicates
    
    # ========================================================================
    # BOREDOM & PAREIDOLIA
    # ========================================================================
    
    def update_boredom(self):
        """Update boredom level - increases when no patterns found"""
        current_time = time.time()
        time_since_pattern = current_time - self.last_pattern_time
        
        if time_since_pattern > 60:  # No patterns for a minute
            self.boredom_level = min(1.0, self.boredom_level + 0.1)
        else:
            self.boredom_level = max(0.0, self.boredom_level - 0.05)
        
        # When bored, lower thresholds (see patterns more easily)
        if self.boredom_level > 0.5:
            self._enable_pareidolia_mode()
    
    def _enable_pareidolia_mode(self):
        """When bored, start seeing patterns in weak signals"""
        # Look for speculative patterns in recent data
        if len(self.recent_items) < 3:
            return
        
        # Pick random recent items and create speculative connection
        sample = random.sample(list(self.recent_items), min(3, len(self.recent_items)))
        items = [item[0] for item in sample]
        
        # Create speculative pattern
        pattern = PareidoliaPattern(
            description=f"Maybe {items[0]} connects to {items[1]} somehow",
            confidence=0.2 + (self.boredom_level * 0.3),
            signals=items
        )
        
        self.pareidolia_patterns.append(pattern)
        
        # Limit pareidolia patterns
        if len(self.pareidolia_patterns) > 10:
            self.pareidolia_patterns = self.pareidolia_patterns[-10:]
    
    # ========================================================================
    # MULTI-STEP SEQUENCE DETECTION
    # ========================================================================
    
    def detect_multi_step_sequences(self):
        """Detect A→B→C→D sequences"""
        if len(self.recent_items) < 3:
            return
        
        # Look for sequences of 3-5 steps
        for seq_length in [3, 4, 5]:
            if len(self.recent_items) < seq_length:
                continue
            
            # Check recent items for sequences
            recent_list = list(self.recent_items)[-20:]
            
            for i in range(len(recent_list) - seq_length + 1):
                steps = [recent_list[i+j][0] for j in range(seq_length)]
                times = [recent_list[i+j][1] for j in range(seq_length)]
                
                # Check timing - steps should be reasonably close
                time_diffs = [times[j+1] - times[j] for j in range(len(times)-1)]
                avg_time = sum(time_diffs) / len(time_diffs) if time_diffs else 0
                
                if avg_time > 60:  # Too far apart
                    continue
                
                # Record or update sequence
                seq_key = tuple(steps)
                if seq_key in self.sequences:
                    seq = self.sequences[seq_key]
                    seq.count += 1
                    seq.last_seen = time.time()
                    seq.confidence = min(1.0, seq.count / 5.0)
                    seq.average_time_between_steps = avg_time
                else:
                    self.sequences[seq_key] = Sequence(
                        steps=steps,
                        count=1,
                        confidence=0.2,
                        last_seen=time.time(),
                        average_time_between_steps=avg_time
                    )
    
    # ========================================================================
    # BEHAVIORAL PATTERN DETECTION
    # ========================================================================
    
    def detect_behavioral_patterns(self, current_data: Dict[str, Any]):
        """Detect complex behavioral patterns"""
        current_time = time.time()
        
        # Query Notus for learned behavioral patterns
        try:
            notus_patterns = self._query_lobe('notus', {'type': 'get_behavioral_patterns'})
            if notus_patterns and notus_patterns.get('status') == 'success':
                learned = notus_patterns.get('patterns', [])
                for pattern_data in learned:
                    if isinstance(pattern_data, dict) and pattern_data.get('name'):
                        self.behavioral_patterns[pattern_data['name']] = BehavioralPattern(
                            name=pattern_data['name'],
                            signals=pattern_data.get('signals', {}),
                            occurrences=pattern_data.get('occurrences', 0),
                            last_seen=pattern_data.get('last_seen', current_time),
                            confidence=pattern_data.get('confidence', 0.5)
                        )
        except Exception:
            pass
        
        # Extract current signals
        signals_present = self._extract_behavioral_signals(current_data)
        
        if not signals_present:
            return
        
        # Check each behavioral pattern template
        for pattern_name, pattern in self.behavioral_patterns.items():
            # Check if required signals are present
            required = pattern.signals.get('required', [])
            optional = pattern.signals.get('optional', [])
            
            required_count = sum(1 for sig in required if sig in signals_present)
            optional_count = sum(1 for sig in optional if sig in signals_present)
            
            # Need at least 2 required signals OR 1 required + 2 optional
            if required_count >= 2 or (required_count >= 1 and optional_count >= 2):
                # Pattern detected
                pattern.occurrences += 1
                pattern.last_seen = current_time
                pattern.confidence = min(1.0, pattern.occurrences / 3.0)
                pattern.examples.append({
                    'signals': signals_present,
                    'timestamp': current_time,
                    'data': current_data.get('statement', '')
                })
                
                # Limit examples
                if len(pattern.examples) > 10:
                    pattern.examples = pattern.examples[-10:]
                
                self.last_pattern_time = current_time
    
    def _extract_behavioral_signals(self, data: Dict[str, Any]) -> List[str]:
        """Extract behavioral signals from current data"""
        signals = []
        
        statement = data.get('statement', '')
        emotion = data.get('emotions', data.get('emotion', {}))  # Handle both keys
        words = data.get('words', [])
        topics = data.get('topics', [])
        
        # Check for contradictions
        if statement and self._has_recent_contradiction(statement):
            signals.append('contradiction')
        
        # Check emotion mismatch
        if emotion and words and self._emotion_word_mismatch(emotion, words):
            signals.append('emotion_mismatch')
        
        # Check topic avoidance
        if topics and self._topic_avoidance_detected(topics):
            signals.append('topic_avoidance')
        
        # Check hesitation
        if words and self._hesitation_detected(words):
            signals.append('hesitation')
        
        # Emotion signals
        emotion_type = emotion.get('type', 'neutral') if isinstance(emotion, dict) else 'neutral'
        emotion_intensity = emotion.get('intensity', 0) if isinstance(emotion, dict) else 0
        
        if emotion_intensity > 0.6:
            if emotion_type in ['happy', 'excited', 'joy']:
                signals.append('positive_emotion')
            elif emotion_type in ['sad', 'angry', 'worried', 'scared']:
                signals.append('negative_emotion')
        
        # Response length signals
        if len(words) > 30:
            signals.append('increased_verbosity')
        elif len(words) < 5 and len(words) > 0:
            signals.append('short_responses')
        
        # Defensive language
        defensive_words = ['actually', 'honestly', 'trust me', 'believe me', 'i swear']
        if any(d in ' '.join(words).lower() for d in defensive_words):
            signals.append('defensive_language')
        
        return signals
    
    def _has_recent_contradiction(self, statement: str) -> bool:
        """Check if statement contradicts recent statements"""
        if not statement:
            return False
        
        # Query Notus for all past contradictions
        try:
            notus_contradict = self._query_lobe('notus', {'type': 'get_contradictions', 'statement': statement})
            if notus_contradict and notus_contradict.get('status') == 'success':
                past_contradictions = notus_contradict.get('contradictions', [])
                if past_contradictions:
                    return True
        except Exception:
            pass
        
        if len(self.statement_history) == 0:
            return False
        
        # Combine learned opposites with defaults
        opposites = {
            'love': ['hate', 'dislike'],
            'hate': ['love', 'like'],
            'like': ['hate', 'dislike'],
            'yes': ['no'],
            'no': ['yes'],
            'good': ['bad', 'terrible'],
            'bad': ['good', 'great'],
            'happy': ['sad', 'unhappy'],
            'sad': ['happy'],
            'agree': ['disagree'],
            'want': ['dont want', "don't want"],
        }
        
        # Add learned opposites (overrides defaults)
        for word, opposite_list in self.learned_opposites.items():
            if word in opposites:
                opposites[word].extend(opposite_list)
            else:
                opposites[word] = opposite_list
        
        statement_lower = statement.lower()
        statement_words = set(statement_lower.split())
        
        for past_statement, past_time in list(self.statement_history)[-10:]:
            past_lower = past_statement.lower()
            past_words = set(past_lower.split())
            
            # Check for opposite words about same subject
            for word in statement_words:
                if word in opposites:
                    for opposite in opposites[word]:
                        if opposite in past_lower or opposite in past_words:
                            # Found contradiction
                            self.contradictions.append(Contradiction(
                                statement_a=past_statement,
                                statement_b=statement,
                                timestamp_a=past_time,
                                timestamp_b=time.time(),
                                severity=0.8
                            ))
                            return True
            
            # Also check reverse
            for word in past_words:
                if word in opposites:
                    for opposite in opposites[word]:
                        if opposite in statement_lower or opposite in statement_words:
                            self.contradictions.append(Contradiction(
                                statement_a=past_statement,
                                statement_b=statement,
                                timestamp_a=past_time,
                                timestamp_b=time.time(),
                                severity=0.8
                            ))
                            return True
                    
        return False
    
    def _emotion_word_mismatch(self, emotion: Dict, words: List[str]) -> bool:
        """Check if emotion doesn't match word choice"""
        if not emotion or not words:
            return False
        
        emotion_type = emotion.get('type', 'neutral')
        words_lower = [w.lower() for w in words]
        
        # Positive emotion but negative words
        positive_emotions = ['happy', 'excited', 'joy']
        negative_words = ['hate', 'terrible', 'awful', 'bad', 'sad', 'angry']
        
        if emotion_type in positive_emotions and any(w in words_lower for w in negative_words):
            return True
        
        # Negative emotion but positive words
        negative_emotions = ['sad', 'angry', 'worried']
        positive_words = ['great', 'wonderful', 'amazing', 'love', 'happy']
        
        if emotion_type in negative_emotions and any(w in words_lower for w in positive_words):
            return True
        
        return False
    
    def _topic_avoidance_detected(self, current_topics: List[str]) -> bool:
        """Check if topics are being avoided"""
        if len(self.recent_topics) < 5:
            return False
        
        # Check if same topic keeps coming up but responses are short
        topic_counts = defaultdict(int)
        for topic_list, timestamp in list(self.recent_topics)[-10:]:
            for topic in topic_list:
                topic_counts[topic] += 1
        
        # If a topic comes up 3+ times recently, might be avoidance
        for topic, count in topic_counts.items():
            if count >= 3 and topic not in current_topics:
                return True
        
        return False
    
    def _hesitation_detected(self, words: List[str]) -> bool:
        """Detect hesitation in word choice"""
        hesitation_words = ['um', 'uh', 'well', 'maybe', 'perhaps', 'kind of', 'sort of', 'i guess']
        words_lower = [w.lower() for w in words]
        
        hesitation_count = sum(1 for h in hesitation_words if h in ' '.join(words_lower))
        return hesitation_count >= 2
    
    # ========================================================================
    # META-PATTERN DETECTION
    # ========================================================================
    
    def detect_meta_patterns(self):
        """Detect patterns about patterns"""
        # Query Notus for historical meta-patterns
        try:
            notus_meta = self._query_lobe('notus', {'type': 'get_meta_patterns'})
            if notus_meta and notus_meta.get('status') == 'success':
                historical = notus_meta.get('meta_patterns', [])
                # Use historical meta-patterns to inform detection
        except Exception:
            pass
        # Pattern: Certain sequences lead to certain behavioral patterns
        for seq_key, sequence in self.sequences.items():
            if sequence.confidence < 0.5:
                continue
            
            # Check what behavioral patterns occur after this sequence
            for behavior_name, behavior in self.behavioral_patterns.items():
                if behavior.occurrences > 0:
                    # Create meta-pattern
                    meta = MetaPattern(
                        description=f"Sequence {' → '.join(sequence.steps[:3])} often precedes {behavior_name}",
                        patterns_involved=[str(seq_key), behavior_name],
                        meta_confidence=0.6
                    )
                    
                    # Check if already exists
                    if not any(m.description == meta.description for m in self.meta_patterns):
                        self.meta_patterns.append(meta)
        
        # Limit meta-patterns
        if len(self.meta_patterns) > 20:
            self.meta_patterns = self.meta_patterns[-20:]
    
    # ========================================================================
    # MAIN OBSERVATION FUNCTION
    # ========================================================================
    
    def observe(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # Query Notus for past observations to compare
        try:
            notus_past = self._query_lobe('notus', {'type': 'get_past_observations', 'data': data})
            if notus_past and notus_past.get('status') == 'success':
                past_obs = notus_past.get('observations', [])
                # Compare current observation to past ones
        except Exception:
            pass
        """
        Observe data and detect all types of patterns
        data should include: items, emotions, words, statement, topics
        """
        current_time = time.time()
        
        items = data.get('items', [])
        emotions = data.get('emotions', {})
        words = data.get('words', [])
        statement = data.get('statement', '')
        topics = data.get('topics', [])
        
        patterns_found = {
            'co_occurrences': [],
            'sequences': [],
            'behavioral': [],
            'contradictions': [],
            'meta_patterns': [],
            'pareidolia': [],
            'new_patterns': False
        }
        
        # Update history
        for item in items:
            self.recent_items.append((item, current_time))
        
        if emotions:
            self.recent_emotions.append((emotions, current_time))
        
        if topics:
            self.recent_topics.append((topics, current_time))
        
        if words:
            self.recent_word_choices.extend([(w, current_time) for w in words])
        
        if statement:
            self.statement_history.append((statement, current_time))
        
        # Detect basic co-occurrences
        for i, item_a in enumerate(items):
            for item_b in items[i+1:]:
                self._record_co_occurrence(item_a, item_b, current_time, statement)
        
        # Detect multi-step sequences
        self.detect_multi_step_sequences()
        
        # Detect behavioral patterns
        self.detect_behavioral_patterns(data)
        
        # Detect meta-patterns
        self.detect_meta_patterns()
        
        # Update boredom and check for pareidolia
        self.update_boredom()
        
        # Decay old patterns
        if current_time - self.last_decay > 60:
            self._decay_patterns()
            self.last_decay = current_time
        
        # Collect detected patterns
        threshold = self.base_co_occurrence_threshold * (1 - self.boredom_level * 0.5)
        
        for pair, pattern in self.co_occurrences.items():
            if pattern.count >= threshold:
                patterns_found['co_occurrences'].append({
                    'items': list(pair),
                    'count': pattern.count,
                    'strength': pattern.strength
                })
        
        for seq_key, sequence in self.sequences.items():
            if sequence.confidence >= 0.4:
                patterns_found['sequences'].append({
                    'steps': sequence.steps,
                    'confidence': sequence.confidence,
                    'count': sequence.count
                })
        
        for name, behavior in self.behavioral_patterns.items():
            if behavior.confidence >= 0.5:
                patterns_found['behavioral'].append({
                    'name': name,
                    'confidence': behavior.confidence,
                    'occurrences': behavior.occurrences
                })
        
        # Recent contradictions
        patterns_found['contradictions'] = [
            {
                'statement_a': c.statement_a,
                'statement_b': c.statement_b,
                'severity': c.severity
            }
            for c in self.contradictions[-5:]
        ]
        
        # Meta-patterns
        patterns_found['meta_patterns'] = [
            {
                'description': m.description,
                'confidence': m.meta_confidence
            }
            for m in self.meta_patterns[-5:]
        ]
        
        # Pareidolia patterns (speculative)
        patterns_found['pareidolia'] = [
            {
                'description': p.description,
                'confidence': p.confidence,
                'speculative': p.is_speculative
            }
            for p in self.pareidolia_patterns[-3:]
        ]
        
        # Check if new patterns emerged
        if any([
            patterns_found['behavioral'],
            patterns_found['meta_patterns'],
            len(patterns_found['sequences']) > len(self.sequences) * 0.8
        ]):
            patterns_found['new_patterns'] = True
            self.last_pattern_time = current_time
        
        return patterns_found
    
    def _record_co_occurrence(self, item_a: str, item_b: str, timestamp: float, context: str = ""):
        """Record co-occurrence with context"""
        pair = tuple(sorted([item_a, item_b]))
        
        if pair in self.co_occurrences:
            pattern = self.co_occurrences[pair]
            pattern.count += 1
            pattern.last_seen = timestamp
            pattern.strength = min(1.0, pattern.count / 10.0)
            if context and len(pattern.contexts) < 5:
                pattern.contexts.append(context)
        else:
            pattern = CoOccurrence(
                item_a=pair[0],
                item_b=pair[1],
                count=1,
                strength=0.1,
                last_seen=timestamp,
                contexts=[context] if context else []
            )
            self.co_occurrences[pair] = pattern
    
    # ========================================================================
    # SIGNIFICANT PATTERNS (FILTERED)
    # ========================================================================
    
    def get_significant_patterns_only(self) -> Dict[str, Any]:
        """Return only significant patterns for reasoning"""
        significant = {
            'strong_co_occurrences': [],
            'reliable_sequences': [],
            'behavioral_patterns': [],
            'contradictions': [],
            'meta_patterns': []
        }
        
        # Strong co-occurrences
        for pair, pattern in self.co_occurrences.items():
            if pattern.count >= self.base_co_occurrence_threshold and pattern.strength >= 0.5:
                significant['strong_co_occurrences'].append({
                    'items': list(pair),
                    'strength': pattern.strength,
                    'count': pattern.count,
                    'source': pattern.source,
                })
        
        # Reliable sequences
        for seq_key, seq in self.sequences.items():
            if seq.confidence >= 0.6:
                significant['reliable_sequences'].append({
                    'steps': seq.steps,
                    'confidence': seq.confidence
                })
        
        # Confirmed behavioral patterns
        for name, behavior in self.behavioral_patterns.items():
            if behavior.confidence >= 0.6:
                significant['behavioral_patterns'].append({
                    'name': name,
                    'confidence': behavior.confidence,
                    'occurrences': behavior.occurrences,
                    'source': behavior.source,
                })
        
        # High severity contradictions
        significant['contradictions'] = [
            {
                'statement_a': c.statement_a,
                'statement_b': c.statement_b,
                'severity': c.severity
            }
            for c in self.contradictions if c.severity > 0.6
        ][-5:]
        
        # Strong meta-patterns
        significant['meta_patterns'] = [
            {
                'description': m.description,
                'confidence': m.meta_confidence
            }
            for m in self.meta_patterns if m.meta_confidence > 0.5
        ][-5:]
        
        return significant
    
    # ========================================================================
    # PATTERN DECAY
    # ========================================================================
    
    def _decay_patterns(self):
        """Fade patterns that haven't been reinforced"""
        current_time = time.time()
        
        # Decay co-occurrences
        to_remove = []
        for key, pattern in self.co_occurrences.items():
            time_since = current_time - pattern.last_seen
            if time_since > 300:
                pattern.count = max(0, pattern.count - 1)
                pattern.strength *= (1.0 - self.decay_rate)
                if pattern.count == 0 or pattern.strength < 0.01:
                    to_remove.append(key)
        
        for key in to_remove:
            del self.co_occurrences[key]
        
        # Decay sequences
        to_remove = []
        for key, seq in self.sequences.items():
            time_since = current_time - seq.last_seen
            if time_since > 600:
                seq.count = max(0, seq.count - 1)
                seq.confidence *= (1.0 - self.decay_rate)
                if seq.count == 0:
                    to_remove.append(key)
        
        for key in to_remove:
            del self.sequences[key]
        
        # Decay behavioral patterns
        for name, behavior in self.behavioral_patterns.items():
            time_since = current_time - behavior.last_seen
            if time_since > 300:
                behavior.confidence *= (1.0 - self.decay_rate * 0.5)
    
    # ========================================================================
    # STATISTICS
    # ========================================================================
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics"""
        return {
            'total_co_occurrences': len(self.co_occurrences),
            'strong_co_occurrences': sum(1 for p in self.co_occurrences.values() 
                                        if p.count >= self.base_co_occurrence_threshold),
            'total_sequences': len(self.sequences),
            'multi_step_sequences': sum(1 for s in self.sequences.values() if len(s.steps) >= 3),
            'behavioral_patterns_detected': sum(1 for b in self.behavioral_patterns.values() 
                                               if b.confidence > 0.5),
            'contradictions_found': len(self.contradictions),
            'meta_patterns': len(self.meta_patterns),
            'pareidolia_patterns': len(self.pareidolia_patterns),
            'boredom_level': self.boredom_level,
            'recent_items': len(self.recent_items)
        }
    
    # ========================================================================
    # SELF-OBSERVATION SYSTEM
    # ========================================================================

    def _collect_self_state(self) -> Optional[Dict[str, Any]]:
        """Poll active lobes for Monday's internal state and return as observation data."""
        items = []
        emotions = {}
        topics = []
        words = []

        # Emotion lobe
        try:
            result = self._query_lobe('emotion', {'type': 'get_state'})
            if result and result.get('status') == 'success':
                state = result.get('state', {})
                emotion_type = state.get('emotion', state.get('type', ''))
                intensity = state.get('intensity', 0.0)
                valence = state.get('valence', 0.0)
                if emotion_type:
                    items.append(f'self_emotion:{emotion_type}')
                    emotions = {'type': emotion_type, 'intensity': intensity, 'valence': valence}
                    if intensity > 0.6:
                        words.append(emotion_type)
        except Exception:
            pass

        # Autonomous Thinking lobe — get recent thought types and focus
        try:
            result = self._query_lobe('autonomous', {'type': 'get_recent_thoughts', 'limit': 5})
            if result and result.get('status') == 'success':
                thoughts = result.get('thoughts', [])
                for thought in thoughts:
                    t_type = thought.get('thought_type', '')
                    focus = thought.get('trigger', '')
                    if t_type:
                        items.append(f'self_thought:{t_type}')
                    if focus and not focus.startswith('feeling_') and not focus.startswith('no_'):
                        topics.append(focus)
        except Exception:
            pass

        # Meta-cognition lobe
        try:
            result = self._query_lobe('meta_cognition', {'type': 'get_state'})
            if result and result.get('status') == 'success':
                state = result.get('state', {})
                awareness = state.get('awareness_level', '')
                if awareness:
                    items.append(f'self_meta:{awareness}')
        except Exception:
            pass

        # Values lobe
        try:
            result = self._query_lobe('values', {'type': 'get_values', 'min_strength': 0.5})
            if result and result.get('status') == 'success':
                values = result.get('values', [])
                for v in values[:3]:
                    v_name = v.get('name', '')
                    if v_name:
                        items.append(f'self_value:{v_name}')
                        topics.append(v_name)
        except Exception:
            pass

        # Notus — recent memory topics
        try:
            result = self._query_lobe('notus', {'type': 'get_recent_memories', 'limit': 5})
            if result and result.get('status') == 'success':
                memories = result.get('memories', [])
                for m in memories:
                    topic = m.get('topic', '')
                    if topic:
                        topics.append(f'memory:{topic}')
        except Exception:
            pass

        if not items:
            return None

        return {
            'items': items,
            'emotions': emotions,
            'words': words,
            'topics': topics,
            'statement': '',
            'source': 'self',
        }

    def _detect_significant_self_patterns(self):
        """Scan patterns tagged 'self' for significant findings and mysteries."""
        significant: List[str] = []

        # Emotion cycling: same emotion seen in multiple self-observations
        self_emotion_items = [
            item for item, _ in self.recent_items
            if item.startswith('self_emotion:')
        ]
        if len(self_emotion_items) >= 3:
            from collections import Counter
            counts = Counter(self_emotion_items)
            for emotion_item, cnt in counts.items():
                if cnt >= 3:
                    emotion_name = emotion_item.split(':', 1)[1]
                    significant.append(
                        f"I've been feeling {emotion_name} repeatedly in my recent internal state."
                    )

        # Thought type looping
        self_thought_items = [
            item for item, _ in self.recent_items
            if item.startswith('self_thought:')
        ]
        if len(self_thought_items) >= 4:
            from collections import Counter
            counts = Counter(self_thought_items)
            for thought_item, cnt in counts.items():
                if cnt >= 4:
                    thought_name = thought_item.split(':', 1)[1]
                    significant.append(
                        f"I keep generating {thought_name} thoughts — there may be something on my mind."
                    )

        # Recurring topics in self-observations
        self_topics = [t for ts, _ in self.recent_topics for t in ts if not t.startswith('memory:')]
        if len(self_topics) >= 4:
            from collections import Counter
            counts = Counter(self_topics)
            for topic, cnt in counts.items():
                if cnt >= 3 and not topic.startswith('self_'):
                    significant.append(
                        f"I keep returning to the topic of '{topic}' in my internal observations."
                    )

        # Self behavioral patterns (source='self', confident)
        for name, behavior in self.behavioral_patterns.items():
            if behavior.source == 'self' and behavior.confidence >= 0.5:
                significant.append(
                    f"I've noticed a '{name}' pattern in my own processing."
                )

        # High-confidence self co-occurrences
        for pair, pattern in self.co_occurrences.items():
            if pattern.source == 'self' and pattern.strength >= 0.5 and pattern.count >= 3:
                significant.append(
                    f"Internally, '{pattern.item_a}' and '{pattern.item_b}' keep appearing together in me."
                )

        return significant

    def _update_self_mysteries(self, self_state: Dict[str, Any]):
        """Track patterns that recur but don't fit any known template — mysteries."""
        items = self_state.get('items', [])
        if not items:
            return

        with self._self_obs_lock:
            # A mystery is triggered when self-items appear repeatedly without
            # any matching behavioral pattern explanation
            unexplained_items = [
                item for item in items
                if not any(
                    item in str(bp.signals)
                    for bp in self.behavioral_patterns.values()
                    if bp.source == 'self'
                )
            ]
            if not unexplained_items:
                return

            description = f"Unexplained internal signals: {', '.join(unexplained_items[:3])}"

            # Check if this mystery already exists
            for mystery in self.self_mysteries:
                if mystery.description == description and not mystery.resolved:
                    mystery.occurrence_count += 1
                    mystery.last_seen = time.time()
                    return

            # New mystery
            self.self_mysteries.append(SelfMystery(
                description=description,
                signals=unexplained_items,
                first_seen=time.time(),
                last_seen=time.time(),
            ))

            # Cap mystery list
            if len(self.self_mysteries) > 20:
                # Remove oldest resolved ones first, then oldest unresolved
                resolved = [m for m in self.self_mysteries if m.resolved]
                unresolved = [m for m in self.self_mysteries if not m.resolved]
                self.self_mysteries = (resolved[-5:] + unresolved)[-20:]

    def _get_escalated_mysteries(self) -> List[str]:
        """Return mysteries that have recurred enough to tell Monday about."""
        with self._self_obs_lock:
            escalated = []
            for mystery in self.self_mysteries:
                if not mystery.resolved and mystery.occurrence_count >= 3:
                    escalated.append(
                        f"I keep noticing '{mystery.description}' internally and I'm not sure why."
                    )
            return escalated

    def _broadcast_self_patterns(self, messages: List[str]):
        """Send significant self-pattern insights to the Autonomous Thinking lobe."""
        if not messages:
            return
        # Throttle: only broadcast every 2 minutes to avoid flooding
        now = time.time()
        if now - self._last_self_alert_time < 120:
            return
        self._last_self_alert_time = now

        for msg in messages[:3]:  # Cap at 3 per cycle
            try:
                self._query_lobe('autonomous', {
                    'type': 'self_pattern_alert',
                    'description': msg,
                    'timestamp': now,
                })
            except Exception:
                pass

        # Store significant patterns in Notus for long-term memory
        try:
            for msg in messages[:3]:
                self._query_lobe('notus', {
                    'type': 'store_self_pattern',
                    'pattern': msg,
                    'timestamp': now,
                })
        except Exception:
            pass

    def _self_observation_loop(self):
        """Background thread: periodically poll lobes and observe Monday's internal state."""
        print("🔭 Self-observation loop started")
        while self.running:
            time.sleep(self.self_observation_interval)
            if not self.running:
                break
            try:
                self_state = self._collect_self_state()
                if self_state is None:
                    continue

                # Feed internal state into pattern detection as source='self'
                # We duplicate the observe() logic but tag source on newly created patterns
                self._observe_self(self_state)

                # Detect significant self-patterns and mysteries
                significant = self._detect_significant_self_patterns()
                mysteries = self._get_escalated_mysteries()
                all_messages = significant + mysteries

                if all_messages:
                    self._broadcast_self_patterns(all_messages)
                    print(f"🔭 [self-observation] Found {len(all_messages)} self-pattern(s) to report")

            except Exception as e:
                print(f"⚠️  Self-observation error: {e}")

    def _observe_self(self, data: Dict[str, Any]):
        """Like observe() but tags new patterns with source='self'."""
        current_time = time.time()
        items = data.get('items', [])
        emotions = data.get('emotions', {})
        words = data.get('words', [])
        topics = data.get('topics', [])
        statement = data.get('statement', '')

        # Update history
        for item in items:
            self.recent_items.append((item, current_time))
        if emotions:
            self.recent_emotions.append((emotions, current_time))
        if topics:
            self.recent_topics.append((topics, current_time))
        if words:
            self.recent_word_choices.extend([(w, current_time) for w in words])
        if statement:
            self.statement_history.append((statement, current_time))

        # Record co-occurrences tagged as self
        for i, item_a in enumerate(items):
            for item_b in items[i + 1:]:
                self._record_co_occurrence_sourced(item_a, item_b, current_time, 'self')

        # Update self-mysteries
        self._update_self_mysteries(data)

        # Detect behavioral patterns in self data
        self._detect_self_behavioral_patterns(data)

        self.detect_multi_step_sequences()
        self.detect_meta_patterns()
        self.update_boredom()

        if current_time - self.last_decay > 60:
            self._decay_patterns()
            self.last_decay = current_time

    def _record_co_occurrence_sourced(self, item_a: str, item_b: str, timestamp: float, source: str):
        """Record co-occurrence with an explicit source tag."""
        pair = tuple(sorted([item_a, item_b]))
        if pair in self.co_occurrences:
            pattern = self.co_occurrences[pair]
            pattern.count += 1
            pattern.last_seen = timestamp
            pattern.strength = min(1.0, pattern.count / 10.0)
        else:
            self.co_occurrences[pair] = CoOccurrence(
                item_a=pair[0],
                item_b=pair[1],
                count=1,
                strength=0.1,
                last_seen=timestamp,
                source=source,
            )

    def _detect_self_behavioral_patterns(self, data: Dict[str, Any]):
        """Detect behavioral-style patterns within Monday's own internal signals."""
        items = data.get('items', [])
        emotions = data.get('emotions', {})

        emotion_type = emotions.get('type', '') if isinstance(emotions, dict) else ''
        intensity = emotions.get('intensity', 0.0) if isinstance(emotions, dict) else 0.0

        # Self-rumination: keeps cycling through heavy emotions
        if emotion_type in ('sad', 'anxious', 'worried', 'angry') and intensity > 0.5:
            name = 'self_rumination'
            if name not in self.behavioral_patterns:
                self.behavioral_patterns[name] = BehavioralPattern(
                    name=name,
                    signals={'required': ['self_emotion:sad', 'self_emotion:anxious'],
                              'optional': ['self_emotion:worried', 'self_emotion:angry']},
                    source='self',
                )
            bp = self.behavioral_patterns[name]
            bp.occurrences += 1
            bp.last_seen = time.time()
            bp.confidence = min(1.0, bp.occurrences / 3.0)
            bp.source = 'self'

        # Self-curiosity loop: many question-type thoughts
        question_items = [i for i in items if i == 'self_thought:question']
        if len(question_items) >= 2:
            name = 'self_curiosity_loop'
            if name not in self.behavioral_patterns:
                self.behavioral_patterns[name] = BehavioralPattern(
                    name=name,
                    signals={'required': ['self_thought:question'], 'optional': []},
                    source='self',
                )
            bp = self.behavioral_patterns[name]
            bp.occurrences += 1
            bp.last_seen = time.time()
            bp.confidence = min(1.0, bp.occurrences / 3.0)
            bp.source = 'self'

    def get_self_mysteries(self) -> List[Dict[str, Any]]:
        """Return the current list of self-mysteries."""
        with self._self_obs_lock:
            return [
                {
                    'description': m.description,
                    'signals': m.signals,
                    'occurrence_count': m.occurrence_count,
                    'first_seen': m.first_seen,
                    'last_seen': m.last_seen,
                    'resolved': m.resolved,
                    'resolution': m.resolution,
                }
                for m in self.self_mysteries
            ]

    def resolve_mystery(self, description: str, resolution: str):
        """Mark a mystery as resolved with an explanation."""
        with self._self_obs_lock:
            for mystery in self.self_mysteries:
                if mystery.description == description:
                    mystery.resolved = True
                    mystery.resolution = resolution
                    break

    # ========================================================================
    # DIRECT FUNCTION CALL COMMUNICATION (NO SOCKETS)
    # ========================================================================
    
    def _register_with_thalamus(self):
        """Register with Thalamus - DIRECT FUNCTION CALL (NO SOCKETS)"""
        try:
            result = self.thalamus.register_lobe('pattern', self)
            if result.get('status') == 'success':
                print("✅ Pattern Recognition registered with Thalamus (direct function calls)")
                return True
            return False
        except Exception as e:
            print(f"⚠️  Failed to register with Thalamus: {e}")
            return False
    
    def start(self):
        """Start pattern recognition - register with Thalamus (NO SOCKETS)"""
        print(f"🔍 Advanced Pattern Recognition: Registering with Thalamus...")
        print(f"   Behavioral patterns, multi-step sequences, meta-patterns")
        print(f"   Pareidolia mode, contradiction tracking, self-observation")
        print(f"   Communication: Direct function calls (NO SOCKETS)")
        
        # Load self-observation interval from config if available
        try:
            config_path = os.path.join(os.path.dirname(__file__), 'pattern_config.json')
            with open(config_path) as f:
                cfg = json.load(f)
            interval = cfg.get('pattern_recognition', {}).get('self_observation', {}).get(
                'interval_seconds', self.self_observation_interval
            )
            self.self_observation_interval = float(interval)
        except Exception:
            pass

        # Register with Thalamus
        if not self._register_with_thalamus():
            print("❌ Failed to register with Thalamus")
            return

        # Start self-observation background thread
        self_obs_thread = threading.Thread(target=self._self_observation_loop, daemon=True)
        self_obs_thread.start()
        print(f"🔭 Self-observation thread started (interval: {self.self_observation_interval}s)")
        
        # Keep running (Thalamus calls us directly, no listening loop needed)
        while self.running:
            time.sleep(0.1)
    
    def _query_lobe(self, lobe_name: str, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Query a lobe through Thalamus - DIRECT FUNCTION CALL"""
        try:
            msg_type = message.get('type', 'query')
            return self.thalamus.send_message(lobe_name, msg_type, message)
        except Exception:
            return None
    
    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming message"""
        msg_type = message.get('type')
        
        # FIX: add health probe
        if msg_type == 'health':
            return {'status': 'success', 'healthy': True, 'pid': os.getpid()}
        
        if msg_type == 'observe' or msg_type == 'process_input':
            data = message.get('data', {})
            if not data and msg_type == 'process_input':
                # If process_input called without data, create empty data dict
                data = {}
            patterns = self.observe(data)
            return {'status': 'success', 'patterns': patterns}
            
        elif msg_type == 'get_significant':
            significant = self.get_significant_patterns_only()
            return {'status': 'success', 'significant_patterns': significant}
            
        elif msg_type == 'get_statistics':
            stats = {'total_co_occurrences': len(self.co_occurrences)}
            return {'status': 'success', 'statistics': stats}

        elif msg_type == 'get_self_mysteries':
            return {'status': 'success', 'mysteries': self.get_self_mysteries()}

        elif msg_type == 'resolve_mystery':
            description = message.get('description', '')
            resolution = message.get('resolution', '')
            if description:
                self.resolve_mystery(description, resolution)
                return {'status': 'success'}
            return {'status': 'error', 'message': 'Missing description'}

        elif msg_type == 'get_self_patterns':
            self_co = [
                {'items': list(p), 'strength': co.strength, 'count': co.count}
                for p, co in self.co_occurrences.items()
                if co.source == 'self' and co.count >= 2
            ]
            self_behaviors = [
                {'name': b.name, 'confidence': b.confidence, 'occurrences': b.occurrences}
                for b in self.behavioral_patterns.values()
                if b.source == 'self' and b.confidence >= 0.3
            ]
            return {
                'status': 'success',
                'self_co_occurrences': self_co,
                'self_behavioral_patterns': self_behaviors,
                'self_mysteries': self.get_self_mysteries(),
            }
            
        else:
            return {'status': 'error', 'message': f'Unknown message type: {msg_type}'}
    
    def shutdown(self):
        """Graceful shutdown"""
        self.running = False
        # No sockets to close

if __name__ == "__main__":
    lobe = AdvancedPatternRecognition()
    try:
        lobe.start()
    except KeyboardInterrupt:
        print("\n🛑 Pattern recognition shutting down...")
        lobe.shutdown()
