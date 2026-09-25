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
from collections import deque
from typing import Dict, List, Optional, Tuple, Any, Callable
from threading import Lock
from thalamus import get_thalamus
from monday_core_affect import MondayCoreAffect, SelfImpact, label_from_va, THIN_LABELS

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
    RELIEVED = "relieved"
    EXHAUSTED = "exhausted"
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

@dataclass
class InternalEventAppraisal:
    """Metadata for an autonomously recalled memory or thought passed to the appraisal pipeline."""
    source: str                            # "memory", "thought", "rumination", "association"
    content: str                           # Text passed to AppraisalEngine.appraise()
    memory_age_seconds: float              # How old the memory is (0 = fresh thought)
    resolved: bool                         # Was the underlying situation resolved?
    prior_appraisal_event_type: Optional[str]  # event_type from first appraisal, or None
    relevance: float                       # 0..1 caller's estimate of present relevance


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
    # Explicit self-report (I'm happy/angry/…) when present; may differ from event mapping
    explicit_user_emotion: Optional[str] = None
    # Contrastive current-state clause authored event and/or user emotion
    contrast_affected: bool = False
    # Emotion implied by event_type alone (before explicit override)
    event_inferred_emotion: str = 'neutral'
    # Continuity / ownership markers (per-utterance; not a redesign)
    temporal: str = 'current'  # current | historical | returning
    third_party_emotion: Optional[str] = None
    resolution_signal: bool = False
    quoted_affect: bool = False

@dataclass
class UserAffectModel:
    """Monday's model of what the user is feeling, kept separate from Monday's own emotion."""
    inferred_emotion: str = 'neutral'
    confidence: float = 0.0
    inferred_need: str = 'neutral'   # 'validation','help','celebration','space','neutral'
    last_updated: float = 0.0
    # Multi-turn continuity (USER only — never written into Monday INTERNAL enum)
    previous_emotion: str = 'neutral'
    temporal: str = 'current'  # current | historical | returning
    last_event_type: str = 'neutral'
    third_party_emotion: Optional[str] = None

@dataclass
class EmotionalUnderstanding:
    """Combined text-understanding result for an emotional NL event.
    LEGACY container. Live mood does not use this pipeline (CoreAffect + SelfImpact).
    """
    appraisal: AppraisalResult
    semantic_event: Optional[str] = None
    semantic_emotion: Optional[str] = None
    semantic_confidence: float = 0.0
    semantic_used: bool = False
    keyword_cues: Dict[str, float] = field(default_factory=dict)
    primary_source: str = 'neutral'  # appraisal|semantic|keyword|neutral
    inferred_emotion: str = 'neutral'
    event_type: str = 'neutral'
    severity: float = 0.0
    confidence: float = 0.0
    negation_affected: bool = False
    contrast_affected: bool = False
    explicit_emotion: Optional[str] = None
    appraisal_inferred_emotion: str = 'neutral'  # event-type mapping only
    final_appraisal: Optional[AppraisalResult] = None

