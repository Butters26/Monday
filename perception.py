#!/usr/bin/env python3
"""Perception Lobe — senses → concepts/entities/novelty → thalamus.

Modalities (design):
  - text: always online (normalize + extract concepts/entities)
  - hearing/audio: real acoustic + semantic STT (whisper/vosk/google) from mic OR file/bytes
  - vision: real low-level features + optional BLIP generative caption (CLIP supplemental only) from camera OR file/bytes

Hardware mic/webcam are probed honestly and never claimed live unless
device open succeeds. File/buffer paths are first-class sensory intake
so the lobe still perceives when hardware is absent.
"""

from __future__ import annotations

import io
import os
import re
import tempfile
import time
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import numpy as np

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

PathLike = Union[str, Path]
AudioSource = Union[PathLike, bytes, bytearray, memoryview]
ImageSource = Union[PathLike, bytes, bytearray, memoryview]


class PerceptionLobe:
    """Multi-modal perception with honest capability probing + file intake."""

    TEXT_ENABLED = True

    def __init__(self, thalamus=None, probe_devices: bool = True) -> None:
        self.thalamus = thalamus if thalamus is not None else get_thalamus()
        self.running = True
        self.seen_concepts: Set[str] = set()
        self.seen_entities: Set[str] = set()

        # Hardware live flags (mic / camera) — never set without real open.
        self.stt_available = False
        self.vision_available = False
        self.stt_engine = None
        self._audio_reason = "not probed"
        self._vision_reason = "not probed"
        self._sr_module = None
        self._cv2 = None
        self._pil = None

        # File/buffer processing flags (independent of hardware).
        self.audio_file_available = False
        self.vision_file_available = False
        self._audio_file_reason = "not probed"
        self._vision_file_reason = "not probed"

        # Semantic backends (file STT + visual inference) — independent of mic/camera.
        self.semantic_stt_available = False
        self.stt_backend = None  # whisper | vosk | google | None
        self._stt_backend_reason = "not probed"
        self._whisper_model = None
        self._whisper_module = None
        self._vosk_model = None
        self.semantic_vision_available = False
        self.vision_semantic_backend = None  # blip | None
        self._vision_semantic_reason = "not probed"
        self._blip_model = None
        self._blip_processor = None
        self._blip_torch = None
        self._blip_model_cls = None
        self._blip_processor_cls = None
        # Optional CLIP supplemental classifier (never sole semantic source / never a caption).
        self._clip_model = None
        self._clip_processor = None
        self._clip_torch = None
        self._clip_model_cls = None
        self._clip_processor_cls = None
        self._clip_supplemental_available = False

        self._probe_processing_libs()
        if probe_devices:
            self._probe_audio()
            self._probe_vision()

    # ------------------------------------------------------------------
    # Honest capability probes
    # ------------------------------------------------------------------

    def _probe_processing_libs(self) -> None:
        """File/buffer processing does not require mic/camera hardware."""
        # Audio file path: stdlib wave + numpy is enough for real acoustics.
        self.audio_file_available = True
        self._audio_file_reason = "wave+numpy acoustic processing online"
        try:
            import speech_recognition as sr  # type: ignore
            self._sr_module = sr
            if self.stt_engine is None:
                self.stt_engine = sr.Recognizer()
        except ImportError:
            # STT optional; acoustic path still real.
            pass

        self._probe_semantic_stt()

        try:
            import cv2  # type: ignore
            self._cv2 = cv2
            self.vision_file_available = True
            self._vision_file_reason = "opencv image-file processing online"
        except ImportError:
            self._cv2 = None
            try:
                from PIL import Image  # type: ignore
                self._pil = Image
                self.vision_file_available = True
                self._vision_file_reason = "PIL image-file processing online"
            except ImportError:
                self._pil = None
                self.vision_file_available = False
                self._vision_file_reason = "opencv/PIL not installed"

        self._probe_semantic_vision()

    def _probe_semantic_stt(self) -> None:
        """Prefer offline whisper, then vosk, then speech_recognition google."""
        # openai-whisper
        try:
            import whisper  # type: ignore
            self._whisper_module = whisper
            # Defer model load until first use (CPU tiny is ~75MB).
            self.semantic_stt_available = True
            self.stt_backend = "whisper"
            self._stt_backend_reason = "openai-whisper available (model=tiny, loaded on first STT)"
            return
        except ImportError:
            self._whisper_module = None

        # vosk offline
        try:
            from vosk import Model as VoskModel  # type: ignore
            import json as _json  # noqa: F401
            model_dir = os.environ.get("MONDAY_VOSK_MODEL")
            candidates = []
            if model_dir:
                candidates.append(model_dir)
            candidates.extend(
                [
                    "/workspace/Monday/models/vosk-model-small-en-us-0.15",
                    str(Path.home() / "vosk-model-small-en-us-0.15"),
                    "/usr/share/vosk/models/vosk-model-small-en-us-0.15",
                ]
            )
            for c in candidates:
                if c and os.path.isdir(c):
                    self._vosk_model = VoskModel(c)
                    self.semantic_stt_available = True
                    self.stt_backend = "vosk"
                    self._stt_backend_reason = f"vosk model online at {c}"
                    return
            # vosk installed but no model yet
            self._stt_backend_reason = "vosk installed but no model directory found"
        except ImportError:
            pass

        if self._sr_module is not None:
            self.semantic_stt_available = True
            self.stt_backend = "google"
            self._stt_backend_reason = "speech_recognition recognize_google (network)"
            return

        self.semantic_stt_available = False
        self.stt_backend = None
        self._stt_backend_reason = "no STT backend (whisper/vosk/speech_recognition)"

    def _probe_semantic_vision(self) -> None:
        """BLIP generative captioning primary; CLIP optional supplemental only.

        CLIP candidate labels never define possible captions. Lazy-load weights
        on first use. Honest degrade when transformers/torch unavailable.
        """
        try:
            import torch  # type: ignore
            from transformers import (  # type: ignore
                BlipForConditionalGeneration,
                BlipProcessor,
            )
            self._blip_torch = torch
            self._blip_model_cls = BlipForConditionalGeneration
            self._blip_processor_cls = BlipProcessor
            self.semantic_vision_available = True
            self.vision_semantic_backend = "blip"
            self._vision_semantic_reason = (
                "transformers BLIP Salesforce/blip-image-captioning-base "
                "(lazy load, CPU; generative caption)"
            )
        except ImportError as exc:
            self.semantic_vision_available = False
            self.vision_semantic_backend = None
            self._blip_model_cls = None
            self._blip_processor_cls = None
            self._vision_semantic_reason = f"BLIP unavailable: {exc}"

        # Supplemental zero-shot classifier — broad general labels only.
        try:
            import torch  # type: ignore
            from transformers import CLIPModel, CLIPProcessor  # type: ignore
            self._clip_torch = torch
            self._clip_model_cls = CLIPModel
            self._clip_processor_cls = CLIPProcessor
            self._clip_supplemental_available = True
        except ImportError:
            self._clip_model_cls = None
            self._clip_processor_cls = None
            self._clip_supplemental_available = False

    def _probe_audio(self) -> None:
        """Mark mic online only if speech_recognition + mic open succeed."""
        if self._sr_module is None:
            try:
                import speech_recognition as sr  # type: ignore
                self._sr_module = sr
            except ImportError:
                self.stt_available = False
                self.stt_engine = None
                self._audio_reason = "speech_recognition not installed (mic STT offline; file acoustics still online)"
                return

        sr = self._sr_module
        try:
            recognizer = sr.Recognizer()
            mic = sr.Microphone()
            with mic as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.1)
            self.stt_engine = recognizer
            self.stt_available = True
            self._audio_reason = "microphone open succeeded"
            print("Perception: microphone open succeeded — live mic online")
        except Exception as exc:
            self.stt_available = False
            if self.stt_engine is None:
                self.stt_engine = sr.Recognizer()
            self._audio_reason = f"microphone unavailable: {exc}"

    def _probe_vision(self) -> None:
        """Mark camera online only if opencv + camera open + frame succeed."""
        if self._cv2 is None:
            try:
                import cv2  # type: ignore
                self._cv2 = cv2
            except ImportError:
                self.vision_available = False
                self._vision_reason = "opencv not installed (camera offline; file vision may still work via PIL)"
                return

        cv2 = self._cv2
        cap = None
        try:
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                self.vision_available = False
                self._vision_reason = "camera index 0 not openable"
                return
            ret, frame = cap.read()
            if not ret or frame is None:
                self.vision_available = False
                self._vision_reason = "camera opened but no frame"
                return
            self.vision_available = True
            self._vision_reason = "camera open + frame succeeded"
            print("Perception: camera open succeeded — live vision online")
        except Exception as exc:
            self.vision_available = False
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

    def process_text_input(self, text: str) -> Dict[str, Any]:
        result = self.perceive_text(text)
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
    # Audio helpers — real acoustic analysis from WAV samples
    # ------------------------------------------------------------------

    def _resolve_wav_path(
        self, path: Optional[PathLike] = None, audio_bytes: Optional[bytes] = None
    ) -> Tuple[str, Optional[str]]:
        """Return (wav_path, temp_path_to_cleanup_or_None)."""
        if path is not None:
            p = str(path)
            if not os.path.isfile(p):
                raise FileNotFoundError(f"audio file not found: {p}")
            return p, None
        if audio_bytes is not None:
            raw = bytes(audio_bytes)
            fd, tmp = tempfile.mkstemp(suffix=".wav", prefix="monday_perc_aud_")
            os.close(fd)
            with open(tmp, "wb") as fh:
                fh.write(raw)
            return tmp, tmp
        raise ValueError("audio path or bytes required")

    def _load_wav_mono(self, wav_path: str) -> Tuple[np.ndarray, int, Dict[str, Any]]:
        with wave.open(wav_path, "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)

        if sampwidth == 1:
            data = np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0
            data /= 128.0
        elif sampwidth == 2:
            data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        elif sampwidth == 4:
            data = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
        else:
            raise ValueError(f"unsupported sample width: {sampwidth}")

        if n_channels > 1:
            data = data.reshape(-1, n_channels).mean(axis=1)

        meta = {
            "channels": n_channels,
            "sampwidth": sampwidth,
            "sample_rate": framerate,
            "n_frames": n_frames,
            "duration_sec": float(n_frames) / float(framerate) if framerate else 0.0,
        }
        return data, framerate, meta

    def _analyze_acoustics(self, samples: np.ndarray, sample_rate: int) -> Dict[str, Any]:
        if samples.size == 0:
            return {
                "rms": 0.0,
                "peak": 0.0,
                "zcr": 0.0,
                "spectral_centroid_hz": 0.0,
                "loudness": "silent",
                "speech_like": False,
                "energy_variance": 0.0,
            }

        rms = float(np.sqrt(np.mean(np.square(samples))))
        peak = float(np.max(np.abs(samples)))
        # Zero-crossing rate
        signs = np.sign(samples)
        signs[signs == 0] = 1
        zcr = float(np.mean(signs[:-1] != signs[1:])) if samples.size > 1 else 0.0

        # Spectral centroid (magnitude-weighted mean frequency)
        windowed = samples * np.hanning(samples.size)
        spectrum = np.abs(np.fft.rfft(windowed))
        freqs = np.fft.rfftfreq(samples.size, d=1.0 / float(sample_rate or 1))
        mag_sum = float(np.sum(spectrum)) + 1e-12
        centroid = float(np.sum(freqs * spectrum) / mag_sum)

        # Frame energy variance — speech tends to vary more than steady tones
        frame = max(1, int(0.02 * (sample_rate or 16000)))
        if samples.size >= frame * 2:
            n = (samples.size // frame) * frame
            frames = samples[:n].reshape(-1, frame)
            energies = np.mean(np.square(frames), axis=1)
            energy_var = float(np.var(energies))
        else:
            energy_var = 0.0

        if rms < 0.005:
            loudness = "silent"
        elif rms < 0.02:
            loudness = "quiet"
        elif rms < 0.15:
            loudness = "moderate"
        else:
            loudness = "loud"

        # Heuristic: mid ZCR + energy variance suggests speech-like signal
        speech_like = bool(0.02 < zcr < 0.35 and energy_var > 1e-6 and rms > 0.008)

        return {
            "rms": rms,
            "peak": peak,
            "zcr": zcr,
            "spectral_centroid_hz": centroid,
            "loudness": loudness,
            "speech_like": speech_like,
            "energy_variance": energy_var,
        }

    def _ensure_whisper(self) -> Optional[Any]:
        if self._whisper_model is not None:
            return self._whisper_model
        if self._whisper_module is None:
            return None
        try:
            # tiny = offline, CPU-friendly, real STT on audio bytes
            self._whisper_model = self._whisper_module.load_model("tiny")
            return self._whisper_model
        except Exception:
            return None

    def _stt_whisper(self, wav_path: str) -> Tuple[Optional[str], Optional[str]]:
        model = self._ensure_whisper()
        if model is None:
            return None, "whisper model load failed"
        try:
            result = model.transcribe(wav_path, fp16=False, language="en")
            text = (result or {}).get("text")
            if isinstance(text, str):
                text = text.strip()
            if text:
                return text, None
            return None, "whisper returned empty transcript"
        except Exception as exc:
            return None, f"whisper STT failed: {exc}"

    def _stt_vosk(self, wav_path: str) -> Tuple[Optional[str], Optional[str]]:
        if self._vosk_model is None:
            return None, "vosk model not loaded"
        try:
            from vosk import KaldiRecognizer  # type: ignore
            import json as _json
            samples, rate, _meta = self._load_wav_mono(wav_path)
            # vosk wants 16-bit PCM bytes at model rate (usually 16k)
            if rate != 16000:
                # naive resample
                duration = samples.size / float(rate or 1)
                new_n = max(1, int(duration * 16000))
                idx = (np.linspace(0, samples.size - 1, new_n)).astype(np.int64)
                samples = samples[idx]
                rate = 16000
            pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()
            rec = KaldiRecognizer(self._vosk_model, rate)
            rec.AcceptWaveform(pcm)
            final = _json.loads(rec.FinalResult() or "{}")
            text = (final.get("text") or "").strip()
            if text:
                return text, None
            return None, "vosk could not understand audio"
        except Exception as exc:
            return None, f"vosk STT failed: {exc}"

    def _stt_google(self, wav_path: str) -> Tuple[Optional[str], Optional[str]]:
        if self._sr_module is None:
            return None, "speech_recognition not installed"
        if self.stt_engine is None:
            self.stt_engine = self._sr_module.Recognizer()
        sr = self._sr_module
        try:
            with sr.AudioFile(wav_path) as source:
                audio = self.stt_engine.record(source)
            try:
                transcript = self.stt_engine.recognize_google(audio)
                return (transcript if isinstance(transcript, str) else str(transcript)), None
            except sr.UnknownValueError:
                return None, "could not understand audio"
            except sr.RequestError as exc:
                return None, f"STT service error: {exc}"
        except Exception as exc:
            return None, f"STT from file failed: {exc}"

    def _stt_from_wav(self, wav_path: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Run real STT on audio bytes. Returns (transcript, error, engine).

        Prefer offline whisper, then vosk, then network google. Acoustics are
        unaffected when STT fails — caller keeps acoustic-only envelope.
        """
        engines: List[Tuple[str, Any]] = []
        if self.stt_backend == "whisper" or self._whisper_module is not None:
            engines.append(("whisper", self._stt_whisper))
        if self.stt_backend == "vosk" or self._vosk_model is not None:
            engines.append(("vosk", self._stt_vosk))
        if self._sr_module is not None:
            engines.append(("google", self._stt_google))

        # Deduplicate while preserving order
        seen = set()
        ordered = []
        for name, fn in engines:
            if name not in seen:
                seen.add(name)
                ordered.append((name, fn))

        if not ordered:
            return None, "no STT backend available", None

        errors: List[str] = []
        for name, fn in ordered:
            transcript, err = fn(wav_path)
            if transcript:
                return transcript, None, name
            errors.append(f"{name}: {err or 'failed'}")
        return None, "; ".join(errors), None

    def _envelope_from_acoustics(
        self,
        acoustics: Dict[str, Any],
        wav_meta: Dict[str, Any],
        *,
        transcript: Optional[str] = None,
        stt_error: Optional[str] = None,
        stt_engine: Optional[str] = None,
        intake: str = "file",
        source_label: str = "audio_file",
    ) -> Dict[str, Any]:
        # Acoustic descriptors always present (low-level hearing).
        acoustic_concepts = [
            f"loudness:{acoustics['loudness']}",
            f"duration:{wav_meta['duration_sec']:.2f}s",
            f"sr:{wav_meta['sample_rate']}",
        ]
        if acoustics["speech_like"]:
            acoustic_concepts.append("speech_like:true")
        else:
            acoustic_concepts.append("speech_like:false")
        acoustic_concepts.append(f"centroid:{acoustics['spectral_centroid_hz']:.0f}hz")

        novelty_flags: List[str] = []
        if acoustics["loudness"] in ("loud", "silent"):
            novelty_flags.append(f"loudness_extreme:{acoustics['loudness']}")
        if acoustics["speech_like"]:
            novelty_flags.append("speech_like_signal")

        entities: List[str] = []
        text_out: Optional[str] = None
        confidence = 0.55
        semantic_concepts: List[str] = []

        if transcript:
            # Reuse text semantic extraction — no second NLP system.
            base = self.perceive_text(transcript)
            text_out = base.get("text")
            semantic_concepts = list(base.get("concepts") or [])
            entities = list(base.get("entities") or [])
            novelty_flags = list(dict.fromkeys(
                list(base.get("novelty_flags") or []) + novelty_flags
            ))
            confidence = min(0.95, max(0.75, float(base.get("confidence") or 0.75)))
            meta_extra = dict(base.get("raw_meta") or {})
        else:
            meta_extra = {}
            if stt_error:
                novelty_flags.append("stt_unavailable_or_failed")

        # Unified concept list: acoustic + linguistic (linguistic first when present
        # so downstream Attention/Conversation see what was said).
        if semantic_concepts:
            concepts = semantic_concepts + [c for c in acoustic_concepts if c not in semantic_concepts]
        else:
            concepts = acoustic_concepts

        raw_meta = {
            **meta_extra,
            "available": True,
            "intake": intake,
            "source": source_label,
            "acoustics": acoustics,
            "wav": wav_meta,
            "transcript": transcript,
            "stt_error": stt_error,
            "stt": stt_engine if transcript else None,
            "stt_backend_preferred": self.stt_backend,
            "semantic_stt_available": bool(self.semantic_stt_available),
            "mic_live": bool(self.stt_available),
            "timestamp": time.time(),
        }
        out = self._unified(
            "audio",
            text=text_out,
            concepts=concepts,
            entities=entities,
            novelty_flags=novelty_flags,
            confidence=confidence,
            raw_meta=raw_meta,
        )
        if transcript:
            out["transcript"] = transcript
        return out

    # ------------------------------------------------------------------
    # Audio channel — file/bytes (always when wave works) + optional mic
    # ------------------------------------------------------------------

    def perceive_audio(
        self,
        path: Optional[PathLike] = None,
        audio_bytes: Optional[bytes] = None,
        *,
        use_mic: bool = False,
        try_stt: bool = True,
    ) -> Dict[str, Any]:
        """Perceive hearing input from file/bytes, or live mic when requested.

        File/buffer acoustic analysis is real processing (RMS/ZCR/centroid).
        Optional STT enriches with transcript when speech_recognition works.
        Live mic is only used when use_mic=True and hardware probe succeeded.
        """
        if path is not None or audio_bytes is not None:
            return self._perceive_audio_file(
                path=path, audio_bytes=audio_bytes, try_stt=try_stt
            )

        if use_mic or (path is None and audio_bytes is None):
            # Legacy no-arg call = try mic; degrade honestly if unavailable.
            return self._perceive_audio_mic()

        return self._unified(
            "audio",
            confidence=0.0,
            raw_meta={
                "available": False,
                "error": "no audio source provided",
                "timestamp": time.time(),
            },
        )

    def _perceive_audio_file(
        self,
        path: Optional[PathLike] = None,
        audio_bytes: Optional[bytes] = None,
        try_stt: bool = True,
    ) -> Dict[str, Any]:
        if not self.audio_file_available:
            return self._unified(
                "audio",
                confidence=0.0,
                raw_meta={
                    "available": False,
                    "reason": self._audio_file_reason,
                    "error": "audio file perception disabled",
                    "timestamp": time.time(),
                },
            )

        tmp: Optional[str] = None
        try:
            wav_path, tmp = self._resolve_wav_path(path=path, audio_bytes=audio_bytes)
            # If non-wav, try ffmpeg → wav via tempfile
            if not wav_path.lower().endswith(".wav"):
                wav_path, tmp2 = self._ffmpeg_to_wav(wav_path)
                if tmp:
                    try:
                        os.unlink(tmp)
                    except Exception:
                        pass
                tmp = tmp2

            samples, sr, wav_meta = self._load_wav_mono(wav_path)
            acoustics = self._analyze_acoustics(samples, sr)
            transcript = None
            stt_error = None
            stt_engine_used = None
            if try_stt:
                transcript, stt_error, stt_engine_used = self._stt_from_wav(wav_path)
            return self._envelope_from_acoustics(
                acoustics,
                wav_meta,
                transcript=transcript,
                stt_error=stt_error,
                stt_engine=stt_engine_used,
                intake="file",
                source_label="audio_file",
            )
        except Exception as exc:
            return self._unified(
                "audio",
                confidence=0.0,
                raw_meta={
                    "available": True,
                    "intake": "file",
                    "error": f"audio file processing failed: {exc}",
                    "timestamp": time.time(),
                },
            )
        finally:
            if tmp and os.path.isfile(tmp):
                try:
                    os.unlink(tmp)
                except Exception:
                    pass

    def _ffmpeg_to_wav(self, src_path: str) -> Tuple[str, str]:
        import subprocess
        fd, tmp = tempfile.mkstemp(suffix=".wav", prefix="monday_perc_ff_")
        os.close(fd)
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", src_path,
                    "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", tmp,
                ],
                check=True,
                capture_output=True,
                timeout=60,
            )
            return tmp, tmp
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise

    def _perceive_audio_mic(self) -> Dict[str, Any]:
        if not self.stt_available or self.stt_engine is None or self._sr_module is None:
            return self._unified(
                "audio",
                concepts=[],
                entities=[],
                novelty_flags=[],
                confidence=0.0,
                raw_meta={
                    "available": False,
                    "intake": "mic",
                    "reason": self._audio_reason,
                    "error": "live mic perception disabled — device unavailable",
                    "audio_file_available": bool(self.audio_file_available),
                    "hint": "pass path= or audio_bytes= for file-based hearing",
                    "timestamp": time.time(),
                },
            )

        sr = self._sr_module
        try:
            with sr.Microphone() as source:
                self.stt_engine.adjust_for_ambient_noise(source, duration=0.3)
                audio = self.stt_engine.listen(source, timeout=5, phrase_time_limit=10)
            # Persist to temp wav for acoustic analysis + STT
            fd, tmp = tempfile.mkstemp(suffix=".wav", prefix="monday_perc_mic_")
            os.close(fd)
            try:
                with open(tmp, "wb") as fh:
                    fh.write(audio.get_wav_data())
                samples, rate, wav_meta = self._load_wav_mono(tmp)
                acoustics = self._analyze_acoustics(samples, rate)
                transcript = None
                stt_error = None
                try:
                    transcript = self.stt_engine.recognize_google(audio)
                except sr.UnknownValueError:
                    stt_error = "could not understand audio"
                except sr.RequestError as exc:
                    stt_error = f"STT service error: {exc}"
                return self._envelope_from_acoustics(
                    acoustics,
                    wav_meta,
                    transcript=transcript if isinstance(transcript, str) else None,
                    stt_error=stt_error,
                    stt_engine="google" if transcript else None,
                    intake="mic",
                    source_label="audio_mic",
                )
            finally:
                try:
                    os.unlink(tmp)
                except Exception:
                    pass
        except sr.WaitTimeoutError:
            return self._unified(
                "audio",
                confidence=0.0,
                raw_meta={
                    "available": True,
                    "intake": "mic",
                    "error": "no speech detected (timeout)",
                    "timestamp": time.time(),
                },
            )
        except Exception as exc:
            return self._unified(
                "audio",
                confidence=0.0,
                raw_meta={
                    "available": self.stt_available,
                    "intake": "mic",
                    "error": f"audio capture failed: {exc}",
                    "timestamp": time.time(),
                },
            )

    def process_audio_input(
        self,
        path: Optional[PathLike] = None,
        audio_bytes: Optional[bytes] = None,
    ) -> Optional[Dict[str, Any]]:
        """Legacy helper — file if given, else mic; None on hard failure."""
        if path is not None or audio_bytes is not None:
            result = self.perceive_audio(path=path, audio_bytes=audio_bytes)
        elif not self.stt_available and not self.audio_file_available:
            return None
        else:
            result = self.perceive_audio()
        if (result.get("raw_meta") or {}).get("error") and not result.get("concepts"):
            return None
        return result

    # ------------------------------------------------------------------
    # Vision helpers — real features from ndarray BGR/RGB frames
    # ------------------------------------------------------------------

    def _load_image_bgr(
        self, path: Optional[PathLike] = None, image_bytes: Optional[bytes] = None
    ) -> Tuple[Any, Dict[str, Any]]:
        meta: Dict[str, Any] = {"intake": "file"}
        if path is not None:
            p = str(path)
            if not os.path.isfile(p):
                raise FileNotFoundError(f"image file not found: {p}")
            meta["path"] = p
            if self._cv2 is not None:
                frame = self._cv2.imread(p)
                if frame is None:
                    raise ValueError(f"opencv could not decode image: {p}")
                return frame, meta
            if self._pil is not None:
                from PIL import Image
                img = Image.open(p).convert("RGB")
                arr = np.array(img)
                # RGB → BGR for shared feature path
                return arr[:, :, ::-1].copy(), meta
            raise RuntimeError("no image decoder available")

        if image_bytes is not None:
            raw = bytes(image_bytes)
            meta["nbytes"] = len(raw)
            if self._cv2 is not None:
                buf = np.frombuffer(raw, dtype=np.uint8)
                frame = self._cv2.imdecode(buf, self._cv2.IMREAD_COLOR)
                if frame is None:
                    raise ValueError("opencv could not decode image bytes")
                return frame, meta
            if self._pil is not None:
                from PIL import Image
                img = Image.open(io.BytesIO(raw)).convert("RGB")
                arr = np.array(img)
                return arr[:, :, ::-1].copy(), meta
            raise RuntimeError("no image decoder available")

        raise ValueError("image path or bytes required")

    def _analyze_frame(self, frame: Any) -> Dict[str, Any]:
        """Real vision features: brightness, faces, edges, color stats."""
        height, width = frame.shape[:2]
        if self._cv2 is not None:
            cv2 = self._cv2
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            brightness = float(gray.mean())
            # Edge density via Canny
            edges = cv2.Canny(gray, 80, 160)
            edge_density = float(np.mean(edges > 0))
            faces = 0
            try:
                cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
                face_cascade = cv2.CascadeClassifier(cascade_path)
                if not face_cascade.empty():
                    detected = face_cascade.detectMultiScale(gray, 1.1, 4)
                    faces = int(len(detected))
            except Exception:
                faces = 0
            # Simple dominant channel
            means = frame.reshape(-1, 3).mean(axis=0)  # BGR
            dominant = ("blue", "green", "red")[int(np.argmax(means))]
            colorfulness = float(np.std(frame.reshape(-1, 3), axis=0).mean())
        else:
            # PIL-loaded frame still BGR ndarray here
            gray = frame.mean(axis=2)
            brightness = float(gray.mean())
            # Sobel-ish edge proxy
            gy, gx = np.gradient(gray.astype(np.float32))
            edge_density = float(np.mean(np.hypot(gx, gy) > 20.0))
            faces = 0
            means = frame.reshape(-1, 3).mean(axis=0)
            dominant = ("blue", "green", "red")[int(np.argmax(means))]
            colorfulness = float(np.std(frame.reshape(-1, 3), axis=0).mean())

        if brightness < 50:
            bright_label = "dim"
        elif brightness > 200:
            bright_label = "bright"
        else:
            bright_label = "normal"

        if edge_density < 0.02:
            complexity = "flat"
        elif edge_density < 0.08:
            complexity = "moderate"
        else:
            complexity = "busy"

        return {
            "width": int(width),
            "height": int(height),
            "brightness": brightness,
            "brightness_label": bright_label,
            "faces_detected": faces,
            "edge_density": edge_density,
            "complexity": complexity,
            "dominant_channel": dominant,
            "colorfulness": colorfulness,
            "resolution": f"{width}x{height}",
        }

    # Supplemental CLIP labels ONLY — broad open vocabulary, NOT a caption source.
    # Must never include upcoming proof-image descriptions or fixture-tailored phrases.
    # Selected CLIP labels are classifier hints, never treated as generated captions.
    _CLIP_SUPPLEMENTAL_LABELS = (
        "person",
        "animal",
        "vehicle",
        "building",
        "furniture",
        "food",
        "plant",
        "water",
        "sky",
        "ground",
        "indoor scene",
        "outdoor scene",
        "text or sign",
        "electronic device",
        "tool or utensil",
        "clothing",
        "sports equipment",
        "abstract pattern",
        "empty surface",
        "crowd of people",
    )

    # Prior fixture-tailored CLIP answer phrases have been deleted; CLIP is
    # supplemental only and cannot be the sole semantic path.

    def _ensure_blip(self) -> bool:
        if self._blip_model is not None and self._blip_processor is not None:
            return True
        if not self.semantic_vision_available:
            return False
        cls_m = getattr(self, "_blip_model_cls", None)
        cls_p = getattr(self, "_blip_processor_cls", None)
        if cls_m is None or cls_p is None:
            return False
        try:
            name = "Salesforce/blip-image-captioning-base"
            self._blip_processor = cls_p.from_pretrained(name)
            self._blip_model = cls_m.from_pretrained(name)
            self._blip_model.eval()
            return True
        except Exception as exc:
            self.semantic_vision_available = False
            self._vision_semantic_reason = f"BLIP load failed: {exc}"
            return False

    def _ensure_clip(self) -> bool:
        """Optional supplemental CLIP — never required for semantic vision."""
        if self._clip_model is not None and self._clip_processor is not None:
            return True
        if not getattr(self, "_clip_supplemental_available", False):
            return False
        cls_m = getattr(self, "_clip_model_cls", None)
        cls_p = getattr(self, "_clip_processor_cls", None)
        if cls_m is None or cls_p is None:
            return False
        try:
            name = "openai/clip-vit-base-patch32"
            self._clip_processor = cls_p.from_pretrained(name)
            self._clip_model = cls_m.from_pretrained(name)
            self._clip_model.eval()
            return True
        except Exception:
            self._clip_supplemental_available = False
            return False

    def _clip_supplemental_classify(self, img: Any) -> Dict[str, Any]:
        """Broad-vocab CLIP hints only. Never invents a caption."""
        result: Dict[str, Any] = {"scores": [], "labels": [], "confidence": 0.0}
        if not self._ensure_clip():
            return result
        try:
            torch = self._clip_torch
            labels = list(self._CLIP_SUPPLEMENTAL_LABELS)
            inputs = self._clip_processor(
                text=labels, images=img, return_tensors="pt", padding=True
            )
            with torch.no_grad():
                logits = self._clip_model(**inputs).logits_per_image[0]
                probs = logits.softmax(dim=0).tolist()
            ranked = sorted(zip(labels, probs), key=lambda x: -x[1])
            top_p = float(ranked[0][1]) if ranked else 0.0
            second_p = float(ranked[1][1]) if len(ranked) > 1 else 0.0
            result["scores"] = [
                {"label": lab, "score": float(p)} for lab, p in ranked[:5]
            ]
            result["confidence"] = top_p
            # Only surface labels with clear margin — supplemental hints.
            if top_p >= 0.20 and (top_p - second_p) >= 0.04:
                result["labels"] = [
                    lab
                    for lab, p in ranked
                    if p >= max(0.12, top_p * 0.40) and p >= 0.10
                ][:4]
            return result
        except Exception:
            return result

    def _semantic_vision_infer(self, frame: Any) -> Dict[str, Any]:
        """Generative visual semantics via BLIP image captioning.

        Caption is model-generated free text — NOT selection from a candidate
        list. CLIP may add supplemental class hints only. Honest degradation
        when model unavailable or low-confidence; never invents objects.
        """
        out: Dict[str, Any] = {
            "available": False,
            "backend": self.vision_semantic_backend,
            "caption": None,
            "objects": [],
            "scene": None,
            "scores": [],
            "confidence": 0.0,
            "error": None,
            "clip_supplemental": None,
        }
        if not self.semantic_vision_available:
            out["error"] = self._vision_semantic_reason or "semantic vision unavailable"
            return out
        if not self._ensure_blip():
            out["error"] = self._vision_semantic_reason or "BLIP not loaded"
            return out

        try:
            from PIL import Image
            torch = self._blip_torch
            rgb = frame[:, :, ::-1].copy()
            img = Image.fromarray(rgb.astype(np.uint8)).convert("RGB")

            inputs = self._blip_processor(images=img, return_tensors="pt")
            with torch.no_grad():
                generated = self._blip_model.generate(
                    **inputs,
                    max_new_tokens=30,
                    num_beams=3,
                    return_dict_in_generate=True,
                    output_scores=True,
                )
            seq = generated.sequences[0]
            caption = self._blip_processor.decode(seq, skip_special_tokens=True)
            caption = (caption or "").strip()
            # Strip common BLIP prompt echo if present.
            for prefix in ("a photography of ", "a photo of ", "an image of "):
                if caption.lower().startswith(prefix):
                    caption = caption[len(prefix):].strip()
                    break

            # Mean max-token probability as generative confidence.
            token_probs: List[float] = []
            if getattr(generated, "scores", None):
                for step_logits in generated.scores:
                    probs = torch.softmax(step_logits[0], dim=-1)
                    token_probs.append(float(probs.max().item()))
            mean_tp = float(sum(token_probs) / len(token_probs)) if token_probs else 0.0
            # Beam sequences: also consider relative sequence score when present.
            seq_score = None
            if getattr(generated, "sequences_scores", None) is not None:
                try:
                    seq_score = float(generated.sequences_scores[0].item())
                except Exception:
                    seq_score = None

            # Reject empty / trivial captions; require solid token confidence.
            confident = bool(
                caption
                and len(caption.split()) >= 2
                and mean_tp >= 0.42
            )

            out["available"] = True
            out["backend"] = "blip"
            out["confidence"] = mean_tp
            out["scores"] = [
                {"token_mean_prob": mean_tp, "seq_score": seq_score, "caption_preview": caption[:80]}
            ]

            # Supplemental CLIP — classifier hints only, never becomes caption.
            clip_sup = self._clip_supplemental_classify(img)
            out["clip_supplemental"] = {
                "labels": list(clip_sup.get("labels") or []),
                "scores": list(clip_sup.get("scores") or [])[:5],
                "confidence": float(clip_sup.get("confidence") or 0.0),
            }

            if not confident:
                out["error"] = (
                    f"semantic vision low confidence "
                    f"(token_mean_prob={mean_tp:.3f}); no caption invented"
                )
                out["caption"] = None
                out["objects"] = []
                out["scene"] = None
                return out

            out["caption"] = caption
            out["scene"] = caption
            # Objects: content words from caption + optional CLIP supplemental labels.
            words = [
                w.strip(_PUNCT_STRIP).lower()
                for w in caption.split()
                if len(w.strip(_PUNCT_STRIP)) > 2
            ]
            stop = {
                "the", "and", "with", "from", "that", "this", "are", "was",
                "for", "its", "his", "her", "their", "onto", "into", "over",
                "under", "near", "beside", "there", "here", "some", "many",
            }
            obj_from_cap = [w for w in words if w not in stop][:8]
            clip_labels = list(clip_sup.get("labels") or [])
            objects = list(dict.fromkeys(obj_from_cap + clip_labels))
            out["objects"] = objects
            return out
        except Exception as exc:
            out["error"] = f"semantic vision inference failed: {exc}"
            return out

    def _envelope_from_vision(
        self,
        features: Dict[str, Any],
        *,
        intake: str = "file",
        source_label: str = "vision_file",
        extra_meta: Optional[Dict[str, Any]] = None,
        semantic: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        low_level = [
            f"faces:{features['faces_detected']}",
            f"brightness:{features['brightness_label']}",
            f"resolution:{features['resolution']}",
            f"complexity:{features['complexity']}",
            f"dominant:{features['dominant_channel']}",
        ]
        novelty_flags: List[str] = []
        if features["faces_detected"] > 0:
            novelty_flags.append(f"faces_detected:{features['faces_detected']}")
        if features["brightness_label"] != "normal":
            novelty_flags.append(f"brightness_extreme:{features['brightness_label']}")
        if features["complexity"] == "busy":
            novelty_flags.append("visual_complexity:busy")

        semantic = semantic or {}
        caption = semantic.get("caption")
        objects = list(semantic.get("objects") or [])
        scene = semantic.get("scene")
        sem_conf = float(semantic.get("confidence") or 0.0)
        sem_err = semantic.get("error")
        sem_ok = bool(caption) and not sem_err

        entities: List[str] = []
        semantic_concepts: List[str] = []
        text_out: Optional[str] = None
        confidence = 0.75 if features["faces_detected"] > 0 else 0.6

        if sem_ok and isinstance(caption, str) and caption.strip():
            # Reuse text concept/entity extraction on the inferred caption.
            base = self.perceive_text(caption)
            semantic_concepts = list(base.get("concepts") or [])
            entities = list(base.get("entities") or [])
            novelty_flags = list(dict.fromkeys(
                list(base.get("novelty_flags") or []) + novelty_flags
            ))
            text_out = caption
            confidence = min(0.95, max(0.7, 0.55 + sem_conf * 0.4))
            meta_ling = dict(base.get("raw_meta") or {})
        else:
            meta_ling = {}
            # Honest low-level sensory note when no semantic caption.
            text_out = (
                f"[vision {intake}] {features['resolution']} "
                f"brightness={features['brightness_label']} "
                f"faces={features['faces_detected']} "
                f"complexity={features['complexity']} "
                f"dominant={features['dominant_channel']}"
            )
            if sem_err:
                novelty_flags.append("semantic_vision_unavailable_or_low_confidence")

        if semantic_concepts:
            concepts = semantic_concepts + [c for c in low_level if c not in semantic_concepts]
        else:
            concepts = low_level

        raw_meta = {
            **meta_ling,
            "available": True,
            "intake": intake,
            "source": source_label,
            "faces_detected": features["faces_detected"],
            "brightness": features["brightness"],
            "brightness_label": features["brightness_label"],
            "resolution": features["resolution"],
            "width": features["width"],
            "height": features["height"],
            "edge_density": features["edge_density"],
            "complexity": features["complexity"],
            "dominant_channel": features["dominant_channel"],
            "colorfulness": features["colorfulness"],
            "caption": caption,
            "objects": objects,
            "scene": scene,
            "semantic": {
                "available": bool(semantic.get("available")),
                "backend": semantic.get("backend"),
                "confidence": sem_conf,
                "scores": list(semantic.get("scores") or [])[:5],
                "error": sem_err,
                "clip_supplemental": semantic.get("clip_supplemental"),
            },
            "semantic_vision_available": bool(self.semantic_vision_available),
            "camera_live": bool(self.vision_available),
            "timestamp": time.time(),
        }
        if extra_meta:
            raw_meta.update(extra_meta)

        out = self._unified(
            "vision",
            text=text_out,
            concepts=concepts,
            entities=entities,
            novelty_flags=novelty_flags,
            confidence=confidence,
            raw_meta=raw_meta,
        )
        if caption:
            out["caption"] = caption
        return out

    # ------------------------------------------------------------------
    # Vision channel — file/bytes + optional camera
    # ------------------------------------------------------------------

    def perceive_vision(
        self,
        path: Optional[PathLike] = None,
        image_bytes: Optional[bytes] = None,
        *,
        use_camera: bool = False,
    ) -> Dict[str, Any]:
        """Perceive vision from image file/bytes, or live camera when requested."""
        if path is not None or image_bytes is not None:
            return self._perceive_vision_file(path=path, image_bytes=image_bytes)

        if use_camera or (path is None and image_bytes is None):
            return self._perceive_vision_camera()

        return self._unified(
            "vision",
            confidence=0.0,
            raw_meta={
                "available": False,
                "error": "no vision source provided",
                "timestamp": time.time(),
            },
        )

    def _perceive_vision_file(
        self,
        path: Optional[PathLike] = None,
        image_bytes: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        if not self.vision_file_available:
            return self._unified(
                "vision",
                confidence=0.0,
                raw_meta={
                    "available": False,
                    "reason": self._vision_file_reason,
                    "error": "vision file perception disabled — opencv/PIL unavailable",
                    "timestamp": time.time(),
                },
            )
        try:
            frame, load_meta = self._load_image_bgr(path=path, image_bytes=image_bytes)
            features = self._analyze_frame(frame)
            semantic = self._semantic_vision_infer(frame)
            return self._envelope_from_vision(
                features,
                intake="file",
                source_label="vision_file",
                extra_meta=load_meta,
                semantic=semantic,
            )
        except Exception as exc:
            return self._unified(
                "vision",
                confidence=0.0,
                raw_meta={
                    "available": True,
                    "intake": "file",
                    "error": f"vision file processing failed: {exc}",
                    "timestamp": time.time(),
                },
            )

    def _perceive_vision_camera(self) -> Dict[str, Any]:
        if not self.vision_available or self._cv2 is None:
            return self._unified(
                "vision",
                concepts=[],
                entities=[],
                novelty_flags=[],
                confidence=0.0,
                raw_meta={
                    "available": False,
                    "intake": "camera",
                    "reason": self._vision_reason,
                    "error": "live camera perception disabled — device unavailable",
                    "vision_file_available": bool(self.vision_file_available),
                    "hint": "pass path= or image_bytes= for file-based vision",
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
                    confidence=0.0,
                    raw_meta={
                        "available": False,
                        "intake": "camera",
                        "error": "could not open camera",
                        "timestamp": time.time(),
                    },
                )
            ret, frame = cap.read()
            if not ret or frame is None:
                return self._unified(
                    "vision",
                    confidence=0.0,
                    raw_meta={
                        "available": True,
                        "intake": "camera",
                        "error": "could not read frame",
                        "timestamp": time.time(),
                    },
                )
            features = self._analyze_frame(frame)
            semantic = self._semantic_vision_infer(frame)
            return self._envelope_from_vision(
                features,
                intake="camera",
                source_label="vision_camera",
                semantic=semantic,
            )
        except Exception as exc:
            return self._unified(
                "vision",
                confidence=0.0,
                raw_meta={
                    "available": self.vision_available,
                    "intake": "camera",
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

    def process_visual_input(
        self,
        path: Optional[PathLike] = None,
        image_bytes: Optional[bytes] = None,
    ) -> Optional[Dict[str, Any]]:
        if path is not None or image_bytes is not None:
            result = self.perceive_vision(path=path, image_bytes=image_bytes)
        elif not self.vision_available and not self.vision_file_available:
            return None
        else:
            result = self.perceive_vision()
        if (result.get("raw_meta") or {}).get("error") and not result.get("concepts"):
            return None
        return result

    # Aliases matching design naming
    def perceive_audio_file(self, path: PathLike, try_stt: bool = True) -> Dict[str, Any]:
        return self.perceive_audio(path=path, try_stt=try_stt)

    def perceive_vision_file(self, path: PathLike) -> Dict[str, Any]:
        return self.perceive_vision(path=path)

    def perceive_image_file(self, path: PathLike) -> Dict[str, Any]:
        return self.perceive_vision(path=path)

    # ------------------------------------------------------------------
    # Status / messaging
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        hearing_online = bool(self.stt_available or self.audio_file_available)
        vision_online = bool(self.vision_available or self.vision_file_available)
        return {
            "text": True,
            "text_input": True,
            "audio": hearing_online,
            "vision": vision_online,
            "stt_available": bool(self.stt_available),
            "vision_available": bool(self.vision_available),
            "audio_enabled": hearing_online,
            "vision_enabled": vision_online,
            "audio_mic": bool(self.stt_available),
            "audio_file": bool(self.audio_file_available),
            "vision_camera": bool(self.vision_available),
            "vision_file": bool(self.vision_file_available),
            "semantic_stt_available": bool(self.semantic_stt_available),
            "stt_backend": self.stt_backend,
            "stt_backend_reason": self._stt_backend_reason,
            "semantic_vision_available": bool(self.semantic_vision_available),
            "vision_semantic_backend": self.vision_semantic_backend,
            "vision_semantic_reason": self._vision_semantic_reason,
            "audio_reason": self._audio_reason,
            "vision_reason": self._vision_reason,
            "audio_file_reason": self._audio_file_reason,
            "vision_file_reason": self._vision_file_reason,
            "senses_online": {
                "text": True,
                "audio": hearing_online,
                "vision": vision_online,
                "audio_mic": bool(self.stt_available),
                "audio_file": bool(self.audio_file_available),
                "vision_camera": bool(self.vision_available),
                "vision_file": bool(self.vision_file_available),
                "semantic_stt": bool(self.semantic_stt_available),
                "semantic_vision": bool(self.semantic_vision_available),
            },
            "claimed_modalities": [
                m
                for m, on in (
                    ("text", True),
                    ("audio", hearing_online),
                    ("vision", vision_online),
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
            result["normalized_text"] = result.get("text", "")
            result["words"] = list(result.get("concepts") or [])
            return {"status": "success", "content": result}

        if msg_type in ("perceive_audio", "listen_audio", "perceive_audio_file"):
            path = payload.get("path") or payload.get("file") or payload.get("audio_path")
            audio_bytes = payload.get("audio_bytes") or payload.get("bytes") or payload.get("data")
            use_mic = bool(payload.get("use_mic"))
            try_stt = payload.get("try_stt", True)
            if isinstance(audio_bytes, str):
                # allow base64
                import base64
                try:
                    audio_bytes = base64.b64decode(audio_bytes)
                except Exception:
                    audio_bytes = audio_bytes.encode("utf-8")
            if path or audio_bytes is not None:
                result = self.perceive_audio(
                    path=path, audio_bytes=audio_bytes, try_stt=bool(try_stt)
                )
            elif use_mic:
                result = self.perceive_audio(use_mic=True)
            else:
                # Prefer honest file hint over silent mic failure when no source.
                result = self.perceive_audio()
            err = (result.get("raw_meta") or {}).get("error")
            if err and not result.get("concepts") and not result.get("text"):
                return {"status": "error", "message": err, "content": result}
            return {"status": "success", "content": result}

        if msg_type in ("perceive_vision", "capture_visual", "perceive_vision_file", "perceive_image"):
            path = payload.get("path") or payload.get("file") or payload.get("image_path")
            image_bytes = payload.get("image_bytes") or payload.get("bytes") or payload.get("data")
            use_camera = bool(payload.get("use_camera"))
            if isinstance(image_bytes, str):
                import base64
                try:
                    image_bytes = base64.b64decode(image_bytes)
                except Exception:
                    image_bytes = image_bytes.encode("utf-8")
            if path or image_bytes is not None:
                result = self.perceive_vision(path=path, image_bytes=image_bytes)
            elif use_camera:
                result = self.perceive_vision(use_camera=True)
            else:
                result = self.perceive_vision()
            err = (result.get("raw_meta") or {}).get("error")
            if err and not result.get("concepts"):
                return {"status": "error", "message": err, "content": result}
            return {"status": "success", "content": result}

        if msg_type == "get_status":
            status = self.get_status()
            return {"status": "success", "content": status, **status}

        if msg_type == "sensory_data":
            signals = payload.get("signals") or []
            fused: List[Dict[str, Any]] = []
            for sig in signals:
                if isinstance(sig, str) and sig.strip():
                    fused.append(self.perceive_text(sig))
                elif isinstance(sig, dict):
                    modality = str(sig.get("modality") or sig.get("type") or "text").lower()
                    if modality in ("audio", "hearing") and (sig.get("path") or sig.get("audio_bytes") or sig.get("bytes")):
                        fused.append(
                            self.perceive_audio(
                                path=sig.get("path"),
                                audio_bytes=sig.get("audio_bytes") or sig.get("bytes"),
                            )
                        )
                    elif modality in ("vision", "visual", "image") and (
                        sig.get("path") or sig.get("image_bytes") or sig.get("bytes")
                    ):
                        fused.append(
                            self.perceive_vision(
                                path=sig.get("path"),
                                image_bytes=sig.get("image_bytes") or sig.get("bytes"),
                            )
                        )
                    elif sig.get("text"):
                        fused.append(self.perceive_text(str(sig["text"])))
            return {"status": "success", "content": {"fused": fused, "count": len(fused)}}

        return {"status": "error", "message": f"Unknown message type: {msg_type}"}

    def start(self) -> None:
        """CLI helper — register and idle. No hearing/vision theater threads."""
        senses = self.get_status()["senses_online"]
        print(
            "Perception Lobe: "
            f"text={'online' if senses['text'] else 'off'} "
            f"audio_file={'online' if senses['audio_file'] else 'disabled'} "
            f"audio_mic={'online' if senses['audio_mic'] else 'disabled'} "
            f"vision_file={'online' if senses['vision_file'] else 'disabled'} "
            f"vision_camera={'online' if senses['vision_camera'] else 'disabled'}"
        )
        if not senses["audio_mic"]:
            print(f"  audio_mic: {self._audio_reason}")
        if senses["audio_file"]:
            print(f"  audio_file: {self._audio_file_reason}")
        print(f"  semantic_stt: {self.stt_backend or 'none'} — {self._stt_backend_reason}")
        if not senses["vision_camera"]:
            print(f"  vision_camera: {self._vision_reason}")
        if senses["vision_file"]:
            print(f"  vision_file: {self._vision_file_reason}")
        print(
            f"  semantic_vision: {self.vision_semantic_backend or 'none'} — "
            f"{self._vision_semantic_reason}"
        )
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
