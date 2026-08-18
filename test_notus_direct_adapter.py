"""Direct unit tests for notus.py internals.

These tests bypass Thalamus entirely and exercise the classes in notus.py
directly, so that internal bugs are caught before they ever surface through
the high-level pipeline.

Run with:
    python -m unittest -q test_notus_direct_adapter.py
"""

import json
import os
import sys
import types
import unittest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Stub thalamus so notus.py can be imported in isolation
# ---------------------------------------------------------------------------
_mock_thalamus = MagicMock()
_mock_thalamus.register_lobe = MagicMock(return_value={"status": "success"})
_mock_thalamus.send_message = MagicMock(return_value={})
_thalamus_module = types.ModuleType("thalamus")
_thalamus_module.get_thalamus = lambda: _mock_thalamus
sys.modules.setdefault("thalamus", _thalamus_module)

import notus  # noqa: E402  (must come after stub)
from notus import (
    AdvancedEmbeddingEngine,
    DirectNotusProcess,
    EMBEDDING_DIM,
    MemoryType,
    NotusProcess,
    SuperhumanConfig,
    SuperhumanMemorySystem,
)


# ---------------------------------------------------------------------------
# Helper: in-memory SuperhumanMemorySystem (SQLite, no seed threads)
# ---------------------------------------------------------------------------
def _make_memory_system(tmp_path: str) -> SuperhumanMemorySystem:
    cfg = SuperhumanConfig(
        snapshot_path=os.path.join(tmp_path, "snap.json"),
        autosave_enabled=False,
    )
    db = os.path.join(tmp_path, "test_memory.db")
    sys = SuperhumanMemorySystem(config=cfg, storage_path=db)
    # Wait for background seed to finish (max 3 s) so tests are deterministic
    import time
    deadline = time.time() + 3
    while time.time() < deadline:
        try:
            with notus.DB_LOCK:
                sys._db_connection.execute("SELECT COUNT(*) FROM brain_facts")
            break
        except Exception:
            time.sleep(0.05)
    return sys


# ---------------------------------------------------------------------------
# AdvancedEmbeddingEngine
# ---------------------------------------------------------------------------
class TestAdvancedEmbeddingEngine(unittest.TestCase):

    def setUp(self):
        self.cfg = SuperhumanConfig()
        self.engine = AdvancedEmbeddingEngine(self.cfg)

    def test_empty_string_returns_zero_vector(self):
        v = self.engine.get_embedding("")
        self.assertEqual(v.shape, (EMBEDDING_DIM,))
        self.assertEqual(v.sum(), 0.0)

    def test_whitespace_only_returns_zero_vector(self):
        v = self.engine.get_embedding("   \t\n  ")
        self.assertEqual(v.shape, (EMBEDDING_DIM,))
        self.assertEqual(v.sum(), 0.0)

    def test_non_empty_text_returns_correct_shape(self):
        v = self.engine.get_embedding("hello world")
        self.assertEqual(v.shape, (EMBEDDING_DIM,))

    def test_cache_hit_returns_same_object(self):
        v1 = self.engine.get_embedding("cache test")
        v2 = self.engine.get_embedding("cache test")
        self.assertIs(v1, v2, "Second call should return the cached array")

    def test_different_texts_produce_different_vectors(self):
        import numpy as np
        v1 = self.engine.get_embedding("apple")
        v2 = self.engine.get_embedding("zeppelin")
        self.assertFalse(np.array_equal(v1, v2))

    def test_similarity_identical_texts(self):
        sim = self.engine.calculate_similarity("hello", "hello")
        self.assertAlmostEqual(sim, 1.0, places=5)

    def test_similarity_empty_texts_returns_zero(self):
        sim = self.engine.calculate_similarity("", "")
        self.assertEqual(sim, 0.0)

    def test_similarity_bounded_zero_to_one(self):
        sim = self.engine.calculate_similarity("dog", "cat")
        self.assertGreaterEqual(sim, 0.0)
        self.assertLessEqual(sim, 1.0)

    def test_normalize_dimensions_pads_short_vector(self):
        import numpy as np
        short = np.ones(10)
        result = self.engine._normalize_dimensions(short)
        self.assertEqual(result.shape, (EMBEDDING_DIM,))

    def test_normalize_dimensions_truncates_long_vector(self):
        import numpy as np
        long_vec = np.ones(EMBEDDING_DIM + 100)
        result = self.engine._normalize_dimensions(long_vec)
        self.assertEqual(result.shape, (EMBEDDING_DIM,))

    def test_normalize_dimensions_empty_returns_zeros(self):
        import numpy as np
        result = self.engine._normalize_dimensions(np.array([]))
        self.assertEqual(result.shape, (EMBEDDING_DIM,))
        self.assertEqual(result.sum(), 0.0)

    def test_basic_embedding_stable_across_calls(self):
        import numpy as np
        v1 = self.engine._get_basic_embedding("stable test")
        v2 = self.engine._get_basic_embedding("stable test")
        self.assertTrue(np.array_equal(v1, v2))


