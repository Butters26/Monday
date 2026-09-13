"""Runtime integration for per-lobe learning on the direct core."""
from __future__ import annotations

import re
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


def _query_from_message(message: Dict[str, Any]) -> str:
    payload = message.get("content", {}) if isinstance(message, dict) else {}
    if not isinstance(payload, dict):
        return ""
    for key in ("user_input", "text", "query"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    nested = payload.get("input")
    if isinstance(nested, dict):
        value = nested.get("user_input")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _effective_guidance(lobe: Any, message: Dict[str, Any]) -> list[str]:
    guidance = _guidance_from_message(message)
    if guidance:
        return guidance
    store = getattr(lobe, "_lobe_learning_store", None)
    if store is None:
        return []
    payload = message.get("content", {}) if isinstance(message, dict) else {}
    user_id = _safe_user(payload.get("user_id") if isinstance(payload, dict) else None)
    query = _query_from_message(message)
    if not query:
        return []
    recalled = store.recall(
        {
            "user_id": user_id,
            "query": query,
            "min_confidence": 0.55,
            "limit": 5,
            "include_only_active": True,
            "exclude_auto_adapt": True,
            "mark_used": True,
        }
    )
    content = recalled.get("content", {}) if isinstance(recalled, dict) else {}
    memories = content.get("memories", []) if isinstance(content, dict) else []
    return [
        row.get("fact", "").strip()
        for row in memories
        if isinstance(row, dict) and isinstance(row.get("fact"), str) and row.get("fact", "").strip()
    ]


def _relation_from_guidance(guidance: str) -> tuple[str, str] | None:
    match = re.match(r"^\s*(.+?)\s+means\s+(.+?)\s*\.?\s*$", guidance, re.IGNORECASE)
    if not match:
        return None
    left = match.group(1).strip()
    right = match.group(2).strip()
    return (left, right) if left and right else None


def _replace_relation(text: str, guidance: list[str]) -> str:
    result = text
    for item in guidance:
        relation = _relation_from_guidance(item)
        if relation is None:
            continue
        left, right = relation
        result = re.sub(re.escape(left), right, result, flags=re.IGNORECASE)
    return result


def _wrap_conversation(lobe: Any) -> None:
    original = lobe.process_message

    def process_message(self: Any, message: Dict[str, Any]) -> Dict[str, Any]:
        guidance = _effective_guidance(self, message)
        result = original(message)
        if guidance and isinstance(result, dict) and result.get("status") == "success":
            content = result.setdefault("content", {})
            if isinstance(content, dict):
                understanding = content.get("understanding", {})
                if isinstance(understanding, dict):
                    understanding["learned_guidance"] = list(guidance)
                    understanding["learned_interpretations"] = [
                        {"term": relation[0], "meaning": relation[1]}
                        for item in guidance
                        if (relation := _relation_from_guidance(item)) is not None
                    ]
                    understanding["learning_applied"] = True
                content["learned_guidance_used"] = True
        return result

    lobe.process_message = MethodType(process_message, lobe)


def _wrap_emotion(lobe: Any) -> None:
    handler_name = "process_message" if callable(getattr(lobe, "process_message", None)) else "process_message_safe"
    original = getattr(lobe, handler_name)

    def handler(self: Any, message: Dict[str, Any]) -> Dict[str, Any]:
        guidance = _effective_guidance(self, message)
        result = original(message)
        if guidance and isinstance(result, dict) and result.get("status") == "success":
            user_input = _query_from_message(message)
            applicable = []
            for item in guidance:
                relation = _relation_from_guidance(item)
                if relation and re.search(re.escape(relation[0]), user_input, re.IGNORECASE):
                    applicable.append(item)
            if applicable and isinstance(result.get("response"), str):
                result["response"] = f"{result['response'].rstrip()} {applicable[0]}".strip()
            result["learned_guidance"] = list(guidance)
            result["learned_guidance_used"] = True
            content = result.setdefault("content", {})
            if isinstance(content, dict):
                content["learned_guidance"] = list(guidance)
                content["learned_guidance_used"] = True
                if isinstance(result.get("response"), str):
                    content["response"] = result["response"]
        return result

    setattr(lobe, handler_name, MethodType(handler, lobe))


def _wrap_output(lobe: Any) -> None:
    original = lobe.process_message

    def process_message(self: Any, message: Dict[str, Any]) -> Dict[str, Any]:
        guidance = _effective_guidance(self, message)
        result = original(message)
        if guidance and isinstance(result, dict) and result.get("status") == "success":
            text = result.get("text")
            if not isinstance(text, str):
                content = result.get("content", {})
                text = content.get("text", "") if isinstance(content, dict) else ""
            changed_text = _replace_relation(text, guidance) if isinstance(text, str) else text
            if isinstance(changed_text, str) and changed_text != text:
                result["text"] = changed_text
                self.last_output = changed_text
                content = result.setdefault("content", {})
                if isinstance(content, dict):
                    content["text"] = changed_text
                    formatted = content.get("formatted")
                    if isinstance(formatted, dict):
                        formatted["text"] = changed_text
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
    """Connect learned state while preserving each lobe's core implementation."""
    thalamus = systems["thalamus"]
    thalamus._latest_pattern_by_user = {}
    original_send_message = thalamus.send_message

    def send_message(self: Any, destination: str, msg_type: str, content=None, source: str = "thalamus"):
        payload = dict(content) if isinstance(content, dict) else content

        if destination == "reasoning" and msg_type == "think" and isinstance(payload, dict):
            user_id = self._normalised_user_id(payload)
            nested = payload.get("input")
            nested = dict(nested) if isinstance(nested, dict) else {}
            user_input = nested.get("user_input", payload.get("user_input", ""))
            pattern = original_send_message(
                "pattern",
                "process_input",
                {
                    "user_id": user_id,
                    "data": {
                        "user_input": user_input,
                        "understanding": nested.get("understanding", {}),
                        "memory_context": nested.get("memory_context", {}),
                        "emotion_result": nested.get("emotion_result", {}),
                    },
                },
                "thalamus:prompted_path",
            )
            if isinstance(pattern, dict) and pattern.get("status") == "success":
                pattern_content = self._content(pattern)
                self._latest_pattern_by_user[user_id] = pattern_content
                payload["pattern_result"] = pattern_content
                nested["pattern_result"] = pattern_content
                payload["input"] = nested

        result = original_send_message(destination, msg_type, payload, source)

        # Only simple explicit relation teaching is staged for a pre-promotion
        # behavior check. Other direct learning remains proposed until validated.
        if (
            destination in {"conversation", "emotion", "output"}
            and msg_type == "learn"
            and isinstance(result, dict)
            and result.get("status") == "success"
            and isinstance(payload, dict)
        ):
            fact = payload.get("fact")
            if isinstance(fact, str) and _relation_from_guidance(fact) is not None:
                result_content = result.get("content", {})
                key = result.get("key")
                if not isinstance(key, str) and isinstance(result_content, dict):
                    key = result_content.get("key")
                if isinstance(key, str) and key:
                    original_send_message(
                        destination,
                        "stage_activation",
                        {"user_id": self._normalised_user_id(payload), "key": key},
                        "runtime_integration:staging",
                    )
        return result

    thalamus.send_message = MethodType(send_message, thalamus)

    if "conversation" in systems:
        _wrap_conversation(systems["conversation"])
    if "emotion" in systems:
        _wrap_emotion(systems["emotion"])
    if "output" in systems:
        _wrap_output(systems["output"])
