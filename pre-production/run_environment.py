#!/usr/bin/env python3
"""Run the isolated pre-production Notus and reasoning validation harness."""

import argparse
import importlib.util
import json
import os
import sys
import tempfile
import types
from pathlib import Path
from typing import Any, Dict

from data_checker import DataChecker


HERE = Path(__file__).resolve().parent


def _load_copy(name: str, extra_stubs: Dict[str, Any]):
    module_path = HERE / f"{name}.py"
    module_name = f"_monday_preproduction_{name}"
    previous = {key: sys.modules.get(key) for key in extra_stubs}
    missing = {key for key in extra_stubs if key not in sys.modules}
    sys.modules.update(extra_stubs)
    try:
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(module_name, None)
        for key in missing:
            sys.modules.pop(key, None)
        for key, module in previous.items():
            if module is not None:
                sys.modules[key] = module


def _load_notus():
    runtime_dir = Path(
        os.environ.get(
            "MONDAY_PREPRODUCTION_RUNTIME_DIR",
            Path.home() / ".local" / "state" / "monday-preproduction",
        )
    )
    runtime_dir.mkdir(parents=True, exist_ok=True)
    thalamus_stub = types.ModuleType("thalamus")
    thalamus_stub.get_thalamus = lambda: None
    paths_stub = types.ModuleType("runtime_paths")
    paths_stub.runtime_file = lambda name: str(runtime_dir / name)
    numpy_stub = types.ModuleType("numpy")
    numpy_stub.ndarray = object
    return _load_copy(
        "notus",
        {
            "thalamus": thalamus_stub,
            "runtime_paths": paths_stub,
            "numpy": numpy_stub,
        },
    )


def _load_reasoning():
    thalamus_stub = types.ModuleType("thalamus")
    thalamus_stub.get_thalamus = lambda: None
    return _load_copy("reasoning", {"thalamus": thalamus_stub})


class PreProductionEnvironment:
    def __init__(self, database: str):
        notus_module = _load_notus()
        reasoning_module = _load_reasoning()
        self.notus = notus_module.DirectNotusProcess(storage_path=database)
        self.guard = reasoning_module.PropositionGroundingGuard()
        self.checker = DataChecker()

    def close(self):
        self.notus.shutdown()

    def handle(self, command: Dict[str, Any]) -> Dict[str, Any]:
        operation = command.get("type")
        payload = command.get("content", command)
        if not isinstance(payload, dict):
            raise ValueError("content must be a JSON object")

        if operation == "health":
            return {"status": "success", "environment": "pre-production"}
        if operation == "store":
            return self.notus.process_message({"type": "store", "content": payload})
        if operation == "recall":
            return self.notus.process_message(
                {
                    "type": "query",
                    "content": {
                        "query": payload.get("query", ""),
                        "user_id": payload.get("user_id", "default"),
                        "limit": payload.get("limit", 15),
                    },
                }
            )
        if operation == "evaluate":
            proposition = payload.get("proposition")
            evidence_records = payload.get("evidence_records")
            if not isinstance(proposition, dict) or not isinstance(evidence_records, list):
                raise ValueError("evaluate requires proposition and evidence_records")

            evaluation = self.guard.evaluate_proposition(proposition, evidence_records)
            cited_ids = proposition.get("provenance_ids", [])
            cited = {
                str(record.get("id")): record
                for record in evidence_records
                if isinstance(record, dict) and record.get("id") is not None
            }
            supporting_count = sum(
                1 for record_id in set(map(str, cited_ids))
                if cited.get(record_id, {}).get("stance") == "supports"
            )
            contradicting_count = sum(
                1 for record_id in set(map(str, cited_ids))
                if cited.get(record_id, {}).get("stance") == "contradicts"
            )
            if evaluation["status"] in {"GROUNDED", "NEUTRAL_DEADLOCK"}:
                self.checker.validate_notus_provenance(
                    {
                        "provenance_ids": cited_ids,
                        "supporting_count": supporting_count,
                        "contradicting_count": contradicting_count,
                        "confidence": evaluation["confidence"],
                    }
                )

            realized_text = payload.get("realized_text")
            realized_entities = payload.get("realized_entities")
            if evaluation["status"] == "GROUNDED" and realized_text is not None:
                self.checker.validate_output_stream(realized_text)
                if not self.guard.validate_realized_entities(
                    evaluation, realized_entities
                ):
                    raise ValueError("realization introduced unsupported entities")
            return {
                "status": "success",
                "evaluation": evaluation,
                "realization_checked": (
                    evaluation["status"] == "GROUNDED" and realized_text is not None
                ),
            }
        if operation == "validate_output":
            self.checker.validate_output_stream(payload.get("text", ""))
            return {"status": "success", "valid": True}
        if operation == "sanitize_schema":
            schema = payload.get("schema")
            return {
                "status": "success",
                "schema": self.checker.sanitize_liquid_schema(schema),
            }
        raise ValueError(f"unsupported command type: {operation}")


