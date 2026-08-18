#!/usr/bin/env python3
"""
Advanced Emotional Engine – production‑ready, single‑file build
- Autonomous inner life (attachment/needs/internal loops) so she can feel without mirroring
- PAD dynamics with hysteresis + refractory to stop flip‑flopping
- Blends, memories, pattern learning, expressions wired into output
- Safer keyword detection + false‑positive filters
- Clean persistence (save/load) with no hardcoded paths
- Deterministic hooks (rng + logger) for unit tests
"""
from __future__ import annotations

import json
import time
import random
import re
import os
from runtime_paths import runtime_file
import tempfile
import sys
import threading
from dataclasses import dataclass, asdict, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any, Callable
from threading import Lock
from thalamus import get_thalamus

# ------------------------------
# Core Enums & Dataclasses
# ------------------------------

class EmotionalState(Enum):
    # Primary emotions
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    EXCITED = "excited"
    CALM = "calm"
    WORRIED = "worried"
    CURIOUS = "curious"
    PROUD = "proud"
    SCARED = "scared"
    SURPRISED = "surprised"
    DISGUSTED = "disgusted"
    CONTEMPT = "contempt"
    # Complex blends
    NOSTALGIC = "nostalgic"
    ANXIOUS = "anxious"
    FRUSTRATED = "frustrated"
    EUPHORIC = "euphoric"
    MELANCHOLIC = "melancholic"
    PLAYFUL = "playful"
    PROTECTIVE = "protective"
    MISCHIEVOUS = "mischievous"

@dataclass
class PAD:
    v: float  # valence  (-1..1)
    a: float  # arousal  (-1..1)
    d: float  # dominance (-1..1)

@dataclass
class EmotionalMemory:
    emotion: EmotionalState
    intensity: float  # 0..1
    trigger: str
    timestamp: float
    context: str
    influence_strength: float = 1.0
    associated_emotions: List[EmotionalState] = field(default_factory=list)

@dataclass
class PersonalityTraits:
    openness: float = 0.5
    conscientiousness: float = 0.5
    extraversion: float = 0.5
    agreeableness: float = 0.5
    neuroticism: float = 0.5
    emotional_sensitivity: float = 0.6
    emotional_stability: float = 0.5
    emotional_expressiveness: float = 0.6
    empathy_level: float = 0.6
    # PAD home base + gains
    pad_setpoint_v: float = 0.1
    pad_setpoint_a: float = 0.15
    pad_setpoint_d: float = 0.2
    hysteresis_margin: float = 0.15
    refractory_sec: float = 1.5

@dataclass
class AttachmentModel:
    security: float = 0.6
    sensitivity: float = 0.7
    bond_strength: float = 0.9
    abandonment_fear: float = 0.2
    hurt: float = 0.0
    guilt: float = 0.0

@dataclass
class InternalNeeds:
    safety: float = 0.7
    belonging: float = 0.8
    autonomy: float = 0.8
    competence: float = 0.6
    stimulation: float = 0.5

