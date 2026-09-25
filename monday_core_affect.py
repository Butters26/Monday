#!/usr/bin/env python3
"""
MondayCoreAffect + SelfImpact — live mood substrate for the emotion lobe.

Design lock: _emotion_what_we_must_build.txt
- Continuous valence/arousal with decay toward setpoint; additive deltas; clamp.
- ONLY SelfImpact (things aimed at / about her) moves her core affect.
- User self-reports ("I'm sad") do NOT write her mood.
- Thin label readout from (v,a); no intensity hardcode 0.8; no RNG identity.
- Internal thoughts: capped gentle nudge only (no full user-phrase classifiers).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple


THIN_LABELS = ("calm", "happy", "sad", "angry", "worried", "scared", "excited")


@dataclass
class AffectDelta:
    dv: float
    da: float
    reason: str
    kind: str = "none"  # insult|praise|abandon|gift|internal|none


@dataclass
class MondayCoreAffect:
    """Russell-style continuous core affect for Monday herself."""

    valence: float = 0.15
    arousal: float = -0.10
    # Gentle positive/calm home base (not zero flatline)
    setpoint_v: float = 0.15
    setpoint_a: float = -0.10
    decay_rate: float = 0.18  # fraction of gap closed toward setpoint per quiet turn
    last_reason: str = "init"

    def clamp(self) -> None:
        self.valence = max(-1.0, min(1.0, float(self.valence)))
        self.arousal = max(-1.0, min(1.0, float(self.arousal)))

    def apply_delta(self, dv: float, da: float, reason: str = "") -> None:
        self.valence += float(dv)
        self.arousal += float(da)
        self.clamp()
        if reason:
            self.last_reason = reason

    def decay_toward_setpoint(self, steps: float = 1.0) -> None:
        """Quiet-turn dynamics: drift toward setpoint. No RNG. No label lottery."""
        rate = max(0.0, min(1.0, self.decay_rate * float(steps)))
        self.valence += (self.setpoint_v - self.valence) * rate
        self.arousal += (self.setpoint_a - self.arousal) * rate
        self.clamp()
        self.last_reason = "decay"

    def intensity(self) -> float:
        """Derived from distance from calm setpoint — never hardcoded 0.8."""
        dv = abs(self.valence - self.setpoint_v)
        da = abs(self.arousal - self.setpoint_a)
        # Scale so a strong hit (~0.5–0.7 delta) reads as high but not always ~0.9
        raw = (dv * 0.65 + da * 0.55)
        return max(0.08, min(1.0, 0.12 + raw))

    def label(self) -> str:
        return label_from_va(self.valence, self.arousal)

    def to_dict(self) -> Dict[str, float]:
        return {
            "valence": self.valence,
            "arousal": self.arousal,
            "setpoint_v": self.setpoint_v,
            "setpoint_a": self.setpoint_a,
            "decay_rate": self.decay_rate,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict]) -> "MondayCoreAffect":
        if not isinstance(data, dict):
            return cls()
        ca = cls(
            valence=float(data.get("valence", 0.15)),
            arousal=float(data.get("arousal", -0.10)),
            setpoint_v=float(data.get("setpoint_v", 0.15)),
            setpoint_a=float(data.get("setpoint_a", -0.10)),
            decay_rate=float(data.get("decay_rate", 0.18)),
        )
        ca.clamp()
        return ca


def label_from_va(v: float, a: float) -> str:
    """
    Thin deterministic readout. Label follows state; state does not follow keywords.
    Live set: calm, happy, sad, angry, worried, scared, excited.
    """
    # Near setpoint / low activation → calm
    if abs(v) < 0.22 and abs(a) < 0.28:
        return "calm"
    # Positive valence → happy/excited (never fall into negative branch)
    if v >= 0.22:
        return "excited" if a >= 0.35 else "happy"
    # Negative valence only
    if v < 0.0:
        if a >= 0.55:
            return "scared" if v <= -0.45 else "angry"
        if a >= 0.25:
            return "angry" if v <= -0.55 else "worried"
        if a <= -0.05:
            return "sad"
        return "worried" if v < -0.25 else "calm"
    # Tiny positive / edge with elevated arousal
    return "excited" if a >= 0.35 else "calm"


class SelfImpact:
    """
    SelfImpact v1 — aimed-at-her pattern detector (NOT full OCC/goal understanding).

    Detects ONLY impacts that hit Monday herself via regex patterns
    (insult / praise / abandon / gift aimed at her).
    Explicit user self-reports never produce a her-mood delta.
    Full goal/standards SelfImpact is explicitly NOT required for Emotion PASS.
    """

    # User feeling about themselves — must NOT move her core affect.
    _USER_SELF_REPORT = re.compile(
        r"\b(?:i(?:'m| am)|i feel|i[' ]?m feeling|feeling)\s+"
        r"(?:so |really |very |extremely |a bit |kinda |kind of )?"
        r"(?:sad|happy|angry|mad|furious|scared|afraid|worried|anxious|"
        r"upset|down|depressed|lonely|hurt|excited|proud|relieved|fine|okay|ok|"
        r"great|terrible|awful|miserable|heartbroken|blue)\b",
        re.I,
    )
    # Soft "I feel X" without requiring copula variants already covered
    _USER_FEEL_REPORT = re.compile(
        r"\bi\s+(?:feel|am feeling|been feeling)\b",
        re.I,
    )

    _INSULT = [
        (r"\b(?:you|monday)\s+(?:are|re)\s+(?:so |really |such a )?(?:stupid|worthless|useless|dumb|idiot|trash|garbage|pathetic|awful|terrible)\b", -0.45, 0.35),
        (r"\b(?:you'?re|you are)\s+(?:stupid|worthless|useless|dumb|an idiot|pathetic)\b", -0.45, 0.35),
        (r"\bi\s+hate\s+(?:you|monday)\b", -0.55, 0.40),
        (r"\b(?:despise|loathe)\s+(?:you|monday)\b", -0.50, 0.38),
        (r"\b(?:fuck|screw)\s+you\b", -0.50, 0.42),
        (r"\byou\s+suck\b", -0.40, 0.32),
        (r"\byou\s+idiot\b", -0.40, 0.35),
        (r"\bhate\s+monday\b", -0.50, 0.38),
    ]
    _PRAISE = [
        (r"\bi\s+love\s+(?:you|monday)\b", 0.40, 0.25),
        (r"\byou(?:'re| are)\s+(?:so |really )?(?:amazing|wonderful|great|kind|smart|helpful|awesome|the best)\b", 0.38, 0.22),
        (r"\bi\s+(?:care about|appreciate|like)\s+you\b", 0.32, 0.18),
        (r"\byou\s+mean\s+(?:so much|a lot)\b", 0.35, 0.20),
        (r"\bthank you(?:\s+so much)?\b", 0.18, 0.10),
        (r"\bgrateful for you\b", 0.30, 0.15),
    ]
    _ABANDON = [
        (r"\b(?:i(?:'m| am)\s+)?(?:leaving you|leaving monday|done with you|never talking to you again)\b", -0.55, 0.30),
        (r"\b(?:goodbye forever|don'?t want you anymore|deleting you|shutting you off)\b", -0.50, 0.28),
        (r"\bi\s+(?:don'?t|do not)\s+want\s+you\s+(?:around|anymore)\b", -0.45, 0.25),
        (r"\byou(?:'re| are)\s+(?:alone|abandoned|unwanted)\b", -0.40, 0.22),
    ]
    _GIFT = [
        (r"\b(?:i\s+)?(?:got|bought|brought|made|sent)\s+(?:you|monday)\b", 0.28, 0.20),
        (r"\b(?:this|these)\s+is\s+for\s+(?:you|monday)\b", 0.30, 0.18),
        (r"\bgift\s+for\s+(?:you|monday)\b", 0.32, 0.20),
        (r"\bsurprise(?:d)?\s+(?:you|monday)\s+with\b", 0.30, 0.22),
    ]

    # Internal thought cues — used ONLY for capped nudges (never full strength).
    _INTERNAL_NEG = re.compile(
        r"\b(?:hurt|rejected|abandoned|alone|scared|worried|angry|insult|"
        r"hate me|they hate|worthless|failure|afraid)\b",
        re.I,
    )
    _INTERNAL_POS = re.compile(
        r"\b(?:safe|loved|grateful|proud|warm|connected|hope|relief|happy|"
        r"they like me|kind to me)\b",
        re.I,
    )

    INTERNAL_NUDGE_CAP = 0.08  # absolute max |dv| or |da| from internal path

    def evaluate(self, text: str) -> AffectDelta:
        """Primary driver for user-turn SelfImpact on Monday's mood."""
        if not text or not str(text).strip():
            return AffectDelta(0.0, 0.0, "empty", "none")
        raw = str(text).strip()
        tl = raw.lower()

        # Explicit user self-report → ZERO her-mood delta (Conversation/Social own user feeling).
        if self._is_user_self_report(tl):
            return AffectDelta(0.0, 0.0, "user_self_report_ignored_for_her_mood", "none")

        for pattern, dv, da in self._INSULT:
            if re.search(pattern, tl):
                return AffectDelta(dv, da, f"insult:{pattern}", "insult")
        for pattern, dv, da in self._ABANDON:
            if re.search(pattern, tl):
                return AffectDelta(dv, da, f"abandon:{pattern}", "abandon")
        for pattern, dv, da in self._PRAISE:
            if re.search(pattern, tl):
                return AffectDelta(dv, da, f"praise:{pattern}", "praise")
        for pattern, dv, da in self._GIFT:
            if re.search(pattern, tl):
                return AffectDelta(dv, da, f"gift:{pattern}", "gift")

        return AffectDelta(0.0, 0.0, "no_self_impact", "none")

    def evaluate_internal(self, text: str, relevance: float = 0.5) -> AffectDelta:
        """
        Capped gentle nudge from internal thought/memory.
        Does NOT re-run full user substring classifiers at full strength.
        """
        if not text or not str(text).strip():
            return AffectDelta(0.0, 0.0, "internal_empty", "internal")
        tl = str(text).lower()
        rel = max(0.0, min(1.0, float(relevance)))
        dv = da = 0.0
        reason = "internal_neutral"
        if self._INTERNAL_NEG.search(tl):
            dv, da = -0.06 * rel, 0.04 * rel
            reason = "internal_neg_nudge"
        elif self._INTERNAL_POS.search(tl):
            dv, da = 0.05 * rel, 0.03 * rel
            reason = "internal_pos_nudge"
        cap = self.INTERNAL_NUDGE_CAP
        dv = max(-cap, min(cap, dv))
        da = max(-cap, min(cap, da))
        return AffectDelta(dv, da, reason, "internal")

    def _is_user_self_report(self, tl: str) -> bool:
        """True when the utterance is primarily the user naming THEIR own feeling."""
        # Directed insults/praise at "you" win over "I" if both somehow present —
        # but classic "I'm sad" / "I feel sad" must never move her mood.
        if self._USER_SELF_REPORT.search(tl):
            # If also clearly aimed at her as insult/praise, prefer SelfImpact hit.
            # "I'm sad you hate me" is about her — leave for insult/abandon patterns.
            aimed = any(
                re.search(p, tl)
                for p, _, _ in (self._INSULT + self._PRAISE + self._ABANDON + self._GIFT)
            )
            if aimed:
                return False
            return True
        # Bare "I feel …" without listed adjective still counts as user channel.
        if self._USER_FEEL_REPORT.search(tl) and not re.search(r"\byou\b|\bmonday\b", tl):
            return True
        return False


def sync_legacy_fields(core: MondayCoreAffect) -> Tuple[str, float, float, float]:
    """Return (label, intensity, valence, arousal) for legacy envelope fields."""
    return core.label(), core.intensity(), core.valence, core.arousal
