"""
ThinkingLoop: Core cognitive cycle module for the AI brain architecture.
Wraps AutonomousThinkingLoop and exposes a simple interface for the Thalamus.
"""

import time
import threading
import random
from typing import Dict, Any, List, Optional
from thalamus import get_thalamus


class ThinkingLoop:
    """
    Core cognitive thinking loop. Manages one think cycle at a time and
    tracks execution metrics. Use start() for the continuous background
    loop; call _run_think_cycle() directly for single-step testing.
    """

    def __init__(self):
        self.thalamus = get_thalamus()
        self.running = False
        self._lock = threading.Lock()

        # Metrics
        self._cycle_count = 0
        self._last_cycle_time: Optional[float] = None
        self._recent_executions: List[Dict[str, Any]] = []

        # Register with Thalamus
        try:
            self.thalamus.register_lobe('thinking_loop', self)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _run_think_cycle(self) -> Dict[str, Any]:
        """Execute a single think cycle and record the result."""
        start = time.time()

        # Gather emotional context from Thalamus (best-effort)
        emotion_state = self._fetch_emotion()
        thought = self._generate_thought(emotion_state)

        duration = time.time() - start
        record = {
            'cycle': self._cycle_count,
            'timestamp': start,
            'duration_ms': round(duration * 1000, 2),
            'thought': thought,
            'emotion': emotion_state.get('emotion', 'neutral'),
        }

        with self._lock:
            self._cycle_count += 1
            self._last_cycle_time = start
            self._recent_executions.append(record)
            self._recent_executions = self._recent_executions[-100:]

        return record

    def start(self) -> None:
        """Start the continuous background thinking loop."""
        self.running = True
        thread = threading.Thread(target=self._loop, daemon=True)
        thread.start()

    def shutdown(self) -> None:
        """Stop the continuous background thinking loop."""
        self.running = False

    # ------------------------------------------------------------------
    # Thalamus message handler
    # ------------------------------------------------------------------

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = message.get('type')

        if msg_type == 'run_cycle':
            result = self._run_think_cycle()
            return {'status': 'success', 'result': result}

        elif msg_type == 'get_metrics':
            return self._get_metrics()

        elif msg_type == 'get_recent_executions':
            limit = message.get('limit', 10)
            return self._get_recent_executions(limit)

        elif msg_type == 'health':
            return {'status': 'success', 'healthy': True}

        else:
            return {'status': 'error', 'message': f'Unknown message type: {msg_type}'}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        """Continuous background loop."""
        while self.running:
            self._run_think_cycle()
            time.sleep(random.uniform(5.0, 30.0))

    def _fetch_emotion(self) -> Dict[str, Any]:
        """Best-effort fetch of emotional state from Thalamus."""
        try:
            result = self.thalamus.send_message('emotion', 'get_state', {})
            if result and result.get('status') == 'success':
                return result.get('state', {})
        except Exception:
            pass
        return {'emotion': 'neutral', 'intensity': 0.5}

    def _generate_thought(self, emotion_state: Dict[str, Any]) -> str:
        """Generate a simple thought string based on emotional context."""
        emotion = emotion_state.get('emotion', 'neutral')
        templates = {
            'curious': [
                "What else is there to explore?",
                "I wonder what happens next.",
            ],
            'happy': [
                "Things feel good right now.",
                "There is momentum here.",
            ],
            'sad': [
                "Something feels off. Worth reflecting on.",
                "I should sit with this feeling.",
            ],
            'neutral': [
                "Processing current state.",
                "Maintaining steady awareness.",
            ],
        }
        options = templates.get(emotion, templates['neutral'])
        return random.choice(options)

    def _get_metrics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'status': 'success',
                'cycle_count': self._cycle_count,
                'last_cycle_time': self._last_cycle_time,
                'running': self.running,
            }

    def _get_recent_executions(self, limit: int) -> Dict[str, Any]:
        with self._lock:
            executions = self._recent_executions[-limit:]
            return {
                'status': 'success',
                'executions': executions,
                'count': len(executions),
            }
