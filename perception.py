#!/usr/bin/env python3
"""Perception Lobe — honest text input for the live path.

Claimed modalities:
  - text: implemented (normalize + extract concepts/entities)
  - audio: disabled (no STT / microphone claimed)
  - vision: disabled (no webcam / Haar / OpenCV claimed)

Does not start autonomous hearing/vision loops and does not print fake
"microphone initialized" / "webcam initialized" success lines.
"""

from __future__ import annotations

import os
import re
import time
from typing import Any, Dict, List, Optional, Set

from thalamus import get_thalamus


_WHITESPACE_RE = re.compile(r"\s+")
_PUNCT_STRIP = ".,!?;:\"'()[]{}"


class PerceptionLobe:
    """Text perception: normalize input and extract simple concepts."""

    # Explicit: do not claim senses we do not implement.
    AUDIO_ENABLED = False
    VISION_ENABLED = False
    TEXT_ENABLED = True

    def __init__(self, thalamus=None) -> None:
        self.thalamus = thalamus if thalamus is not None else get_thalamus()
        self.running = True
        self.seen_concepts: Set[str] = set()
        self.seen_entities: Set[str] = set()
        # Honest capability flags — never flipped by optional imports.
        self.stt_available = False
        self.vision_available = False
        self.camera = None
        self.stt_engine = None

    @staticmethod
    def normalize_text(text: str) -> str:
        """Collapse whitespace and strip edges; keep original casing for entities."""
        if not isinstance(text, str):
            return ""
        return _WHITESPACE_RE.sub(" ", text).strip()

    def process_text_input(self, text: str) -> Dict[str, Any]:
        """Normalize text, extract concepts/entities, optionally signal novelty."""
        normalized = self.normalize_text(text)
        concepts = self._extract_concepts(normalized)
        self._maybe_signal_novelty(normalized, concepts)
        return {
            "type": "text_input",
            "raw_text": text if isinstance(text, str) else "",
            "text": normalized,
            "normalized_text": normalized,
            "confidence": 1.0 if normalized else 0.0,
            "concepts": concepts,
            "intent_hints": list(concepts.get("questions") or []),
            "entities": list(concepts.get("entities") or []),
            "words": list(concepts.get("words") or []),
            "sentiment": concepts.get("sentiment", "neutral"),
            "emotions": list(concepts.get("emotions") or []),
            "input_type": "text",
            "source": "text",
            "modalities": {
                "text": True,
                "audio": False,
                "vision": False,
            },
            "timestamp": time.time(),
        }

    def _extract_concepts(self, text: str) -> Dict[str, Any]:
        """Simple concept/entity extraction — no remote STT, no vision."""
        text_lower = text.lower()
        words = text.split() if text else []

        meaningful_words: List[str] = []
        for word in words:
            cleaned = word.lower().strip(_PUNCT_STRIP)
            if len(cleaned) >= 2:
                meaningful_words.append(cleaned)
        if not meaningful_words and words:
            meaningful_words = [w.lower().strip(_PUNCT_STRIP) for w in words if w.strip()]

        concepts: Dict[str, Any] = {
            "words": meaningful_words,
            "length": len(text),
            "questions": [],
            "emotions": [],
            "entities": [],
            "negations": [],
            "subject": None,
            "verb": None,
            "object": None,
            "sentiment": "neutral",
        }

        question_words = ("what", "why", "how", "when", "where", "who", "which")
        for word in question_words:
            if word in text_lower.split() or (word in text_lower and "?" in text):
                if word not in concepts["questions"]:
                    concepts["questions"].append(word)
        if text.endswith("?") and not concepts["questions"]:
            concepts["questions"].append("?")

        negation_words = {
            "not",
            "never",
            "no",
            "n't",
            "dont",
            "don't",
            "cant",
            "can't",
            "wont",
            "won't",
        }
        for i, word in enumerate(words):
            if word.lower().strip(_PUNCT_STRIP) in negation_words and i + 1 < len(words):
                concepts["negations"].append(words[i + 1].lower().strip(_PUNCT_STRIP))

        emotion_words = {
            "happy": ("happy", "joy", "great", "wonderful", "amazing", "glad", "pleased"),
            "sad": ("sad", "unhappy", "depressed", "down", "miserable", "blue"),
            "angry": ("angry", "mad", "furious", "hate", "pissed"),
            "excited": ("excited", "thrilled", "pumped", "enthusiastic"),
            "worried": ("worried", "anxious", "concerned", "scared", "nervous"),
        }
        for emotion, emo_list in emotion_words.items():
            for emo_word in emo_list:
                if emo_word in text_lower:
                    if emo_word in concepts["negations"]:
                        if emotion == "happy":
                            concepts["emotions"].append("sad")
                        elif emotion == "sad":
                            concepts["emotions"].append("happy")
                    else:
                        concepts["emotions"].append(emotion)
                    break

        common_verbs = (
            "is",
            "are",
            "was",
            "were",
            "feel",
            "think",
            "want",
            "need",
            "like",
            "love",
            "hate",
            "have",
            "had",
            "am",
        )
        if words:
            concepts["subject"] = words[0].strip(_PUNCT_STRIP) or None
            for i, word in enumerate(words):
                if word.lower().strip(_PUNCT_STRIP) in common_verbs:
                    concepts["verb"] = word.strip(_PUNCT_STRIP)
                    if i + 1 < len(words):
                        concepts["object"] = " ".join(
                            w.strip(_PUNCT_STRIP) for w in words[i + 1 :]
                        )
                    break

        positive_words = {
            "good",
            "great",
            "wonderful",
            "amazing",
            "love",
            "like",
            "happy",
            "excellent",
        }
        negative_words = {
            "bad",
            "terrible",
            "awful",
            "hate",
            "dislike",
            "sad",
            "horrible",
        }
        tokens = text_lower.split()
        pos_count = sum(
            1 for w in tokens if w.strip(_PUNCT_STRIP) in positive_words and w not in concepts["negations"]
        )
        neg_count = sum(
            1 for w in tokens if w.strip(_PUNCT_STRIP) in negative_words and w not in concepts["negations"]
        )
        if pos_count > neg_count:
            concepts["sentiment"] = "positive"
        elif neg_count > pos_count:
            concepts["sentiment"] = "negative"

        # Proper-noun-ish entities: capitalized tokens after the first word,
        # plus consecutive Capitalized Name sequences.
        entity_parts: List[str] = []
        for i, word in enumerate(words):
            bare = word.strip(_PUNCT_STRIP)
            if not bare:
                continue
            if i > 0 and len(bare) > 1 and bare[0].isupper() and not bare.isupper():
                entity_parts.append(bare)
            elif entity_parts:
                concepts["entities"].append(" ".join(entity_parts))
                entity_parts = []
        if entity_parts:
            concepts["entities"].append(" ".join(entity_parts))

        # Deduplicate while preserving order
        seen: Set[str] = set()
        unique_entities: List[str] = []
        for ent in concepts["entities"]:
            key = ent.lower()
            if key not in seen:
                seen.add(key)
                unique_entities.append(ent)
        concepts["entities"] = unique_entities

        return concepts

    def _maybe_signal_novelty(self, text: str, concepts: Dict[str, Any]) -> None:
        """Best-effort novelty signal only if a novelty lobe is registered."""
        with self.thalamus.lobe_handlers_lock:
            has_novelty = "novelty" in self.thalamus.lobe_handlers
        if not has_novelty:
            return

        novel_entities: List[str] = []
        for entity in concepts.get("entities") or []:
            key = entity.lower()
            if key not in self.seen_entities:
                novel_entities.append(entity)
                self.seen_entities.add(key)

        novel_concepts: List[str] = []
        common = {
            "what",
            "this",
            "that",
            "have",
            "from",
            "with",
            "will",
            "know",
            "think",
            "about",
            "which",
            "your",
            "their",
            "them",
            "then",
            "than",
        }
        for word in concepts.get("words") or []:
            word_lower = word.lower()
            if len(word_lower) > 3 and word_lower not in self.seen_concepts and word_lower not in common:
                novel_concepts.append(word)
                self.seen_concepts.add(word_lower)

        novel_questions = bool(concepts.get("questions"))
        if not (novel_entities or novel_concepts or (novel_questions and len(text) > 20)):
            return

        confidence = min(
            0.95,
            len(novel_entities) * 0.3
            + len(novel_concepts) * 0.2
            + (0.15 if novel_questions else 0),
        )
        try:
            self.thalamus.send_message(
                destination="novelty",
                msg_type="novelty_signal",
                content={
                    "type": "novelty_signal",
                    "source": "perception",
                    "stimulus": text,
                    "stimulus_type": "text_input",
                    "novel_entities": novel_entities,
                    "novel_concepts": novel_concepts,
                    "has_novel_questions": novel_questions,
                    "confidence": confidence,
                },
                source="perception",
            )
        except Exception:
            pass

    def process_audio_input(self) -> Optional[Dict[str, Any]]:
        """Audio is not implemented — never claim STT success."""
        return None

    def process_visual_input(self) -> Optional[Dict[str, Any]]:
        """Vision is not implemented — never claim webcam/Haar success."""
        return None

    def get_status(self) -> Dict[str, Any]:
        return {
            "text_input": True,
            "stt_available": False,
            "vision_available": False,
            "audio_enabled": False,
            "vision_enabled": False,
            "claimed_modalities": ["text"],
        }

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = message.get("type")
        payload = message.get("content", message)
        if not isinstance(payload, dict):
            payload = {}

        if msg_type == "health":
            return {"status": "success", "healthy": True, "pid": os.getpid()}

        if msg_type in ("process_text", "user_input", "perceive"):
            text = payload.get("text") or payload.get("user_input") or ""
            result = self.process_text_input(text if isinstance(text, str) else "")
            return {"status": "success", "content": result}

        if msg_type == "listen_audio":
            return {
                "status": "error",
                "message": "Audio perception disabled — text only",
                "content": {"audio_enabled": False},
            }

        if msg_type == "capture_visual":
            return {
                "status": "error",
                "message": "Vision perception disabled — text only",
                "content": {"vision_enabled": False},
            }

        if msg_type == "get_status":
            status = self.get_status()
            return {"status": "success", "content": status, **status}

        return {"status": "error", "message": f"Unknown message type: {msg_type}"}

    def start(self) -> None:
        """CLI helper — register and idle. No hearing/vision threads."""
        print("Perception Lobe: text only (audio/vision disabled)")
        result = self.thalamus.register_lobe("perception", self)
        if result.get("status") != "success":
            print("Failed to register with Thalamus")
            return
        while self.running:
            time.sleep(0.1)

    def shutdown(self) -> None:
        self.running = False


if __name__ == "__main__":
    lobe = PerceptionLobe()
    try:
        lobe.start()
    except KeyboardInterrupt:
        print("\nPerception lobe shutting down...")
        lobe.shutdown()
