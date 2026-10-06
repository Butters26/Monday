#!/usr/bin/env python3
"""Phase 4 routing bridge for Mercy's Thalamus.

HARD ROUTING RULE:
Thalamus routes information; it does not determine linguistic or semantic meaning.
Raw user language goes to Language comprehension first. Shared Representation is
then addressed only with already-resolved IDs/structures for storage, activation,
and retrieval.

This removes the live-path inversion where Thalamus asked Shared Representation
``resolve_from_text`` and Shared Representation had to delegate back to Language.
Phase 5 can fold this bridge into the native coordinator after migration cleanup.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from phase3_thalamus import Phase3Thalamus


class Phase4Thalamus(Phase3Thalamus):
    """Route raw language to Language first; route only IDs to SR afterward."""

    @staticmethod
    def _response_content(response: Dict[str, Any]) -> Dict[str, Any]:
        content = response.get("content")
        return content if isinstance(content, dict) else response

    def _empty_representation(self, user_id: str) -> Dict[str, Any]:
        return {
            "status": "absent",
            "resolved": [],
            "concept_ids": [],
            "referent_ids": [],
            "proposition_ids": [],
            "highly_active_concepts": [],
            "active_concepts": [],
            "activation": {},
            "language_understanding": None,
            "phase3_language_comprehension": False,
            "phase4_language_first": True,
            "legacy_raw_text_parser_used": False,
            "user_id": user_id,
            "source": "shared_representation",
        }

    def _activate_representation_ids(
        self,
        concept_ids: List[str],
        *,
        user_id: str,
    ) -> Dict[str, Any]:
        """Route activation by stable IDs only; never reinterpret text here."""
        activation: Dict[str, float] = {}
        highly_active: List[Dict[str, Any]] = []

        for concept_id in concept_ids:
            response = self.send_and_wait(
                "shared_representation",
                "activate",
                {
                    "concept_id": concept_id,
                    "amount": 1.0,
                    "spread": True,
                    "user_id": user_id,
                },
                source="thalamus",
            )
            if response.get("status") != "success":
                continue
            body = self._response_content(response)
            current = body.get("activation") or response.get("activation") or {}
            if isinstance(current, dict):
                for key, value in current.items():
                    try:
                        score = float(value)
                    except (TypeError, ValueError):
                        continue
                    activation[str(key)] = max(activation.get(str(key), 0.0), score)
            candidates = (
                body.get("highly_active_concepts")
                or response.get("highly_active_concepts")
                or []
            )
            if isinstance(candidates, list):
                highly_active = [dict(item) for item in candidates if isinstance(item, dict)]

        active_concepts: List[Dict[str, Any]] = []
        active_response = self.send_and_wait(
            "shared_representation",
            "get_active",
            {"user_id": user_id},
            source="thalamus",
        )
        if active_response.get("status") == "success":
            body = self._response_content(active_response)
            active = body.get("active_concepts") or active_response.get("active_concepts") or []
            if isinstance(active, list):
                active_concepts = [dict(item) for item in active if isinstance(item, dict)]

        return {
            "activation": activation,
            "highly_active_concepts": highly_active,
            "active_concepts": active_concepts,
        }

    def _resolve_representation_live(
        self,
        user_input: str,
        perception_payload: Optional[Dict[str, Any]] = None,
        user_id: str = "default",
    ) -> Dict[str, Any]:
        """Language → Shared Representation IDs → downstream routing envelope."""
        empty = self._empty_representation(user_id)
        with self.lobe_handlers_lock:
            has_language = "language" in self.lobe_handlers
            has_shared = "shared_representation" in self.lobe_handlers

        # No semantic fallback through Shared Representation. If Language is not
        # available, Thalamus reports absence rather than interpreting raw text.
        if not has_language or not has_shared:
            self.last_representation = None
            return empty

        try:
            language_response = self.send_and_wait(
                "language",
                "comprehend",
                {
                    "text": user_input or "",
                    "user_id": user_id,
                },
                source="thalamus",
            )
        except Exception:
            self.last_representation = None
            return empty

        if language_response.get("status") != "success":
            self.last_representation = None
            return empty

        body = self._response_content(language_response)
        understanding = body.get("language_understanding")
        concept_ids = [str(item) for item in (body.get("concept_ids") or []) if item]
        referent_ids = [str(item) for item in (body.get("referent_ids") or []) if item]
        proposition_ids = [str(item) for item in (body.get("proposition_ids") or []) if item]
        resolved = [
            dict(item)
            for item in (body.get("resolved_concepts") or body.get("resolved") or [])
            if isinstance(item, dict)
        ]

        activation_state = self._activate_representation_ids(
            concept_ids,
            user_id=user_id,
        )

        env: Dict[str, Any] = {
            "status": "success",
            "resolved": resolved,
            "concept_ids": concept_ids,
            "referent_ids": referent_ids,
            "proposition_ids": proposition_ids,
            "highly_active_concepts": activation_state["highly_active_concepts"],
            "active_concepts": activation_state["active_concepts"],
            "activation": activation_state["activation"],
            "language_understanding": understanding if isinstance(understanding, dict) else None,
            "phase3_language_comprehension": isinstance(understanding, dict),
            "phase4_language_first": True,
            "legacy_raw_text_parser_used": False,
            "user_id": user_id,
            "source": "shared_representation",
        }

        self.last_representation = dict(env)
        if isinstance(perception_payload, dict):
            # Routing metadata only. Perception did not derive these semantics.
            perception_payload["concept_ids"] = list(concept_ids)
            perception_payload["resolved_concepts"] = list(resolved)
            perception_payload["language_understanding"] = env["language_understanding"]
            perception_payload["referent_ids"] = list(referent_ids)
            perception_payload["proposition_ids"] = list(proposition_ids)
            perception_payload["representation_source"] = "language_via_shared_representation"

        return env


Thalamus = Phase4Thalamus

__all__ = ["Phase4Thalamus", "Thalamus"]
