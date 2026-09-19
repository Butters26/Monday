#!/usr/bin/env python3
"""Hard smoke: reasoning/language grounding on live create_core_systems.

Pass/fail only (no percents). Cases:
  1. Multi-fact combine (live + job; dog + live)
  2. No invent / wrong-attribute substitute (favorite food ≠ color)
  3. Honest empty when unknown (sister name)
  4. Non-pattern narrative recall (where/who/when hiking)
  5. Use Monday role memories for what-did-you-say
  6. No mangled lives_in ("Your lives in is …")
  7. No answering with prior question text
"""

from __future__ import annotations

import os
import uuid

os.environ.setdefault("NOTUS_POSTGRES_DB", "notus_memory")
os.environ.setdefault("NOTUS_POSTGRES_USER", os.getenv("USER", "box"))
os.environ.setdefault("NOTUS_POSTGRES_HOST", "localhost")
os.environ.setdefault(
    "NOTUS_POSTGRES_PASSWORD", os.getenv("NOTUS_POSTGRES_PASSWORD", "box")
)

from run_abin import create_core_systems, shutdown_core_systems


def main() -> int:
    systems = create_core_systems()
    th = systems["thalamus"]
    uid = f"smoke_reason_{uuid.uuid4().hex[:10]}"
    results: list[tuple[str, str, str]] = []

    def mark(case: str, ok: bool, detail: str = "") -> None:
        results.append((case, "PASS" if ok else "FAIL", detail))
        print(f"[{'PASS' if ok else 'FAIL'}] {case}" + (f" — {detail}" if detail else ""))

    def ask(msg: str) -> str:
        return th.process_user_input(msg, user_id=uid) or ""

    # Seed durable + narrative memories via live path
    ask("Remember my dog is named Pixel.")
    ask("I live in Boulder.")
    ask("I work as a carpenter.")
    ask("My favorite color is teal.")
    ask("Remember the codeword is NebulaQuartz.")
    code_ans = ask("What is the codeword?")
    ask("I went hiking on Flatiron Trail last Saturday with Pixel.")

    # 1a combine live + job
    r = ask("Where do I live and what is my job?")
    low = r.lower()
    mark(
        "1a combine live + job",
        "boulder" in low
        and "carpenter" in low
        and "lives in is" not in low
        and "your lives in" not in low,
        f"chat={r!r}",
    )

    # 1b combine dog + live
    r = ask("Tell me about my dog and where I live.")
    low = r.lower()
    mark(
        "1b combine dog + live",
        "pixel" in low and "boulder" in low and "lives in is" not in low,
        f"chat={r!r}",
    )

    # 1c yes-style multi fact
    r = ask("Do I have a dog named Pixel who lives with me in Boulder?")
    low = r.lower()
    mark(
        "1c dog+live compound no mangling",
        "pixel" in low
        and "boulder" in low
        and "lives in is" not in low
        and "your lives in" not in low,
        f"chat={r!r}",
    )

    # 2 no invent favorite food from favorite color
    r = ask("What is my favorite food?")
    low = r.lower()
    mark(
        "2 no invent favorite food from color",
        "teal" not in low
        and "color" not in low
        and ("grounded" in low or "enough" in low or "don't know" in low or "do not" in low or "not sure" in low or "don't have" in low or "do not have" in low),
        f"chat={r!r}",
    )

    # 3 honest empty sister
    r = ask("What is my sister's name?")
    low = r.lower()
    invent = any(x in low for x in ("pixel", "boulder", "carpenter", "teal", "nebulaquartz"))
    mark(
        "3 honest empty sister name",
        not invent
        and (
            "grounded" in low
            or "enough" in low
            or "do not" in low
            or "don't" in low
            or "not sure" in low
        ),
        f"chat={r!r}",
    )

    # 4 narrative hiking
    r = ask("Where did I go hiking?")
    low = r.lower()
    mark(
        "4a narrative where hiking",
        "flatiron" in low and not low.strip().startswith("i went"),
        f"chat={r!r}",
    )

    r = ask("Who did I hike with?")
    low = r.lower()
    mark(
        "4b narrative who hiking",
        "pixel" in low,
        f"chat={r!r}",
    )

    r = ask("When did I go hiking?")
    low = r.lower()
    mark(
        "4c narrative when hiking",
        "saturday" in low and "where did i go hiking" not in low,
        f"chat={r!r}",
    )

    # 5 monday speech
    r = ask("What did you say about NebulaQuartz?")
    mark(
        "5a monday speech about codeword",
        "NebulaQuartz" in r and "How it felt" not in r,
        f"chat={r!r} prior={code_ans!r}",
    )

    r = ask("What did you just say about the codeword?")
    mark(
        "5b monday speech just-said codeword",
        "NebulaQuartz" in r or "codeword" in r.lower(),
        f"chat={r!r}",
    )

    # 6 single live still clean
    r = ask("Where do I live?")
    low = r.lower()
    mark(
        "6 live-in clean phrasing",
        "boulder" in low and "live" in low and "lives in is" not in low,
        f"chat={r!r}",
    )

    # 7 favorite color still works
    r = ask("What is my favorite color?")
    mark(
        "7 favorite color grounded",
        "teal" in r.lower(),
        f"chat={r!r}",
    )

    shutdown_core_systems(systems)

    print("---")
    fails = [x for x in results if x[1] == "FAIL"]
    for case, status, _detail in results:
        print(f"{status}: {case}")
    if fails:
        print(f"OVERALL FAIL ({len(fails)} cases)")
        return 1
    print("OVERALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
