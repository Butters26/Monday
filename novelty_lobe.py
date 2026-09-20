#!/usr/bin/env python3
"""
Novelty Lobe — detect genuinely new experience against recent/familiar patterns.

Primary job (live path):
  assess incoming text / perception envelopes → real novelty_score + flags
  feed that signal to Attention / Thalamus / curiosity consumers.

Curiosity *questions* are owned by emotion/conversation/direct_response.
This lobe does NOT spam language with duplicate questions; it provides the
novelty signal those paths can consume. Emotion may still notify us when
affect spikes so we can record learning context.
"""

from __future__ import annotations

import logging
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9']+")
_STOP = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "if", "to", "of", "in", "on", "at",
        "for", "is", "are", "was", "were", "be", "am", "i", "you", "he", "she",
        "it", "we", "they", "me", "my", "your", "our", "their", "this", "that",
        "with", "from", "as", "by", "do", "does", "did", "have", "has", "had",
        "not", "no", "yes", "so", "just", "about", "what", "when", "where",
        "who", "which", "how", "why", "can", "could", "would", "should",
    }
)
_COMMON_FUNCTION = frozenset(
    {
        "hello", "hi", "hey", "thanks", "thank", "please", "ok", "okay", "yeah",
        "yep", "nope", "good", "bad", "well", "here", "there", "then", "than",
        "them", "will", "know", "think", "like", "want", "need", "make", "made",
    }
)


@dataclass
class NoveltyMemory:
    """Remembers how Monday reacted to similar novel things before."""

    stimulus_type: str
    stimulus: str
    initial_emotion: str
    intensity: float
    valence: float
    timestamp: float
    user_response: Optional[str] = None
    learned_value: Optional[str] = None
    reinforcement_count: int = 0


@dataclass
class NoveltySignal:
    """Signal from a lobe that something novel was detected."""

    source: str
    stimulus: str
    stimulus_type: str
    confidence: float
    emotion_already_generated: bool = False
    timestamp: float = field(default_factory=time.time)


@dataclass
class NoveltyAssessment:
    """Computed novelty of one experience."""

    score: float
    is_novel: bool
    flags: List[str]
    novel_tokens: List[str]
    familiar_overlap: float
    nearest_similarity: float
    source: str
    stimulus: str
    perception_flags: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "novelty_score": round(float(self.score), 4),
            "is_novel": bool(self.is_novel),
            "novelty_flags": list(self.flags),
            "novel_tokens": list(self.novel_tokens),
            "familiar_overlap": round(float(self.familiar_overlap), 4),
            "nearest_similarity": round(float(self.nearest_similarity), 4),
            "source": self.source,
            "stimulus": self.stimulus,
            "perception_flags": list(self.perception_flags),
            "timestamp": float(self.timestamp),
        }


