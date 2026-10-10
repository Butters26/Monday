import importlib.util
import unittest
from pathlib import Path


def _load_checker():
    path = Path(__file__).with_name("data_checker.py")
    spec = importlib.util.spec_from_file_location("_monday_preproduction_data_checker", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.DataChecker()


class DataCheckerTests(unittest.TestCase):
    def setUp(self):
        self.checker = _load_checker()

    def test_valid_evidence_ratio_and_provenance_pass(self):
        payload = {
            "provenance_ids": ["notus-1", "notus-2"],
            "supporting_count": 1,
            "contradicting_count": 1,
            "confidence": 0.5,
        }

        self.assertTrue(self.checker.validate_notus_provenance(payload))

    def test_missing_or_duplicate_provenance_is_rejected(self):
        for ids in ([], ["notus-1", "notus-1"]):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                self.checker.validate_notus_provenance(
                    {"provenance_ids": ids, "confidence": 0}
                )

    def test_mismatched_or_invalid_confidence_is_rejected(self):
        invalid_payloads = (
            {
                "provenance_ids": ["notus-1", "notus-2"],
                "supporting_count": 1,
                "contradicting_count": 1,
                "confidence": 0.7,
            },
            {
                "provenance_ids": ["notus-1"],
                "confidence": float("nan"),
            },
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.checker.validate_notus_provenance(payload)

    def test_zero_evidence_only_allows_zero_confidence(self):
        self.assertTrue(
            self.checker.validate_notus_provenance(
                {"provenance_ids": ["notus-1"], "confidence": 0}
            )
        )
        with self.assertRaises(ValueError):
            self.checker.validate_notus_provenance(
                {"provenance_ids": ["notus-1"], "confidence": 0.2}
            )

    def test_schema_sanitization_is_case_insensitive_and_non_mutating(self):
        original = {"ordinary": 1, "THALAMUS_ROUTER": "replace", "nested": {"core_daemon": 2}}

        result = self.checker.sanitize_liquid_schema(original)

        self.assertEqual(result, {"ordinary": 1, "nested": {"core_daemon": 2}})
        self.assertIn("THALAMUS_ROUTER", original)

    def test_output_phrase_validation(self):
        self.assertTrue(self.checker.validate_output_stream("Pixel is a dog."))
        with self.assertRaises(ValueError):
            self.checker.validate_output_stream("As an AI, I cannot help.")
        with self.assertRaises(TypeError):
            self.checker.validate_output_stream(None)


if __name__ == "__main__":
    unittest.main()
