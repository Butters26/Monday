"""Common contracts and lifecycle normalization for lobe learning."""

from __future__ import annotations

from typing import Any, Dict, Protocol


class ExperienceLearningLobe(Protocol):
    """Protocol for lobes that can interpret and update from a shared envelope."""

    supports_experience_learning: bool

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle learn_from_experience and normal processing messages."""


_DEFAULT_CONTRACT = {
    "learning_enabled": True,
    "capabilities": {"facts", "rules"},
    "allowed_record_types": {"fact", "rule"},
    "mutable_surfaces": {"behavior_rules"},
    "fixed_surfaces": {"core_pipeline"},
    "required_evidence": {"saved", "retrieved", "applied", "behavior_changed", "validated"},
}

_LOBE_CONTRACTS: Dict[str, Dict[str, Any]] = {
    "conversation": {
        "capabilities": {"facts", "rules", "feedback"},
        "allowed_record_types": {"fact", "rule", "example", "exception"},
        "mutable_surfaces": {"tone_policy", "reply_guidance"},
        "fixed_surfaces": {"envelope_shape"},
    },
    "reasoning": {
        "capabilities": {"facts", "rules", "procedures"},
        "allowed_record_types": {"fact", "rule", "procedure", "exception"},
        "mutable_surfaces": {"inference_preferences", "heuristic_selection"},
        "fixed_surfaces": {"message_routing"},
    },
    "emotion": {
        "capabilities": {"feedback", "rules"},
        "allowed_record_types": {"rule", "exception"},
        "mutable_surfaces": {"emotion_response_guidance"},
        "fixed_surfaces": {"emotion_state_engine"},
    },
    "pattern": {
        "capabilities": {"facts", "rules", "procedures"},
        "allowed_record_types": {"fact", "rule", "procedure", "example"},
        "mutable_surfaces": {"pattern_rules"},
        "fixed_surfaces": {"signal_pipeline"},
    },
    "language": {
        "capabilities": {"facts", "rules", "procedures", "feedback"},
        "allowed_record_types": {"fact", "rule", "procedure", "example", "exception"},
        "mutable_surfaces": {"generation_guidance"},
        "fixed_surfaces": {"surface_realizer_core"},
    },
    "output": {
        "capabilities": {"feedback", "rules"},
        "allowed_record_types": {"rule", "exception"},
        "mutable_surfaces": {"delivery_tone"},
        "fixed_surfaces": {"output_transport"},
    },
}


def resolve_lobe_contract(lobe: str, lobe_handler: Any) -> Dict[str, Any]:
    contract = dict(_DEFAULT_CONTRACT)
    contract.update(_LOBE_CONTRACTS.get(lobe, {}))
    handler_contract = getattr(lobe_handler, "learning_contract", None)
    if isinstance(handler_contract, dict):
        contract.update(handler_contract)
    contract["capabilities"] = set(contract.get("capabilities", set()))
    contract["allowed_record_types"] = set(contract.get("allowed_record_types", set()))
    contract["required_evidence"] = set(contract.get("required_evidence", set()))
    contract["mutable_surfaces"] = set(contract.get("mutable_surfaces", set()))
    contract["fixed_surfaces"] = set(contract.get("fixed_surfaces", set()))
    contract["learning_enabled"] = bool(contract.get("learning_enabled", True))
    return contract


def normalize_learning_result(lobe: str, event_id: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize lobe response into explicit lifecycle stages."""
    response = raw if isinstance(raw, dict) else {"status": "error", "message": "non-dict response"}
    content = response.get("content", response)
    if not isinstance(content, dict):
        content = {}

    delivered = bool(content.get("delivered", response.get("status") != "error"))
    interpreted = bool(content.get("interpreted", False))
    proposed = bool(content.get("proposed", content.get("update_proposed", False)))
    saved = bool(content.get("saved", content.get("update_accepted", False)))
    retrieved = bool(content.get("retrieved", False))
    applied = bool(content.get("applied", content.get("behavior_affected", False)))
    behavior_changed = bool(content.get("behavior_changed", content.get("behavior_affected", False)))
    validated = bool(content.get("validated", content.get("validation_passed", False)))

    return {
        "lobe": lobe,
        "event_id": event_id,
        "status": response.get("status", "error"),
        "delivered": delivered,
        "interpreted": interpreted,
        "proposed": proposed,
        "saved": saved,
        "retrieved": retrieved,
        "applied": applied,
        "behavior_changed": behavior_changed,
        "validated": validated,
        # Backward-compatible aliases
        "update_proposed": proposed,
        "update_accepted": saved,
        "behavior_affected": behavior_changed,
        "validation_passed": validated,
        "confidence": content.get("confidence"),
        "evidence": content.get("evidence", []),
        "changes": content.get("changes", {}),
        "message": response.get("message", content.get("message")),
    }
