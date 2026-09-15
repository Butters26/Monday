"""Functional lobe-owned learning policies for the native-learning branch.

These classes keep application inside each lobe while tightening two boundaries:
- a lobe only accepts lessons it can actually interpret; and
- directly taught guidance can be staged by the owning lobe for validation.
"""

from __future__ import annotations

import re
from typing import Any, Dict

from learning.adaptive_lobes import (
    AdaptiveConversationSystem,
    AdaptiveEmotionProcess,
    AdaptiveLanguageGenerator,
    AdaptiveOutputLobe,
    AdaptivePatternRecognition,
    AdaptiveReasoningAdapter,
)
from learning.lobe_guidance import relation_from_guidance, trigger_from_guidance


def _assessment(accept: bool, score: float, *reasons: str) -> Dict[str, Any]:
    return {
        "accept": bool(accept),
        "score": max(0.0, min(float(score), 1.0)),
        "reasons": [reason for reason in reasons if isinstance(reason, str) and reason],
    }


def _surface(record: Dict[str, Any]) -> str:
    return str(record.get("surface", "")).strip().lower() if isinstance(record, dict) else ""


def _subject(record: Dict[str, Any]) -> str:
    return str(record.get("subject", "")).strip().lower() if isinstance(record, dict) else ""


def _record_type(record: Dict[str, Any]) -> str:
    return str(record.get("type", "fact")).strip().lower() if isinstance(record, dict) else "fact"


def _has_linguistic_structure(lesson_text: str) -> bool:
    """Language's own small parser for lessons about surface realization."""
    if not isinstance(lesson_text, str):
        return False
    return bool(
        re.search(
            r"\b(grammar|grammatical|sentence|sentences|wording|words|phrase|phrasing|"
            r"writing|rewrite|clarity|clearer|concise|verbosity|punctuation)\b",
            lesson_text,
            re.IGNORECASE,
        )
    )


def _has_reasoning_structure(lesson_text: str) -> bool:
    """Reasoning's own parser for inference/arithmetic procedures."""
    if not isinstance(lesson_text, str):
        return False
    text = lesson_text.strip()
    if not text:
        return False
    if re.search(r"\b\d+\s*[+\-*/=]\s*\d+\b", text):
        return True
    return bool(
        re.search(
            r"\b(arithmetic|calculate|calculation|equation|sum|difference|product|quotient|"
            r"reciprocal|infer|inference|reason|reasoning|logic|verify|verification|"
            r"cross-check|crosscheck)\b",
            text,
            re.IGNORECASE,
        )
    )


class _DirectGuidanceActivation:
    """Let the owning lobe stage a directly saved guidance rule for validation."""

    def on_learning_saved(self, payload: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict) or not isinstance(result, dict):
            return result
        fact = payload.get("fact")
        if not isinstance(fact, str) or not fact.strip():
            return result
        # Only guidance with an explicit applicability boundary is safe to stage.
        if relation_from_guidance(fact) is None and trigger_from_guidance(fact) is None:
            return result
        content = result.get("content", {})
        key = result.get("key")
        if not isinstance(key, str) and isinstance(content, dict):
            key = content.get("key")
        if not isinstance(key, str) or not key:
            return result
        store = getattr(self, "_lobe_learning_store", None)
        if store is None:
            return result
        user_id = payload.get("user_id", "default")
        user_id = user_id.strip() if isinstance(user_id, str) and user_id.strip() else "default"
        staged = store.stage_activation({"user_id": user_id, "key": key})
        result["staged_for_validation"] = bool(
            isinstance(staged, dict) and staged.get("status") == "success"
        )
        if not result["staged_for_validation"]:
            result["staging_error"] = (
                staged.get("message", "unknown staging failure")
                if isinstance(staged, dict)
                else "unknown staging failure"
            )
        return result


class FunctionalConversationSystem(_DirectGuidanceActivation, AdaptiveConversationSystem):
    pass


class FunctionalReasoningAdapter(AdaptiveReasoningAdapter):
    def assess_learning_relevance(
        self, lesson_text: str, lesson_type: str, record: Dict[str, Any]
    ) -> Dict[str, Any]:
        surface = _surface(record)
        subject = _subject(record)
        record_type = _record_type(record)
        if surface in {"inference_preferences", "heuristic_selection"} or subject in {
            "inference_preferences",
            "heuristic_selection",
        }:
            return _assessment(True, 1.0, "reasoning_surface_match")
        if _has_reasoning_structure(lesson_text):
            return _assessment(True, 0.95, "arithmetic_relevance_match")
        if record_type == "fact" and relation_from_guidance(lesson_text) is not None:
            return _assessment(True, 0.9, "reasoning_fact_relation")
        if record_type == "procedure" and lesson_type == "skill":
            return _assessment(True, 0.8, "reasoning_procedure")
        if lesson_type == "correction" and record_type == "exception":
            return _assessment(True, 0.8, "reasoning_correction")
        return _assessment(False, 0.0, "reasoning_cannot_interpret_lesson")


class FunctionalPatternRecognition(AdaptivePatternRecognition):
    pass


class FunctionalLanguageGenerator(AdaptiveLanguageGenerator):
    def assess_learning_relevance(
        self, lesson_text: str, lesson_type: str, record: Dict[str, Any]
    ) -> Dict[str, Any]:
        surface = _surface(record)
        subject = _subject(record)
        if surface == "generation_guidance" or subject == "generation_guidance":
            return _assessment(True, 1.0, "language_surface_match")
        metadata = record.get("metadata", {}) if isinstance(record, dict) else {}
        metadata = metadata if isinstance(metadata, dict) else {}
        if self._extract_relations(lesson_text, metadata):
            return _assessment(True, 0.9, "language_relation_interpreted")
        if lesson_type in {"skill", "feedback"} and _has_linguistic_structure(lesson_text):
            return _assessment(True, 0.9, "language_generation_lesson")
        return _assessment(False, 0.0, "language_cannot_interpret_lesson")


class FunctionalEmotionProcess(_DirectGuidanceActivation, AdaptiveEmotionProcess):
    def assess_learning_relevance(
        self, lesson_text: str, lesson_type: str, record: Dict[str, Any]
    ) -> Dict[str, Any]:
        surface = _surface(record)
        subject = _subject(record)
        if surface == "emotion_response_guidance" or subject == "emotion_response_guidance":
            return _assessment(True, 1.0, "emotion_surface_match")
        if lesson_type == "feedback" and _record_type(record) in {"rule", "exception"}:
            return _assessment(True, 0.85, "emotion_feedback")
        return _assessment(False, 0.0, "emotion_cannot_interpret_lesson")


class FunctionalOutputLobe(_DirectGuidanceActivation, AdaptiveOutputLobe):
    def assess_learning_relevance(
        self, lesson_text: str, lesson_type: str, record: Dict[str, Any]
    ) -> Dict[str, Any]:
        surface = _surface(record)
        subject = _subject(record)
        if surface == "delivery_tone" or subject == "delivery_tone":
            return _assessment(True, 1.0, "output_surface_match")
        if lesson_type == "feedback" and _record_type(record) in {"rule", "exception"}:
            return _assessment(True, 0.85, "output_feedback")
        return _assessment(False, 0.0, "output_cannot_interpret_lesson")
