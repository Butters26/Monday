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
    "Explicit/contrast": [
        "I'm happy.",
        "I'm proud of myself.",
        "I'm angry about what happened.",
        "I'm scared.",
        "I'm relieved.",
        "I'm really happy with how that turned out.",
        "I thought I'd be furious, but I'm actually relieved.",
        "I was sad earlier, but I'm fine now.",
        "I'm not angry.",
        "I'm not happy about this.",
        "I'm proud of finishing it, but I'm exhausted.",
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
    # Explicit/contrast group
    "I'm happy.": "affection",
    "I'm proud of myself.": "success",
    "I'm angry about what happened.": "conflict",
    "I'm scared.": "threat",
    "I'm relieved.": "success",
    "I'm really happy with how that turned out.": "success",
    "I thought I'd be furious, but I'm actually relieved.": "success",
    "I was sad earlier, but I'm fine now.": "neutral",
    "I'm not angry.": "neutral",
    "I'm not happy about this.": "neutral",
    "I'm proud of finishing it, but I'm exhausted.": "success",
}

EXPECT_USER_EMOTION = {
    "I'm happy.": "happy",
    "I'm proud of myself.": "proud",
    "I'm angry about what happened.": "angry",
    "I'm scared.": "scared",
    "I'm relieved.": "relieved",
    "I'm really happy with how that turned out.": "happy",
    "I thought I'd be furious, but I'm actually relieved.": "relieved",
    "I was sad earlier, but I'm fine now.": "neutral",
    "I'm not angry.": "neutral",
    "I'm not happy about this.": "neutral",
    "I'm proud of finishing it, but I'm exhausted.": "proud",
    "I'm really happy with how that turned out": "happy",
    "I thought I'd be furious, but I'm actually relieved": "relieved",
    "I'm not angry": "neutral",
    "I'm not sad anymore": "neutral",
    "It's not unfair": "neutral",
    "I'm angry": "angry",
    "I'm furious": "angry",
    "I'm sad": "sad",
    "I'm worried": "worried",
}

EXPECT_NEGATION = {
    "I'm not angry",
    "I'm not sad anymore",
    "I thought I'd be furious, but I'm actually relieved",
    "It's not unfair",
    "I'm not angry.",
    "I'm not happy about this.",
    "I thought I'd be furious, but I'm actually relieved.",
    "I was sad earlier, but I'm fine now.",
}

EXPECT_CONTRAST = {
    "I thought I'd be furious, but I'm actually relieved",
    "I thought I'd be furious, but I'm actually relieved.",
    "I was sad earlier, but I'm fine now.",
}


def fmt_cues(cues):
    nz = {k: round(v, 3) for k, v in cues.items() if v > 0}
    return nz if nz else "ALL_ZEROS"


def dump_line(text: str, u) -> list[str]:
    a = u.appraisal
    changed = []
    if u.negation_affected:
        changed.append("negation")
    if u.contrast_affected:
        changed.append("contrast")
    changed_s = "+".join(changed) if changed else "none"
    return [
        f"TEXT: {text}",
        f"  explicit/self-reported: {u.explicit_emotion}",
        f"  appraisal event: {a.event_type}",
        f"  AppraisalEngine inferred emotion: {u.appraisal_inferred_emotion}",
        f"  semantic candidate: event={u.semantic_event} emotion={u.semantic_emotion} "
        f"conf={u.semantic_confidence} used={u.semantic_used}",
        f"  keyword cues: {fmt_cues(u.keyword_cues)}",
        f"  final user emotion: {u.inferred_emotion}",
        f"  final event: {u.event_type}",
        f"  confidence: {u.confidence:.3f}",
        f"  negation/contrast changed result: {changed_s} "
        f"(neg={u.negation_affected}, contrast={u.contrast_affected}, src={u.primary_source})",
    ]


def main() -> int:
    eng = AdvancedEmotionalEngine()
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
            "meaning phrases; basic hash embeddings have LOW authority "
            "(support-only when agreeing; must not override confident appraisal)."
        )

    fails = []
    for group, texts in GROUPS.items():
        lines.append(f"\n## {group}")
        for text in texts:
            u = eng._understand_emotional_text(text)
            lines.extend(dump_line(text, u))
            expected = EXPECT_EVENT.get(text)
            if expected is not None and u.event_type != expected:
                fails.append(f"{text!r}: event {u.event_type} != {expected}")
            exp_emo = EXPECT_USER_EMOTION.get(text)
            if exp_emo is not None and u.inferred_emotion != exp_emo:
                fails.append(f"{text!r}: user emotion {u.inferred_emotion} != {exp_emo}")
            if text in EXPECT_NEGATION and not (u.negation_affected or u.contrast_affected):
                fails.append(f"{text!r}: expected negation/contrast affected")
            if text in EXPECT_CONTRAST and not u.contrast_affected:
                fails.append(f"{text!r}: expected contrast_affected")
            if text in ("I'm not angry", "I'm not sad anymore", "I'm not angry.") and sum(
                u.keyword_cues.values()
            ) > 0:
                fails.append(f"{text!r}: keyword should be suppressed")
            # Basic semantic must not override confident appraisal on known conflicts
            if text in ("I'm furious", "I'm sad", "I'm worried", "I'm scared."):
                if u.semantic_used and u.semantic_event and u.semantic_event != u.event_type:
                    fails.append(f"{text!r}: basic semantic overrode appraisal")

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
