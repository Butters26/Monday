"""Appraisal: how what happens affects Monday herself.

This is the Emotion lobe's own job (its contract: "processes how situations and
internal activity affect her emotionally"). It replaces SelfImpact's regex
lists of insults and praise (moved to legacy/self_impact_regex_legacy.py).

How it works:
- Language reads the sentence (Emotion does not parse grammar): who it is
  about, the words in it, and whether it is negated.
- How good or bad a word feels is a BELIEF she holds, not a rule. Her starting
  beliefs come from a published resource of human ratings (VADER, MIT licence,
  about 7,500 words rated -4..+4). She can change any of them
  (adjust_word_feeling); her changes are kept in her own state and win over the
  starting rating.
- Who it is about decides how much it moves her:
    aimed at her (you / Monday / Mercy)   -> her own feeling moves most
    about him (I / me / my)               -> she is moved for him, gently;
                                             she does not adopt his feeling
    about something else                  -> a little
- Things aimed at her stir her up (arousal rises); being moved for someone
  else is quieter (valence moves, arousal doesn't).
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# How much an event moves her, by whom it is about (her / him / other).
AIMED_AT_HER = 0.6
ABOUT_HIM = 0.3
ABOUT_OTHER = 0.15
INTERNAL = 0.12  # her own thoughts: a gentle nudge
NEGATIVITY_BIAS = 1.5

_CONTENT_KINDS = {"noun", "verb", "adjective", "adverb", "interjection"}


@dataclass
class Appraisal:
    dv: float
    da: float
    reason: str
    about: str            # "her" | "him" | "other" | "none"
    words: List[Tuple[str, float]]


def _starting_file() -> Optional[Path]:
    try:
        import vaderSentiment  # type: ignore
        path = Path(vaderSentiment.__file__).with_name("vader_lexicon.txt")
        return path if path.is_file() else None
    except Exception:
        return None


class WordFeelings:
    """Her beliefs about how words feel (-1 bad .. +1 good)."""

    _shared: Optional[Dict[str, float]] = None
    _shared_lock = threading.Lock()

    def __init__(self, learned: Optional[Dict[str, float]] = None) -> None:
        self.learned: Dict[str, float] = dict(learned or {})
        self.starting = self._load_starting()

    @classmethod
    def _load_starting(cls) -> Dict[str, float]:
        with cls._shared_lock:
            if cls._shared is None:
                ratings: Dict[str, float] = {}
                path = _starting_file()
                if path is None:
                    print("⚠️  Emotion: no starting word feelings (vaderSentiment not installed); "
                          "she can only feel what she has learned")
                else:
                    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                        parts = line.split("\t")
                        if len(parts) >= 2:
                            try:
                                ratings[parts[0].strip().casefold()] = max(-1.0, min(1.0, float(parts[1]) / 4.0))
                            except ValueError:
                                continue
                cls._shared = ratings
            return cls._shared

    def feel(self, *forms: str) -> Optional[float]:
        for form in forms:
            key = str(form or "").strip().casefold()
            if not key:
                continue
            if key in self.learned:
                return self.learned[key]
            if key in self.starting:
                return self.starting[key]
        return None

    def adjust(self, word: str, feeling: float) -> float:
        key = str(word).strip().casefold()
        self.learned[key] = max(-1.0, min(1.0, float(feeling)))
        return self.learned[key]


def _about(reading: Dict[str, Any]) -> str:
    """Who the sentence is about, from Language's reading of it."""
    assertion = reading.get("assertion") or {}
    concept = str(assertion.get("theme_concept") or "")
    lemmas = [str(t.get("lemma") or t.get("surface") or "").casefold()
              for t in reading.get("tokens") or [] if t.get("kind") == "pronoun"]
    if concept == "mercy" or any(l in ("you", "yourself") for l in lemmas):
        return "her"
    if concept == "user" or any(l in ("i", "me", "myself") for l in lemmas) \
            or any(str(t.get("lemma") or "").casefold() == "my" for t in reading.get("tokens") or []):
        return "him"
    return "other"


def _negated(reading: Dict[str, Any]) -> bool:
    assertion = reading.get("assertion") or {}
    if str(assertion.get("polarity") or "") == "negative":
        return True
    return any(t.get("negation") or str(t.get("lemma") or "").casefold() in ("not", "n't", "never")
               for t in reading.get("tokens") or [])


def appraise(reading: Dict[str, Any], feelings: WordFeelings, *, scale: Optional[float] = None) -> Appraisal:
    if not reading or not reading.get("tokens"):
        return Appraisal(0.0, 0.0, "nothing read", "none", [])
    words: List[Tuple[str, float]] = []
    for token in reading.get("tokens") or []:
        if token.get("kind") not in _CONTENT_KINDS:
            continue
        surface = str(token.get("surface") or "")
        lemma = str(token.get("lemma") or "")
        value = feelings.feel(surface, lemma)
        if value is not None and abs(value) > 1e-9:
            words.append((surface or lemma, value))
    if not words:
        return Appraisal(0.0, 0.0, "no word in it feels good or bad to her", _about(reading), [])
    # The strongest words carry the moment (two at most), like hearing the gist.
    strongest = sorted(words, key=lambda w: abs(w[1]), reverse=True)[:2]
    feel = sum(v for _, v in strongest) / len(strongest)
    if _negated(reading):
        feel = -feel * 0.6  # "not bad" is milder than "good"
    about = _about(reading)
    weight = scale if scale is not None else {"her": AIMED_AT_HER, "him": ABOUT_HIM}.get(about, ABOUT_OTHER)
    # Bad things land harder than good ones (negativity bias), most of all
    # when they are aimed at her.
    dv = feel * weight * (NEGATIVITY_BIAS if feel < 0 and about == "her" else 1.0)
    # Something aimed at her stirs her up (praise excites, an insult hurts and
    # angers). Being sorry or glad for someone else is a quieter feeling.
    da = abs(feel) * weight * (0.75 if about == "her" else 0.0)
    shown = ", ".join(f"{w} {v:+.2f}" for w, v in strongest)
    return Appraisal(dv, da, f"about {about}: {shown}", about, strongest)


__all__ = ["Appraisal", "WordFeelings", "appraise", "AIMED_AT_HER", "ABOUT_HIM", "ABOUT_OTHER", "INTERNAL"]
