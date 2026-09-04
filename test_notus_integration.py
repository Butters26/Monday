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
        assert failing_notus.store_calls == 2
        assert failing_notus.query_calls == 2
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
