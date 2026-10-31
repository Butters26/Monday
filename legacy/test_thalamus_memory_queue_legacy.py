"""Moved here Oct 30, 2026 (not run): tests for thalamus holding his words in a
backup queue when memory failed to save them.

Memory now hears each moment and saves it itself, so thalamus no longer saves
or holds anything (its contract: it decides nothing). A failed save now shows
as a failure in the live trace instead. These need the helpers in
test_notus_integration.py to run.
"""

def test_notus_store_error_continues_pipeline(tmp_path):
    systems, holder = _factory(tmp_path)
    ctl = holder["ctl"]
    assert ctl is not None
    try:
        ctl.fail_store_with_error = True
        reply = systems["thalamus"].process_user_input(
            "Remember my token ALPHA_ONE", user_id="alice"
        )
        # Store outage must not abort routing; ungrounded prompt may return silence.
        assert isinstance(reply, str)
        assert "trouble remembering" not in reply.lower()
        pending = systems["thalamus"].notus_fallback.pending_records("alice")
        assert any("ALPHA_ONE" in r["content"] for r in pending)
        # Pipeline reached later lobes
        route_tos = [r["to"] for r in systems["thalamus"].message_routes]
        assert "emotion" in route_tos
        assert "reasoning" in route_tos
        assert "language" in route_tos
        assert "output" in route_tos
    finally:
        shutdown_core_systems(systems)


def test_notus_store_exception_continues_pipeline(tmp_path):
    systems, holder = _factory(tmp_path)
    ctl = holder["ctl"]
    try:
        ctl.raise_on_store = True
        reply = systems["thalamus"].process_user_input(
            "Remember my token BETA_TWO", user_id="bob"
        )
        # Store exception must not abort routing; ungrounded prompt may return silence.
        assert isinstance(reply, str)
        assert "trouble remembering" not in reply.lower()
        pending = systems["thalamus"].notus_fallback.pending_records("bob")
        assert any("BETA_TWO" in r["content"] for r in pending)
    finally:
        shutdown_core_systems(systems)


def test_identical_messages_survive_outage_as_separate_events(tmp_path):
    """Regression: enqueue identical user message twice during outage;
    both pending as separate events; after recovery both stored once in order;
    second retry stores neither again.
    """
    systems, holder = _factory(tmp_path)
    ctl = holder["ctl"]
    thalamus = systems["thalamus"]
    try:
        fb = thalamus.notus_fallback
        ctl.fail_store_with_error = True
        thalamus.process_user_input("hello", user_id="twin")
        thalamus.process_user_input("hello", user_id="twin")

        pending = [
            r
            for r in fb.pending_records("twin")
            if r.get("role") == "user" and r.get("content") == "hello"
        ]
        assert len(pending) == 2
        assert pending[0]["event_id"] != pending[1]["event_id"]

        ctl.fail_store_with_error = False
        ctl.fail_store_after = None
        # Drain monday reply rows too if any — flush all for user.
        result = thalamus.retry_unsaved_notus_records(user_id="twin")
        assert result["failed"] == 0
        assert fb.pending_count("twin") == 0

        hello_stores = [
            c
            for c in ctl.store_calls
            if c.get("content") == "hello" and c.get("role") in {"user", "User"}
        ]
        # Two distinct hello user events stored (may include live failed attempts
        # that never persisted — count successful durable rows via retrieve).
        memories = ctl.retrieve_memories("hello", user_id="twin", limit=50)
        hello_mems = [
            m
            for m in memories
            if str(m.get("content") or "") == "hello"
            and str(m.get("role") or "").lower() in {"user", ""}
        ]
        # DirectNotus may not always stamp role; fall back to content count.
        if not hello_mems:
            hello_mems = [m for m in memories if str(m.get("content") or "") == "hello"]
        assert len(hello_mems) >= 2, f"expected both hellos durable, got {memories!r}"

        stores_before = len(ctl.store_calls)
        result2 = thalamus.retry_unsaved_notus_records(user_id="twin")
        assert result2["synced"] == 0
        assert len(ctl.store_calls) == stores_before
    finally:
        shutdown_core_systems(systems)