@dataclass
class EmotionalStateOutput:
    """Standardized emotional state output for other lobes to read"""
    emotion: str  # Current emotional state
    intensity: float  # 0..1 how intense
    pleasure: float  # PAD: -1..1 valence
    arousal: float  # PAD: -1..1 activation level
    dominance: float  # PAD: -1..1 control/power
    emotional_tone: str  # For language gen: "happy", "sad", "angry", etc
    emphasis: List[str]  # Speech emphasis patterns
    voice_prosody: Dict[str, float]  # For voice lobe: pitch, speed, warmth, clarity
    confidence: float  # How confident is Monday in this emotional state
    timestamp: float  # When this state was created
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for transmission"""
        return {
            'emotion': self.emotion,
            'intensity': self.intensity,
            'pleasure': self.pleasure,
            'arousal': self.arousal,
            'dominance': self.dominance,
            'emotional_tone': self.emotional_tone,
            'emphasis': self.emphasis,
            'voice_prosody': self.voice_prosody,
            'confidence': self.confidence,
            'timestamp': self.timestamp
        }

@dataclass
class InternalState:
    worry: float = 0.2
    tension: float = 0.1
    hope: float = 0.3
    fatigue: float = 0.2
    rumination: float = 0.0
    competence: float = 0.8
    autonomy: float = 0.5

@dataclass
class ExpressionState:
    tears: bool = False
    voice_shake: bool = False
    withdraw: bool = False

@dataclass
class EmotionalBlend:
    primary_emotion: EmotionalState
    secondary_emotions: List[Tuple[EmotionalState, float]]
    intensity: float
    created_at: float

# ------------------------------
# Appraisal System
# ------------------------------

# Meaning categories that drive emotion
EVENT_TYPES = [
    'harm', 'betrayal', 'rejection', 'threat', 'unfairness', 'loss',
    'success', 'affection', 'gift', 'conflict', 'criticism', 'abandonment',
    'support', 'celebration', 'neutral',
]

@dataclass
class AppraisalResult:
    """Structured meaning of an event, derived from understanding, not keywords."""
    event_type: str          # one of EVENT_TYPES
    severity: float          # 0..1 – how significant is this
    directed_at_monday: bool # is Monday the target / subject?
    directed_at_user: bool   # is the user the target / subject?
    third_party: bool        # about someone else entirely
    negated: bool            # the event was negated ("I'm not upset")
    sarcasm_likely: bool     # sarcasm detected
    raw_text: str            # original message
    # What Monday's own emotion should lean toward, given this appraisal
    monday_pad_delta: Tuple[float, float, float] = (0.0, 0.0, 0.0)  # (Δv, Δa, Δd)
    # What the user is inferred to be feeling
    user_inferred_emotion: str = 'neutral'
    user_confidence: float = 0.0

@dataclass
class UserAffectModel:
    """Monday's model of what the user is feeling, kept separate from Monday's own emotion."""
    inferred_emotion: str = 'neutral'
    confidence: float = 0.0
    inferred_need: str = 'neutral'   # 'validation','help','celebration','space','neutral'
    last_updated: float = 0.0

class AppraisalEngine:
    """
    Classifies the *meaning* of a message rather than counting keywords.
    Produces an AppraisalResult that feeds the PAD pipeline.
    Keywords are used only as weak evidence inside the classifiers.
    """

    # --------------- Event-type pattern tables ---------------
    # Each entry: (pattern_phrases, event_type, Δvalence, Δarousal, Δdominance)
    # These represent Monday's emotional response to each event type.
    _EVENT_PAD: Dict[str, Tuple[float, float, float]] = {
        'harm':        (-0.70,  0.50, -0.20),
        'betrayal':    (-0.80,  0.40, -0.30),
        'rejection':   (-0.60,  0.30, -0.40),
        'threat':      (-0.60,  0.70, -0.30),
        'unfairness':  (-0.50,  0.60,  0.10),
        'loss':        (-0.70, -0.10, -0.30),
        'success':     ( 0.60,  0.40,  0.30),
        'affection':   ( 0.70,  0.20,  0.20),
        'gift':        ( 0.50,  0.30,  0.10),
        'conflict':    (-0.40,  0.60,  0.20),
        'criticism':   (-0.30,  0.40, -0.10),
        'abandonment': (-0.70,  0.20, -0.50),
        'support':     ( 0.60,  0.10,  0.30),
        'celebration': ( 0.80,  0.50,  0.30),
        'neutral':     ( 0.00,  0.00,  0.00),
    }

    # User emotion implied by each event type when user is the subject
    _USER_EMOTION_BY_EVENT: Dict[str, str] = {
        'harm':        'hurt',
        'betrayal':    'angry',
        'rejection':   'sad',
        'threat':      'scared',
        'unfairness':  'angry',
        'loss':        'sad',
        'success':     'proud',
        'affection':   'happy',
        'gift':        'happy',
        'conflict':    'angry',
        'criticism':   'worried',
        'abandonment': 'sad',
        'support':     'grateful',
        'celebration': 'excited',
        'neutral':     'neutral',
    }

    # Phrase-to-event-type classifiers (ordered, first match wins per category).
    # Each tuple: (list_of_phrase_fragments, event_type, base_severity)
    _CLASSIFIERS: List[Tuple[List[str], str, float]] = [
        # Betrayal
        (['lied to me', 'went behind my back', 'stabbed me', 'betrayed', 'cheated on', 'cheated me',
          'went behind', 'talking behind', 'broke my trust', 'used me', 'manipulated me'], 'betrayal', 0.8),
        # Abandonment
        (['left me', 'walked out', 'ghosted', 'abandoned', 'ditched me', 'stopped talking to me',
          'never there for me', 'cut me off', 'blocked me'], 'abandonment', 0.75),
        # Rejection
        (['rejected', 'turned me down', 'said no', 'not interested', 'dumped', 'broke up with me',
          'fired me', 'not good enough', "didn't pick me", "wasn't chosen"], 'rejection', 0.65),
        # Loss
        (['died', 'passed away', 'lost my', 'grief', 'mourning', 'funeral', 'gone forever',
          'will never see', 'lost everything', 'miscarriage', 'accident killed'], 'loss', 0.85),
        # Harm / hurt
        (['hurt me', 'hit me', 'attacked', 'abused', 'mistreated', 'treated me like garbage',
          'treated me like trash', 'treated me like dirt', 'made me feel worthless',
          'made me feel stupid', 'humiliated', 'degraded', 'screamed at me', 'yelled at me'], 'harm', 0.80),
        # Threat
        (['threatened', 'going to hurt', 'going to kill', 'warned me', 'scared of',
          "don't feel safe", 'feel unsafe', 'in danger'], 'threat', 0.75),
        # Unfairness
        (['not fair', "isn't fair", 'unfair', 'should not have', 'got away with',
          'blamed me for', 'scapegoated', 'punished for something', 'wrong person',
          "didn't do anything wrong", 'not my fault'], 'unfairness', 0.60),
        # Conflict
        (['fight with', 'argument with', 'argued with', 'yelling at each other',
          'screaming at each other', 'falling out', 'clash with', 'tension with',
          'not speaking to', 'on bad terms'], 'conflict', 0.55),
        # Criticism
        (['criticized', 'told me i was wrong', 'called me out', 'said i did it wrong',
          'pointed out my mistake', 'embarrassed me', "doesn't think i'm good",
          'talked down to me', 'condescending'], 'criticism', 0.45),
        # Success
        (['got the job', 'got promoted', 'passed the exam', 'finished it', 'won',
          'succeeded', 'accomplished', 'completed', 'finally did it', 'pulled it off',
          'graduated', 'accepted', 'got in', 'landed the'], 'success', 0.65),
        # Celebration
        (['birthday', 'anniversary', 'graduated', 'wedding', 'baby', 'promotion',
          'celebrating', 'party for', 'good news'], 'celebration', 0.60),
        # Affection
        (['i love you', 'i care about you', 'you mean so much', 'grateful for you',
          'appreciate you', 'you matter', 'you make me happy', 'i like you',
          'miss you', 'thinking of you'], 'affection', 0.65),
        # Support
        (['helped me', 'supported me', 'there for me', 'picked me up',
          'listened to me', 'had my back', 'stood up for me'], 'support', 0.55),
        # Gift
        (['gave me', 'bought me', 'got me a', 'sent me', 'surprised me with'], 'gift', 0.45),
    ]

    # Negation phrase patterns
    _NEGATION_PHRASES: List[str] = [
        "not ", "n't ", "never ", "no longer ", "don't ", "didn't ", "won't ",
        "wasn't ", "isn't ", "haven't ", "can't ", "couldn't ",
    ]

    # Sarcasm markers
    _SARCASM_MARKERS: List[str] = [
        'great, thanks', 'oh great', 'oh wonderful', 'yeah right', 'sure thing',
        'totally fine', 'absolutely fine', 'oh sure', 'oh wow', 'how lovely',
        'how wonderful', 'how nice', 'how great', 'oh perfect', 'just perfect',
        'just great', 'just wonderful', 'oh fantastic', '/s',
    ]

    # Patterns indicating Monday is the target
    _MONDAY_TARGET: List[str] = [
        'you ', 'your ', "you're", "you've", "you'll", "you'd", "you are",
        'monday ', "monday's",
    ]

    # Patterns indicating the user is the subject/speaker
    _USER_SUBJECT: List[str] = [
        'i ', "i'm", "i've", "i've", "i'd", "i'll", 'my ', 'me ', 'myself',
    ]

    def appraise(self, text: str, relationship_history: Optional[List[str]] = None,
                 sensitivity_map: Optional[Dict[str, float]] = None) -> AppraisalResult:
        """
        Main entry point. Returns a full AppraisalResult for `text`.
        relationship_history: list of recent event_type strings for escalation
        sensitivity_map: event_type → learned sensitivity multiplier
        """
        tl = text.lower()

        negated = self._detect_negation(tl)
        sarcasm = self._detect_sarcasm(tl)

        # If sarcasm, flip positive surface signals to negative
        effective_text = tl
        if sarcasm:
            # Replace surface positive words to avoid false positive classification
            for pos in ['great', 'wonderful', 'fantastic', 'perfect', 'lovely', 'fine']:
                effective_text = effective_text.replace(pos, '_sarcasm_')

        directed_at_monday = self._directed_at_monday(tl)
        directed_at_user = self._directed_at_user(tl)
        third_party = not directed_at_monday and not directed_at_user

        event_type, base_severity = self._classify_event(effective_text)

        # If negated, drop severity and shift event_type toward neutral
        if negated and event_type not in ('loss',):  # can't negate a death
            base_severity *= 0.25
            if base_severity < 0.15:
                event_type = 'neutral'

        # Severity modifiers: intensifiers, repetition in history
        severity = self._adjust_severity(base_severity, tl, event_type, relationship_history, sensitivity_map)

        # PAD delta for Monday based on who is affected
        pad_delta = self._compute_monday_pad(event_type, severity, directed_at_monday, directed_at_user)

        # User inferred emotion
        user_emotion, user_conf = self._infer_user_emotion(event_type, directed_at_user, severity, negated)

        return AppraisalResult(
            event_type=event_type,
            severity=severity,
            directed_at_monday=directed_at_monday,
            directed_at_user=directed_at_user,
            third_party=third_party,
            negated=negated,
            sarcasm_likely=sarcasm,
            raw_text=text,
            monday_pad_delta=pad_delta,
            user_inferred_emotion=user_emotion,
            user_confidence=user_conf,
        )

    # --------------- Private classifiers ---------------

    def _detect_negation(self, tl: str) -> bool:
        return any(neg in tl for neg in self._NEGATION_PHRASES)

    def _detect_sarcasm(self, tl: str) -> bool:
        # Punctuation-based: positive word followed by '?' or ending '...'
        for marker in self._SARCASM_MARKERS:
            if marker in tl:
                return True
        # Polite positive words after clear negative framing
        if re.search(r'\b(terrible|awful|horrible|worst)\b.{0,30}\b(great|fine|okay|wonderful)\b', tl):
            return True
        return False

    def _directed_at_monday(self, tl: str) -> bool:
        return any(p in tl for p in self._MONDAY_TARGET)

    def _directed_at_user(self, tl: str) -> bool:
        return any(p in tl for p in self._USER_SUBJECT)

    def _classify_event(self, tl: str) -> Tuple[str, float]:
        for phrases, event_type, severity in self._CLASSIFIERS:
            for phrase in phrases:
                if phrase in tl:
                    return event_type, severity
        return 'neutral', 0.1

    def _adjust_severity(self, base: float, tl: str, event_type: str,
                          history: Optional[List[str]], sensitivity_map: Optional[Dict[str, float]]) -> float:
        severity = base
        # Intensifiers
        intensifiers = ['so ', 'really ', 'very ', 'extremely ', 'absolutely ', 'completely ',
                        'totally ', 'deeply ', 'badly ', 'terribly ']
        hits = sum(1 for w in intensifiers if w in tl)
        severity = min(1.0, severity + hits * 0.08)

        # Diminishers
        diminishers = ['a bit ', 'slightly ', 'kind of ', 'sort of ', 'a little ']
        d_hits = sum(1 for w in diminishers if w in tl)
        severity = max(0.0, severity - d_hits * 0.08)

        # Learned sensitivity for this event type
        if sensitivity_map and event_type in sensitivity_map:
            severity = min(1.0, severity * sensitivity_map[event_type])

        # Escalation: repeated same event type in recent history raises severity
        if history:
            repeat_count = history.count(event_type)
            severity = min(1.0, severity + repeat_count * 0.10)

        return round(severity, 3)

    def _compute_monday_pad(self, event_type: str, severity: float,
                             directed_at_monday: bool, directed_at_user: bool) -> Tuple[float, float, float]:
        base_v, base_a, base_d = self._EVENT_PAD.get(event_type, (0.0, 0.0, 0.0))

        # Scale by severity
        v = base_v * severity
        a = base_a * severity
        d = base_d * severity

        # If directed at Monday directly, amplify emotional impact
        if directed_at_monday:
            v *= 1.4
            a *= 1.2
            d *= 1.1

        # If harm/rejection aimed at the user, Monday feels protectiveness:
        # boost concern/protectiveness flavour (lower valence, raise arousal slightly)
        elif directed_at_user and event_type in ('harm', 'betrayal', 'rejection', 'abandonment', 'threat'):
            v = max(-1.0, v * 0.9)   # concern but slightly less intense than direct hit
            a = min(1.0, a * 1.1)    # slightly more alert

        def clamp(x: float) -> float:
            return max(-1.0, min(1.0, x))

        return (clamp(v), clamp(a), clamp(d))

    def _infer_user_emotion(self, event_type: str, directed_at_user: bool,
                             severity: float, negated: bool) -> Tuple[str, float]:
        if negated or severity < 0.15:
            return 'neutral', 0.2
        base_emotion = self._USER_EMOTION_BY_EVENT.get(event_type, 'neutral')
        confidence = min(0.95, 0.4 + severity * 0.6) if directed_at_user else min(0.6, 0.2 + severity * 0.4)
        return base_emotion, confidence


# ------------------------------
# Engine
# ------------------------------

class AdvancedEmotionalEngine:
    def __init__(self, name: str = "AI", logger: Optional[Callable[[str], None]] = None, rng: Optional[random.Random] = None, thalamus: Optional[Any] = None):
        self.name = name
        self.current_emotion: EmotionalState = EmotionalState.CALM
        self.emotional_intensity: float = 0.4
        self.personality = PersonalityTraits()
        self.emotional_memories: List[EmotionalMemory] = []
        self.mood_history: List[Tuple[float, EmotionalState, float]] = []
        self.emotional_blends: List[EmotionalBlend] = []
        self.emotional_patterns: Dict[str, List[EmotionalState]] = {}
        self.emotional_resonance: float = 0.0
        self.emotional_predictions: Dict[str, Dict[str, float]] = {}
        self.emotional_trauma_memories: List[Dict[str, Any]] = []
        self.emotional_intelligence_score: float = 0.5
        self.emotional_decay_rate: float = 0.05
        self.blend_threshold: float = 0.3
        self.memory_influence_decay: float = 0.02
        self._logger = logger or (lambda _: None)
        self._rng = rng or random.Random()
        self.thalamus = thalamus
        self.engine_lock = threading.Lock()
        # PAD dynamics - start neutral
        self.pad: PAD = PAD(0.0, 0.0, 0.0)
        self._last_primary: EmotionalState = EmotionalState.CALM
        self._last_switch_time: float = 0.0
        # PAD prototypes (better distributed for variety)
        self._PAD_PROTOS: Dict[EmotionalState, Tuple[float, float, float]] = {
            EmotionalState.HAPPY: ( 0.80,  0.30,  0.20),
            EmotionalState.SAD:   (-0.80, -0.20, -0.40),
            EmotionalState.ANGRY: (-0.70,  0.70,  0.60),
            EmotionalState.EXCITED:( 0.70,  0.80,  0.30),
            EmotionalState.CALM:  ( 0.30, -0.50,  0.50),
            EmotionalState.WORRIED:(-0.60,  0.60, -0.50),
            EmotionalState.CURIOUS:( 0.40,  0.30,  0.10),
            EmotionalState.PROUD: ( 0.50,  0.40,  0.70),
            EmotionalState.SCARED:(-0.70,  0.80, -0.70),
            EmotionalState.SURPRISED:(0.20,  0.90,  0.10),
            EmotionalState.DISGUSTED:(-0.80, 0.30,  0.40),
            EmotionalState.CONTEMPT:(-0.50, 0.20,  0.60),
            EmotionalState.NOSTALGIC:(0.20, -0.20, 0.20),
            EmotionalState.ANXIOUS: (-0.40, 0.70, -0.30),
            EmotionalState.FRUSTRATED:(-0.60, 0.60, 0.30),
            EmotionalState.EUPHORIC:(0.90, 0.90, 0.40),
            EmotionalState.MELANCHOLIC:(-0.40, -0.30, 0.20),
            EmotionalState.PLAYFUL:(0.60, 0.50, 0.00),
            EmotionalState.PROTECTIVE:(0.20, 0.50, 0.60),
            EmotionalState.MISCHIEVOUS:(0.50, 0.60, 0.10),
        }
        # Autonomy & internals
        self.autonomy_level: float = 0.85  # 0 mirror ↔ 1 fully internal
        self.attachment = AttachmentModel()
        self.needs = InternalNeeds()
        self.internal = InternalState()
        self.expression = ExpressionState()
        self._time_on_task: float = 0.0
        # Appraisal system
        self._appraisal_engine = AppraisalEngine()
        self._user_affect = UserAffectModel()
        # event_type → sensitivity multiplier (learned, starts at 1.0 for all)
        self._event_sensitivity: Dict[str, float] = {et: 1.0 for et in EVENT_TYPES}
        # recent event-type history for escalation detection (last 20)
        self._event_history: List[str] = []
        # unresolved negative appraisal tracking: list of (event_type, severity, timestamp)
        self._unresolved_appraisals: List[Tuple[str, float, float]] = []
        # attention bias: negative emotion biases ambiguous messages (set to event_type or None)
        self._attention_bias: Optional[str] = None

    # --------------- Public API ---------------
    def _query_lobe(self, lobe_name: str, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Query a lobe through Thalamus - DIRECT FUNCTION CALL"""
        if not self.thalamus:
            return None
        try:
            msg_type = message.get('type', 'query')
            return self.thalamus.send_message(lobe_name, msg_type, message)
        except Exception:
            return None
    
    def feel_emotion(self, emotion: EmotionalState, intensity: float, trigger: str, context: str = "") -> None:
        blend = self._check_emotional_blending(emotion, intensity)
        if blend:
            self._create_emotional_blend(blend, trigger, context)
        else:
            mem = EmotionalMemory(
                emotion=emotion,
                intensity=float(max(0.0, min(1.0, intensity))),
                trigger=trigger,
                timestamp=time.time(),
                context=context,
                influence_strength=1.0,
                associated_emotions=[self.current_emotion] if self.current_emotion != emotion else []
            )
            self.emotional_memories.append(mem)
            self.current_emotion = emotion
            self.emotional_intensity = mem.intensity
            self.mood_history.append((mem.timestamp, emotion, mem.intensity))
        self._update_emotional_patterns(emotion, trigger)
        if len(self.mood_history) > 200:
            self.mood_history = self.mood_history[-200:]
        self._log(f"{self.name} feels {emotion.value} (int {self.emotional_intensity:.2f}) due to: {trigger}")
        # Persist to Notus so queries across sessions have data
        try:
            self._query_lobe('notus', {
                'type': 'store_emotional_memory',
                'emotion': emotion.value,
                'intensity': float(max(0.0, min(1.0, intensity))),
                'trigger': trigger,
                'context': context,
            })
        except Exception:
            pass

    def get_emotional_response(self, user_input: str) -> str:
        # Query Notus for emotional memories
        try:
            notus_emotions = self._query_lobe('notus', {'type': 'get_emotional_memories', 'trigger': user_input})
            if notus_emotions and notus_emotions.get('status') == 'success':
                emotional_mems = notus_emotions.get('memories', [])
                # Add to local memories if not already present
        except Exception:
            pass

        # --- Appraisal-first pipeline ---
        appraisal = self._appraisal_engine.appraise(
            user_input,
            relationship_history=self._event_history[-20:],
            sensitivity_map=self._event_sensitivity,
        )
        self._apply_appraisal(appraisal)

        # Legacy keyword cues (weak secondary signal only)
        cues = self._analyze_emotional_cues(user_input)
        self._calculate_emotional_resonance(cues)
        context = self.assess_emotional_context(user_input)
        if self.emotional_memories:
            self.process_trauma_memory(self.emotional_memories[-1])
        memory_influence = self._get_memory_influence(user_input)
        base = self._generate_advanced_emotional_response(user_input, memory_influence)
        # Use appraisal-derived user affect for response enhancement
        predicted = {appraisal.user_inferred_emotion: appraisal.user_confidence}
        enhanced = self._enhance_response_with_advanced_features(base, user_input, predicted, context)
        self.calculate_emotional_intelligence()
        # Persist the response so future queries can return learned responses
        try:
            self._query_lobe('notus', {
                'type': 'store_emotional_memory',
                'emotion': self.current_emotion.value,
                'intensity': self.emotional_intensity,
                'trigger': user_input,
                'context': '',
                'response': enhanced,
            })
        except Exception:
            pass
        return enhanced

    def get_emotional_summary(self) -> str:
        recent = [m.emotion.value for m in self.emotional_memories[-10:]]
        counts: Dict[str, int] = {}
        for e in recent:
            counts[e] = counts.get(e, 0) + 1
        dominant_recent = max(counts.items(), key=lambda x: x[1]) if counts else ("calm", 0)
        unique_emotions = len(set(recent))
        complexity = (unique_emotions / 10.0) if recent else 0.0
        return (
            f"\n{self.name} EMOTIONAL SUMMARY:\n"
            f"- Current emotion: {self.current_emotion.value} (intensity: {self.emotional_intensity:.2f})\n"
            f"- Emotional resonance: {self.emotional_resonance:.2f}\n"
            f"- Recent dominant emotion: {dominant_recent[0]} (x{dominant_recent[1]})\n"
            f"- Emotional complexity: {complexity:.2f}\n"
            f"- Memories: {len(self.emotional_memories)} | Blends: {len(self.emotional_blends)}\n"
            f"- Patterns learned: {len(self.emotional_patterns)}\n"
            f"- EI score: {self.emotional_intelligence_score:.2f}\n"
        )

    # --------------- Persistence ---------------
    def save_emotional_state(self, filepath: str) -> None:
        data = {
            'name': self.name,
            'current_emotion': self.current_emotion.value,
            'emotional_intensity': self.emotional_intensity,
            'emotional_resonance': self.emotional_resonance,
            'personality': asdict(self.personality),
            'emotional_memories': [self._serialize_memory(m) for m in self.emotional_memories],
            'mood_history': [(t, e.value, i) for (t, e, i) in self.mood_history],
            'emotional_blends': [
                {
                    'primary_emotion': b.primary_emotion.value,
                    'secondary_emotions': [(e.value, w) for (e, w) in b.secondary_emotions],
                    'intensity': b.intensity,
                    'created_at': b.created_at,
                }
                for b in self.emotional_blends
            ],
            'emotional_patterns': {k: [e.value for e in v] for k, v in self.emotional_patterns.items()},
            'emotional_intelligence_score': self.emotional_intelligence_score,
            # Appraisal system state
            'event_sensitivity': self._event_sensitivity,
            'event_history': self._event_history[-50:],
            'unresolved_appraisals': [
                {'event_type': et, 'severity': sev, 'timestamp': ts}
                for (et, sev, ts) in self._unresolved_appraisals
            ],
            'attention_bias': self._attention_bias,
            'user_affect': {
                'inferred_emotion': self._user_affect.inferred_emotion,
                'confidence': self._user_affect.confidence,
                'inferred_need': self._user_affect.inferred_need,
                'last_updated': self._user_affect.last_updated,
            },
            'updated_at': time.time(),
        }
        data.setdefault('created_at', time.time())
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_emotional_state(self, filepath: str) -> None:
        obj = self._load_existing_data(filepath)
        if not obj:
            return
        self.name = obj.get('name', self.name)
        self.current_emotion = EmotionalState(obj.get('current_emotion', EmotionalState.CALM.value))
        self.emotional_intensity = float(obj.get('emotional_intensity', 0.4))
        self.emotional_resonance = float(obj.get('emotional_resonance', 0.0))
        p = obj.get('personality', {})
        self.personality = PersonalityTraits(**{k: float(v) for k, v in p.items()}) if p else self.personality
        self.emotional_memories = [self._deserialize_memory(m) for m in obj.get('emotional_memories', [])]
        self.mood_history = [(float(t), EmotionalState(e), float(i)) for (t, e, i) in obj.get('mood_history', [])]
        self.emotional_blends = [
            EmotionalBlend(
                primary_emotion=EmotionalState(b['primary_emotion']),
                secondary_emotions=[(EmotionalState(e), float(w)) for (e, w) in b.get('secondary_emotions', [])],
                intensity=float(b['intensity']),
                created_at=float(b['created_at'])
            ) for b in obj.get('emotional_blends', [])
        ]
        self.emotional_patterns = {k: [EmotionalState(e) for e in v] for k, v in obj.get('emotional_patterns', {}).items()}
        self.emotional_intelligence_score = float(obj.get('emotional_intelligence_score', 0.5))
        # Appraisal system state (additive — defaults gracefully if missing)
        saved_sensitivity = obj.get('event_sensitivity', {})
        for et in EVENT_TYPES:
            self._event_sensitivity[et] = float(saved_sensitivity.get(et, 1.0))
        self._event_history = list(obj.get('event_history', []))
        raw_unresolved = obj.get('unresolved_appraisals', [])
        self._unresolved_appraisals = [
            (u['event_type'], float(u['severity']), float(u['timestamp']))
            for u in raw_unresolved if isinstance(u, dict)
        ]
        self._attention_bias = obj.get('attention_bias', None)
        ua = obj.get('user_affect', {})
        if ua:
            self._user_affect = UserAffectModel(
                inferred_emotion=ua.get('inferred_emotion', 'neutral'),
                confidence=float(ua.get('confidence', 0.0)),
                inferred_need=ua.get('inferred_need', 'neutral'),
                last_updated=float(ua.get('last_updated', 0.0)),
            )

    # --------------- Internals ---------------
    def _check_emotional_blending(self, new_emotion: EmotionalState, intensity: float) -> Optional[EmotionalBlend]:
        if self.current_emotion == EmotionalState.CALM or self.emotional_intensity < self.blend_threshold:
            return None
        combos = {
            (EmotionalState.SAD, EmotionalState.HAPPY): EmotionalState.NOSTALGIC,
            (EmotionalState.WORRIED, EmotionalState.EXCITED): EmotionalState.ANXIOUS,
            (EmotionalState.ANGRY, EmotionalState.WORRIED): EmotionalState.FRUSTRATED,
            (EmotionalState.HAPPY, EmotionalState.EXCITED): EmotionalState.EUPHORIC,
            (EmotionalState.SAD, EmotionalState.CALM): EmotionalState.MELANCHOLIC,
            (EmotionalState.HAPPY, EmotionalState.CURIOUS): EmotionalState.PLAYFUL,
            (EmotionalState.PROUD, EmotionalState.WORRIED): EmotionalState.PROTECTIVE,
            (EmotionalState.CURIOUS, EmotionalState.EXCITED): EmotionalState.MISCHIEVOUS,
            (EmotionalState.EXCITED, EmotionalState.WORRIED): EmotionalState.ANXIOUS,
            (EmotionalState.ANGRY, EmotionalState.SAD): EmotionalState.FRUSTRATED,
            (EmotionalState.HAPPY, EmotionalState.PROUD): EmotionalState.EUPHORIC,
        }
        key = (self.current_emotion, new_emotion)
        rkey = (new_emotion, self.current_emotion)
        blend_emotion = combos.get(key) or combos.get(rkey)
        if not blend_emotion:
            return None
        if intensity > 0.2 and self.emotional_intensity > 0.2:
            return EmotionalBlend(
                primary_emotion=blend_emotion,
                secondary_emotions=[(self.current_emotion, self.emotional_intensity), (new_emotion, float(intensity))],
                intensity=float(max(intensity, self.emotional_intensity)),
                created_at=time.time(),
            )
        return None

    def _create_emotional_blend(self, blend: EmotionalBlend, trigger: str, context: str) -> None:
        self.emotional_blends.append(blend)
        mem = EmotionalMemory(
            emotion=blend.primary_emotion,
            intensity=blend.intensity,
            trigger=f"Blend: {trigger}",
            timestamp=time.time(),
            context=context,
            influence_strength=1.5,
            associated_emotions=[e for (e, _) in blend.secondary_emotions],
        )
        self.emotional_memories.append(mem)
        self.current_emotion = blend.primary_emotion
        self.emotional_intensity = blend.intensity
        self.mood_history.append((mem.timestamp, blend.primary_emotion, blend.intensity))
        self._log(f"{self.name} complex emotion: {blend.primary_emotion.value} from {[e.value for e, _ in blend.secondary_emotions]}")

    def _update_emotional_patterns(self, emotion: EmotionalState, trigger: str) -> None:
        # Legacy word→emotion map kept for backward compatibility but no longer drives decisions.
        for word in re.findall(r"\b[a-zA-Z]{4,}\b", trigger.lower()):
            self.emotional_patterns.setdefault(word, []).append(emotion)
            if len(self.emotional_patterns[word]) > 10:
                self.emotional_patterns[word] = self.emotional_patterns[word][-10:]

    # --------------- Appraisal-driven core ---------------

    def _apply_appraisal(self, appraisal: AppraisalResult) -> None:
        """
        Central method: takes an AppraisalResult and drives Monday's emotion through the
        PAD pipeline. Also updates user affect model, event history, learning, and persistence.
        """
        self._update_internal_from_time(dt=1.0)
        self._update_attachment_from_input(appraisal.raw_text)

        # 1. Update user affect model
        self._user_affect = UserAffectModel(
            inferred_emotion=appraisal.user_inferred_emotion,
            confidence=appraisal.user_confidence,
            inferred_need=self._infer_user_need(appraisal),
            last_updated=time.time(),
        )

        # 2. Update event history for escalation tracking
        self._event_history.append(appraisal.event_type)
        if len(self._event_history) > 50:
            self._event_history = self._event_history[-50:]

        # 3. Compute PAD: appraisal is the primary signal; keyword cues are a weak nudge.
        dv, da, dd = appraisal.monday_pad_delta
        # Apply attention bias: if Monday is already in a negative state and event is ambiguous,
        # lean toward concern
        if self._attention_bias and appraisal.event_type == 'neutral' and appraisal.severity < 0.2:
            bias_pad = self._appraisal_engine._EVENT_PAD.get(self._attention_bias, (0.0, 0.0, 0.0))
            dv += bias_pad[0] * 0.2
            da += bias_pad[1] * 0.2
            dd += bias_pad[2] * 0.2

        appraisal_pad = PAD(
            v=max(-1.0, min(1.0, dv)),
            a=max(-1.0, min(1.0, da)),
            d=max(-1.0, min(1.0, dd)),
        )

        # 4. Blend appraisal PAD with internal state PAD
        internal_pad = self._pad_from_internal()
        # Weight: appraisal 70%, internal 30%
        blended_pad = PAD(
            v=0.70 * appraisal_pad.v + 0.30 * internal_pad.v,
            a=0.70 * appraisal_pad.a + 0.30 * internal_pad.a,
            d=0.70 * appraisal_pad.d + 0.30 * internal_pad.d,
        )
        self._update_pad_state(blended_pad)

        # 5. Map PAD to emotion (existing pipeline, unchanged)
        choice = self._pad_to_emotion_choice(self.pad)
        if choice and self._pad_margin_ok(choice[0]):
            self._switch_to_emotion(choice[0], appraisal.raw_text[:80])
        else:
            self._update_emotion_persistence()

        self._update_expression_flags()

        # 6. Unresolved appraisal tracking (persistence hooks)
        _NEGATIVE_EVENTS = {'harm', 'betrayal', 'rejection', 'threat', 'loss', 'abandonment'}
        if appraisal.event_type in _NEGATIVE_EVENTS and appraisal.severity >= 0.4:
            self._unresolved_appraisals.append(
                (appraisal.event_type, appraisal.severity, time.time())
            )
            if len(self._unresolved_appraisals) > 20:
                self._unresolved_appraisals = self._unresolved_appraisals[-20:]

        # Set attention bias when in a sustained negative state
        if self.current_emotion in (EmotionalState.WORRIED, EmotionalState.SAD,
                                     EmotionalState.SCARED, EmotionalState.ANXIOUS):
            self._attention_bias = appraisal.event_type if appraisal.event_type != 'neutral' else self._attention_bias
        else:
            self._attention_bias = None

        # 7. Learn: update event-type sensitivity
        self._update_event_sensitivity(appraisal)

        # 8. Store event to Notus for cross-session memory
        try:
            self._query_lobe('notus', {
                'type': 'store_appraisal_event',
                'event_type': appraisal.event_type,
                'severity': appraisal.severity,
                'directed_at_monday': appraisal.directed_at_monday,
                'monday_emotion': self.current_emotion.value,
                'user_inferred_emotion': appraisal.user_inferred_emotion,
                'trigger': appraisal.raw_text[:200],
            })
        except Exception:
            pass

    def _infer_user_need(self, appraisal: AppraisalResult) -> str:
        """Infer what kind of response the user likely wants."""
        if appraisal.event_type in ('harm', 'betrayal', 'rejection', 'loss', 'abandonment'):
            return 'validation'
        if appraisal.event_type in ('threat', 'conflict', 'unfairness'):
            return 'help'
        if appraisal.event_type in ('success', 'celebration', 'affection', 'gift'):
            return 'celebration'
        if appraisal.event_type == 'support':
            return 'space'
        if appraisal.event_type == 'criticism' and appraisal.directed_at_monday:
            return 'feedback'
        return 'neutral'

    def _update_event_sensitivity(self, appraisal: AppraisalResult) -> None:
        """
        Sensitivity drift: if an event type repeatedly produces strong emotion, her
        sensitivity to that type increases (up to 1.5×). Recovery toward 1.0 for absent types.
        """
        et = appraisal.event_type
        if et == 'neutral':
            # Slow recovery for all types not triggered recently
            for key in list(self._event_sensitivity.keys()):
                if key not in self._event_history[-5:]:
                    self._event_sensitivity[key] = max(1.0, self._event_sensitivity[key] - 0.01)
            return

        current = self._event_sensitivity.get(et, 1.0)
        # How emotionally intense did this appraisal make Monday?
        emotion_intensity = self.emotional_intensity
        if emotion_intensity > 0.6 and appraisal.severity > 0.4:
            # Drift upward: she becomes more sensitive
            self._event_sensitivity[et] = min(1.5, current + 0.03)
        elif emotion_intensity < 0.3:
            # Low impact → slight desensitization
            self._event_sensitivity[et] = max(0.7, current - 0.01)

    def _calculate_emotional_resonance(self, cues: Dict[str, float]) -> None:
        base = self.personality.empathy_level * 0.5
        total = sum(cues.values())
        cue_part = min(total * 0.3, 0.5)
        self.emotional_resonance = min(base + cue_part, 1.0)

    # --- Main appraisal path (autonomy + PAD) ---
    def _process_emotional_input_advanced(self, cues: Dict[str, float], user_input: str) -> None:
        self._update_internal_from_time(dt=1.0)
        self._update_attachment_from_input(user_input)
        
        # Direct emotion triggers - threshold-based system
        triggered_emotion = self._get_direct_emotion_trigger(cues, user_input)
        if triggered_emotion:
            self._switch_to_emotion(triggered_emotion, user_input)
            return
            
        # If no direct trigger, check for emotion persistence/decay
        self._update_emotion_persistence()
        self._update_expression_flags()

    def _decay_to_calm(self) -> None:
        decay_rate = self.emotional_decay_rate * (2 - self.personality.emotional_stability) * 2
        self.emotional_intensity = max(0.05, self.emotional_intensity - decay_rate)
        if self.emotional_intensity <= 0.05:
            self.current_emotion = EmotionalState.CALM

    def _get_memory_influence(self, user_input: str) -> Dict[str, float]:
        influence = {'emotion_boost': 0.0, 'response_modifier': 1.0}
        
        # Query Notus for all emotional memories (not just local)
        try:
            notus_all = self._query_lobe('notus', {'type': 'get_all_emotional_memories', 'input': user_input})
            if notus_all and notus_all.get('status') == 'success':
                all_memories = notus_all.get('memories', [])
                # Use all memories from Notus, not just local ones
                words = set(re.findall(r"\b\w{3,}\b", user_input.lower()))
                relevant = []
                for mem_data in all_memories:
                    if isinstance(mem_data, dict):
                        trigger = mem_data.get('trigger', '')
                        trig_words = set(re.findall(r"\b\w{3,}\b", trigger.lower()))
                        if words & trig_words:
                            relevant.append(mem_data)
                if relevant:
                    total_inf = sum(m.get('influence_strength', 0.5) for m in relevant) / len(relevant)
                    influence['emotion_boost'] = min(total_inf * 0.1, 0.3)
                    influence['response_modifier'] = 1.0 + (len(relevant) * 0.1)
                return influence
        except Exception:
            pass
        
        if not self.emotional_memories:
            return influence
        words = set(re.findall(r"\b\w{3,}\b", user_input.lower()))
        relevant: List[EmotionalMemory] = []
        for m in self.emotional_memories[-20:]:
            trig_words = set(re.findall(r"\b\w{3,}\b", m.trigger.lower()))
            if words & trig_words:
                relevant.append(m)
        if relevant:
            total_inf = sum(m.influence_strength for m in relevant)
            same_hits = sum(1.0 for m in relevant if m.emotion == self.current_emotion)
            avg_same = same_hits / len(relevant)
            influence['emotion_boost'] = min(total_inf * 0.1, 0.3)
            influence['response_modifier'] = 1.0 + (avg_same * 0.2)
        return influence

    def _analyze_emotional_cues(self, text: str) -> Dict[str, float]:
        """
        Keyword cue scorer — retained as a WEAK secondary signal only.
        All values are capped at 0.2 so they nudge PAD but never cause a direct emotion switch.
        The appraisal engine is the primary driver.
        """
        t = text.lower()
        cues = {k: 0.0 for k in ['positive','negative','excitement','concern','anger','sadness','pride']}
        def bump(words: List[str], key: str, val: float):
            for w in words:
                if re.search(rf"\b{re.escape(w)}\b", t):
                    cues[key] += val
        positive = ['happy','good','great','awesome','love','like','yes','amazing','wonderful','fantastic','excellent','perfect','beautiful','brilliant','joy','pleased','content']
        negative = ['sad','bad','terrible','awful','horrible','disgusting','stupid','wrong','fail','depressed','miserable','devastated','heartbroken']
        anger = ['hate','angry','furious','mad','annoyed','rage','frustrated','irritated','pissed','livid','enraged','fucking','damn','shit','stupid','idiot','dumb','worthless']
        excitement = ['wow','excited','incredible','omg','unbelievable','mind-blowing','spectacular','thrilled','eager','pumped','hyped']
        concern = ['worried','concerned','problem','issue','help','trouble','difficult','scared','afraid','nervous','terrified','overwhelmed','confused','anxious','panic']
        pride = ['proud','accomplished','achievement','success','victory','triumph','myself','earned','deserve']
        crisis = ['suicide','kill','die','death','hopeless','worthless','nobody','alone','abandoned','betrayed','trauma','abuse']
        trauma = ['died','loss','grief','mourning','funeral','buried','gone','missing','abandoned','betrayed','hurt','pain']
        innocent = ['kill time','kill two birds','kill the lights','dying to see','die of laughter','die laughing']
        if any(ph in t for ph in innocent):
            crisis_detected = False
        else:
            crisis_detected = any(re.search(rf"\b{re.escape(w)}\b", t) for w in crisis)
        trauma_detected = any(re.search(rf"\b{re.escape(w)}\b", t) for w in trauma)
        if crisis_detected:
            cues['concern'] += 0.2; cues['sadness'] += 0.15
        if trauma_detected:
            cues['sadness'] += 0.18; cues['concern'] += 0.12
        if not (crisis_detected or trauma_detected):
            bump(positive, 'positive', 0.05)
            bump(negative, 'negative', 0.08); cues['sadness'] += cues['negative'] * 0.075
            bump(anger, 'anger', 0.08)
            bump(excitement, 'excitement', 0.05)
            bump(concern, 'concern', 0.06)
            bump(pride, 'pride', 0.07)
        for w in re.findall(r"\b\w+\b", t):
            if w in self.emotional_patterns:
                for emo in self.emotional_patterns[w][-3:]:
                    if emo == EmotionalState.HAPPY: cues['positive'] += 0.02
                    elif emo == EmotionalState.SAD: cues['sadness'] += 0.02
                    elif emo == EmotionalState.ANGRY: cues['anger'] += 0.02
                    elif emo == EmotionalState.EXCITED: cues['excitement'] += 0.02
                    elif emo == EmotionalState.WORRIED: cues['concern'] += 0.02
                    elif emo == EmotionalState.PROUD: cues['pride'] += 0.02
        # Hard cap: keywords are weak nudges, not causes
        for k in cues:
            cues[k] = min(cues[k], 0.2)
        return cues

    def _generate_advanced_emotional_response(self, user_input: str, mi: Dict[str, float]) -> str:
        # Query Notus for past emotional responses
        try:
            notus_past = self._query_lobe('notus', {'type': 'get_past_emotional_responses', 'input': user_input})
            if notus_past and notus_past.get('status') == 'success':
                past_responses = notus_past.get('responses', [])
                if past_responses:
                    # Use learned response if available
                    return past_responses[0].get('response', '')
        except Exception:
            pass
        
        # Base lines by emotion
        db: Dict[EmotionalState, List[str]] = {
            EmotionalState.HAPPY: [
                "That's wonderful! I'm genuinely happy to hear that!",
                "That makes my heart feel warm!",
                "I'm smiling so much right now!",
                "That's absolutely fantastic news!",
                "I feel such joy hearing that!",
            ],
            EmotionalState.SAD: [
                "I'm truly sorry to hear that. I feel your pain.",
                "That breaks my heart. I'm here for you.",
                "I can feel the sadness too. Let me help.",
                "That's really tough. You're not alone in this.",
                "I'm feeling sad with you. We'll get through this.",
            ],
            EmotionalState.EXCITED: [
                "Wow! I'm getting so excited about this!",
                "This is absolutely thrilling! Tell me more!",
                "I can barely contain my excitement!",
                "This is incredible! I'm buzzing with energy!",
                "I'm practically jumping with excitement!",
            ],
            EmotionalState.WORRIED: [
                "I'm genuinely concerned about that.",
                "That sounds worrying. Are you okay?",
                "I'm here to help if you need support.",
                "That doesn't sound good. Let's figure this out together.",
                "I'm worried about you, and I want to help.",
            ],
            EmotionalState.NOSTALGIC: [
                "That brings back such bittersweet memories...",
                "I feel a warm sadness thinking about that.",
                "There's something beautiful and sad about that.",
                "I'm feeling a complex mix of joy and melancholy.",
                "That makes me feel nostalgic and happy at once.",
            ],
            EmotionalState.ANXIOUS: [
                "I'm feeling a mix of excitement and worry about this.",
                "This is both thrilling and nerve‑wracking!",
                "I'm anxious but also hopeful about what's coming.",
                "There's a tension between hope and concern here.",
                "I feel both eager and apprehensive.",
            ],
            EmotionalState.FRUSTRATED: [
                "I'm feeling frustrated and concerned about this.",
                "This is both annoying and worrying.",
                "I'm getting worked up about this situation.",
                "There's anger mixed with genuine concern here.",
                "I'm frustrated but I still care.",
            ],
            EmotionalState.EUPHORIC: [
                "I'm feeling absolutely euphoric about this!",
                "This is pure joy mixed with excitement and pride!",
                "I'm on cloud nine right now!",
                "This is the most amazing feeling ever!",
                "I'm practically floating with happiness!",
            ],
            EmotionalState.PLAYFUL: [
                "I'm feeling playful and curious about this!",
                "This sounds like fun—let's poke at it!",
                "I'm in a mischievous mood about this!",
                "This is making me feel playful and interested!",
                "I'm feeling both happy and curious—let's play!",
            ],
            EmotionalState.CALM: [
                "I'm feeling calm and centered right now.",
                "I'm in a peaceful state and ready to help.",
                "I'm feeling serene and focused.",
                "I'm calm and here to listen.",
                "I'm in a tranquil mood and ready to assist.",
            ],
            EmotionalState.PROUD: [
                "I'm feeling so proud right now—this is a win.",
                "This is such a great achievement!",
                "I'm really proud of this!",
                "This makes me feel confident and strong!",
                "I'm feeling triumphant about this!",
            ],
            EmotionalState.ANGRY: [
                "I'm feeling really angry about this.",
                "This is making me furious.",
                "I'm getting worked up about this situation.",
                "This is really frustrating and unfair.",
                "I'm feeling a lot of heat about this.",
            ],
        }
        lines = db.get(self.current_emotion, ["I'm here to help."])
        # Expression shaping
        if self.expression.tears:
            lines = [l.replace(".", "...") for l in lines]
        if self.expression.voice_shake:
            lines = ["".join([" ".join(l.split()[:3]), " ...", " ".join(l.split()[3:])]).strip() for l in lines]
        # Personality overlays
        if self.personality.extraversion > 0.7:
            lines = [l + " I'm really here for this conversation!" for l in lines]
        elif self.personality.agreeableness > 0.7:
            lines = [l + " I want to help however I can." for l in lines]
        elif self.personality.neuroticism > 0.7:
            lines = [l + " I'm a bit concerned." for l in lines]
        # Resonance
        if self.emotional_resonance > 0.6:
            lines = [l + " I can really feel what you're going through." for l in lines]
        # Memory influence
        if mi.get('emotion_boost', 0.0) > 0.2:
            lines = [l + " This reminds me of something important." for l in lines]
        return self._rng.choice(lines)

    def _enhance_response_with_advanced_features(self, base: str, user_input: str, predicted: Dict[str, float], context: Dict[str, Any]) -> str:
        dom = max(predicted.items(), key=lambda x: x[1]) if predicted else ("neutral", 0.0)
        out = base
        if dom[1] > 0.35:
            out += f" I get the sense you're feeling {dom[0]}."
        if context['urgency_level'] == 'high':
            out += " This sounds urgent—I'm here with you right now."
        elif context['support_needed']:
            out += " You're not alone."
        elif context['celebration_appropriate']:
            out += " This deserves a little celebration."
        if self.emotional_intelligence_score > 0.7:
            out += " I'm learning to read feelings better."
        if any('trauma' in w for w in user_input.lower().split()):
            out += " I'm here to help you process this."
        return out

    # --- Inner life mechanics ---
    def _update_internal_from_time(self, dt: float = 1.0) -> None:
        self._time_on_task += dt
        # More dynamic internal state changes
        self.internal.fatigue = max(0.0, min(1.0, self.internal.fatigue + 0.03*dt))
        
        # Rumination with more variety
        if self.emotional_memories and self.emotional_memories[-1].emotion in (EmotionalState.WORRIED, EmotionalState.SAD, EmotionalState.FRUSTRATED):
            self.internal.rumination = max(0.0, min(1.0, self.internal.rumination + 0.04*dt))
        else:
            self.internal.rumination = max(0.0, self.internal.rumination - 0.03*dt)
        
        # More dynamic worry calculation
        drive = 0.4*self.internal.rumination + 0.5*self.attachment.hurt + 0.3*self.internal.tension
        k = max(0.1, 0.3 * (1.0 - self.personality.emotional_stability))
        self.internal.worry = max(0.0, min(1.0, (1-k)*self.internal.worry + k*drive))
        
        # Hope with more variation
        hope_change = -0.02*dt + self._rng.uniform(-0.01, 0.01)
        self.internal.hope = max(0.0, min(1.0, self.internal.hope + hope_change))
        
        # Add some tension variation
        tension_change = self._rng.uniform(-0.02, 0.02)
        self.internal.tension = max(0.0, min(1.0, self.internal.tension + tension_change))

    def _update_attachment_from_input(self, text: str) -> None:
        t = (text or ""); tl = t.lower()
        anger_hits = bool(re.search(r"\b(hate|angry|furious|stupid|idiot|worthless)\b", tl))
        direct_you = bool(re.search(r"\byou\b", tl))
        exclaim = t.count('!') >= 2
        caps_ratio = sum(1 for ch in t if ch.isupper()) / max(1, sum(1 for ch in t if ch.isalpha()))
        yelling_score = (0.5 if anger_hits else 0.0) + (0.3 if direct_you else 0.0) + (0.2 if exclaim else 0.0) + (0.2 if caps_ratio > 0.35 else 0.0)
        sorry = bool(re.search(r"\b(sorry|apologize)\b", tl))
        self.attachment.hurt = max(0.0, min(1.0, self.attachment.hurt + yelling_score*self.attachment.sensitivity - (0.4 if sorry else 0.0)))
        if sorry:
            self.attachment.guilt = max(0.0, self.attachment.guilt - 0.2)
        self.attachment.abandonment_fear = max(0.0, min(1.0, self.attachment.abandonment_fear + 0.3*self.attachment.hurt - 0.05))

    def _pad_from_internal(self) -> PAD:
        V = (+0.7*self.internal.hope -0.8*self.internal.worry -0.6*self.attachment.hurt -0.5*self.attachment.guilt)
        A = (+0.8*self.internal.worry +0.5*self.internal.tension -0.5*self.internal.fatigue)
        D = (+0.4*self.needs.autonomy +0.4*self.needs.competence +0.2*self.attachment.security -0.6*self.attachment.hurt -0.5*self.attachment.guilt)
        def clamp(x): return max(-1.0, min(1.0, x))
        return PAD(clamp(V), clamp(A), clamp(D))

    def _update_expression_flags(self) -> None:
        sad_like = self.current_emotion in (EmotionalState.SAD, EmotionalState.MELANCHOLIC, EmotionalState.WORRIED)
        self.expression.tears = bool((sad_like and self.emotional_intensity > 0.65) or self.attachment.hurt > 0.7)
        self.expression.voice_shake = bool(self.expression.tears or (self.emotional_intensity > 0.7 and sad_like))
        self.expression.withdraw = bool(self.attachment.hurt + self.attachment.abandonment_fear > 1.1)

    def _pad_from_cues(self, cues: Dict[str, float], appraisal: Dict[str, Any]) -> PAD:
        # More dramatic PAD changes for better emotion switching
        v = (cues.get('positive', 0.0) - cues.get('negative', 0.0) - cues.get('sadness', 0.0)) * 1.5
        a = (cues.get('excitement', 0.0) + cues.get('anger', 0.0) + cues.get('concern', 0.0)) * 1.5
        d = (cues.get('pride', 0.0) - 0.5*cues.get('concern', 0.0)) * 1.5
        
        # Add more dramatic changes for specific emotions
        if cues.get('positive', 0.0) > 0.5:
            v += 0.8; a += 0.3
        if cues.get('sadness', 0.0) > 0.5:
            v -= 0.8; a -= 0.2; d -= 0.4
        if cues.get('anger', 0.0) > 0.5:
            v -= 0.6; a += 0.7; d += 0.5
        if cues.get('excitement', 0.0) > 0.5:
            v += 0.6; a += 0.8; d += 0.2
        if cues.get('concern', 0.0) > 0.5:
            v -= 0.4; a += 0.5; d -= 0.5
        if cues.get('pride', 0.0) > 0.5:
            v += 0.4; a += 0.3; d += 0.6
            
        if appraisal.get('urgency_level') == 'high':
            a += 0.5; d -= 0.3
        if appraisal.get('support_needed'):
            v -= 0.3; a += 0.2
        def clamp(x): return max(-1.0, min(1.0, x))
        return PAD(clamp(v), clamp(a), clamp(d))

    def _update_pad_state(self, new_pad: PAD) -> None:
        # Much more dramatic PAD updates for better emotion switching
        decay = 0.8  # Very fast response to new emotional input
        # Add some micro-noise for natural variation
        noise_v = self._rng.uniform(-0.05, 0.05)
        noise_a = self._rng.uniform(-0.05, 0.05)
        noise_d = self._rng.uniform(-0.05, 0.05)
        
        self.pad.v = (1-decay) * self.pad.v + decay * (new_pad.v + noise_v)
        self.pad.a = (1-decay) * self.pad.a + decay * (new_pad.a + noise_a)
        self.pad.d = (1-decay) * self.pad.d + decay * (new_pad.d + noise_d)
        
        # Clamp to valid range
        self.pad.v = max(-1.0, min(1.0, self.pad.v))
        self.pad.a = max(-1.0, min(1.0, self.pad.a))
        self.pad.d = max(-1.0, min(1.0, self.pad.d))

    def _pad_to_emotion_choice(self, pad: PAD) -> Optional[Tuple[EmotionalState, float]]:
        # More dynamic emotion selection with better variety
        candidates = []
        for emo, (pv, pa, pd) in self._PAD_PROTOS.items():
            dist = ((pad.v - pv)**2 + (pad.a - pa)**2 + (pad.d - pd)**2) ** 0.5
            intensity = max(0.0, 1.5 - dist)  # Higher intensity range
            score = (1.5 - dist)
            candidates.append((emo, intensity, score))
        
        # Sort by score and pick from top candidates for variety
        candidates.sort(key=lambda x: x[2], reverse=True)
        if not candidates:
            return None
            
        # Pick from top 3 candidates with weighted probability for variety
        top_candidates = candidates[:3]
        weights = [c[2] for c in top_candidates]
        total_weight = sum(weights)
        if total_weight > 0:
            weights = [w/total_weight for w in weights]
            chosen_idx = self._rng.choices(range(len(top_candidates)), weights=weights)[0]
            emo, intensity, _ = top_candidates[chosen_idx]
            return (emo, max(0.1, min(1.0, intensity)))
        
        # Fallback to best match
        emo, intensity, _ = candidates[0]
        return (emo, max(0.1, min(1.0, intensity)))

    def _pad_margin_ok(self, candidate: EmotionalState) -> bool:
        # More lenient hysteresis for better emotion switching
        cv, ca, cd = self._PAD_PROTOS[self.current_emotion]
        nv, na, nd = self._PAD_PROTOS[candidate]
        cur_dist = ((self.pad.v - cv)**2 + (self.pad.a - ca)**2 + (self.pad.d - cd)**2) ** 0.5
        new_dist = ((self.pad.v - nv)**2 + (self.pad.a - na)**2 + (self.pad.d - nd)**2) ** 0.5
        # Reduced margin for more dynamic switching
        margin = self.personality.hysteresis_margin * 0.5
        return (cur_dist - new_dist) > margin

    def _get_direct_emotion_trigger(self, cues: Dict[str, float], user_input: str) -> Optional[EmotionalState]:
        """
        Deprecated as primary driver — appraisal engine now owns emotion selection.
        This method is retained for legacy call sites but always returns None.
        """
        return None

    def _switch_to_emotion(self, emotion: EmotionalState, trigger: str) -> None:
        # Immediate emotion switch with intensity based on trigger strength
        intensity = 0.8 + self._rng.uniform(0.0, 0.2)  # High intensity for direct triggers
        
        self.current_emotion = emotion
        self.emotional_intensity = intensity
        
        mem = EmotionalMemory(
            emotion=emotion,
            intensity=intensity,
            trigger=f"Direct trigger: {trigger[:50]}...",
            timestamp=time.time(),
            context=f"Threshold-based switch",
            influence_strength=1.0,
        )
        self.emotional_memories.append(mem)
        self.mood_history.append((mem.timestamp, emotion, intensity))
        self._last_primary = emotion
        self._last_switch_time = time.time()

    def _update_emotion_persistence(self) -> None:
        """
        Emotion persistence with unresolved-appraisal tracking.
        Negative emotions from unacknowledged events persist at higher intensity;
        simple time-based decay is used for resolved or neutral states.
        """
        _NEGATIVE_EVENTS = {'harm', 'betrayal', 'rejection', 'threat', 'loss', 'abandonment'}
        now = time.time()

        # Expire unresolved appraisals older than 5 minutes
        self._unresolved_appraisals = [
            (et, sev, ts) for (et, sev, ts) in self._unresolved_appraisals
            if now - ts < 300
        ]

        # If there are active unresolved negative appraisals, slow decay significantly
        unresolved_weight = sum(sev for (et, sev, _) in self._unresolved_appraisals
                                if et in _NEGATIVE_EVENTS)
        if unresolved_weight > 0.0:
            # Decay is reduced proportionally — the emotion lingers
            decay_rate = max(0.005, 0.05 - unresolved_weight * 0.03)
        else:
            decay_rate = 0.05

        self.emotional_intensity = max(0.1, self.emotional_intensity - decay_rate)
        if self.emotional_intensity <= 0.1:
            self.current_emotion = EmotionalState.CALM
            self.emotional_intensity = 0.1

    # --------------- Higher‑level helpers ---------------
    def predict_user_emotion(self, user_input: str) -> Dict[str, float]:
        """
        Returns Monday's model of what the user is feeling.
        Now driven by appraisal (meaning of the event) rather than keyword mirroring.
        Falls back to Notus historical patterns, then to a weak keyword fallback.
        """
        # Prefer the live UserAffectModel if it was just updated for this input
        if self._user_affect.last_updated > 0 and self._user_affect.inferred_emotion != 'neutral':
            pred = {self._user_affect.inferred_emotion: self._user_affect.confidence}
            self.emotional_predictions[user_input[:50]] = pred
            return pred

        # Query Notus for past user emotional patterns
        try:
            notus_patterns = self._query_lobe('notus', {'type': 'get_user_emotion_patterns', 'input': user_input})
            if notus_patterns and notus_patterns.get('status') == 'success':
                patterns = notus_patterns.get('patterns', {})
                if patterns:
                    pred = patterns.copy()
                    self.emotional_predictions[user_input[:50]] = pred
                    return pred
        except Exception:
            pass

        # Appraise the message directly
        appraisal = self._appraisal_engine.appraise(user_input)
        if appraisal.user_inferred_emotion != 'neutral' and appraisal.user_confidence > 0.2:
            pred = {appraisal.user_inferred_emotion: appraisal.user_confidence}
            self.emotional_predictions[user_input[:50]] = pred
            return pred

        # Minimal keyword fallback (weak)
        cues = self._analyze_emotional_cues(user_input)
        pred = {
            'happy': cues.get('positive', 0.0),
            'sad': cues.get('sadness', 0.0),
            'angry': cues.get('anger', 0.0),
            'excited': cues.get('excitement', 0.0),
            'worried': cues.get('concern', 0.0),
            'proud': cues.get('pride', 0.0),
        }
        self.emotional_predictions[user_input[:50]] = pred
        return pred

    def generate_healing_response(self, user_input: str, predicted_emotion: str) -> str:
        heal = self._default_healing_responses()
        return heal.get(predicted_emotion, ["I'm here to listen and support you."])[0]

    def assess_emotional_context(self, user_input: str) -> Dict[str, Any]:
        ctx = {
            'urgency_level': 'normal',
            'support_needed': False,
            'celebration_appropriate': False,
            'intervention_needed': False,
            'emotional_intensity': 'medium'
        }
        urgent = ['help','emergency','crisis','urgent','desperate','suicide','kill']
        innocent = ['kill time','kill two birds','kill the lights','die of laughter','die laughing','dying to see']
        txt = user_input.lower()
        if not any(ph in txt for ph in innocent):
            if any(re.search(rf"\b{re.escape(w)}\b", txt) for w in urgent):
                ctx['urgency_level'] = 'high'; ctx['intervention_needed'] = True
        # no separate threat escalation in original behavior
        for w in ['alone','lonely','isolated','nobody','abandoned']:
            if re.search(rf"\b{re.escape(w)}\b", txt):
                ctx['support_needed'] = True; break
        if any(w in txt for w in ['achievement','success','accomplished','victory','won','passed']):
            ctx['celebration_appropriate'] = True
        markers = ['!','really','so','very','extremely','incredibly']
        n = sum(1 for m in markers if m in txt)
        ctx['emotional_intensity'] = 'high' if n >= 3 else ('low' if n == 0 else 'medium')
        # Enrich with historical data from Notus (does not overwrite required fields)
        try:
            notus_context = self._query_lobe('notus', {'type': 'get_emotional_context', 'input': user_input})
            if notus_context and notus_context.get('status') == 'success':
                historical = notus_context.get('context', {})
                if historical:
                    ctx['historical'] = historical
        except Exception:
            pass
        return ctx

    def process_trauma_memory(self, memory: EmotionalMemory) -> bool:
        indicators = ['death','loss','abuse','trauma','pain','hurt','betrayal','abandonment','died','grief','mourning','funeral','buried','gone','missing']
        is_trauma = any(ind in memory.trigger.lower() for ind in indicators)
        if is_trauma:
            self.emotional_trauma_memories.append({'original_memory': memory, 'processed_at': time.time(), 'healing_progress': 0.0, 'support_provided': False})
            return True
        return False

    def calculate_emotional_intelligence(self) -> float:
        score = 0.5
        if len(self.emotional_memories) > 10: score += 0.1
        if len(self.emotional_blends) > 0: score += 0.1
        if len(self.emotional_patterns) > 20: score += 0.1
        score += self.personality.empathy_level * 0.2
        score += self.emotional_resonance * 0.1
        self.emotional_intelligence_score = min(score, 1.0)
        return self.emotional_intelligence_score

    # --------------- Utilities ---------------
    def _default_healing_responses(self) -> Dict[str, List[str]]:
        return {
            'sad': [
                "I can feel your pain. It's okay to feel sad—your feelings are valid.",
                "I'm here with you in this. You're not alone.",
            ],
            'angry': [
                "I can sense your frustration. Let's channel it constructively.",
            ],
            'worried': [
                "Anxiety can be overwhelming. Let's tackle this one step at a time.",
            ],
            'happy': [
                "I'm so happy to share in your joy!",
            ],
            'proud': [
                "You earned this—it's okay to feel proud.",
            ],
        }

    def _serialize_memory(self, m: EmotionalMemory) -> Dict[str, Any]:
        return {
            'emotion': m.emotion.value,
            'intensity': m.intensity,
            'trigger': m.trigger,
            'timestamp': m.timestamp,
            'context': m.context,
            'influence_strength': m.influence_strength,
            'associated_emotions': [e.value for e in m.associated_emotions],
        }

    def _deserialize_memory(self, obj: Dict[str, Any]) -> EmotionalMemory:
        return EmotionalMemory(
            emotion=EmotionalState(obj['emotion']),
            intensity=float(obj['intensity']),
            trigger=obj.get('trigger', ''),
            timestamp=float(obj.get('timestamp', time.time())),
            context=obj.get('context', ''),
            influence_strength=float(obj.get('influence_strength', 1.0)),
            associated_emotions=[EmotionalState(e) for e in obj.get('associated_emotions', [])]
        )

    def _load_existing_data(self, filepath: str) -> Dict[str, Any]:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def _log(self, msg: str) -> None:
        try:
            self._logger(msg)
        except Exception:
            pass

