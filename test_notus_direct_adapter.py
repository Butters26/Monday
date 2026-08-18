import pytest

from notus import DirectNotusProcess, NotusProcess


class FakeThalamus:
    def __init__(self):
        self.registrations = []

    def register_lobe(self, name, lobe):
        self.registrations.append((name, lobe))
        return {"status": "success"}


def test_direct_notus_initializes_storage_and_registers_with_thalamus(tmp_path):
    storage_path = tmp_path / "nested" / "notus.sqlite3"
    thalamus = FakeThalamus()

    notus = DirectNotusProcess(storage_path=str(storage_path), thalamus=thalamus)

    try:
        assert storage_path.exists()
        assert notus.memory_ready.is_set()
        assert notus.start() is notus
        assert thalamus.registrations == [("notus", notus)]
        assert NotusProcess is DirectNotusProcess
    finally:
        notus.shutdown()


def test_direct_notus_store_and_retrieve_memories_filters_rows(tmp_path):
    notus = DirectNotusProcess(storage_path=str(tmp_path / "notus.sqlite3"), thalamus=FakeThalamus())

    try:
        stored = notus._store(
            {
                "role": "user",
                "content": "  Gravity pulls objects together.  ",
                "user_id": "alice",
                "memory_type": "fact",
            }
        )
        assert stored == {
            "status": "success",
            "content": {"stored": True, "content": "Gravity pulls objects together."},
        }

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

        assert memories == [
            {
                "role": "user",
                "content": "Gravity pulls objects together.",
                "user_id": "alice",
                "memory_type": "fact",
                "timestamp": memories[0]["timestamp"],
            }
        ]
        assert notus.retrieve_memories("gravity", user_id=object()) == []
    finally:
        notus.shutdown()


def test_direct_notus_rejects_invalid_store_payloads(tmp_path):
    notus = DirectNotusProcess(storage_path=str(tmp_path / "notus.sqlite3"), thalamus=FakeThalamus())

    try:
        assert notus._store({"role": "user", "content": "", "user_id": "alice"}) == {
            "status": "error",
            "message": "Memory must be clean structured content",
        }
        assert notus._store({"role": "user", "content": "User: transcript", "user_id": "alice"}) == {
            "status": "error",
            "message": "Memory must be clean structured content",
        }
        assert notus._store({"role": "user", "content": "ok", "user_id": ""}) == {
            "status": "error",
            "message": "Memory user_id must be a non-empty string",
        }
    finally:
        notus.shutdown()


def test_direct_notus_process_message_routes_supported_queries(tmp_path):
    notus = DirectNotusProcess(storage_path=str(tmp_path / "notus.sqlite3"), thalamus=FakeThalamus())

    try:
        assert notus.process_message({"type": "health"}) == {
            "status": "success",
            "content": {"healthy": True, "memory_status": "ready"},
        }

        store_result = notus.process_message(
            {
                "type": "store",
                "content": {"role": "note", "content": "remember this", "user_id": "alice"},
            }
        )
        assert store_result["status"] == "success"

        query_result = notus.process_message(
            {"type": "query_semantic", "content": {"query": "remember", "user_id": "alice", "limit": 1}}
        )
        assert query_result["status"] == "success"
        assert query_result["content"]["results"] == query_result["content"]["memories"]
        assert query_result["content"]["results"][0]["content"] == "remember this"

        context_result = notus.process_message(
            {"type": "query_context", "content": {"text": "remember", "user_id": "alice", "max_results": 1}}
        )
        assert context_result == {
            "status": "success",
            "content": {
                "query_text": "remember",
                "semantic": query_result["content"]["results"],
                "episodic": [],
                "facts": [],
                "summary": "Found 1 stored memories",
            },
        }

        assert notus.process_message({"type": "query_episodic"}) == {
            "status": "success",
            "content": {"events": []},
        }
        assert notus.process_message({"type": "query_facts"}) == {
            "status": "success",
            "content": {"facts": []},
        }
        assert notus.process_message({"type": "query_patterns"}) == {
            "status": "success",
            "content": {"patterns": []},
        }
        assert notus.process_message({"type": "unknown"}) == {
            "status": "error",
            "message": "Unknown message type: unknown",
        }
    finally:
        notus.shutdown()


def test_direct_notus_shutdown_closes_connection(tmp_path):
    notus = DirectNotusProcess(storage_path=str(tmp_path / "notus.sqlite3"), thalamus=FakeThalamus())

    notus.shutdown()

    assert notus.running is False
    with pytest.raises(RuntimeError, match="Notus is closed"):
        notus.retrieve_memories("anything")
    with pytest.raises(RuntimeError, match="Cannot restart a closed Notus adapter"):
        notus.start()
