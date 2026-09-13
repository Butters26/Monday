from run_abin import create_core_systems, shutdown_core_systems


def _activate(store, user_id, key, fact, subject):
    result = store.learn(
        {
            "user_id": user_id,
            "key": key,
            "fact": fact,
            "confidence": 0.95,
            "record": {
                "type": "rule",
                "subject": subject,
                "surface": subject,
                "value": fact,
                "status": "active",
            },
            "required_evidence": [],
        }
    )
    assert result["status"] == "success"
    assert result["content"]["status"] == "active"


def test_real_lobes_receive_and_use_active_learning_and_pattern_is_live(tmp_path):
    systems = create_core_systems(runtime_directory=str(tmp_path))
    thalamus = systems["thalamus"]
    user_id = "integration-user"
    probe = "anchor signal"

    try:
        subjects = {
            "conversation": "reply_guidance",
            "emotion": "emotion_response_guidance",
            "reasoning": "inference_preferences",
            "language": "generation_guidance",
            "output": "delivery_tone",
        }
        for name, subject in subjects.items():
            _activate(
                systems[name]._lobe_learning_store,
                user_id,
                f"integration:{name}",
                f"For anchor signal, apply {name} learned rule.",
                subject,
            )

        conversation = thalamus.send_message(
            "conversation", "understand", {"user_input": probe, "user_id": user_id}
        )
        assert conversation["status"] == "success"
        assert conversation["content"]["learned_guidance_used"] is True
        assert conversation["content"]["understanding"]["learning_applied"] is True

        emotion = thalamus.send_message(
            "emotion", "process_input", {"user_input": probe, "user_id": user_id}
        )
        assert emotion["status"] == "success"
        assert emotion["content"]["learned_guidance_used"] is True

        reasoning = thalamus.send_message(
            "reasoning",
            "think",
            {
                "user_id": user_id,
                "user_input": probe,
                "input": {
                    "user_id": user_id,
                    "user_input": probe,
                    "understanding": conversation["content"]["understanding"],
                    "memory_context": {"memories": []},
                    "emotion_result": emotion["content"],
                },
            },
        )
        assert reasoning["status"] == "success"
        assert reasoning["content"]["learned_guidance_used"] is True

        language = thalamus.send_message(
            "language",
            "generate",
            {
                "user_id": user_id,
                "user_input": probe,
                "semantic_input": {
                    "intent": "conversation",
                    "certainty": 0.8,
                },
            },
        )
        assert language["status"] == "success"
        assert language["learned_guidance_used"] is True

        output = thalamus.send_message(
            "output",
            "generate_output",
            {
                "user_id": user_id,
                "user_input": probe,
                "text": "baseline output",
                "emotion": "neutral",
                "intensity": 0.5,
                "preserve_text": True,
            },
        )
        assert output["status"] == "success"
        assert output["content"]["learned_guidance_used"] is True

        final = thalamus.process_user_input(probe, user_id=user_id)
        assert isinstance(final, str) and final.strip()
        assert user_id in thalamus._latest_pattern_by_user
        assert isinstance(thalamus._latest_pattern_by_user[user_id], dict)
    finally:
        shutdown_core_systems(systems)