# ---------------------------------------------------------------------------
# SuperhumanMemorySystem — store / retrieve
# ---------------------------------------------------------------------------
class TestSuperhumanMemoryStore(unittest.TestCase):

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self.mem = _make_memory_system(self.tmp)

    def tearDown(self):
        try:
            self.mem._db_connection.close()
        except Exception:
            pass

    def test_store_memory_returns_id_string(self):
        mid = self.mem.store_memory("user", "hello world")
        self.assertIsInstance(mid, str)
        self.assertTrue(len(mid) > 0)

    def test_store_memory_empty_content_returns_none_or_id(self):
        # Should not crash; may return None or an id depending on DB backend
        try:
            result = self.mem.store_memory("user", "")
        except Exception as e:
            self.fail(f"store_memory raised unexpectedly: {e}")

    def test_retrieve_memories_returns_list(self):
        self.mem.store_memory("user", "the sky is blue")
        results = self.mem.retrieve_memories("sky")
        self.assertIsInstance(results, list)

    def test_retrieve_memories_user_isolation(self):
        self.mem.store_memory("user", "secret for alice", user_id="alice")
        alice_results = self.mem.retrieve_memories("secret", user_id="alice")
        bob_results = self.mem.retrieve_memories("secret", user_id="bob")
        alice_contents = [m["content"] for m in alice_results]
        bob_contents = [m["content"] for m in bob_results]
        self.assertIn("secret for alice", alice_contents)
        self.assertNotIn("secret for alice", bob_contents)

    def test_retrieve_memories_limit_respected(self):
        for i in range(20):
            self.mem.store_memory("user", f"memory number {i}")
        results = self.mem.retrieve_memories("memory", limit=5)
        self.assertLessEqual(len(results), 5)

    def test_retrieve_memories_empty_db_returns_empty_list(self):
        import tempfile
        tmp2 = tempfile.mkdtemp()
        fresh = _make_memory_system(tmp2)
        results = fresh.retrieve_memories("anything")
        self.assertIsInstance(results, list)
        fresh._db_connection.close()

    def test_store_memory_result_has_required_keys(self):
        self.mem.store_memory("user", "test content for keys")
        results = self.mem.retrieve_memories("test content")
        if results:
            m = results[0]
            for key in ("content", "role", "user_id", "memory_type"):
                self.assertIn(key, m, f"Key '{key}' missing from memory dict")


