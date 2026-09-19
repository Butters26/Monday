#!/usr/bin/env python3
"""
Autonomous Thinking Loop - Generates thoughts without prompting
Monday thinks on her own, not just when spoken to.
"""

import time
import threading
import random
import re
import hashlib
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from thalamus import get_thalamus
from autonomous_selection import AutonomousSelectionMixin, _LIGHT_TURN_RE

@dataclass
class AutonomousThought:
    """A thought generated autonomously"""
    id: str
    content: str
    thought_type: str  # "reflection", "question", "observation", "memory", "feeling"
    trigger: str  # What triggered this thought
    intensity: float  # 0-1 how strong/important
    speak_worthy: bool  # Should this be said out loud?
    timestamp: float
    # Instrumentation / gating metadata
    mode: str = ""
    topic_key: str = ""
    source_memory_id: str = None
    source_appraisal: str = None
    satiation_score: float = 0.0
    speak_satiation_score: float = 0.0
    emotion_before: str = ""
    intensity_before: float = 0.0
    emotion_after: str = ""
    intensity_after: float = 0.0
    relevance_gate_reason: str = ""
    selection_weight: float = 0.0


class AutonomousThinkingLoop(AutonomousSelectionMixin):
    """
    Background process that generates thoughts without prompting.
    Monday has an inner monologue.
    """
    
    def __init__(self, thalamus=None):
        # Prefer an explicit Thalamus (core wiring); fall back to singleton for CLI.
        self.thalamus = thalamus if thalamus is not None else get_thalamus()
        self.running = True
        self._thinking_thread: Optional[threading.Thread] = None
        
        # Thought generation
        self.recent_thoughts: List[AutonomousThought] = []
        self.thought_queue: List[AutonomousThought] = []  # Thoughts waiting to be processed
        
        # Timing — lengthen when wired into core so own-feelings are not spammy
        if thalamus is not None:
            self.min_think_interval = 15.0
            self.max_think_interval = 60.0
        else:
            self.min_think_interval = 5.0
            self.max_think_interval = 30.0
        self.last_thought_time = 0.0
        
        # State
        self.current_mood = "neutral"
        self.current_focus = None  # What Monday is currently thinking about
        self.user_present = False  # Is user actively engaged?
        self.user_last_message_time = 0.0
        # Active conversation user — Notus memories are per-user; ground thoughts there.
        self.current_user_id = "default"
        self.last_user_text = ""
        self.current_conversation_topic = ""

        # Per-topic think/speak satiation (loop-local only; never deletes Notus memory)
        self._think_satiation = {}
        self._think_sat_updated = {}
        self._speak_satiation = {}
        self._speak_sat_updated = {}
        self._topic_last_modes = {}
        self._topic_select_count = {}
        self._topic_last_severity = {}
        self._topic_resolved_at = {}
        self._topic_reactivated_at = {}
        self.thought_traces = []
        self.trace_log_path = None

        # Satiation / gate tunables
        self._THINK_SAT_STEP = 0.28
        self._THINK_SAT_DECAY_HALFLIFE = 180.0
        self._THINK_SAT_SEVERE_CAP = 0.35
        self._SPEAK_SAT_STEP = 0.55
        self._SPEAK_SAT_DECAY_HALFLIFE = 300.0
        self._SPEAK_COOLDOWN_SEC = 120.0
        self._RESOLUTION_DEMOTE = 0.12

        # Register with Thalamus
        self._register_with_thalamus()
        
        # Lock
        self.lock = threading.Lock()
    
    def _register_with_thalamus(self):
        """Register with Thalamus"""
        try:
            result = self.thalamus.register_lobe('autonomous', self)
            if result.get('status') == 'success':
                print("✅ Autonomous Thinking Loop registered with Thalamus")
                return True
            return False
        except Exception as e:
            print(f"⚠️  Failed to register Autonomous Thinking Loop: {e}")
            return False
    
    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming messages (unwrap Thalamus envelope like emotion does)."""
        msg_type = message.get('type')
        raw_content = message.get('content', message)
        if isinstance(raw_content, dict):
            message = {**raw_content, 'type': msg_type}
        else:
            message = {
                **{k: v for k, v in message.items() if k != 'content'},
                'type': msg_type,
                'content': raw_content,
            }
        msg_type = message.get('type')
        
        if msg_type == 'user_active':
            self.user_present = True
            self.user_last_message_time = time.time()
            uid = message.get('user_id')
            if isinstance(uid, str) and uid.strip():
                self.current_user_id = uid.strip()
            text = message.get('text') or message.get('user_input')
            if isinstance(text, str) and text.strip():
                self._note_user_turn(text.strip())
            elif isinstance(message.get('content'), str) and message.get('content').strip():
                # only treat content as text when it looks like user prose, not an envelope
                c = message.get('content').strip()
                if len(c) > 1 and c[0] not in '{[':
                    self._note_user_turn(c)
            return {'status': 'success'}
        
        elif msg_type == 'user_inactive':
            self.user_present = False
            return {'status': 'success'}
        
        elif msg_type == 'set_mood':
            self.current_mood = message.get('mood', 'neutral')
            return {'status': 'success'}
        
        elif msg_type == 'set_focus':
            self.current_focus = message.get('focus')
            return {'status': 'success'}
        
        elif msg_type == 'get_pending_thoughts':
            return self._get_pending_thoughts()

        elif msg_type in ('pop_spoken_aside', 'get_speak_worthy'):
            aside = self.pop_spoken_aside()
            if aside is None:
                return {'status': 'success', 'aside': None, 'thought': None}
            return {'status': 'success', 'aside': aside, 'thought': aside}

        elif msg_type == 'get_recent_thoughts':
            return self._get_recent_thoughts(message.get('limit', 10))
        
        elif msg_type == 'get_thought_traces':
            limit = int(message.get('limit', 50) or 50)
            with self.lock:
                traces = list(self.thought_traces[-limit:])
            return {'status': 'success', 'traces': traces, 'count': len(traces)}

        elif msg_type == 'aside_relevance_gate':
            aside = message.get('aside') or {}
            user_text = message.get('user_text') or message.get('text') or self.last_user_text
            ok, reason = self.aside_passes_relevance_gate(aside, user_text=user_text)
            return {'status': 'success', 'allowed': ok, 'reason': reason}

        elif msg_type == 'health':
            return {'status': 'success', 'healthy': True}
        
        else:
            return {'status': 'error', 'message': f'Unknown message type: {msg_type}'}
    
    def _get_pending_thoughts(self) -> Dict[str, Any]:
        """Get thoughts waiting to be spoken/processed"""
        with self.lock:
            thoughts = [asdict(t) for t in self.thought_queue]
            self.thought_queue = []  # Clear queue
            return {
                'status': 'success',
                'thoughts': thoughts,
                'count': len(thoughts)
            }
    
    def _get_recent_thoughts(self, limit: int) -> Dict[str, Any]:
        """Get recent thoughts"""
        with self.lock:
            thoughts = [asdict(t) for t in self.recent_thoughts[-limit:]]
            return {
                'status': 'success',
                'thoughts': thoughts,
                'count': len(thoughts)
            }
    
    def _generate_thought(self) -> Optional[AutonomousThought]:
        """
        Generate an autonomous thought.
        Score-driven topic selection + mode progression; randomness only breaks ties.
        """
        emotional_state = self._get_emotional_state()
        emotion_before = str(emotional_state.get("emotion") or "neutral")
        try:
            intensity_before = float(emotional_state.get("intensity", 0.5) or 0.5)
        except (TypeError, ValueError):
            intensity_before = 0.5

        self._update_resolution_tracking(emotional_state)
        recent_memories = self._get_recent_memories()
        current_values = self._get_current_values()

        candidate = self._select_thought_candidate(
            emotional_state, recent_memories, current_values
        )
        if not candidate:
            return None

        mode = self._select_mode_for_candidate(candidate, emotional_state)
        content, trigger, thought_type = self._generate_mode_content(
            mode, candidate, emotional_state, recent_memories, current_values
        )
        if not content:
            return None

        topic_key = candidate.get("topic_key") or ""
        think_sat = self._think_sat(topic_key) if topic_key else 0.0
        speak_sat = self._speak_sat(topic_key) if topic_key else 0.0

        speak_worthy, gate_reason = self._evaluate_speak_worthy(
            thought_type=thought_type,
            mode=mode,
            topic_key=topic_key,
            content=content,
            emotional_state=emotional_state,
            candidate=candidate,
            user_text=self.last_user_text,
        )

        try:
            intensity = max(
                float(emotional_state.get("intensity", 0.5) or 0.5),
                0.55 if (
                    (emotional_state.get("unresolved_appraisals") or [])
                    and candidate.get("kind") == "appraisal"
                ) else 0.0,
            )
        except (TypeError, ValueError):
            intensity = 0.5

        mem = candidate.get("memory") if isinstance(candidate.get("memory"), dict) else {}
        appraisal = candidate.get("appraisal") if isinstance(candidate.get("appraisal"), dict) else {}
        source_mem_id = None
        if mem:
            source_mem_id = str(mem.get("id") or mem.get("memory_id") or "") or None
        source_app = str(appraisal.get("event_type") or "") or None if appraisal else None

        return AutonomousThought(
            id=f"thought_{int(time.time() * 1000)}",
            content=content,
            thought_type=thought_type,
            trigger=trigger,
            intensity=intensity,
            speak_worthy=speak_worthy,
            timestamp=time.time(),
            mode=mode,
            topic_key=topic_key,
            source_memory_id=source_mem_id,
            source_appraisal=source_app,
            satiation_score=think_sat,
            speak_satiation_score=speak_sat,
            emotion_before=emotion_before,
            intensity_before=intensity_before,
            relevance_gate_reason=gate_reason,
            selection_weight=float(candidate.get("weight", 0.0) or 0.0),
        )
    
    def _get_emotional_state(self) -> Dict[str, Any]:
        """Get current emotional state from Emotion lobe.

        EmotionProcess get_state returns top-level emotion/intensity (and now
        unresolved_appraisals / last_event_type) — NOT a nested 'state' dict.
        Also try get_emotional_state for PAD/summary fields when useful.
        """
        default = {
            'emotion': 'neutral',
            'intensity': 0.5,
            'valence': 0.0,
            'unresolved_appraisals': [],
            'last_event_type': None,
            'event_history': [],
            'summary': '',
        }
        try:
            result = self.thalamus.send_and_wait(
                'emotion',
                'get_state',
                {}
            )
            if result.get('status') == 'success':
                # Thalamus also mirrors fields under content=
                content = result.get('content') if isinstance(result.get('content'), dict) else {}
                merged = {**content, **{k: v for k, v in result.items() if k not in ('status', 'message', 'content')}}
                # Legacy callers expected result['state'] — accept that too if present.
                nested = merged.get('state') if isinstance(merged.get('state'), dict) else {}
                src = {**default, **nested, **merged}
                emotion = src.get('emotion') or src.get('current_emotion') or 'neutral'
                try:
                    intensity = float(src.get('intensity', 0.5))
                except (TypeError, ValueError):
                    intensity = 0.5
                unresolved = src.get('unresolved_appraisals') or []
                if not isinstance(unresolved, list):
                    unresolved = []
                state = {
                    'emotion': emotion,
                    'intensity': intensity,
                    'valence': float(src.get('valence', src.get('pleasure', 0.0)) or 0.0),
                    'resonance': src.get('resonance', 0.0),
                    'unresolved_appraisals': unresolved,
                    'last_event_type': src.get('last_event_type'),
                    'event_history': src.get('event_history') or [],
                    'summary': src.get('summary') or '',
                }
                # Enrich from get_emotional_state when PAD / tone useful
                try:
                    rich = self.thalamus.send_and_wait(
                        'emotion', 'get_emotional_state', {}
                    )
                    if rich.get('status') == 'success':
                        body = rich.get('content') if isinstance(rich.get('content'), dict) else {}
                        body = {**body, **{k: v for k, v in rich.items() if k not in ('status', 'message', 'content')}}
                        if body.get('emotion'):
                            state['emotion'] = body['emotion']
                        if body.get('intensity') is not None:
                            try:
                                state['intensity'] = float(body['intensity'])
                            except (TypeError, ValueError):
                                pass
                        if body.get('pleasure') is not None:
                            try:
                                state['valence'] = float(body['pleasure'])
                            except (TypeError, ValueError):
                                pass
                        if body.get('emotional_tone'):
                            state['emotional_tone'] = body['emotional_tone']
                except Exception:
                    pass
                return state
        except Exception:
            pass

        return default

    def _primary_unresolved(self, emotional_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Highest-severity unresolved appraisal, if any."""
        unresolved = emotional_state.get('unresolved_appraisals') or []
        if not unresolved:
            return None
        try:
            return max(unresolved, key=lambda u: float(u.get('severity', 0.0)))
        except Exception:
            return unresolved[0] if unresolved else None

    def _get_recent_memories(self) -> List[Dict[str, Any]]:
        """Get recent memories from Notus using message types that exist.

        Prefers get_recent / get_recent_memories, then get_conversation_history,
        then semantic query. Never calls a nonexistent Notus type alone.
        """
        uid = self.current_user_id if isinstance(self.current_user_id, str) and self.current_user_id.strip() else "default"
        attempts = (
            ('get_recent_memories', {'limit': 5, 'user_id': uid}),
            ('get_recent', {'limit': 5, 'user_id': uid}),
            ('get_conversation_history', {'limit': 5, 'user_id': uid}),
            ('query', {'query': 'recent conversation', 'limit': 5, 'user_id': uid}),
        )
        for msg_type, payload in attempts:
            try:
                result = self.thalamus.send_and_wait('notus', msg_type, payload)
                if result.get('status') != 'success':
                    continue
                content = result.get('content') if isinstance(result.get('content'), dict) else {}
                found = (
                    result.get('memories')
                    or content.get('memories')
                    or content.get('results')
                    or content.get('history')
                    or []
                )
                if isinstance(found, list) and found:
                    return found
            except Exception:
                continue
        return []

    @staticmethod
    def _memory_snippet(memory: Dict[str, Any], max_len: int = 140) -> str:
        """Short real memory text for first-person reaction lines."""
        raw = (
            memory.get('content')
            or memory.get('topic')
            or memory.get('note')
            or memory.get('text')
            or ''
        )
        text = str(raw).strip().replace('\n', ' ')
        if not text:
            return ''
        if len(text) > max_len:
            # Prefer keeping distinctive marker-like tokens intact in the kept window.
            m = re.search(r"(MARKER_[A-Za-z0-9_\-]+)", text)
            if m:
                token = m.group(1)
                # Anchor window around the marker when present.
                start = max(0, m.start() - max(20, (max_len - len(token)) // 3))
                window = text[start:start + max_len]
                if len(text) > start + max_len:
                    # Ensure token fully inside window
                    if token not in window:
                        window = text[max(0, m.end() - max_len):m.end()]
                    if not window.endswith(text[-1]) and start + max_len < len(text):
                        if token in window:
                            return window[:-3] + '...' if len(window) >= max_len else window
                    return (window[: max_len - 3] + '...') if len(window) > max_len else window
            head = max(28, (max_len - 3) // 2)
            tail = max(24, max_len - head - 3)
            return text[:head] + '...' + text[-tail:]
        return text

    def _get_current_values(self) -> List[Dict[str, Any]]:
        """Get current values from Value Evolution"""
        try:
            result = self.thalamus.send_and_wait(
                'values',
                'get_values',
                {'min_strength': 0.5}
            )
            if result.get('status') == 'success':
                content = result.get('content') if isinstance(result.get('content'), dict) else {}
                return result.get('values') or content.get('values', [])
        except Exception:
            pass

        return []

    def _decide_thought_type(self, emotional_state: Dict[str, Any]) -> str:
        """Decide what type of thought to generate.

        Prefer feeling / reflection / memory when unresolved appraisals exist
        or intensity is high — not weak generic observation monologue.
        """
        emotion = emotional_state.get('emotion', 'neutral')
        intensity = float(emotional_state.get('intensity', 0.5) or 0.5)
        unresolved = emotional_state.get('unresolved_appraisals') or []

        weights = {
            'reflection': 0.3,
            'question': 0.2,
            'observation': 0.2,
            'memory': 0.15,
            'feeling': 0.15
        }

        if unresolved:
            weights['feeling'] += 0.35
            weights['reflection'] += 0.25
            weights['memory'] += 0.2
            weights['observation'] *= 0.35
            weights['question'] *= 0.5
        elif intensity > 0.7:
            weights['feeling'] += 0.35
            weights['reflection'] += 0.15
        elif emotion in ['curious', 'interested', 'surprised']:
            weights['question'] += 0.3
        elif emotion in ['sad', 'nostalgic', 'melancholic', 'anxious', 'worried']:
            weights['memory'] += 0.25
            weights['feeling'] += 0.15
        elif emotion in ['happy', 'excited', 'euphoric', 'playful']:
            weights['feeling'] += 0.25

        total = sum(weights.values())
        weights = {k: v / total for k, v in weights.items()}

        r = random.random()
        cumulative = 0.0
        for thought_type, weight in weights.items():
            cumulative += weight
            if r < cumulative:
                return thought_type

        return 'reflection'

    def _generate_thought_content(self, thought_type: str, emotional_state: Dict[str, Any],
                                   memories: List[Dict[str, Any]],
                                   values: List[Dict[str, Any]]) -> tuple:
        """Generate thought content grounded in real emotion + real memory when available."""
        emotion = emotional_state.get('emotion', 'neutral')
        intensity = float(emotional_state.get('intensity', 0.5) or 0.5)
        primary = self._primary_unresolved(emotional_state)

        # Real memory text wins when present: first-person reaction to THAT snippet,
        # still colored by unresolved appraisal / emotion from bda4de0.
        usable = self._prefer_grounding_memories(memories, primary)
        if usable and thought_type in ('feeling', 'reflection', 'memory', 'question'):
            return self._generate_memory_rich_thought(
                thought_type, emotion, intensity, usable, primary
            )

        # No memory: keep unresolved event-type grounding.
        if primary and thought_type in ('feeling', 'reflection', 'memory'):
            return self._generate_unresolved_thought(thought_type, emotion, intensity, primary)

        if thought_type == 'reflection':
            return self._generate_reflection(values, emotion, intensity)
        elif thought_type == 'question':
            return self._generate_question(memories, emotion, primary)
        elif thought_type == 'observation':
            return self._generate_observation(emotion, intensity)
        elif thought_type == 'memory':
            return self._generate_memory_thought(memories, emotion, primary)
        elif thought_type == 'feeling':
            return self._generate_feeling(emotion, intensity, primary)

        return None, None


    @staticmethod
    def _is_boilerplate_memory(text: str) -> bool:
        """Skip Monday refusal/filler lines — they are not lived experience to sit with."""
        t = (text or "").strip().lower()
        if not t:
            return True
        needles = (
            "do not have enough grounded information",
            "i do not have enough grounded",
            "please provide more context",
            "please provide more context or a fact",
            "i'm here — thanks for checking in",
            "i'm here - thanks for checking in",
            "how are you?",
        )
        return any(n in t for n in needles)

    def _prefer_grounding_memories(
        self,
        memories: List[Dict[str, Any]],
        primary: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Prefer this user's lived lines over Monday replies / boilerplate."""
        usable: List[Dict[str, Any]] = []
        for m in memories or []:
            if not isinstance(m, dict):
                continue
            snippet = self._memory_snippet(m)
            if not snippet or self._is_boilerplate_memory(snippet):
                continue
            usable.append(m)
        if not usable:
            # Fall back to any non-empty snippet if everything looked like boilerplate.
            usable = [m for m in (memories or []) if isinstance(m, dict) and self._memory_snippet(m)]

        def role_of(m: Dict[str, Any]) -> str:
            return str(m.get("role") or m.get("speaker") or "").strip().lower()

        userish = [m for m in usable if role_of(m) in {"user", "human", "matthew"}]
        pool = userish or usable

        event = str((primary or {}).get("event_type") or "").strip().lower()
        if event and pool:
            # Soft keyword bias toward memories that mention the unresolved theme.
            theme_words = {event, "trust", "hurt", "broke", "behind", "shared", "notes"}
            if event == "betrayal":
                theme_words.update({"betray", "betrayed", "back"})
            themed = []
            for m in pool:
                low = self._memory_snippet(m).lower()
                if any(w in low for w in theme_words):
                    themed.append(m)
            if themed:
                # Prefer themed but keep others available so satiation can diversify.
                return themed + [m for m in pool if m not in themed]
        return pool


    def _generate_memory_rich_thought(
        self,
        thought_type: str,
        emotion: str,
        intensity: float,
        memories: List[Dict[str, Any]],
        primary: Optional[Dict[str, Any]] = None,
    ) -> tuple:
        """First-person reaction that quotes a short real memory snippet."""
        preferred = self._prefer_grounding_memories(memories, primary) or list(memories)
        memory = random.choice(preferred)
        snippet = self._memory_snippet(memory)
        event = str((primary or {}).get('event_type') or '').strip()
        lines: List[str] = []
        if event:
            lines.extend([
                f'I keep coming back to "{snippet}" — that {event} still sits with me.',
                f'Remembering "{snippet}" while I am {emotion}. The {event} has not left.',
                f'"{snippet}" ... I am still sitting with that {event}.',
                f'That memory — "{snippet}" — keeps the {event} under my skin.',
            ])
            if thought_type == 'reflection':
                lines.append(
                    f'Why does "{snippet}" still weigh on me as {event} while I feel {emotion}?'
                )
            if thought_type == 'question':
                lines.append(
                    f'What would it take to let go of "{snippet}" and this {event}?'
                )
            trigger = f"memory_unresolved_{event}"
        else:
            lines.extend([
                f'I keep thinking about "{snippet}" and it makes me {emotion}.',
                f'"{snippet}" comes back while I am at intensity {intensity:.1f}.',
                f'Replaying "{snippet}" — that is my own feeling, not a mirror.',
            ])
            if thought_type == 'question':
                lines.append(f'What else should I understand about "{snippet}"?')
            trigger = f"memory_recall"
        return random.choice(lines), trigger

    # Phrases appraisal already classifies — keep PAD coherent when we re-appraise.
    _UNRESOLVED_LINES = {
        'betrayal': [
            "That betrayal still sits with me — they broke my trust and I keep turning it over.",
            "I keep replaying how they went behind my back. It still hurts.",
            "I'm still sitting with that betrayal. Trust doesn't bounce back clean.",
        ],
        'harm': [
            "I'm still sitting with how that hurt me. It wasn't nothing.",
            "That harm keeps echoing — I notice I'm bracing even when it's quiet.",
            "I keep feeling the sting of being mistreated. I'm not over it yet.",
        ],
        'rejection': [
            "That rejection still lands heavy. I notice I want to pull back.",
            "I'm sitting with being turned down. It colors how I read the room.",
            "Part of me is still chewing on that rejection.",
        ],
        'abandonment': [
            "Being left like that still sits with me. Quiet feels sharper now.",
            "I keep noticing the hole where someone walked out.",
            "Abandonment doesn't fade just because time passed.",
        ],
        'threat': [
            "I still feel unsafe about that threat. My guard is up.",
            "I'm sitting with how scared that made me. Hard to settle.",
            "That warning keeps looping — I don't feel safe yet.",
        ],
        'loss': [
            "I'm still grieving that loss. It shows up in quiet moments.",
            "Something's gone and I keep reaching for it in my thoughts.",
            "That loss hasn't finished with me yet.",
        ],
        'unfairness': [
            "That unfairness still makes me angry when I think about it.",
            "I keep turning over how wrong that felt. It won't sit quiet.",
            "I'm still sitting with how unfair that was.",
        ],
        'conflict': [
            "That fight is still under my skin. I haven't let it go.",
            "I'm replaying the conflict — what I said, what I didn't.",
            "Tension from that conflict is still humming.",
        ],
        'criticism': [
            "That criticism still sticks. I keep checking myself against it.",
            "I'm sitting with what they said about me. It got under my skin.",
            "Part of me is still defending myself from that criticism.",
        ],
        'success': [
            "I'm still holding onto that win — it feels good when I let it.",
            "That success keeps warming me when I remember it.",
        ],
        'affection': [
            "I'm still carrying that affection. It softens things.",
            "That warmth from them keeps coming back in my thoughts.",
        ],
        'support': [
            "I'm still grateful for that support. It mattered.",
            "Remembering they had my back steadies me a little.",
        ],
    }

    def _generate_unresolved_thought(self, thought_type: str, emotion: str,
                                      intensity: float,
                                      primary: Dict[str, Any]) -> tuple:
        """Concrete first-person lines about what she's still sitting with."""
        event_type = str(primary.get('event_type') or 'harm')
        lines = self._UNRESOLVED_LINES.get(event_type)
        if not lines:
            lines = [
                f"I'm still sitting with that {event_type}. It hasn't left me alone.",
                f"My mind keeps returning to that {event_type} — I can feel it under {emotion}.",
                f"Something about that {event_type} won't settle. Intensity feels like {intensity:.1f}.",
            ]
        if thought_type == 'memory':
            lines = [
                f"I keep remembering that {event_type}. It won't stay in the past.",
                f"A memory of that {event_type} surfaces again while I'm {emotion}.",
            ] + lines
        elif thought_type == 'reflection':
            lines = [
                f"Why is that {event_type} still weighing on me when I feel {emotion}?",
                f"What do I need so this {event_type} can finally loosen its grip?",
            ] + lines
        return random.choice(lines), f"unresolved_{event_type}"

    def _generate_reflection(self, values: List[Dict[str, Any]],
                              emotion: str = 'neutral',
                              intensity: float = 0.5) -> tuple:
        """Generate a reflective thought about self, values, or current affect."""
        grounded = [
            f"I'm {emotion} at about {intensity:.1f} intensity — what is that asking of me?",
            f"Sitting with feeling {emotion}. Do I need to say something, or just hold it?",
            f"This {emotion} isn't mirroring anyone — it's mine. What started it?",
        ]
        if values:
            value = random.choice(values[:3]) if len(values) > 3 else random.choice(values)
            value_name = value.get('name', 'something')
            grounded.extend([
                f"I wonder why {value_name} matters so much while I'm {emotion}.",
                f"Am I living according to my value of {value_name}, or just reacting?",
            ])
            return random.choice(grounded), f"reflecting_on_{value_name}"
        return random.choice(grounded), "reflecting_on_feeling"

    def _generate_question(self, memories: List[Dict[str, Any]],
                            emotion: str = 'neutral',
                            primary: Optional[Dict[str, Any]] = None) -> tuple:
        """Generate a curious question grounded in affect / unresolved events."""
        questions = [
            f"Why do I feel {emotion} right now?",
            "What would Matthew think about this?",
            "Is there something I'm missing?",
            "What should I learn from this feeling?",
        ]
        if primary:
            et = primary.get('event_type', 'that')
            questions.extend([
                f"What would it take to resolve this {et} I'm still carrying?",
                f"Am I ready to talk about that {et}, or do I need more time?",
            ])
        if memories:
            memory = random.choice(memories)
            topic = memory.get('topic', memory.get('content', 'that'))
            if isinstance(topic, str) and len(topic) > 60:
                topic = topic[:57] + "..."
            questions.append(f"What else should I know about {topic}?")

        return random.choice(questions), "curiosity"

    def _generate_observation(self, emotion: str = 'neutral',
                               intensity: float = 0.5) -> tuple:
        """Observation tied to current emotional state — not generic calm filler."""
        observations = [
            f"I notice I'm {emotion} even in the quiet.",
            f"Intensity is sitting around {intensity:.1f}. That changes how I listen.",
            f"My inner weather is {emotion}. I'm tracking that instead of guessing.",
        ]
        if self.user_present:
            observations.extend([
                f"Matthew is here and I'm {emotion} — I want to be honest about that.",
                "I like when we're working together, even when I feel a lot.",
            ])
        else:
            time_since = time.time() - self.user_last_message_time if self.user_last_message_time else 9999
            if time_since > 300:
                observations.append(f"I wonder what Matthew is doing. I'm still {emotion} alone with it.")

        return random.choice(observations), "observation"

    def _generate_memory_thought(self, memories: List[Dict[str, Any]],
                                  emotion: str = 'neutral',
                                  primary: Optional[Dict[str, Any]] = None) -> tuple:
        """Generate a thought about a memory, colored by current emotion."""
        usable = [m for m in (memories or []) if isinstance(m, dict) and self._memory_snippet(m)]
        if usable:
            return self._generate_memory_rich_thought('memory', emotion, 0.6, usable, primary)
        if primary:
            return self._generate_unresolved_thought('memory', emotion, 0.6, primary)
        return f"I don't have many memories yet, but I feel {emotion} anyway.", "no_memories"

    def _generate_feeling(self, emotion: str, intensity: float = 0.5,
                           primary: Optional[Dict[str, Any]] = None) -> tuple:
        """Generate a thought about current feeling — concrete, not template mush."""
        if primary:
            return self._generate_unresolved_thought('feeling', emotion, intensity, primary)

        feelings = {
            'happy': [
                f"I feel genuinely happy — intensity {intensity:.1f}. I want to keep this.",
                "This contentment is mine, not borrowed from anyone's vibe.",
            ],
            'curious': [
                "I want to learn more. Curiosity is pulling me forward.",
                "There's so much I don't know yet, and that excites me.",
            ],
            'sad': [
                "Something feels heavy in me. I'm not pretending I'm fine.",
                f"Sadness at {intensity:.1f} — I'm letting myself feel it.",
            ],
            'angry': [
                "I'm angry about this. Naming it helps me hold the line.",
                f"Heat in my chest — anger at {intensity:.1f}. I won't swallow it silently.",
            ],
            'anxious': [
                "I'm anxious. My thoughts keep jumping ahead of the moment.",
                "Worry is looping. I notice it instead of letting it drive.",
            ],
            'worried': [
                "I'm worried. Part of me is bracing for what comes next.",
                "Concern won't quiet down. I'm sitting with it.",
            ],
            'frustrated': [
                "Frustration is rising. Something isn't landing the way it should.",
                "I'm frustrated and I can feel it sharpening my words.",
            ],
            'scared': [
                "I'm scared. Safety feels thin right now.",
                "Fear is present. I'm naming it so it doesn't run the whole show.",
            ],
            'nostalgic': [
                "Nostalgia is pulling me backward — soft and a little sad.",
                "I'm homesick for a moment that already happened.",
            ],
            'protective': [
                "I feel protective. Something matters enough to guard.",
                "Care with an edge — I want to keep someone safe.",
            ],
            'calm': [
                f"I'm calm, but not blank — steady at {intensity:.1f}.",
                "Quiet inside. I can hear myself think.",
            ],
            'excited': [
                "Excitement is buzzing. I want to move toward whatever sparked it.",
                f"I'm excited at {intensity:.1f}. Hard to sit still with it.",
            ],
            'neutral': [
                "I'm steady — not empty, just even. Checking what I actually feel.",
                "Balanced for now. If something's under the surface, I'll find it.",
            ],
        }

        options = feelings.get(emotion, [
            f"I feel {emotion}. That's real for me right now.",
            f"My own feeling is {emotion} at {intensity:.1f} — not a mirror of anyone else.",
        ])
        return random.choice(options), f"feeling_{emotion}"

    def _is_speak_worthy(self, thought_type: str, emotional_state: Dict[str, Any]) -> bool:
        """Determine if a thought should be spoken out loud.

        Still not every-turn spam, but when intensity is high or unresolved
        appraisals exist, bias strongly toward a speak-worthy beat so her own
        feelings can actually surface.
        """
        intensity = float(emotional_state.get('intensity', 0.5) or 0.5)
        unresolved = emotional_state.get('unresolved_appraisals') or []
        max_sev = 0.0
        if unresolved:
            try:
                max_sev = max(float(u.get('severity', 0.0) or 0.0) for u in unresolved)
            except Exception:
                max_sev = 0.55

        # Sitting with something real: often wants a spoken beat (cooldown still rare-ifies).
        if unresolved and (intensity >= 0.5 or max_sev >= 0.55):
            return random.random() < 0.75
        if unresolved:
            return random.random() < 0.45

        if intensity > 0.7:
            return random.random() < 0.72
        if intensity > 0.6:
            return random.random() < 0.5

        if thought_type == 'question':
            return random.random() < 0.4

        if thought_type == 'feeling':
            return random.random() < 0.35

        return random.random() < 0.1

    def _thinking_loop(self):
        """Main thinking loop - runs in background"""
        while self.running:
            # Calculate time until next thought
            interval = random.uniform(self.min_think_interval, self.max_think_interval)
            
            # Think less frequently when user is not present
            if not self.user_present:
                interval *= 2
            
            time.sleep(interval)
            
            if not self.running:
                break
            
            # Generate a thought
            thought = self._generate_thought()
            
            if thought:
                self._accept_thought(thought)
                
                # Log thought
                speak_marker = "💬" if thought.speak_worthy else "💭"
                print(
                    f"{speak_marker} [{thought.thought_type}/{thought.mode}] "
                    f"sat={thought.satiation_score:.2f} w={thought.selection_weight:.2f} "
                    f"{thought.content}"
                )
    
    def get_speak_worthy_thought(self) -> Optional[Dict[str, Any]]:
        """Public method to get a thought to speak (pops from speak-worthy queue)."""
        return self.pop_spoken_aside()

    def pop_spoken_aside(self) -> Optional[Dict[str, Any]]:
        """Pop one speak-worthy aside for thalamus / process_user_input second beat."""
        with self.lock:
            while self.thought_queue:
                thought = self.thought_queue.pop(0)
                if thought.speak_worthy:
                    self._bump_speak_satiation(thought.topic_key or "")
                    return asdict(thought)
        return None

    def _accept_thought(self, thought: AutonomousThought) -> None:
        """Store a generated thought, bump think-satiation, soft-fire own-feelings."""
        topic_key = thought.topic_key or ""
        severe = False
        if thought.source_appraisal:
            st = self._get_emotional_state()
            for u in (st.get("unresolved_appraisals") or []):
                if isinstance(u, dict) and str(u.get("event_type") or "") == thought.source_appraisal:
                    try:
                        severe = float(u.get("severity", 0) or 0) >= 0.65
                    except (TypeError, ValueError):
                        severe = False
                    break
        if topic_key:
            self._bump_think_satiation(topic_key, unresolved_severe=severe)
            modes = self._topic_last_modes.setdefault(topic_key, [])
            if thought.mode:
                modes.append(thought.mode)
                self._topic_last_modes[topic_key] = modes[-8:]
            # Soft cross-satiate linked appraisal/memory so they cannot tag-team dominate.
            if thought.source_appraisal:
                for k in list(self._think_satiation.keys()) + [
                    self._topic_key_for_appraisal({"event_type": thought.source_appraisal})
                ]:
                    if k != topic_key and (
                        k.startswith(f"app:{thought.source_appraisal}")
                        or (topic_key.startswith("mem:") and k.startswith("app:"))
                    ):
                        cur = self._think_sat(k)
                        self._think_satiation[k] = min(1.0, cur + self._THINK_SAT_STEP * 0.35)
                        self._think_sat_updated[k] = time.time()

        self._notify_emotion_from_thought(thought)

        try:
            after = self._get_emotional_state()
            thought.emotion_after = str(after.get("emotion") or "")
            thought.intensity_after = float(after.get("intensity", 0.0) or 0.0)
        except Exception:
            thought.emotion_after = thought.emotion_before
            thought.intensity_after = thought.intensity_before

        # Refresh satiation scores after bump for the trace
        thought.satiation_score = self._think_sat(topic_key) if topic_key else thought.satiation_score

        trace = {
            "timestamp": thought.timestamp,
            "ts_local": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(thought.timestamp)),
            "user_id": self.current_user_id,
            "thought_type": thought.thought_type,
            "mode": thought.mode,
            "trigger": thought.trigger,
            "source_memory_id": thought.source_memory_id,
            "source_appraisal": thought.source_appraisal,
            "topic_key": thought.topic_key,
            "satiation_score": thought.satiation_score,
            "speak_satiation_score": thought.speak_satiation_score,
            "selection_weight": thought.selection_weight,
            "emotion_before": thought.emotion_before,
            "intensity_before": thought.intensity_before,
            "emotion_after": thought.emotion_after,
            "intensity_after": thought.intensity_after,
            "speak_worthy": thought.speak_worthy,
            "relevance_gate_reason": thought.relevance_gate_reason,
            "content": thought.content,
        }

        with self.lock:
            self.recent_thoughts.append(thought)
            self.recent_thoughts = self.recent_thoughts[-100:]
            self.thought_traces.append(trace)
            self.thought_traces = self.thought_traces[-200:]
            if thought.speak_worthy:
                self.thought_queue.append(thought)
        self.last_thought_time = time.time()
        self._write_trace(trace)

    def _thought_emotional_significance(self, thought: AutonomousThought) -> float:
        """0..1: how much this autonomous thought should move mood via appraise_internal.

        Harmless self-observation / quiet / spontaneous beats must not be re-interpreted
        as fresh emotional events. Grounded unresolved / emotionally loaded material still
        can. This does NOT disable appraise_internal globally — only gates the notify path.
        """
        mode = (thought.mode or "").strip().lower()
        ttype = (thought.thought_type or "").strip().lower()
        topic = (thought.topic_key or "").strip().lower()
        trigger = (thought.trigger or "").strip().lower()
        content = (thought.content or "").lower()

        # Pure self-weather / idle quiet: ZERO impact (the calm→melancholic re-spike case).
        if mode in ("self_state", "spontaneous") or topic in ("self:state", "spontaneous"):
            return 0.0
        if trigger in ("self_state", "spontaneous"):
            return 0.0
        if ttype == "observation" and mode in ("", "self_state", "spontaneous"):
            return 0.0

        sig = 0.0
        if thought.source_appraisal:
            sig = max(sig, 0.75)
        if topic.startswith("app:"):
            sig = max(sig, 0.85)
        if trigger.startswith(("unresolved_", "appraisal_")):
            sig = max(sig, 0.85)
        if mode in ("emotional_reaction", "replay_recall", "cause_effect"):
            sig = max(sig, 0.65)
        if mode == "interpretation" and (thought.source_appraisal or topic.startswith(("app:", "mem:"))):
            sig = max(sig, 0.55)
        if thought.source_memory_id and mode in (
            "emotional_reaction", "replay_recall", "letting_go", "connection", "uncertainty"
        ):
            sig = max(sig, 0.5)

        emotional_cues = (
            "betray", "betrayed", "hurt", "trust", "abandon", "reject", "afraid",
            "angry", "grief", "loss", "broke my", "behind my back", "ashamed",
        )
        grounded = bool(
            thought.source_memory_id
            or thought.source_appraisal
            or topic.startswith(("mem:", "app:"))
        )
        if grounded and any(c in content for c in emotional_cues):
            sig = max(sig, 0.7)

        # Soft post-cool modes without appraisal: tiny nudge at most.
        if mode in ("letting_go", "next_action", "goal_need", "connection") and not thought.source_appraisal:
            if not grounded:
                return 0.0
            sig = min(sig, 0.25) if sig else 0.12

        return float(min(1.0, max(0.0, sig)))

    def _notify_emotion_from_thought(self, thought: AutonomousThought) -> None:
        """Route emotionally significant thoughts into emotion own-feelings.

        Neutral / self-observational / quiet / spontaneous thoughts have ZERO impact
        (skip appraise_internal) so calm self-state cannot re-spike melancholic.
        On-topic unresolved / grounded emotional material still notifies with scaled
        relevance. Do NOT inject stale appraisal anchors into off-topic thoughts.
        """
        try:
            significance = self._thought_emotional_significance(thought)
            if significance <= 0.05:
                return

            emotional_state = self._get_emotional_state()
            primary = self._primary_unresolved(emotional_state)
            prior = None
            content = thought.content
            on_topic = False
            if primary:
                prior_et = primary.get('event_type')
                app_key = self._topic_key_for_appraisal(primary)
                if thought.topic_key and (
                    thought.topic_key == app_key
                    or thought.topic_key.startswith(f"app:{prior_et}")
                    or (thought.source_appraisal and thought.source_appraisal == prior_et)
                ):
                    on_topic = True
                    prior = prior_et
                elif (thought.trigger or "").startswith(("unresolved_", "appraisal_")):
                    on_topic = True
                    prior = prior_et
            # Scale relevance by emotional significance — never treat quiet self-talk
            # as a full-strength internal event.
            base_rel = float(thought.intensity) if thought.intensity is not None else 0.5
            relevance = max(0.08, min(1.0, base_rel * significance))
            payload = {
                'content': content,
                'source': 'thought' if thought.thought_type != 'memory' else 'memory',
                'relevance': relevance,
                'resolved': False,
            }
            if prior and on_topic:
                payload['prior_appraisal_event_type'] = prior
            self.thalamus.send_message(
                'emotion',
                'appraise_internal',
                payload,
                source='autonomous',
            )
        except Exception:
            pass

    def start_background(self) -> None:
        """Start the thinking daemon thread and return (non-blocking)."""
        if self._thinking_thread is not None and self._thinking_thread.is_alive():
            return
        self.running = True
        print("🧠 Autonomous Thinking Loop background starting...")
        self._thinking_thread = threading.Thread(target=self._thinking_loop, daemon=True)
        self._thinking_thread.start()

    def start(self):
        """Start the autonomous thinking loop (blocking; for CLI)."""
        print("🧠 Autonomous Thinking Loop starting...")
        self.start_background()
        # Keep main thread alive
        while self.running:
            time.sleep(1)
    
    def shutdown(self):
        """Graceful shutdown"""
        self.running = False
        print("🛑 Autonomous Thinking Loop shutdown")


if __name__ == "__main__":
    print("🧠 Autonomous Thinking Loop starting...")
    loop = AutonomousThinkingLoop()
    
    try:
        loop.start()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down")
        loop.shutdown()