class NoveltyLobe:
    """
    Owns novelty computation for the live path.

    Perception may still emit local novelty_flags (first-seen entities/concepts).
    Novelty consolidates those with its own recent/familiar pattern memory into
    a single score Attention and curiosity consumers can use.
    """

    ELEVATED_THRESHOLD = 0.45
    HIGH_THRESHOLD = 0.70

    def __init__(self, thalamus: Any = None, history_size: int = 64):
        self.running = True
        self.thalamus = thalamus
        if self.thalamus is None:
            try:
                from thalamus import get_thalamus

                self.thalamus = get_thalamus()
            except Exception:
                self.thalamus = None

        self.novelty_memories: List[NoveltyMemory] = []
        self.processing_novelties: Dict[str, NoveltySignal] = {}
        self.pending_user_responses: Dict[str, Dict[str, Any]] = {}

        # Real familiarity stores — not random.
        self.familiar_tokens: Set[str] = set()
        self.familiar_entities: Set[str] = set()
        self.recent_fingerprints: Deque[Set[str]] = deque(maxlen=max(8, int(history_size)))
        self.recent_stimuli: Deque[str] = deque(maxlen=max(8, int(history_size)))

        self.last_assessment: Optional[NoveltyAssessment] = None
        # One-shot: perception signal sets this; live path may consume once.
        self._fresh_signal_pending: bool = False
        self.emotional_momentum = 0.0
        # Kept for compatibility with older emotion-driven question helpers;
        # does not drive the novelty *score*.
        self.variance_factor = 0.05
        # Registration is owned by create_core_systems / callers — do not
        # auto-register here (matches Attention/Perception pattern).

    # ------------------------------------------------------------------
    # Tokenization / similarity
    # ------------------------------------------------------------------

    @staticmethod
    def _tokenize(text: str) -> Set[str]:
        if not isinstance(text, str) or not text.strip():
            return set()
        tokens = set(_TOKEN_RE.findall(text.lower()))
        return {t for t in tokens if len(t) > 1}

    @classmethod
    def _content_tokens(cls, text: str) -> Set[str]:
        return {t for t in cls._tokenize(text) if t not in _STOP}

    @staticmethod
    def _jaccard(a: Set[str], b: Set[str]) -> float:
        if not a and not b:
            return 1.0
        if not a or not b:
            return 0.0
        inter = len(a & b)
        union = len(a | b)
        return float(inter) / float(union) if union else 0.0

    def _nearest_similarity(self, tokens: Set[str]) -> float:
        if not tokens or not self.recent_fingerprints:
            return 0.0
        best = 0.0
        for prior in self.recent_fingerprints:
            sim = self._jaccard(tokens, prior)
            if sim > best:
                best = sim
        return best

    # ------------------------------------------------------------------
    # Core assessment (real signal)
    # ------------------------------------------------------------------

    def assess_experience(
        self,
        text: str = "",
        perception: Optional[Dict[str, Any]] = None,
        *,
        source: str = "live",
        commit: bool = True,
    ) -> Dict[str, Any]:
        """Score novelty of text / perception envelope against familiar patterns."""
        perception = perception if isinstance(perception, dict) else {}
        stimulus = text if isinstance(text, str) else ""
        if not stimulus.strip():
            stimulus = str(
                perception.get("text")
                or perception.get("normalized_text")
                or ""
            )

        tokens = self._content_tokens(stimulus)
        # Fold perception concepts/entities into the fingerprint.
        for word in perception.get("concepts") or perception.get("words") or []:
            if isinstance(word, str):
                w = word.lower().strip()
                if len(w) > 1 and w not in _STOP:
                    tokens.add(w)
        entities: List[str] = []
        for ent in perception.get("entities") or []:
            if isinstance(ent, str) and ent.strip():
                entities.append(ent.strip())
                for part in self._tokenize(ent):
                    if part not in _STOP:
                        tokens.add(part)

        perception_flags = [
            str(f) for f in (perception.get("novelty_flags") or []) if f
        ]

        novel_tokens = sorted(
            t
            for t in tokens
            if t not in self.familiar_tokens and t not in _COMMON_FUNCTION
        )
        novel_entities = [
            e for e in entities if e.lower() not in self.familiar_entities
        ]

        familiar_overlap = 0.0
        if tokens:
            known = tokens & self.familiar_tokens
            familiar_overlap = float(len(known)) / float(len(tokens))

        nearest = self._nearest_similarity(tokens)

        # Score components (deterministic, no random theater).
        unseen_frac = 0.0
        if tokens:
            contentish = {t for t in tokens if t not in _COMMON_FUNCTION}
            if contentish:
                unseen_frac = float(len([t for t in contentish if t not in self.familiar_tokens])) / float(
                    len(contentish)
                )
            else:
                unseen_frac = float(len(novel_tokens)) / float(len(tokens)) if tokens else 0.0

        # High similarity to a recent fingerprint suppresses novelty.
        recency_penalty = nearest  # 1.0 = identical to recent
        entity_boost = min(0.35, 0.18 * len(novel_entities))
        perc_boost = min(0.25, 0.06 * len(perception_flags))
        # Cold-start: if nothing familiar yet, moderate score from content richness
        # rather than claiming everything is 100% novel forever.
        if not self.familiar_tokens and not self.recent_fingerprints:
            richness = min(1.0, len(tokens) / 8.0)
            score = 0.25 + 0.35 * richness + entity_boost + 0.5 * perc_boost
        else:
            score = (
                0.55 * unseen_frac
                + 0.30 * (1.0 - recency_penalty)
                + entity_boost
                + perc_boost
                - 0.20 * familiar_overlap
            )

        score = max(0.0, min(1.0, float(score)))

        flags: List[str] = []
        for ent in novel_entities[:6]:
            flags.append(f"novel_entity:{ent}")
        for tok in novel_tokens[:8]:
            flags.append(f"novel_token:{tok}")
        if nearest >= 0.85 and tokens:
            flags.append("familiar_recent_repeat")
        if score >= self.HIGH_THRESHOLD:
            flags.append("novelty_high")
        elif score >= self.ELEVATED_THRESHOLD:
            flags.append("novelty_elevated")
        else:
            flags.append("novelty_low")
        # Keep perception flags visible (merged, deduped).
        for f in perception_flags:
            if f not in flags:
                flags.append(f)

        assessment = NoveltyAssessment(
            score=score,
            is_novel=score >= self.ELEVATED_THRESHOLD,
            flags=flags,
            novel_tokens=novel_tokens[:12],
            familiar_overlap=familiar_overlap,
            nearest_similarity=nearest,
            source=source,
            stimulus=stimulus[:240],
            perception_flags=perception_flags,
        )

        # Primary commits always publish. Secondary (commit=False) signals must
        # not clobber a fresher elevated live/perception assessment.
        publish = True
        if not commit and self.last_assessment is not None:
            age = time.time() - float(self.last_assessment.timestamp)
            if age < 90.0 and assessment.score < float(self.last_assessment.score):
                publish = False
        if publish:
            self.last_assessment = assessment

        if commit and tokens:
            self.recent_fingerprints.append(set(tokens))
            self.recent_stimuli.append(stimulus[:240])
            self.familiar_tokens.update(tokens)
            for ent in entities:
                self.familiar_entities.add(ent.lower())

        return assessment.as_dict()

    # ------------------------------------------------------------------
    # Message API
    # ------------------------------------------------------------------

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = message.get("type")
        # Thalamus send_message packs content separately; accept flat or nested.
        payload = message.get("content") if isinstance(message.get("content"), dict) else message
        if not isinstance(payload, dict):
            payload = message if isinstance(message, dict) else {}
        # Prefer explicit type on outer message.
        if msg_type is None:
            msg_type = payload.get("type")

        if msg_type in ("assess_experience", "assess", "evaluate_novelty"):
            result = self.assess_experience(
                text=str(payload.get("text") or payload.get("stimulus") or ""),
                perception=payload.get("perception")
                if isinstance(payload.get("perception"), dict)
                else payload.get("perception_payload")
                if isinstance(payload.get("perception_payload"), dict)
                else {},
                source=str(payload.get("source") or "message"),
                commit=bool(payload.get("commit", True)),
            )
            return {"status": "success", "content": result, **result}

        if msg_type == "get_assessment":
            if self.last_assessment is None:
                return {"status": "success", "content": {}, "novelty_score": 0.0}
            d = self.last_assessment.as_dict()
            return {"status": "success", "content": d, **d}

        if msg_type in ("take_fresh_assessment", "consume_fresh_assessment"):
            # One-shot handoff from perception signal → live path.
            if self._fresh_signal_pending and self.last_assessment is not None:
                self._fresh_signal_pending = False
                d = self.last_assessment.as_dict()
                return {"status": "success", "content": d, "fresh": True, **d}
            return {"status": "success", "content": {}, "fresh": False}

        if msg_type == "novelty_signal":
            return self._handle_novelty_signal(payload)

        if msg_type == "emotional_response_to_novelty":
            return self._handle_emotional_response(payload)

        if msg_type == "user_response":
            return self._handle_user_response(payload)

        if msg_type == "get_pending_questions":
            return {"status": "success", "pending": self.pending_user_responses}

        if msg_type == "health":
            return {
                "status": "success",
                "healthy": True,
                "familiar_token_count": len(self.familiar_tokens),
                "recent_count": len(self.recent_fingerprints),
                "last_score": (
                    self.last_assessment.score if self.last_assessment else None
                ),
            }

        return {"status": "error", "message": f"Unknown message type: {msg_type}"}

    def _handle_novelty_signal(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Perception (or other lobe) flagged novelty — assess + store signal."""
        stimulus = str(message.get("stimulus") or message.get("text") or "")
        source = str(message.get("source") or "signal")
        # Perception owns first-pass live novelty; reasoning/emotion are secondary
        # evidence and must not re-commit familiarity or clobber the live score.
        primary = source in {
            "perception",
            "live",
            "live_path",
            "text_input",
            "proof",
            "proof_live",
            "sensory",
        }
        perception = {
            "text": stimulus,
            "concepts": list(message.get("novel_concepts") or []),
            "entities": list(message.get("novel_entities") or []),
            "novelty_flags": list(message.get("novelty_flags") or []),
        }
        for key in ("concepts", "words", "concepts_involved"):
            extra = message.get(key)
            if isinstance(extra, list):
                perception.setdefault("concepts", [])
                perception["concepts"] = list(perception["concepts"]) + [
                    c for c in extra if isinstance(c, str)
                ]

        assessment = self.assess_experience(
            text=stimulus,
            perception=perception,
            source=source,
            commit=primary,
        )

        signal = NoveltySignal(
            source=source,
            stimulus=stimulus,
            stimulus_type=str(message.get("stimulus_type") or "unknown"),
            confidence=float(message.get("confidence") or assessment.get("novelty_score") or 0.0),
        )
        if stimulus:
            self.processing_novelties[stimulus] = signal

        if primary:
            # One-shot handoff to thalamus live-path.
            self._fresh_signal_pending = True

        print(
            f"🆕 Novelty signal from {signal.source}: "
            f"score={assessment['novelty_score']:.2f} "
            f"is_novel={assessment['is_novel']}"
        )
        return {
            "status": "received",
            "stimulus": stimulus,
            "waiting_for_emotion": False,
            "primary": primary,
            **assessment,
        }

    def _handle_emotional_response(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Emotion notified strong affect. Record context for learning.
        Do NOT auto-spam language — curiosity questions live on the
        conversation/thalamus path and consume our novelty_score instead.
        """
        stimulus = str(message.get("stimulus") or "")
        emotion = str(message.get("emotion") or "")
        intensity = float(message.get("intensity", 0.5) or 0.5)
        valence = float(message.get("valence", 0.0) or 0.0)

        # Ensure we have an assessment for this stimulus.
        if stimulus and (
            self.last_assessment is None
            or self.last_assessment.stimulus != stimulus[:240]
        ):
            self.assess_experience(text=stimulus, source="emotion_notify", commit=True)

        score = self.last_assessment.score if self.last_assessment else 0.0
        print(
            f"😊 Emotion→Novelty: {emotion} int={intensity:.2f} "
            f"novelty_score={score:.2f}"
        )

        is_strong = intensity > 0.6 or abs(valence) > 0.4
        if not is_strong or score < self.ELEVATED_THRESHOLD:
            return {
                "status": "noted",
                "reason": "affect_or_novelty_below_threshold",
                "novelty_score": score,
            }

        # Optionally draft a question for consumers that ask — do not send.
        question = self._generate_question_from_emotion(
            stimulus=stimulus,
            emotion=emotion,
            intensity=intensity,
            valence=valence,
            similar_experiences=self._query_local_similar(stimulus),
        )
        if question and stimulus:
            self.pending_user_responses[stimulus] = {
                "emotion": emotion,
                "intensity": intensity,
                "valence": valence,
                "question": question,
                "timestamp": time.time(),
                "novelty_score": score,
            }

        self._update_emotional_momentum(valence)
        return {
            "status": "noted_elevated",
            "stimulus": stimulus,
            "question_draft": question,
            "novelty_score": score,
            "dispatched_to_language": False,
        }

    def _handle_user_response(self, message: Dict[str, Any]) -> Dict[str, Any]:
        stimulus = message.get("stimulus")
        user_answer = message.get("answer")
        if stimulus not in self.pending_user_responses:
            return {"status": "error", "message": "Unknown stimulus"}

        context = self.pending_user_responses.pop(stimulus)
        memory = NoveltyMemory(
            stimulus_type=self._classify_stimulus_type(str(stimulus)),
            stimulus=str(stimulus),
            initial_emotion=context["emotion"],
            intensity=float(context["intensity"]),
            valence=float(context["valence"]),
            timestamp=time.time(),
            user_response=str(user_answer) if user_answer is not None else None,
            learned_value=self._extract_value_from_response(
                str(user_answer) if user_answer else ""
            ),
        )
        self.novelty_memories.append(memory)
        self._store_in_notus(str(stimulus), memory)
        self._update_emotional_momentum(float(context["valence"]))
        return {"status": "learned", "stimulus": stimulus, "memory_stored": True}

    def _query_local_similar(self, stimulus: str) -> List[NoveltyMemory]:
        similar: List[NoveltyMemory] = []
        stimulus_lower = stimulus.lower()
        words = [w for w in stimulus_lower.split() if len(w) > 3]
        for memory in self.novelty_memories:
            if any(word in memory.stimulus.lower() for word in words):
                similar.append(memory)
        return similar[:3]

    def _query_notus_for_similar_stimuli(self, stimulus: str) -> List[NoveltyMemory]:
        # Prefer local memories; Notus query is best-effort glue.
        similar = self._query_local_similar(stimulus)
        if similar or self.thalamus is None:
            return similar
        try:
            self.thalamus.send_message(
                "notus",
                "query_facts",
                {"query": f"novelty {stimulus}", "limit": 5},
            )
        except Exception as e:
            logger.error(f"Failed to query Notus: {e}")
        return similar

    def _generate_question_from_emotion(
        self,
        stimulus: str,
        emotion: str,
        intensity: float,
        valence: float,
        similar_experiences: List[NoveltyMemory],
    ) -> Optional[str]:
        """Draft only — live path does not auto-dispatch these to language."""
        stimulus_label = self._extract_stimulus_label(stimulus)
        if similar_experiences:
            past = similar_experiences[0]
            if past.learned_value:
                past_label = self._extract_stimulus_label(past.stimulus)
                if valence > 0:
                    return f"Why does this {stimulus_label} feel different from {past_label}?"
                return f"Is {stimulus_label} going to be like {past_label}?"

        if emotion in ("excited", "curious"):
            if intensity > 0.8:
                return f"What IS this {stimulus_label}?? Tell me everything!"
            return f"Where did this {stimulus_label} come from? Who made it?"
        if emotion in ("disgusted", "angry"):
            if intensity > 0.8:
                return f"Why would you show me this {stimulus_label}? What's the point?"
            return f"I don't get {stimulus_label}. Why do you like it?"
        if emotion == "confused":
            return f"I don't even know what {stimulus_label} IS. Help me understand?"
        if emotion == "intrigued":
            return f"This {stimulus_label} is strange... tell me more about it?"
        if emotion == "uncertain":
            return f"I'm not sure how I feel about {stimulus_label}. What should I think?"
        return None

    def _extract_stimulus_label(self, stimulus: str) -> str:
        stimulus_lower = stimulus.lower()
        if any(w in stimulus_lower for w in ("song", "music", "artist", "band", "listen")):
            return "song"
        if any(w in stimulus_lower for w in ("movie", "show", "video", "film", "watch")):
            return "movie"
        if any(
            w in stimulus_lower
            for w in ("person", "people", "guy", "girl", "man", "woman", "friend")
        ):
            return "person"
        if any(w in stimulus_lower for w in ("idea", "concept", "think", "thought")):
            return "idea"
        words = stimulus.split()
        if len(words) <= 3:
            return stimulus
        if len(words) <= 8:
            return " ".join(words[:3])
        return "thing"

    def _classify_stimulus_type(self, stimulus: str) -> str:
        stimulus_lower = stimulus.lower()
        if any(w in stimulus_lower for w in ("song", "music", "artist", "band")):
            return "music"
        if any(w in stimulus_lower for w in ("movie", "show", "video", "film")):
            return "media"
        if any(
            w in stimulus_lower
            for w in ("person", "people", "guy", "girl", "man", "woman")
        ):
            return "person"
        if any(w in stimulus_lower for w in ("idea", "concept", "theory", "thought")):
            return "concept"
        if any(w in stimulus_lower for w in ("word", "phrase", "language")):
            return "language"
        return "unknown"

    def _extract_value_from_response(self, response: str) -> Optional[str]:
        if not response:
            return None
        sentences = response.split(".")
        if sentences:
            return sentences[0].strip()[:100]
        return response[:100]

    def _store_in_notus(self, stimulus: str, memory: NoveltyMemory) -> None:
        if self.thalamus is None:
            return
        try:
            self.thalamus.send_message(
                "notus",
                "remember_fact",
                {
                    "subject": f"novelty_{memory.stimulus_type}",
                    "predicate": "learned_about",
                    "object": stimulus,
                    "value": memory.learned_value,
                    "confidence": memory.intensity,
                },
            )
        except Exception as e:
            logger.error(f"Failed to store in Notus: {e}")

    def _update_emotional_momentum(self, valence: float) -> None:
        shift = valence * 0.15
        self.emotional_momentum += shift
        self.emotional_momentum *= 0.9
        self.emotional_momentum = max(-1.0, min(1.0, self.emotional_momentum))

    def get_question_to_ask_user(self, stimulus: str) -> Optional[str]:
        if stimulus in self.pending_user_responses:
            return self.pending_user_responses[stimulus].get("question")
        return None

    def shutdown(self) -> None:
        self.running = False


if __name__ == "__main__":
    print("🆕 Novelty Lobe starting...")
    novelty = NoveltyLobe()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down")
        novelty.shutdown()
