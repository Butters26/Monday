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


def _relation_from_guidance(guidance: str) -> tuple[str, str] | None:
    match = re.match(r"^\s*(.+?)\s+means\s+(.+?)\s*\.?\s*$", guidance, re.IGNORECASE)
    if not match:
        return None
    left = match.group(1).strip()
    right = match.group(2).strip()
    return (left, right) if left and right else None


def _trigger_from_guidance(guidance: str) -> str | None:
    """Extract an explicit applicability trigger from a general rule."""
    match = re.match(r"^\s*for\s+(.+?),\s+.+$", guidance, re.IGNORECASE)
    if not match:
        return None
    trigger = match.group(1).strip()
    return trigger or None


def _guidance_applies(item: str, query: str) -> bool:
    relation = _relation_from_guidance(item)
    if relation is not None:
        return bool(re.search(re.escape(relation[0]), query, re.IGNORECASE))
    trigger = _trigger_from_guidance(item)
    if trigger is not None:
        return bool(re.search(re.escape(trigger), query, re.IGNORECASE))
    return False


def _applicable_guidance(items: list[str], query: str) -> list[str]:
    if not query:
        return []
    return [item for item in items if _guidance_applies(item, query)]


def _staged_guidance(lobe: Any, user_id: str, query: str) -> list[str]:
    """Return only explicitly staged rules for this user that match this input."""
    cache = getattr(lobe, "_runtime_staged_guidance", {})
    if not isinstance(cache, dict):
        return []
    user_cache = cache.get(user_id, {})
    if not isinstance(user_cache, dict):
        return []
    return _applicable_guidance(
        [value for value in user_cache.values() if isinstance(value, str)], query
    )


def _effective_guidance(lobe: Any, message: Dict[str, Any]) -> list[str]:
    guidance = _guidance_from_message(message)
    if guidance:
        return guidance
    payload = message.get("content", {}) if isinstance(message, dict) else {}
    user_id = _safe_user(payload.get("user_id") if isinstance(payload, dict) else None)
    query = _query_from_message(message)
    if not query:
        return []

    store = getattr(lobe, "_lobe_learning_store", None)
    if store is not None:
        def recall(query_text: str) -> list[dict]:
            result = store.recall(
                {
                    "user_id": user_id,
                    "query": query_text,
                    "min_confidence": 0.55,
                    "limit": 20,
                    "include_only_active": True,
                    "exclude_auto_adapt": True,
                    "mark_used": True,
                }
            )
            content = result.get("content", {}) if isinstance(result, dict) else {}
            rows = content.get("memories", []) if isinstance(content, dict) else []
            return [row for row in rows if isinstance(row, dict)]

        memories = recall(query)
        if not memories:
            memories = recall("")
        stored_guidance = [
            row.get("fact", "").strip()
            for row in memories
            if isinstance(row.get("fact"), str)
            and row.get("fact", "").strip()
            and _guidance_applies(row.get("fact", ""), query)
        ]
        if stored_guidance:
            return stored_guidance

    # During validation, use only exact rules that were successfully staged.
    return _staged_guidance(lobe, user_id, query)


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


