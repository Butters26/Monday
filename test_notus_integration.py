"""Focused tests for Notus failure handling in the direct core path."""

from run_abin import create_core_systems, shutdown_core_systems


class FailingNotus:
    def __init__(self):
        self.store_calls = 0
        self.query_calls = 0
        self.health_calls = 0

    def process_message(self, message):
        msg_type = message.get("type")
        if msg_type == "store":
            self.store_calls += 1
            return {"status": "error", "message": "store unavailable", "content": {}}
        if msg_type == "query":
            self.query_calls += 1
            return {"status": "error", "message": "query unavailable", "content": {}}
        if msg_type == "health":
            self.health_calls += 1
            return {"status": "success", "content": {"healthy": False}}
        return {"status": "error", "message": "unsupported", "content": {}}

    def shutdown(self):
        return None


class RecoveringNotus:
    def __init__(self):
        self.available = False
        self.store_calls = 0
        self.query_calls = 0
        self.stored = []
        self.stored_ids = []
        self.fail_next_store = False

    def process_message(self, message):
        msg_type = message.get("type")
        payload = message.get("content", {})
        if msg_type == "store":
            self.store_calls += 1
            if not self.available or self.fail_next_store:
                self.fail_next_store = False
                return {"status": "error", "message": "store unavailable", "content": {}}
            self.stored.append(
                {
                    "user_id": payload.get("user_id"),
                    "content": payload.get("content"),
                    "role": payload.get("role"),
                }
            )
            self.stored_ids.append(payload.get("_thalamus_write_id"))
            return {"status": "success", "content": {"stored": True}}
        if msg_type == "query":
            self.query_calls += 1
            if not self.available:
                return {"status": "error", "message": "query unavailable", "content": {}}
            return {"status": "success", "content": {"memories": [], "results": []}}
        if msg_type == "health":
            return {"status": "success", "content": {"healthy": self.available}}
        return {"status": "error", "message": "unsupported", "content": {}}

    def shutdown(self):
        return None


def test_notus_failures_do_not_abort_response_pipeline(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    failing_notus = FailingNotus()
    systems["thalamus"].register_lobe("notus", failing_notus)
    try:
        response = systems["thalamus"].process_user_input(
            "Hello Monday, please respond calmly.", user_id="alice"
        )
        assert response
        assert "trouble remembering" not in response.lower()
        assert "trouble retrieving context" not in response.lower()
        assert failing_notus.store_calls >= 2
        assert failing_notus.query_calls >= 2
    finally:
        shutdown_core_systems(systems)


def test_fallback_memory_buffer_supports_follow_up_when_notus_unavailable(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    systems["thalamus"].register_lobe("notus", FailingNotus())
    try:
        systems["thalamus"].process_user_input(
            "My favorite snack is apples.", user_id="alice"
        )
        follow_up = systems["thalamus"].process_user_input(
            "What is my favorite snack?", user_id="alice"
        )
        assert "favorite snack is apples" in follow_up.lower()
    finally:
        shutdown_core_systems(systems)


def test_health_endpoint_performs_live_lobe_probes(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    failing_notus = FailingNotus()
    systems["thalamus"].register_lobe("notus", failing_notus)
    try:
        health = systems["thalamus"].handle_request({"type": "health"})
        assert health["status"] == "success"
        assert health["content"]["thalamus_healthy"] is False
        assert health["content"]["lobes"]["notus"]["healthy"] is False
        assert failing_notus.health_calls >= 1
    finally:
        shutdown_core_systems(systems)


def test_unsynced_notus_writes_replay_after_recovery(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    recovering_notus = RecoveringNotus()
    systems["thalamus"].register_lobe("notus", recovering_notus)
    try:
        systems["thalamus"].process_user_input(
            "This message should queue while Notus is down.", user_id="alice"
        )
        status_before = systems["thalamus"].handle_request({"type": "notus_sync_status"})
        assert status_before["status"] == "success"
        assert status_before["content"]["pending"].get("alice", 0) >= 1

        recovering_notus.available = True
        sync_result = systems["thalamus"].handle_request(
            {"type": "sync_notus_pending", "content": {"user_id": "alice"}}
        )
        assert sync_result["status"] == "success"
        assert sync_result["content"]["synced"] >= 1
        assert any(
            row["content"] == "This message should queue while Notus is down."
            and row["user_id"] == "alice"
            for row in recovering_notus.stored
        )
    finally:
        shutdown_core_systems(systems)


def test_sync_replay_is_deduplicated_per_write_id(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    recovering_notus = RecoveringNotus()
    systems["thalamus"].register_lobe("notus", recovering_notus)
    try:
        systems["thalamus"].process_user_input("duplicate queue test", user_id="alice")
        status = systems["thalamus"].handle_request({"type": "notus_sync_status"})
        assert status["status"] == "success"
        assert status["content"]["pending"].get("alice", 0) >= 1

        recovering_notus.available = True
        systems["thalamus"].handle_request(
            {"type": "sync_notus_pending", "content": {"user_id": "alice"}}
        )
        first_synced_ids = list(recovering_notus.stored_ids)
        systems["thalamus"].handle_request(
            {"type": "sync_notus_pending", "content": {"user_id": "alice"}}
        )
        assert recovering_notus.stored_ids == first_synced_ids
        assert len(recovering_notus.stored_ids) == len(set(recovering_notus.stored_ids))
    finally:
        shutdown_core_systems(systems)


def test_sync_stops_on_partial_failure_and_recovers_later(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    recovering_notus = RecoveringNotus()
    systems["thalamus"].register_lobe("notus", recovering_notus)
    try:
        systems["thalamus"].process_user_input("first queued write", user_id="alice")
        systems["thalamus"].process_user_input("second queued write", user_id="alice")
        recovering_notus.available = True
        recovering_notus.fail_next_store = True

        first_sync = systems["thalamus"].handle_request(
            {"type": "sync_notus_pending", "content": {"user_id": "alice", "limit": 10}}
        )
        assert first_sync["status"] == "success"
        assert first_sync["content"]["failed"] >= 1
        assert first_sync["content"]["pending"] >= 1

        second_sync = systems["thalamus"].handle_request(
            {"type": "sync_notus_pending", "content": {"user_id": "alice", "limit": 10}}
        )
        assert second_sync["status"] == "success"
        assert second_sync["content"]["pending"] == 0
        assert any(row["content"] == "first queued write" for row in recovering_notus.stored)
        assert any(row["content"] == "second queued write" for row in recovering_notus.stored)
    finally:
        shutdown_core_systems(systems)


def test_pending_notus_sync_respects_user_isolation(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    recovering_notus = RecoveringNotus()
    systems["thalamus"].register_lobe("notus", recovering_notus)
    try:
        systems["thalamus"].process_user_input("alice queued", user_id="alice")
        systems["thalamus"].process_user_input("bob queued", user_id="bob")

        recovering_notus.available = True
        sync_alice = systems["thalamus"].handle_request(
            {"type": "sync_notus_pending", "content": {"user_id": "alice"}}
        )
        assert sync_alice["status"] == "success"
        assert any(row["content"] == "alice queued" and row["user_id"] == "alice" for row in recovering_notus.stored)
        assert not any(row["content"] == "bob queued" for row in recovering_notus.stored)

        sync_bob = systems["thalamus"].handle_request(
            {"type": "sync_notus_pending", "content": {"user_id": "bob"}}
        )
        assert sync_bob["status"] == "success"
        assert any(row["content"] == "bob queued" and row["user_id"] == "bob" for row in recovering_notus.stored)
    finally:
        shutdown_core_systems(systems)