class AppraisalEngine:
    """
    LEGACY STUB (2026-09-25 emotion honesty cleanup).

    Phrase→event classifier tables and the old appraisal driver were DELETED.
    Live Monday mood is MondayCoreAffect + SelfImpact only
    (see get_emotional_response / appraise_internal_event).

    This class remains only so unused/compat call sites do not crash.
    appraise() fails closed: always returns a neutral AppraisalResult
    with zero monday_pad_delta — never writes her mood.
    """

    # Minimal event-type list for leftover sensitivity maps / persist keys.
    # Not a live driver. No phrase tables.
    _EVENT_PAD = {et: (0.0, 0.0, 0.0) for et in (
        'harm', 'betrayal', 'rejection', 'threat', 'unfairness', 'loss',
        'success', 'affection', 'gift', 'conflict', 'criticism', 'abandonment',
        'support', 'celebration', 'neutral',
    )}
    _USER_EMOTION_BY_EVENT = {et: 'neutral' for et in _EVENT_PAD}

    def appraise(self, text: str, relationship_history=None,
                 sensitivity_map=None) -> "AppraisalResult":
        """Fail closed: neutral appraisal, zero PAD delta. Not a mood driver."""
        return AppraisalResult(
            event_type='neutral',
            severity=0.0,
            directed_at_monday=False,
            directed_at_user=False,
            third_party=False,
            negated=False,
            sarcasm_likely=False,
            raw_text=text or '',
            monday_pad_delta=(0.0, 0.0, 0.0),
            user_inferred_emotion='unknown',
            user_confidence=0.0,
            explicit_user_emotion=None,
            contrast_affected=False,
            event_inferred_emotion='neutral',
            temporal='current',
            third_party_emotion=None,
            resolution_signal=False,
            quoted_affect=False,
        )

    # Thin no-op helpers kept for rare leftover call sites (not classifiers).
    def _strip_quoted_speech(self, tl: str) -> str:
        return tl or ''

    def _mask_hypotheticals(self, tl: str) -> str:
        return tl or ''

    def _has_third_party_person_ref(self, tl: str) -> bool:
        return False

    def _compute_monday_pad(self, event_type: str, severity: float,
                            directed_at_monday: bool = False,
                            directed_at_user: bool = False):
        return (0.0, 0.0, 0.0)


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
        # LIVE mood substrate (design lock 2026-09-25). Classifiers no longer drive her mood.
        self.core_affect = MondayCoreAffect()
        self._self_impact = SelfImpact()
        self._last_self_impact_reason: str = "init"
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
            EmotionalState.RELIEVED:( 0.55, -0.25,  0.35),
            EmotionalState.EXHAUSTED:(-0.20, -0.55, -0.25),
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
        self._last_appraisal: Optional[AppraisalResult] = None
        self._last_understanding: Optional[EmotionalUnderstanding] = None
        # event_type → sensitivity multiplier (learned, starts at 1.0 for all)
        self._event_sensitivity: Dict[str, float] = {et: 1.0 for et in EVENT_TYPES}
        # recent event-type history for escalation detection (last 20)
        self._event_history: List[str] = []
        # unresolved negative appraisal tracking: list of (event_type, severity, timestamp)
        self._unresolved_appraisals: List[Tuple[str, float, float]] = []
        # attention bias: negative emotion biases ambiguous messages (set to event_type or None)
        self._attention_bias: Optional[str] = None
        # Internal-event deduplication / loop-guard
        self.INTERNAL_COOLDOWN_SEC: float = 120.0
        self._internal_event_cooldowns: Dict[str, float] = {}   # fingerprint → last-appraised timestamp
        self._internal_event_history: deque = deque(maxlen=20)  # rolling fingerprint log
        # Shared Notus embedding layer (optional ST; basic hash fallback). Lazy — never crash.
        self._embedding_engine = None
        self._embedding_engine_tried = False
        self._embedding_model_type = 'unavailable'

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
        prior = self.current_emotion
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
        if self.current_emotion != prior:
            self._last_primary = self.current_emotion
            self._last_switch_time = time.time()
        self._update_emotional_patterns(emotion, trigger)
        if len(self.mood_history) > 200:
            self.mood_history = self.mood_history[-200:]
        self._log(f"{self.name} feels {emotion.value} (int {self.emotional_intensity:.2f}) due to: {trigger}")
        # Keep CoreAffect coherent with explicit feel_emotion (compat API).
        try:
            proto = self._PAD_PROTOS.get(emotion, (0.0, 0.0, 0.0))
            self.core_affect.valence = float(proto[0]) * float(max(0.0, min(1.0, intensity)))
            self.core_affect.arousal = float(proto[1]) * float(max(0.0, min(1.0, intensity)))
            self.core_affect.clamp()
            self.core_affect.last_reason = f"feel_emotion:{emotion.value}"
            self.pad.v = self.core_affect.valence
            self.pad.a = self.core_affect.arousal
        except Exception:
            pass
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
        """Live mood path: CoreAffect + SelfImpact only (not AppraisalEngine classifiers)."""
        # Query Notus for emotional memories (side channel; does not set her mood)
        try:
            notus_emotions = self._query_lobe('notus', {'type': 'get_emotional_memories', 'trigger': user_input})
            if notus_emotions and notus_emotions.get('status') == 'success':
                emotional_mems = notus_emotions.get('memories', [])
        except Exception:
            pass

        # Quiet baseline first: decay toward setpoint (no RNG flip)
        self.core_affect.decay_toward_setpoint(1.0)

        # SelfImpact: ONLY things aimed at / about her move core affect.
        # Explicit user self-reports ("I'm sad") return zero delta.
        delta = self._self_impact.evaluate(user_input or "")
        self._last_self_impact_reason = delta.reason
        if delta.kind != "none" and (abs(delta.dv) > 1e-9 or abs(delta.da) > 1e-9):
            self.core_affect.apply_delta(delta.dv, delta.da, delta.reason)

        self._sync_from_core_affect(trigger=(user_input or "")[:80])

        # Compat: keep last_understanding/appraisal slots filled but gated —
        # classifiers must not write her mood. User feeling stays outside this engine.
        self._last_appraisal = None
        self._last_understanding = None
        # Clear legacy unresolved reinjection so sticky wrong events cannot respike her.
        self._unresolved_appraisals = []
        self._attention_bias = None

        # Response text helpers (do not call _apply_appraisal / PAD lottery)
        try:
            cues = {}
            self._calculate_emotional_resonance(cues)
            context = self.assess_emotional_context(user_input)
            if self.emotional_memories:
                self.process_trauma_memory(self.emotional_memories[-1])
            memory_influence = self._get_memory_influence(user_input)
            base = self._generate_advanced_emotional_response(user_input, memory_influence)
            predicted = {self.current_emotion.value: self.emotional_intensity}
            enhanced = self._enhance_response_with_advanced_features(base, user_input, predicted, context)
            self.calculate_emotional_intelligence()
        except Exception:
            enhanced = f"I'm feeling {self.current_emotion.value}."

        try:
            self._query_lobe('notus', {
                'type': 'store_emotional_memory',
                'emotion': self.current_emotion.value,
                'intensity': self.emotional_intensity,
                'trigger': user_input,
                'context': self._last_self_impact_reason,
                'response': enhanced,
            })
        except Exception:
            pass
        return enhanced

    def appraise_internal_event(self, event: InternalEventAppraisal) -> None:
        """
        Internal thought/memory influence — capped gentle nudge only.
        Does NOT re-run AppraisalEngine user-phrase classifiers at full strength.
        (Old classifier+dampen+_apply_appraisal path ripped from live mood driver.)
        """
        fingerprint = (event.content or "")[:80].lower().strip()

        history_list = list(self._internal_event_history)
        if history_list.count(fingerprint) >= 2:
            self._log(f"[internal_appraisal] loop-guard suppressed: {fingerprint[:40]!r}")
            return

        last_appraised = self._internal_event_cooldowns.get(fingerprint, 0.0)
        if time.time() - last_appraised < self.INTERNAL_COOLDOWN_SEC:
            return

        # Gentle capped nudge — never full phrase-table slam
        delta = self._self_impact.evaluate_internal(
            event.content or "", relevance=float(getattr(event, "relevance", 0.5) or 0.5)
        )
        if event.resolved:
            delta = type(delta)(delta.dv * 0.5, delta.da * 0.5, delta.reason + "|resolved", delta.kind)

        if abs(delta.dv) > 1e-9 or abs(delta.da) > 1e-9:
            self.core_affect.apply_delta(delta.dv, delta.da, delta.reason)
            self._sync_from_core_affect(trigger=f"internal:{fingerprint[:40]}")
        self._last_self_impact_reason = delta.reason

        self._internal_event_cooldowns[fingerprint] = time.time()
        self._internal_event_history.append(fingerprint)
        cutoff = time.time() - self.INTERNAL_COOLDOWN_SEC * 2
        self._internal_event_cooldowns = {
            fp: ts for fp, ts in self._internal_event_cooldowns.items() if ts > cutoff
        }
        self._log(
            f"[internal_nudge] source={event.source} reason={delta.reason} "
            f"dv={delta.dv:.3f} da={delta.da:.3f} → {self.current_emotion.value}"
        )

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
            'internal_event_cooldowns': self._internal_event_cooldowns,
            'user_affect': {
                'inferred_emotion': self._user_affect.inferred_emotion,
                'confidence': self._user_affect.confidence,
                'inferred_need': self._user_affect.inferred_need,
                'last_updated': self._user_affect.last_updated,
                'previous_emotion': self._user_affect.previous_emotion,
                'temporal': self._user_affect.temporal,
                'last_event_type': self._user_affect.last_event_type,
                'third_party_emotion': self._user_affect.third_party_emotion,
            },
            'pad': {'v': self.pad.v, 'a': self.pad.a, 'd': self.pad.d},
            'core_affect': self.core_affect.to_dict(),
            'last_self_impact_reason': getattr(self, '_last_self_impact_reason', ''),
            'attachment': asdict(self.attachment),
            'needs': asdict(self.needs),
            'internal': asdict(self.internal),
            'expression': asdict(self.expression),
            'autonomy_level': self.autonomy_level,
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
        raw_cooldowns = obj.get('internal_event_cooldowns', {})
        if isinstance(raw_cooldowns, dict):
            # Prune already-expired entries on load so stale data doesn't linger.
            cutoff = time.time() - self.INTERNAL_COOLDOWN_SEC * 2
            self._internal_event_cooldowns = {
                fp: float(ts) for fp, ts in raw_cooldowns.items()
                if isinstance(ts, (int, float)) and float(ts) > cutoff
            }
        ua = obj.get('user_affect', {})
        if ua:
            self._user_affect = UserAffectModel(
                inferred_emotion=ua.get('inferred_emotion', 'neutral'),
                confidence=float(ua.get('confidence', 0.0)),
                inferred_need=ua.get('inferred_need', 'neutral'),
                last_updated=float(ua.get('last_updated', 0.0)),
                previous_emotion=ua.get('previous_emotion', 'neutral'),
                temporal=ua.get('temporal', 'current'),
                last_event_type=ua.get('last_event_type', 'neutral'),
                third_party_emotion=ua.get('third_party_emotion'),
            )
        pad_obj = obj.get('pad')
        if isinstance(pad_obj, dict):
            self.pad = PAD(
                v=float(pad_obj.get('v', self.pad.v)),
                a=float(pad_obj.get('a', self.pad.a)),
                d=float(pad_obj.get('d', self.pad.d)),
            )
        # Prefer persisted CoreAffect; else seed from pad (compat with older state files).
        ca_obj = obj.get('core_affect')
        if isinstance(ca_obj, dict):
            self.core_affect = MondayCoreAffect.from_dict(ca_obj)
        elif isinstance(pad_obj, dict):
            self.core_affect = MondayCoreAffect(
                valence=float(pad_obj.get('v', 0.15)),
                arousal=float(pad_obj.get('a', -0.10)),
            )
        self._last_self_impact_reason = str(obj.get('last_self_impact_reason', 'loaded'))
        self._sync_from_core_affect(trigger="load")
        att = obj.get('attachment')
        if isinstance(att, dict):
            self.attachment = AttachmentModel(**{
                k: float(att[k]) for k in AttachmentModel.__dataclass_fields__ if k in att
            })
        needs = obj.get('needs')
        if isinstance(needs, dict):
            self.needs = InternalNeeds(**{
                k: float(needs[k]) for k in InternalNeeds.__dataclass_fields__ if k in needs
            })
        internal = obj.get('internal')
        if isinstance(internal, dict):
            self.internal = InternalState(**{
                k: float(internal[k]) for k in InternalState.__dataclass_fields__ if k in internal
            })
        expr = obj.get('expression')
        if isinstance(expr, dict):
            self.expression = ExpressionState(
                tears=bool(expr.get('tears', False)),
                voice_shake=bool(expr.get('voice_shake', False)),
                withdraw=bool(expr.get('withdraw', False)),
            )
        if 'autonomy_level' in obj:
            self.autonomy_level = float(obj.get('autonomy_level', self.autonomy_level))

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

    # --------------- CoreAffect sync (live mood) ---------------

    def _sync_from_core_affect(self, trigger: str = "") -> None:
        """Publish CoreAffect into legacy fields consumers already read."""
        label = self.core_affect.label()
        intensity = self.core_affect.intensity()
        try:
            emo = EmotionalState(label)
        except ValueError:
            emo = EmotionalState.CALM
        prev = self.current_emotion
        self.current_emotion = emo
        self.emotional_intensity = intensity
        self.pad.v = self.core_affect.valence
        self.pad.a = self.core_affect.arousal
        self.pad.d = max(-1.0, min(1.0, 0.15 - 0.25 * abs(self.core_affect.valence)
                                   + (0.2 if self.core_affect.valence > 0 else -0.15)))
        if emo != prev:
            mem = EmotionalMemory(
                emotion=emo,
                intensity=intensity,
                trigger=(trigger or self.core_affect.last_reason)[:80],
                timestamp=time.time(),
                context=f"core_affect:{self.core_affect.last_reason}",
                influence_strength=1.0,
            )
            self.emotional_memories.append(mem)
            self.mood_history.append((mem.timestamp, emo, intensity))
            self._update_emotional_patterns(emo, trigger or label)
            self._last_primary = emo
            self._last_switch_time = time.time()
        self._update_expression_flags()

    # --------------- Appraisal apply (DELETED driver; honest stub) ---------------

    def _apply_appraisal(self, appraisal: AppraisalResult) -> None:
        """
        DELETED as mood driver (2026-09-25). Live mood is MondayCoreAffect + SelfImpact.
        Fail closed: may stash last_appraisal for debug; never writes valence/arousal/
        current_emotion/intensity from classifier PAD. No phrase tables remain.
        """
        self._last_appraisal = appraisal
        # Do not update Monday PAD / emotion / intensity from appraisal.
        return

    def _has_continuity_cue(self, text: str) -> bool:
        """Anaphoric / episode-continuing language across turns."""
        tl = (text or '').lower()
        patterns = [
            r"\b(he|she|him|her|they|them|it|that|this)\b",
            r"\bdon'?t even want\b", r"\bwant to talk\b",
            r"\btomorrow\b", r"\bstill\b", r"\bagain\b",
            r"\bby it\b", r"\bat first\b", r"\bnow i\b",
            r"\bthe (?:same |whole )?(?:thing|situation|incident)\b",
            r"\bthinking about\b",
        ]
        return any(re.search(p, tl) for p in patterns)

    def _is_topic_shift_neutral(self, text: str) -> bool:
        """Small-talk / topic change that should not lock prior USER peak affect."""
        tl = (text or '').lower()
        return bool(re.search(
            r"\b(weather|temperature|hello|hi\b|hey\b|what time|good morning|good night|how are you)\b",
            tl,
        ))

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

    # Explicit self-report cue tables DELETED (2026-09-25).
    # They were leftover phrase→cue machinery from the old appraisal pipeline and
    # looked active even though live mood ignores them. User feeling stays outside.

    def _analyze_emotional_cues(self, text: str) -> Dict[str, float]:
        """Fail closed stub — cue phrase tables deleted; not a mood driver."""
        return {k: 0.0 for k in ['positive', 'negative', 'excitement', 'concern', 'anger', 'sadness', 'pride']}

    def _get_embedding_engine(self):
        """Reuse Notus AdvancedEmbeddingEngine — optional sentence-transformers, basic fallback."""
        if self._embedding_engine_tried:
            return self._embedding_engine
        self._embedding_engine_tried = True
        try:
            from notus import AdvancedEmbeddingEngine, SuperhumanConfig
            eng = AdvancedEmbeddingEngine(SuperhumanConfig())
            self._embedding_engine = eng
            self._embedding_model_type = getattr(eng, 'model_type', 'basic')
        except Exception:
            self._embedding_engine = None
            self._embedding_model_type = 'unavailable'
        return self._embedding_engine

    # Semantic phrase→event prototypes DELETED (2026-09-25 honesty cleanup).
    # They duplicated AppraisalEngine classifiers (e.g. sadness→rejection) and
    # looked like a live mood driver. Live mood does not use this path.
    _SEMANTIC_EVENT_PROTOTYPES: Dict[str, List[str]] = {}
    _SEMANTIC_EMOTION_BY_EVENT: Dict[str, str] = {}

    def _semantic_emotion_support(self, text: str) -> Dict[str, Any]:
        """Fail closed stub — semantic event prototypes removed; not a mood driver."""
        return {
            'event_type': None,
            'emotion': None,
            'confidence': 0.0,
            'eligible': False,
            'model_type': 'disabled',
        }

    def _understand_emotional_text(
        self,
        text: str,
        relationship_history: Optional[List[str]] = None,
        sensitivity_map: Optional[Dict[str, float]] = None,
    ) -> EmotionalUnderstanding:
        """
        Fail closed stub (2026-09-25). Old pipeline was AppraisalEngine classifiers
        → semantic prototypes → keyword soft-events. That is NOT the live mood path.
        User-feeling recognition belongs outside this engine (Conversation/Social).
        Returns neutral understanding with zero severity.
        """
        appraisal = self._appraisal_engine.appraise(text or '')
        return EmotionalUnderstanding(
            appraisal=appraisal,
            semantic_event=None,
            semantic_emotion=None,
            semantic_confidence=0.0,
            semantic_used=False,
            keyword_cues={},
            primary_source='neutral',
            inferred_emotion='neutral',
            event_type='neutral',
            severity=0.0,
            confidence=0.0,
            negation_affected=False,
            contrast_affected=False,
            explicit_emotion=None,
            appraisal_inferred_emotion='neutral',
            final_appraisal=appraisal,
        )

    def _situation_wording_should_reflect_current(self, user_input: str) -> bool:
        """True when OUTPUT must not narrate a resolved/irrelevant prior conflict as active.
        PAD/INTERNAL may linger; explicit wording must match the current situation.
        """
        appr = getattr(self, '_last_appraisal', None)
        if appr is None:
            return False
        event = getattr(appr, 'event_type', 'neutral') or 'neutral'
        situation_calm = event in (
            'neutral', 'success', 'affection', 'support', 'celebration', 'gift'
        )
        ua = self._user_affect
        user_calm = ua.inferred_emotion in ('unknown', 'neutral', 'calm', 'happy', 'relieved', 'proud')
        resolution = bool(getattr(appr, 'resolution_signal', False))
        unresolved_clear = not bool(getattr(self, '_unresolved_appraisals', None))

        # Resolution: threat/harm cleared — do not speak as if conflict still active.
        if resolution and situation_calm and unresolved_clear:
            return True
        # Unrelated topic / object question: no content hijack from lingering INTERNAL.
        if situation_calm and user_calm and ua.confidence < 0.45:
            if self._is_topic_shift_neutral(user_input):
                return True
            if self._is_unrelated_object_topic(user_input, appr):
                return True
        return False

    def _is_unrelated_object_topic(self, text: str, appraisal: AppraisalResult) -> bool:
        """Object/topic ask with no person owning emotion and no episode continuity."""
        if getattr(appraisal, 'third_party', False):
            return False
        if getattr(appraisal, 'third_party_emotion', None):
            return False
        if appraisal.explicit_user_emotion:
            return False
        if appraisal.directed_at_user or appraisal.directed_at_monday:
            return False
        tl = (text or '').lower()
        # Continuity into an episode is not an unrelated topic shift.
        if self._has_continuity_cue(text) and not self._is_topic_shift_neutral(text):
            return False
        # Question / request about a non-person topic.
        if ('?' in (text or '')) or re.search(r"\b(?:what|how|when|where)\b", tl):
            if not re.search(r"\b(?:i|me|my|mine|you|we|us|she|he|they|him|her|them)\b", tl):
                return True
        return False

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

        # Stale-expression gate: INTERNAL/PAD may linger; wording must not claim
        # resolved threat/conflict (or unrelated topics) are still the active situation.
        if self._situation_wording_should_reflect_current(user_input):
            lines = [
                "I'm here to help.",
                "Okay — I'm with you.",
                "Got it. I'm listening.",
                "Alright. I'm here.",
                "I'm still with you.",
            ]
            # Mild residual via expression punctuation only (not content hijack).
            if self.expression.tears:
                lines = [l.replace(".", "...") for l in lines]
            if self.expression.voice_shake:
                lines = ["".join([" ".join(l.split()[:3]), " ...", " ".join(l.split()[3:])]).strip() for l in lines]
            return self._rng.choice(lines)
        
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
            EmotionalState.RELIEVED: [
                "I feel a wave of relief.",
                "That took a weight off — I'm relieved.",
                "I'm glad that settled; I feel relieved.",
                "Relief is settling in.",
                "I'm breathing easier now.",
            ],
            EmotionalState.EXHAUSTED: [
                "I'm worn out.",
                "I feel drained right now.",
                "I'm exhausted — running on empty.",
                "That took a lot out of me.",
                "I'm tired down to the bone.",
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
        situational = self._situation_wording_should_reflect_current(user_input)
        # Reflect current USER state; never invent active threat language after resolution.
        if dom[1] > 0.35 and dom[0] not in ('unknown',):
            out += f" I get the sense you're feeling {dom[0]}."
        if situational:
            # Prosody/INTERNAL may linger; do not add urgency/support-as-crisis overlays.
            return out
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

    def _update_attachment_from_appraisal(self, appraisal: AppraisalResult) -> None:
        """Attachment drifts from appraised event meaning, not only yelling keywords."""
        et = appraisal.event_type
        sev = float(max(0.0, min(1.0, appraisal.severity)))
        sens = float(self.attachment.sensitivity)
        if et in ('betrayal', 'rejection', 'abandonment', 'harm', 'loss'):
            self.attachment.hurt = min(1.0, self.attachment.hurt + 0.28 * sev * sens)
            self.attachment.abandonment_fear = min(
                1.0, self.attachment.abandonment_fear + 0.22 * sev
            )
            if et == 'abandonment':
                self.attachment.abandonment_fear = min(
                    1.0, self.attachment.abandonment_fear + 0.12 * sev
                )
            self.attachment.security = max(0.0, self.attachment.security - 0.08 * sev)
        elif et in ('affection', 'support', 'gift', 'celebration'):
            self.attachment.hurt = max(0.0, self.attachment.hurt - 0.18 * sev)
            self.attachment.abandonment_fear = max(
                0.0, self.attachment.abandonment_fear - 0.10 * sev
            )
            self.attachment.security = min(1.0, self.attachment.security + 0.06 * sev)
            self.attachment.guilt = max(0.0, self.attachment.guilt - 0.05 * sev)

    def _update_needs_from_appraisal(self, appraisal: AppraisalResult) -> None:
        """Internal needs shift with appraised events so autonomy/belonging/safety are live."""
        et = appraisal.event_type
        sev = float(max(0.0, min(1.0, appraisal.severity)))
        if et in ('harm', 'threat', 'abandonment'):
            self.needs.safety = max(0.0, self.needs.safety - 0.18 * sev)
        if et in ('rejection', 'betrayal', 'abandonment', 'loss'):
            self.needs.belonging = max(0.0, self.needs.belonging - 0.18 * sev)
        if et == 'criticism' and appraisal.directed_at_monday:
            self.needs.competence = max(0.0, self.needs.competence - 0.12 * sev)
        if et in ('conflict', 'unfairness'):
            self.needs.autonomy = max(0.0, self.needs.autonomy - 0.08 * sev)
        if et in ('affection', 'support', 'gift'):
            self.needs.belonging = min(1.0, self.needs.belonging + 0.12 * sev)
            self.needs.safety = min(1.0, self.needs.safety + 0.06 * sev)
        if et in ('success', 'celebration'):
            self.needs.competence = min(1.0, self.needs.competence + 0.12 * sev)
        if et in ('gift', 'celebration', 'affection'):
            self.needs.stimulation = min(1.0, self.needs.stimulation + 0.05 * sev)

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
        """GATED: live mood uses CoreAffect.apply_delta / decay — not 80% PAD overwrite + noise."""
        # Mirror into pad fields for any legacy reader without mutating CoreAffect.
        # Intentionally does NOT apply decay=0.8 overwrite or RNG noise.
        self.pad.v = max(-1.0, min(1.0, float(new_pad.v)))
        self.pad.a = max(-1.0, min(1.0, float(new_pad.a)))
        self.pad.d = max(-1.0, min(1.0, float(new_pad.d)))

    def _pad_to_emotion_choice(self, pad: PAD) -> Optional[Tuple[EmotionalState, float]]:
        """GATED: thin deterministic label from CoreAffect; no top-3 RNG lottery."""
        # Prefer live CoreAffect; fall back to pad.v/a if somehow called standalone.
        v = getattr(self, "core_affect", None).valence if getattr(self, "core_affect", None) else pad.v
        a = getattr(self, "core_affect", None).arousal if getattr(self, "core_affect", None) else pad.a
        label = label_from_va(v, a)
        try:
            emo = EmotionalState(label)
        except ValueError:
            emo = EmotionalState.CALM
        intensity = self.core_affect.intensity() if getattr(self, "core_affect", None) else max(0.1, min(1.0, (abs(v) + abs(a)) / 2))
        return (emo, intensity)

    def _pad_margin_ok(self, candidate: EmotionalState) -> bool:
        # Refractory: block unwanted flips too soon after the last emotion switch.
        if candidate != self.current_emotion and self._last_switch_time > 0.0:
            elapsed = time.time() - self._last_switch_time
            if elapsed < float(self.personality.refractory_sec):
                return False
        # Hysteresis: require enough PAD distance improvement to switch.
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
        """Compat hook — intensity from CoreAffect, never hardcoded 0.8 + RNG."""
        # Prefer syncing through CoreAffect label when emotion matches thin set;
        # otherwise adopt named emotion but intensity still from core distance.
        intensity = float(self.core_affect.intensity())
        self.current_emotion = emotion
        self.emotional_intensity = intensity
        mem = EmotionalMemory(
            emotion=emotion,
            intensity=intensity,
            trigger=f"switch:{trigger[:50]}",
            timestamp=time.time(),
            context="compat_switch_via_core_intensity",
            influence_strength=1.0,
        )
        self.emotional_memories.append(mem)
        self.mood_history.append((mem.timestamp, emotion, intensity))
        self._update_emotional_patterns(emotion, trigger)
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
        User-feeling estimate only — does NOT write Monday mood.
        Prefer Conversation/Social; phrase classifiers were deleted.
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

        understanding = self._understand_emotional_text(user_input)
        if understanding.inferred_emotion != 'neutral' and understanding.confidence > 0.15:
            pred = {understanding.inferred_emotion: understanding.confidence}
            self.emotional_predictions[user_input[:50]] = pred
            return pred

        # Residual keyword cue vector (already negation-aware)
        cues = understanding.keyword_cues
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
    
    def _affect_snapshot(self) -> Dict[str, Any]:
        """Live-path affect contract: PAD, attachment/needs, expression, patterns, prosody."""
        emo_out = self.get_emotional_state_output()
        patterns_summary = {
            k: [e.value for e in v[-3:]]
            for k, v in list(self.engine.emotional_patterns.items())[-20:]
        }
        # Ensure envelope mirrors CoreAffect (her mood only).
        try:
            self.engine._sync_from_core_affect(trigger="snapshot")
        except Exception:
            pass
        ca = getattr(self.engine, "core_affect", None)
        valence = float(ca.valence) if ca is not None else float(self.engine.pad.v)
        arousal = float(ca.arousal) if ca is not None else float(self.engine.pad.a)
        return {
            'current_emotion': self.engine.current_emotion.value,
            'emotion': self.engine.current_emotion.value,
            'monday_emotion': self.engine.current_emotion.value,
            'intensity': self.engine.emotional_intensity,
            'resonance': self.engine.emotional_resonance,
            'valence': valence,
            'pleasure': valence,
            'arousal': arousal,
            'dominance': self.engine.pad.d,
            'self_impact_reason': getattr(self.engine, '_last_self_impact_reason', ''),
            'pad': {
                'v': valence,
                'a': arousal,
                'd': self.engine.pad.d,
            },
            'core_affect': ca.to_dict() if ca is not None else {},
            'attachment': asdict(self.engine.attachment),
            'needs': asdict(self.engine.needs),
            'internal': asdict(self.engine.internal),
            'expression': asdict(self.engine.expression),
            'emotional_tone': emo_out.emotional_tone,
            'emphasis': list(emo_out.emphasis),
            'voice_prosody': dict(emo_out.voice_prosody),
            'autonomy_level': self.engine.autonomy_level,
            'memory_count': len(self.engine.emotional_memories),
            'patterns': patterns_summary,
            'emotional_patterns': patterns_summary,
            'user_affect': {
                'inferred_emotion': self.engine._user_affect.inferred_emotion,
                'confidence': self.engine._user_affect.confidence,
                'inferred_need': self.engine._user_affect.inferred_need,
                'previous_emotion': self.engine._user_affect.previous_emotion,
                'temporal': self.engine._user_affect.temporal,
                'last_event_type': self.engine._user_affect.last_event_type,
                'third_party_emotion': self.engine._user_affect.third_party_emotion,
            },
        }

    def process_message_safe(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Safe dispatcher with validation (FIX)"""
        with self.engine.engine_lock:
            msg_type = message.get('type')
            # Envelope unwrap: content may be a dict payload, or (rarely) a bare string.
            raw_content = message.get('content', message)
            if isinstance(raw_content, dict):
                message = {**raw_content, 'type': msg_type}
            else:
                # Preserve top-level fields; stash non-dict content for internal handlers.
                message = {**{k: v for k, v in message.items() if k != 'content'},
                           'type': msg_type, 'content': raw_content}
            
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
                
                unresolved = [
                    {'event_type': et, 'severity': float(sev), 'timestamp': float(ts)}
                    for (et, sev, ts) in getattr(self.engine, '_unresolved_appraisals', [])
                ]
                snap = self._affect_snapshot()
                return {
                    'status': 'success',
                    'response': response,
                    'current_emotion': snap['current_emotion'],
                    'intensity': snap['intensity'],
                    'resonance': snap['resonance'],
                    'worry': self.engine.internal.worry,
                    'tension': self.engine.internal.tension,
                    'autonomy_level': snap['autonomy_level'],
                    'unresolved_appraisals': unresolved,
                    'valence': snap.get('valence', snap['pleasure']),
                    'pleasure': snap['pleasure'],
                    'arousal': snap['arousal'],
                    'dominance': snap['dominance'],
                    'monday_emotion': snap.get('monday_emotion', snap['current_emotion']),
                    'self_impact_reason': snap.get('self_impact_reason', ''),
                    'pad': snap['pad'],
                    'attachment': snap['attachment'],
                    'needs': snap['needs'],
                    'internal': snap['internal'],
                    'expression': snap['expression'],
                    'emotional_tone': snap['emotional_tone'],
                    'emphasis': snap['emphasis'],
                    'voice_prosody': snap['voice_prosody'],
                    'memory_count': snap['memory_count'],
                    'patterns': snap['patterns'],
                    'user_affect': snap.get('user_affect'),
                }
                
            elif msg_type == 'feel_emotion':
                # Canonical live contract matches AdvancedEmotionalEngine.feel_emotion:
                #   emotion   (required): EmotionalState value string
                #   intensity (optional, default 0.5)
                #   trigger   (optional, default "External trigger";
                #              aliases: text / user_input when emotion is present)
                #   context   (optional)
                # Free-text appraisal is process_input / appraise_internal — not feel_emotion.
                emotion_raw = message.get('emotion')
                if emotion_raw is None or (isinstance(emotion_raw, str) and not str(emotion_raw).strip()):
                    keys = sorted(k for k in message.keys() if k != 'type')
                    return {
                        'status': 'error',
                        'message': (
                            "feel_emotion requires 'emotion' (EmotionalState value), "
                            f"optional intensity/trigger; got keys {keys}. "
                            "For text appraisal use process_input or appraise_internal."
                        ),
                    }
                if isinstance(emotion_raw, EmotionalState):
                    emotion = emotion_raw
                    emotion_str = emotion.value
                else:
                    emotion_str = str(emotion_raw).strip().lower()
                    try:
                        emotion = EmotionalState(emotion_str)
                    except Exception:
                        return {'status': 'error', 'message': f'Unknown emotion: {emotion_str}'}

                intensity = float(message.get('intensity', 0.5))
                trigger = message.get('trigger')
                if not (isinstance(trigger, str) and trigger.strip()):
                    alt = message.get('text', message.get('user_input', 'External trigger'))
                    trigger = alt if isinstance(alt, str) and alt.strip() else 'External trigger'
                context = message.get('context', '')
                if not isinstance(context, str):
                    context = str(context or '')

                before_emotion = self.engine.current_emotion.value
                before_intensity = float(self.engine.emotional_intensity)
                before_mems = len(self.engine.emotional_memories)

                self.engine.feel_emotion(emotion, intensity, trigger, context)

                if intensity > 0.6:
                    self._notify_novelty_lobe(trigger, emotion_str, intensity)

                return {
                    'status': 'success',
                    'current_emotion': self.engine.current_emotion.value,
                    'intensity': self.engine.emotional_intensity,
                    'emotion_changed': (
                        self.engine.current_emotion.value != before_emotion
                        or abs(float(self.engine.emotional_intensity) - before_intensity) > 1e-9
                    ),
                    'memory_count': len(self.engine.emotional_memories),
                    'memories_added': len(self.engine.emotional_memories) - before_mems,
                    'trigger': trigger,
                }
                
            elif msg_type == 'get_state':
                # Top-level emotion/intensity (not nested under 'state') so lobes
                # reading get_state see real affect. Full affect contract for live path.
                unresolved = [
                    {'event_type': et, 'severity': float(sev), 'timestamp': float(ts)}
                    for (et, sev, ts) in getattr(self.engine, '_unresolved_appraisals', [])
                ]
                history = list(getattr(self.engine, '_event_history', [])[-10:])
                last_event = history[-1] if history else None
                snap = self._affect_snapshot()
                return {
                    'status': 'success',
                    'emotion': snap['emotion'],
                    'intensity': snap['intensity'],
                    'resonance': snap['resonance'],
                    'summary': self.engine.get_emotional_summary(),
                    'last_event_type': last_event,
                    'unresolved_appraisals': unresolved,
                    'event_history': history,
                    'valence': snap.get('valence', snap['pleasure']),
                    'pleasure': snap['pleasure'],
                    'arousal': snap['arousal'],
                    'dominance': snap['dominance'],
                    'monday_emotion': snap.get('monday_emotion', snap['current_emotion']),
                    'self_impact_reason': snap.get('self_impact_reason', ''),
                    'pad': snap['pad'],
                    'attachment': snap['attachment'],
                    'needs': snap['needs'],
                    'internal': snap['internal'],
                    'expression': snap['expression'],
                    'emotional_tone': snap['emotional_tone'],
                    'emphasis': snap['emphasis'],
                    'voice_prosody': snap['voice_prosody'],
                    'memory_count': snap['memory_count'],
                    'patterns': snap['patterns'],
                    'emotional_patterns': snap['emotional_patterns'],
                    'autonomy_level': snap['autonomy_level'],
                    'user_affect': snap.get('user_affect'),
                }
            
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

            elif msg_type in ('appraise_internal', 'internal_event'):
                # Thalamus / other lobes can drive Monday's own feelings without user text.
                content = message.get('content', message.get('text', message.get('user_input', '')))
                if isinstance(content, dict):
                    # Nested payload: prefer explicit fields
                    source = content.get('source', message.get('source', 'thought'))
                    text_body = content.get('text', content.get('content', content.get('trigger', '')))
                    relevance = float(content.get('relevance', message.get('relevance', 0.5)))
                    resolved = bool(content.get('resolved', message.get('resolved', False)))
                    memory_age = float(content.get('memory_age_seconds', message.get('memory_age_seconds', 0.0)))
                    prior = content.get('prior_appraisal_event_type',
                                       message.get('prior_appraisal_event_type'))
                else:
                    source = message.get('source', 'thought')
                    text_body = content if isinstance(content, str) else str(content or '')
                    relevance = float(message.get('relevance', 0.5))
                    resolved = bool(message.get('resolved', False))
                    memory_age = float(message.get('memory_age_seconds', 0.0))
                    prior = message.get('prior_appraisal_event_type')

                if not isinstance(text_body, str) or not text_body.strip():
                    return {'status': 'error', 'message': 'internal event content must be a non-empty string'}

                event = InternalEventAppraisal(
                    source=str(source or 'thought'),
                    content=text_body.strip(),
                    memory_age_seconds=memory_age,
                    resolved=resolved,
                    prior_appraisal_event_type=prior,
                    relevance=relevance,
                )
                self.engine.appraise_internal_event(event)
                return {
                    'status': 'success',
                    'current_emotion': self.engine.current_emotion.value,
                    'intensity': self.engine.emotional_intensity,
                    'source': event.source,
                    'event_type': getattr(self.engine, '_event_history', [None])[-1]
                                  if getattr(self.engine, '_event_history', None) else None,
                }
            
            else:
                return {'status': 'error', 'message': f'Unknown message type: {msg_type}'}
    
    def nudge_from_inner_life(self, content: str, source: str = 'thought',
                               relevance: float = 0.5, resolved: bool = False,
                               memory_age_seconds: float = 0.0,
                               prior_appraisal_event_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Safe entry point for other lobes to color Monday's feelings from inner life
        (thoughts / memories) without user chat. No background spam thread — callable API only.
        """
        if not isinstance(content, str) or not content.strip():
            return {'status': 'error', 'message': 'content must be a non-empty string'}
        event = InternalEventAppraisal(
            source=str(source or 'thought'),
            content=content.strip(),
            memory_age_seconds=float(memory_age_seconds),
            resolved=bool(resolved),
            prior_appraisal_event_type=prior_appraisal_event_type,
            relevance=float(max(0.0, min(1.0, relevance))),
        )
        with self.engine.engine_lock:
            self.engine.appraise_internal_event(event)
            return {
                'status': 'success',
                'current_emotion': self.engine.current_emotion.value,
                'intensity': self.engine.emotional_intensity,
                'source': event.source,
                'event_type': self.engine._event_history[-1] if self.engine._event_history else None,
            }

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
        Optionally tell Novelty Lobe about strong affect.

        Live six-path does not register novelty_lobe — silence and return when
        missing so notify errors never break chat. Curiosity is owned elsewhere.
        """
        try:
            thalamus = getattr(self, 'thalamus', None)
            if thalamus is None:
                return
            handlers = getattr(thalamus, 'lobe_handlers', None)
            lock = getattr(thalamus, 'lobe_handlers_lock', None)
            if handlers is None:
                return
            if lock is not None:
                with lock:
                    has_novelty = 'novelty' in handlers
            else:
                has_novelty = 'novelty' in handlers
            if not has_novelty:
                return  # novelty_lobe dead / unregistered — do not spam or fail

            positive_emotions = ['happy', 'excited', 'curious', 'proud', 'euphoric', 'playful']
            negative_emotions = ['sad', 'angry', 'disgusted', 'scared', 'worried', 'anxious']
            if emotion in positive_emotions:
                valence = 0.5 + (intensity * 0.5)
            elif emotion in negative_emotions:
                valence = -(0.5 + (intensity * 0.5))
            else:
                valence = 0.0

            thalamus.send_message(
                'novelty',
                'emotional_response_to_novelty',
                {
                    'stimulus': stimulus,
                    'emotion': emotion,
                    'intensity': intensity,
                    'valence': valence,
                    'timestamp': time.time(),
                },
            )
        except Exception:
            # Never let novelty notify errors break emotion / chat.
            return

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
