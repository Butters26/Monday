#!/usr/bin/env python3
"""Autonomous Thinking: her mind when nothing is being asked of it.

The brain's default mode: active at rest, quiet during focused talk. This lobe
does not write thoughts. It starts one and steers it through the lobes that do
the work:

    a start point -> what Notus associates with it -> what Reasoning makes of
    it -> how it feels (Emotion, from the feelings those memories carry)

So a thought is what those lobes found. There are no pre-written lines, and
nothing here reads or matches words.

Where a thought starts, in this order:
  1. something another lobe handed it to think about (set_focus);
  2. a memory that came up on its own while it was quiet (Notus);
  3. where the last thought led (its strongest association), so her mind
     wanders from one thing to the next;
  4. something she was asked and never answered (Executive Control);
  5. one of her recent memories she hasn't thought about lately, the most
     strongly held first.

Each thought is announced ("thought_arose") for whoever wants it: Notus
replays the memories in it (they get stronger), Emotion feels what they carry,
Meta-Awareness notices it, and Autonomous Speech can decide whether to say it.
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional

from team import announce, ask, listen


def _trace(kind: str, **data: Any) -> None:
    try:
        from trace_monitor import trace_event
        trace_event(kind, **data)
    except Exception:
        pass


def _seconds(name: str, default: float) -> float:
    try:
        return max(0.1, float(os.environ.get(name) or default))
    except ValueError:
        return default


class AutonomousThinkingLoop:
    """Starts and steers her idle thinking. Runs on its own thread."""

    def __init__(self, thalamus: Any = None) -> None:
        self.thalamus = thalamus
        self.name = "autonomous"
        self.running = False
        self.lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        # How long she has to be left alone before her mind wanders, and how
        # long between one thought and the next.
        self.idle_after = _seconds("MERCY_THINK_IDLE_SECONDS", 45.0)
        self.think_every = _seconds("MERCY_THINK_EVERY_SECONDS", 60.0)
        self.last_moment_at = time.monotonic()
        self.last_thought_at = 0.0
        self.current_user_id = "default"   # who she was last with
        self.recent_thoughts: Deque[Dict[str, Any]] = deque(maxlen=50)
        self._thought_about: Deque[Any] = deque(maxlen=30)   # memories lately thought about
        self._handed: List[Dict[str, Any]] = []     # start points other lobes handed it
        self._came_up: List[Dict[str, Any]] = []    # memories that came up on their own
        self._led_to: Optional[Dict[str, Any]] = None   # where the last thought led
        self._counter = 0

    # ------------------------------------------------------------------
    # On the team
    # ------------------------------------------------------------------

    def on_joined(self, name: str) -> None:
        self.name = name
        # A moment means someone is with her (it goes quiet); a memory Notus
        # brings up on its own is something to think about.
        listen(self.thalamus, name, "moment", "remembered")

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = message.get("type")
        content = message.get("content") if isinstance(message.get("content"), dict) else {}

        if msg_type == "moment":
            with self.lock:
                self.last_moment_at = time.monotonic()
                who = str(content.get("user_id") or "").strip()
                if who:
                    self.current_user_id = who
                # Someone is talking to her: her mind stops wandering where it was.
                self._led_to = None
            return {"status": "success", "content": {"quiet": True}}

        if msg_type == "remembered":
            if content.get("while_quiet"):
                memories = [m for m in content.get("memories") or [] if isinstance(m, dict)]
                if memories:
                    with self.lock:
                        self._came_up.append({"memory": memories[0],
                                              "user_id": str(content.get("user_id") or self.current_user_id)})
            return {"status": "success", "content": {"heard": True}}

        if msg_type == "set_focus":
            # Another lobe hands her something to think about when she is idle.
            about = str(content.get("about") or content.get("focus") or content.get("text") or "").strip()
            if not about:
                return {"status": "error", "message": "set_focus needs what to think about", "content": {}}
            with self.lock:
                self._handed.append({"about": about, "from": str(message.get("source") or "a lobe"),
                                     "user_id": str(content.get("user_id") or self.current_user_id)})
            return {"status": "success", "content": {"kept": True}}

        if msg_type == "think_now":
            # Another lobe asks her to think right now (about something, or whatever is next).
            about = str(content.get("about") or content.get("text") or "").strip()
            if about:
                with self.lock:
                    self._handed.append({"about": about, "from": str(message.get("source") or "a lobe"),
                                         "user_id": str(content.get("user_id") or self.current_user_id)})
            thought = self.think()
            return {"status": "success", "content": {"thought": thought}}

        if msg_type == "get_recent_thoughts":
            try:
                limit = int(content.get("limit") or 10)
            except (TypeError, ValueError):
                limit = 10
            with self.lock:
                thoughts = list(self.recent_thoughts)[-limit:]
            return {"status": "success", "content": {"thoughts": thoughts}}

        if msg_type == "health":
            return {"status": "success", "content": {"healthy": True, "running": self.running}}

        return {"status": "error", "message": f"Unknown message type: {msg_type}", "content": {}}

    # ------------------------------------------------------------------
    # One thought
    # ------------------------------------------------------------------

    def _start_point(self) -> Optional[Dict[str, Any]]:
        """Where the next thought starts: {about, memory, user_id, started_from}."""
        with self.lock:
            if self._handed:
                handed = self._handed.pop(0)
                return {"about": handed["about"], "memory": None, "user_id": handed["user_id"],
                        "started_from": f"{handed['from']} handed it to her"}
            while self._came_up:
                came = self._came_up.pop(0)
                memory = came["memory"]
                if memory.get("id") not in self._thought_about and str(memory.get("content") or "").strip():
                    return {"about": str(memory["content"]).strip(), "memory": memory, "user_id": came["user_id"],
                            "started_from": "a memory that came up on its own"}
            led = self._led_to
            self._led_to = None
            user_id = self.current_user_id
        if led and led.get("id") not in self._thought_about and str(led.get("content") or "").strip():
            return {"about": str(led["content"]).strip(), "memory": led, "user_id": user_id,
                    "started_from": "where her last thought led"}
        goal = ask(self.thalamus, "executive_control", "get_goal", {}, self.name)
        for owed in goal.get("owed") or []:
            about = str((owed or {}).get("about") or "").strip()
            if about and ("owed", about) not in self._thought_about:
                self._thought_about.append(("owed", about))
                return {"about": about, "memory": None, "user_id": user_id,
                        "started_from": "something she was asked and never answered"}
        recent = ask(self.thalamus, "notus", "get_recent", {"user_id": user_id, "limit": 40}, self.name)
        # (Not what she said herself: what happened and what she was told.)
        memories = [m for m in recent.get("memories") or []
                    if isinstance(m, dict) and m.get("id") not in self._thought_about
                    and m.get("role") != "mercy" and str(m.get("content") or "").strip()]
        if not memories:
            return None
        memories.sort(key=lambda m: float(m.get("strength") or 1.0), reverse=True)
        return {"about": str(memories[0]["content"]).strip(), "memory": memories[0], "user_id": user_id,
                "started_from": "a recent memory she hadn't thought about lately"}

    def think(self) -> Optional[Dict[str, Any]]:
        """Start one thought and steer it through Notus, Reasoning and Emotion."""
        started = time.perf_counter()
        start = self._start_point()
        self.last_thought_at = time.monotonic()
        if start is None:
            _trace("thought_none", reason="nothing to think from: no memories she hasn't already thought about")
            return None
        about, user_id, memory = start["about"], start["user_id"], start["memory"]
        if memory is not None and memory.get("id") is not None:
            self._thought_about.append(memory.get("id"))

        # What Notus associates with it.
        found = ask(self.thalamus, "notus", "find_similar", {"text": about, "user_id": user_id, "limit": 6}, self.name)
        associated = [m for m in found.get("memories") or []
                      if isinstance(m, dict) and (memory is None or m.get("id") != memory.get("id"))]

        # What Reasoning makes of it.
        worked = ask(self.thalamus, "reasoning", "work_out", {"question": about, "user_id": user_id}, self.name)

        self._counter += 1
        thought = {
            "id": self._counter,
            "at": time.time(),
            "user_id": user_id,
            "started_from": start["started_from"],
            "about": about,
            "memory": memory,
            "with": associated,
            "knows": list(worked.get("knows") or []),
            "follows": list(worked.get("conclusions") or []),
            "explains": list(worked.get("explanations") or []),
            "problem": worked.get("problem"),
            "unsure": worked.get("unsure"),
        }
        with self.lock:
            self.recent_thoughts.append(thought)
            # Her mind wanders on to what this thought is most strongly tied to.
            # (On to something that happened or she was told, not to her own words about it.)
            onward = [m for m in associated if m.get("id") not in self._thought_about
                      and m.get("role") != "mercy"]
            onward.sort(key=lambda m: float(m.get("strength") or 1.0), reverse=True)
            self._led_to = onward[0] if onward else None

        # For whoever wants it: Notus replays it, Emotion feels what the memories
        # carry, Meta-Awareness notices it, Autonomous Speech may say it.
        announce(self.thalamus, "thought_arose", {
            **thought,
            "memories": ([memory] if memory else []) + associated,
        }, self.name)
        _trace("thought", started_from=thought["started_from"], about=about[:160],
               with_memories=[str(m.get("content") or "")[:80] for m in associated],
               knows=[str(k)[:80] for k in thought["knows"]],
               follows=[self._said_plainly(c) for c in thought["follows"]],
               problem=thought["problem"], unsure=thought["unsure"],
               leads_to=str((self._led_to or {}).get("content") or "")[:80] or None,
               ms=round((time.perf_counter() - started) * 1000, 1))
        return thought

    @staticmethod
    def _said_plainly(conclusion: Any) -> str:
        if isinstance(conclusion, dict):
            parts = [str(conclusion.get(k) or "") for k in ("subject", "predicate", "object")]
            return " ".join(p for p in parts if p)[:120]
        return str(conclusion)[:120]

    # ------------------------------------------------------------------
    # Her own thread: thinks when she is idle
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        while self.running:
            time.sleep(min(1.0, self.think_every, self.idle_after))
            if not self.running:
                break
            now = time.monotonic()
            with self.lock:
                left_alone = now - self.last_moment_at
            if left_alone < self.idle_after or now - self.last_thought_at < self.think_every:
                continue
            try:
                self.think()
            except Exception as error:
                import traceback
                _trace("lobe_crashed", lobe=self.name, msg_type="idle thinking",
                       error=f"{type(error).__name__}: {error}",
                       traceback="".join(traceback.format_exception(error))[-3000:])

    def start_background(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self.running = True
        self._thread = threading.Thread(target=self._loop, name="autonomous-thinking", daemon=True)
        self._thread.start()

    def shutdown(self) -> None:
        self.running = False


__all__ = ["AutonomousThinkingLoop"]