# ---------------------------------------------------------------------------
# SuperhumanMemorySystem — brain facts
# ---------------------------------------------------------------------------
class TestBrainFacts(unittest.TestCase):

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self.mem = _make_memory_system(self.tmp)

    def tearDown(self):
        try:
            self.mem._db_connection.close()
        except Exception:
            pass

    def test_remember_fact_returns_id(self):
        fid = self.mem.remember_fact("sky", "is", "blue")
        self.assertIsInstance(fid, str)

    def test_remember_fact_empty_fields_returns_none(self):
        self.assertIsNone(self.mem.remember_fact("", "is", "blue"))
        self.assertIsNone(self.mem.remember_fact("sky", "", "blue"))
        self.assertIsNone(self.mem.remember_fact("sky", "is", ""))

    def test_remember_fact_idempotent_upsert(self):
        fid1 = self.mem.remember_fact("sun", "is", "hot")
        fid2 = self.mem.remember_fact("sun", "is", "hot")
        self.assertEqual(fid1, fid2)

    def test_remember_fact_confidence_reinforcement(self):
        fid = self.mem.remember_fact("earth", "orbits", "sun", confidence=0.5)
        # Reinforce same fact
        self.mem.remember_fact("earth", "orbits", "sun", confidence=0.5)
        with notus.DB_LOCK:
            row = self.mem._db_connection.execute(
                "SELECT confidence FROM brain_facts WHERE id = ?", (fid,)
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertGreater(row[0], 0.5)

    def test_recall_facts_returns_list(self):
        self.mem.remember_fact("water", "is", "wet")
        facts = self.mem.recall_facts("water")
        self.assertIsInstance(facts, list)

    def test_recall_facts_user_isolation(self):
        self.mem.remember_fact("color", "is", "red", user_id="alice")
        alice_facts = self.mem.recall_facts("color", user_id="alice")
        bob_facts = self.mem.recall_facts("color", user_id="bob")
        alice_texts = [f["text"] for f in alice_facts]
        bob_texts = [f["text"] for f in bob_facts]
        self.assertTrue(any("color" in t for t in alice_texts))
        self.assertFalse(any("color" in t for t in bob_texts))

    def test_learn_facts_from_text_x_is_y(self):
        ids = self.mem.learn_facts_from_text("Python is a programming language")
        self.assertIsInstance(ids, list)
        # At least one fact should be extracted
        self.assertGreater(len(ids), 0)

    def test_learn_facts_from_text_empty_returns_empty(self):
        ids = self.mem.learn_facts_from_text("")
        self.assertEqual(ids, [])

    def test_learn_facts_from_text_preference(self):
        ids = self.mem.learn_facts_from_text("I love pizza")
        self.assertGreater(len(ids), 0)

    def test_learn_facts_from_text_goal(self):
        ids = self.mem.learn_facts_from_text("I want to write a novel")
        self.assertGreater(len(ids), 0)


# ---------------------------------------------------------------------------
# SuperhumanMemorySystem — episodic events
# ---------------------------------------------------------------------------
class TestEpisodicMemory(unittest.TestCase):

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self.mem = _make_memory_system(self.tmp)

    def tearDown(self):
        try:
            self.mem._db_connection.close()
        except Exception:
            pass

    def test_store_event_returns_id(self):
        eid = self.mem.store_event("user", "walked", object="dog")
        self.assertIsInstance(eid, str)

    def test_recall_episodes_returns_list(self):
        self.mem.store_event("user", "walked", object="dog")
        episodes = self.mem.recall_episodes("walked")
        self.assertIsInstance(episodes, list)

    def test_recall_episodes_result_has_required_keys(self):
        self.mem.store_event("alice", "ran", object="race", user_id="alice")
        episodes = self.mem.recall_episodes("ran", user_id="alice")
        if episodes:
            ep = episodes[0]
            for key in ("actor", "action", "timestamp"):
                self.assertIn(key, ep)

    def test_extract_events_from_text(self):
        ids = self.mem._extract_events_from_text("I walked to the store yesterday")
        self.assertIsInstance(ids, list)


# ---------------------------------------------------------------------------
# SuperhumanMemorySystem — memory associations
# ---------------------------------------------------------------------------
class TestMemoryAssociations(unittest.TestCase):

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self.mem = _make_memory_system(self.tmp)

    def tearDown(self):
        try:
            self.mem._db_connection.close()
        except Exception:
            pass

    def test_get_associated_memories_returns_list(self):
        mid = self.mem.store_memory("user", "cats are fluffy animals")
        self.mem.store_memory("user", "dogs are fluffy animals")
        results = self.mem.get_associated_memories(mid)
        self.assertIsInstance(results, list)

    def test_get_associated_memories_unknown_id_returns_empty(self):
        results = self.mem.get_associated_memories("nonexistent-id-12345")
        self.assertEqual(results, [])


# ---------------------------------------------------------------------------
# _CompatCursor SQL translation (SQLite only)
# ---------------------------------------------------------------------------
class TestCompatCursor(unittest.TestCase):
    """Verify the %s→? and ON CONFLICT translation layer works correctly."""

    def setUp(self):
        import tempfile, sqlite3
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "CREATE TABLE t (a TEXT PRIMARY KEY, b TEXT)"
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def _compat(self):
        """Return a _CompatCursor wrapping the in-memory connection."""
        raw = self.conn.cursor()
        # Replicate the _CompatCursor factory from notus._cursor()
        # by constructing a throwaway SQLite-backed SuperhumanMemorySystem
        # and borrowing its cursor factory.
        import tempfile
        tmp = tempfile.mkdtemp()
        cfg = SuperhumanConfig(autosave_enabled=False,
                               snapshot_path=os.path.join(tmp, "snap.json"))
        mem = SuperhumanMemorySystem(config=cfg,
                                     storage_path=os.path.join(tmp, "c.db"))
        mem._db_sqlite = True
        mem._db_connection = self.conn
        cursor = mem._cursor()
        return cursor, mem

    def test_percent_s_to_question_mark(self):
        c, mem = self._compat()
        self.conn.execute("CREATE TABLE IF NOT EXISTS pct (v TEXT)")
        c.execute("INSERT INTO pct (v) VALUES (%s)", ("hello",))
        self.conn.commit()
        row = self.conn.execute("SELECT v FROM pct").fetchone()
        self.assertEqual(row[0], "hello")
        mem._db_connection.close()

    def test_on_conflict_translated(self):
        c, mem = self._compat()
        # Insert, then try ON CONFLICT upsert — should not raise
        self.conn.execute("CREATE TABLE IF NOT EXISTS upsert (a TEXT PRIMARY KEY, b TEXT)")
        c.execute("INSERT INTO upsert (a, b) VALUES (%s, %s)", ("k", "v1"))
        self.conn.commit()
        c.execute(
            "INSERT INTO upsert (a, b) VALUES (%s, %s) "
            "ON CONFLICT (a) DO UPDATE SET b = EXCLUDED.b",
            ("k", "v2"),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT b FROM upsert WHERE a = 'k'").fetchone()
        self.assertEqual(row[0], "v2")
        mem._db_connection.close()

    def test_least_to_min(self):
        c, mem = self._compat()
        self.conn.execute("CREATE TABLE IF NOT EXISTS nums (v REAL)")
        self.conn.execute("INSERT INTO nums VALUES (0.5)")
        self.conn.commit()
        c.execute("UPDATE nums SET v = LEAST(v, %s)", (0.8,))
        self.conn.commit()
        row = self.conn.execute("SELECT v FROM nums").fetchone()
        self.assertAlmostEqual(row[0], 0.5)
        mem._db_connection.close()


# ---------------------------------------------------------------------------
# DirectNotusProcess
# ---------------------------------------------------------------------------
class TestDirectNotusProcess(unittest.TestCase):

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self.notus = notus.DirectNotusProcess(
            storage_path=os.path.join(self.tmp, "direct.sqlite3"),
            thalamus=_mock_thalamus,
        )

    def tearDown(self):
        try:
            self.notus.shutdown()
        except Exception:
            pass

    # --- health ---
    def test_health_returns_success(self):
        r = self.notus.process_message({"type": "health"})
        self.assertEqual(r["status"], "success")
        self.assertTrue(r["content"]["healthy"])
        self.assertEqual(r["content"]["memory_status"], "ready")

    # --- store ---
    def test_store_valid_memory(self):
        r = self.notus.process_message({
            "type": "store",
            "content": {"role": "user", "content": "hello notus", "user_id": "default"},
        })
        self.assertEqual(r["status"], "success")

    def test_store_empty_content_returns_error(self):
        r = self.notus.process_message({
            "type": "store",
            "content": {"role": "user", "content": "", "user_id": "default"},
        })
        self.assertEqual(r["status"], "error")

    def test_store_missing_content_returns_error(self):
        r = self.notus.process_message({
            "type": "store",
            "content": {"role": "user", "user_id": "default"},
        })
        self.assertEqual(r["status"], "error")

    # --- query ---
    def test_query_returns_success(self):
        self.notus._store({"role": "user", "content": "the cat sat on the mat", "user_id": "default"})
        r = self.notus.process_message({"type": "query", "content": {"query": "cat", "user_id": "default"}})
        self.assertEqual(r["status"], "success")
        self.assertIn("results", r["content"])

    def test_query_semantic_alias(self):
        r = self.notus.process_message({"type": "query_semantic", "content": {"text": "cat", "user_id": "default"}})
        self.assertEqual(r["status"], "success")

    # --- query_context ---
    def test_query_context_returns_semantic_episodic_facts(self):
        r = self.notus.process_message({
            "type": "query_context",
            "content": {"text": "anything", "user_id": "default"},
        })
        self.assertEqual(r["status"], "success")
        c = r["content"]
        self.assertIn("semantic", c)
        self.assertIn("episodic", c)
        self.assertIn("facts", c)

    # --- stub types ---
    def test_query_episodic_returns_empty_list(self):
        r = self.notus.process_message({"type": "query_episodic", "content": {}})
        self.assertEqual(r["status"], "success")
        self.assertEqual(r["content"]["events"], [])

    def test_query_facts_returns_empty_list(self):
        r = self.notus.process_message({"type": "query_facts", "content": {}})
        self.assertEqual(r["status"], "success")
        self.assertEqual(r["content"]["facts"], [])

    def test_query_patterns_returns_empty_list(self):
        r = self.notus.process_message({"type": "query_patterns", "content": {}})
        self.assertEqual(r["status"], "success")
        self.assertEqual(r["content"]["patterns"], [])

    # --- unknown type ---
    def test_unknown_type_returns_error(self):
        r = self.notus.process_message({"type": "does_not_exist"})
        self.assertEqual(r["status"], "error")

    # --- retrieve_memories ---
    def test_retrieve_memories_empty_db(self):
        results = self.notus.retrieve_memories("anything")
        self.assertIsInstance(results, list)
        self.assertEqual(results, [])

    def test_retrieve_memories_user_isolation(self):
        self.notus._store({"role": "user", "content": "alice secret", "user_id": "alice"})
        alice = self.notus.retrieve_memories("alice secret", user_id="alice")
        bob = self.notus.retrieve_memories("alice secret", user_id="bob")
        self.assertTrue(any("alice secret" in m["content"] for m in alice))
        self.assertFalse(any("alice secret" in m["content"] for m in bob))

    def test_retrieve_memories_result_keys(self):
        self.notus._store({"role": "user", "content": "keys test", "user_id": "default"})
        results = self.notus.retrieve_memories("keys test", user_id="default")
        self.assertTrue(len(results) > 0)
        m = results[0]
        for key in ("role", "content", "user_id", "memory_type", "timestamp"):
            self.assertIn(key, m)

    # --- shutdown idempotency ---
    def test_shutdown_twice_does_not_raise(self):
        try:
            self.notus.shutdown()
            self.notus.shutdown()
        except Exception as e:
            self.fail(f"Double shutdown raised: {e}")


# ---------------------------------------------------------------------------
# NotusProcess — shutdown safety before start()
# ---------------------------------------------------------------------------
class TestNotusProcessShutdown(unittest.TestCase):

    def test_shutdown_before_start_does_not_crash(self):
        """shutdown() must not crash if start() was never called."""
        p = notus.NotusProcess()
        p.running = False  # prevent any loops
        try:
            p.shutdown()
        except AttributeError as e:
            self.fail(f"shutdown() crashed before start(): {e}")


# ---------------------------------------------------------------------------
# observe() end-to-end through SuperhumanMemorySystem
# ---------------------------------------------------------------------------
class TestObserve(unittest.TestCase):

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self.mem = _make_memory_system(self.tmp)

    def tearDown(self):
        try:
            self.mem._db_connection.close()
        except Exception:
            pass

    def test_observe_stores_user_message(self):
        self.mem.observe("I enjoy hiking in the mountains")
        results = self.mem.retrieve_memories("hiking")
        contents = [m["content"] for m in results]
        self.assertIn("I enjoy hiking in the mountains", contents)

    def test_observe_returns_required_keys(self):
        r = self.mem.observe("hello monday")
        for key in ("facts", "episodes", "working_set", "prompt_chunks", "stored_events"):
            self.assertIn(key, r, f"Key '{key}' missing from observe() result")

    def test_observe_stores_ai_response_too(self):
        self.mem.observe("how are you?", ai_text="I am doing well today")
        results = self.mem.retrieve_memories("doing well")
        contents = [m["content"] for m in results]
        self.assertIn("I am doing well today", contents)


# ---------------------------------------------------------------------------
# chunk_for_ui / _enforce_final_length
# ---------------------------------------------------------------------------
class TestPromptUtils(unittest.TestCase):

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self.mem = _make_memory_system(self.tmp)

    def tearDown(self):
        try:
            self.mem._db_connection.close()
        except Exception:
            pass

    def test_chunk_short_text_returns_single_chunk(self):
        chunks = self.mem.chunk_for_ui("hello", chunk_size=100)
        self.assertEqual(chunks, ["hello"])

    def test_chunk_long_text_produces_multiple_chunks(self):
        text = "word " * 500
        chunks = self.mem.chunk_for_ui(text, chunk_size=100)
        self.assertGreater(len(chunks), 1)

    def test_chunks_reassemble_losslessly(self):
        text = "line one\nline two\nline three\n" * 50
        chunks = self.mem.chunk_for_ui(text, chunk_size=80)
        reassembled = "".join(chunks)
        self.assertEqual(reassembled, text)

    def test_enforce_final_length_under_limit_unchanged(self):
        short = "short prompt"
        result = self.mem._enforce_final_length(short)
        self.assertEqual(result, short)

    def test_enforce_final_length_truncates_over_limit(self):
        long_prompt = "x" * 10000
        self.mem.config.final_prompt_max_chars = 500
        result = self.mem._enforce_final_length(long_prompt)
        self.assertLessEqual(len(result), 500)


# ---------------------------------------------------------------------------
# SuperhumanConfig env overrides
# ---------------------------------------------------------------------------
class TestConfigEnvOverride(unittest.TestCase):

    def test_env_override_max_context_chars(self):
        import tempfile
        os.environ["NOTUS_MAX_CONTEXT_CHARS"] = "999"
        try:
            tmp = tempfile.mkdtemp()
            cfg = SuperhumanConfig(autosave_enabled=False,
                                   snapshot_path=os.path.join(tmp, "snap.json"),
                                   allow_env_override=True)
            mem = SuperhumanMemorySystem(config=cfg,
                                         storage_path=os.path.join(tmp, "env.db"))
            # Give the init a moment to apply env overrides
            import time; time.sleep(0.05)
            self.assertEqual(mem.config.max_context_chars, 999)
            mem._db_connection.close()
        finally:
            del os.environ["NOTUS_MAX_CONTEXT_CHARS"]

    def test_env_override_clamped_to_minimum(self):
        import tempfile
        os.environ["NOTUS_MAX_CONTEXT_CHARS"] = "1"  # below 500 minimum
        try:
            tmp = tempfile.mkdtemp()
            cfg = SuperhumanConfig(autosave_enabled=False,
                                   snapshot_path=os.path.join(tmp, "snap.json"),
                                   allow_env_override=True)
            mem = SuperhumanMemorySystem(config=cfg,
                                         storage_path=os.path.join(tmp, "env2.db"))
            import time; time.sleep(0.05)
            self.assertGreaterEqual(mem.config.max_context_chars, 500)
            mem._db_connection.close()
        finally:
            del os.environ["NOTUS_MAX_CONTEXT_CHARS"]


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    unittest.main()
