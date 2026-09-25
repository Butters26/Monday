#!/usr/bin/env python3
"""Prove WANT-GAP 5 (Belief part): form belief in session A → present in session B."""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

from run_abin import create_core_systems, shutdown_core_systems
from reasoning import Belief


def main() -> int:
    marker = f"WANTGAP5_{int(time.time())}"
    key = f"wantgap5_{marker.lower()}"
    about = f"TOPIC_{marker}"
    believe = f"BELIEF_{marker}"
    conf = 0.73

    tmp = tempfile.mkdtemp(prefix="wantgap5-prove-")
    sqlite = str(Path(tmp) / "notus_memory.sqlite3")
    os.environ["MONDAY_NOTUS_SQLITE"] = sqlite
    print(f"MONDAY_NOTUS_SQLITE={sqlite}")

    rt_a = Path(tempfile.mkdtemp(prefix="wg5-prove-a-"))
    sys_a = create_core_systems(runtime_directory=str(rt_a), enable_autonomous=False)
    print("session_a_identity", json.dumps(sys_a["notus_identity"], default=str))
    reasoner_a = sys_a["reasoning"].reasoner
    reasoner_a.beliefs[key] = Belief(
        about=about,
        what_i_believe=believe,
        why_i_believe_it=["formed in session A WANT-GAP5 proof"],
        confidence=conf,
        formed_when=time.time(),
        times_reinforced=2,
    )
    save = reasoner_a._save_persistent_state_to_memory()
    print("session_a_save", json.dumps(save, default=str)[:400])
    if not save or save.get("status") != "success":
        shutdown_core_systems(sys_a)
        print("FAIL save")
        return 1
    # Also exercise shutdown flush path
    shutdown_core_systems(sys_a)

    rt_b = Path(tempfile.mkdtemp(prefix="wg5-prove-b-"))
    sys_b = create_core_systems(runtime_directory=str(rt_b), enable_autonomous=False)
    print("session_b_identity", json.dumps(sys_b["notus_identity"], default=str))
    reasoner_b = sys_b["reasoning"].reasoner
    present = key in reasoner_b.beliefs
    belief = reasoner_b.beliefs.get(key)
    content_ok = bool(
        belief
        and belief.about == about
        and belief.what_i_believe == believe
        and abs(float(belief.confidence) - conf) < 1e-9
        and int(belief.times_reinforced) == 2
    )
    # Usable on Reasoning path: methods that walk self.beliefs see it
    abouts = [b.about for b in reasoner_b.beliefs.values()]
    usable = about in abouts and content_ok
    reasoner_b._question_own_beliefs()  # exercises belief walk
    print(f"session_b_belief_key_present={present}")
    print(f"session_b_belief_content_ok={content_ok}")
    print(f"session_b_belief_usable_on_reasoning={usable}")
    if belief:
        print(
            "session_b_belief",
            json.dumps(
                {
                    "about": belief.about,
                    "what_i_believe": belief.what_i_believe,
                    "confidence": belief.confidence,
                    "times_reinforced": belief.times_reinforced,
                },
                default=str,
            ),
        )
    shutdown_core_systems(sys_b)
    if present and content_ok and usable:
        print("PASS")
        return 0
    print("FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
