import sys
import tempfile
import types
import unittest
from pathlib import Path


def _install_notus_import_stubs():
    if "numpy" not in sys.modules:
        numpy_stub = types.ModuleType("numpy")
        numpy_stub.ndarray = object
        numpy_stub.zeros = lambda *args, **kwargs: []
        numpy_stub.array = lambda *args, **kwargs: []
        numpy_stub.dot = lambda *args, **kwargs: 0.0
        numpy_stub.linalg = types.SimpleNamespace(norm=lambda *args, **kwargs: 1.0)
        sys.modules["numpy"] = numpy_stub

    if "torch" not in sys.modules:
        sys.modules["torch"] = types.ModuleType("torch")

    if "psycopg2" not in sys.modules:
        psycopg2_stub = types.ModuleType("psycopg2")
        psycopg2_extras_stub = types.ModuleType("psycopg2.extras")
        psycopg2_extras_stub.RealDictCursor = object
        psycopg2_stub.extras = psycopg2_extras_stub
        sys.modules["psycopg2"] = psycopg2_stub
        sys.modules["psycopg2.extras"] = psycopg2_extras_stub


_install_notus_import_stubs()

from notus import DirectNotusProcess, NotusProcess


class FakeThalamus:
    def __init__(self):
        self.registrations = []

    def register_lobe(self, name, lobe):
        self.registrations.append((name, lobe))
        return {"status": "success"}


class DirectNotusProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage_path = Path(self.temp_dir.name) / "nested" / "notus.sqlite3"
        self.thalamus = FakeThalamus()

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_notus(self):
        return DirectNotusProcess(storage_path=str(self.storage_path), thalamus=self.thalamus)

    def test_initializes_storage_and_registers_with_thalamus(self):
        notus = self.create_notus()
        try:
            self.assertTrue(self.storage_path.exists())
            self.assertTrue(notus.memory_ready.is_set())
            self.assertIs(notus.start(), notus)
            self.assertEqual(self.thalamus.registrations, [("notus", notus)])
            self.assertIs(NotusProcess, DirectNotusProcess)
        finally:
            notus.shutdown()

    def test_store_and_retrieve_memories_filters_rows(self):
        notus = self.create_notus()
        try:
            stored = notus._store(
                {
                    "role": "user",
                    "content": "  Gravity pulls objects together.  ",
                    "user_id": "alice",
                    "memory_type": "fact",
                }
            )
            self.assertEqual(
                stored,
                {
                    "status": "success",
                    "content": {"stored": True, "content": "Gravity pulls objects together."},
                },
            )

            notus._connection.execute(
                "INSERT INTO memories(role, content, user_id, memory_type, created_at) VALUES (?, ?, ?, ?, ?)",
                ("note", "User: hidden transcript", "alice", "conversation", "2000-01-01T00:00:00+00:00"),
            )
            notus._connection.execute(
                "INSERT INTO memories(role, content, user_id, memory_type, created_at) VALUES (?, ?, ?, ?, ?)",
                ("assistant", "visible but unsupported role", "alice", "conversation", "2000-01-01T00:00:01+00:00"),
            )
            notus._connection.execute(
                "INSERT INTO memories(role, content, user_id, memory_type, created_at) VALUES (?, ?, ?, ?, ?)",
                ("fact", "Gravity is a force.", "bob", "fact", "2000-01-01T00:00:02+00:00"),
            )
            notus._connection.commit()

            memories = notus.retrieve_memories("gravity user", user_id="alice", limit="25")

            self.assertEqual(len(memories), 1)
            self.assertEqual(memories[0]["role"], "user")
            self.assertEqual(memories[0]["content"], "Gravity pulls objects together.")
            self.assertEqual(memories[0]["user_id"], "alice")
            self.assertEqual(memories[0]["memory_type"], "fact")
            self.assertEqual(notus.retrieve_memories("gravity", user_id=object()), [])
        finally:
            notus.shutdown()

    def test_rejects_invalid_store_payloads(self):
        notus = self.create_notus()
        try:
            self.assertEqual(
                notus._store({"role": "user", "content": "", "user_id": "alice"}),
                {"status": "error", "message": "Memory must be clean structured content"},
            )
            self.assertEqual(
                notus._store({"role": "user", "content": "User: transcript", "user_id": "alice"}),
                {"status": "error", "message": "Memory must be clean structured content"},
            )
            self.assertEqual(
                notus._store({"role": "user", "content": "ok", "user_id": ""}),
                {"status": "error", "message": "Memory user_id must be a non-empty string"},
            )
        finally:
            notus.shutdown()

    def test_process_message_routes_supported_queries(self):
        notus = self.create_notus()
        try:
            self.assertEqual(
                notus.process_message({"type": "health"}),
                {"status": "success", "content": {"healthy": True, "memory_status": "ready"}},
            )

            store_result = notus.process_message(
                {
                    "type": "store",
                    "content": {"role": "note", "content": "remember this", "user_id": "alice"},
                }
            )
            self.assertEqual(store_result["status"], "success")

            query_result = notus.process_message(
                {"type": "query_semantic", "content": {"query": "remember", "user_id": "alice", "limit": 1}}
            )
            self.assertEqual(query_result["status"], "success")
            self.assertEqual(query_result["content"]["results"], query_result["content"]["memories"])
            self.assertEqual(query_result["content"]["results"][0]["content"], "remember this")

            context_result = notus.process_message(
                {"type": "query_context", "content": {"text": "remember", "user_id": "alice", "max_results": 1}}
            )
            self.assertEqual(context_result["status"], "success")
            self.assertEqual(context_result["content"]["query_text"], "remember")
            self.assertEqual(context_result["content"]["semantic"], query_result["content"]["results"])
            self.assertEqual(context_result["content"]["episodic"], [])
            self.assertEqual(context_result["content"]["facts"], [])
            self.assertEqual(context_result["content"]["summary"], "Found 1 stored memories")

            self.assertEqual(
                notus.process_message({"type": "query_episodic"}),
                {"status": "success", "content": {"events": []}},
            )
            self.assertEqual(
                notus.process_message({"type": "query_facts"}),
                {"status": "success", "content": {"facts": []}},
            )
            self.assertEqual(
                notus.process_message({"type": "query_patterns"}),
                {"status": "success", "content": {"patterns": []}},
            )
            self.assertEqual(
                notus.process_message({"type": "unknown"}),
                {"status": "error", "message": "Unknown message type: unknown"},
            )
        finally:
            notus.shutdown()

    def test_shutdown_closes_connection_and_blocks_restart(self):
        notus = self.create_notus()

        notus.shutdown()

        self.assertFalse(notus.running)
        with self.assertRaisesRegex(RuntimeError, "Notus is closed"):
            notus.retrieve_memories("anything")
        with self.assertRaisesRegex(RuntimeError, "Cannot restart a closed Notus adapter"):
            notus.start()


if __name__ == "__main__":
    unittest.main()