def _run_demo(database: str) -> int:
    environment = PreProductionEnvironment(database)
    try:
        stored = environment.handle(
            {
                "type": "store",
                "content": {
                    "role": "fact",
                    "memory_type": "fact",
                    "user_id": "demo",
                    "content": "The test subject's dog's name is Pixel.",
                },
            }
        )
        memory_id = str(stored["content"]["id"])
        recalled = environment.handle(
            {"type": "recall", "content": {"query": "Pixel", "user_id": "demo"}}
        )
        memory = next(
            item
            for item in recalled["content"]["memories"]
            if str(item["id"]) == memory_id
        )
        result = environment.handle(
            {
                "type": "evaluate",
                "content": {
                    "proposition": {
                        "content": "The dog's name is Pixel.",
                        "provenance_ids": [memory_id],
                        "entities": ["Pixel"],
                    },
                    # The demo explicitly labels this fixture as supporting;
                    # Notus itself does not determine evidentiary stance.
                    "evidence_records": [
                        {**memory, "stance": "supports", "entities": ["Pixel"]}
                    ],
                    "realized_text": "The dog's name is Pixel.",
                    "realized_entities": ["Pixel"],
                },
            }
        )
        print(
            json.dumps(
                {
                    "stored_record_id": memory_id,
                    "recalled_content": memory["content"],
                    **result,
                },
                ensure_ascii=False,
            )
        )
        return 0 if result["evaluation"]["status"] == "GROUNDED" else 1
    finally:
        environment.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        help="SQLite path (default: private pre-production runtime directory)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="run a disposable end-to-end Notus-to-grounding example",
    )
    args = parser.parse_args(argv)

    if args.demo:
        with tempfile.TemporaryDirectory(prefix="monday-preproduction-") as temp_dir:
            return _run_demo(str(Path(temp_dir) / "notus.sqlite3"))

    if args.database:
        database = args.database
    else:
        runtime_dir = Path(
            os.environ.get(
                "MONDAY_PREPRODUCTION_RUNTIME_DIR",
                Path.home() / ".local" / "state" / "monday-preproduction",
            )
        )
        runtime_dir.mkdir(parents=True, exist_ok=True)
        database = str(runtime_dir / "notus.sqlite3")

    environment = PreProductionEnvironment(database)
    print(
        "Pre-production environment ready. Send one JSON command per line; "
        "Ctrl-D exits.",
        file=sys.stderr,
    )
    try:
        for line in sys.stdin:
            try:
                command = json.loads(line)
                if not isinstance(command, dict):
                    raise ValueError("each command must be a JSON object")
                result = environment.handle(command)
                print(json.dumps(result, ensure_ascii=False), flush=True)
            except Exception as exc:
                print(
                    json.dumps({"status": "error", "error": str(exc)}),
                    flush=True,
                )
    finally:
        environment.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
