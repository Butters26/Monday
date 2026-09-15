"""Learning-aware direct-core lobe classes.

Each class owns two things that used to be centralized:
1. whether a lesson is actually relevant to that lobe; and
2. how active learned guidance is applied during that lobe's normal work.
"""

from __future__ import annotations

from typing import Any, Dict, List

from advanced_emotional_engine import EmotionalProcess
from conversation import ConversationSystem
from direct_reasoning import DirectMaximumSophisticationAdapter
from language_generation import LanguageGenerator
from output import OutputLobe
from pattern_recognition import AdvancedPatternRecognition

from learning.lobe_guidance import (
    applicable_guidance,
    effective_guidance,
    query_from_payload,
    relation_from_guidance,
)


def _assessment(accept: bool, score: float, *reasons: str) -> Dict[str, Any]:
    return {
        "accept": bool(accept),
        "score": max(0.0, min(float(score), 1.0)),
        "reasons": [reason for reason in reasons if isinstance(reason, str) and reason],
    }


def _record_surface(record: Dict[str, Any]) -> str:
    return str(record.get("surface", "")).strip().lower() if isinstance(record, dict) else ""


def _record_subject(record: Dict[str, Any]) -> str:
    return str(record.get("subject", "")).strip().lower() if isinstance(record, dict) else ""


def _record_type(record: Dict[str, Any]) -> str:
    return str(record.get("type", "fact")).strip().lower() if isinstance(record, dict) else "fact"


def _copy_message_with_guidance(lobe: Any, message: Dict[str, Any]) -> tuple[Dict[str, Any], List[str]]:
    payload = message.get("content", message) if isinstance(message, dict) else {}
    payload = dict(payload) if isinstance(payload, dict) else {}
    guidance = effective_guidance(lobe, payload)
    if guidance:
        payload["learned_guidance"] = list(guidance)
    copied = dict(message) if isinstance(message, dict) else {}
    copied["content"] = payload
    return copied, guidance


class AdaptiveConversationSystem(ConversationSystem):
    owns_learning_application = True

    def assess_learning_relevance(
        self, lesson_text: str, lesson_type: str, record: Dict[str, Any]
    ) -> Dict[str, Any]:
        surface = _record_surface(record)
        subject = _record_subject(record)
        if surface in {"reply_guidance", "tone_policy"} or subject in {"reply_guidance", "tone_policy"}:
            return _assessment(True, 1.0, "conversation_surface_match")
        if lesson_type == "feedback" and _record_type(record) in {"rule", "exception"}:
            return _assessment(True, 0.85, "conversation_feedback")
        return _assessment(False, 0.0, "conversation_not_relevant")

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        copied, guidance = _copy_message_with_guidance(self, message)
        result = super().process_message(copied)
        if copied.get("type") != "understand" or not guidance or result.get("status") != "success":
            return result
        content = result.setdefault("content", {})
        if not isinstance(content, dict):
            return result
        understanding = content.get("understanding", {})
        if not isinstance(understanding, dict):
            return result
        interpretations = []
        for item in guidance:
            relation = relation_from_guidance(item)
            if relation is not None:
                interpretations.append({"term": relation[0], "meaning": relation[1]})
        understanding["learned_guidance"] = list(guidance)
        understanding["learned_interpretations"] = interpretations
        understanding["learning_applied"] = True
        content["learned_guidance_used"] = True
        return result


class AdaptiveReasoningAdapter(DirectMaximumSophisticationAdapter):
    owns_learning_application = True

    def assess_learning_relevance(
        self, lesson_text: str, lesson_type: str, record: Dict[str, Any]
    ) -> Dict[str, Any]:
        surface = _record_surface(record)
        subject = _record_subject(record)
        record_type = _record_type(record)
        if surface in {"inference_preferences", "heuristic_selection"} or subject in {
            "inference_preferences",
            "heuristic_selection",
        }:
            return _assessment(True, 1.0, "reasoning_surface_match")
        if record_type in {"fact", "procedure"}:
            return _assessment(True, 0.9, "reasoning_knowledge_record")
        if lesson_type == "correction" and record_type == "exception":
            return _assessment(True, 0.85, "reasoning_correction")
        return _assessment(False, 0.0, "reasoning_not_relevant")

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        copied, _guidance = _copy_message_with_guidance(self, message)
        return super().process_message(copied)


