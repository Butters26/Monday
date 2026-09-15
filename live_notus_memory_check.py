#!/usr/bin/env python3
"""Live behavioral check for the active Notus memory lobe.

This is intentionally not a mocked unit test. It boots the actual direct core,
stores memory through Thalamus, shuts the core down, boots a new core against
the same PostgreSQL database, and asks the new process to remember what the
old process was told.
"""

from __future__ import annotations

import uuid

from run_abin import create_core_systems, shutdown_core_systems


def content(result):
    assert result.get("status") == "success", result
    value = result.get("content", {})
    assert isinstance(value, dict), result
    return value


def main() -> int:
    user_id = f"live-memory-{uuid.uuid4()}"
    other_user = f"other-{uuid.uuid4()}"
    phrase = "My workshop air compressor is an Atlas Copco GA11 named Copper."

    systems = create_core_systems()
    thalamus = systems["thalamus"]
    try:
        health = content(thalamus.send_and_wait("notus", "health", {}))
        assert health.get("backend") == "postgresql", health
        assert health.get("ready") is True, health

        stored = content(
            thalamus.send_and_wait(
                "notus",
                "store",
                {
                    "role": "user",
                    "content": phrase,
                    "user_id": user_id,
                    "importance": 9.0,
                },
                source="live_check",
            )
        )
        memory_id = stored["id"]

        content(
            thalamus.send_and_wait(
                "notus",
                "remember_fact",
                {
                    "subject": "workshop air compressor",
                    "predicate": "model",
                    "object": "Atlas Copco GA11",
                    "value": "Copper",
                    "confidence": 0.96,
                    "user_id": user_id,
                },
                source="live_check",
            )
        )

        content(
            thalamus.send_and_wait(
                "notus",
                "store_event",
                {
                    "actor": "user",
                    "action": "named",
                    "object": "Atlas Copco GA11 compressor Copper",
                    "place": "workshop",
                    "user_id": user_id,
                    "confidence": 0.95,
                },
                source="live_check",
            )
        )

        # Give the memory graph a second related item to associate.
        content(
            thalamus.send_and_wait(
                "notus",
                "store",
                {
                    "role": "user",
                    "content": "Copper is the compressor I use in the workshop for pneumatic tools.",
                    "user_id": user_id,
                    "importance": 8.0,
                },
                source="live_check",
            )
        )

        associations = content(
            thalamus.send_and_wait(
                "notus",
                "query_associations",
                {"memory_id": memory_id, "limit": 10, "user_id": user_id},
                source="live_check",
            )
        )
        print(f"Before restart: {associations['count']} associated memories")
    finally:
        shutdown_core_systems(systems)

    # New objects, same PostgreSQL database. This is the persistence test.
    systems = create_core_systems()
    thalamus = systems["thalamus"]
    try:
        remembered = content(
            thalamus.send_and_wait(
                "notus",
                "query",
                {
                    "query": "Which compressor is in my workshop and what is it named?",
                    "user_id": user_id,
                    "limit": 10,
                },
                source="live_check",
            )
        )
        memory_text = "\n".join(
            str(item.get("content", "")) for item in remembered.get("memories", [])
        )
        assert "Atlas Copco GA11" in memory_text, remembered
        assert "Copper" in memory_text, remembered

        facts = content(
            thalamus.send_and_wait(
                "notus",
                "query_facts",
                {
                    "query": "workshop compressor model",
                    "user_id": user_id,
                    "limit": 10,
                },
                source="live_check",
            )
        )
        fact_text = "\n".join(str(item.get("text", "")) for item in facts.get("facts", []))
        assert "Atlas Copco GA11" in fact_text, facts

        episodes = content(
            thalamus.send_and_wait(
                "notus",
                "query_episodic",
                {
                    "query": "named compressor workshop",
                    "user_id": user_id,
                    "limit": 10,
                },
                source="live_check",
            )
        )
        episode_text = "\n".join(
            " ".join(
                str(item.get(key, "") or "")
                for key in ("actor", "action", "object", "place", "note")
            )
            for item in episodes.get("episodes", [])
        )
        assert "Copper" in episode_text, episodes

        isolated = content(
            thalamus.send_and_wait(
                "notus",
                "query",
                {
                    "query": "Atlas Copco GA11 Copper workshop compressor",
                    "user_id": other_user,
                    "limit": 10,
                },
                source="live_check",
            )
        )
        isolated_text = "\n".join(
            str(item.get("content", "")) for item in isolated.get("memories", [])
        )
        assert "Copper" not in isolated_text, isolated

        print("LIVE NOTUS MEMORY CHECK PASSED")
        print("Remembered conversation:", memory_text)
        print("Remembered facts:", fact_text)
        print("Remembered episode:", episode_text)
        print("User isolation: passed")
        return 0
    finally:
        shutdown_core_systems(systems)


if __name__ == "__main__":
    raise SystemExit(main())
