"""Runtime integration for per-lobe learning on the direct core.

This module does not replace lobe algorithms. It keeps each lobe's original
implementation authoritative while making learned state part of the same
prompted path and restoring Pattern as a first-class input to Reasoning.
"""
from __future__ import annotations

from types import MethodType
from typing import Any, Dict


def _safe_user(user_id: Any) -> str:
    return user_id.strip() if isinstance(user_id, str) and user_id.strip() else "default"


def _guidance_from_message(message: Dict[str, Any]) -> list[str]:
    payload = message.get("content", {}) if isinstance(message, dict) else {}
    guidance = payload.get("learned_guidance", []) if isinstance(payload, dict) else []
    if not isinstance(guidance, list):
        return []
    return [item.strip() for item in guidance if isinstance(item, str) and item.strip()]


def _wrap_conversation(lobe: Any) -> None:
    original = lobe.process_message

    def process_message(self: Any, message: Dict[str, Any]) -> Dict[str, Any]:
        guidance = _guidance_from_message(message)
        result = original(message)
        if guidance and isinstance(result, dict) and result.get("status") == "success":
            content = result.setdefault("content", {})
            if isinstance(content, dict):
                understanding = content.get("understanding", {})
                if isinstance(understanding, dict):
                    understanding["learned_guidance"] = list(guidance)
                    understanding["learning_applied"] = True
                content["learned_guidance_used"] = True
        return result

    lobe.process_message = MethodType(process_message, lobe)


def _wrap_emotion(lobe: Any) -> None:
    handler_name = "process_message_safe" if callable(getattr(lobe, "process_message_safe", None)) else "process_message"
    original = getattr(lobe, handler_name)

    def handler(self: Any, message: Dict[str, Any]) -> Dict[str, Any]:
        guidance = _guidance_from_message(message)
        result = original(message)
        if guidance and isinstance(result, dict) and result.get("status") == "success":
            # Emotion keeps its native PAD/state algorithm. Learned rules become
            # explicit emotional context for downstream reasoning instead of
            # silently mutating the engine's permanent state machine.
            result["learned_guidance"] = list(guidance)
            result["learned_guidance_used"] = True
            content = result.setdefault("content", {})
            if isinstance(content, dict):
                content["learned_guidance"] = list(guidance)
                content["learned_guidance_used"] = True
        return result

    setattr(lobe, handler_name, MethodType(handler, lobe))


def _wrap_output(lobe: Any) -> None:
    original = lobe.process_message

    def process_message(self: Any, message: Dict[str, Any]) -> Dict[str, Any]:
        guidance = _guidance_from_message(message)
        result = original(message)
        if guidance and isinstance(result, dict) and result.get("status") == "success":
            content = result.setdefault("content", {})
            if isinstance(content, dict):
                content["learned_guidance"] = list(guidance)
                content["learned_guidance_used"] = True
                formatted = content.get("formatted")
                if isinstance(formatted, dict):
                    formatted["learned_guidance"] = list(guidance)
                    formatted["learning_applied"] = True
            result["learned_guidance_used"] = True
        return result

    lobe.process_message = MethodType(process_message, lobe)


def install_learning_integration(systems: Dict[str, Any]) -> None:
    """Connect Pattern and learned lobe context without replacing core lobe logic."""
    thalamus = systems["thalamus"]
    thalamus._latest_pattern_by_user = {}

    original_send_message = thalamus.send_message

    def send_message(self: Any, destination: str, msg_type: str, content=None, source: str = "thalamus"):
        payload = dict(content) if isinstance(content, dict) else content
        if destination == "reasoning" and msg_type == "think" and isinstance(payload, dict):
            user_id = self._normalised_user_id(payload)
            pattern_result = self._latest_pattern_by_user.get(user_id)
            if isinstance(pattern_result, dict):
                payload["pattern_result"] = pattern_result
                nested = payload.get("input")
                if isinstance(nested, dict):
                    nested = dict(nested)
                    nested["pattern_result"] = pattern_result
                    payload["input"] = nested
        return original_send_message(destination, msg_type, payload, source)

    thalamus.send_message = MethodType(send_message, thalamus)

    original_process_user_input = thalamus.process_user_input

    def process_user_input(self: Any, user_input: str, user_id: str = "default") -> str:
        safe_user = _safe_user(user_id)
        pattern = self.send_and_wait(
            "pattern",
            "process_input",
            {"user_id": safe_user, "data": {"user_input": user_input}},
            source="thalamus:prompted_path",
        )
        if isinstance(pattern, dict) and pattern.get("status") == "success":
            self._latest_pattern_by_user[safe_user] = self._content(pattern)
        else:
            self._latest_pattern_by_user.pop(safe_user, None)
        return original_process_user_input(user_input, user_id=safe_user)

    thalamus.process_user_input = MethodType(process_user_input, thalamus)

    if "conversation" in systems:
        _wrap_conversation(systems["conversation"])
    if "emotion" in systems:
        _wrap_emotion(systems["emotion"])
    if "output" in systems:
        _wrap_output(systems["output"])