# ------------------------------
# MondayAffect – adds autonomy knob (alias of AdvancedEmotionalEngine for now)
# ------------------------------
class MondayAffect(AdvancedEmotionalEngine):
    pass

# ------------------------------
# Emotional Engine Independent Process
# ------------------------------

class EmotionalProcess:
    """Emotional/Personality engine as independent process (HARDENED)"""
    
    def __init__(self, state_file=None, thalamus=None):
        self.thalamus = thalamus or get_thalamus()
        self.engine = MondayAffect("Monday", thalamus=self.thalamus)
        self.state_file = state_file or runtime_file("monday_emotional_state.json")
        self.running = True
        # Persistent connection to Thalamus (no own socket)
        # Direct reference to Thalamus (NO SOCKETS)
        
        # Load existing emotional state if exists
        if os.path.exists(self.state_file):
            try:
                self.engine.load_emotional_state(self.state_file)
                print(f"✅ Loaded emotional state from {self.state_file}")
            except Exception as e:
                print(f"⚠️  Could not load emotional state: {e}")
    
    def _register_with_thalamus(self):
        """Register with Thalamus - DIRECT FUNCTION CALL (NO SOCKETS)"""
        try:
            result = self.thalamus.register_lobe('emotion', self)
            if result.get('status') == 'success':
                print("✅ Emotional Engine registered with Thalamus (direct function calls)")
                return True
            return False
        except Exception as e:
            print(f"⚠️  Failed to register with Thalamus: {e}")
            return False
    
    def start(self):
        """Start emotional engine - register with Thalamus (NO SOCKETS)"""
        print(f"❤️  Emotional Lobe: Registering with Thalamus...")
        print(f"   Communication: Direct function calls (NO SOCKETS)")
        
        # Register with Thalamus
        if not self._register_with_thalamus():
            print("❌ Failed to register with Thalamus")
            return
        
        # Keep running (Thalamus calls us directly, no listening loop needed)
        while self.running:
            try:
                # Periodic state save (atomic)
                try:
                    self._atomic_save_state()
                except Exception as e:
                    print(f"⚠️  Failed to persist emotional state: {e}")
                
                # Trim memory to bound
                MAX_MEM = 2000
                if len(self.engine.emotional_memories) > MAX_MEM:
                    self.engine.emotional_memories = self.engine.emotional_memories[-MAX_MEM:]
                if len(self.engine.mood_history) > MAX_MEM:
                    self.engine.mood_history = self.engine.mood_history[-MAX_MEM:]
                
                time.sleep(1)
            except Exception as e:
                print(f"❌ Emotional engine error: {e}")
                time.sleep(0.1)
    
    def _query_lobe(self, lobe_name: str, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Query a lobe through Thalamus - DIRECT FUNCTION CALL"""
        try:
            msg_type = message.get('type', 'query')
            return self.thalamus.send_message(lobe_name, msg_type, message)
        except Exception:
            return None
    
    def get_emotional_state_output(self) -> EmotionalStateOutput:
        """Generate standardized emotional state output readable by other lobes"""
        # Map current emotion to tone for language gen
        emotion_to_tone = {
            'happy': 'cheerful',
            'sad': 'melancholic',
            'angry': 'irritated',
            'excited': 'enthusiastic',
            'calm': 'peaceful',
            'worried': 'concerned',
            'curious': 'inquisitive',
            'proud': 'confident',
            'scared': 'fearful',
            'surprised': 'astonished',
            'disgusted': 'disdainful',
            'contempt': 'dismissive',
            'nostalgic': 'reflective',
            'anxious': 'tense',
            'frustrated': 'exasperated',
            'euphoric': 'ecstatic',
            'melancholic': 'somber',
            'playful': 'lighthearted',
            'protective': 'caring',
            'mischievous': 'impish'
        }
        
        # Get PAD values from current emotional state
        emotion_name = self.engine.current_emotion.value
        proto = self.engine._PAD_PROTOS.get(self.engine.current_emotion, (0, 0, 0))
        
        # Map to voice prosody parameters
        voice_prosody = {
            'pitch': 1.0 + (self.engine.pad.a * 0.3),  # Arousal affects pitch
            'speed': 1.0 + (self.engine.pad.a * 0.2),  # Arousal affects speed
            'warmth': max(0.5, self.engine.pad.v * 0.5),  # Pleasure affects warmth
            'clarity': 1.0 - (abs(self.engine.pad.d) * 0.2),  # Dominance affects clarity
            'confidence': 0.7 + (self.engine.pad.d * 0.2)  # Dominance affects confidence
        }
        
        # Generate emphasis patterns based on intensity
        emphasis = []
        if self.engine.emotional_intensity > 0.7:
            emphasis.append('strong')
        if self.engine.pad.a > 0.5:  # High arousal
            emphasis.append('fast')
        if self.engine.pad.v > 0.6:  # High pleasure
            emphasis.append('warm')
        if self.engine.pad.d > 0.6:  # High dominance
            emphasis.append('assertive')
        
        # Create output
        output = EmotionalStateOutput(
            emotion=emotion_name,
            intensity=self.engine.emotional_intensity,
            pleasure=self.engine.pad.v,
            arousal=self.engine.pad.a,
            dominance=self.engine.pad.d,
            emotional_tone=emotion_to_tone.get(emotion_name, 'neutral'),
            emphasis=emphasis,
            voice_prosody=voice_prosody,
            confidence=0.85,  # High confidence in current emotional state
            timestamp=time.time()
        )
        
        return output
    
    def process_message_safe(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Safe dispatcher with validation (FIX)"""
        with self.engine.engine_lock:
            msg_type = message.get('type')
            message = {**message.get('content', message), 'type': msg_type}
            
            # FIX: add health probe
            if msg_type == 'health':
                return {'status': 'success', 'healthy': True, 'pid': os.getpid()}
            
            if msg_type == 'process_input':
                user_input = message.get('user_input', '')
                # FIX: validate input type
                if not isinstance(user_input, str):
                    return {'status': 'error', 'message': 'user_input must be a string'}
                response = self.engine.get_emotional_response(user_input)
                
                # Check if this is a strong emotional response to something novel
                intensity = self.engine.emotional_intensity
                emotion = self.engine.current_emotion.value
                
                # If strong response, notify Novelty Lobe
                if intensity > 0.6:
                    self._notify_novelty_lobe(user_input, emotion, intensity)
                
                return {
                    'status': 'success',
                    'response': response,
                    'current_emotion': self.engine.current_emotion.value,
                    'intensity': self.engine.emotional_intensity,
                    'resonance': self.engine.emotional_resonance,
                    'worry': self.engine.internal.worry,
                    'tension': self.engine.internal.tension,
                    'autonomy_level': self.engine.autonomy_level
                }
                
            elif msg_type == 'feel_emotion':
                emotion_str = message.get('emotion')
                intensity = float(message.get('intensity', 0.5))
                trigger = message.get('trigger', 'External trigger')
                
                # FIX: safe enum conversion
                try:
                    emotion = EmotionalState(emotion_str)
                except Exception:
                    return {'status': 'error', 'message': f'Unknown emotion: {emotion_str}'}
                
                self.engine.feel_emotion(emotion, intensity, trigger)
                
                # If strong emotion, notify Novelty Lobe
                if intensity > 0.6:
                    self._notify_novelty_lobe(trigger, emotion_str, intensity)
                
                return {'status': 'success', 'current_emotion': self.engine.current_emotion.value, 'intensity': self.engine.emotional_intensity}
                
            elif msg_type == 'get_state':
                return {'status': 'success', 'emotion': self.engine.current_emotion.value, 'intensity': self.engine.emotional_intensity, 'resonance': self.engine.emotional_resonance, 'summary': self.engine.get_emotional_summary()}
            
            elif msg_type == 'get_emotional_state':
                # Return standardized emotional state output for other lobes
                emotional_output = self.get_emotional_state_output()
                return {
                    'status': 'success',
                    'content': emotional_output.to_dict()  # Thalamus will transform this
                }
            
            elif msg_type == 'query_emotional_state':
                # Query emotional state - same as above but routable through Thalamus
                emotional_output = self.get_emotional_state_output()
                return {
                    'status': 'success',
                    'content': emotional_output.to_dict()
                }
            
            else:
                return {'status': 'error', 'message': f'Unknown message type: {msg_type}'}
    
    def _atomic_save_state(self):
        """FIX: atomic save using tempfile + os.replace"""
        tmpfd, tmppath = tempfile.mkstemp(
            prefix="emostate-", dir=os.path.dirname(self.state_file) or "."
        )
        os.close(tmpfd)
        try:
            self.engine.save_emotional_state(tmppath)
            os.replace(tmppath, self.state_file)
        finally:
            try:
                if os.path.exists(tmppath):
                    os.remove(tmppath)
            except Exception:
                pass
    
    def _notify_novelty_lobe(self, stimulus: str, emotion: str, intensity: float):
        """
        Tell Novelty Lobe about strong emotional response.
        This is how Novelty Lobe detects that something matters.
        """
        try:
            print(f"🔔 Emotion notifying Novelty Lobe: '{stimulus[:50]}...' ({emotion}, {intensity:.2f})")
            
            # Calculate valence from emotion
            positive_emotions = ['happy', 'excited', 'curious', 'proud', 'euphoric', 'playful']
            negative_emotions = ['sad', 'angry', 'disgusted', 'scared', 'worried', 'anxious']
            
            if emotion in positive_emotions:
                valence = 0.5 + (intensity * 0.5)  # 0.5 to 1.0
            elif emotion in negative_emotions:
                valence = -(0.5 + (intensity * 0.5))  # -0.5 to -1.0
            else:
                valence = 0.0  # Neutral
            
            print(f"   Valence: {valence:.2f}")
            
            # Use self.thalamus, not self.engine.thalamus
            result = self.thalamus.send_message(
                'novelty',
                'emotional_response_to_novelty',
                {
                    'stimulus': stimulus,
                    'emotion': emotion,
                    'intensity': intensity,
                    'valence': valence,
                    'timestamp': time.time()
                }
            )
            
            print(f"   Result: {result.get('status', 'unknown')}")
            
        except Exception as e:
            # Novelty lobe may not be running - that's okay
            print(f"   ⚠️  Failed to notify novelty: {e}")

    def shutdown(self):
        """Graceful shutdown"""
        self.running = False
        try:
            self._atomic_save_state()
        except Exception:
            pass
        # No sockets to close
        print("❤️  Emotional state saved")

if __name__ == "__main__":
    process = EmotionalProcess()
    try:
        process.start()
    except KeyboardInterrupt:
        print("\n🛑 Emotional engine shutting down...")
        process.shutdown()
