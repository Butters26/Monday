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
    Precedence: explicit structured → AppraisalEngine → semantic → keyword → neutral.
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
        'success':     'unknown',  # event≠user emotion; no evidence → unknown (not proud/happy/neutral)
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
          'fired me', 'not good enough', "didn't pick me", "wasn't chosen",
          'nobody wants me', 'wants me around', "doesn't want me", 'dont want me',
          "i'm sad", 'i am sad', 'feel sad', 'feeling sad', 'i feel sad'], 'rejection', 0.65),
        # Loss / disappearance
        (['died', 'passed away', 'lost my', 'grief', 'mourning', 'funeral', 'gone forever',
          'will never see', 'lost everything', 'miscarriage', 'accident killed',
          'vanished', 'disappeared', 'went missing', 'is missing', 'are missing',
          'has gone missing', 'missing person'], 'loss', 0.85),
        # Harm / hurt (includes insults / hate aimed at Monday or the listener)
        (['hurt me', 'hit me', 'attacked', 'abused', 'mistreated', 'treated me like garbage',
          'treated me like trash', 'treated me like dirt', 'made me feel worthless',
          'made me feel stupid', 'humiliated', 'degraded', 'screamed at me', 'yelled at me',
          'i hate you', 'hate you', 'hate monday', 'despise you', 'despise monday',
          'i despise you', 'loath you', 'loathe you', 'you suck', 'you are worthless',
          "you're worthless", 'you are stupid', "you're stupid", 'you idiot', 'fuck you',
          'screw you', 'really hurt', 'that hurt', 'hurt my feelings', 'that really hurt',
          'embarrassed me', 'humiliated me'], 'harm', 0.80),
        # Threat / fear
        (['threatened', 'going to hurt', 'going to kill', 'warned me', 'scared of',
          "don't feel safe", 'feel unsafe', 'in danger', 'i am terrified', "i'm terrified",
          'i am scared', "i'm scared", 'i am afraid', "i'm afraid", 'cannot sleep',
          "can't sleep", 'can not sleep', 'panic', 'panicking',
          "i'm worried", 'i am worried', 'feel worried', 'bad feeling',
          'going to go wrong', 'feel uneasy', 'have a bad feeling'], 'threat', 0.75),
        # Unfairness
        (['not fair', "isn't fair", 'unfair', 'unfairly', 'should not have', 'got away with',
          'blamed me for', 'scapegoated', 'punished for something', 'wrong person',
          "didn't do anything wrong", 'not my fault', 'screwed over', 'got screwed',
          'except me', 'left out', 'ripped off', 'double standard', 'treated differently'], 'unfairness', 0.60),
        # Conflict
        (['fight with', 'argument with', 'argued with', 'yelling at each other',
          'screaming at each other', 'falling out', 'clash with', 'tension with',
          'not speaking to', 'on bad terms', 'mad at you', 'angry at you',
          'pissed at you', 'hate talking to you',
          "i'm angry", 'i am angry', "i'm furious", 'i am furious', "i'm mad", 'i am mad',
          'fed up', 'pissed off', 'pissing me off', 'had enough', 'so angry'], 'conflict', 0.55),
        # Criticism
        (['criticized', 'told me i was wrong', 'called me out', 'said i did it wrong',
          'pointed out my mistake', "doesn't think i'm good",
          'talked down to me', 'condescending'], 'criticism', 0.45),
        # Success
        (['got the job', 'got promoted', 'passed the exam', 'finished it', 'won',
          'succeeded', 'accomplished', 'completed', 'finally did it', 'pulled it off',
          'graduated', 'accepted', 'got in', 'landed the',
          "i'm proud", 'i am proud', 'proud of', 'happy with how', 'really happy with',
          'happy with how that', 'actually relieved', "i'm relieved", 'i am relieved'], 'success', 0.65),
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

    # Negation phrase patterns (applied after masking event idioms that contain "not")
    _NEGATION_PHRASES: List[str] = [
        "not ", "n't ", "never ", "no longer ", "don't ", "didn't ", "won't ",
        "wasn't ", "isn't ", "haven't ", "can't ", "couldn't ",
    ]

    # Event idioms where "not" is part of the phrase, NOT logical negation of the claim.
    # Masking these prevents "not fair" / "not interested" from crushing appraisal severity.
    _NEGATION_IDIOMS: List[str] = [
        'not fair', "isn't fair", 'not interested', 'not good enough',
        'not my fault', 'not speaking to', "didn't do anything wrong",
        'should not have', "don't feel safe", 'not safe',
    ]

    # Sarcasm markers
    _SARCASM_MARKERS: List[str] = [
        'great, thanks', 'oh great', 'oh wonderful', 'yeah right', 'sure thing',
        'totally fine', 'absolutely fine', 'oh sure', 'oh wow', 'how lovely',
        'how wonderful', 'how nice', 'how great', 'oh perfect', 'just perfect',
        'just great', 'just wonderful', 'oh fantastic', '/s',
    ]

    # Patterns indicating Monday is the target.
    # Prefer space-padded forms so end-of-string "you" / "monday" still match.
    _MONDAY_TARGET: List[str] = [
        ' you ', ' your ', " you're", " you've", " you'll", " you'd",
        ' you are', ' monday ', " monday's", ' monday',
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
        quoted_affect = self._has_quoted_self_report(tl)
        # Strip quoted speech so "He said I'm furious" is not treated as USER self-report.
        unquoted = self._strip_quoted_speech(tl)

        negated = self._detect_negation(unquoted)
        sarcasm = self._detect_sarcasm(tl)
        contrast_override = self._detect_contrastive_override(unquoted)
        explicit_emo, explicit_conf, contrast_emo = self._extract_explicit_user_emotion(unquoted)
        hist_emo, hist_conf = self._extract_historical_self_emotion(unquoted)
        returning_emo, returning_conf = self._extract_returning_emotion(unquoted)
        third_party_emo = self._extract_third_party_emotion(tl)
        resolution_signal = self._detect_resolution(unquoted)

        temporal = 'current'
        # Historical past ("I was furious at first / yesterday") is not current affect.
        if hist_emo and explicit_emo is None and not contrast_emo and not returning_emo:
            temporal = 'historical'
            explicit_emo, explicit_conf = None, 0.0  # do not treat as current self-report
        elif returning_emo:
            temporal = 'returning'
            if explicit_emo is None:
                explicit_emo, explicit_conf = returning_emo, returning_conf

        # If sarcasm, flip positive surface signals to negative
        effective_text = unquoted
        if sarcasm:
            for pos in ['great', 'wonderful', 'fantastic', 'perfect', 'lovely', 'fine']:
                effective_text = effective_text.replace(pos, '_sarcasm_')

        # Mask hypothetical / counterfactual affect so "thought I'd be furious" does not classify.
        effective_text = self._mask_hypotheticals(effective_text)
        # Mask resolved-threat phrasing so residual "threat" token does not re-fire threat.
        if resolution_signal:
            effective_text = self._mask_resolution_phrases(effective_text)

        directed_at_monday = self._directed_at_monday(tl)
        directed_at_user = self._directed_at_user(unquoted)
        # Third-party = positive evidence of another person as focus — NOT mere
        # absence of I/you (object/topic questions must not become third_party).
        third_party = (
            not directed_at_monday
            and not directed_at_user
            and (
                bool(third_party_emo)
                or self._has_third_party_person_ref(tl)
            )
        )

        event_type, base_severity = self._classify_event(effective_text)

        # Contrastive override ("but I'm actually relieved") wins over earlier affect naming for EVENT.
        contrast_affected = False
        if contrast_override:
            event_type, base_severity = contrast_override
            negated = False
            contrast_affected = True
        if contrast_emo:
            contrast_affected = True

        # Soft event from explicit CURRENT self-report when classifiers found nothing useful.
        if event_type == 'neutral' and explicit_emo and explicit_emo != 'neutral' and temporal != 'historical':
            soft = self._EXPLICIT_SOFT_EVENT.get(explicit_emo)
            if soft:
                event_type, base_severity = soft

        # Returning irritation / reopened affect → mild conflict if still neutral.
        if temporal == 'returning' and event_type == 'neutral' and returning_emo:
            soft = self._EXPLICIT_SOFT_EVENT.get(returning_emo, ('conflict', 0.35))
            event_type, base_severity = soft

        # Resolution: event clears toward neutral; do not re-escalate from residual tokens.
        if resolution_signal:
            if event_type in ('threat', 'harm', 'conflict', 'rejection', 'criticism'):
                event_type = 'neutral'
                base_severity = min(base_severity, 0.12)
            if explicit_emo is None and re.search(r"\bi(?:'m| am) (?:fine|okay|ok|better|calm)\b", unquoted):
                explicit_emo, explicit_conf = 'neutral', 0.88

        # If negated, drop severity and shift event_type toward neutral
        if negated and event_type not in ('loss',):  # can't negate a death
            base_severity *= 0.25
            if base_severity < 0.15:
                event_type = 'neutral'

        # Severity modifiers: intensifiers, repetition in history
        severity = self._adjust_severity(base_severity, tl, event_type, relationship_history, sensitivity_map)

        # PAD delta for Monday based on who is affected
        pad_delta = self._compute_monday_pad(event_type, severity, directed_at_monday, directed_at_user)
        if resolution_signal:
            # Soft positive recovery nudge for Monday INTERNAL (not user-affect cast).
            pad_delta = (
                max(-0.05, pad_delta[0] * 0.15 + 0.15),
                max(0.0, pad_delta[1] * 0.2),
                pad_delta[2] * 0.3 + 0.05,
            )

        # Event-mapped user emotion (kept separate from explicit self-report)
        event_inferred, event_conf = self._infer_user_emotion(
            event_type, directed_at_user, severity, negated
        )
        # Explicit CURRENT self-report outranks event-inferred USER emotion.
        if temporal == 'historical' and hist_emo:
            # Historical naming is recorded via temporal; current USER emotion stays unknown.
            user_emotion, user_conf = 'unknown', 0.25
            event_inferred = hist_emo  # park historical label in event_inferred for continuity layer
        elif explicit_emo is not None:
            user_emotion, user_conf = explicit_emo, explicit_conf
        elif third_party and third_party_emo:
            # Third-party affect ≠ USER affect
            user_emotion, user_conf = 'unknown', 0.2
        else:
            user_emotion, user_conf = event_inferred, event_conf

        # Quoted self-report speech must not become USER emotion.
        if quoted_affect and temporal == 'current' and not directed_at_user:
            if user_emotion in ('angry', 'furious', 'sad', 'scared', 'worried', 'happy'):
                user_emotion, user_conf = 'unknown', 0.2
                if event_type == 'conflict' and severity < 0.6:
                    event_type, severity = 'neutral', 0.1
                    pad_delta = (0.0, 0.0, 0.0)

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
            explicit_user_emotion=explicit_emo,
            contrast_affected=contrast_affected,
            event_inferred_emotion=event_inferred if temporal != 'historical' else (hist_emo or event_inferred),
            temporal=temporal,
            third_party_emotion=third_party_emo,
            resolution_signal=resolution_signal,
            quoted_affect=quoted_affect,
        )

    # --------------- Private classifiers ---------------

    def _strip_quoted_speech(self, tl: str) -> str:
        """Remove quoted spans so reported speech is not treated as USER self-report.
        Only strip double-quoted spans (and space-bounded single-quoted spans) so
        contractions like I'm / don't are preserved.
        """
        out = re.sub(r'"[^"]*"', ' ', tl)
        out = re.sub(r"(^|[\s])'([^']{2,})'([\s,.!?]|$)", r'\1 \3', out)
        return out

    def _has_quoted_self_report(self, tl: str) -> bool:
        return bool(re.search(
            r'["\'].{0,60}\bi(?:\'m| am)\s+(?:so |really )?(?:angry|furious|mad|sad|scared|afraid|worried|happy|hurt)',
            tl, re.I,
        ))

    def _detect_resolution(self, tl: str) -> bool:
        patterns = [
            r'\bthreat is gone\b', r'\bdanger (?:is |has )?passed\b',
            r'\bno longer (?:a )?(?:threat|problem|issue|danger)\b',
            r'\bapologi[sz]ed\b', r'\bfeel(?:ing)? better\b',
            r'\bi(?:\'m| am) fine now\b', r'\bi(?:\'m| am) okay now\b',
            r'\bi(?:\'m| am) (?:fine|okay|ok|better) now\b',
        ]
        return any(re.search(p, tl) for p in patterns)

    def _mask_resolution_phrases(self, tl: str) -> str:
        out = tl
        for pat in [
            r'\bthe threat is gone\b', r'\bthreat is gone\b',
            r'\bdanger (?:is |has )?passed\b',
            r'\bno longer (?:a )?(?:threat|problem|issue|danger)\b',
        ]:
            out = re.sub(pat, ' ', out)
        return out

    def _extract_historical_self_emotion(self, tl: str) -> Tuple[Optional[str], float]:
        """Past-tense self affect that is not the speaker's current state."""
        # Hypothetical fear about another's reaction is not historical self-affect.
        if re.search(r"\bi was (?:afraid|scared|worried) (?:she|he|they|that)\b", tl):
            return None, 0.0
        m = re.search(
            r"\bi was\s+(?:so |really |completely |totally |very )?"
            r"(angry|furious|mad|livid|sad|heartbroken|scared|afraid|worried|hurt|happy|proud|annoyed)"
            r"(?:\s+(?:at first|yesterday|earlier|before|then|last night))?\b",
            tl,
        )
        if not m:
            return None, 0.0
        word = m.group(1)
        emo = self._SELF_REPORT_CANON.get(word, word)
        return emo, 0.72

    def _extract_returning_emotion(self, tl: str) -> Tuple[Optional[str], float]:
        """Reopened / returning affect after a calmer period."""
        if re.search(r'\b(?:thinking about it again|coming back|coming up again)\b', tl):
            if re.search(r'\bannoy', tl) or re.search(r'\birritat', tl):
                return 'annoyed', 0.78
            if re.search(r'\bang', tl) or re.search(r'\bmad\b', tl):
                return 'angry', 0.78
            return 'annoyed', 0.70
        if re.search(r'\bstarting to (?:annoy|irritate|anger|bother)\b', tl):
            return 'annoyed', 0.80
        if re.search(r'\b(?:getting|feeling) (?:mad|angry|annoyed|upset) again\b', tl):
            return 'angry', 0.80
        if re.search(r'\bis starting to annoy me\b', tl):
            return 'annoyed', 0.80
        return None, 0.0

    def _extract_third_party_emotion(self, tl: str) -> Optional[str]:
        """Someone else's affect — never USER affect."""
        # Mask hypothetical attributions ("I thought he was angry")
        scan = re.sub(
            r"\bi thought (?:she|he|they) was\b.{0,20}",
            ' ',
            tl,
        )
        scan = re.sub(
            r"\bi was (?:afraid|scared|worried) (?:she|he|they) would\b.{0,30}",
            ' ',
            scan,
        )
        # Current-state supersession for third party: "scared yesterday but okay now"
        if re.search(r"\b(?:she|he|they)\b.{0,40}\b(?:scared|afraid|worried|angry|sad|upset)\b.{0,40}\b(?:but |however ).{0,20}\b(?:okay|ok|fine|better|calm)\b", scan):
            return 'calm'
        m = re.search(
            r"\b(?:she|he|they|ariana)\s+(?:is|was|thinks)\s+(?:so |really |completely )?"
            r"(worried|angry|furious|mad|scared|afraid|sad|upset|hurt|annoyed|calm)\b",
            scan, re.I,
        )
        if m:
            word = m.group(1).lower()
            return self._SELF_REPORT_CANON.get(word, word)
        m = re.search(
            r"\b(?:she|he|they)'s\s+(?:so |really )?(worried|angry|furious|mad|scared|afraid|sad|upset|hurt)\b",
            scan, re.I,
        )
        if m:
            word = m.group(1).lower()
            return self._SELF_REPORT_CANON.get(word, word)
        return None

    def _detect_negation(self, tl: str) -> bool:
        # Mask event idioms so "not fair" etc. are not treated as full negation.
        masked = tl
        for idiom in self._NEGATION_IDIOMS:
            if idiom in masked:
                masked = masked.replace(idiom, ' ' + ('_' * max(1, len(idiom))) + ' ')
        return any(neg in masked for neg in self._NEGATION_PHRASES)

    def _detect_sarcasm(self, tl: str) -> bool:
        # Punctuation-based: positive word followed by '?' or ending '...'
        for marker in self._SARCASM_MARKERS:
            if marker in tl:
                return True
        # Polite positive words after clear negative framing
        if re.search(r'\b(terrible|awful|horrible|worst)\b.{0,30}\b(great|fine|okay|wonderful)\b', tl):
            return True
        return False

    def _mask_hypotheticals(self, tl: str) -> str:
        """Remove counterfactual affect clauses so they do not drive event type."""
        patterns = [
            r"\bi thought i(?:'d| would) be \w+",
            r"\bi expected to (?:be|feel) \w+",
            r"\bi was going to (?:be|feel) \w+",
            r"\bi figured i(?:'d| would) (?:be|feel) \w+",
        ]
        out = tl
        for pat in patterns:
            out = re.sub(pat, ' ', out)
        return out

    # Canonical explicit self-report words → user emotion (not event type).
    _SELF_REPORT_CANON: Dict[str, str] = {
        'happy': 'happy', 'glad': 'happy', 'joyful': 'happy',
        'angry': 'angry', 'furious': 'angry', 'mad': 'angry', 'livid': 'angry',
        'sad': 'sad', 'heartbroken': 'sad', 'miserable': 'sad', 'depressed': 'sad',
        'scared': 'scared', 'afraid': 'scared', 'terrified': 'scared',
        'worried': 'worried', 'anxious': 'worried', 'concerned': 'worried',
        'relieved': 'relieved',
        'proud': 'proud',
        'exhausted': 'exhausted', 'tired': 'exhausted',
        'hurt': 'hurt',
        'annoyed': 'annoyed', 'irritated': 'annoyed',
        'fine': 'neutral', 'okay': 'neutral', 'ok': 'neutral', 'better': 'neutral',
        'calm': 'calm',
    }
    # After "but" these name a non-affect state and do not override prior explicit emotion.
    _CONTRAST_NON_OVERRIDE = frozenset({'busy', 'hungry', 'sleepy'})

    # Soft event when appraisal is otherwise neutral but user explicitly self-reports.
    _EXPLICIT_SOFT_EVENT: Dict[str, Tuple[str, float]] = {
        'happy': ('affection', 0.45),
        'proud': ('success', 0.55),
        'angry': ('conflict', 0.55),
        'sad': ('rejection', 0.55),
        'scared': ('threat', 0.65),
        'worried': ('threat', 0.55),
        'relieved': ('success', 0.55),
        'hurt': ('harm', 0.65),
        'exhausted': ('neutral', 0.25),
        'annoyed': ('conflict', 0.40),
        'calm': ('neutral', 0.2),
    }

    def _detect_contrastive_override(self, tl: str) -> Optional[Tuple[str, float]]:
        """
        Later clause wins when speaker corrects a prior expected emotion.
        e.g. "I thought I'd be furious, but I'm actually relieved"
        Event type only — user emotion is handled by _extract_explicit_user_emotion.
        """
        m = re.search(r"\bbut i(?:'m| am)(?: actually)? (\w+)(?: now)?\b", tl)
        if not m:
            return None
        word = m.group(1)
        if word in self._CONTRAST_NON_OVERRIDE:
            return None
        positive = {
            'relieved': ('success', 0.55),
            'happy': ('success', 0.55),
            'fine': ('neutral', 0.15),
            'okay': ('neutral', 0.15),
            'ok': ('neutral', 0.15),
            'calm': ('neutral', 0.15),
            'better': ('success', 0.45),
            'proud': ('success', 0.55),
            'grateful': ('support', 0.50),
        }
        if word in positive:
            return positive[word]
        return None

    def _extract_explicit_user_emotion(self, tl: str) -> Tuple[Optional[str], float, bool]:
        """
        Explicit self-reported USER emotion (I'm happy/angry/sad/…).
        Returns (emotion, confidence, contrast_used).
        Corrective contrast after 'but' outranks earlier naming / hypotheticals.
        Negation of a self-emotion → neutral. Does not collapse into event type.
        """
        # 1) Corrective / current-state contrast ("but I'm actually relieved", "but I'm fine now")
        m = re.search(r"\bbut i(?:'m| am)(?: actually)? (\w+)(?: now)?\b", tl)
        if m:
            word = m.group(1)
            if word in self._CONTRAST_NON_OVERRIDE:
                pass  # additive contrast — keep earlier explicit if any
            elif word in self._SELF_REPORT_CANON:
                return self._SELF_REPORT_CANON[word], 0.92, True

        # 2) Negated self-emotion ("I'm not angry", "I'm not sad anymore", "I'm not happy about")
        neg = re.search(
            r"\bi(?:'m| am) not (?:so |really |completely |totally |very )?(\w+)",
            tl,
        )
        if neg:
            word = neg.group(1)
            if word in self._SELF_REPORT_CANON and self._SELF_REPORT_CANON[word] != 'neutral':
                return 'neutral', 0.88, False

        # 3) Affirmative self-report (hypotheticals masked so "thought I'd be furious" is ignored)
        scan = self._mask_hypotheticals(tl)
        # "Now I'm mostly just hurt" / "I'm hurt by it"
        hurt = re.search(
            r"\bi(?:'m| am)\s+(?:now\s+)?(?:mostly |just |mostly just |really |so )?"
            r"(hurt)\b",
            scan,
        )
        if hurt:
            return 'hurt', 0.90, False
        aff = re.search(
            r"\bi(?:'m| am)\s+(?:so |really |completely |totally |very |mostly |just )?"
            r"(happy|glad|joyful|angry|furious|mad|livid|sad|heartbroken|depressed|miserable|"
            r"scared|afraid|terrified|worried|anxious|concerned|relieved|proud|exhausted|tired|"
            r"hurt|annoyed|irritated|fine|okay|ok|calm)\b",
            scan,
        )
        if aff:
            return self._SELF_REPORT_CANON[aff.group(1)], 0.90, False
        feel = re.search(
            r"\bi feel\s+(?:so |really )?"
            r"(happy|glad|angry|furious|mad|sad|heartbroken|depressed|miserable|"
            r"scared|afraid|worried|anxious|proud|relieved|exhausted|tired|hurt|better)\b",
            scan,
        )
        if feel:
            word = feel.group(1)
            if word == 'better':
                return 'neutral', 0.85, False
            return self._SELF_REPORT_CANON[word], 0.85, False
        # Bare continuity phrases: "Still glad I did it" / "glad I finished"
        bare = re.search(
            r"\b(?:still |also )?(glad|happy|proud)\b(?:\s+i\b|\s+about\b|\s+i\s)",
            scan,
        )
        if bare:
            return self._SELF_REPORT_CANON[bare.group(1)], 0.82, False
        return None, 0.0, False

    def _directed_at_monday(self, tl: str) -> bool:
        # Pad so trailing "you" / "monday" (end of string) count as targets.
        padded = f' {tl.strip()} '
        return any(p in padded for p in self._MONDAY_TARGET)

    def _directed_at_user(self, tl: str) -> bool:
        # Normalize trailing punctuation so "annoy me." still counts as user-directed.
        norm = re.sub(r'[.!?,;:]+', ' ', tl.strip())
        padded = f' {norm} '
        if any(p in norm for p in self._USER_SUBJECT):
            return True
        return any(tok in padded for tok in (' me ', ' myself ', ' i '))

    def _has_third_party_person_ref(self, tl: str) -> bool:
        """Positive evidence of another person — pronouns or name+affect/belief.
        Absence of I/you alone is NOT third-party (object/topic questions stay non-third-party).
        """
        if re.search(r"\b(?:she|he|they|him|her|them|his|hers|their)\b", tl):
            return True
        # Name-like token + affect state (e.g. "ariana is worried")
        if re.search(
            r"\b[a-z]{3,}\s+(?:is|was)\s+(?:so |really |completely )?"
            r"(?:worried|angry|furious|mad|scared|afraid|sad|upset|hurt|annoyed|calm|happy|fine|okay|ok)\b",
            tl,
        ):
            return True
        # Name-like token + belief verb (e.g. "ariana thinks") — not "I think"
        if re.search(r"\b[a-z]{3,}\s+thinks\b", tl) and not re.search(r"\bi\s+think", tl):
            return True
        return False

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
        # Negation / near-zero severity → neutral (claim of non-affect / cleared).
        # Some events (e.g. success) map to 'unknown': event known, user emotion not evidenced.
        if negated or severity < 0.15:
            return 'neutral', 0.2
        base_emotion = self._USER_EMOTION_BY_EVENT.get(event_type, 'neutral')
        if base_emotion == 'unknown':
            return 'unknown', 0.15
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

        # Rare residual color from unresolved appraisals (very low rate; no spam loop)
        if self._unresolved_appraisals and self._rng.random() < 0.06:
            et, sev, _ts = max(self._unresolved_appraisals, key=lambda x: x[1])
            bias = self._appraisal_engine._EVENT_PAD.get(et, (0.0, 0.0, 0.0))
            scale = min(0.15, 0.08 * sev)
            self.pad = PAD(
                v=max(-1.0, min(1.0, self.pad.v + bias[0] * scale)),
                a=max(-1.0, min(1.0, self.pad.a + bias[1] * scale)),
                d=max(-1.0, min(1.0, self.pad.d + bias[2] * scale)),
            )

        # --- Text-understanding pipeline: AppraisalEngine primary, semantic support, keyword supplement ---
        understanding = self._understand_emotional_text(
            user_input,
            relationship_history=self._event_history[-20:],
            sensitivity_map=self._event_sensitivity,
        )
        self._last_understanding = understanding
        appraisal = understanding.final_appraisal or understanding.appraisal
        self._apply_appraisal(appraisal)

        # Keyword cues remain supplement-only (resonance nudge); appraisal already applied.
        cues = understanding.keyword_cues
        self._calculate_emotional_resonance(cues)
        context = self.assess_emotional_context(user_input)
        if self.emotional_memories:
            self.process_trauma_memory(self.emotional_memories[-1])
        memory_influence = self._get_memory_influence(user_input)
        base = self._generate_advanced_emotional_response(user_input, memory_influence)
        # Prefer combined understanding emotion for response enhancement
        predicted = {understanding.inferred_emotion: understanding.confidence}
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

    def appraise_internal_event(self, event: InternalEventAppraisal) -> None:
        """
        Appraise an autonomously recalled memory or thought through the existing PAD pipeline.

        Safety guarantees:
        - Cooldown: the same content fingerprint cannot be appraised more than once per
          INTERNAL_COOLDOWN_SEC (default 120 s).
        - Loop guard: if the same fingerprint appears more than once in the last-20 history,
          the call is silently dropped to break any self-reinforcing chain.
        - Intensity cap: internal events are dampened to at most 60 % of the PAD delta a
          live message of the same type would produce. Resolved memories are further halved.
        - All actual PAD / emotion-switch logic runs through the unchanged _apply_appraisal.
        """
        fingerprint = event.content[:80].lower().strip()

        # --- Loop guard ---
        history_list = list(self._internal_event_history)
        if history_list.count(fingerprint) >= 2:
            self._log(f"[internal_appraisal] loop-guard suppressed: {fingerprint[:40]!r}")
            return

        # --- Cooldown ---
        last_appraised = self._internal_event_cooldowns.get(fingerprint, 0.0)
        if time.time() - last_appraised < self.INTERNAL_COOLDOWN_SEC:
            return

        # --- Run appraisal through the existing engine ---
        appraisal = self._appraisal_engine.appraise(
            event.content,
            relationship_history=self._event_history[-20:],
            sensitivity_map=self._event_sensitivity,
        )

        # --- Dampening factor ---
        # Age: decays toward 0.2 over 1 hour; floors at 0.2 so old memories still colour mood.
        age_factor = max(0.2, 1.0 - (event.memory_age_seconds / 3600.0) * 0.8)
        # Relevance: caller's 0-1 estimate.
        relevance_factor = max(0.1, min(1.0, event.relevance))
        # Resolved memories are much less impactful.
        resolved_factor = 0.5 if event.resolved else 1.0
        # If prior appraisal matches and it was resolved, reduce further to near-neutral.
        if (event.resolved
                and event.prior_appraisal_event_type is not None
                and event.prior_appraisal_event_type == appraisal.event_type):
            resolved_factor = 0.25

        dampening = age_factor * relevance_factor * resolved_factor
        # Hard cap: internal events ≤ 60 % of a live message's PAD delta.
        dampening = min(dampening, 0.60)

        # Apply dampening to the PAD delta and severity on the appraisal result.
        dv, da, dd = appraisal.monday_pad_delta
        appraisal.monday_pad_delta = (dv * dampening, da * dampening, dd * dampening)
        appraisal.severity = round(appraisal.severity * dampening, 3)

        # --- Push through the unchanged appraisal pipeline ---
        self._apply_appraisal(appraisal)

        # --- Record cooldown and history ---
        self._internal_event_cooldowns[fingerprint] = time.time()
        self._internal_event_history.append(fingerprint)
        # Prune stale cooldown entries (older than 2× the cooldown window) to avoid unbounded growth.
        cutoff = time.time() - self.INTERNAL_COOLDOWN_SEC * 2
        self._internal_event_cooldowns = {
            fp: ts for fp, ts in self._internal_event_cooldowns.items() if ts > cutoff
        }
        self._log(
            f"[internal_appraisal] source={event.source} event={appraisal.event_type} "
            f"sev={appraisal.severity:.3f} damp={dampening:.2f} → {self.current_emotion.value}"
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

    # --------------- Appraisal-driven core ---------------

    def _apply_appraisal(self, appraisal: AppraisalResult) -> None:
        """
        Central method: takes an AppraisalResult and drives Monday's emotion through the
        PAD pipeline. Also updates user affect model, event history, learning, and persistence.
        """
        self._last_appraisal = appraisal
        self._update_internal_from_time(dt=1.0)
        self._update_attachment_from_input(appraisal.raw_text)
        self._update_attachment_from_appraisal(appraisal)
        self._update_needs_from_appraisal(appraisal)

        # 1. Update user affect model (multi-turn continuity; USER ≠ Monday INTERNAL)
        prev_ua = self._user_affect
        prev_emo = prev_ua.inferred_emotion
        new_emo = appraisal.user_inferred_emotion
        new_conf = appraisal.user_confidence
        temporal = getattr(appraisal, 'temporal', 'current') or 'current'
        tp_emo = getattr(appraisal, 'third_party_emotion', None)
        resolution = bool(getattr(appraisal, 'resolution_signal', False))

        if temporal == 'historical':
            # Past naming is not current; park historical, keep prior current if any.
            hist_label = appraisal.event_inferred_emotion or new_emo
            if prev_emo not in ('neutral', 'unknown', '') and prev_ua.confidence >= 0.25:
                cur_emo, cur_conf = prev_emo, max(0.25, prev_ua.confidence * 0.95)
            else:
                cur_emo, cur_conf = 'unknown', 0.25
            previous_emotion = hist_label if hist_label not in ('neutral', 'unknown', None) else prev_emo
            new_emo, new_conf = cur_emo, cur_conf
        elif temporal == 'returning':
            previous_emotion = prev_emo
            # returning emotion already in appraisal.user_inferred_emotion
        elif resolution or (
            appraisal.explicit_user_emotion in ('neutral', 'calm')
            and appraisal.user_inferred_emotion in ('neutral', 'calm')
        ):
            previous_emotion = prev_emo
            # Allow clear to neutral/calm — do not keep strongest-ever
        elif (
            new_emo in ('neutral', 'unknown')
            and new_conf < 0.35
            and prev_emo not in ('neutral', 'unknown', '')
            and prev_ua.confidence >= 0.30
        ):
            # Weak/empty turn: carry forward if anaphoric/continuity cue, else decay (not lock).
            if self._has_continuity_cue(appraisal.raw_text):
                previous_emotion = prev_emo
                new_emo = prev_emo
                new_conf = max(0.28, prev_ua.confidence * 0.85)
            elif self._is_topic_shift_neutral(appraisal.raw_text):
                previous_emotion = prev_emo
                new_emo, new_conf = 'unknown', 0.15
            else:
                previous_emotion = prev_emo
                # Mild decay toward unknown rather than hard lock on prior peak
                new_emo, new_conf = 'unknown', 0.18
        else:
            previous_emotion = prev_emo

        # Prefer third-party emotion from this turn; else retain across nearby
        # turns when pronoun/coreference keeps the same third-party focus.
        if tp_emo is None and prev_ua.third_party_emotion:
            tl_raw = (appraisal.raw_text or '').lower()
            if (
                self._has_continuity_cue(appraisal.raw_text)
                or (
                    bool(getattr(appraisal, 'third_party', False))
                    and self._appraisal_engine._has_third_party_person_ref(tl_raw)
                )
            ):
                tp_emo = prev_ua.third_party_emotion
                # Reflect carry on this turn's appraisal meta (no giant entity memory).
                try:
                    appraisal.third_party_emotion = tp_emo
                except Exception:
                    pass
        if appraisal.third_party and tp_emo and new_emo in ('neutral', 'unknown') and appraisal.explicit_user_emotion is None:
            # Ensure USER is not overwritten by third-party naming
            if new_emo == 'neutral' and new_conf < 0.4:
                new_emo, new_conf = 'unknown', max(new_conf, 0.2)

        self._user_affect = UserAffectModel(
            inferred_emotion=new_emo,
            confidence=new_conf,
            inferred_need=self._infer_user_need(appraisal),
            last_updated=time.time(),
            previous_emotion=previous_emotion or 'neutral',
            temporal=temporal,
            last_event_type=appraisal.event_type,
            third_party_emotion=tp_emo,
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
        if getattr(appraisal, 'resolution_signal', False):
            # Resolution language clears stale unresolved (USER calm ≠ lock Monday INTERNAL)
            self._unresolved_appraisals = []
            self._attention_bias = None
            # Soften Monday INTERNAL intensity when threat/hurt resolved
            self.emotional_intensity = max(0.15, self.emotional_intensity * 0.55)
        elif (
            appraisal.explicit_user_emotion in ('happy', 'proud', 'relieved', 'calm')
            and appraisal.user_confidence >= 0.7
            and appraisal.event_type in ('affection', 'success', 'celebration', 'support', 'gift')
        ):
            # Positive self-report flip clears lingering negative unresolved
            self._unresolved_appraisals = []
            self._attention_bias = None
        elif appraisal.event_type in _NEGATIVE_EVENTS and appraisal.severity >= 0.4:
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

        # 7. Learn: update event-type sensitivity + trigger→emotion patterns
        self._update_event_sensitivity(appraisal)
        self._update_emotional_patterns(self.current_emotion, appraisal.raw_text)

        # 8. Store event to Notus for cross-session memory (graceful no-op if unsupported)
        try:
            result = self._query_lobe('notus', {
                'type': 'store_appraisal_event',
                'event_type': appraisal.event_type,
                'severity': appraisal.severity,
                'directed_at_monday': appraisal.directed_at_monday,
                'monday_emotion': self.current_emotion.value,
                'user_inferred_emotion': appraisal.user_inferred_emotion,
                'trigger': appraisal.raw_text[:200],
            })
            # Prefer no-op when Notus lacks the handler / returns error
            if result and result.get('status') == 'error':
                pass
        except Exception:
            pass

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

    # Explicit high-confidence self-report patterns only (supplement — not primary).
    _EXPLICIT_SELF_REPORTS: List[Tuple[str, str, float]] = [
        (r"\bi(?:'m| am)\s+(?:so |really |completely |totally |very )?(angry|furious|mad|livid)\b", 'anger', 0.85),
        (r"\bi(?:'m| am)\s+(?:so |really |completely |totally |very )?(sad|heartbroken|depressed|miserable)\b", 'sadness', 0.85),
        (r"\bi(?:'m| am)\s+(?:so |really |completely |totally |very )?(worried|concerned|anxious)\b", 'concern', 0.85),
        (r"\bi(?:'m| am)\s+(?:so |really |completely |totally |very )?(scared|afraid|terrified)\b", 'concern', 0.85),
        (r"\bi(?:'m| am)\s+(?:so |really |completely |totally |very )?(proud)\b", 'pride', 0.85),
        (r"\bi(?:'m| am)\s+(?:so |really |completely |totally |very )?(happy|glad|joyful|excited)\b", 'positive', 0.80),
        (r"\bi feel\s+(?:so |really )?(rejected|alone|hurt|sad|heartbroken|depressed|miserable)\b", 'sadness', 0.75),
        (r"\bi feel\s+(?:so |really )?(angry|furious|mad)\b", 'anger', 0.75),
        (r"\bi feel\s+(?:so |really )?(worried|scared|afraid|anxious)\b", 'concern', 0.75),
        (r"\bi feel\s+(?:so |really )?(proud|happy)\b", 'positive', 0.75),
        # High-confidence celebratory language (short list — not a general lexicon)
        (r"\b(?:wonderful|amazing|fantastic)\b(?:\s+\w+){0,3}\b(?:news|day|job|result|outcome)?", 'positive', 0.55),
    ]

    _CUE_NEGATION_WINDOW = re.compile(
        r"(?:\bnot\b|\bn'?t\b|\bnever\b|\bno longer\b)\s+(?:\w+\s+){0,3}"
        r"(?:angry|furious|mad|sad|heartbroken|depressed|worried|scared|afraid|proud|happy)",
        re.I,
    )
    _CUE_CONTRAST = re.compile(
        r"\b(?:but|however|though)\b.{0,40}\b(?:actually|really)?\s*"
        r"(?:relieved|fine|okay|ok|better|happy|calm|proud|grateful|exhausted|tired)\b",
        re.I,
    )
    _CUE_HYPOTHETICAL = re.compile(
        r"\bi thought i(?:'d| would) be\b|\bi expected to (?:be|feel)\b",
        re.I,
    )

    def _analyze_emotional_cues(self, text: str) -> Dict[str, float]:
        """
        Explicit self-report keyword SUPPLEMENT only.
        Not the primary path — AppraisalEngine (+ semantic) owns meaning.
        Negation / contrastive context suppresses misleading matches
        ("I'm not angry", "thought I'd be sad but relieved").
        """
        cues = {k: 0.0 for k in ['positive', 'negative', 'excitement', 'concern', 'anger', 'sadness', 'pride']}
        t = text.lower().strip()
        if not t:
            return cues

        # Suppress when local negation or contrastive override applies
        if self._CUE_NEGATION_WINDOW.search(t) or self._CUE_CONTRAST.search(t):
            return cues

        # Strip quotes + mask hypotheticals so reported/past speech does not nudge cues.
        scan = self._appraisal_engine._strip_quoted_speech(t)
        scan = self._appraisal_engine._mask_hypotheticals(scan)
        # Historical past self-report should not drive current cue tops
        if re.search(r"\bi was\s+(?:so |really )?(?:angry|furious|mad|sad|scared|afraid|worried|hurt)\b", scan):
            if not re.search(r"\b(?:now|but)\s+i(?:'m| am)\b", scan):
                return cues

        for pattern, key, strength in self._EXPLICIT_SELF_REPORTS:
            if re.search(pattern, scan):
                # Cap: supplement nudge, never dominates appraisal
                cues[key] = max(cues[key], min(0.2, strength * 0.22))
                if key == 'sadness':
                    cues['negative'] = max(cues['negative'], cues[key] * 0.5)
                if key == 'positive':
                    cues['excitement'] = max(cues['excitement'], cues[key] * 0.4)

        return cues

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

    # Meaning prototypes for semantic support (anchors — not proof-phrase special cases).
    # Meaning anchors for paraphrase support (general event senses — not smoke-test phrases).
    _SEMANTIC_EVENT_PROTOTYPES: Dict[str, List[str]] = {
        'unfairness': [
            'I was treated unfairly or unjustly',
            'others got a chance while I was excluded',
            'someone took advantage of me or cheated me',
            'I was cheated swindled or treated dishonestly',
            'this situation is unfair and unjust',
        ],
        'conflict': [
            'I am angry frustrated or fed up',
            'this is making me furious and pissed off',
        ],
        'rejection': [
            'I feel rejected unwanted or left out',
            'nobody wants me around and I feel sad',
            'I feel sad downhearted or unhappy',
        ],
        'harm': [
            'that hurt me emotionally and caused pain',
            'I was mistreated or harmed',
        ],
        'threat': [
            'I am worried scared or have a bad feeling something will go wrong',
            'I feel threatened or unsafe',
            'I feel uneasy or dread about what might happen',
        ],
        'success': [
            'I am proud happy and succeeded at what I did',
            'I accomplished my goal and it worked out',
            'I am happy with a good outcome',
            'I feel relieved that a stressful situation is over',
        ],
        'betrayal': [
            'someone betrayed my trust and lied to me',
        ],
        'loss': [
            'I lost someone or something important and feel grief',
        ],
    }
    _SEMANTIC_EMOTION_BY_EVENT = {
        'unfairness': 'angry', 'conflict': 'angry', 'rejection': 'sad', 'harm': 'hurt',
        'threat': 'scared', 'success': 'unknown', 'betrayal': 'angry', 'loss': 'sad',
        'affection': 'happy', 'support': 'grateful', 'celebration': 'excited',
        'criticism': 'worried', 'abandonment': 'sad', 'gift': 'happy', 'neutral': 'neutral',
    }

    def _semantic_emotion_support(self, text: str) -> Dict[str, Any]:
        """
        Optional meaning support via existing Notus embedding layer.
        Always returns a candidate when a best match exists; eligibility for
        primary use is gated by model_type. Basic hash embeddings have LOW
        authority — they may support agreeing appraisal but must not override
        a confident AppraisalEngine result (enforced in _understand_emotional_text).
        """
        result = {
            'used': False,
            'eligible': False,
            'event_type': None,
            'emotion': None,
            'confidence': 0.0,
            'model_type': self._embedding_model_type,
        }
        eng = self._get_embedding_engine()
        if eng is None:
            return result
        result['model_type'] = getattr(eng, 'model_type', self._embedding_model_type)
        self._embedding_model_type = result['model_type']

        # ST: usable paraphrase matching (MiniLM cosine scale ≠ basic hash).
        # Basic: noisy — keep high eligibility bar (do not lower casually).
        # ST primary ~0.50 / support ~0.42 calibrated so true paraphrases support
        # while weak wrong tops (e.g. third-party quotes ~0.48) stay ineligible as primary.
        if result['model_type'] == 'sentence_transformer':
            primary_threshold = 0.50
        elif result['model_type'] == 'basic':
            primary_threshold = 0.65  # very low authority; almost never primary
        else:
            primary_threshold = 0.99

        best_event = None
        best_score = 0.0
        try:
            for event_type, prototypes in self._SEMANTIC_EVENT_PROTOTYPES.items():
                for proto in prototypes:
                    sim = float(eng.calculate_similarity(text, proto))
                    if sim > best_score:
                        best_score = sim
                        best_event = event_type
        except Exception:
            return result

        if best_event and best_score >= 0.30:
            # Candidate always reported for diagnostics; used/eligible gated later.
            result['event_type'] = best_event
            result['emotion'] = self._SEMANTIC_EMOTION_BY_EVENT.get(best_event, 'neutral')
            result['confidence'] = round(min(0.9, best_score), 3)
            result['eligible'] = best_score >= primary_threshold
        return result

    def _understand_emotional_text(
        self,
        text: str,
        relationship_history: Optional[List[str]] = None,
        sensitivity_map: Optional[Dict[str, float]] = None,
    ) -> EmotionalUnderstanding:
        """
        Priority pipeline:
          (1) explicit structured/direct is outside this path (feel_emotion)
          (2) AppraisalEngine — primary for NL emotional events
              (explicit self-report outranks event-inferred USER emotion)
          (3) semantic meaning support where useful (basic = low authority)
          (4) keyword/cue explicit self-reports as supplement
          (5) neutral
        Not naive score summing — stronger higher-precedence source wins.
        """
        appraisal = self._appraisal_engine.appraise(
            text,
            relationship_history=relationship_history,
            sensitivity_map=sensitivity_map,
        )
        keyword_cues = self._analyze_emotional_cues(text)
        semantic = self._semantic_emotion_support(text)

        # Negation and contrast are independent:
        # contrast ("but I'm actually X") supersedes an earlier clause without being negation.
        # Only grammatical/logical negation ("I'm not angry") sets negation_affected.
        negation_affected = bool(appraisal.negated)
        if self._CUE_NEGATION_WINDOW.search(text.lower()):
            negation_affected = True
        contrast_affected = bool(appraisal.contrast_affected)
        if self._CUE_CONTRAST.search(text.lower()):
            contrast_affected = True

        primary = 'neutral'
        inferred = 'neutral'
        event_type = 'neutral'
        severity = 0.0
        confidence = 0.0
        final = appraisal
        semantic_used = False

        # Confident appraisal OR contrast-authored result is authoritative.
        appraisal_strong = (
            appraisal.event_type != 'neutral'
            and appraisal.severity >= 0.15
            and not (appraisal.negated and appraisal.severity < 0.2)
        )
        appraisal_authoritative = appraisal_strong or bool(appraisal.contrast_affected)

        def _with_user(base: AppraisalResult, user_emo: str, user_conf: float) -> AppraisalResult:
            return AppraisalResult(
                event_type=base.event_type,
                severity=base.severity,
                directed_at_monday=base.directed_at_monday,
                directed_at_user=base.directed_at_user,
                third_party=base.third_party,
                negated=base.negated,
                sarcasm_likely=base.sarcasm_likely,
                raw_text=base.raw_text,
                monday_pad_delta=base.monday_pad_delta,
                user_inferred_emotion=user_emo,
                user_confidence=user_conf,
                explicit_user_emotion=base.explicit_user_emotion,
                contrast_affected=base.contrast_affected,
                event_inferred_emotion=base.event_inferred_emotion,
                temporal=getattr(base, 'temporal', 'current'),
                third_party_emotion=getattr(base, 'third_party_emotion', None),
                resolution_signal=getattr(base, 'resolution_signal', False),
                quoted_affect=getattr(base, 'quoted_affect', False),
            )

        if appraisal_authoritative:
            primary = 'appraisal' if appraisal.event_type != 'neutral' else (
                'neutral' if (
                    appraisal.negated
                    or appraisal.user_inferred_emotion in ('neutral', 'unknown', None)
                ) else 'appraisal'
            )
            if appraisal.contrast_affected and appraisal.event_type == 'neutral':
                primary = 'neutral'
            inferred = appraisal.user_inferred_emotion
            # Tiny surface refinement if explicit path missed worried vs scared
            tl = text.lower()
            if (
                inferred == 'scared'
                and re.search(r"\bworried\b", tl)
                and not re.search(r"\b(scared|afraid|terrified)\b", tl)
                and not appraisal.explicit_user_emotion
            ):
                inferred = 'worried'
            event_type = appraisal.event_type
            severity = appraisal.severity
            confidence = max(appraisal.user_confidence, appraisal.severity if appraisal_strong else appraisal.user_confidence)
            final = appraisal if inferred == appraisal.user_inferred_emotion else _with_user(
                appraisal, inferred, appraisal.user_confidence
            )

            # Basic/ST semantic may SUPPORT agreeing appraisal; never override / never on conflict.
            sem_event = semantic.get('event_type')
            sem_conf = float(semantic.get('confidence') or 0.0)
            model = semantic.get('model_type') or self._embedding_model_type
            if sem_event and sem_event == event_type:
                # Basic: require stronger agreement; ST support bar on MiniLM cosine scale
                support_bar = 0.55 if model == 'basic' else 0.42
                if sem_conf >= support_bar and not appraisal.negated:
                    semantic_used = True
                    if model == 'sentence_transformer':
                        confidence = min(0.95, confidence + 0.05)
            # else: conflict or weak → IGNORE semantic (semantic_used stays False)

        elif (
            semantic.get('eligible')
            and semantic.get('event_type')
            and not appraisal.negated
            and not appraisal.contrast_affected
            and not appraisal.third_party
            and getattr(appraisal, 'temporal', 'current') != 'historical'
            and not getattr(appraisal, 'resolution_signal', False)
            and not getattr(appraisal, 'quoted_affect', False)
        ):
            # Semantic fills gaps only when eligible (ST normal bar; basic high bar).
            # Basic must not become primary on weak noisy matches.
            model = semantic.get('model_type') or self._embedding_model_type
            if model == 'basic' and float(semantic.get('confidence') or 0.0) < 0.65:
                # fall through to keyword below by not entering — handled via flag
                pass
            else:
                primary = 'semantic'
                event_type = semantic['event_type']
                inferred = semantic.get('emotion') or 'neutral'
                # Prefer explicit self-report for USER emotion even when event came from semantic
                if appraisal.explicit_user_emotion:
                    inferred = appraisal.explicit_user_emotion
                confidence = float(semantic.get('confidence') or 0.0)
                severity = max(0.35, confidence * 0.85)
                semantic_used = True
                pad = self._appraisal_engine._compute_monday_pad(
                    event_type, severity,
                    appraisal.directed_at_monday, appraisal.directed_at_user,
                )
                final = AppraisalResult(
                    event_type=event_type,
                    severity=round(severity, 3),
                    directed_at_monday=appraisal.directed_at_monday,
                    directed_at_user=appraisal.directed_at_user,
                    third_party=appraisal.third_party,
                    negated=False,
                    sarcasm_likely=appraisal.sarcasm_likely,
                    raw_text=text,
                    monday_pad_delta=pad,
                    user_inferred_emotion=inferred,
                    user_confidence=confidence,
                    explicit_user_emotion=appraisal.explicit_user_emotion,
                    contrast_affected=False,
                    event_inferred_emotion=self._appraisal_engine._USER_EMOTION_BY_EVENT.get(event_type, 'neutral'),
                )

        if primary == 'neutral' and not appraisal_authoritative and not semantic_used:
            # Keyword explicit self-report supplement
            cue_map = {
                'anger': 'angry', 'sadness': 'sad', 'concern': 'worried',
                'pride': 'proud', 'positive': 'happy', 'excitement': 'excited',
            }
            best_key = None
            best_val = 0.0
            for k, v in keyword_cues.items():
                if v > best_val and k in cue_map:
                    best_val = v
                    best_key = k
            if best_key and best_val > 0.05 and not negation_affected:
                primary = 'keyword'
                inferred = cue_map[best_key]
                if appraisal.explicit_user_emotion:
                    inferred = appraisal.explicit_user_emotion
                confidence = min(0.7, best_val * 3.5)
                event_type = {
                    'anger': 'conflict', 'sadness': 'rejection', 'concern': 'threat',
                    'pride': 'success', 'positive': 'affection', 'excitement': 'celebration',
                }.get(best_key, 'neutral')
                severity = max(0.3, confidence * 0.7)
                pad = self._appraisal_engine._compute_monday_pad(
                    event_type, severity,
                    appraisal.directed_at_monday, appraisal.directed_at_user,
                )
                final = AppraisalResult(
                    event_type=event_type,
                    severity=round(severity, 3),
                    directed_at_monday=appraisal.directed_at_monday,
                    directed_at_user=appraisal.directed_at_user,
                    third_party=appraisal.third_party,
                    negated=False,
                    sarcasm_likely=appraisal.sarcasm_likely,
                    raw_text=text,
                    monday_pad_delta=pad,
                    user_inferred_emotion=inferred,
                    user_confidence=confidence,
                    explicit_user_emotion=appraisal.explicit_user_emotion,
                    contrast_affected=False,
                    event_inferred_emotion=self._appraisal_engine._USER_EMOTION_BY_EVENT.get(event_type, 'neutral'),
                )
            else:
                primary = 'neutral'
                inferred = 'neutral' if appraisal.negated else appraisal.user_inferred_emotion
                if appraisal.negated and appraisal.severity < 0.2:
                    event_type = 'neutral'
                    severity = appraisal.severity
                    confidence = 0.2
                    final = AppraisalResult(
                        event_type='neutral',
                        severity=appraisal.severity,
                        directed_at_monday=appraisal.directed_at_monday,
                        directed_at_user=appraisal.directed_at_user,
                        third_party=appraisal.third_party,
                        negated=True,
                        sarcasm_likely=appraisal.sarcasm_likely,
                        raw_text=text,
                        monday_pad_delta=(0.0, 0.0, 0.0),
                        user_inferred_emotion='neutral',
                        user_confidence=0.2,
                        explicit_user_emotion=appraisal.explicit_user_emotion,
                        contrast_affected=appraisal.contrast_affected,
                        event_inferred_emotion='neutral',
                    )
                else:
                    event_type = appraisal.event_type
                    severity = appraisal.severity
                    confidence = appraisal.user_confidence
                    final = appraisal

        # Preserve continuity/ownership markers if a rebuilt final dropped them.
        if final is not None and final is not appraisal:
            final = AppraisalResult(
                event_type=final.event_type,
                severity=final.severity,
                directed_at_monday=final.directed_at_monday,
                directed_at_user=final.directed_at_user,
                third_party=final.third_party,
                negated=final.negated,
                sarcasm_likely=final.sarcasm_likely,
                raw_text=final.raw_text,
                monday_pad_delta=final.monday_pad_delta,
                user_inferred_emotion=final.user_inferred_emotion,
                user_confidence=final.user_confidence,
                explicit_user_emotion=final.explicit_user_emotion,
                contrast_affected=final.contrast_affected,
                event_inferred_emotion=final.event_inferred_emotion,
                temporal=getattr(final, 'temporal', None) or getattr(appraisal, 'temporal', 'current'),
                third_party_emotion=(
                    getattr(final, 'third_party_emotion', None)
                    or getattr(appraisal, 'third_party_emotion', None)
                ),
                resolution_signal=bool(
                    getattr(final, 'resolution_signal', False)
                    or getattr(appraisal, 'resolution_signal', False)
                ),
                quoted_affect=bool(
                    getattr(final, 'quoted_affect', False)
                    or getattr(appraisal, 'quoted_affect', False)
                ),
            )

        return EmotionalUnderstanding(
            appraisal=appraisal,
            semantic_event=semantic.get('event_type'),
            semantic_emotion=semantic.get('emotion'),
            semantic_confidence=float(semantic.get('confidence') or 0.0),
            semantic_used=semantic_used,
            keyword_cues=keyword_cues,
            primary_source=primary,
            inferred_emotion=inferred,
            event_type=event_type,
            severity=float(severity),
            confidence=float(confidence),
            negation_affected=negation_affected,
            contrast_affected=contrast_affected,
            explicit_emotion=appraisal.explicit_user_emotion,
            appraisal_inferred_emotion=appraisal.event_inferred_emotion or 'neutral',
            final_appraisal=final,
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
        Driven by text-understanding: AppraisalEngine primary, semantic support, keyword supplement.
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
        return {
            'current_emotion': self.engine.current_emotion.value,
            'emotion': self.engine.current_emotion.value,
            'intensity': self.engine.emotional_intensity,
            'resonance': self.engine.emotional_resonance,
            'pleasure': self.engine.pad.v,
            'arousal': self.engine.pad.a,
            'dominance': self.engine.pad.d,
            'pad': {
                'v': self.engine.pad.v,
                'a': self.engine.pad.a,
                'd': self.engine.pad.d,
            },
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
                    'pleasure': snap['pleasure'],
                    'arousal': snap['arousal'],
                    'dominance': snap['dominance'],
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
                    'pleasure': snap['pleasure'],
                    'arousal': snap['arousal'],
                    'dominance': snap['dominance'],
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
