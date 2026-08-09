#!/usr/bin/env python3
"""In-process message coordinator for Monday's lobes.

Thalamus owns routing only. Persistent identity, memory, and emotional state
belong to the respective lobes and are requested through the registry.
"""

from __future__ import annotations

from collections import deque
import contextvars
from datetime import datetime, timezone
import threading
import time
import uuid
from typing import Any, Dict, Optional


_ROUTING_PATH: contextvars.ContextVar[tuple[str, ...]] = contextvars.ContextVar(
    "thalamus_routing_path", default=()
)
_TRACE_ID: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "thalamus_trace_id", default=None
)


class MessageEnvelope(dict):
    """Canonical nested envelope with a temporary read-only legacy view.

    Lobes receive ``type``, ``source``, ``content``, ``message_id``,
    ``timestamp``, and ``trace_id``.  ``get`` and item lookup also find a
    missing key in ``content`` so older production lobes can migrate without
    reintroducing flattened envelopes.
    """

    _METADATA_KEYS = frozenset(
        {"type", "source", "content", "message_id", "timestamp", "trace_id"}
    )

    def __init__(
        self,
        *,
        msg_type: str,
        source: str,
        content: Dict[str, Any],
        message_id: str,
        timestamp: str,
        trace_id: str,
    ) -> None:
        super().__init__(
            type=msg_type,
            source=source,
            content=content,
            message_id=message_id,
            timestamp=timestamp,
            trace_id=trace_id,
        )

    def __contains__(self, key: object) -> bool:
        return super().__contains__(key) or key in self["content"]

    def __getitem__(self, key: str) -> Any:
        if super().__contains__(key):
            return super().__getitem__(key)
        return self["content"][key]

    def get(self, key: str, default: Any = None) -> Any:
        if super().__contains__(key):
            return super().get(key, default)
        return self["content"].get(key, default)