class AdaptivePatternRecognition(AdvancedPatternRecognition):
    owns_learning_application = True

    def assess_learning_relevance(
        self, lesson_text: str, lesson_type: str, record: Dict[str, Any]
    ) -> Dict[str, Any]:
        surface = _record_surface(record)
        subject = _record_subject(record)
        if surface == "pattern_rules" or subject == "pattern_rules":
            return _assessment(True, 1.0, "pattern_surface_match")
        metadata = record.get("metadata", {}) if isinstance(record, dict) else {}
        metadata = metadata if isinstance(metadata, dict) else {}
        relations = self._extract_relations(lesson_text, metadata)
        if relations:
            return _assessment(True, 0.9, "pattern_relation_interpreted")
        if _record_type(record) == "procedure":
            return _assessment(True, 0.75, "pattern_procedure")
        return _assessment(False, 0.0, "pattern_not_relevant")

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        copied, guidance = _copy_message_with_guidance(self, message)
        result = super().process_message(copied)
        if copied.get("type") not in {"observe", "process_input"} or not guidance or result.get("status") != "success":
            return result
        payload = copied.get("content", {})
        query = query_from_payload(payload if isinstance(payload, dict) else {})
        used = applicable_guidance(guidance, query)
        if not used:
            return result
        content = result.setdefault("content", {})
        if not isinstance(content, dict):
            return result
        learned_matches = []
        for item in used:
            relation = relation_from_guidance(item)
            if relation is not None:
                learned_matches.append(
                    {
                        "token": relation[0],
                        "concept_hint": relation[1],
                        "classification": "learned_guidance",
                        "confidence": 1.0,
                        "provisional": False,
                    }
                )
        if learned_matches:
            existing = content.get("token_rule_matches", [])
            existing = list(existing) if isinstance(existing, list) else []
            content["token_rule_matches"] = [*existing, *learned_matches]
            content["token_rule_applied"] = True
        content["learned_guidance"] = list(used)
        content["learned_guidance_used"] = True
        patterns = result.get("patterns")
        if isinstance(patterns, dict):
            patterns["learned_guidance"] = list(used)
        return result


class AdaptiveLanguageGenerator(LanguageGenerator):
    owns_learning_application = True

    def assess_learning_relevance(
        self, lesson_text: str, lesson_type: str, record: Dict[str, Any]
    ) -> Dict[str, Any]:
        surface = _record_surface(record)
        subject = _record_subject(record)
        if surface == "generation_guidance" or subject == "generation_guidance":
            return _assessment(True, 1.0, "language_surface_match")
        metadata = record.get("metadata", {}) if isinstance(record, dict) else {}
        metadata = metadata if isinstance(metadata, dict) else {}
        relations = self._extract_relations(lesson_text, metadata)
        if relations:
            return _assessment(True, 0.88, "language_relation_interpreted")
        return _assessment(False, 0.0, "language_not_relevant")

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        copied, _guidance = _copy_message_with_guidance(self, message)
        return super().process_message(copied)


class AdaptiveEmotionProcess(EmotionalProcess):
    owns_learning_application = True

    def assess_learning_relevance(
        self, lesson_text: str, lesson_type: str, record: Dict[str, Any]
    ) -> Dict[str, Any]:
        surface = _record_surface(record)
        subject = _record_subject(record)
        if surface == "emotion_response_guidance" or subject == "emotion_response_guidance":
            return _assessment(True, 1.0, "emotion_surface_match")
        return _assessment(False, 0.0, "emotion_requires_explicit_surface")

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        copied, guidance = _copy_message_with_guidance(self, message)
        result = self.process_message_safe(copied)
        if copied.get("type") != "process_input" or not guidance or result.get("status") != "success":
            return result
        payload = copied.get("content", {})
        query = query_from_payload(payload if isinstance(payload, dict) else {})
        used = applicable_guidance(guidance, query)
        if not used:
            return result
        response = result.get("response")
        if isinstance(response, str) and used[0] not in response:
            result["response"] = f"{response.rstrip()} {used[0]}".strip()
        result["learned_guidance"] = list(used)
        result["learned_guidance_used"] = True
        content = result.setdefault("content", {})
        if isinstance(content, dict):
            content["learned_guidance"] = list(used)
            content["learned_guidance_used"] = True
            if isinstance(result.get("response"), str):
                content["response"] = result["response"]
        return result


class AdaptiveOutputLobe(OutputLobe):
    owns_learning_application = True

    def assess_learning_relevance(
        self, lesson_text: str, lesson_type: str, record: Dict[str, Any]
    ) -> Dict[str, Any]:
        surface = _record_surface(record)
        subject = _record_subject(record)
        if surface == "delivery_tone" or subject == "delivery_tone":
            return _assessment(True, 1.0, "output_surface_match")
        return _assessment(False, 0.0, "output_requires_explicit_surface")

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        copied, guidance = _copy_message_with_guidance(self, message)
        result = super().process_message(copied)
        if copied.get("type") != "generate_output" or not guidance or result.get("status") != "success":
            return result
        payload = copied.get("content", {})
        query = query_from_payload(payload if isinstance(payload, dict) else {})
        used = applicable_guidance(guidance, query)
        if not used:
            return result
        text = result.get("text")
        if not isinstance(text, str):
            content = result.get("content", {})
            text = content.get("text", "") if isinstance(content, dict) else ""
        item = used[0]
        relation = relation_from_guidance(item)
        suffix = relation[1] if relation is not None else item
        changed = text
        if isinstance(text, str) and suffix and suffix not in text:
            changed = f"{text.rstrip()} — {suffix}"
        if isinstance(changed, str) and changed != text:
            result["text"] = changed
            self.last_output = changed
            content = result.setdefault("content", {})
            if isinstance(content, dict):
                content["text"] = changed
                formatted = content.get("formatted")
                if isinstance(formatted, dict):
                    formatted["text"] = changed
        content = result.setdefault("content", {})
        if isinstance(content, dict):
            content["learned_guidance"] = list(used)
            content["learned_guidance_used"] = True
        result["learned_guidance_used"] = True
        return result
