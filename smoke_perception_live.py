#!/usr/bin/env python3
"""Pass/fail smoke: real text perception on the live path.

Proves:
  (1) create_core_systems registers perception
  (2) process_user_input still works (no crash)
  (3) perception produces concepts/entities for a sample line
  (4) core start does not print fake microphone/webcam success
  (5) get_status claims text only (audio/vision false)

No test_*.py. No cloud. No percents.
Run: python3 smoke_perception_live.py
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
import traceback
import uuid
from contextlib import redirect_stdout
from pathlib import Path
from typing import List, Tuple

os.environ.setdefault("NOTUS_POSTGRES_DB", "notus_memory")
os.environ.setdefault("NOTUS_POSTGRES_USER", os.getenv("USER", "box"))
os.environ.setdefault("NOTUS_POSTGRES_HOST", "localhost")
os.environ.setdefault(
    "NOTUS_POSTGRES_PASSWORD", os.getenv("NOTUS_POSTGRES_PASSWORD", "box")
)

from run_abin import create_core_systems, shutdown_core_systems


FAKE_SUCCESS = (
    "microphone initialized",
    "webcam initialized",
    "autonomous hearing active",
    "autonomous vision active",
    "speech-to-text engine initialized",
)


def main() -> int:
    runtime = Path(tempfile.mkdtemp(prefix="monday-perception-smoke-"))
    results: List[Tuple[str, str, str]] = []

    def mark(case: str, ok: bool, detail: str = "") -> None:
        results.append((case, "PASS" if ok else "FAIL", detail))
        print(f"[{'PASS' if ok else 'FAIL'}] {case}" + (f" — {detail}" if detail else ""))

    print("=== smoke_perception_live ===")
    print(f"runtime: {runtime}")

    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            systems = create_core_systems(runtime_directory=str(runtime))
        boot_out = buf.getvalue().lower()
    except Exception as exc:
        print(buf.getvalue())
        mark("create_core_systems", False, f"CRASH: {exc}")
        for case, status, detail in results:
            print(f"{status}: {case}" + (f" — {detail}" if detail else ""))
        return 1

    # Replay boot lines for the human running smoke (redirect captured them).
    captured = buf.getvalue()
    if captured.strip():
        print(captured, end="" if captured.endswith("\n") else "\n")

    mark("create_core_systems", True)

    th = systems["thalamus"]
    fake_hits = [phrase for phrase in FAKE_SUCCESS if phrase in boot_out]
    mark(
        "no fake mic/webcam success on core start",
        not fake_hits,
        ("found: " + ", ".join(fake_hits)) if fake_hits else "clean",
    )

    with th.lobe_handlers_lock:
        registered = "perception" in th.lobe_handlers
    mark("perception registered", registered)

    status = th.send_and_wait("perception", "get_status", {})
    body = status.get("content") if isinstance(status.get("content"), dict) else {}
    text_ok = bool(body.get("text_input") or status.get("text_input"))
    audio_off = body.get("stt_available", status.get("stt_available", True)) is False
    vision_off = body.get("vision_available", status.get("vision_available", True)) is False
    mark(
        "status text-only",
        status.get("status") == "success" and text_ok and audio_off and vision_off,
        f"status={status.get('status')} text={text_ok} stt={not audio_off} vision={not vision_off}",
    )

    sample = "My dog Pixel loves Denver parks."
    perc = th.send_and_wait("perception", "process_text", {"text": sample})
    content = perc.get("content") if isinstance(perc.get("content"), dict) else {}
    concepts = content.get("concepts") if isinstance(content.get("concepts"), dict) else {}
    words = concepts.get("words") or content.get("words") or []
    entities = concepts.get("entities") or content.get("entities") or []
    normalized = content.get("text") or content.get("normalized_text") or ""
    has_concepts = bool(words) or bool(entities)
    entity_hit = any("pixel" in str(e).lower() for e in entities) or "pixel" in " ".join(
        str(w).lower() for w in words
    )
    mark(
        "perception concepts for sample",
        perc.get("status") == "success" and has_concepts and entity_hit and bool(normalized),
        f"words={words[:8]} entities={entities} text={normalized!r}",
    )

    # Disabled senses must refuse, not pretend.
    audio = th.send_and_wait("perception", "listen_audio", {})
    vision = th.send_and_wait("perception", "capture_visual", {})
    mark(
        "audio/vision honestly disabled",
        audio.get("status") == "error" and vision.get("status") == "error",
        f"audio={audio.get('status')} vision={vision.get('status')}",
    )

    uid = f"perc_smoke_{uuid.uuid4().hex[:10]}"
    try:
        reply = th.process_user_input("Hello Monday, my name is Matthew.", user_id=uid) or ""
        crashed = reply.startswith("CRASH:")
        mark(
            "process_user_input still works",
            (not crashed) and isinstance(reply, str) and bool(reply.strip()),
            (reply[:120] + "…") if len(reply) > 120 else reply,
        )
    except Exception as exc:
        mark("process_user_input still works", False, f"CRASH: {exc}\n{traceback.format_exc()}")

    # Whitespace normalization through the live path.
    try:
        reply2 = th.process_user_input("  hi   there  ", user_id=uid) or ""
        mark(
            "normalized text still chats",
            isinstance(reply2, str) and bool(reply2.strip()) and not reply2.startswith("CRASH:"),
            (reply2[:80] + "…") if len(reply2) > 80 else reply2,
        )
    except Exception as exc:
        mark("normalized text still chats", False, str(exc))

    try:
        shutdown_core_systems(systems)
        mark("shutdown", True)
    except Exception as exc:
        mark("shutdown", False, str(exc))

    print("---")
    failed = [r for r in results if r[1] == "FAIL"]
    if failed:
        print("FAIL")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
