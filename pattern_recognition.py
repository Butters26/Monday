#!/usr/bin/env python3
"""
Advanced Pattern Recognition Lobe
Detects human-like patterns including behavioral, pareidolia, meta-patterns
Like how humans see patterns everywhere - including patterns that aren't there
"""

import atexit
import json
import os
import time
import random
import sys
import weakref
from pathlib import Path
from typing import Dict, Any, List, Tuple, Set, Optional
from collections import defaultdict, deque
from dataclasses import dataclass, field
from thalamus import get_thalamus
from runtime_paths import runtime_dir

# ============================================================================
# PATTERN DATA STRUCTURES
# ============================================================================

@dataclass
class CoOccurrence:
    """Two things appearing together"""
    item_a: str
    item_b: str
    count: int = 0
    strength: float = 0.0
    last_seen: float = 0.0
    contexts: List[str] = field(default_factory=list)

@dataclass
class Sequence:
    """Multi-step sequence A→B→C→D"""
    steps: List[str]
    count: int = 0
    confidence: float = 0.0
    last_seen: float = 0.0
    average_time_between_steps: float = 0.0
    durable: bool = False  # promoted beyond working-window / persisted

@dataclass
class BehavioralPattern:
    """Complex behavioral pattern combining multiple signals"""
    name: str
    signals: Dict[str, Any]  # What signals make up this pattern
    occurrences: int = 0
    confidence: float = 0.0
    examples: List[Dict] = field(default_factory=list)
    last_seen: float = 0.0

@dataclass
class Contradiction:
    """Detected contradiction"""
    statement_a: str
    statement_b: str
    timestamp_a: float
    timestamp_b: float
    severity: float = 0.5

@dataclass
class MetaPattern:
    """Pattern about patterns"""
    description: str
    patterns_involved: List[str]
    meta_confidence: float = 0.0

@dataclass
class PareidoliaPattern:
    """Speculative pattern seen in weak signals"""
    description: str
    confidence: float = 0.0
    is_speculative: bool = True
    signals: List[str] = field(default_factory=list)

# ============================================================================
# ADVANCED PATTERN RECOGNITION LOBE
# ============================================================================

