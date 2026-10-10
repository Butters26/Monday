import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


RUNNER = Path(__file__).with_name("run_environment.py")


class PreProductionEnvironmentTests(unittest.TestCase):
    def test_demo_runs_complete_isolated_flow(self):
        result = subprocess.run(
            [sys.executable, str(RUNNER), "--demo"],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["evaluation"]["status"], "GROUNDED")
        self.assertTrue(output["realization_checked"])
        self.assertEqual(output["recalled_content"], "The test subject's dog's name is Pixel.")

    def test_json_line_runner_stores_and_recalls_without_live_runtime(self):
        with tempfile.TemporaryDirectory(prefix="monday-preproduction-test-") as temp_dir:
            database = Path(temp_dir) / "notus.sqlite3"
            env = dict(os.environ)
            env["MONDAY_PREPRODUCTION_RUNTIME_DIR"] = str(Path(temp_dir) / "runtime")
            result = subprocess.run(
                [sys.executable, str(RUNNER), "--database", str(database)],
                input=(
                    json.dumps(
                        {
                            "type": "store",
                            "content": {
                                "role": "fact",
                                "memory_type": "fact",
                                "user_id": "cli-test",
                                "content": "The test subject's dog's name is Pixel.",
                            },
                        }
                    )
                    + "\n"
                    + json.dumps(
                        {
                            "type": "recall",
                            "content": {"query": "Pixel", "user_id": "cli-test"},
                        }
                    )
                    + "\n"
                ),
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        responses = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(responses[0]["status"], "success")
        self.assertEqual(responses[1]["status"], "success")
        self.assertEqual(
            responses[1]["content"]["memories"][0]["content"],
            "The test subject's dog's name is Pixel.",
        )


if __name__ == "__main__":
    unittest.main()
