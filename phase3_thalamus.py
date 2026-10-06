#!/usr/bin/env python3
"""Phase 3 routing bridge for Mercy's Thalamus.

This subclass changes no cognitive ownership. It only preserves the richer
Language → Shared Representation payload that the legacy Thalamus helper used
to discard while normalizing the Shared Representation response.

Phase 4 can fold this behavior into a cleaned native Thalamus once routing is
rewritten around stable representation IDs.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from thalamus import Thalamus as LegacyThalamus


class Phase3Thalamus(LegacyThalamus):
    """Legacy Thalamus with Phase 3 representation fields preserved."""

    def _resolve_representation_live(
        self,
        user_input: str,
        perception_payload: Optional[Dict[str, Any]] = None,
        user_id: str = "default",
    ) -> Dict[str, Any]:
        empty: Dict[str, Any] = {
            "status": "absent",
            "resolved": [],
            "concept_ids": [],
            "highly_active_concepts": [],
            "active_concepts": [],
            "activation": {},
            "user_id": user_id,
            "source": "shared_representation",
            "language_understanding": None,
            "referent_ids": [],
            "proposition_ids": [],
            "phase3_language_comprehension": False,
        }
        with self.lobe_handlers_lock:
            has = "shared_representation" in self.lobe_handlers
        if not has:
            self.last_representation = None
            return empty

        extra_terms: List[str] = []
        if isinstance(perception_payload, dict):
            concepts = perception_payload.get("concepts")
            if isinstance(concepts, list):
                for concept in concepts:
                    if isinstance(concept, str) and concept.strip():
                        extra_terms.append(concept.strip())
                    elif isinstance(concept, dict):
                        name = (
                            concept.get("name")
                            or concept.get("word")
                            or concept.get("canonical_name")
                        )
                        if name:
                            extra_terms.append(str(name))
            elif isinstance(concepts, dict):
                for word in concepts.get("words") or []:
                    if word:
                        extra_terms.append(str(word))

        try:
            response = self.send_and_wait(
                "shared_representation",
                "resolve_from_text",
                {
                    "text": user_input or "",
                    "terms": extra_terms,
                    "user_id": user_id,
                    "activate": True,
                },
                source="thalamus",
            )
        except Exception:
            self.last_representation = None
            return empty

        if response.get("status") != "success":
            self.last_representation = None
            return empty

        body = self._content(response)
        if not isinstance(body, dict):
            body = {}

        env: Dict[str, Any] = {
            "status": "success",
            "resolved": list(body.get("resolved") or response.get("resolved") or []),
            "concept_ids": list(body.get("concept_ids") or response.get("concept_ids") or []),
            "highly_active_concepts": list(
                body.get("highly_active_concepts")
                or response.get("highly_active_concepts")
                or []
            ),
            "active_concepts": list(
                body.get("active_concepts") or response.get("active_concepts") or []
            ),
            "activation": dict(body.get("activation") or response.get("activation") or {}),
            "user_id": body.get("user_id", user_id),
            "source": "shared_representation",
            "timestamp": body.get("timestamp"),
            # Phase 3 fields: routing only. Thalamus never interprets these.
            "language_understanding": body.get("language_understanding"),
            "referent_ids": list(body.get("referent_ids") or []),
            "proposition_ids": list(body.get("proposition_ids") or []),
            "phase3_language_comprehension": bool(
                body.get("phase3_language_comprehension")
            ),
            "legacy_raw_text_parser_used": body.get("legacy_raw_text_parser_used"),
        }

        self.last_representation = dict(env)
        if isinstance(perception_payload, dict):
            perception_payload["concept_ids"] = list(env["concept_ids"])
            perception_payload["resolved_concepts"] = list(env["resolved"])
            # Carry, don't interpret. Conversation/Reasoning may consume these
            # while their native interfaces migrate in later work.
            perception_payload["language_understanding"] = env.get("language_understanding")
            perception_payload["referent_ids"] = list(env.get("referent_ids") or [])
            perception_payload["proposition_ids"] = list(env.get("proposition_ids") or [])

        return env


Thalamus = Phase3Thalamus

__all__ = ["Phase3Thalamus", "Thalamus"]