def _postprocess_emotion(lobe: Any, payload: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    guidance = _effective_guidance(lobe, {"content": payload})
    if not guidance or result.get("status") != "success":
        return result
    user_input = _query_from_message({"content": payload})
    applicable = _applicable_guidance(guidance, user_input)
    if applicable and isinstance(result.get("response"), str) and applicable[0] not in result["response"]:
        result["response"] = f"{result['response'].rstrip()} {applicable[0]}".strip()
    result["learned_guidance"] = list(guidance)
    result["learned_guidance_used"] = bool(applicable)
    content = result.setdefault("content", {})
    if isinstance(content, dict):
        content["learned_guidance"] = list(guidance)
        content["learned_guidance_used"] = bool(applicable)
        if isinstance(result.get("response"), str):
            content["response"] = result["response"]
    return result


def _postprocess_output(lobe: Any, payload: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    guidance = _effective_guidance(lobe, {"content": payload})
    if not guidance or result.get("status") != "success":
        return result
    query = _query_from_message({"content": payload})
    applicable = _applicable_guidance(guidance, query)
    text = result.get("text")
    if not isinstance(text, str):
        content = result.get("content", {})
        text = content.get("text", "") if isinstance(content, dict) else ""
    changed_text = text
    if applicable and isinstance(text, str):
        item = applicable[0]
        relation = _relation_from_guidance(item)
        suffix = relation[1] if relation is not None else item
        if suffix and suffix not in text:
            changed_text = f"{text.rstrip()} — {suffix}"
    applied = bool(applicable)
    if isinstance(changed_text, str) and changed_text != text:
        result["text"] = changed_text
        lobe.last_output = changed_text
        content = result.setdefault("content", {})
        if isinstance(content, dict):
            content["text"] = changed_text
            formatted = content.get("formatted")
            if isinstance(formatted, dict):
                formatted["text"] = changed_text
    content = result.setdefault("content", {})
    if isinstance(content, dict):
        content["learned_guidance"] = list(guidance)
        content["learned_guidance_used"] = applied
        formatted = content.get("formatted")
        if isinstance(formatted, dict):
            formatted["learned_guidance"] = list(guidance)
            formatted["learning_applied"] = applied
    result["learned_guidance_used"] = applied
    return result


def _cache_staged_rule(lobe: Any, user_id: str, key: str, fact: str) -> None:
    cache = getattr(lobe, "_runtime_staged_guidance", None)
    if not isinstance(cache, dict):
        cache = {}
        setattr(lobe, "_runtime_staged_guidance", cache)
    cache.setdefault(user_id, {})[key] = fact


def _clear_staged_rule(lobe: Any, user_id: str, key: str) -> None:
    cache = getattr(lobe, "_runtime_staged_guidance", None)
    if not isinstance(cache, dict):
        return
    user_cache = cache.get(user_id)
    if isinstance(user_cache, dict):
        user_cache.pop(key, None)
        if not user_cache:
            cache.pop(user_id, None)


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

        if (
            destination in {"conversation", "emotion", "output"}
            and msg_type == "learn"
            and isinstance(result, dict)
            and result.get("status") == "success"
            and isinstance(payload, dict)
        ):
            fact = payload.get("fact")
            if isinstance(fact, str) and (_relation_from_guidance(fact) is not None or _trigger_from_guidance(fact) is not None):
                result_content = result.get("content", {})
                key = result.get("key")
                if not isinstance(key, str) and isinstance(result_content, dict):
                    key = result_content.get("key")
                if isinstance(key, str) and key:
                    user_id = self._normalised_user_id(payload)
                    staged = original_send_message(
                        destination,
                        "stage_activation",
                        {"user_id": user_id, "key": key},
                        "runtime_integration:staging",
                    )
                    if isinstance(staged, dict) and staged.get("status") == "success":
                        _cache_staged_rule(systems[destination], user_id, key, fact)
                        result["staged_for_validation"] = True
                    else:
                        result["staged_for_validation"] = False
                        result["staging_error"] = staged.get("message") if isinstance(staged, dict) else "unknown staging failure"

        if (
            destination in {"conversation", "emotion", "output"}
            and msg_type in {"promote_learning", "rollback_staged", "forget_learning", "deprecate_learning_id"}
            and isinstance(payload, dict)
        ):
            key = payload.get("key")
            if isinstance(key, str) and key:
                _clear_staged_rule(systems[destination], self._normalised_user_id(payload), key)

        if isinstance(result, dict) and isinstance(payload, dict):
            if destination == "emotion" and msg_type == "process_input":
                result = _postprocess_emotion(systems["emotion"], payload, result)
            elif destination == "output" and msg_type == "generate_output":
                result = _postprocess_output(systems["output"], payload, result)
        return result

    thalamus.send_message = MethodType(send_message, thalamus)

    if "conversation" in systems:
        _wrap_conversation(systems["conversation"])
