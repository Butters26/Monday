#!/usr/bin/env python3
"""Compatibility facade for the retired autonomous thought generator.

Continuous cognition now belongs exclusively to ``reasoning.py``.  This lobe
remains import-compatible for older callers but neither generates canned
thoughts nor originates speech.
"""

import time
from typing import Any, Dict

from thalamus import get_thalamus


class AutonomousThinkingLoop:
    """Deprecated adapter; Reasoning is the sole autonomous thought source."""

    def __init__(self):
        self.thalamus = get_thalamus()
        self.running = True
        self.thalamus.register_lobe("autonomous", self)

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        message_type = message.get("type")
        if message_type in {"health", "process_interaction"}:
            return {
                "status": "success",
                "autonomous_source": "reasoning",
                "generated": False,
            }
        if message_type in {"get_pending_thoughts", "get_recent_thoughts"}:
            return {
                "status": "success",
                "thoughts": [],
                "count": 0,
                "autonomous_source": "reasoning",
            }
        return {
            "status": "error",
            "message": "Autonomous thought generation is provided by reasoning",
        }

    def start(self):
        """Keep the legacy lobe available without starting a second thinker."""
        while self.running:
            time.sleep(0.1)

    def shutdown(self):
        self.running = False
