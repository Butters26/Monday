"""
SensoryIntegrationLobe — thin fuse of normalized signals into perception.

Optional helper: normalize raw inputs and hand them to PerceptionLobe's
unified shape via thalamus (sensory_data). Not a socket theater loop.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class SensoryIntegrationLobe:
    def __init__(self, thalamus=None):
        self.thalamus = thalamus
        self.sensory_buffer: List[Any] = []
        self.normalized_signals: List[Any] = []

    def integrate_inputs(self, inputs):
        """Normalize inputs and optionally route strings into perception."""
        self.sensory_buffer.extend(inputs)
        self.normalized_signals = self._normalize(inputs)
        if self.thalamus:
            try:
                self.thalamus.send_message(
                    "perception",
                    "sensory_data",
                    {"signals": self.normalized_signals},
                    source="sensory_integration",
                )
            except Exception as e:
                print(f"[SensoryIntegrationLobe] Error routing to perception: {e}")
        return self.normalized_signals

    def _normalize(self, inputs):
        normalized = []
        for item in inputs:
            if isinstance(item, str):
                normalized.append(item.strip())
            elif isinstance(item, dict):
                # Preserve modality-tagged dicts; strip string fields lightly.
                out = dict(item)
                if isinstance(out.get("text"), str):
                    out["text"] = out["text"].strip()
                normalized.append(out)
            else:
                normalized.append(item)
        return normalized

    def reset(self):
        self.sensory_buffer.clear()
        self.normalized_signals.clear()

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = message.get("type")
        if "content" in message:
            content = message.get("content", {})
        else:
            content = {
                k: v
                for k, v in message.items()
                if k not in ("type", "_message_id", "message_id")
            }
        if msg_type == "ingest":
            inputs = content.get("inputs", [])
            signals = self.integrate_inputs(inputs)
            return {"status": "success", "signals": signals}
        if msg_type == "reset":
            self.reset()
            return {"status": "success", "message": "SensoryIntegrationLobe reset"}
        if msg_type == "get_status":
            return {
                "status": "success",
                "content": {
                    "buffer_size": len(self.sensory_buffer),
                    "last_normalized": len(self.normalized_signals),
                },
            }
        return {"status": "error", "message": f"Unknown message type: {msg_type}"}
