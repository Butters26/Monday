#!/usr/bin/env python3
"""Direct-call coordinator for Monday's prompted core path.

Every lobe receives the same envelope::

    {"type": str, "content": dict, "source": str, "message_id": str}

`content` is the only payload field.  Responses retain legacy top-level fields
for callers that use them, while their canonical payload is always `content`.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import threading
import uuid
from typing import Any, Dict, Iterable, Optional

class Thalamus:
    """Synchronously route direct calls between registered lobes."""

    def __init__(self) -> None:
        self.running = True
        self.lobe_handlers: Dict[str, Any] = {}
        self.lobe_handlers_lock = threading.RLock()
        self.lobe_status: Dict[str, str] = {}
        self.message_routes: deque = deque(maxlen=100)

    def register_lobe(self, name: str, lobe: Any) -> Dict[str, Any]:
        if not name or lobe is None:
            return {"status": "error", "message": "A lobe name and handler are required"}
        if not callable(getattr(lobe, "process_message", None)) and not callable(
            getattr(lobe, "process_message_safe", None)
        ):
            return {"status": "error", "message": f"{name} has no message handler"}
        with self.lobe_handlers_lock:
            self.lobe_handlers[name] = lobe
            self.lobe_status[name] = "online"
        return {"status": "success", "content": {"registered": name}, "registered": name}

    def send_message(
        self,
        destination: str,
        msg_type: str,
        content: Optional[Dict[str, Any]] = None,
        source: str = "thalamus",
    ) -> Dict[str, Any]:
        """Deliver one envelope synchronously and return its normalized response."""
        if not isinstance(content, dict):
            return {"status": "error", "message": "Message content must be a dictionary"}
        with self.lobe_handlers_lock:
            lobe = self.lobe_handlers.get(destination)
        if lobe is None:
            self.lobe_status[destination] = "offline"
            return {"status": "error", "message": f"Unknown destination: {destination}"}

        envelope = {
            "type": msg_type,
            "content": content,
            "source": source,
            "message_id": str(uuid.uuid4()),
        }
        try:
            handler = getattr(lobe, "process_message", None) or getattr(
                lobe, "process_message_safe"
            )
            response = handler(envelope)
            if not isinstance(response, dict):
                response = {"status": "success", "content": {"result": response}}
            response.setdefault("status", "success")
            if "content" not in response:
                response["content"] = {
                    key: value
                    for key, value in response.items()
                    if key not in {"status", "message"}
                }
            self.lobe_status[destination] = "online"
        except Exception as exc:
            self.lobe_status[destination] = "error"
            response = {"status": "error", "message": f"{destination}: {exc}", "content": {}}

        self.message_routes.append(
            {
                "from": source,
                "to": destination,
                "type": msg_type,
                "status": response["status"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        return response

    def send_and_wait(self, destination: str, msg_type: str,
                      content: Optional[Dict[str, Any]] = None,
                      source: str = "thalamus") -> Dict[str, Any]:
        """Compatibility name for direct calls, which are always synchronous."""
        return self.send_message(destination, msg_type, content or {}, source)

    def broadcast_message(
        self, destinations: Iterable[str], msg_type: str,
        content: Optional[Dict[str, Any]] = None, source: str = "thalamus"
    ) -> Dict[str, Dict[str, Any]]:
        return {
            destination: self.send_message(destination, msg_type, content or {}, source)
            for destination in destinations
        }

    @staticmethod
    def _content(response: Dict[str, Any]) -> Dict[str, Any]:
        content = response.get("content", {})
        return content if isinstance(content, dict) else {}

    @staticmethod
    def _first_usable_text(*candidates: Any) -> Optional[str]:
        """Select a reasoning conclusion without replacing it with a provider response."""
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                return candidate
            if isinstance(candidate, (list, tuple)):
                propositions = [
                    proposition
                    for proposition in candidate
                    if isinstance(proposition, str) and proposition.strip()
                ]
                if propositions:
                    return " ".join(propositions)
        return None

    def _reasoning_answer(self, reasoning: Dict[str, Any]) -> tuple[Dict[str, Any], Optional[str]]:
        content = self._content(reasoning)
        semantic_input = content.get("semantic_input", {})
        semantic_input = semantic_input.copy() if isinstance(semantic_input, dict) else {}
        for key in ("answer", "conclusion", "propositions"):
            if key not in semantic_input:
                value = content.get(key, reasoning.get(key))
                if value is not None:
                    semantic_input[key] = value
        answer = self._first_usable_text(
            semantic_input.get("answer"),
            semantic_input.get("conclusion"),
            semantic_input.get("propositions"),
            content.get("composed_response"),
            reasoning.get("composed_response"),
        )
        return semantic_input, answer

    def process_user_input(self, user_input: str, user_id: str = "default") -> str:
        """Run the sole prompted path: conversation → Notus → emotion → reasoning → language → output."""
        if not isinstance(user_input, str) or not user_input.strip():
            return "Please send a message."

        conversation = self.send_and_wait(
            "conversation", "understand", {"user_input": user_input, "user_id": user_id}
        )
        if conversation["status"] != "success":
            return "I'm having trouble understanding right now."
        understanding = self._content(conversation).get("understanding", {})

        memory = self.send_and_wait(
            "notus", "store", {"role": "user", "content": user_input, "user_id": user_id}
        )
        if memory["status"] != "success":
            return "I'm having trouble remembering that right now."

        memory_context = self.send_and_wait(
            "notus", "query", {"query": user_input, "user_id": user_id, "limit": 15}
        )
        if memory_context["status"] != "success":
            return "I'm having trouble retrieving context right now."

        emotion = self.send_and_wait(
            "emotion", "process_input", {"user_input": user_input}
        )
        if emotion["status"] != "success":
            return "I'm having trouble processing that right now."
        emotional_state = self._content(emotion)

        reasoning = self.send_and_wait(
            "reasoning",
            "think",
            {
                "input": {
                    "user_input": user_input,
                    "user_id": user_id,
                    "understanding": understanding,
                    "memory_context": self._content(memory_context),
                    "emotion_result": emotional_state,
                },
            },
        )
        if reasoning["status"] != "success":
            return "I'm having trouble thinking right now."
        semantic_input, reasoning_answer = self._reasoning_answer(reasoning)
        has_reasoning_content = any(
            (
                isinstance(semantic_input.get("concepts"), list)
                and any(
                    isinstance(concept, str) and concept.strip()
                    for concept in semantic_input.get("concepts", [])
                )
            ,
                isinstance(semantic_input.get("relations"), dict)
                and bool(semantic_input.get("relations")),
                isinstance(semantic_input.get("propositions"), list)
                and any(
                    isinstance(proposition, str) and proposition.strip()
                    for proposition in semantic_input.get("propositions", [])
                ),
            )
        )
        if reasoning_answer is None and not has_reasoning_content:
            return "I am unable to formulate a response right now."
        semantic_input.setdefault(
            "intent", understanding.get("intent", "conversation")
        )
        if reasoning_answer is not None:
            semantic_input.setdefault("answer", reasoning_answer)
            semantic_input.setdefault("propositions", [reasoning_answer])

        language = self.send_and_wait("language", "generate", {"semantic_input": semantic_input})
        if language["status"] != "success":
            return "I'm having trouble finding the words right now."
        response_text = self._content(language).get("sentence", "")

        output = self.send_and_wait(
            "output",
            "generate_output",
            {
                "text": response_text,
                "emotion": emotional_state.get("current_emotion", "neutral"),
                "intensity": emotional_state.get("intensity", 0.5),
                "user_input": user_input,
                "user_id": user_id,
                "preserve_text": True,
            },
        )
        return self._content(output).get("text", response_text)

    def handle_request(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Small compatibility entry point for direct callers."""
        msg_type = message.get("type")
        payload = message.get("content", message)
        if msg_type == "process_input":
            response = self.process_user_input(payload.get("user_input", ""))
            return {"status": "success", "content": {"response": response}, "response": response}
        if msg_type == "health":
            return {
                "status": "success",
                "content": {"thalamus_healthy": True, "lobes": self.lobe_status.copy()},
            }
        return {"status": "error", "message": f"Unknown type: {msg_type}", "content": {}}

    def start(self) -> "Thalamus":
        """Direct routing has no listener or background loop to start."""
        self.running = True
        return self

    def shutdown(self) -> None:
        self.running = False


_thalamus_instance: Optional[Thalamus] = None
_thalamus_lock = threading.Lock()


def get_thalamus() -> Thalamus:
    global _thalamus_instance
    with _thalamus_lock:
        if _thalamus_instance is None:
            _thalamus_instance = Thalamus()
        return _thalamus_instance