def test_pending_fallback_visible_when_query_succeeds(tmp_path):
    """STORE fail + QUERY success → pending merged into memory before Reasoning
    (Matthew fix #3). After recovery, no duplicate durable record.
    """
    systems, holder = _factory(tmp_path)
    ctl = holder["ctl"]
    thalamus = systems["thalamus"]

    captured: List[Dict[str, Any]] = []

    class CaptureReasoning:
        def process_message(self, message):
            content = message.get("content") if isinstance(message.get("content"), dict) else {}
            if message.get("type") == "review_reply":
                return {"status": "success", "content": {"ok": True, "reason": "makes sense"}}
            captured.append(content)
            return {
                "status": "success",
                "content": {
                    "answer": "ok-from-fallback-context",
                    "conclusion": "ok-from-fallback-context",
                },
            }

        def shutdown(self):
            pass

    def _memories_from_capture(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Locate memories whether nested under input.memory_context or flat."""
        if not isinstance(payload, dict):
            return []
        candidates = []

        def _push(node):
            if isinstance(node, dict):
                candidates.append(node)
                inner = node.get("content")
                if isinstance(inner, dict):
                    candidates.append(inner)

        for key in ("memory_context", "memory_result"):
            _push(payload.get(key))
        nested = payload.get("input")
        if isinstance(nested, dict):
            for key in ("memory_context", "memory_result"):
                _push(nested.get(key))
        for node in candidates:
            mems = node.get("memories")
            if isinstance(mems, list) and mems:
                return [m for m in mems if isinstance(m, dict)]
        return []

    thalamus.register_lobe("reasoning", CaptureReasoning())
    try:
        ctl.fail_store_with_error = True
        # First turn: store fails, fact lands in fallback queue.
        thalamus.process_user_input(
            "Remember FACT_MERGE_TEAL is my color", user_id="frank"
        )
        pending = thalamus.notus_fallback.pending_records("frank")
        assert any("FACT_MERGE_TEAL" in r["content"] for r in pending)

        # Second turn: store still failing, but QUERY works — pending must merge.
        captured.clear()
        reply = thalamus.process_user_input(
            "What color did I mention?", user_id="frank"
        )
        assert isinstance(reply, str) and reply.strip()
        assert captured, "reasoning should have been invoked"
        memories = _memories_from_capture(captured[-1])
        assert any(
            "FACT_MERGE_TEAL" in str(m.get("content") or "") for m in memories
        ), f"pending fallback missing from reasoning context: {captured[-1]!r}"
        # Must not claim durable.
        fallback_hits = [
            m
            for m in memories
            if "FACT_MERGE_TEAL" in str(m.get("content") or "")
            and m.get("source") == "notus_outage_fallback"
        ]
        assert fallback_hits
        assert all(m.get("durable") is False for m in fallback_hits)

        # Cross-user: other user's reasoning must not see frank's pending.
        captured.clear()
        thalamus.process_user_input("hello from gus", user_id="gus")
        if captured:
            other_mem = _memories_from_capture(captured[-1])
            assert all(
                "FACT_MERGE_TEAL" not in str(m.get("content") or "")
                for m in other_mem
            )

        # Recovery sync → durable once; no duplicate on second flush.
        ctl.fail_store_with_error = False
        ctl.fail_store_after = None
        result = thalamus.retry_unsaved_notus_records(user_id="frank")
        assert result["failed"] == 0
        assert thalamus.notus_fallback.pending_count("frank") == 0

        memories = ctl.retrieve_memories("FACT_MERGE_TEAL", user_id="frank", limit=50)
        teal = [
            m
            for m in memories
            if "FACT_MERGE_TEAL" in str(m.get("content") or "")
        ]
        assert len(teal) >= 1
        # Content may appear as user utterance once (plus maybe monday reply).
        user_teal = [
            m
            for m in teal
            if str(m.get("role") or "").lower() in {"user", ""}
            or "Remember FACT_MERGE_TEAL" in str(m.get("content") or "")
        ]
        assert len(user_teal) <= 2  # utterance once; tolerate role-less duplicate sniff

        stores_before = len(ctl.store_calls)
        result2 = thalamus.retry_unsaved_notus_records(user_id="frank")
        assert result2["synced"] == 0
        assert len(ctl.store_calls) == stores_before
    finally:
        shutdown_core_systems(systems)


def test_outage_queue_does_not_leak_across_users(tmp_path):
    systems, holder = _factory(tmp_path)
    ctl = holder["ctl"]
    thalamus = systems["thalamus"]
    try:
        ctl.fail_store_with_error = True
        thalamus.process_user_input("ALICE_ONLY_SECRET", user_id="alice")
        thalamus.process_user_input("BOB_ONLY_SECRET", user_id="bob")

        alice_pending = thalamus.notus_fallback.pending_records("alice")
        bob_pending = thalamus.notus_fallback.pending_records("bob")
        assert any("ALICE_ONLY_SECRET" in r["content"] for r in alice_pending)
        assert any("BOB_ONLY_SECRET" in r["content"] for r in bob_pending)
        assert all("BOB_ONLY_SECRET" not in r["content"] for r in alice_pending)
        assert all("ALICE_ONLY_SECRET" not in r["content"] for r in bob_pending)

        alice_ctx = thalamus.notus_fallback.memories_for("alice")
        bob_ctx = thalamus.notus_fallback.memories_for("bob")
        assert all("BOB_ONLY_SECRET" not in m["content"] for m in alice_ctx)
        assert all("ALICE_ONLY_SECRET" not in m["content"] for m in bob_ctx)
    finally:
        shutdown_core_systems(systems)
