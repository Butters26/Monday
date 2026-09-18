#!/usr/bin/env python3
"""
Autonomous Thinking Loop - Generates thoughts without prompting
Monday thinks on her own, not just when spoken to.
"""

import time
import threading
import random
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from thalamus import get_thalamus

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


class AutonomousThinkingLoop:
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
        This is the heart of the inner monologue.
        """
        # Get context from other lobes
        emotional_state = self._get_emotional_state()
        recent_memories = self._get_recent_memories()
        current_values = self._get_current_values()
        
        # Decide what type of thought to generate
        thought_type = self._decide_thought_type(emotional_state)
        
        # Generate thought content based on type
        content, trigger = self._generate_thought_content(
            thought_type, emotional_state, recent_memories, current_values
        )
        
        if not content:
            return None
        
        # Determine if this should be spoken
        speak_worthy = self._is_speak_worthy(thought_type, emotional_state)
        
        thought = AutonomousThought(
            id=f"thought_{int(time.time() * 1000)}",
            content=content,
            thought_type=thought_type,
            trigger=trigger,
            intensity=max(
                float(emotional_state.get('intensity', 0.5) or 0.5),
                0.55 if (emotional_state.get('unresolved_appraisals') or []) else 0.0,
            ),
            speak_worthy=speak_worthy,
            timestamp=time.time()
        )
        
        return thought
    
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
        attempts = (
            ('get_recent_memories', {'limit': 5}),
            ('get_recent', {'limit': 5}),
            ('get_conversation_history', {'limit': 5}),
            ('query', {'query': 'recent conversation', 'limit': 5}),
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
    def _memory_snippet(memory: Dict[str, Any], max_len: int = 72) -> str:
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
            return text[: max_len - 3] + '...'
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
        usable = [m for m in (memories or []) if isinstance(m, dict) and self._memory_snippet(m)]
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

    def _generate_memory_rich_thought(
        self,
        thought_type: str,
        emotion: str,
        intensity: float,
        memories: List[Dict[str, Any]],
        primary: Optional[Dict[str, Any]] = None,
    ) -> tuple:
        """First-person reaction that quotes a short real memory snippet."""
        memory = random.choice(memories)
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
                print(f"{speak_marker} [{thought.thought_type}] {thought.content}")
    
    def get_speak_worthy_thought(self) -> Optional[Dict[str, Any]]:
        """Public method to get a thought to speak (pops from speak-worthy queue)."""
        return self.pop_spoken_aside()

    def pop_spoken_aside(self) -> Optional[Dict[str, Any]]:
        """Pop one speak-worthy aside for thalamus / process_user_input second beat."""
        with self.lock:
            while self.thought_queue:
                thought = self.thought_queue.pop(0)
                if thought.speak_worthy:
                    return asdict(thought)
        return None

    def _accept_thought(self, thought: AutonomousThought) -> None:
        """Store a generated thought and soft-fire own-feelings via emotion."""
        with self.lock:
            self.recent_thoughts.append(thought)
            self.recent_thoughts = self.recent_thoughts[-100:]  # Keep last 100
            if thought.speak_worthy:
                self.thought_queue.append(thought)
        self.last_thought_time = time.time()
        self._notify_emotion_from_thought(thought)

    def _notify_emotion_from_thought(self, thought: AutonomousThought) -> None:
        """Route thought into emotion own-feelings; match unresolved event when possible."""
        try:
            emotional_state = self._get_emotional_state()
            primary = self._primary_unresolved(emotional_state)
            prior = None
            content = thought.content
            if primary:
                prior = primary.get('event_type')
                # Prefer content already about the unresolved event (trigger prefix).
                if thought.trigger.startswith('unresolved_') and prior:
                    content = thought.content
                elif prior and prior not in (thought.content or '').lower():
                    # Nudge wording so appraisal PAD moves coherently with what she sits with.
                    content = f"{thought.content} (still sitting with that {prior})"
            payload = {
                'content': content,
                'source': 'thought' if thought.thought_type != 'memory' else 'memory',
                'relevance': float(thought.intensity),
                'resolved': False,
            }
            if prior:
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
