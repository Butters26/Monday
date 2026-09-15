"""Shared helpers that let each lobe own application of learned guidance."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple


def safe_user(user_id: Any) -> str:
    return user_id.strip() if isinstance(user_id, str) and user_id.strip() else "default"


def relation_from_guidance(guidance: str) -> Optional[Tuple[str, str]]:
    if not isinstance(guidance, str):
        return None
    match = re.match(r"^\s*(.+?)\s+(?:means|is|equals|refers\s+to)\s+(.+?)\s*\.?\s*$", guidance, re.IGNORECASE)
    if not match:
        return None
    left = match.group(1).strip()
    right = match.group(2).strip()
    return (left, right) if left and right else None


def trigger_from_guidance(guidance: str) -> Optional[str]:
    if not isinstance(guidance, str):
        return None
    match = re.match(r"^\s*for\s+(.+?),\s+.+$", guidance, re.IGNORECASE)
    if match:
        trigger = match.group(1).strip()
        return trigger or None
    marker = re.search(r"(?:^|\|)\s*Trigger context:\s*([^|]+)", guidance, re.IGNORECASE)
    if marker:
        trigger = marker.group(1).strip()
        return trigger or None
    return None


def _normalise_guidance(items: Any) -> List[str]:
    if not isinstance(items, Iterable) or isinstance(items, (str, bytes, dict)):
        return []
    result: List[str] = []
    for item in items:
        if isinstance(item, str) and item.strip() and item.strip() not in result:
            result.append(item.strip())
    return result


def query_from_payload(payload: Dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("user_input", "text", "query"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for nested_key in ("input", "semantic_input", "data"):
        nested = payload.get(nested_key)
        if not isinstance(nested, dict):
            continue
        for key in ("user_input", "text", "query"):
            value = nested.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def guidance_applies(guidance: str, query: str) -> bool:
    if not isinstance(guidance, str) or not isinstance(query, str) or not query.strip():
        return False
    relation = relation_from_guidance(guidance)
    if relation is not None:
        return bool(re.search(re.escape(relation[0]), query, re.IGNORECASE))
    trigger = trigger_from_guidance(guidance)
    if trigger is not None:
        return bool(re.search(re.escape(trigger), query, re.IGNORECASE))
    return False


def applicable_guidance(items: Any, query: str) -> List[str]:
    return [item for item in _normalise_guidance(items) if guidance_applies(item, query)]


def effective_guidance(lobe: Any, payload: Dict[str, Any]) -> List[str]:
    """Return active guidance owned by this lobe that applies to this input.

    Thalamus may already inject guidance.  If it does not, the lobe asks its own
    persistent learning store.  This keeps actual application inside the lobe
    rather than in a global runtime postprocessor.
    """
    if not isinstance(payload, dict):
        return []
    query = query_from_payload(payload)
    if not query:
        return []

    supplied = applicable_guidance(payload.get("learned_guidance", []), query)
    if supplied:
        return supplied

    user_id = safe_user(
        payload.get("user_id")
        or (payload.get("input", {}).get("user_id") if isinstance(payload.get("input"), dict) else None)
        or (payload.get("semantic_input", {}).get("user_id") if isinstance(payload.get("semantic_input"), dict) else None)
    )
    store = getattr(lobe, "_lobe_learning_store", None)
    if store is None:
        return []

    def recall(query_text: str) -> List[Dict[str, Any]]:
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
        memories = content.get("memories", []) if isinstance(content, dict) else []
        return [row for row in memories if isinstance(row, dict)]

    memories = recall(query)
    if not memories:
        memories = recall("")
    facts = [
        row.get("fact", "").strip()
        for row in memories
        if isinstance(row.get("fact"), str) and row.get("fact", "").strip()
    ]
    return applicable_guidance(facts, query)
