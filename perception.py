#!/usr/bin/env python3
"""Perception Lobe — senses → concepts/entities/novelty → thalamus.

Modalities:
  - text: always online (normalize + extract concepts/entities)
  - audio: real one-shot STT when speech_recognition + microphone open succeed
  - vision: real one-frame features when opencv + camera open succeed

No autonomous hearing/vision theater loops. Never prints fake
"microphone initialized" / "webcam active" unless the device open
actually succeeded.
"""

from __future__ import annotations

import os
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from thalamus import get_thalamus


_WHITESPACE_RE = re.compile(r"\s+")
_PUNCT_STRIP = ".,!?;:\"'()[]{}"

# Phrases that must never appear unless a real device open succeeded.
_FAKE_SUCCESS_PHRASES = (
    "microphone initialized",
    "webcam initialized",
    "webcam active",
    "autonomous hearing active",
    "autonomous vision active",
)


class PerceptionLobe:
    """Multi-modal perception with honest capability probing."""

    TEXT_ENABLED = True

    def __init__(self, thalamus=None, probe_devices: bool = True) -> None:
        self.thalamus = thalamus if thalamus is not None else get_thalamus()
        self.running = True
        self.seen_concepts: Set[str] = set()
        self.seen_entities: Set[str] = set()

        self.stt_available = False
        self.vision_available = False
        self.stt_engine = None
        self._audio_reason = "not probed"
        self._vision_reason = "not probed"
        self._sr_module = None
        self._cv2 = None

        if probe_devices:
            self._probe_audio()
            self._probe_vision()

    # ------------------------------------------------------------------
    # Honest capability probes (no continuous loops, no fake success)
    # ------------------------------------------------------------------

    def _probe_audio(self) -> None:
        """Mark audio online only if speech_recognition + mic open succeed."""
        try:
            import speech_recognition as sr  # type: ignore
        except ImportError:
            self.stt_available = False
            self.stt_engine = None
            self._sr_module = None
            self._audio_reason = "speech_recognition not installed"
            return

        try:
            recognizer = sr.Recognizer()
            mic = sr.Microphone()
            # Opening the context is the real device check.
            with mic as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.1)
            self._sr_module = sr
            self.stt_engine = recognizer
            self.stt_available = True
            self._audio_reason = "microphone open succeeded"
            # Honest success only after open really worked.
            print("Perception: microphone open succeeded — audio online")
        except Exception as exc:
            self.stt_available = False
            self.stt_engine = None
            self._sr_module = None
            self._audio_reason = f"microphone unavailable: {exc}"

    def _probe_vision(self) -> None:
        """Mark vision online only if opencv + camera open + frame succeed."""
        try:
            import cv2  # type: ignore
        except ImportError:
            self.vision_available = False
            self._cv2 = None
            self._vision_reason = "opencv not installed"
            return

        cap = None
        try:
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                self.vision_available = False
                self._cv2 = None
                self._vision_reason = "camera index 0 not openable"
                return
            ret, frame = cap.read()
            if not ret or frame is None:
                self.vision_available = False
                self._cv2 = None
                self._vision_reason = "camera opened but no frame"
                return
            self._cv2 = cv2
            self.vision_available = True
            self._vision_reason = "camera open + frame succeeded"
            print("Perception: camera open succeeded — vision online")
        except Exception as exc:
            self.vision_available = False
            self._cv2 = None
            self._vision_reason = f"camera unavailable: {exc}"
        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Unified output shape for thalamus
    # ------------------------------------------------------------------

    @staticmethod
    def _unified(
        modality: str,
        *,
        text: Optional[str] = None,
        concepts: Optional[List[str]] = None,
        entities: Optional[List[str]] = None,
        novelty_flags: Optional[List[str]] = None,
        confidence: float = 0.0,
        raw_meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "modality": modality,
            "concepts": list(concepts or []),
            "entities": list(entities or []),
            "novelty_flags": list(novelty_flags or []),
            "confidence": float(confidence),
            "raw_meta": dict(raw_meta or {}),
        }
        if text is not None:
            out["text"] = text
        return out

    @staticmethod
    def normalize_text(text: str) -> str:
        if not isinstance(text, str):
            return ""
        return _WHITESPACE_RE.sub(" ", text).strip()

    # ------------------------------------------------------------------
    # Text channel (required)
    # ------------------------------------------------------------------

    def perceive_text(self, text: str) -> Dict[str, Any]:
        """Normalize text → concepts/entities/novelty → unified shape."""
        raw = text if isinstance(text, str) else ""
        normalized = self.normalize_text(raw)
        extracted = self._extract_concepts(normalized)
        concept_list = list(extracted.get("words") or [])
        entity_list = list(extracted.get("entities") or [])
        novelty_flags = self._compute_novelty_flags(normalized, extracted)
        self._maybe_signal_novelty(normalized, extracted, novelty_flags)

        return self._unified(
            "text",
            text=normalized,
            concepts=concept_list,
            entities=entity_list,
            novelty_flags=novelty_flags,
            confidence=1.0 if normalized else 0.0,
            raw_meta={
                "raw_text": raw,
                "normalized_text": normalized,
                "words": concept_list,
                "questions": list(extracted.get("questions") or []),
                "emotions": list(extracted.get("emotions") or []),
                "sentiment": extracted.get("sentiment", "neutral"),
                "negations": list(extracted.get("negations") or []),
                "subject": extracted.get("subject"),
                "verb": extracted.get("verb"),
                "object": extracted.get("object"),
                "intent_hints": list(extracted.get("questions") or []),
                "source": "text",
                "timestamp": time.time(),
            },
        )

    # Back-compat alias used by older callers / smoke helpers.
    def process_text_input(self, text: str) -> Dict[str, Any]:
        result = self.perceive_text(text)
        # Extra keys some live-path consumers still look for.
        result["normalized_text"] = result.get("text", "")
        result["words"] = list(result.get("concepts") or [])
        result["type"] = "text_input"
        result["input_type"] = "text"
        result["source"] = "text"
        result["intent_hints"] = list((result.get("raw_meta") or {}).get("intent_hints") or [])
        result["sentiment"] = (result.get("raw_meta") or {}).get("sentiment", "neutral")
        result["emotions"] = list((result.get("raw_meta") or {}).get("emotions") or [])
        return result

    def _extract_concepts(self, text: str) -> Dict[str, Any]:
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
            "not", "never", "no", "n't", "dont", "don't", "cant", "can't", "wont", "won't",
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
            "is", "are", "was", "were", "feel", "think", "want", "need",
            "like", "love", "hate", "have", "had", "am",
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
            "good", "great", "wonderful", "amazing", "love", "like", "happy", "excellent",
        }
        negative_words = {
            "bad", "terrible", "awful", "hate", "dislike", "sad", "horrible",
        }
        tokens = text_lower.split()
        pos_count = sum(
            1 for w in tokens
            if w.strip(_PUNCT_STRIP) in positive_words and w not in concepts["negations"]
        )
        neg_count = sum(
            1 for w in tokens
            if w.strip(_PUNCT_STRIP) in negative_words and w not in concepts["negations"]
        )
        if pos_count > neg_count:
            concepts["sentiment"] = "positive"
        elif neg_count > pos_count:
            concepts["sentiment"] = "negative"

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

        seen: Set[str] = set()
        unique_entities: List[str] = []
        for ent in concepts["entities"]:
            key = ent.lower()
            if key not in seen:
                seen.add(key)
                unique_entities.append(ent)
        concepts["entities"] = unique_entities
        return concepts

    def _compute_novelty_flags(self, text: str, concepts: Dict[str, Any]) -> List[str]:
        flags: List[str] = []
        for entity in concepts.get("entities") or []:
            key = entity.lower()
            if key not in self.seen_entities:
                flags.append(f"novel_entity:{entity}")
                self.seen_entities.add(key)

        common = {
            "what", "this", "that", "have", "from", "with", "will", "know",
            "think", "about", "which", "your", "their", "them", "then", "than",
        }
        for word in concepts.get("words") or []:
            word_lower = word.lower()
            if len(word_lower) > 3 and word_lower not in self.seen_concepts and word_lower not in common:
                flags.append(f"novel_concept:{word}")
                self.seen_concepts.add(word_lower)

        if concepts.get("questions") and len(text) > 20:
            flags.append("novel_question")
        return flags

    def _maybe_signal_novelty(
        self, text: str, concepts: Dict[str, Any], novelty_flags: List[str]
    ) -> None:
        if not novelty_flags:
            return
        with self.thalamus.lobe_handlers_lock:
            has_novelty = "novelty" in self.thalamus.lobe_handlers
        if not has_novelty:
            return

        novel_entities = [
            f.split(":", 1)[1] for f in novelty_flags if f.startswith("novel_entity:")
        ]
        novel_concepts = [
            f.split(":", 1)[1] for f in novelty_flags if f.startswith("novel_concept:")
        ]
        novel_questions = "novel_question" in novelty_flags
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
                    "novelty_flags": novelty_flags,
                    "confidence": confidence,
                },
                source="perception",
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Audio channel — one-shot listen when STT+mic really available
    # ------------------------------------------------------------------

    def perceive_audio(self) -> Dict[str, Any]:
        """One-shot listen → transcript → same text pipeline (modality=audio)."""
        if not self.stt_available or self.stt_engine is None or self._sr_module is None:
            return self._unified(
                "audio",
                concepts=[],
                entities=[],
                novelty_flags=[],
                confidence=0.0,
                raw_meta={
                    "available": False,
                    "reason": self._audio_reason,
                    "error": "audio perception disabled — device/libs unavailable",
                    "timestamp": time.time(),
                },
            )

        sr = self._sr_module
        try:
            with sr.Microphone() as source:
                self.stt_engine.adjust_for_ambient_noise(source, duration=0.3)
                audio = self.stt_engine.listen(source, timeout=5, phrase_time_limit=10)
            try:
                transcript = self.stt_engine.recognize_google(audio)
            except sr.UnknownValueError:
                return self._unified(
                    "audio",
                    concepts=[],
                    entities=[],
                    novelty_flags=[],
                    confidence=0.0,
                    raw_meta={
                        "available": True,
                        "error": "could not understand audio",
                        "timestamp": time.time(),
                    },
                )
            except sr.RequestError as exc:
                return self._unified(
                    "audio",
                    concepts=[],
                    entities=[],
                    novelty_flags=[],
                    confidence=0.0,
                    raw_meta={
                        "available": True,
                        "error": f"STT service error: {exc}",
                        "timestamp": time.time(),
                    },
                )

            base = self.perceive_text(transcript)
            base["modality"] = "audio"
            base["confidence"] = min(0.85, float(base.get("confidence") or 0.0))
            meta = dict(base.get("raw_meta") or {})
            meta["source"] = "audio"
            meta["transcript"] = transcript
            meta["stt"] = "recognize_google"
            base["raw_meta"] = meta
            return base
        except sr.WaitTimeoutError:
            return self._unified(
                "audio",
                concepts=[],
                entities=[],
                novelty_flags=[],
                confidence=0.0,
                raw_meta={
                    "available": True,
                    "error": "no speech detected (timeout)",
                    "timestamp": time.time(),
                },
            )
        except Exception as exc:
            return self._unified(
                "audio",
                concepts=[],
                entities=[],
                novelty_flags=[],
                confidence=0.0,
                raw_meta={
                    "available": self.stt_available,
                    "error": f"audio capture failed: {exc}",
                    "timestamp": time.time(),
                },
            )

    def process_audio_input(self) -> Optional[Dict[str, Any]]:
        """Legacy helper — returns unified payload or None if unavailable."""
        if not self.stt_available:
            return None
        result = self.perceive_audio()
        if (result.get("raw_meta") or {}).get("error") and not result.get("text"):
            return None
        return result

    # ------------------------------------------------------------------
    # Vision channel — one frame when opencv+camera really available
    # ------------------------------------------------------------------

    def perceive_vision(self) -> Dict[str, Any]:
        """Capture one frame → honest features (faces/brightness). No fake captions."""
        if not self.vision_available or self._cv2 is None:
            return self._unified(
                "vision",
                concepts=[],
                entities=[],
                novelty_flags=[],
                confidence=0.0,
                raw_meta={
                    "available": False,
                    "reason": self._vision_reason,
                    "error": "vision perception disabled — device/libs unavailable",
                    "timestamp": time.time(),
                },
            )

        cv2 = self._cv2
        cap = None
        try:
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                self.vision_available = False
                self._vision_reason = "camera open failed on capture"
                return self._unified(
                    "vision",
                    concepts=[],
                    entities=[],
                    novelty_flags=[],
                    confidence=0.0,
                    raw_meta={
                        "available": False,
                        "error": "could not open camera",
                        "timestamp": time.time(),
                    },
                )
            ret, frame = cap.read()
            if not ret or frame is None:
                return self._unified(
                    "vision",
                    concepts=[],
                    entities=[],
                    novelty_flags=[],
                    confidence=0.0,
                    raw_meta={
                        "available": True,
                        "error": "could not read frame",
                        "timestamp": time.time(),
                    },
                )

            height, width = frame.shape[:2]
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            brightness = float(gray.mean())
            faces = 0
            try:
                cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
                face_cascade = cv2.CascadeClassifier(cascade_path)
                if not face_cascade.empty():
                    detected = face_cascade.detectMultiScale(gray, 1.1, 4)
                    faces = len(detected)
            except Exception:
                faces = 0

            if brightness < 50:
                bright_label = "dim"
            elif brightness > 200:
                bright_label = "bright"
            else:
                bright_label = "normal"

            concepts = [
                f"faces:{faces}",
                f"brightness:{bright_label}",
                f"resolution:{width}x{height}",
            ]
            novelty_flags: List[str] = []
            if faces > 0:
                novelty_flags.append(f"faces_detected:{faces}")
            if bright_label != "normal":
                novelty_flags.append(f"brightness_extreme:{bright_label}")

            return self._unified(
                "vision",
                # No fake caption/description text — features only.
                concepts=concepts,
                entities=[],
                novelty_flags=novelty_flags,
                confidence=0.7 if faces > 0 else 0.5,
                raw_meta={
                    "available": True,
                    "faces_detected": faces,
                    "brightness": brightness,
                    "brightness_label": bright_label,
                    "resolution": f"{width}x{height}",
                    "width": width,
                    "height": height,
                    "caption": None,  # stub not implemented — honest null
                    "source": "vision",
                    "timestamp": time.time(),
                },
            )
        except Exception as exc:
            return self._unified(
                "vision",
                concepts=[],
                entities=[],
                novelty_flags=[],
                confidence=0.0,
                raw_meta={
                    "available": self.vision_available,
                    "error": f"vision capture failed: {exc}",
                    "timestamp": time.time(),
                },
            )
        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass

    def process_visual_input(self) -> Optional[Dict[str, Any]]:
        if not self.vision_available:
            return None
        result = self.perceive_vision()
        if (result.get("raw_meta") or {}).get("error") and not result.get("concepts"):
            return None
        return result

    # ------------------------------------------------------------------
    # Status / messaging
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        return {
            "text": True,
            "text_input": True,
            "audio": bool(self.stt_available),
            "vision": bool(self.vision_available),
            "stt_available": bool(self.stt_available),
            "vision_available": bool(self.vision_available),
            "audio_enabled": bool(self.stt_available),
            "vision_enabled": bool(self.vision_available),
            "audio_reason": self._audio_reason,
            "vision_reason": self._vision_reason,
            "senses_online": {
                "text": True,
                "audio": bool(self.stt_available),
                "vision": bool(self.vision_available),
            },
            "claimed_modalities": [
                m
                for m, on in (
                    ("text", True),
                    ("audio", self.stt_available),
                    ("vision", self.vision_available),
                )
                if on
            ],
        }

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = message.get("type")
        payload = message.get("content", message)
        if not isinstance(payload, dict):
            payload = {}

        if msg_type == "health":
            return {"status": "success", "healthy": True, "pid": os.getpid()}

        if msg_type in ("perceive_text", "process_text", "user_input", "perceive"):
            text = payload.get("text") or payload.get("user_input") or ""
            result = self.perceive_text(text if isinstance(text, str) else "")
            # Live chat path expects text + entities at top level (unified already has them).
            result["normalized_text"] = result.get("text", "")
            result["words"] = list(result.get("concepts") or [])
            return {"status": "success", "content": result}

        if msg_type in ("perceive_audio", "listen_audio"):
            if not self.stt_available:
                return {
                    "status": "error",
                    "message": f"Audio perception disabled — {self._audio_reason}",
                    "content": self.perceive_audio(),
                }
            result = self.perceive_audio()
            err = (result.get("raw_meta") or {}).get("error")
            if err and not result.get("text"):
                return {"status": "error", "message": err, "content": result}
            return {"status": "success", "content": result}

        if msg_type in ("perceive_vision", "capture_visual"):
            if not self.vision_available:
                return {
                    "status": "error",
                    "message": f"Vision perception disabled — {self._vision_reason}",
                    "content": self.perceive_vision(),
                }
            result = self.perceive_vision()
            err = (result.get("raw_meta") or {}).get("error")
            if err and not result.get("concepts"):
                return {"status": "error", "message": err, "content": result}
            return {"status": "success", "content": result}

        if msg_type == "get_status":
            status = self.get_status()
            return {"status": "success", "content": status, **status}

        if msg_type == "sensory_data":
            # Thin fuse from SensoryIntegrationLobe — normalize strings into text.
            signals = payload.get("signals") or []
            fused: List[Dict[str, Any]] = []
            for sig in signals:
                if isinstance(sig, str) and sig.strip():
                    fused.append(self.perceive_text(sig))
                elif isinstance(sig, dict) and sig.get("text"):
                    fused.append(self.perceive_text(str(sig["text"])))
            return {"status": "success", "content": {"fused": fused, "count": len(fused)}}

        return {"status": "error", "message": f"Unknown message type: {msg_type}"}

    def start(self) -> None:
        """CLI helper — register and idle. No hearing/vision theater threads."""
        senses = self.get_status()["senses_online"]
        print(
            "Perception Lobe: "
            f"text={'online' if senses['text'] else 'off'} "
            f"audio={'online' if senses['audio'] else 'disabled'} "
            f"vision={'online' if senses['vision'] else 'disabled'}"
        )
        if not senses["audio"]:
            print(f"  audio: {self._audio_reason}")
        if not senses["vision"]:
            print(f"  vision: {self._vision_reason}")
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
