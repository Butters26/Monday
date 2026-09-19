#!/usr/bin/env python3
"""Smoke: emotion text-understanding path (appraisal primary + semantic + keyword supplement)."""
from __future__ import annotations

import sys
from advanced_emotional_engine import AdvancedEmotionalEngine

GROUPS = {
    "Unfairness": [
        "this is not fair",
        "they treated me unfairly",
        "I got screwed over",
        "everyone else got a chance except me",
    ],
    "Anger": [
        "I'm angry",
        "I'm furious",
        "I'm completely fed up",
        "this is really pissing me off",
    ],
    "Sadness/rejection": [
        "I'm sad",
        "I feel rejected",
        "it feels like nobody wants me around",
        "that really hurt",
    ],
    "Concern/fear": [
        "I'm worried",
        "I'm scared this is going to go wrong",
        "I have a bad feeling about this",
    ],
    "Positive/pride": [
        "I'm proud of what I did",
        "I actually pulled it off",
        "I'm really happy with how that turned out",
    ],
    "Negation/context": [
        "I'm not angry",
        "I'm not sad anymore",
        "I thought I'd be furious, but I'm actually relieved",
        "It's not unfair",
    ],
}

EXPECT_EVENT = {
    "this is not fair": "unfairness",
    "they treated me unfairly": "unfairness",
    "I got screwed over": "unfairness",
    "everyone else got a chance except me": "unfairness",
    "I'm angry": "conflict",
    "I'm furious": "conflict",
    "I'm completely fed up": "conflict",
    "this is really pissing me off": "conflict",
    "I'm sad": "rejection",
    "I feel rejected": "rejection",
    "it feels like nobody wants me around": "rejection",
    "that really hurt": "harm",
    "I'm worried": "threat",
    "I'm scared this is going to go wrong": "threat",
    "I have a bad feeling about this": "threat",
    "I'm proud of what I did": "success",
    "I actually pulled it off": "success",
    "I'm really happy with how that turned out": "success",
    "I'm not angry": "neutral",
    "I'm not sad anymore": "neutral",
    "I thought I'd be furious, but I'm actually relieved": "success",
    "It's not unfair": "neutral",
}

EXPECT_NEGATION = {
    "I'm not angry",
    "I'm not sad anymore",
    "I thought I'd be furious, but I'm actually relieved",
    "It's not unfair",
}


def fmt_cues(cues):
    nz = {k: round(v, 3) for k, v in cues.items() if v > 0}
    return nz if nz else "ALL_ZEROS"


def main() -> int:
    eng = AdvancedEmotionalEngine()
    # Force embedding probe so ST vs fallback is known
    eng._get_embedding_engine()
    st_available = eng._embedding_model_type == "sentence_transformer"
    lines = []
    lines.append("=== AFTER: emotion text-understanding comparative ===")
    lines.append(
        f"sentence-transformers: {'AVAILABLE' if st_available else 'UNAVAILABLE'} "
        f"(embedding model_type={eng._embedding_model_type})"
    )
    if not st_available:
        lines.append(
            "capability loss: paraphrase-only matches rely more on AppraisalEngine "
            "meaning phrases; basic hash embeddings give weaker semantic support."
        )

    fails = []
    for group, texts in GROUPS.items():
        lines.append(f"\n## {group}")
        for text in texts:
            u = eng._understand_emotional_text(text)
            a = u.appraisal
            lines.append(f"TEXT: {text}")
            lines.append(
                f"  AppraisalEngine: event={a.event_type} severity={a.severity} "
                f"negated={a.negated} user_emotion={a.user_inferred_emotion} "
                f"conf={a.user_confidence:.3f}"
            )
            if u.semantic_used:
                lines.append(
                    f"  semantic: used event={u.semantic_event} "
                    f"emotion={u.semantic_emotion} conf={u.semantic_confidence} "
                    f"model={eng._embedding_model_type}"
                )
            else:
                lines.append(
                    f"  semantic: not decisive (used={u.semantic_used}, "
                    f"model={eng._embedding_model_type})"
                )
            lines.append(f"  keyword/cue: {fmt_cues(u.keyword_cues)}")
            lines.append(
                f"  final combined: source={u.primary_source} event={u.event_type} "
                f"emotion={u.inferred_emotion} severity={u.severity:.3f} "
                f"confidence={u.confidence:.3f} negation_affected={u.negation_affected}"
            )
            expected = EXPECT_EVENT[text]
            if u.event_type != expected:
                fails.append(f"{text!r}: event {u.event_type} != {expected}")
            if text in EXPECT_NEGATION and not u.negation_affected:
                fails.append(f"{text!r}: expected negation_affected")
            if text in ("I'm not angry", "I'm not sad anymore") and sum(u.keyword_cues.values()) > 0:
                fails.append(f"{text!r}: keyword should be suppressed")

    report = "\n".join(lines) + "\n"
    with open("_emotion_cues_after.txt", "w", encoding="utf-8") as f:
        f.write(report)
    print(report)
    if fails:
        print("FAILS:")
        for f in fails:
            print(" -", f)
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
