import importlib.util
import sys
import types
import unittest
from pathlib import Path


def _load_reasoning_copy():
    module_path = Path(__file__).with_name("reasoning.py")
    module_name = "_monday_preproduction_reasoning"
    thalamus_was_loaded = "thalamus" in sys.modules
    previous_thalamus = sys.modules.get("thalamus")
    stub = types.ModuleType("thalamus")
    stub.get_thalamus = lambda: None
    sys.modules["thalamus"] = stub
    try:
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(module_name, None)
        if thalamus_was_loaded:
            sys.modules["thalamus"] = previous_thalamus
        else:
            sys.modules.pop("thalamus", None)


def _evidence(record_id, stance, entities=None):
    return {
        "id": record_id,
        "stance": stance,
        "entities": entities or [],
    }


class GroundingGuardTests(unittest.TestCase):
    def test_empty_provenance_is_rejected(self):
        guard = _load_reasoning_copy().PropositionGroundingGuard()

        result = guard.evaluate_proposition(
            {"content": "Unsupported claim.", "provenance_ids": [], "entities": []},
            [],
        )

        self.assertEqual(result["status"], "REJECTED")
        self.assertIsNone(result["output"])

    def test_provenance_must_resolve_to_supplied_notus_records(self):
        guard = _load_reasoning_copy().PropositionGroundingGuard()

        result = guard.evaluate_proposition(
            {
                "content": "Claim.",
                "provenance_ids": ["missing-record"],
                "entities": [],
            },
            [_evidence("available-record", "supports")],
        )

        self.assertEqual(result["status"], "REJECTED")
        self.assertIsNone(result["output"])

    def test_support_below_floor_returns_neutral_without_assertion(self):
        guard = _load_reasoning_copy().PropositionGroundingGuard(confidence_floor=0.6)

        result = guard.evaluate_proposition(
            {
                "content": "Claim.",
                "provenance_ids": ["support", "contradiction"],
                "entities": [],
            },
            [
                _evidence("support", "supports"),
                _evidence("contradiction", "contradicts"),
            ],
        )

        self.assertEqual(result["status"], "NEUTRAL_DEADLOCK")
        self.assertEqual(result["confidence"], 0.5)
        self.assertIsNone(result["output"])

    def test_supported_proposition_cannot_add_unsupported_entities(self):
        guard = _load_reasoning_copy().PropositionGroundingGuard()

        result = guard.evaluate_proposition(
            {
                "content": "Pixel belongs to Alex.",
                "provenance_ids": ["fact-1"],
                "entities": ["Pixel", "Alex"],
            },
            [_evidence("fact-1", "supports", ["Pixel"])],
        )

        self.assertEqual(result["status"], "REJECTED")
        self.assertEqual(result["reason"], "unsupported_entities")

    def test_valid_grounded_proposition_and_realization_entity_check(self):
        guard = _load_reasoning_copy().PropositionGroundingGuard()
        records = [
            _evidence("fact-1", "supports", ["Pixel"]),
            _evidence("fact-2", "supports", ["Pixel"]),
        ]

        result = guard.evaluate_proposition(
            {
                "content": "Pixel is a dog.",
                "provenance_ids": ["fact-1", "fact-2"],
                "entities": ["Pixel"],
            },
            records,
        )

        self.assertEqual(result["status"], "GROUNDED")
        self.assertEqual(result["confidence"], 1.0)
        self.assertEqual(result["output"], "Pixel is a dog.")
        self.assertTrue(guard.validate_realized_entities(result, ["Pixel"]))
        self.assertFalse(guard.validate_realized_entities(result, ["Pixel", "Alex"]))
