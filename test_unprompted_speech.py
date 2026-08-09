#!/usr/bin/env python3
"""Verify Reasoning is the only source of autonomous speech."""

import unittest

from autonomous_speech import AutonomousSpeechSystem
from thalamus import Thalamus


class ReasoningStub:
    def __init__(self):
        self.actions = [
            {
                "type": "message",
                "id": "reasoning-thought-1",
                "content": "I noticed a connection worth sharing.",
                "thought_type": "observation",
                "intensity": 0.85,
            }
        ]

    def process_message(self, message):
        if message["type"] == "get_autonomous_actions":
            actions, self.actions = self.actions, []
            return {"status": "success", "actions": actions}
        return {"status": "error", "message": "Unknown message type"}


class LanguageStub:
    def process_message(self, message):
        self.assertEqual(message["type"], "express")
        return {"status": "success", "sentence": message["thought"]}

    def assertEqual(self, left, right):
        if left != right:
            raise AssertionError(f"{left!r} != {right!r}")


class OutputStub:
    def __init__(self):
        self.messages = []

    def process_message(self, message):
        self.messages.append(message["text"])
        return {"status": "success", "text": message["text"]}


class AutonomousSpeechPipelineTest(unittest.TestCase):
    def setUp(self):
        self.thalamus = Thalamus()
        self.reasoning = ReasoningStub()
        self.speech = AutonomousSpeechSystem()
        self.speech.thalamus = self.thalamus
        self.output = OutputStub()
        for name, lobe in {
            "reasoning": self.reasoning,
            "speech": self.speech,
            "language": LanguageStub(),
            "output": self.output,
        }.items():
            self.thalamus.register_lobe(name, lobe)

    def test_reasoning_candidate_is_gated_then_delivered(self):
        actions = self.thalamus.send_message("reasoning", "get_autonomous_actions")["actions"]
        decisions = self.thalamus._route_autonomous_actions(actions)
        self.assertEqual(decisions[0]["decision"]["timing"], "now")

        self.thalamus._deliver_pending_autonomous_speech()

        self.assertEqual(self.output.messages, ["I noticed a connection worth sharing."])
        self.assertEqual(
            self.thalamus.get_autonomous_delivery()["content"],
            "I noticed a connection worth sharing.",
        )

    def test_typing_holds_candidate_until_a_natural_pause(self):
        self.speech.user_is_typing = True
        actions = self.thalamus.send_message("reasoning", "get_autonomous_actions")["actions"]
        decisions = self.thalamus._route_autonomous_actions(actions)
        self.assertEqual(decisions[0]["decision"]["timing"], "wait")

        self.thalamus._deliver_pending_autonomous_speech()
        self.assertEqual(self.output.messages, [])

        self.speech.user_is_typing = False
        self.thalamus._deliver_pending_autonomous_speech()
        self.assertEqual(self.output.messages, ["I noticed a connection worth sharing."])


if __name__ == "__main__":
    unittest.main()
