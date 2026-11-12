#!/usr/bin/env python3
"""
Emotion lobe — Monday's feelings.

Where her feelings come from (Matthew, Nov 3): her inner life
(monday_inner_life.py) — her needs (belonging, competence, stimulation,
safety, autonomy) and attachment, changed by what happens to her (what
social context reads in a moment, how her replies go, something new, a
memory coming back) and by time passing. Never by a word's rating.
Each change pushes her core affect (monday_core_affect.py: how good/bad,
how stirred up) and is named by what caused it; the full range of human
feeling has a cause in the inner life. Mood settles with time.
Saved across restarts. Old unused parts are in
legacy/emotion_engine_old_parts_legacy.py.
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
from monday_core_affect import MondayCoreAffect, label_from_va, THIN_LABELS
from monday_inner_life import InnerLife

# ------------------------------
# Core Enums & Dataclasses
# ------------------------------

class EmotionalState(Enum):
    # LIVE thin readout set — label_from_va / CoreAffect exports ONLY these on live path.
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    EXCITED = "excited"
    CALM = "calm"
    WORRIED = "worried"
    SCARED = "scared"
    # Feelings that come from her needs and what happens to her (inner life).
    LONELY = "lonely"
    HURT = "hurt"
    GLAD = "glad"
    BORED = "bored"
    AWED = "awed"
    AMUSED = "amused"
    CONFUSED = "confused"
    GRATEFUL = "grateful"
    LOVING = "loving"
    HOPEFUL = "hopeful"
    ADMIRING = "admiring"
    HORRIFIED = "horrified"
    SYMPATHETIC = "sympathetic"
    APPRECIATIVE = "appreciative"
    JEALOUS = "jealous"
    ENVIOUS = "envious"
    GUILTY = "guilty"
    ASHAMED = "ashamed"
    EMBARRASSED = "embarrassed"
    AWKWARD = "awkward"
    CONTEMPTUOUS = "contemptuous"
    SATISFIED = "satisfied"
    LONGING = "longing"
    # UNUSED/legacy — kept for persisted state + feel_emotion compat.
    # NOT produced by live CoreAffect readout; do not treat as live mood labels.
    CURIOUS = "curious"          # UNUSED/legacy
    PROUD = "proud"              # UNUSED/legacy
    RELIEVED = "relieved"        # UNUSED/legacy
    EXHAUSTED = "exhausted"      # UNUSED/legacy
    SURPRISED = "surprised"      # UNUSED/legacy
    DISGUSTED = "disgusted"      # UNUSED/legacy
    CONTEMPT = "contempt"        # UNUSED/legacy
    NOSTALGIC = "nostalgic"      # UNUSED/legacy
    ANXIOUS = "anxious"          # UNUSED/legacy
    FRUSTRATED = "frustrated"  # from her inner life
    EUPHORIC = "euphoric"        # UNUSED/legacy
    MELANCHOLIC = "melancholic"  # UNUSED/legacy
    PLAYFUL = "playful"          # UNUSED/legacy
    PROTECTIVE = "protective"    # UNUSED/legacy
    MISCHIEVOUS = "mischievous"  # UNUSED/legacy

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
    content: str                           # Thought/memory text for a gentle appraisal nudge
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
        self._last_self_impact_reason: str = "init"
        self.last_appraisal: Dict[str, Any] = {}
        self._last_primary: EmotionalState = EmotionalState.CALM
        self._last_switch_time: float = 0.0
        # PAD prototypes for feel_emotion compat ONLY (thin live set).
        # Live mood labels come from CoreAffect.label_from_va — not nearest-proto lottery.
        # Unused/legacy enum members intentionally omitted from this map.
        self._PAD_PROTOS: Dict[EmotionalState, Tuple[float, float, float]] = {
            EmotionalState.HAPPY: ( 0.80,  0.30,  0.20),
            EmotionalState.SAD:   (-0.80, -0.20, -0.40),
            EmotionalState.ANGRY: (-0.70,  0.70,  0.60),
            EmotionalState.EXCITED:( 0.70,  0.80,  0.30),
            EmotionalState.CALM:  ( 0.30, -0.50,  0.50),
            EmotionalState.WORRIED:(-0.60,  0.60, -0.50),
            EmotionalState.SCARED:(-0.70,  0.80, -0.70),
        }
        # Autonomy & internals
        self.autonomy_level: float = 0.85  # 0 mirror ↔ 1 fully internal
        self.attachment = AttachmentModel()
        self.needs = InternalNeeds()
        # Where her feelings come from: her needs and what happens to her.
        self.inner = InnerLife(self.needs, self.attachment)
        self._feeling_since = 0.0
        self.internal = InternalState()
        self.expression = ExpressionState()
        self._time_on_task: float = 0.0
        self._user_affect = UserAffectModel()
        self._last_appraisal = None
        self._last_understanding = None
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
            return self.thalamus.send_message(lobe_name, msg_type, message, source='emotion')
        except Exception:
            return None
    
    def feel(self, felt: List[Any], main: bool = False) -> None:
        """What happened moves her core affect; the strongest named feeling is
        what she feels now."""
        strongest = None
        values = getattr(self, "_values_now", None) or []
        for f in felt or []:
            # A feeling tied to a value she holds strongly counts for more.
            touched = [v for v in values if (f.need and f.need in v.get("about", []))
                       or (f.feeling and f.feeling in v.get("about", []))]
            if touched:
                weight = 1.0 + (max(float(v.get("strength") or 0.5) for v in touched) - 0.5)
                f.dv, f.da = f.dv * weight, f.da * weight
                if abs(f.dv) > 0.08:
                    self._tell_values(touched, f)
            # The more she already leans one way, the less more of the same moves
            # her (she can't be pushed past the edge; the other way moves her fully).
            v, a = self.core_affect.valence, self.core_affect.arousal
            dv = f.dv * (1.0 - max(0.0, v if f.dv > 0 else -v))
            da = f.da * (1.0 - max(0.0, a if f.da > 0 else -a))
            self.core_affect.apply_delta(dv, da, f.reason)
            self._last_self_impact_reason = f.reason
            if f.feeling and (strongest is None or abs(f.dv) + abs(f.da) > abs(strongest.dv) + abs(strongest.da)):
                strongest = f
        if strongest is not None and abs(strongest.dv) + abs(strongest.da) > 0.06:
            size = abs(strongest.dv) + abs(strongest.da)
            # A smaller feeling doesn't cover a bigger one from moments ago.
            held = getattr(self, "_feeling_size", 0.0) * max(0.0, 1.0 - (time.time() - self._feeling_since) / 600.0)
            # The moment's own feeling takes over unless much smaller; one that
            # comes after (how her reply went, not understanding) must be bigger.
            if main or size >= held:
                self.inner.last_feeling, self.inner.last_reason = strongest.feeling, strongest.reason
                self._feeling_since, self._feeling_size = time.time(), size
                history = self.__dict__.setdefault("_recent_feelings", [])
                history.append((time.time(), strongest.feeling))
                del history[:-8]

    def _feeling_shape(self, name: str):
        """How good/bad and how stirred up a named feeling is (its place on her
        two dials), so a remembered feeling can be felt again."""
        try:
            emotion = EmotionalState(name)
        except ValueError:
            return None
        shapes = {"lonely": (-0.4, -0.3), "hurt": (-0.5, 0.2), "glad": (0.4, 0.1), "bored": (-0.2, -0.4),
                  "proud": (0.5, 0.3), "frustrated": (-0.4, 0.4), "curious": (0.3, 0.4), "relieved": (0.3, -0.2),
                  **{'awed': (0.5, 0.6), 'amused': (0.5, 0.4), 'confused': (-0.1, 0.3), 'grateful': (0.6, 0.2), 'loving': (0.7, 0.2), 'hopeful': (0.4, 0.3), 'admiring': (0.5, 0.3), 'horrified': (-0.7, 0.8), 'sympathetic': (-0.3, 0.0), 'appreciative': (0.5, 0.1), 'disgusted': (-0.6, 0.4), 'jealous': (-0.3, 0.4), 'envious': (-0.3, 0.3), 'guilty': (-0.5, 0.2), 'ashamed': (-0.6, 0.1), 'embarrassed': (-0.3, 0.5), 'awkward': (-0.2, 0.3), 'contemptuous': (-0.4, 0.2), 'anxious': (-0.4, 0.5), 'satisfied': (0.4, -0.1), 'nostalgic': (0.3, -0.2), 'longing': (-0.2, 0.2), 'surprised': (0.0, 0.6)}}
        if name in shapes:
            return shapes[name]
        proto = self._PAD_PROTOS.get(emotion)
        return (proto[0], proto[1]) if proto else None

    @staticmethod
    def _days_ago(when: Any) -> float:
        import datetime as _dt
        try:
            if isinstance(when, (int, float)):
                return max(0.0, (time.time() - float(when)) / 86400.0)
            said = _dt.datetime.fromisoformat(str(when).replace("Z", "+00:00"))
            now = _dt.datetime.now(said.tzinfo) if said.tzinfo else _dt.datetime.now()
            return max(0.0, (now - said).total_seconds() / 86400.0)
        except Exception:
            return 0.0

    def _tell_values(self, touched: List[Dict[str, Any]], f: Any) -> None:
        """What she went through, for her values to change with it."""
        tell = getattr(self.thalamus, "tell", None)
        if not callable(tell):
            return
        try:
            tell("values", "apply_experience", {
                # A strong feeling tied to a value shows the value matters to her
                # (guilt shows she cares about honesty; hurt from Matthew shows the
                # connection matters), so it is reported as the value mattering.
                "values": [v.get("name") for v in touched], "valence": 1.0,
                "intensity": min(1.0, abs(f.dv)), "emotion": f.feeling or "", "experience_id": f.reason[:60],
            }, "emotion")
        except Exception:
            pass

    def _load_values(self) -> None:
        """Her values, as the values lobe holds them now (once per moment)."""
        response = self._query_lobe('values', {'type': 'get_values'}) or {}
        found = response.get('values') or (response.get('content') or {}).get('values') or []
        self._values_now = [v for v in found if isinstance(v, dict)]

    def _settle_for_time(self) -> None:
        """Her mood settles back toward calm with time, not with turns."""
        now = time.time()
        last = getattr(self, "_last_settle", now)
        self._last_settle = now
        minutes = max(0.0, (now - last) / 60.0)
        self.core_affect.decay_toward_setpoint(min(4.0, 0.3 + minutes / 10.0))

    def _social_read(self, text: str, user_id: str) -> Dict[str, Any]:
        heard = (getattr(self, "_social_reads", {}) or {}).get(user_id) or {}
        if str(heard.get("said") or "").strip() == text.strip():
            return heard
        response = self._query_lobe('social_context', {'type': 'get_context', 'user_id': user_id}) or {}
        body = response.get('content') if isinstance(response.get('content'), dict) else {}
        return body if str(body.get("said") or "").strip() == text.strip() else {}

    def _read(self, text: str) -> Dict[str, Any]:
        """Language reads the sentence; Emotion doesn't parse grammar itself."""
        if not text.strip():
            return {}
        response = self._query_lobe('language', {'type': 'analyze', 'text': text})
        if not isinstance(response, dict) or response.get('status') != 'success':
            print(f"⚠️  Emotion: Language couldn't read {text[:40]!r} for her: "
                  f"{(response or {}).get('message') if isinstance(response, dict) else 'no answer'}")
            return {}
        content = response.get('content') if isinstance(response.get('content'), dict) else response
        return content.get('understanding') or {}

    def get_emotional_response(self, user_input: str, user_id: str = "default") -> str:
        """What she feels: her inner life (needs, what happens, time), on her core affect."""
        # Her feelings come from her needs and what happens to her, not from
        # the words themselves (Matthew, Nov 3). First, time has passed.
        self._settle_for_time()
        self._load_values()
        self.feel(self.inner.pass_time())

        # What just happened: social context read the moment (a greeting, an
        # insult, being thanked...); anything said is someone talking to her.
        social = self._social_read(user_input or "", user_id)
        move = str(social.get("move") or "")
        kind = {"greeting": "greeting", "goodbye": "goodbye", "thanks": "thanks",
                "compliment": "compliment", "insult": "insult"}.get(move, "contact")
        if social.get("taught"):
            kind = "taught"
        felt = self.inner.happen(kind, who="he")
        his = social.get("his_feeling") if isinstance(social.get("his_feeling"), dict) else {}
        if his.get("good") is not None:
            felt += self.inner.feel_for(float(his["good"]))
        novelty = self._query_lobe('novelty', {'type': 'get_assessment'}) or {}
        score = float(novelty.get('novelty_score') or (novelty.get('content') or {}).get('score') or 0.0)
        if score > 0.6:
            felt += self.inner.happen("novel", strength=score)
        # The rest of human feeling: what kind of moment this is.
        moment = {k: social.get(k) for k in ("meant", "about_someone_else", "other_person", "tense", "funny",
                                             "correcting", "verbs", "her_to_him")}
        moment.update({"kind": kind, "novelty": score, "valence": self.core_affect.valence,
                       "didnt_understand": bool(getattr(self, "_didnt_understand", {}).get(user_input)),
                       "just_replied": bool(getattr(self, "_replied_last", False))})
        felt += self.inner.moment_feelings(moment)
        self.feel(felt, main=True)
        self.last_appraisal = {"event": kind, "felt": [f.reason for f in felt],
                               "inner": self.inner.state()}
        self._sync_from_core_affect(trigger=(user_input or "")[:80])

        # Compat: keep last_understanding/appraisal slots filled but gated —
        # classifiers must not write her mood. User feeling stays outside this engine.
        self._last_appraisal = None
        self._last_understanding = None
        # Clear legacy unresolved reinjection so sticky wrong events cannot respike her.
        self._unresolved_appraisals = []
        self._attention_bias = None

        # What she feels, in a word (other lobes read her state, not this text).
        enhanced = self.current_emotion.value

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
        # Her own thoughts don't make her feel something from their words; the
        # feelings they carry come back through memory (remembered moments).
        from monday_inner_life import Felt
        delta = Felt(0.0, 0.0, None, "thought noted")

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
            'inner_life': {**self.inner.state(), 'last_time': self.inner.last_time},
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
        # Her inner life works on the needs and attachment just loaded.
        self.inner.needs, self.inner.attachment = self.needs, self.attachment
        self.inner.load(obj.get('inner_life') or {})
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
        named = getattr(getattr(self, "inner", None), "last_feeling", None)
        def _fits(name):
            shape = self._feeling_shape(name) if name else None
            return shape is None or abs(self.core_affect.valence) < 0.15 or \
                (shape[0] >= 0) == (self.core_affect.valence >= 0)
        fits = _fits(named)
        if named and not fits:
            # A good moment while she's still upset: she's still feeling the last
            # thing that fits her mood (not a made-up "angry").
            for when, earlier in reversed(getattr(self, "_recent_feelings", [])):
                if time.time() - when < 3600 and _fits(earlier):
                    named, fits = earlier, True
                    break
        if named and fits and time.time() - getattr(self, "_feeling_since", 0.0) < 3600 and (
                label != "calm" or abs(self.core_affect.valence - self.core_affect.setpoint_v) > 0.05):
            label = named  # what she feels, named by what caused it (lonely, hurt, proud...)
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

    # --------------- (Old appraisal/PAD-lottery driver DELETED 2026-09-25) ---------------

    # --- Main appraisal path (autonomy + PAD) ---
    # --- Inner life mechanics ---
    def _update_expression_flags(self) -> None:
        sad_like = self.current_emotion in (EmotionalState.SAD, EmotionalState.MELANCHOLIC, EmotionalState.WORRIED)
        self.expression.tears = bool((sad_like and self.emotional_intensity > 0.65) or self.attachment.hurt > 0.7)
        self.expression.voice_shake = bool(self.expression.tears or (self.emotional_intensity > 0.7 and sad_like))
        self.expression.withdraw = bool(self.attachment.hurt + self.attachment.abandonment_fear > 1.1)

    # --------------- Utilities ---------------
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
    
    def on_joined(self, name: str) -> None:
        """On the team: hear what social context makes of each moment and what
        memory brings back."""
        listen = getattr(self.thalamus, "listen", None)
        if callable(listen):
            listen(name, "social_read")
            listen(name, "remembered")

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
            return self.thalamus.send_message(lobe_name, msg_type, message, source='emotion')
        except Exception:
            return None
    
    def get_emotional_state_output(self) -> EmotionalStateOutput:
        """Generate standardized emotional state output readable by other lobes"""
        # Tone map: live thin labels first; unused/legacy keys kept for feel_emotion compat only.
        emotion_to_tone = {
            'happy': 'cheerful',
            'sad': 'melancholic',
            'angry': 'irritated',
            'excited': 'enthusiastic',
            'calm': 'peaceful',
            'worried': 'concerned',
            'scared': 'fearful',
            # UNUSED/legacy (not live CoreAffect readout)
            'curious': 'inquisitive',
            'proud': 'confident',
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
            'mischievous': 'impish',
            'relieved': 'peaceful',
            'exhausted': 'somber',
        }
        
        # Live envelope uses CoreAffect-synced pad (her mood only).
        emotion_name = self.engine.current_emotion.value
        
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
        """HER mood envelope only (CoreAffect). user_affect is legacy unused on live path — not merged into monday_emotion."""
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
                response = self.engine.get_emotional_response(
                    user_input, str(message.get('user_id') or 'default'))
                
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
                    'appraisal': dict(getattr(self.engine, 'last_appraisal', {}) or {}),
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

            elif msg_type == 'social_read':
                # Social context's read of each moment (what kind of move it was).
                read = message.get('content') if isinstance(message.get('content'), dict) else message
                self.engine.__dict__.setdefault('_social_reads', {})[str(read.get('user_id') or 'default')] = dict(read)
                return {'status': 'success', 'content': {'heard': True}}

            elif msg_type == 'reply_outcome':
                # Language says whether she managed to reply: doing things right
                # or failing is part of how she feels.
                if message.get('failed'):
                    kind = 'reply_failed'
                elif message.get('used_memory'):
                    kind = 'answered_from_memory'
                else:
                    kind = 'reply_ok'
                felt = self.engine.inner.happen(kind)
                felt += self.engine.inner.moment_feelings(
                    {"kind": kind, "social_move": bool(message.get('social_move'))})
                self.engine.feel(felt)
                self.engine._replied_last = not message.get('failed')
                self.engine._sync_from_core_affect(trigger=kind)
                return {'status': 'success', 'content': {'felt': self.engine.inner.last_feeling}}

            elif msg_type == 'didnt_understand':
                # Language couldn't make sense of what he said.
                # (Language reads after Emotion has felt the moment, so she feels it now.)
                felt = self.engine.inner.moment_feelings({"didnt_understand": True})
                self.engine.feel(felt)
                self.engine._sync_from_core_affect(trigger="didnt_understand")
                return {'status': 'success', 'content': {'felt': self.engine.inner.last_feeling}}

            elif msg_type == 'remembered':
                # A memory came back with the feeling it had: she feels some of it again.
                body = message.get('content') if isinstance(message.get('content'), dict) else message
                felt = []
                # Only memories from before this conversation bring their feeling
                # back, and only the first one: otherwise what she felt a minute
                # ago comes back and feeds on itself.
                older = [m for m in (body.get('memories') or [])
                         if self.engine._days_ago(m.get('timestamp')) * 1440 > 10][:1]
                for memory in older:
                    for past in (memory.get('feelings') or [])[-1:]:
                        proto = self.engine._feeling_shape(str(past.get('emotion') or ''))
                        if proto:
                            felt += self.engine.inner.remember_feeling(
                                proto[0] * float(past.get('intensity') or 0.5),
                                proto[1] * float(past.get('intensity') or 0.5),
                                str(memory.get('content') or ''))
                            days = self.engine._days_ago(memory.get('timestamp'))
                            felt += self.engine.inner.memory_feelings(
                                proto[0], days, memory.get('role') == 'user')
                self.engine.feel(felt)
                return {'status': 'success', 'content': {'remembered_feelings': len(felt)}}

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

            valence = float(self.engine.core_affect.valence)  # her real valence, not a list of names

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
                source='emotion',
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
