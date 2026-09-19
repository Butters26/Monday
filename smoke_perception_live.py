#!/usr/bin/env python3
"""Pass/fail smoke: perception senses on the live path.

Proves:
  (1) create_core_systems registers perception
  (2) perceive_text works with non-empty concepts
  (3) get_status: text online; audio/vision true only if devices really work
  (4) process_user_input chat path still works
  (5) core start does not print fake mic/webcam success when devices missing

No test_*.py. No cloud. No percents. PASS/FAIL only.
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
    "webcam active",
    "autonomous hearing active",
    "autonomous vision active",
    "speech-to-text engine initialized",
)


def _device_really_works(kind: str) -> bool:
    """Independent check: would audio/vision actually open in this environment?"""
    if kind == "audio":
        try:
            import speech_recognition as sr  # type: ignore
        except ImportError:
            return False
        try:
            with sr.Microphone() as source:
                sr.Recognizer().adjust_for_ambient_noise(source, duration=0.05)
            return True
        except Exception:
            return False
    if kind == "vision":
        try:
            import cv2  # type: ignore
        except ImportError:
            return False
        cap = None
        try:
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                return False
            ret, frame = cap.read()
            return bool(ret and frame is not None)
        except Exception:
            return False
        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass
    return False


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

    captured = buf.getvalue()
    if captured.strip():
        print(captured, end="" if captured.endswith("\n") else "\n")

    mark("create_core_systems", True)

    th = systems["thalamus"]
    perc_lobe = systems["perception"]

    # Fake success phrases only OK if the matching device really works.
    audio_real = _device_really_works("audio")
    vision_real = _device_really_works("vision")
    fake_hits = []
    for phrase in FAKE_SUCCESS:
        if phrase not in boot_out:
            continue
        if "mic" in phrase or "hearing" in phrase or "speech-to-text" in phrase:
            if not audio_real:
                fake_hits.append(phrase)
        elif "webcam" in phrase or "vision" in phrase:
            if not vision_real:
                fake_hits.append(phrase)
        else:
            fake_hits.append(phrase)
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
    senses = body.get("senses_online") if isinstance(body.get("senses_online"), dict) else {}
    text_online = bool(
        senses.get("text")
        or body.get("text")
        or body.get("text_input")
        or status.get("text_input")
    )
    audio_claim = bool(
        senses.get("audio")
        if "audio" in senses
        else body.get("audio", body.get("stt_available", False))
    )
    vision_claim = bool(
        senses.get("vision")
        if "vision" in senses
        else body.get("vision", body.get("vision_available", False))
    )
    # Honest: claimed online iff device really works in this environment.
    audio_honest = audio_claim == audio_real
    vision_honest = vision_claim == vision_real
    # Also match lobe's own probe (should agree with independent check).
    lobe_audio = bool(getattr(perc_lobe, "stt_available", False))
    lobe_vision = bool(getattr(perc_lobe, "vision_available", False))
    mark(
        "get_status text online; audio/vision honest",
        status.get("status") == "success"
        and text_online
        and audio_honest
        and vision_honest
        and audio_claim == lobe_audio
        and vision_claim == lobe_vision,
        (
            f"text={text_online} audio_claim={audio_claim}/real={audio_real} "
            f"vision_claim={vision_claim}/real={vision_real}"
        ),
    )

    sample = "My dog Pixel loves Denver parks."
    perc = th.send_and_wait("perception", "perceive_text", {"text": sample})
    content = perc.get("content") if isinstance(perc.get("content"), dict) else {}
    concepts = content.get("concepts")
    if isinstance(concepts, dict):
        concept_items = concepts.get("words") or []
        entities = concepts.get("entities") or content.get("entities") or []
    else:
        concept_items = list(concepts or [])
        entities = list(content.get("entities") or [])
    modality = content.get("modality")
    has_shape = all(
        k in content
        for k in ("modality", "concepts", "entities", "novelty_flags", "confidence", "raw_meta")
    )
    normalized = content.get("text") or ""
    has_concepts = bool(concept_items)
    entity_hit = any("pixel" in str(e).lower() for e in entities) or any(
        "pixel" in str(w).lower() for w in concept_items
    )
    mark(
        "perceive_text concepts non-empty",
        perc.get("status") == "success"
        and has_shape
        and modality == "text"
        and has_concepts
        and entity_hit
        and bool(normalized),
        f"modality={modality} concepts={concept_items[:8]} entities={entities} text={normalized!r}",
    )

    # Disabled senses must refuse honestly when offline.
    if not audio_real:
        audio = th.send_and_wait("perception", "perceive_audio", {})
        mark(
            "perceive_audio honest when offline",
            audio.get("status") == "error",
            f"status={audio.get('status')} msg={audio.get('message', '')[:80]}",
        )
    else:
        mark("perceive_audio honest when offline", True, "audio really online — skip offline check")

    if not vision_real:
        vision = th.send_and_wait("perception", "perceive_vision", {})
        mark(
            "perceive_vision honest when offline",
            vision.get("status") == "error",
            f"status={vision.get('status')} msg={vision.get('message', '')[:80]}",
        )
    else:
        mark("perceive_vision honest when offline", True, "vision really online — skip offline check")

    uid = f"perc_smoke_{uuid.uuid4().hex[:10]}"
    try:
        reply = th.process_user_input("Hello Monday, my name is Matthew.", user_id=uid) or ""
        crashed = reply.startswith("CRASH:")
        mark(
            "chat path process_user_input",
            (not crashed) and isinstance(reply, str) and bool(reply.strip()),
            (reply[:120] + "…") if len(reply) > 120 else reply,
        )
    except Exception as exc:
        mark("chat path process_user_input", False, f"CRASH: {exc}\n{traceback.format_exc()}")

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
