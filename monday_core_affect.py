#!/usr/bin/env python3
"""
MondayCoreAffect — live mood substrate for the emotion lobe.

Design lock: _emotion_what_we_must_build.txt
- Continuous valence/arousal with decay toward setpoint; additive deltas; clamp.
- What moves her core affect is appraisal (monday_appraisal.py): Language's
  reading of who it's about + her beliefs about how words feel.
  (The old regex SelfImpact lists are in legacy/self_impact_regex_legacy.py.)
- Thin label readout from (v,a); no intensity hardcode 0.8; no RNG identity.
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
    if abs(v) < 0.15 and abs(a) < 0.28:
        return "calm"
    if v >= 0.15:
        return "excited" if a >= 0.35 else "happy"
    if v <= -0.15:
        if a >= 0.55:
            return "scared" if v <= -0.45 else "angry"
        if a >= 0.25:
            return "angry" if v <= -0.45 else "worried"
        return "sad"
    # Near-neutral valence but stirred up.
    return "excited" if v >= 0 else "worried"


def sync_legacy_fields(core: MondayCoreAffect) -> Tuple[str, float, float, float]:
    """Return (label, intensity, valence, arousal) for legacy envelope fields."""
    return core.label(), core.intensity(), core.valence, core.arousal
