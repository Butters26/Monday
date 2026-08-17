from run_abin import create_core_systems, shutdown_core_systems


def test_learning_system_records_interactions_and_status(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    try:
        systems["thalamus"].process_user_input("Hello Monday")
        systems["thalamus"].process_user_input("What is gravity?")

        status = systems["thalamus"].handle_request(
            {"type": "learning_status", "content": {"user_id": "default"}}
        )
        assert status["status"] == "success"
        assert status["content"]["interactions"] >= 2
        assert "average_quality" in status["content"]
        assert "improving" in status["content"]
    finally:
        shutdown_core_systems(systems)


def test_learning_system_feedback_override_and_forget_controls(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    try:
        systems["thalamus"].process_user_input("I like short answers", user_id="alice")

        override = systems["thalamus"].handle_request(
            {
                "type": "learning_override",
                "content": {
                    "user_id": "alice",
                    "pref_key": "response_style",
                    "pref_value": "concise",
                    "confidence": 2.0,  # bounded to 1.0
                },
            }
        )
        assert override["status"] == "success"
        assert override["content"]["confidence"] == 1.0

        feedback = systems["thalamus"].handle_request(
            {
                "type": "learning_feedback",
                "content": {"user_id": "alice", "feedback_score": 5, "reason": "too long"},
            }
        )
        assert feedback["status"] == "success"
        assert feedback["content"]["feedback_score"] == 1.0

        status = systems["thalamus"].handle_request(
            {"type": "learning_status", "content": {"user_id": "alice"}}
        )
        assert status["status"] == "success"
        assert status["content"]["feedback_events"] == 1
        assert any(pref["key"] == "response_style" for pref in status["content"]["preferences"])

        forget = systems["thalamus"].handle_request(
            {"type": "learning_forget_user", "content": {"user_id": "alice"}}
        )
        assert forget["status"] == "success"

        post_forget = systems["thalamus"].handle_request(
            {"type": "learning_status", "content": {"user_id": "alice"}}
        )
        assert post_forget["content"]["interactions"] == 0
        assert post_forget["content"]["feedback_events"] == 0
        assert post_forget["content"]["preferences"] == []
    finally:
        shutdown_core_systems(systems)
