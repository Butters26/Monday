from run_abin import create_core_systems, shutdown_core_systems


def test_trace_emotion_output_learning_status(tmp_path):
    systems = create_core_systems(str(tmp_path / "trace"))
    thalamus = systems["thalamus"]
    try:
        cases = {
            "emotion": ("emotion_response_guidance", "emotephrase means emotional-support context", "I feel emotephrase and sad", "process_input"),
            "output": ("delivery_tone", "outputphrase means concise delivery context", "outputphrase test", "generate_output"),
        }
        for lobe, (surface, fact, probe, msg_type) in cases.items():
            learned = thalamus.send_message(
                lobe,
                "learn",
                {
                    "user_id": "alice",
                    "key": f"{lobe}_owned_rule",
                    "fact": fact,
                    "record": {"type": "rule", "subject": surface, "surface": surface},
                },
            )
            active = thalamus.send_message(
                lobe,
                "recall",
                {"user_id": "alice", "query": probe, "include_only_active": True, "limit": 20},
            )
            stats = thalamus.send_message(lobe, "learning_stats", {"user_id": "alice"})
            payload = {"user_id": "alice", "user_input": probe}
            if lobe == "output":
                payload = {"user_id": "alice", "text": probe, "preserve_text": True}
            result = thalamus.send_message(lobe, msg_type, payload)
            print("TRACE", lobe, "LEARN", learned)
            print("TRACE", lobe, "ACTIVE", active)
            print("TRACE", lobe, "STATS", stats)
            print("TRACE", lobe, "RESULT", result)
            assert active.get("content", {}).get("count", 0) > 0, (lobe, learned, active, stats)
            assert result.get("learned_guidance_used") is True or result.get("content", {}).get("learned_guidance_used") is True, (lobe, result)
    finally:
        shutdown_core_systems(systems)