class Thalamus:
    """Thread-safe direct-call lobe registry and router."""

    def __init__(
        self,
        *,
        default_timeout: float = 8.0,
        max_route_depth: int = 32,
        circuit_failure_threshold: int = 3,
        circuit_reset_seconds: float = 30.0,
    ) -> None:
        self.running = False
        self.default_timeout = default_timeout
        self.max_route_depth = max_route_depth
        self.circuit_failure_threshold = circuit_failure_threshold
        self.circuit_reset_seconds = circuit_reset_seconds

        self.lobe_handlers: Dict[str, Any] = {}
        self.lobe_handlers_lock = threading.RLock()
        self.lobe_status: Dict[str, str] = {}
        self._failure_counts: Dict[str, int] = {}
        self._circuit_opened_at: Dict[str, float] = {}
        self.message_routes: deque[Dict[str, Any]] = deque(maxlen=1_000)
        self._route_lock = threading.RLock()
        self._shutdown_event = threading.Event()
        self.autonomous_thread: Optional[threading.Thread] = None

    def register_lobe(self, name: str, handler: Any) -> Dict[str, Any]:
        """Register a direct-call lobe handler."""
        if not isinstance(name, str) or not name.strip():
            return {"status": "error", "message": "Lobe name must be a non-empty string"}
        if not callable(getattr(handler, "process_message", None)) and not callable(
            getattr(handler, "process_message_safe", None)
        ):
            return {
                "status": "error",
                "message": f"Lobe '{name}' must provide process_message(message)",
            }

        with self.lobe_handlers_lock:
            replaced = name in self.lobe_handlers
            self.lobe_handlers[name] = handler
            self.lobe_status[name] = "online"
            self._failure_counts[name] = 0
            self._circuit_opened_at.pop(name, None)
        return {"status": "success", "lobe": name, "replaced": replaced}

    def unregister_lobe(self, name: str) -> Dict[str, Any]:
        """Remove a lobe from the registry."""
        with self.lobe_handlers_lock:
            if name not in self.lobe_handlers:
                return {"status": "error", "message": f"Unknown lobe: {name}"}
            del self.lobe_handlers[name]
            self.lobe_status[name] = "offline"
            self._failure_counts.pop(name, None)
            self._circuit_opened_at.pop(name, None)
        return {"status": "success", "lobe": name}

    def get_lobe_status(self, name: str) -> Dict[str, Any]:
        """Return lifecycle and circuit-breaker state for one lobe."""
        with self.lobe_handlers_lock:
            return {
                "status": "success",
                "lobe": name,
                "registered": name in self.lobe_handlers,
                "state": self.lobe_status.get(name, "offline"),
                "failures": self._failure_counts.get(name, 0),
            }

    def send_message(
        self,
        destination: str,
        msg_type: str,
        content: Optional[Dict[str, Any]] = None,
        *,
        source: str = "thalamus",
        timeout: Optional[float] = None,
        trace_id: Optional[str] = None,
        _route: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        """Route one nested message directly to a registered lobe.

        Failures are returned as structured errors and are never converted to
        successful responses.  ``timeout`` bounds the caller's wait; handlers
        must remain cooperative for cancellation to take effect.
        """
        if not isinstance(content, dict) and content is not None:
            return {"status": "error", "message": "Message content must be a dictionary"}
        if not isinstance(destination, str) or not destination:
            return {"status": "error", "message": "Destination must be a non-empty string"}
        if not isinstance(msg_type, str) or not msg_type:
            return {"status": "error", "message": "Message type must be a non-empty string"}

        route = list(_route if _route is not None else _ROUTING_PATH.get())
        if destination in route:
            return self._error(destination, source, msg_type, "routing cycle detected", trace_id)
        if len(route) >= self.max_route_depth:
            return self._error(destination, source, msg_type, "maximum route depth exceeded", trace_id)

        with self.lobe_handlers_lock:
            handler = self.lobe_handlers.get(destination)
            if handler is None:
                return self._error(destination, source, msg_type, "destination is not registered", trace_id)
            opened_at = self._circuit_opened_at.get(destination)
            if opened_at is not None:
                if time.monotonic() - opened_at < self.circuit_reset_seconds:
                    return self._error(destination, source, msg_type, "circuit breaker is open", trace_id)
                self._circuit_opened_at.pop(destination, None)
                self._failure_counts[destination] = 0

        active_trace_id = trace_id or _TRACE_ID.get() or str(uuid.uuid4())
        message = MessageEnvelope(
            msg_type=msg_type,
            source=source,
            content=dict(content or {}),
            message_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            trace_id=active_trace_id,
        )
        result_holder: Dict[str, Any] = {}
        completed = threading.Event()
        route_token = _ROUTING_PATH.set(tuple(route + [destination]))
        trace_token = _TRACE_ID.set(active_trace_id)
        invocation_context = contextvars.copy_context()
        _ROUTING_PATH.reset(route_token)
        _TRACE_ID.reset(trace_token)

        def invoke() -> None:
            try:
                processor = getattr(handler, "process_message", None) or getattr(
                    handler, "process_message_safe"
                )
                result_holder["result"] = invocation_context.run(processor, message)
            except Exception as exc:
                result_holder["exception"] = exc
            finally:
                completed.set()

        threading.Thread(target=invoke, daemon=True).start()
        wait_timeout = self.default_timeout if timeout is None else timeout
        if not completed.wait(wait_timeout):
            return self._record_failure(
                destination, source, msg_type, f"timed out after {wait_timeout}s", message["trace_id"]
            )
        if "exception" in result_holder:
            return self._record_failure(
                destination,
                source,
                msg_type,
                f"handler raised {type(result_holder['exception']).__name__}: {result_holder['exception']}",
                message["trace_id"],
            )

        result = result_holder.get("result")
        if not isinstance(result, dict):
            return self._record_failure(
                destination, source, msg_type, "handler returned a non-dictionary response", message["trace_id"]
            )
        if result.get("status") == "error":
            return self._record_failure(
                destination,
                source,
                msg_type,
                result.get("message", "handler reported an error"),
                message["trace_id"],
                response=result,
            )

        with self.lobe_handlers_lock:
            self.lobe_status[destination] = "online"
            self._failure_counts[destination] = 0
        self._log_route(source, destination, msg_type, "success", message["trace_id"])
        return result

    def process_user_input(self, user_input: str, *, source: str = "user") -> Dict[str, Any]:
        """Run the conversation pipeline with shared, lobe-owned context."""
        if not isinstance(user_input, str) or not user_input.strip():
            return {"status": "error", "message": "User input must be a non-empty string"}

        trace_id = str(uuid.uuid4())
        context: Dict[str, Any] = {"user_input": user_input, "trace_id": trace_id}

        memory = self.send_message(
            "notus", "get_context", {"user_input": user_input}, source=source, trace_id=trace_id
        )
        if memory.get("status") == "success":
            context["memory"] = memory

        for lobe, message_type, payload_key in (
            ("perception", "process_text", "perception"),
            ("pattern", "observe", "patterns"),
            ("social_context", "analyze_context", "social"),
            ("emotion", "process_input", "emotion"),
            ("value_goal_management", "evaluate_input", "values"),
        ):
            payload = {"text": user_input, "user_input": user_input, "context": context}
            result = self.send_message(
                lobe, message_type, payload, source=source, trace_id=trace_id
            )
            if result.get("status") == "success":
                context[payload_key] = result

        representation = self.send_message(
            "representation",
            "translate_from",
            {"lobe": "perception", "data": context.get("perception", {})},
            source="perception",
            trace_id=trace_id,
        )
        if representation.get("status") == "success":
            context["representation"] = representation

        conversation = self.send_message(
            "conversation",
            "understand",
            {"user_input": user_input, "context": context},
            source=source,
            trace_id=trace_id,
        )
        if conversation.get("status") != "success":
            return self._pipeline_error("conversation", conversation, trace_id)
        context["conversation"] = conversation
        understanding = conversation.get("content", {}).get("understanding", conversation.get("understanding", {}))

        reasoning = self.send_message(
            "reasoning",
            "think",
            {"input": {"user_input": user_input, "understanding": understanding, "context": context}},
            source="conversation",
            trace_id=trace_id,
        )
        if reasoning.get("status") != "success":
            return self._pipeline_error("reasoning", reasoning, trace_id)
        thinking = reasoning.get("thinking", reasoning.get("content", {}))
        response = thinking.get("composed_response", conversation.get("response", ""))

        emotion = context.get("emotion", {})
        emotion_name = emotion.get("current_emotion", "neutral")
        intensity = emotion.get("intensity", 0.5)
        language = self.send_message(
            "language",
            "express",
            {
                "thought": response,
                "emotion": emotion_name,
                "intensity": intensity,
                "context": context,
                "user_input": user_input,
            },
            source="reasoning",
            trace_id=trace_id,
        )
        if language.get("status") == "success":
            response = language.get("sentence", language.get("response", response))

        output = self.send_message(
            "output",
            "generate_output",
            {"text": response, "emotion": emotion_name, "intensity": intensity, "user_input": user_input},
            source="language",
            trace_id=trace_id,
        )
        if output.get("status") != "success":
            return self._pipeline_error("output", output, trace_id)
        voice = self._deliver_to_voice(
            output.get("text", response), emotion_name, intensity, trace_id
        )
        if voice.get("status") == "success":
            context["voice"] = voice

        for lobe, message_type in (
            ("experience", "record_experience"),
            ("reinforcement", "process_outcome"),
            ("reflection", "reflect"),
            ("autonomous", "process_interaction"),
            ("speech", "interaction_complete"),
        ):
            self.send_message(
                lobe,
                message_type,
                {"user_input": user_input, "response": output.get("text", response), "context": context},
                source="thalamus",
                trace_id=trace_id,
            )

        return {"status": "success", "response": output.get("text", response), "trace_id": trace_id}

    def handle_request(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Compatibility entry point for interfaces that call Thalamus directly."""
        message_type = message.get("type")
        if message_type == "process_input":
            return self.process_user_input(message.get("user_input", ""), source=message.get("source", "user"))
        if message_type == "health":
            with self.lobe_handlers_lock:
                statuses = dict(self.lobe_status)
            return {
                "status": "success",
                "thalamus_healthy": self.running,
                "lobes": statuses,
                "all_lobes_online": bool(statuses) and all(state == "online" for state in statuses.values()),
            }
        if message_type == "get_monday_state":
            return {
                "status": "success",
                "lobes": {name: self.get_lobe_status(name) for name in self.lobe_handlers},
            }
        return {"status": "error", "message": f"Unknown request type: {message_type}"}

    def start(self) -> None:
        """Mark the direct router available and start the autonomous poller."""
        if self.running:
            return
        self.running = True
        self._shutdown_event.clear()
        self.autonomous_thread = threading.Thread(target=self._autonomous_action_loop, daemon=True)
        self.autonomous_thread.start()

    def shutdown(self) -> None:
        """Stop routing background work and ask registered lobes to shut down."""
        self.running = False
        self._shutdown_event.set()
        if self.autonomous_thread and self.autonomous_thread.is_alive():
            self.autonomous_thread.join(timeout=2)
        with self.lobe_handlers_lock:
            handlers = list(self.lobe_handlers.items())
        for name, handler in handlers:
            shutdown = getattr(handler, "shutdown", None)
            if callable(shutdown):
                try:
                    shutdown()
                except Exception as exc:
                    self._log_route("thalamus", name, "shutdown", f"error: {exc}", None)

    def _autonomous_action_loop(self) -> None:
        while not self._shutdown_event.wait(5):
            result = self.send_message("reasoning", "get_autonomous_actions", source="thalamus")
            if result.get("status") == "error" and result.get("message") == "destination is not registered":
                continue
            if result.get("status") == "success":
                self._route_autonomous_actions(result.get("actions", []), result.get("trace_id"))

    def _route_autonomous_actions(
        self, actions: Any, trace_id: Optional[str] = None
    ) -> list[Dict[str, Any]]:
        """Express autonomous messages through language and output, not the console."""
        results = []
        if not isinstance(actions, list):
            return [{"status": "error", "message": "Autonomous actions must be a list"}]

        for action in actions:
            if not isinstance(action, dict) or action.get("type") != "message":
                continue
            thought = action.get("content")
            if not isinstance(thought, str) or not thought.strip():
                results.append({"status": "error", "message": "Autonomous message content is required"})
                continue

            language = self.send_message(
                "language",
                "express",
                {
                    "thought": thought,
                    "context": {"autonomous": True, "target": action.get("target")},
                },
                source="reasoning",
                trace_id=trace_id,
            )
            if language.get("status") != "success":
                results.append(language)
                continue

            text = language.get("sentence", language.get("response", thought))
            output = self.send_message(
                "output",
                "generate_output",
                {
                    "text": text,
                    "autonomous": True,
                    "target": action.get("target"),
                },
                source="language",
                trace_id=trace_id,
            )
            if output.get("status") == "success":
                self._deliver_to_voice(text, "neutral", 0.5, trace_id)
            results.append(output)
        return results

    def _deliver_to_voice(
        self, text: str, emotion: str, intensity: float, trace_id: Optional[str]
    ) -> Dict[str, Any]:
        """Deliver finalized text to the optional voice lobe."""
        with self.lobe_handlers_lock:
            voice_available = "voice" in self.lobe_handlers
        if not voice_available:
            return {"status": "unavailable", "message": "voice is not registered"}
        return self.send_message(
            "voice",
            "play",
            {"text": text, "emotion": emotion, "intensity": intensity},
            source="output",
            trace_id=trace_id,
        )

    def _pipeline_error(self, lobe: str, result: Dict[str, Any], trace_id: str) -> Dict[str, Any]:
        return {
            "status": "error",
            "message": f"{lobe} failed: {result.get('message', 'unknown error')}",
            "failed_lobe": lobe,
            "trace_id": trace_id,
        }

    def _record_failure(
        self,
        destination: str,
        source: str,
        msg_type: str,
        message: str,
        trace_id: Optional[str],
        response: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        with self.lobe_handlers_lock:
            failures = self._failure_counts.get(destination, 0) + 1
            self._failure_counts[destination] = failures
            self.lobe_status[destination] = "error"
            if failures >= self.circuit_failure_threshold:
                self._circuit_opened_at[destination] = time.monotonic()
        self._log_route(source, destination, msg_type, "error", trace_id)
        result = dict(response or {})
        result.update({"status": "error", "message": message, "destination": destination, "trace_id": trace_id})
        return result

    def _error(
        self, destination: str, source: str, msg_type: str, message: str, trace_id: Optional[str]
    ) -> Dict[str, Any]:
        self._log_route(source, destination, msg_type, "error", trace_id)
        return {"status": "error", "message": message, "destination": destination, "trace_id": trace_id}

    def _log_route(
        self, source: str, destination: str, msg_type: str, status: str, trace_id: Optional[str]
    ) -> None:
        with self._route_lock:
            self.message_routes.append(
                {
                    "source": source,
                    "destination": destination,
                    "type": msg_type,
                    "status": status,
                    "trace_id": trace_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )


_thalamus_instance: Optional[Thalamus] = None
_thalamus_lock = threading.Lock()


def get_thalamus() -> Thalamus:
    """Get the process-wide Thalamus used by all in-process lobes."""
    global _thalamus_instance
    with _thalamus_lock:
        if _thalamus_instance is None:
            _thalamus_instance = Thalamus()
        return _thalamus_instance


if __name__ == "__main__":
    thalamus = get_thalamus()
    thalamus.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        thalamus.shutdown()
