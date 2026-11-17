"""How a lobe talks to the rest of her through the Thalamus.

Three things a lobe can do: sign up for announcements (listen), tell everyone
who signed up that something happened (announce), and ask another lobe for
something it needs (ask). Nothing here decides anything.

The announcements that carry a moment through her, and who makes them:

  heard_words / heard_sound / saw   Perception: something reached a sense
  moment        Sensory Integration: the moment built from all her senses
  read          Language: what the words in the moment mean
  turn          Conversation: where this leaves the conversation
  remembered    Notus: what the moment brought back
  social_read   Social Context: the social side of it
  understood    Reasoning: what is going on and what follows
  thought       Reasoning: what there is to say about it
  delivered     Output: what she actually said (empty if nothing)

Besides announcing, a lobe that has something she could do bids for it (bid):
Executive Control weighs the bids and one wins.

Each one carries "user_id" (who she is with) and, when it came from something
sensed, "recognition_id" (which moment it is about).
"""

from __future__ import annotations

from typing import Any, Dict


def listen(thalamus: Any, name: str, *topics: str) -> None:
    hear = getattr(thalamus, "listen", None)
    if callable(hear):
        for topic in topics:
            hear(name, topic)


def announce(thalamus: Any, topic: str, content: Dict[str, Any], source: str) -> None:
    tell_all = getattr(thalamus, "announce", None)
    if callable(tell_all):
        tell_all(topic, content, source)


def ask(thalamus: Any, lobe: str, msg_type: str, payload: Dict[str, Any], source: str) -> Dict[str, Any]:
    """Ask another lobe; its answer's content, or {} if it couldn't answer
    (not there, didn't understand, failed). Thalamus reports the failure."""
    send = getattr(thalamus, "send_and_wait", None)
    if not callable(send):
        return {}
    try:
        response = send(lobe, msg_type, payload, source=source)
    except Exception:
        return {}
    if not isinstance(response, dict) or response.get("status") != "success":
        return {}
    body = response.get("content")
    if isinstance(body, dict) and body:
        return body
    return {k: v for k, v in response.items() if k not in ("status", "content", "message")}


def bid(thalamus: Any, source: str, impulse: str, strength: Any, about: str, user_id: str,
        **more: Any) -> None:
    """Tell Executive Control this lobe has something she could do: what the
    impulse is, how strong it is by this lobe's own measure (0 to 1), and what
    it is about. Executive Control weighs it against the other lobes' bids."""
    # Asked, not told: the lobe carries on only once Executive Control has taken
    # the bid, so a lobe that has finished with a moment has its bids in.
    send = getattr(thalamus, "send_and_wait", None)
    if callable(send):
        send("executive_control", "bid", {"from": source, "impulse": impulse, "strength": strength,
                                          "about": about, "user_id": user_id, **more}, source=source)


def words_of(moment: Dict[str, Any]) -> str:
    """The words in a moment, if it has any (typed or heard)."""
    if not isinstance(moment, dict):
        return ""
    sense = str(moment.get("modality") or "text")
    if sense not in ("text", "audio"):
        return ""
    for key in ("text", "normalized_text", "transcript"):
        value = moment.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


__all__ = ["listen", "announce", "ask", "bid", "words_of"]
