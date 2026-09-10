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
    "rejection_conditions": {
        "learning_disabled",
        "unsupported_record_type",
        "fixed_surface_mutation",
        "out_of_scope_surface",
        "missing_required_evidence",
    },
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
    contract["rejection_conditions"] = set(contract.get("rejection_conditions", set()))
    contract["learning_enabled"] = bool(contract.get("learning_enabled", True))
    return contract


def contract_rejection(
    contract: Dict[str, Any], msg_type: str, payload: Dict[str, Any]
) -> Dict[str, Any] | None:
    if msg_type in {"recall", "list_skills", "learning_stats"}:
        return None

    reasons = contract.get("rejection_conditions", set())
    reasons = reasons if isinstance(reasons, set) else set(reasons)

    if not bool(contract.get("learning_enabled", True)) and "learning_disabled" in reasons:
        return {"condition": "learning_disabled", "message": "Learning is disabled for this lobe"}

    record = payload.get("record", {})
    record = record if isinstance(record, dict) else {}
    if msg_type == "teach_skill":
        record_type = "rule"
    else:
        record_type = str(record.get("type", payload.get("record_type", "fact"))).strip().lower() or "fact"
    allowed_record_types = contract.get("allowed_record_types", set())
    allowed_record_types = (
        allowed_record_types if isinstance(allowed_record_types, set) else set(allowed_record_types)
    )
    if (
        record_type
        and allowed_record_types
        and record_type not in allowed_record_types
        and "unsupported_record_type" in reasons
    ):
        return {
            "condition": "unsupported_record_type",
            "message": f"Record type '{record_type}' is not allowed by lobe contract",
        }

    mutable_surfaces = contract.get("mutable_surfaces", set())
    mutable_surfaces = mutable_surfaces if isinstance(mutable_surfaces, set) else set(mutable_surfaces)
    fixed_surfaces = contract.get("fixed_surfaces", set())
    fixed_surfaces = fixed_surfaces if isinstance(fixed_surfaces, set) else set(fixed_surfaces)
    surface = payload.get("surface", record.get("surface", record.get("subject")))
    surface = str(surface).strip().lower() if isinstance(surface, str) and surface.strip() else ""
    if surface and surface in {item.lower() for item in fixed_surfaces} and "fixed_surface_mutation" in reasons:
        return {"condition": "fixed_surface_mutation", "message": f"Surface '{surface}' is fixed by contract"}
    if (
        surface
        and mutable_surfaces
        and surface not in {item.lower() for item in mutable_surfaces}
        and "out_of_scope_surface" in reasons
    ):
        return {
            "condition": "out_of_scope_surface",
            "message": f"Surface '{surface}' is outside mutable surfaces for this lobe",
        }

    record_status = str(record.get("status", payload.get("status", ""))).strip().lower()
    required_evidence = contract.get("required_evidence", set())
    required_evidence = required_evidence if isinstance(required_evidence, set) else set(required_evidence)
    provided_evidence = payload.get("evidence", record.get("evidence", []))
    provided_evidence = provided_evidence if isinstance(provided_evidence, list) else []
    provided = {str(item).strip() for item in provided_evidence if isinstance(item, str) and item.strip()}
    missing = sorted(item for item in required_evidence if item not in provided)
    if (
        record_status in {"validated", "active"}
        and missing
        and "missing_required_evidence" in reasons
    ):
        return {
            "condition": "missing_required_evidence",
            "message": "Validated/active updates require all contract evidence",
            "missing_evidence": missing,
        }
    return None


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