class AdvancedPatternRecognition:
    """Human-like pattern recognition - sees everything"""
    
    def __init__(self, thalamus=None):
        self.running = True
        # Direct reference to Thalamus (NO SOCKETS). Prefer the live instance
        # passed by run_abin so we do not attach to a separate singleton.
        self.thalamus = thalamus if thalamus is not None else get_thalamus()
        
        # Basic patterns
        self.co_occurrences: Dict[Tuple[str, str], CoOccurrence] = {}
        self.sequences: Dict[Tuple, Sequence] = {}
        
        # Advanced patterns
        self.behavioral_patterns: Dict[str, BehavioralPattern] = {}
        self.contradictions: List[Contradiction] = []
        self.meta_patterns: List[MetaPattern] = []
        self.pareidolia_patterns: List[PareidoliaPattern] = []
        
        # Working window (bounded) — ephemeral observation buffer only.
        # Discovered/significant patterns promote to durable & Pattern-local store.
        # Defaults below; pattern_config.json overrides via _apply_pattern_config().
        self.working_window_size = 50
        self.sequence_detect_slice = 20  # local discovery looks at recent slice
        self.local_seq_lengths = (3, 4, 5)  # window-local discovery lengths
        self.max_composed_sequence_length = 32  # growth ceiling via composition
        # Compose tightening: bound low-info / same-token fan-out (pattern_config may override)
        self.min_compose_token_diversity = 0.35  # unique/len floor for longer composed seqs
        self.max_dominant_token_fraction = 0.6  # refuse when one token dominates
        self.compose_min_unique_tokens = 2  # refuse constant / single-token sequences
        self.max_compose_per_observe = 4  # cap new composed records per observe
        # Short near-dup durability scrub (narrow; not a blanket short-seq diversity rule)
        self.short_near_dup_enabled = True
        self.short_near_dup_max_length = 3  # len < 4
        self.short_near_dup_min_run = 2  # adjacent repeated token pair
        self.max_durable_sequences = 500  # soft cap on persisted sequences
        self.persist_sequence_confidence = 0.6
        self.persist_co_occurrence_strength = 0.5
        self.max_recent_concepts = 20
        self.max_sequence_time_gap = 60.0
        self._saving_knowledge = False

        # Thresholds (dynamic based on boredom) — config may override
        self.base_co_occurrence_threshold = 3
        self.base_sequence_threshold = 2
        self.base_behavioral_threshold = 3

        # Decay — config may override
        self.decay_rate = 0.1
        self.last_decay = time.time()

        # Wire pattern_config.json before constructing bounded buffers
        self._apply_pattern_config()

        self.recent_items = deque(maxlen=self.working_window_size)
        self.recent_emotions = deque(maxlen=30)
        self.recent_topics = deque(maxlen=self.max_recent_concepts)
        self.recent_word_choices = deque(maxlen=100)
        self.statement_history = deque(maxlen=100)

        # State tracking
        self.boredom_level = 0.0
        self.last_pattern_time = time.time()

        # Pattern-owned learned knowledge (NOT Notus)
        self.learned_opposites: Dict[str, List[str]] = {}
        self.learned_behavioral_patterns: Dict[str, Dict] = {}
        self._knowledge_dirty = False
        # Prefer Pattern-local file under runtime_dir(); tests set MONDAY_RUNTIME_DIR.
        self.knowledge_path = Path(runtime_dir()) / "pattern_knowledge.json"

        # Initialize default templates, then overlay Pattern-owned learned state
        self._initialize_default_templates()
        self._load_learned_knowledge()

        # Crash-safe: flush dirty durable knowledge on interpreter exit
        atexit.register(AdvancedPatternRecognition._atexit_flush, weakref.ref(self))
        

    def _apply_pattern_config(self) -> None:
        """Read pattern_config.json and apply limits / thresholds / decay already defined there."""
        config_path = Path(__file__).resolve().parent / "pattern_config.json"
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(raw, dict):
            return
        pr = raw.get("pattern_recognition")
        if not isinstance(pr, dict):
            return

        limits = pr.get("limits") if isinstance(pr.get("limits"), dict) else {}
        if "max_recent_items" in limits:
            try:
                self.working_window_size = max(3, int(limits["max_recent_items"]))
            except (TypeError, ValueError):
                pass
        if "max_recent_concepts" in limits:
            try:
                self.max_recent_concepts = max(1, int(limits["max_recent_concepts"]))
            except (TypeError, ValueError):
                pass
        if "max_stored_patterns" in limits:
            try:
                self.max_durable_sequences = max(1, int(limits["max_stored_patterns"]))
            except (TypeError, ValueError):
                pass
        if "sequence_detect_slice" in limits:
            try:
                self.sequence_detect_slice = max(3, int(limits["sequence_detect_slice"]))
            except (TypeError, ValueError):
                pass
        if "max_composed_sequence_length" in limits:
            try:
                self.max_composed_sequence_length = max(5, int(limits["max_composed_sequence_length"]))
            except (TypeError, ValueError):
                pass
        if "local_seq_lengths" in limits and isinstance(limits["local_seq_lengths"], list):
            try:
                lengths = tuple(sorted({int(x) for x in limits["local_seq_lengths"] if int(x) >= 2}))
                if lengths:
                    self.local_seq_lengths = lengths
            except (TypeError, ValueError):
                pass

        thresholds = pr.get("thresholds") if isinstance(pr.get("thresholds"), dict) else {}
        if "co_occurrence_threshold" in thresholds:
            try:
                self.base_co_occurrence_threshold = max(1, int(thresholds["co_occurrence_threshold"]))
            except (TypeError, ValueError):
                pass
        if "sequence_threshold" in thresholds:
            try:
                self.base_sequence_threshold = max(1, int(thresholds["sequence_threshold"]))
            except (TypeError, ValueError):
                pass
        if "cluster_threshold" in thresholds:
            try:
                self.base_behavioral_threshold = max(1, int(thresholds["cluster_threshold"]))
            except (TypeError, ValueError):
                pass

        decay = pr.get("decay") if isinstance(pr.get("decay"), dict) else {}
        if "decay_rate" in decay:
            try:
                self.decay_rate = float(decay["decay_rate"])
            except (TypeError, ValueError):
                pass

        seq_det = pr.get("sequence_detection") if isinstance(pr.get("sequence_detection"), dict) else {}
        if "max_time_gap_seconds" in seq_det:
            try:
                self.max_sequence_time_gap = float(seq_det["max_time_gap_seconds"])
            except (TypeError, ValueError):
                pass
        if "min_confidence" in seq_det:
            # Keep persist bar at least the detection floor; do not lower persist below 0.6 default
            # unless config explicitly raises a higher bar via this key when > current.
            try:
                min_conf = float(seq_det["min_confidence"])
                if min_conf > self.persist_sequence_confidence:
                    self.persist_sequence_confidence = min_conf
            except (TypeError, ValueError):
                pass

        compose = pr.get("compose") if isinstance(pr.get("compose"), dict) else {}
        if "min_token_diversity" in compose:
            try:
                self.min_compose_token_diversity = min(1.0, max(0.0, float(compose["min_token_diversity"])))
            except (TypeError, ValueError):
                pass
        if "max_dominant_token_fraction" in compose:
            try:
                self.max_dominant_token_fraction = min(1.0, max(0.0, float(compose["max_dominant_token_fraction"])))
            except (TypeError, ValueError):
                pass
        if "min_unique_tokens" in compose:
            try:
                self.compose_min_unique_tokens = max(1, int(compose["min_unique_tokens"]))
            except (TypeError, ValueError):
                pass
        if "max_compose_per_observe" in compose:
            try:
                self.max_compose_per_observe = max(1, int(compose["max_compose_per_observe"]))
            except (TypeError, ValueError):
                pass

        short_nd = pr.get("short_seq_near_dup") if isinstance(pr.get("short_seq_near_dup"), dict) else {}
        if "enabled" in short_nd:
            self.short_near_dup_enabled = bool(short_nd["enabled"])
        if "max_length" in short_nd:
            try:
                # max_length is inclusive upper bound for short-window check (default 3 => len < 4)
                self.short_near_dup_max_length = max(2, int(short_nd["max_length"]))
            except (TypeError, ValueError):
                pass
        if "min_run_length" in short_nd:
            try:
                self.short_near_dup_min_run = max(2, int(short_nd["min_run_length"]))
            except (TypeError, ValueError):
                pass

    @staticmethod
    def _atexit_flush(self_ref) -> None:
        """Flush Pattern-owned store if this instance still has dirty durable state."""
        try:
            obj = self_ref() if callable(self_ref) else None
            if obj is None:
                return
            if getattr(obj, "_knowledge_dirty", False):
                obj._save_learned_knowledge()
        except Exception:
            pass

    def _persist_durable_knowledge(self) -> None:
        """Mark dirty and flush so crash without shutdown keeps durable state.

        During observe(), persist is deferred to the end of the call to avoid
        writing the store once per sliding-window update; atexit still covers
        dirty state if the process exits afterward without shutdown().
        """
        self._knowledge_dirty = True
        if getattr(self, "_defer_knowledge_persist", False):
            return
        if not self._saving_knowledge:
            self._save_learned_knowledge()

    @staticmethod
    def _is_cyclic_wrap_of_period(period: List[str], steps: List[str]) -> bool:
        """True when steps rides period's cycle across a wrap boundary (or extends it).

        Genuine contiguous substrings of period (no wrap) return False.
        Exact equality with period returns False (that is the real pattern).
        """
        if not period or not steps or len(period) < 2:
            return False
        period = [str(x) for x in period]
        steps = [str(x) for x in steps]
        if steps == period:
            return False
        n, m = len(steps), len(period)
        for start in range(m):
            if all(steps[i] == period[(start + i) % m] for i in range(n)):
                if n > m:
                    return True  # cyclic extension past one period
                # Same length or shorter: wrap only if the window crosses the seam
                return (start + n) > m
        return False

    @staticmethod
    def _is_rotation(a: List[str], b: List[str]) -> bool:
        if len(a) != len(b) or not a or a == b:
            return False
        n = len(a)
        return any(a[i:] + a[:i] == b for i in range(1, n))

    @staticmethod
    def _looks_like_linear_period(steps: List[str]) -> bool:
        """True for constant-delta / constant-ratio numeric runs (genuine progressions)."""
        if len(steps) < 3:
            return False
        try:
            values = [float(str(s).strip()) for s in steps]
        except (TypeError, ValueError):
            return False
        deltas = [values[i + 1] - values[i] for i in range(len(values) - 1)]
        if deltas and all(abs(d - deltas[0]) < 1e-9 for d in deltas):
            return True
        if all(abs(v) > 1e-12 for v in values[:-1]):
            ratios = [values[i + 1] / values[i] for i in range(len(values) - 1)]
            if all(abs(r - ratios[0]) < 1e-9 for r in ratios):
                return True
        return False

    def _iter_wrap_reference_periods(self):
        """Periods trusted for wrap detection: linear progressions, then other durables.

        Rotations of a linear period are not references (they are wrap noise themselves).
        """
        linear: List[List[str]] = []
        for seq in self.sequences.values():
            period = [str(x) for x in seq.steps]
            if len(period) < 2:
                continue
            if self._looks_like_linear_period(period):
                linear.append(period)
                yield period
        for seq in self.sequences.values():
            period = [str(x) for x in seq.steps]
            if len(period) < 2 or not seq.durable:
                continue
            if self._looks_like_linear_period(period):
                continue
            if any(self._is_rotation(period, L) for L in linear):
                continue
            yield period

    def _is_wrap_noise(self, steps: List[str]) -> bool:
        """Reject cyclic/wrap batch noise (e.g. 2,4,6,8,2) from durable promotion.

        Keeps genuine linear periods (2,4,6,8) and their contiguous substrings
        (2,4,6 / 4,6,8). Rejects seam-crossing windows and cyclic extensions.
        """
        steps = [str(s) for s in steps]
        if len(steps) < 3:
            return False
        # Self: proper prefix that cyclically generates this sequence
        for p in range(2, len(steps)):
            period = steps[:p]
            if all(steps[i] == period[i % p] for i in range(len(steps))):
                return True
        for period in self._iter_wrap_reference_periods():
            if period == steps:
                continue
            if len(period) != len(steps):
                if self._is_cyclic_wrap_of_period(period, steps):
                    return True
                continue
            # Same length: nontrivial rotation of a preferred linear/durable period
            if self._is_rotation(period, steps) and not self._looks_like_linear_period(steps):
                return True
        return False

    def _load_learned_knowledge(self):
        """Load Pattern-owned learned knowledge from the local store.

        This is Pattern's store — not Notus. Genuine learnings (taught opposites /
        behavioral defs, significant sequences, strong co-occurrences) survive restart.
        """
        path = getattr(self, "knowledge_path", None)
        if path is None:
            return
        try:
            path = Path(path)
            if not path.exists():
                return
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return

            opposites = raw.get("learned_opposites") or {}
            if isinstance(opposites, dict):
                cleaned: Dict[str, List[str]] = {}
                for word, opp_list in opposites.items():
                    if not isinstance(word, str) or not isinstance(opp_list, list):
                        continue
                    cleaned[word] = [str(o) for o in opp_list if isinstance(o, (str, int, float))]
                self.learned_opposites = cleaned

            learned_beh = raw.get("learned_behavioral_patterns") or {}
            if isinstance(learned_beh, dict):
                for name, definition in learned_beh.items():
                    if not isinstance(name, str) or not isinstance(definition, dict):
                        continue
                    self.learned_behavioral_patterns[name] = definition
                    signals = definition.get("signals", {})
                    if name not in self.behavioral_patterns:
                        self.behavioral_patterns[name] = BehavioralPattern(
                            name=name,
                            signals=signals if isinstance(signals, dict) else {},
                            occurrences=int(definition.get("occurrences", 0) or 0),
                            confidence=float(definition.get("confidence", 0.0) or 0.0),
                            last_seen=float(definition.get("last_seen", 0.0) or 0.0),
                        )
                    else:
                        self.behavioral_patterns[name].signals = (
                            signals if isinstance(signals, dict) else self.behavioral_patterns[name].signals
                        )

            for seq_data in raw.get("sequences") or []:
                if not isinstance(seq_data, dict):
                    continue
                steps = seq_data.get("steps")
                if not isinstance(steps, list) or len(steps) < 2:
                    continue
                steps_s = [str(s) for s in steps][: self.max_composed_sequence_length]
                key = tuple(steps_s)
                self.sequences[key] = Sequence(
                    steps=steps_s,
                    count=int(seq_data.get("count", 1) or 1),
                    confidence=float(seq_data.get("confidence", 0.6) or 0.6),
                    last_seen=float(seq_data.get("last_seen", time.time()) or time.time()),
                    average_time_between_steps=float(
                        seq_data.get("average_time_between_steps", 0.0) or 0.0
                    ),
                    durable=True,
                )

            # Drop legacy wrap-noise / low-info / short near-dup sequences that should never have been durable
            for key, seq in list(self.sequences.items()):
                steps = list(seq.steps)
                if self._is_low_information_sequence(steps):
                    # Constant / spam sequences: drop entirely from persisted set
                    self.sequences.pop(key, None)
                    continue
                if self._is_wrap_noise(steps) or self._is_short_near_dup_sequence(steps):
                    seq.durable = False
                    # Keep ephemeral for local stats; do not treat as durable knowledge
            for co_data in raw.get("co_occurrences") or []:
                if not isinstance(co_data, dict):
                    continue
                items = co_data.get("items")
                if not isinstance(items, list) or len(items) != 2:
                    continue
                pair = tuple(sorted([str(items[0]), str(items[1])]))
                self.co_occurrences[pair] = CoOccurrence(
                    item_a=pair[0],
                    item_b=pair[1],
                    count=int(co_data.get("count", 1) or 1),
                    strength=float(co_data.get("strength", 0.5) or 0.5),
                    last_seen=float(co_data.get("last_seen", time.time()) or time.time()),
                    contexts=list(co_data.get("contexts") or [])[:5],
                )
            self._knowledge_dirty = False
        except Exception:
            # Corrupt / unreadable store — start empty rather than crash startup
            pass

    def _save_learned_knowledge(self) -> None:
        """Persist Pattern-owned learned knowledge to the local store."""
        path = getattr(self, "knowledge_path", None)
        if path is None:
            return
        if self._saving_knowledge:
            return
        self._saving_knowledge = True
        try:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)

            # Promote significant in-memory discoveries before serialize
            self._promote_significant_to_durable()

            sequences_out = []
            durable_seqs = []
            for s in self.sequences.values():
                steps = list(s.steps)
                if self._is_wrap_noise(steps) or self._is_short_near_dup_sequence(steps):
                    # Never persist cyclic/wrap batch noise or short near-dup junk
                    if s.durable:
                        s.durable = False
                    continue
                if s.durable or s.confidence >= self.persist_sequence_confidence:
                    durable_seqs.append(s)
            # Prefer longer / higher-confidence when soft-capping
            durable_seqs.sort(
                key=lambda s: (1 if s.durable else 0, s.confidence, len(s.steps), s.count),
                reverse=True,
            )
            for seq in durable_seqs[: self.max_durable_sequences]:
                sequences_out.append({
                    "steps": list(seq.steps),
                    "count": int(seq.count),
                    "confidence": float(seq.confidence),
                    "last_seen": float(seq.last_seen),
                    "average_time_between_steps": float(seq.average_time_between_steps),
                    "durable": True,
                })

            co_out = []
            for pair, pattern in self.co_occurrences.items():
                if (
                    pattern.count >= self.base_co_occurrence_threshold
                    and pattern.strength >= self.persist_co_occurrence_strength
                ):
                    co_out.append({
                        "items": list(pair),
                        "count": int(pattern.count),
                        "strength": float(pattern.strength),
                        "last_seen": float(pattern.last_seen),
                        "contexts": list(pattern.contexts)[:5],
                    })

            # Merge occurrence/confidence into learned behavioral defs we own
            learned_beh = dict(self.learned_behavioral_patterns)
            for name, definition in list(learned_beh.items()):
                if not isinstance(definition, dict):
                    continue
                behavior = self.behavioral_patterns.get(name)
                if behavior is None:
                    continue
                merged = dict(definition)
                merged["occurrences"] = int(behavior.occurrences)
                merged["confidence"] = float(behavior.confidence)
                merged["last_seen"] = float(behavior.last_seen)
                learned_beh[name] = merged

            payload = {
                "version": 1,
                "owner": "pattern",
                "learned_opposites": {
                    str(k): [str(x) for x in (v or [])]
                    for k, v in self.learned_opposites.items()
                },
                "learned_behavioral_patterns": learned_beh,
                "sequences": sequences_out,
                "co_occurrences": co_out,
                "saved_at": time.time(),
            }
            tmp = Path(f"{path}.tmp")
            tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            tmp.replace(path)
            self._knowledge_dirty = False
        except Exception:
            pass
        finally:
            self._saving_knowledge = False

    def _promote_significant_to_durable(self) -> None:
        """Mark reliable local discoveries durable so they outlive the working window.

        Cyclic/wrap noise from batch cycling (e.g. 2,4,6,8,2) is never promoted.
        Shorter genuine sequences are promoted first so wrap checks see them.
        """
        changed = False
        # Demote wrap noise / low-info / short near-dup spam that should never stay durable
        for seq in self.sequences.values():
            if seq.durable and (
                self._is_wrap_noise(list(seq.steps))
                or self._is_low_information_sequence(list(seq.steps))
                or self._is_short_near_dup_sequence(list(seq.steps))
            ):
                seq.durable = False
                changed = True

        long_candidates = []
        local_candidates = []
        for seq in self.sequences.values():
            if seq.durable:
                continue
            steps = list(seq.steps)
            if (
                self._is_wrap_noise(steps)
                or self._is_low_information_sequence(steps)
                or self._is_short_near_dup_sequence(steps)
            ):
                continue
            if len(steps) > max(self.local_seq_lengths):
                long_candidates.append(seq)
                continue
            if seq.confidence < self.persist_sequence_confidence:
                continue
            if seq.count < max(3, self.base_sequence_threshold):
                continue
            # Skip exact tilings of a shorter period
            period = self._minimal_period(steps)
            if len(period) < len(steps):
                continue
            local_candidates.append(seq)

        # Prefer linear periods, then shorter, so wrap checks see the real period first
        local_candidates.sort(
            key=lambda s: (
                0 if self._looks_like_linear_period(list(s.steps)) else 1,
                len(s.steps),
                -s.confidence,
                -s.count,
            )
        )
        for seq in local_candidates:
            steps = list(seq.steps)
            if self._is_wrap_noise(steps) or self._is_short_near_dup_sequence(steps):
                continue
            seq.durable = True
            changed = True
        for seq in long_candidates:
            if self._is_wrap_noise(list(seq.steps)):
                continue
            seq.durable = True
            changed = True
        if changed:
            self._knowledge_dirty = True


    def _record_or_update_sequence(
        self,
        steps: List[str],
        avg_time: float = 0.0,
        *,
        durable: bool = False,
        boost_count: int = 1,
    ) -> None:
        """Insert/update a sequence; composed/long sequences are marked durable."""
        if not steps or len(steps) < 2:
            return
        steps = [str(s) for s in steps][: self.max_composed_sequence_length]
        # Refuse constant / low-information spam entirely (no ephemeral flood either)
        if self._is_low_information_sequence(steps):
            return
        # Never durable-promote cyclic/wrap noise or short near-dup junk (p0,t,t)
        if durable and (
            self._is_wrap_noise(steps) or self._is_short_near_dup_sequence(steps)
        ):
            durable = False
        key = tuple(steps)
        now = time.time()
        became_durable = False
        if key in self.sequences:
            seq = self.sequences[key]
            seq.count += boost_count
            seq.last_seen = now
            seq.confidence = min(1.0, seq.count / 5.0)
            if avg_time:
                seq.average_time_between_steps = avg_time
            # Scrub existing durable short near-dups / wrap noise on touch
            if seq.durable and (
                self._is_wrap_noise(steps) or self._is_short_near_dup_sequence(steps)
            ):
                seq.durable = False
                self._knowledge_dirty = True
            want_durable = durable or (
                len(steps) > max(self.local_seq_lengths)
                and not self._is_wrap_noise(steps)
                and not self._is_short_near_dup_sequence(steps)
            )
            if want_durable and not seq.durable:
                seq.durable = True
                became_durable = True
            elif durable:
                seq.durable = True
        else:
            count = max(1, boost_count)
            is_durable = (
                durable or len(steps) > max(self.local_seq_lengths)
            ) and not self._is_wrap_noise(steps) and not self._is_short_near_dup_sequence(steps)
            self.sequences[key] = Sequence(
                steps=steps,
                count=count,
                confidence=min(1.0, count / 5.0) if count > 1 else 0.2,
                last_seen=now,
                average_time_between_steps=avg_time,
                durable=is_durable,
            )
            became_durable = is_durable
        if became_durable:
            # Crash-safe: durable change flushes immediately (not only on shutdown)
            self._persist_durable_knowledge()
    
    def _initialize_default_templates(self):
        """Initialize templates for detecting behavioral patterns"""
        # Lying detection template
        self.behavioral_patterns['lying'] = BehavioralPattern(
            name='lying',
            signals={
                'required': ['contradiction', 'topic_avoidance', 'emotion_mismatch'],
                'optional': ['hesitation', 'defensive_language']
            }
        )
        
        # Stress pattern
        self.behavioral_patterns['stress'] = BehavioralPattern(
            name='stress',
            signals={
                'required': ['negative_emotion', 'short_responses'],
                'optional': ['topic_switching', 'avoidance']
            }
        )
        
        # Excitement pattern
        self.behavioral_patterns['excitement'] = BehavioralPattern(
            name='excitement',
            signals={
                'required': ['positive_emotion', 'increased_verbosity'],
                'optional': ['repetition', 'emphasis']
            }
        )
    
    # ========================================================================
    # LEARNING & TEACHING
    # ========================================================================
    
    def teach_opposite_words(self, word: str, opposites: List[str]):
        """Learn that these words are opposites"""
        if word not in self.learned_opposites:
            self.learned_opposites[word] = []
        
        for opp in opposites:
            if opp not in self.learned_opposites[word]:
                self.learned_opposites[word].append(opp)
        self._knowledge_dirty = True
        self._save_learned_knowledge()
    
    def teach_behavioral_pattern(self, pattern_name: str, definition: Dict[str, Any]):
        """Learn a new behavioral pattern definition"""
        self.learned_behavioral_patterns[pattern_name] = definition
        
        # Create or update pattern
        if pattern_name not in self.behavioral_patterns:
            self.behavioral_patterns[pattern_name] = BehavioralPattern(
                name=pattern_name,
                signals=definition.get('signals', {})
            )
        else:
            # Update existing pattern
            self.behavioral_patterns[pattern_name].signals = definition.get('signals', {})
        self._knowledge_dirty = True
        self._save_learned_knowledge()
    
    def update_pattern_understanding(self, pattern_name: str, additional_signals: List[str]):
        """Add new signals to understanding of a pattern"""
        if pattern_name in self.behavioral_patterns:
            current_signals = self.behavioral_patterns[pattern_name].signals
            optional = current_signals.get('optional', [])
            optional.extend(additional_signals)
            current_signals['optional'] = list(set(optional))  # Remove duplicates
    
    # ========================================================================
    # BOREDOM & PAREIDOLIA
    # ========================================================================
    
    def update_boredom(self):
        """Update boredom level - increases when no patterns found"""
        current_time = time.time()
        time_since_pattern = current_time - self.last_pattern_time
        
        if time_since_pattern > 60:  # No patterns for a minute
            self.boredom_level = min(1.0, self.boredom_level + 0.1)
        else:
            self.boredom_level = max(0.0, self.boredom_level - 0.05)
        
        # When bored, lower thresholds (see patterns more easily)
        if self.boredom_level > 0.5:
            self._enable_pareidolia_mode()
    
    def _enable_pareidolia_mode(self):
        """When bored, start seeing patterns in weak signals"""
        # Look for speculative patterns in recent data
        if len(self.recent_items) < 3:
            return
        
        # Pick random recent items and create speculative connection
        sample = random.sample(list(self.recent_items), min(3, len(self.recent_items)))
        items = [item[0] for item in sample]
        
        # Create speculative pattern
        pattern = PareidoliaPattern(
            description=f"Maybe {items[0]} connects to {items[1]} somehow",
            confidence=0.2 + (self.boredom_level * 0.3),
            signals=items
        )
        
        self.pareidolia_patterns.append(pattern)
        
        # Limit pareidolia patterns
        if len(self.pareidolia_patterns) > 10:
            self.pareidolia_patterns = self.pareidolia_patterns[-10:]
    
    # ========================================================================
    # MULTI-STEP SEQUENCE DETECTION
    # ========================================================================
    
    def detect_multi_step_sequences(self):
        """Detect A→B→C→D sequences inside the working window, then compose beyond it.

        Working window stays bounded. Significant / composed sequences become durable
        so growth is not lost when observations scroll out of the window.
        """
        if len(self.recent_items) < 3:
            self._compose_sequences_beyond_window()
            return
        
        recent_list = list(self.recent_items)[-self.sequence_detect_slice:]

        # Local discovery: manageable lengths inside the observation slice
        for seq_length in self.local_seq_lengths:
            if len(recent_list) < seq_length:
                continue

            for i in range(len(recent_list) - seq_length + 1):
                steps = [recent_list[i + j][0] for j in range(seq_length)]
                times = [recent_list[i + j][1] for j in range(seq_length)]

                time_diffs = [times[j + 1] - times[j] for j in range(len(times) - 1)]
                avg_time = sum(time_diffs) / len(time_diffs) if time_diffs else 0

                if avg_time > self.max_sequence_time_gap:  # Too far apart
                    continue

                self._record_or_update_sequence(steps, avg_time)

        # Grow durable patterns past the immediate observation window
        self._compose_sequences_beyond_window()
        self._promote_significant_to_durable()
        if self._knowledge_dirty:
            self._persist_durable_knowledge()

    @staticmethod
    def _is_periodic_repeat(base: List[str], extended: List[str]) -> bool:
        """True when extended is just base tiled (wrap growth, not real lengthening)."""
        if not base or len(extended) <= len(base):
            return False
        period = len(base)
        return all(extended[i] == base[i % period] for i in range(len(extended)))

    @staticmethod
    def _minimal_period(steps: List[str]) -> List[str]:
        """Smallest period that tiles `steps`, or steps itself."""
        n = len(steps)
        for p in range(1, n // 2 + 1):
            if n % p == 0 and steps[:p] * (n // p) == steps:
                return steps[:p]
        return list(steps)

    @staticmethod
    def _token_diversity(steps: List[str]) -> float:
        """Fraction of unique tokens in steps (0..1)."""
        if not steps:
            return 0.0
        normalized = [str(s) for s in steps]
        return len(set(normalized)) / float(len(normalized))

    @staticmethod
    def _dominant_token_fraction(steps: List[str]) -> float:
        """Share of the most common token (1.0 = constant sequence)."""
        if not steps:
            return 0.0
        counts: Dict[str, int] = {}
        for s in steps:
            key = str(s)
            counts[key] = counts.get(key, 0) + 1
        return max(counts.values()) / float(len(steps))

    def _is_low_information_sequence(self, steps: List[str]) -> bool:
        """True for constant / same-token-dominated / low-diversity spam sequences.

        Used to refuse compose growth and durable promotion so repeated-token
        feeds cannot flood composed patterns. Genuine progressions (a1..a8,
        2,4,6,8) stay accepted.
        """
        steps = [str(s) for s in steps]
        if len(steps) < 2:
            return False
        uniq = len(set(steps))
        min_unique = getattr(self, "compose_min_unique_tokens", 2)
        if uniq < min_unique:
            return True
        dominant_cap = getattr(self, "max_dominant_token_fraction", 0.6)
        if len(steps) >= 4 and self._dominant_token_fraction(steps) >= dominant_cap:
            return True
        diversity_floor = getattr(self, "min_compose_token_diversity", 0.35)
        if len(steps) >= 5 and self._token_diversity(steps) < diversity_floor:
            return True
        return False

    def _is_short_near_dup_sequence(self, steps: List[str]) -> bool:
        """True for short token-run near-dups (e.g. p0,t,t / x,t,t).

        Targeted durability scrub only: length <= short_near_dup_max_length (default 3,
        i.e. len < 4) with >=2 unique tokens and an adjacent repeated-token run.
        Does NOT raise a blanket short-sequence diversity floor — genuine shorts like
        2,4,6 / a1,a2,a3 / a,b,a stay eligible for durable promotion.
        """
        if not getattr(self, "short_near_dup_enabled", True):
            return False
        steps = [str(s) for s in steps]
        max_len = int(getattr(self, "short_near_dup_max_length", 3))
        min_run = int(getattr(self, "short_near_dup_min_run", 2))
        if len(steps) < 2 or len(steps) > max_len:
            return False
        if len(set(steps)) < 2:
            # Constants are handled by _is_low_information_sequence
            return False
        run = 1
        for i in range(1, len(steps)):
            if steps[i] == steps[i - 1]:
                run += 1
                if run >= min_run:
                    return True
            else:
                run = 1
        return False

    def _would_be_cyclic_wrap(self, new_steps: List[str]) -> bool:
        """Reject composed results that are just cycling an already-known durable period."""
        if len(new_steps) < 2:
            return False
        if self._is_wrap_noise(list(new_steps)):
            return True
        own = self._minimal_period(new_steps)
        if len(own) < len(new_steps) and self._is_periodic_repeat(own, new_steps):
            return True
        for seq in self.sequences.values():
            if not seq.durable:
                continue
            period = self._minimal_period(list(seq.steps))
            if len(period) < 2:
                continue
            if self._is_cyclic_wrap_of_period(period, list(new_steps)):
                return True
            for i in range(len(period)):
                rot = period[i:] + period[:i]
                if len(new_steps) > len(rot) and self._is_periodic_repeat(rot, new_steps):
                    return True
        return False


    def _compose_sequences_beyond_window(self):
        """Extend durable sequences when the window ends with a true continuation.

        Example: durable [a1..a5] scrolled out; fresh ends with [a4,a5,a6,a7,a8]
        → compose [a1..a8]. Requires overlap>=2 and that the full durable sequence
        is no longer contiguous in the working window (so trailing junk is not glued).

        Tightening vs low-info / same-token spam:
        - Refuse constant or token-dominated extensions and results.
        - Prefer one best parent per (overlap suffix, extension) so shared-suffix
          near-duplicates do not fan out into many composed patterns.
        - Cap new composed records per observe via max_compose_per_observe.
        """
        if not self.recent_items:
            return
        fresh = [item for item, _ts in list(self.recent_items)[-self.sequence_detect_slice:]]
        if len(fresh) < 3:
            return
        max_grow = max(self.local_seq_lengths)
        min_overlap = 2

        existing = [
            (list(seq.steps), seq)
            for seq in list(self.sequences.values())
            if seq.durable and len(seq.steps) >= min_overlap
        ]
        # (score, anchor_key, new_steps, seq) — one winner per anchor later
        candidates = []
        for steps, seq in existing:
            if len(steps) >= self.max_composed_sequence_length:
                continue
            if len(self._minimal_period(steps)) < len(steps):
                continue
            if self._is_low_information_sequence(steps):
                continue
            # Still fully visible in the window → reinforce only
            fully_visible = any(
                fresh[i : i + len(steps)] == steps
                for i in range(0, len(fresh) - len(steps) + 1)
            )
            if fully_visible:
                seq.last_seen = time.time()
                continue

            matched = False
            for overlap in range(min(len(steps), len(fresh) - 1), min_overlap - 1, -1):
                for ext_len in range(1, min(max_grow, len(fresh) - overlap) + 1):
                    segment = fresh[-(overlap + ext_len) :]
                    if segment[:overlap] != steps[-overlap:]:
                        continue
                    extension = segment[overlap:]
                    if not extension:
                        continue
                    # Repeated-token / low-info extensions must not grow chains
                    if self._is_low_information_sequence(extension):
                        continue
                    # Do not extend a trailing run of the same token (…,x + x/x,x,…)
                    if steps and all(str(t) == str(steps[-1]) for t in extension):
                        continue
                    # Do not re-append a segment already inside the parent (window re-tile)
                    ext_list = [str(t) for t in extension]
                    parent_s = [str(t) for t in steps]
                    if len(ext_list) >= 2 and any(
                        parent_s[i : i + len(ext_list)] == ext_list
                        for i in range(0, len(parent_s) - len(ext_list) + 1)
                    ):
                        continue
                    new_steps = steps + extension
                    if len(new_steps) > self.max_composed_sequence_length:
                        new_steps = new_steps[: self.max_composed_sequence_length]
                    if new_steps == steps or self._would_be_cyclic_wrap(new_steps):
                        continue
                    if self._is_low_information_sequence(new_steps):
                        continue
                    score = (
                        len(steps),
                        float(seq.confidence),
                        self._token_diversity(steps),
                        int(seq.count),
                    )
                    anchor = (tuple(steps[-overlap:]), tuple(extension))
                    candidates.append((score, anchor, new_steps, seq))
                    matched = True
                    break
                if matched:
                    break

        if not candidates:
            return

        # Prefer extending one durable chain per fresh anchor (drop near-dup parents)
        best_by_anchor = {}
        for score, anchor, new_steps, seq in candidates:
            prev = best_by_anchor.get(anchor)
            if prev is None or score > prev[0]:
                best_by_anchor[anchor] = (score, new_steps, seq)

        winners = sorted(best_by_anchor.values(), key=lambda t: t[0], reverse=True)
        cap = getattr(self, "max_compose_per_observe", 4)
        seen_results = set()
        composed_n = 0
        for _score, new_steps, seq in winners:
            key = tuple(new_steps)
            if key in seen_results:
                continue
            seen_results.add(key)
            self._record_or_update_sequence(
                new_steps,
                seq.average_time_between_steps,
                durable=True,
                boost_count=max(1, min(seq.count, 3)),
            )
            composed_n += 1
            if composed_n >= cap:
                break


    def _prune_ephemeral_sequences(self) -> None:
        """Keep working-memory sequences bounded; never drop durable learnings."""
        durable_items = [(k, v) for k, v in self.sequences.items() if v.durable]
        ephemeral = [(k, v) for k, v in self.sequences.items() if not v.durable]
        max_ephemeral = 100
        if len(ephemeral) > max_ephemeral:
            ephemeral.sort(key=lambda kv: (kv[1].confidence, kv[1].count, kv[1].last_seen))
            ephemeral = ephemeral[-max_ephemeral:]
        if len(durable_items) > self.max_durable_sequences:
            durable_items.sort(
                key=lambda kv: (kv[1].confidence, len(kv[1].steps), kv[1].count),
                reverse=True,
            )
            durable_items = durable_items[: self.max_durable_sequences]
        self.sequences = {**dict(durable_items), **dict(ephemeral)}


    # ========================================================================
    # BEHAVIORAL PATTERN DETECTION
    # ========================================================================
    
    def detect_behavioral_patterns(self, current_data: Dict[str, Any]):
        """Detect complex behavioral patterns"""
        current_time = time.time()
        
        # Query Notus for learned behavioral patterns
        try:
            notus_patterns = self._query_lobe('notus', {'type': 'get_behavioral_patterns'})
            if notus_patterns and notus_patterns.get('status') == 'success':
                learned = notus_patterns.get('patterns', [])
                for pattern_data in learned:
                    if isinstance(pattern_data, dict) and pattern_data.get('name'):
                        self.behavioral_patterns[pattern_data['name']] = BehavioralPattern(
                            name=pattern_data['name'],
                            signals=pattern_data.get('signals', {}),
                            occurrences=pattern_data.get('occurrences', 0),
                            last_seen=pattern_data.get('last_seen', current_time),
                            confidence=pattern_data.get('confidence', 0.5)
                        )
        except Exception:
            pass
        
        # Extract current signals
        signals_present = self._extract_behavioral_signals(current_data)
        
        if not signals_present:
            return
        
        # Check each behavioral pattern template
        for pattern_name, pattern in self.behavioral_patterns.items():
            # Check if required signals are present
            required = pattern.signals.get('required', [])
            optional = pattern.signals.get('optional', [])
            
            required_count = sum(1 for sig in required if sig in signals_present)
            optional_count = sum(1 for sig in optional if sig in signals_present)
            
            # Need at least 2 required signals OR 1 required + 2 optional
            if required_count >= 2 or (required_count >= 1 and optional_count >= 2):
                # Pattern detected
                pattern.occurrences += 1
                pattern.last_seen = current_time
                pattern.confidence = min(1.0, pattern.occurrences / 3.0)
                pattern.examples.append({
                    'signals': signals_present,
                    'timestamp': current_time,
                    'data': current_data.get('statement', '')
                })
                
                # Limit examples
                if len(pattern.examples) > 10:
                    pattern.examples = pattern.examples[-10:]
                
                self.last_pattern_time = current_time
    
    def _extract_behavioral_signals(self, data: Dict[str, Any]) -> List[str]:
        """Extract behavioral signals from current data"""
        signals = []
        
        statement = data.get('statement', '')
        emotion = data.get('emotions', data.get('emotion', {}))  # Handle both keys
        words = data.get('words', [])
        topics = data.get('topics', [])
        
        # Check for contradictions
        if statement and self._has_recent_contradiction(statement):
            signals.append('contradiction')
        
        # Check emotion mismatch
        if emotion and words and self._emotion_word_mismatch(emotion, words):
            signals.append('emotion_mismatch')
        
        # Check topic avoidance
        if topics and self._topic_avoidance_detected(topics):
            signals.append('topic_avoidance')
        
        # Check hesitation
        if words and self._hesitation_detected(words):
            signals.append('hesitation')
        
        # Emotion signals
        emotion_type = emotion.get('type', 'neutral') if isinstance(emotion, dict) else 'neutral'
        emotion_intensity = emotion.get('intensity', 0) if isinstance(emotion, dict) else 0
        
        if emotion_intensity > 0.6:
            if emotion_type in ['happy', 'excited', 'joy']:
                signals.append('positive_emotion')
            elif emotion_type in ['sad', 'angry', 'worried', 'scared']:
                signals.append('negative_emotion')
        
        # Response length signals
        if len(words) > 30:
            signals.append('increased_verbosity')
        elif len(words) < 5 and len(words) > 0:
            signals.append('short_responses')
        
        # Defensive language
        defensive_words = ['actually', 'honestly', 'trust me', 'believe me', 'i swear']
        if any(d in ' '.join(words).lower() for d in defensive_words):
            signals.append('defensive_language')
        
        return signals
    
    def _has_recent_contradiction(self, statement: str) -> bool:
        """Check if statement contradicts recent statements"""
        if not statement:
            return False
        
        # Query Notus for all past contradictions
        try:
            notus_contradict = self._query_lobe('notus', {'type': 'get_contradictions', 'statement': statement})
            if notus_contradict and notus_contradict.get('status') == 'success':
                past_contradictions = notus_contradict.get('contradictions', [])
                if past_contradictions:
                    return True
        except Exception:
            pass
        
        if len(self.statement_history) == 0:
            return False
        
        # Combine learned opposites with defaults
        opposites = {
            'love': ['hate', 'dislike'],
            'hate': ['love', 'like'],
            'like': ['hate', 'dislike'],
            'yes': ['no'],
            'no': ['yes'],
            'good': ['bad', 'terrible'],
            'bad': ['good', 'great'],
            'happy': ['sad', 'unhappy'],
            'sad': ['happy'],
            'agree': ['disagree'],
            'want': ['dont want', "don't want"],
        }
        
        # Add learned opposites (overrides defaults)
        for word, opposite_list in self.learned_opposites.items():
            if word in opposites:
                opposites[word].extend(opposite_list)
            else:
                opposites[word] = opposite_list
        
        statement_lower = statement.lower()
        statement_words = set(statement_lower.split())
        
        for past_statement, past_time in list(self.statement_history)[-10:]:
            past_lower = past_statement.lower()
            past_words = set(past_lower.split())
            
            # Check for opposite words about same subject
            for word in statement_words:
                if word in opposites:
                    for opposite in opposites[word]:
                        if opposite in past_lower or opposite in past_words:
                            # Found contradiction
                            self.contradictions.append(Contradiction(
                                statement_a=past_statement,
                                statement_b=statement,
                                timestamp_a=past_time,
                                timestamp_b=time.time(),
                                severity=0.8
                            ))
                            return True
            
            # Also check reverse
            for word in past_words:
                if word in opposites:
                    for opposite in opposites[word]:
                        if opposite in statement_lower or opposite in statement_words:
                            self.contradictions.append(Contradiction(
                                statement_a=past_statement,
                                statement_b=statement,
                                timestamp_a=past_time,
                                timestamp_b=time.time(),
                                severity=0.8
                            ))
                            return True
                    
        return False
    
    def _emotion_word_mismatch(self, emotion: Dict, words: List[str]) -> bool:
        """Check if emotion doesn't match word choice"""
        if not emotion or not words:
            return False
        
        emotion_type = emotion.get('type', 'neutral')
        words_lower = [w.lower() for w in words]
        
        # Positive emotion but negative words
        positive_emotions = ['happy', 'excited', 'joy']
        negative_words = ['hate', 'terrible', 'awful', 'bad', 'sad', 'angry']
        
        if emotion_type in positive_emotions and any(w in words_lower for w in negative_words):
            return True
        
        # Negative emotion but positive words
        negative_emotions = ['sad', 'angry', 'worried']
        positive_words = ['great', 'wonderful', 'amazing', 'love', 'happy']
        
        if emotion_type in negative_emotions and any(w in words_lower for w in positive_words):
            return True
        
        return False
    
    def _topic_avoidance_detected(self, current_topics: List[str]) -> bool:
        """Check if topics are being avoided"""
        if len(self.recent_topics) < 5:
            return False
        
        # Check if same topic keeps coming up but responses are short
        topic_counts = defaultdict(int)
        for topic_list, timestamp in list(self.recent_topics)[-10:]:
            for topic in topic_list:
                topic_counts[topic] += 1
        
        # If a topic comes up 3+ times recently, might be avoidance
        for topic, count in topic_counts.items():
            if count >= 3 and topic not in current_topics:
                return True
        
        return False
    
    def _hesitation_detected(self, words: List[str]) -> bool:
        """Detect hesitation in word choice"""
        hesitation_words = ['um', 'uh', 'well', 'maybe', 'perhaps', 'kind of', 'sort of', 'i guess']
        words_lower = [w.lower() for w in words]
        
        hesitation_count = sum(1 for h in hesitation_words if h in ' '.join(words_lower))
        return hesitation_count >= 2
    
    # ========================================================================
    # META-PATTERN DETECTION
    # ========================================================================
    
    def detect_meta_patterns(self):
        """Detect patterns about patterns"""
        # Query Notus for historical meta-patterns
        try:
            notus_meta = self._query_lobe('notus', {'type': 'get_meta_patterns'})
            if notus_meta and notus_meta.get('status') == 'success':
                historical = notus_meta.get('meta_patterns', [])
                # Use historical meta-patterns to inform detection
        except Exception:
            pass
        # Pattern: Certain sequences lead to certain behavioral patterns
        for seq_key, sequence in self.sequences.items():
            if sequence.confidence < 0.5:
                continue
            
            # Check what behavioral patterns occur after this sequence
            for behavior_name, behavior in self.behavioral_patterns.items():
                if behavior.occurrences > 0:
                    # Create meta-pattern
                    meta = MetaPattern(
                        description=f"Sequence {' → '.join(sequence.steps[:3])} often precedes {behavior_name}",
                        patterns_involved=[str(seq_key), behavior_name],
                        meta_confidence=0.6
                    )
                    
                    # Check if already exists
                    if not any(m.description == meta.description for m in self.meta_patterns):
                        self.meta_patterns.append(meta)
        
        # Limit meta-patterns
        if len(self.meta_patterns) > 20:
            self.meta_patterns = self.meta_patterns[-20:]
    
    # ========================================================================
    # MAIN OBSERVATION FUNCTION
    # ========================================================================
    
    def observe(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # Query Notus for past observations to compare
        try:
            notus_past = self._query_lobe('notus', {'type': 'get_past_observations', 'data': data})
            if notus_past and notus_past.get('status') == 'success':
                past_obs = notus_past.get('observations', [])
                # Compare current observation to past ones
        except Exception:
            pass
        """
        Observe data and detect all types of patterns
        data should include: items, emotions, words, statement, topics
        """
        self._defer_knowledge_persist = True
        try:
            return self._observe_body(data)
        finally:
            self._defer_knowledge_persist = False
            if self._knowledge_dirty and not self._saving_knowledge:
                self._save_learned_knowledge()

    def _observe_body(self, data: Dict[str, Any]) -> Dict[str, Any]:
        current_time = time.time()
        
        items = data.get('items', [])
        emotions = data.get('emotions', {})
        words = data.get('words', [])
        statement = data.get('statement', '')
        topics = data.get('topics', [])
        
        patterns_found = {
            'co_occurrences': [],
            'sequences': [],
            'behavioral': [],
            'contradictions': [],
            'meta_patterns': [],
            'pareidolia': [],
            'new_patterns': False
        }
        
        # Update history
        for item in items:
            self.recent_items.append((item, current_time))
        
        if emotions:
            self.recent_emotions.append((emotions, current_time))
        
        if topics:
            self.recent_topics.append((topics, current_time))
        
        if words:
            self.recent_word_choices.extend([(w, current_time) for w in words])
        
        if statement:
            self.statement_history.append((statement, current_time))
        
        # Detect basic co-occurrences
        for i, item_a in enumerate(items):
            for item_b in items[i+1:]:
                self._record_co_occurrence(item_a, item_b, current_time, statement)
        
        # Detect multi-step sequences
        self.detect_multi_step_sequences()
        
        # Detect behavioral patterns
        self.detect_behavioral_patterns(data)
        
        # Detect meta-patterns
        self.detect_meta_patterns()
        
        # Update boredom and check for pareidolia
        self.update_boredom()
        
        # Decay old patterns
        if current_time - self.last_decay > 60:
            self._decay_patterns()
            self.last_decay = current_time
        
        # Collect detected patterns
        threshold = self.base_co_occurrence_threshold * (1 - self.boredom_level * 0.5)
        
        for pair, pattern in self.co_occurrences.items():
            if pattern.count >= threshold:
                patterns_found['co_occurrences'].append({
                    'items': list(pair),
                    'count': pattern.count,
                    'strength': pattern.strength
                })
        
        for seq_key, sequence in self.sequences.items():
            if sequence.confidence >= 0.4:
                patterns_found['sequences'].append({
                    'steps': sequence.steps,
                    'confidence': sequence.confidence,
                    'count': sequence.count
                })
        
        for name, behavior in self.behavioral_patterns.items():
            if behavior.confidence >= 0.5:
                patterns_found['behavioral'].append({
                    'name': name,
                    'confidence': behavior.confidence,
                    'occurrences': behavior.occurrences
                })
        
        # Recent contradictions
        patterns_found['contradictions'] = [
            {
                'statement_a': c.statement_a,
                'statement_b': c.statement_b,
                'severity': c.severity
            }
            for c in self.contradictions[-5:]
        ]
        
        # Meta-patterns
        patterns_found['meta_patterns'] = [
            {
                'description': m.description,
                'confidence': m.meta_confidence
            }
            for m in self.meta_patterns[-5:]
        ]
        
        # Pareidolia patterns (speculative)
        patterns_found['pareidolia'] = [
            {
                'description': p.description,
                'confidence': p.confidence,
                'speculative': p.is_speculative
            }
            for p in self.pareidolia_patterns[-3:]
        ]
        
        # Check if new patterns emerged
        if any([
            patterns_found['behavioral'],
            patterns_found['meta_patterns'],
            len(patterns_found['sequences']) > len(self.sequences) * 0.8
        ]):
            patterns_found['new_patterns'] = True
            self.last_pattern_time = current_time

        # Promote + prune; flush Pattern store when durable knowledge changed
        self._promote_significant_to_durable()
        self._prune_ephemeral_sequences()
        if self._knowledge_dirty:
            self._persist_durable_knowledge()
        
        return patterns_found
    
    def _record_co_occurrence(self, item_a: str, item_b: str, timestamp: float, context: str = ""):
        """Record co-occurrence with context"""
        pair = tuple(sorted([item_a, item_b]))
        
        if pair in self.co_occurrences:
            pattern = self.co_occurrences[pair]
            pattern.count += 1
            pattern.last_seen = timestamp
            pattern.strength = min(1.0, pattern.count / 10.0)
            if context and len(pattern.contexts) < 5:
                pattern.contexts.append(context)
        else:
            pattern = CoOccurrence(
                item_a=pair[0],
                item_b=pair[1],
                count=1,
                strength=0.1,
                last_seen=timestamp,
                contexts=[context] if context else []
            )
            self.co_occurrences[pair] = pattern
    
    # ========================================================================
    # SIGNIFICANT PATTERNS (FILTERED)
    # ========================================================================
    
    def get_significant_patterns_only(self) -> Dict[str, Any]:
        """Return only significant patterns for reasoning"""
        significant = {
            'strong_co_occurrences': [],
            'reliable_sequences': [],
            'behavioral_patterns': [],
            'contradictions': [],
            'meta_patterns': []
        }
        
        # Strong co-occurrences
        for pair, pattern in self.co_occurrences.items():
            if pattern.count >= self.base_co_occurrence_threshold and pattern.strength >= 0.5:
                significant['strong_co_occurrences'].append({
                    'items': list(pair),
                    'strength': pattern.strength,
                    'count': pattern.count
                })
        
        # Reliable sequences (include durable composed patterns; exclude wrap / short near-dup noise)
        for seq_key, seq in self.sequences.items():
            steps = list(seq.steps)
            if self._is_wrap_noise(steps) or self._is_short_near_dup_sequence(steps):
                continue
            if seq.confidence >= 0.6 or (seq.durable and seq.confidence >= 0.4):
                significant['reliable_sequences'].append({
                    'steps': seq.steps,
                    'confidence': seq.confidence,
                    'durable': bool(seq.durable),
                })
        
        # Confirmed behavioral patterns
        for name, behavior in self.behavioral_patterns.items():
            if behavior.confidence >= 0.6:
                significant['behavioral_patterns'].append({
                    'name': name,
                    'confidence': behavior.confidence,
                    'occurrences': behavior.occurrences
                })
        
        # High severity contradictions
        significant['contradictions'] = [
            {
                'statement_a': c.statement_a,
                'statement_b': c.statement_b,
                'severity': c.severity
            }
            for c in self.contradictions if c.severity > 0.6
        ][-5:]
        
        # Strong meta-patterns
        significant['meta_patterns'] = [
            {
                'description': m.description,
                'confidence': m.meta_confidence
            }
            for m in self.meta_patterns if m.meta_confidence > 0.5
        ][-5:]
        
        return significant
    
    # ========================================================================
    # PATTERN DECAY
    # ========================================================================
    
    def _decay_patterns(self):
        """Fade patterns that haven't been reinforced"""
        current_time = time.time()
        
        # Decay co-occurrences
        to_remove = []
        for key, pattern in self.co_occurrences.items():
            time_since = current_time - pattern.last_seen
            if time_since > 300:
                pattern.count = max(0, pattern.count - 1)
                pattern.strength *= (1.0 - self.decay_rate)
                if pattern.count == 0 or pattern.strength < 0.01:
                    to_remove.append(key)
        
        for key in to_remove:
            del self.co_occurrences[key]
        
        # Decay sequences — durable/significant learnings resist eviction
        to_remove = []
        for key, seq in self.sequences.items():
            if seq.durable or seq.confidence >= self.persist_sequence_confidence:
                # Light touch only; never delete durable from working memory here
                time_since = current_time - seq.last_seen
                if time_since > 3600:
                    seq.confidence = max(self.persist_sequence_confidence, seq.confidence * (1.0 - self.decay_rate * 0.25))
                continue
            time_since = current_time - seq.last_seen
            if time_since > 600:
                seq.count = max(0, seq.count - 1)
                seq.confidence *= (1.0 - self.decay_rate)
                if seq.count == 0:
                    to_remove.append(key)
        
        for key in to_remove:
            del self.sequences[key]
        
        # Decay behavioral patterns
        for name, behavior in self.behavioral_patterns.items():
            time_since = current_time - behavior.last_seen
            if time_since > 300:
                behavior.confidence *= (1.0 - self.decay_rate * 0.5)
    
    # ========================================================================
    # STATISTICS
    # ========================================================================
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics"""
        return {
            'total_co_occurrences': len(self.co_occurrences),
            'strong_co_occurrences': sum(1 for p in self.co_occurrences.values() 
                                        if p.count >= self.base_co_occurrence_threshold),
            'total_sequences': len(self.sequences),
            'multi_step_sequences': sum(1 for s in self.sequences.values() if len(s.steps) >= 3),
            'behavioral_patterns_detected': sum(1 for b in self.behavioral_patterns.values() 
                                               if b.confidence > 0.5),
            'contradictions_found': len(self.contradictions),
            'meta_patterns': len(self.meta_patterns),
            'pareidolia_patterns': len(self.pareidolia_patterns),
            'boredom_level': self.boredom_level,
            'recent_items': len(self.recent_items)
        }
    
    # ========================================================================
    # DIRECT FUNCTION CALL COMMUNICATION (NO SOCKETS)
    # ========================================================================
    
    def _register_with_thalamus(self):
        """Register with Thalamus - DIRECT FUNCTION CALL (NO SOCKETS)"""
        try:
            result = self.thalamus.register_lobe('pattern', self)
            if result.get('status') == 'success':
                print("✅ Pattern Recognition registered with Thalamus (direct function calls)")
                return True
            return False
        except Exception as e:
            print(f"⚠️  Failed to register with Thalamus: {e}")
            return False
    
    def start(self):
        """Start pattern recognition - register with Thalamus (NO SOCKETS)"""
        print(f"🔍 Advanced Pattern Recognition: Registering with Thalamus...")
        print(f"   Behavioral patterns, multi-step sequences, meta-patterns")
        print(f"   Pareidolia mode, contradiction tracking")
        print(f"   Communication: Direct function calls (NO SOCKETS)")
        
        # Register with Thalamus
        if not self._register_with_thalamus():
            print("❌ Failed to register with Thalamus")
            return
        
        # Keep running (Thalamus calls us directly, no listening loop needed)
        while self.running:
            time.sleep(0.1)
    
    def _query_lobe(self, lobe_name: str, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Query a lobe through Thalamus - DIRECT FUNCTION CALL"""
        try:
            msg_type = message.get('type', 'query')
            return self.thalamus.send_message(lobe_name, msg_type, message)
        except Exception:
            return None
    
    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming message.

        Thalamus envelopes use ``content``; older callers may still pass ``data``.
        Accept either so the live path and direct tests both work.
        """
        msg_type = message.get('type')
        payload = message.get('content') if isinstance(message.get('content'), dict) else {}
        if not payload and isinstance(message.get('data'), dict):
            payload = message.get('data') or {}
        if not isinstance(payload, dict):
            payload = {}
        # Nested ``data`` inside content (explicit observe envelope).
        nested = payload.get('data') if isinstance(payload.get('data'), dict) else None
        
        # FIX: add health probe
        if msg_type == 'health':
            return {'status': 'success', 'healthy': True, 'pid': os.getpid(), 'content': {'healthy': True}}
        
        if msg_type == 'observe' or msg_type == 'process_input':
            data = nested if nested is not None else payload
            if not data and msg_type == 'process_input':
                data = {}
            patterns = self.observe(data if isinstance(data, dict) else {})
            return {'status': 'success', 'patterns': patterns, 'content': {'patterns': patterns}}
            
        elif msg_type in ('get_significant', 'get_significant_patterns'):
            significant = self.get_significant_patterns_only()
            return {
                'status': 'success',
                'significant_patterns': significant,
                'content': {'significant_patterns': significant},
            }
            
        elif msg_type == 'get_statistics':
            stats = {'total_co_occurrences': len(self.co_occurrences)}
            return {'status': 'success', 'statistics': stats, 'content': {'statistics': stats}}
            
        else:
            return {'status': 'error', 'message': f'Unknown message type: {msg_type}'}
    
    def shutdown(self):
        """Graceful shutdown — flush Pattern-owned learned knowledge."""
        try:
            self._save_learned_knowledge()
        except Exception:
            pass
        self.running = False
        # No sockets to close

if __name__ == "__main__":
    lobe = AdvancedPatternRecognition()
    try:
        lobe.start()
    except KeyboardInterrupt:
        print("\n🛑 Pattern recognition shutting down...")
        lobe.shutdown()
