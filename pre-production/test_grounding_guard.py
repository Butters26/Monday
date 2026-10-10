import importlib.util
import os
import sys
import tempfile
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


def _load_notus_copy():
    module_path = Path(__file__).with_name("notus.py")
    module_name = "_monday_preproduction_notus"
    stubs = {
        "thalamus": types.ModuleType("thalamus"),
        "runtime_paths": types.ModuleType("runtime_paths"),
        "numpy": types.ModuleType("numpy"),
    }
    stubs["thalamus"].get_thalamus = lambda: None
    stubs["runtime_paths"].runtime_file = lambda name: os.path.join(
        tempfile.gettempdir(), name
    )
    stubs["numpy"].ndarray = object
    previous = {name: sys.modules.get(name) for name in stubs}
    missing = {name for name in stubs if name not in sys.modules}
    sys.modules.update(stubs)
    try:
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(module_name, None)
        for name in missing:
            sys.modules.pop(name, None)
        for name, old_module in previous.items():
            if old_module is not None:
                sys.modules[name] = old_module


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

    def test_sqlite_notus_record_flows_through_guard_before_realization(self):
        notus_module = _load_notus_copy()
        reasoning_module = _load_reasoning_copy()
        with tempfile.TemporaryDirectory(prefix="monday-preproduction-") as temp_dir:
            notus = notus_module.DirectNotusProcess(
                storage_path=str(Path(temp_dir) / "notus.sqlite3")
            )
            try:
                stored = notus.process_message(
                    {
                        "type": "store",
                        "content": {
                            "role": "fact",
                            "content": "My dog's name is Pixel.",
                            "user_id": "isolated-test-user",
                            "memory_type": "fact",
                        },
                    }
                )
                self.assertEqual(stored["status"], "success")
                record_id = str(stored["content"]["id"])

                recalled = notus.process_message(
                    {
                        "type": "query",
                        "content": {
                            "query": "Pixel",
                            "user_id": "isolated-test-user",
                        },
                    }
                )
                recalled_records = recalled["content"]["memories"]
                self.assertEqual(len(recalled_records), 1)
                self.assertEqual(str(recalled_records[0]["id"]), record_id)

                # The harness supplies evidence stance/entity extraction; Notus
                # itself only stores and recalls the statement and its identity.
                evidence_records = [
                    {
                        **recalled_records[0],
                        "stance": "supports",
                        "entities": ["Pixel"],
                    }
                ]
                guard = reasoning_module.PropositionGroundingGuard()
                evaluation = guard.evaluate_proposition(
                    {
                        "content": "Your dog's name is Pixel.",
                        "provenance_ids": [record_id],
                        "entities": ["Pixel"],
                    },
                    evidence_records,
                )
                self.assertEqual(evaluation["status"], "GROUNDED")
                self.assertEqual(evaluation["output"], "Your dog's name is Pixel.")
                self.assertTrue(
                    guard.validate_realized_entities(evaluation, ["Pixel"])
                )
                self.assertFalse(
                    guard.validate_realized_entities(evaluation, ["Pixel", "Alex"])
                )
            finally:
                notus.shutdown()
