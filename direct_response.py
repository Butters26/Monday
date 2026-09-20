"""Safe, deterministic response realization for the direct core.

The direct runtime intentionally does not assume an external language model.
Providers receive structured understanding and clean, user-scoped memory only.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Dict, Iterable, List, Optional, Protocol




_STOPWORDS = frozenset(
    {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "am",
        "i", "my", "me", "mine", "you", "your", "yours", "we", "our",
        "what", "whats", "who", "whom", "where", "when", "why", "how",
        "do", "does", "did", "can", "could", "would", "should", "please",
        "remember", "that", "this", "these", "those", "with", "from",
        "about", "tell", "of", "to", "in", "on", "at", "for", "and", "or",
        "it", "its", "have", "has", "had", "will", "just", "also", "so",
        "as", "if", "but", "not", "no", "yes", "ok", "okay", "hey", "hi",
        "hello", "named", "name", "got", "know", "say", "said", "just",
        "there", "here", "into", "over", "under", "again", "more",
    }
)

_QUESTIONISH = re.compile(
    # "tell me" only as a real ask — not "nobody will tell me anything".
    r"(?:^\s*(?:please\s+)?tell me\b)|"
    r"\b(?:can you|could you)\s+tell me\b|"
    r"\b(?:explain|what|who|where|when|why|how|which|do you remember|"
    r"can you remember|remind me|did i|do i|have i)\b|\?",
    re.IGNORECASE,
)

_SPEAKER_ROLES = frozenset({"user", "fact", "note", "monday", "assistant", "abin"})
_MONDAY_ROLES = frozenset({"monday", "assistant", "abin"})


_MILD_SOCIAL_EXACT = frozenset(
    {
        "hi", "hello", "hey", "yo", "sup", "hiya", "howdy", "greetings",
        "good morning", "good afternoon", "good evening",
        "hello there", "hi there", "hey there", "hello!", "hi!", "hey!",
        "hello.", "hi.", "hey.",
    }
)
_MILD_SOCIAL_RE = re.compile(
    r"^\s*(?:hi|hello|hey|yo|sup|hiya|howdy|greetings|"
    r"good\s+(?:morning|afternoon|evening))\b[\s!.]*$"
    r"|^\s*(?:hey[, ]+)?(?:are you (?:still )?with me|you (?:still )?there|still there)\??\s*$"
    r"|^\s*(?:what'?s|how'?s)\s+the\s+weather\b.*$"
    r"|^\s*how are you\??\s*$",
    re.IGNORECASE,
)


def is_mild_social_turn(user_input: str, intent: Optional[str] = None) -> bool:
    """True for short greetings / social filler that must not force curiosity spam."""
    text = (user_input or "").strip()
    if not text:
        return True
    lower = text.lower().rstrip()
    bare = lower.rstrip("!.?")
    if bare in _MILD_SOCIAL_EXACT or lower in _MILD_SOCIAL_EXACT:
        return True
    if _MILD_SOCIAL_RE.match(text):
        return True
    # Light check-ins / presence pings — must not drag stale unresolved rumination.
    light_needles = (
        "still with me", "you there", "you still there", "are you there",
        "what's the weather", "whats the weather", "how are you",
    )
    if any(n in bare for n in light_needles) and len(text.split()) <= 10:
        return True
    if intent == "greeting" and len(text.split()) <= 5:
        return True
    return False


def honest_curiosity_question(
    user_input: str,
    emotional_state: Optional[Dict[str, Any]] = None,
) -> str:
    """One honest follow-up that asks instead of inventing facts.

    Owned by the live emotion/conversation/direct_response path — not novelty_lobe.
    """
    state = emotional_state if isinstance(emotional_state, dict) else {}
    unresolved = state.get("unresolved_appraisals") or []
    emotion = str(
        state.get("current_emotion")
        or state.get("emotion")
        or "this"
    ).strip() or "this"
    text = (user_input or "").strip()

    primary = None
    if isinstance(unresolved, list) and unresolved:
        try:
            primary = max(
                (u for u in unresolved if isinstance(u, dict)),
                key=lambda u: float(u.get("severity", 0.0) or 0.0),
                default=None,
            )
        except Exception:
            primary = next((u for u in unresolved if isinstance(u, dict)), None)

    if isinstance(primary, dict):
        et = str(primary.get("event_type") or "feeling").replace("_", " ").strip()
        return (
            f"What would help with this {et} - or is there more I should understand "
            f"before I guess?"
        )

    snippet = text
    if len(snippet) > 72:
        cut = snippet[:69].rsplit(" ", 1)[0]
        snippet = (cut or snippet[:69]) + "..."
    if snippet:
        # Ask about their words; do not invent missing details.
        safe = snippet.replace('"', "'")
        return (
            f'I do not want to invent details - can you tell me more about what you '
            f'meant by "{safe}"?'
        )
    return (
        f"I am feeling {emotion} about this and I do not want to invent an answer - "
        f"what am I missing?"
    )



_DISTRESS_RE = re.compile(
    r"\b(?:terrified|scared|afraid|panic|anxious|worried|heartbroken|"
    r"devastated|grieving|mourning|vanished|missing|disappeared|cannot sleep|"
    r"can'?t sleep|lost my|passed away|died|hurt|alone|help me)\b",
    re.IGNORECASE,
)


def looks_like_teaching_turn(user_input: str) -> bool:
    """True when the user is clearly teaching a durable personal fact."""
    text = (user_input or "").strip()
    if not text:
        return False
    if re.search(
        r"(?i)\b(?:remember\s+(?:that\s+)?)?(?:my\s+(?:favorite\s+)?[a-z]+|"
        r"my\s+name|i\s+live\s+in|i\s+work\s+(?:as|at|in))\b",
        text,
    ):
        if re.search(r"(?i)\b(?:is\s+named|name\s+is|\bis\b|live\s+in|work\s+(?:as|at|in))\b", text):
            return True
    return False


def empathic_grounded_reply(
    user_input: str,
    emotional_state: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Brief empathic acknowledge for distress / hot affect — never invent facts."""
    state = emotional_state if isinstance(emotional_state, dict) else {}
    text = (user_input or "").strip()
    if not text or looks_questionish(text) or looks_like_teaching_turn(text):
        return None
    if is_mild_social_turn(text):
        return None
    try:
        intensity = float(state.get("intensity", 0.0) or 0.0)
    except (TypeError, ValueError):
        intensity = 0.0
    unresolved = state.get("unresolved_appraisals") or []
    emo_resp = state.get("response")
    distress = bool(_DISTRESS_RE.search(text))
    hot = intensity >= 0.55 or bool(unresolved) or distress
    if not hot:
        return None
    # Prefer emotion lobe's own line when it is a real sentence (not poison).
    if isinstance(emo_resp, str):
        cleaned = emo_resp.strip()
        if (
            cleaned
            and "How it felt:" not in cleaned
            and "What it meant:" not in cleaned
            and len(cleaned) >= 12
            and not cleaned.lower().startswith("i do not have enough grounded")
        ):
            return cleaned
    emotion = str(
        state.get("current_emotion") or state.get("emotion") or ""
    ).strip().lower()
    if distress or unresolved:
        if emotion in {"sad", "worried", "fearful", "anxious", "nostalgic"}:
            return (
                "That sounds heavy — I am sitting with how frightening this is for you. "
                "I am here."
            )
        return (
            "I hear how hard this is. I do not want to invent details — "
            "I am here with you in it."
        )
    if intensity >= 0.70:
        return "I can feel how much this matters. Tell me what you need from me right now."
    return None



def _token_stems(token: str) -> set:
    """Light stems so hike↔hiking and similar still overlap."""
    t = (token or "").lower()
    out = {t}
    if len(t) <= 3:
        return out
    if t.endswith("ing") and len(t) > 5:
        base = t[:-3]
        out.add(base)
        out.add(base + "e")  # hiking -> hike
        if base.endswith(base[-1:]) and len(base) > 2:
            out.add(base[:-1])  # running -> run
    if t.endswith("ied") and len(t) > 4:
        out.add(t[:-3] + "y")
    if t.endswith("ed") and len(t) > 4:
        out.add(t[:-2])
        out.add(t[:-1])
    if t.endswith("es") and len(t) > 4:
        out.add(t[:-2])
    elif t.endswith("s") and len(t) > 3 and not t.endswith("ss"):
        out.add(t[:-1])
    return out


def content_tokens(text: str) -> set:
    """Meaningful tokens for relevance scoring (stopwords stripped)."""
    words = re.findall(r"[a-z0-9']+", (text or "").lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 1}


def _stem_set(tokens: set) -> set:
    out = set()
    for t in tokens or set():
        out |= _token_stems(t)
    return out


def relevance_score(query: str, candidate: str) -> float:
    """Fraction of query content tokens that appear in the candidate (stem-aware)."""
    qt = content_tokens(query)
    mt = _stem_set(content_tokens(candidate))
    if not qt or not mt:
        return 0.0
    hits = sum(1 for q in qt if _token_stems(q) & mt)
    return hits / float(len(qt))


def looks_questionish(text: str) -> bool:
    return bool(_QUESTIONISH.search(text or ""))


def _looks_like_question_memory(text: str) -> bool:
    """Prior user/monday questions are not answer evidence."""
    t = (text or "").strip()
    if not t:
        return True
    if t.endswith("?"):
        return True
    if re.match(
        r"^(?:what|who|where|when|why|how|which|do|does|did|is|are|can|could|"
        r"would|should|tell|remind)\b",
        t,
        re.IGNORECASE,
    ):
        return True
    return False


def format_predicate_fact(predicate: str, obj: str, subject: str = "user") -> str:
    """Readable sentence for a stored triple — never 'Your lives in is …'."""
    pred = (predicate or "").strip()
    obj = (obj or "").strip()
    if not pred or not obj:
        return ""
    if pred.endswith("_name"):
        noun = pred[:-5].replace("_", " ").strip() or "thing"
        return f"Your {noun}'s name is {obj}."
    if pred.startswith("favorite_") or pred.startswith("favourite_"):
        return f"Your {pred.replace('_', ' ')} is {obj}."
    if pred == "lives_in":
        return f"You live in {obj}."
    if pred.startswith("work_"):
        prep = pred[5:] or "as"
        if prep == "as" and obj and obj[0].isalpha() and not obj.lower().startswith(
            ("a ", "an ", "the ")
        ):
            article = "an" if obj[0].lower() in "aeiou" else "a"
            return f"You work as {article} {obj}."
        return f"You work {prep} {obj}."
    if pred in {"codeword", "password", "passcode"}:
        return f"Your {pred} is {obj}."
    if (subject or "").lower() in {"user", "i", "me", ""}:
        return f"Your {pred.replace('_', ' ')} is {obj}."
    return f"{subject} {pred.replace('_', ' ')} {obj}".strip()



def make_grounded_structure(
    subject: str,
    relation: str,
    value: str,
    *,
    certainty: float = 1.0,
) -> Dict[str, Any]:
    """One grounded meaning unit for Language — not a finished sentence."""
    rel = (relation or "").strip()
    val = (value or "").strip()
    sub = (subject or "user").strip() or "user"
    return {
        "subject": sub,
        "relation": rel,
        "predicate": rel,
        "value": val,
        "object": val,
        "certainty": float(certainty),
    }


def parse_prose_to_structure(text: str) -> Optional[Dict[str, Any]]:
    """Strip a finished fact line into {subject, relation, value} when possible."""
    raw = (text or "").strip()
    if not raw:
        return None
    # Drop soft teaching / reflective Language wrappers if present.
    raw = re.sub(r"^(?:got it\s*[—\-]\s*)", "", raw, flags=re.I).strip()
    raw = re.sub(r"^(?:yes\s*[—\-]\s*)", "", raw, flags=re.I).strip()
    raw = re.sub(r"^(?:i\s+remember|i\s+recall)(?:\s*[—\-,:]+\s*|\s+)", "", raw, flags=re.I).strip()
    t = raw.rstrip(".!?")
    m = re.match(r"^your\s+name\s+is\s+(.+)$", t, re.IGNORECASE)
    if m:
        return make_grounded_structure("user", "name", m.group(1).strip())
    m = re.match(
        r"^your\s+([a-z][a-z0-9 ]{0,40}?)(?:'s|s')\s+name\s+is\s+(.+)$",
        t,
        re.IGNORECASE,
    )
    if m:
        noun = " ".join(m.group(1).lower().split())
        return make_grounded_structure("user", f"{noun.replace(' ', '_')}_name", m.group(2).strip())
    m = re.match(r"^you\s+live\s+in\s+(.+)$", t, re.IGNORECASE)
    if m:
        return make_grounded_structure("user", "lives_in", m.group(1).strip())
    m = re.match(
        r"^you\s+work\s+(as|at|in)\s+(?:an?\s+)?(.+)$",
        t,
        re.IGNORECASE,
    )
    if m:
        return make_grounded_structure("user", f"work_{m.group(1).lower()}", m.group(2).strip())
    m = re.match(
        r"^your\s+(favorite\s+[a-z][a-z0-9 ]{0,40}?|favourite\s+[a-z][a-z0-9 ]{0,40}?|"
        r"codeword|password|passcode)\s+is\s+(.+)$",
        t,
        re.IGNORECASE,
    )
    if m:
        attr = " ".join(m.group(1).lower().split()).replace(" ", "_")
        return make_grounded_structure("user", attr, m.group(2).strip())
    m = re.match(r"^your\s+([a-z][a-z0-9 ]{0,40}?)\s+is\s+(.+)$", t, re.IGNORECASE)
    if m:
        attr = " ".join(m.group(1).lower().split()).replace(" ", "_")
        if attr.endswith("_name") or attr == "name":
            return make_grounded_structure("user", attr, m.group(2).strip())
        return make_grounded_structure("user", attr, m.group(2).strip())
    return None


def format_structure(structure: Dict[str, Any]) -> str:
    """Neutral readable line from a structure (Language may re-tone)."""
    if not isinstance(structure, dict):
        return ""
    rel = str(structure.get("relation") or structure.get("predicate") or "").strip()
    val = str(structure.get("value") or structure.get("object") or "").strip()
    sub = str(structure.get("subject") or "user").strip() or "user"
    if not rel or not val:
        return ""
    return format_predicate_fact(rel, val, sub)


def prose_answer_to_structures(answer: str) -> List[Dict[str, Any]]:
    """Split finished multi-fact prose into structures. Unparseable lines are dropped."""
    text = (answer or "").strip()
    if not text:
        return []
    # Split on sentence boundaries while keeping abbreviations simple.
    parts = re.split(r"(?<=[.!?])\s+", text)
    out: List[Dict[str, Any]] = []
    seen = set()
    for part in parts:
        # Also allow "A. B." already split; handle "Yes — a. b." prefix.
        chunk = part.strip()
        if not chunk:
            continue
        struct = parse_prose_to_structure(chunk)
        if not struct:
            continue
        key = (struct["relation"].casefold(), struct["value"].casefold())
        if key in seen:
            continue
        seen.add(key)
        out.append(struct)
    return out


def structures_from_grounded_memories(
    user_input: str,
    memories: Iterable[Dict[str, Any]],
    *,
    min_score: float = 0.34,
) -> Optional[List[Dict[str, Any]]]:
    """Grounded meaning for Language: list of structures, or None if empty/unstructured.

    Returns None when there is no grounded fact answer (honest empty) or when the
    only answer is narrative/speech prose that cannot be structured yet.
    """
    prose = answer_from_grounded_memories(user_input, memories, min_score=min_score)
    if not isinstance(prose, str) or not prose.strip():
        return None
    structs = prose_answer_to_structures(prose)
    return structs or None


def _repair_mangled_fact(content: str) -> str:
    """Fix legacy mangled lines like 'Your lives in is Boulder.'"""
    text = (content or "").strip()
    m = re.match(r"^your\s+lives\s+in\s+is\s+(.+)$", text, re.IGNORECASE)
    if m:
        return f"You live in {m.group(1).strip(' .!?')}."
    m = re.match(r"^your\s+work\s+(as|at|in)\s+is\s+(.+)$", text, re.IGNORECASE)
    if m:
        return f"You work {m.group(1).lower()} {m.group(2).strip(' .!?')}."
    return text


def rephrase_user_memory(content: str) -> str:
    """Turn a first-person user memory into a second-person answerable line."""
    text = _repair_mangled_fact((content or "").strip())
    if not text:
        return text
    text = re.sub(r"^(?:please\s+)?remember\s+(?:that\s+)?", "", text, flags=re.I).strip()
    m = re.match(
        r"^i\s+(live|work|am|was|have|had|like|love|hate|prefer)\s+(.+)$",
        text,
        re.IGNORECASE,
    )
    if m:
        return f"You {m.group(1).lower()} {m.group(2).strip(' .!?')}."
    m = re.match(
        r"^i\s+(went|did|saw|met|bought|made|took|hiked|visited|ate|drank|"
        r"played|watched|read|wrote|drove|flew|walked|ran)\s+(.+)$",
        text,
        re.IGNORECASE,
    )
    if m:
        return f"You {m.group(1).lower()} {m.group(2).strip(' .!?')}."
    m = re.match(r"^my\s+(.+)$", text, re.IGNORECASE)
    if m:
        body = m.group(1).strip(" .!?")
        return f"Your {body}." if body else text
    if text.endswith((".", "!", "?")):
        return text
    return text + "."


def _normalize_snippet_content(memory: Dict[str, Any]) -> Optional[str]:
    """Build one clean snippet line from a memory/fact row."""
    if not isinstance(memory, dict):
        return None
    role = str(memory.get("role", "") or "").lower()
    if role not in _SPEAKER_ROLES:
        return None
    content = memory.get("content")
    if not isinstance(content, str):
        content = ""
    content = content.strip()
    if "How it felt:" in content or "What it meant:" in content:
        return None
    if re.match(r"^\s*(?:user|abin|monday|assistant)\s*:", content, re.IGNORECASE):
        return None
    pred = str(memory.get("predicate", "") or "")
    obj = str(memory.get("object", "") or "")
    sub = str(memory.get("subject", "") or "")
    if pred and obj and (role == "fact" or sub.lower() in {"user", "i", "me", ""}):
        formatted = format_predicate_fact(pred, obj, sub or "user")
        if formatted:
            content = formatted
    elif content:
        content = _repair_mangled_fact(content)
    if not content:
        return None
    return content.strip()


def _attribute_asked(query: str) -> Optional[str]:
    """Return normalized 'favorite color' / 'dog' style attribute if asked."""
    q = (query or "").strip()
    fav = re.search(
        r"\bwhat(?:'s|\s+is)\s+my\s+(favorite\s+[a-z][a-z ]{0,40}?)\b",
        q,
        re.IGNORECASE,
    )
    if fav:
        return " ".join(fav.group(1).lower().split())
    # Possessive / noun name: "what is my dog's name", "what is my sister's name"
    name_poss = re.search(
        r"\bwhat(?:'s|\s+is)\s+my\s+([a-z][a-z ]{0,40}?)(?:'s|s')\s+name\b",
        q,
        re.IGNORECASE,
    )
    if name_poss:
        return " ".join(name_poss.group(1).lower().split()) + " name"
    # Plain self-name (including compounds: "what is my name and where...")
    if re.search(r"\bwhat(?:'s|\s+is)\s+my\s+name\b", q, re.IGNORECASE):
        return "name"
    my_attr = re.search(
        r"\bwhat(?:'s|\s+is)\s+my\s+([a-z][a-z0-9 ]{0,40}?)\s*\??\s*$",
        q,
        re.IGNORECASE,
    )
    if my_attr:
        attr = " ".join(my_attr.group(1).lower().split())
        # Do not treat compound tails ("name and where do i live") as one attribute.
        if " and " in attr or " & " in attr:
            attr = attr.split(" and ")[0].split(" & ")[0].strip()
        return attr or None
    return None


def _fact_covers_attribute(fact: str, attr: str) -> bool:
    low = (fact or "").casefold()
    attr = (attr or "").strip().casefold()
    if not attr:
        return True
    if attr == "name":
        return "your name is " in low or low.startswith("your name is")
    if attr.endswith(" name"):
        noun = attr[:-5].strip()
        return f"your {noun}'s name is " in low or (
            noun in low and "name is" in low
        )
    needle = f"your {attr} is "
    if needle in low:
        return True
    # Do not let favorite color answer favorite food.
    if attr.startswith("favorite ") or attr.startswith("favourite "):
        return needle in low
    return attr in low and (" is " in low or low.startswith("you "))


def _narrative_answer(query: str, snippets: List[tuple]) -> Optional[str]:
    """Answer where/who/when from a non-patterned user narrative memory."""
    q = query or ""
    narratives = []
    for role, text in snippets:
        if role in _MONDAY_ROLES:
            continue
        if _looks_like_question_memory(text):
            continue
        if relevance_score(q, text) < 0.25 and not (
            _stem_set(content_tokens(q)) & _stem_set(content_tokens(text))
        ):
            continue
        narratives.append(text)
    if not narratives:
        return None
    # Prefer the most overlapping narrative.
    narratives.sort(key=lambda t: (-relevance_score(q, t), len(t)))
    raw = narratives[0]
    you = rephrase_user_memory(raw)

    if re.search(r"\bwhere\s+(?:did|do)\s+i\b", q, re.IGNORECASE) or re.search(
        r"\bwhere\s+did\s+i\s+go\b", q, re.IGNORECASE
    ):
        m = re.search(
            r"\b(?:hiking|went|visited|was)\s+(?:on|at|to|in)\s+"
            r"([A-Za-z0-9][A-Za-z0-9\s'-]{1,60}?)(?=\s+(?:last|with|on|at|,|\.|$))",
            raw,
            re.IGNORECASE,
        )
        if m:
            place = m.group(1).strip(" .!?")
            return f"You went to {place}." if place else you
        m = re.search(
            r"\b(?:on|at|to|in)\s+([A-Z][A-Za-z0-9\s'-]{1,60}?)(?=\s+(?:last|with|,|\.|$))",
            raw,
        )
        if m:
            return f"You went to {m.group(1).strip(' .!?')}."
        return you

    if re.search(r"\bwho\s+did\s+i\b", q, re.IGNORECASE) or re.search(
        r"\b(?:who|whom)\s+.+\bwith\b", q, re.IGNORECASE
    ):
        m = re.search(r"\bwith\s+([A-Za-z0-9][\w'-]*)", raw, re.IGNORECASE)
        if m:
            return f"You were with {m.group(1)}."
        return None

    if re.search(r"\bwhen\s+did\s+i\b", q, re.IGNORECASE):
        m = re.search(
            r"\b(last\s+\w+|yesterday|today|this\s+\w+|on\s+\w+day|"
            r"\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b",
            raw,
            re.IGNORECASE,
        )
        if m:
            return f"You went {m.group(1)}." if not m.group(1).lower().startswith("on ") else f"You went {m.group(1)}."
        return None

    return None


def _asks_about_monday_own_speech(query: str) -> bool:
    """True when the user is asking what Monday herself previously said/told/called.

    Intent-level match — not a whitelist of example sentences. Covers phrasing
    like "what did you say/tell/call", "your exact words", "remind me what you
    called/said", "the thing you said about…", "did you say you would…".
    """
    q = query or ""
    if re.search(
        r"\b(?:what (?:did|do) you (?:just )?(?:say|tell|call|mention)|"
        r"what you (?:said|told|called|mentioned)|"
        r"you said about|"
        r"what (?:were|was) your (?:exact )?words|"
        r"remind me what you (?:called|said|told|mentioned)|"
        r"what was the (?:thing|name|phrase|word|marker) you (?:said|called|told|mentioned)|"
        r"(?:what|which)\b.{0,48}\bdid you (?:say|tell|call|mention)\b|"
        r"\bdid you say you (?:would|will)\b|"
        r"\byou (?:told|said) me (?:earlier|before|about)\b)\b",
        q,
        re.IGNORECASE,
    ):
        return True
    # "What X did you say you would use / call …"
    if re.search(
        r"\bwhat\b.{0,40}\bdid you (?:say|tell|call)\b.{0,40}\b(?:you )?(?:would|will|use|call)\b",
        q,
        re.IGNORECASE,
    ):
        return True
    return False


def _monday_speech_answer(query: str, snippets: List[tuple]) -> Optional[str]:
    """Use stored Monday speech when asked what she herself said.

    Returns:
      - None when the question is not about Monday's prior speech
      - "" when it is, but no monday/assistant/abin row grounds an answer
        (caller must not fall through to user facts/memories)
      - the best matching Monday line otherwise
    """
    q = query or ""
    if not _asks_about_monday_own_speech(q):
        return None
    monday = [
        (relevance_score(q, text), text)
        for role, text in snippets
        if role in _MONDAY_ROLES and not _looks_like_question_memory(text)
    ]
    monday = [(s, t) for s, t in monday if s >= 0.15 or (content_tokens(q) & content_tokens(t))]
    if not monday:
        # Asked what Monday said — do not impersonate from user/fact rows.
        return ""
    monday.sort(key=lambda item: (-item[0], item[1]))
    best = monday[0][1]
    return best if best.endswith((".", "!", "?")) else best + "."


def answer_from_grounded_memories(
    user_input: str,
    memories: Iterable[Dict[str, Any]],
    *,
    min_score: float = 0.34,
) -> Optional[str]:
    """Build an answer from retrieved memories/facts when they match the question."""
    q = (user_input or "").strip()
    if not q:
        return None

    snippets: List[tuple] = []
    seen = set()
    for memory in memories or []:
        content = _normalize_snippet_content(memory)
        if not content:
            continue
        role = str(memory.get("role", "") or "user").lower()
        if role in {"assistant", "abin"}:
            role = "monday"
        key = content.casefold()
        if key in seen or key == q.casefold():
            continue
        seen.add(key)
        snippets.append((role if role else "user", content))

    if not snippets:
        return None


    # Prefer Monday's own prior speech when asked what she said.
    # "" means speech-intent matched but no monday/assistant/abin grounding —
    # do not answer from user memories or durable facts as if Monday said them.
    monday_ans = _monday_speech_answer(q, snippets)
    if monday_ans is not None:
        return monday_ans or None

    def _name_answer() -> Optional[str]:
        # Possessive / noun name first: "what is my dog's name"
        name_q = re.search(
            r"\bwhat(?:'s|\s+is)\s+my\s+([a-z][a-z ]{0,40}?)(?:'s|s')\s+name\b",
            q,
            re.IGNORECASE,
        )
        if name_q:
            noun = " ".join(name_q.group(1).lower().split())
            needle = f"your {noun}'s name is "
            for _role, fact in snippets:
                low = fact.casefold()
                if needle in low or (noun in low and "name is" in low):
                    return fact if fact.endswith(".") else fact + "."
            return ""  # asked, missing
        # Plain self-name (also compounds: "what is my name and where do I live")
        if re.search(r"\bwhat(?:'s|\s+is)\s+my\s+name\b", q, re.IGNORECASE):
            for _role, fact in snippets:
                low = fact.casefold()
                if "your name is " in low or low.startswith("your name is"):
                    return fact if fact.endswith(".") else fact + "."
            return ""  # asked, missing
        return None

    def _fav_answer() -> Optional[str]:
        fav_q = re.search(
            r"\bwhat(?:'s|\s+is)\s+my\s+(favorite\s+[a-z][a-z ]{0,40}?)\b",
            q,
            re.IGNORECASE,
        )
        if not fav_q:
            return None
        attr = " ".join(fav_q.group(1).lower().split())
        needle = f"your {attr} is "
        for _role, fact in snippets:
            if needle in fact.casefold():
                return fact if fact.endswith(".") else fact + "."
        return ""  # asked, missing — do not substitute another favorite

    def _live_answer() -> Optional[str]:
        if not (
            re.search(r"\bwhere\s+do\s+i\s+live\b", q, re.IGNORECASE)
            or re.search(
                r"\bwhat(?:'s|\s+is)\s+my\s+(?:city|hometown|address|location)\b",
                q,
                re.IGNORECASE,
            )
            or re.search(r"\blive(?:s)?\s+with\s+me\s+in\b", q, re.IGNORECASE)
            or re.search(r"\bwhere\s+i\s+live\b", q, re.IGNORECASE)
        ):
            return None
        for _role, fact in snippets:
            low = fact.casefold()
            if any(
                key in low
                for key in (
                    "live in",
                    "lives in",
                    "living in",
                    "hometown is",
                    "city is",
                    "location is",
                )
            ):
                return rephrase_user_memory(fact)
        return ""

    def _job_answer() -> Optional[str]:
        if not (
            re.search(r"\bwhere\s+do\s+i\s+work\b", q, re.IGNORECASE)
            or re.search(
                r"\bwhat(?:'s|\s+is)\s+my\s+(?:job|work|occupation|profession)\b",
                q,
                re.IGNORECASE,
            )
        ):
            return None
        for _role, fact in snippets:
            low = fact.casefold()
            if any(
                key in low
                for key in (
                    "job is",
                    "work as",
                    "work at",
                    "work in",
                    "occupation is",
                    "profession is",
                )
            ):
                return rephrase_user_memory(fact)
        return ""

    def _dog_answer() -> Optional[str]:
        if not re.search(r"\b(?:my\s+)?dog\b", q, re.IGNORECASE):
            return None
        # Prefer name fact when dog is mentioned.
        for _role, fact in snippets:
            low = fact.casefold()
            if "dog" in low and "name is" in low:
                return fact if fact.endswith(".") else fact + "."
        return None  # dog mentioned but no forced empty

    def _codeword_answer() -> Optional[str]:
        if not re.search(r"\bcodeword\b", q, re.IGNORECASE):
            return None
        for _role, fact in snippets:
            low = fact.casefold()
            if "codeword is" in low:
                return fact if fact.endswith(".") else fact + "."
        return ""

    def _generic_my_attr() -> Optional[str]:
        my_attr = re.search(
            r"\bwhat(?:'s|\s+is)\s+my\s+([a-z][a-z0-9 ]{0,40}?)\s*\??\s*$",
            q,
            re.IGNORECASE,
        )
        if not my_attr:
            return None
        attr = " ".join(my_attr.group(1).lower().split())
        if not attr or attr.endswith(" name") or attr.startswith("favorite"):
            return None
        if attr in {"job", "work", "occupation", "profession", "city", "hometown", "location", "address"}:
            return None  # handled by job/live
        needle = f"your {attr} is "
        for _role, fact in snippets:
            if needle in fact.casefold():
                return fact if fact.endswith(".") else fact + "."
        for _role, fact in snippets:
            low = fact.casefold()
            if low.startswith(f"my {attr} is ") or low.startswith(f"your {attr} is "):
                return rephrase_user_memory(fact)
        return ""  # asked specific attr, missing

    slot_fns = (
        _name_answer,
        _fav_answer,
        _live_answer,
        _job_answer,
        _dog_answer,
        _codeword_answer,
        _generic_my_attr,
    )
    slot_hits = []
    slot_miss_forced = False
    for fn in slot_fns:
        got = fn()
        if got is None:
            continue
        if got == "":
            # Pattern matched the question but no grounded fact — honest empty
            # unless other slots still fill a compound question.
            slot_miss_forced = True
            continue
        # Prefer clean structure-backed fact lines (strip prior Language tone framing).
        cleaned = format_structure(parse_prose_to_structure(got) or {}) or got
        if not cleaned:
            cleaned = got
        key = cleaned.casefold()
        if key not in {s.casefold() for s in slot_hits}:
            slot_hits.append(cleaned if cleaned.endswith((".", "!", "?")) else cleaned + ".")

    if len(slot_hits) >= 2:
        joined = " ".join(slot_hits)
        if re.match(r"^(?:do|does|did|is|are|have)\b", q, re.IGNORECASE):
            return f"Yes — {joined[0].lower() + joined[1:]}"
        return joined
    if len(slot_hits) == 1:
        # Single slot hit. If another slot was explicitly asked and missed, stay honest
        # only when the hit is unrelated to a forced miss on a sole attribute question.
        if slot_miss_forced and not re.search(r"\b(?:and|&|both|also|who|with)\b", q, re.IGNORECASE):
            # e.g. favorite food missed — do not return an unrelated live/job hit.
            # But name/fav miss with only one hit from another fn shouldn't happen often.
            only_attr = _attribute_asked(q)
            if only_attr and not _fact_covers_attribute(slot_hits[0], only_attr):
                return None
        return slot_hits[0]
    if slot_miss_forced and not slot_hits:
        return None

    # Narrative where/who/when from non-patterned user memories.
    narr = _narrative_answer(q, snippets)
    if narr:
        return narr

    if not looks_questionish(q):
        return None

    attr = _attribute_asked(q)
    q_tokens = content_tokens(q)
    q_stems = _stem_set(q_tokens)
    ranked = []
    for role, text_snip in snippets:
        if _looks_like_question_memory(text_snip):
            continue
        if attr and not _fact_covers_attribute(text_snip, attr):
            continue
        score = relevance_score(q, text_snip)
        if role == "fact":
            score += 0.05
        if role in _MONDAY_ROLES:
            score += 0.02
        # Require real stem overlap — no cosine-style invention.
        if not (q_stems & _stem_set(content_tokens(text_snip))):
            continue
        if score >= min_score:
            ranked.append((score, 0 if role == "fact" else 1, text_snip, role))

    if not ranked:
        return None

    # Compound questions: combine distinct grounded facts when several match.
    compound = bool(
        re.search(r"\b(?:and|&)\b", q, re.IGNORECASE)
        or re.search(r"\b(?:both|also)\b", q, re.IGNORECASE)
    )
    ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
    if compound and len(ranked) >= 2:
        chosen = []
        seen_keys = set()
        for score, _prio, text_snip, role in ranked:
            if score < min_score:
                continue
            key = text_snip.casefold()
            # Dedup near-identical / same-slot facts.
            slot = key
            for marker in ("live in", "work as", "work at", "name is", "favorite "):
                if marker in key:
                    slot = marker
                    break
            if slot in seen_keys:
                continue
            seen_keys.add(slot)
            line = (
                text_snip
                if (role == "fact" or text_snip.casefold().startswith("your ")
                    or text_snip.casefold().startswith("you "))
                else rephrase_user_memory(text_snip)
            )
            if not line.endswith((".", "!", "?")):
                line += "."
            chosen.append(line)
            if len(chosen) >= 3:
                break
        if len(chosen) >= 2:
            joined = " ".join(chosen)
            if re.match(r"^(?:do|does|did|is|are|have)\b", q, re.IGNORECASE):
                return f"Yes — {joined[0].lower() + joined[1:]}" if joined else joined
            return joined
        if chosen:
            return chosen[0]

    _best_score, _, best_text, best_role = ranked[0]
    # Strict attribute questions already returned None above when uncovered.
    # For general ranked hits, require majority token coverage when ≥2 tokens.
    if len(q_tokens) >= 2 and _best_score < 0.5:
        # Allow if every significant (≥4) query token is covered.
        significant = {t for t in q_tokens if len(t) >= 4}
        cand_stems = _stem_set(content_tokens(best_text))
        if significant and not all(_token_stems(t) & cand_stems for t in significant):
            return None
    if best_role == "fact" or best_text.casefold().startswith(("your ", "you ")):
        return best_text if best_text.endswith(".") else best_text + "."
    return rephrase_user_memory(best_text)


class ResponseProvider(Protocol):
    """Supplies a final, semantically grounded response for a user prompt."""

    def render(
        self,
        user_input: str,
        understanding: Dict[str, Any],
        memories: Iterable[Dict[str, Any]],
    ) -> str:
        """Return a complete user-facing response."""


@dataclass(frozen=True)
class DeterministicResponseProvider:
    """A credential-free provider backed by stored facts and a small verified set."""

    _greeting: re.Pattern[str] = re.compile(
        r"^\s*(?:hello|hi|hey|sup|yo|hiya|howdy)(?:\s+(?:there|you|friend))?(?:\s*[!.,]*)?\s*$",
        re.IGNORECASE,
    )
    _gravity: re.Pattern[str] = re.compile(r"\bgravity\b", re.IGNORECASE)
    _memory: re.Pattern[str] = re.compile(r"\bmemory\b", re.IGNORECASE)
    _transcript: re.Pattern[str] = re.compile(r"^\s*(?:user|abin)\s*:", re.IGNORECASE)
    _name_question: re.Pattern[str] = re.compile(
        r"\bwhat(?:'s|\s+is)\s+my\s+([a-z][a-z ]{0,40}?)(?:'s|s')?\s+name\b",
        re.IGNORECASE,
    )
    _favorite_question: re.Pattern[str] = re.compile(
        r"\bwhat(?:'s|\s+is)\s+my\s+(favorite\s+[a-z][a-z ]{0,40}?)\b",
        re.IGNORECASE,
    )
    _named_fact: re.Pattern[str] = re.compile(
        r"\b(?:remember\s+(?:that\s+)?)?my\s+([a-z]+(?:\s+[a-z]+){0,3})\s+is\s+named\s+"
        r"([A-Za-z0-9][\w-]{0,40})\b",
        re.IGNORECASE,
    )
    _name_is_fact: re.Pattern[str] = re.compile(
        r"\b(?:remember\s+(?:that\s+)?)?my\s+([a-z]+(?:\s+[a-z]+){0,3})(?:'s|s')\s+name\s+is\s+"
        r"([A-Za-z0-9][\w-]{0,40})\b",
        re.IGNORECASE,
    )
    _favorite_fact: re.Pattern[str] = re.compile(
        r"\bmy\s+(favorite\s+[a-z][a-z ]{0,40}?)\s+is\s+"
        r"([a-z0-9][a-z0-9 -]{0,80}?)(?:[.!?]|$)",
        re.IGNORECASE,
    )

    def _safe_memories(self, memories: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        clean: List[Dict[str, Any]] = []
        for memory in memories:
            if not isinstance(memory, dict):
                continue
            role = str(memory.get("role", "") or "").lower()
            content = memory.get("content")
            if role not in _SPEAKER_ROLES:
                continue
            if not isinstance(content, str) or not content.strip():
                # Keep fact triples that only have predicate/object.
                if not (memory.get("predicate") and memory.get("object")):
                    continue
            if isinstance(content, str) and "How it felt:" in content:
                continue
            if isinstance(content, str) and self._transcript.match(content):
                continue
            clean.append(memory)
        return clean

    def _answer_from_facts(self, user_input: str, memories: List[Dict[str, Any]]) -> Optional[str]:
        return answer_from_grounded_memories(user_input, memories)

    def _teaching_ack(self, user_input: str) -> Optional[str]:
        text = user_input or ""
        parts: List[str] = []

        # Compound-safe: my name is X (stop before "and …")
        own_name = re.search(
            r"(?i)\b(?:remember\s+(?:that\s+)?)?my\s+name\s+is\s+"
            r"([A-Za-z][\w-]{0,40})(?=\s+and\b|[.!?,]|$)",
            text,
        )
        if own_name:
            parts.append(f"your name is {own_name.group(1).strip()}")

        for pattern, kind in (
            (self._name_is_fact, "name"),
            (self._named_fact, "name"),
            (self._favorite_fact, "favorite"),
        ):
            match = pattern.search(text)
            if not match:
                continue
            if kind == "name":
                noun = " ".join(match.group(1).lower().split())
                if re.search(r"\b(?:is|are|and|named)\b", noun):
                    continue
                value = match.group(2).strip(" .!?")
                parts.append(f"your {noun}'s name is {value}")
            else:
                attr = " ".join(match.group(1).lower().split())
                value = match.group(2).strip(" .!?")
                if re.search(r"(?i)\band\s+(?:i|my)\b", value):
                    value = re.split(r"(?i)\s+and\s+(?:i|my)\b", value, maxsplit=1)[0].strip()
                parts.append(f"your {attr} is {value}")

        live = re.search(
            r"(?i)\b(?:remember\s+(?:that\s+)?)?i\s+live\s+in\s+"
            r"([A-Za-z0-9][A-Za-z0-9\s,.-]{0,60}?)(?=\s+and\s+i\b|[.!?]|$)",
            text,
        )
        if live:
            place = live.group(1).strip(" .!?")
            if place and not re.search(r"(?i)\band\s+i\b", place):
                parts.append(f"you live in {place}")

        work = re.search(
            r"(?i)\b(?:remember\s+(?:that\s+)?)?i\s+work\s+(as|at|in)\s+"
            r"([A-Za-z0-9][A-Za-z0-9\s,.-]{0,60}?)(?=\s+and\s+i\b|[.!?]|$)",
            text,
        )
        if work:
            job = work.group(2).strip(" .!?")
            if job and not re.search(r"(?i)\band\s+i\b", job):
                parts.append(f"you work {work.group(1).lower()} {job}")

        if not parts:
            generic = re.search(
                r"(?i)\b(?:remember\s+(?:that\s+)?)?my\s+([a-z]+(?:\s+[a-z]+){0,3})\s+is\s+"
                r"([a-z0-9][a-z0-9 -]{0,80}?)(?=\s+and\s+(?:i|my)\b|[.!?]|$)",
                text,
            )
            if generic:
                noun = " ".join(generic.group(1).lower().split())
                value = generic.group(2).strip(" .!?")
                fragile = {
                    "day", "life", "mood", "feeling", "feelings", "time", "thing",
                    "stuff", "question", "answer", "message", "chat", "conversation",
                    "thought", "idea", "problem", "issue", "way", "point", "one",
                }
                if (
                    noun
                    and value
                    and not noun.startswith("favorite ")
                    and " name" not in noun
                    and not value.lower().startswith("named ")
                    and noun not in fragile
                    and not re.search(r"\b(?:is|are|and|named)\b", noun)
                    and not any(value.lower().startswith(p) for p in (
                        "going", "feeling", "looking", "doing", "getting", "being",
                        "really", "just", "kinda", "kind of", "sort of", "pretty",
                        "great", "good", "bad", "fine", "okay", "ok",
                    ))
                ):
                    parts.append(f"your {noun} is {value}")

        if not parts:
            return None
        # Dedup while preserving order
        seen = set()
        clean = []
        for p in parts:
            key = p.casefold()
            if key in seen:
                continue
            seen.add(key)
            clean.append(p)
        if len(clean) == 1:
            return f"Got it — {clean[0]}."
        return f"Got it — {clean[0]}, and {clean[1]}."

    def render(
        self,
        user_input: str,
        understanding: Dict[str, Any],
        memories: Iterable[Dict[str, Any]],
    ) -> str:
        """Realize intent from the prompt and grounded fact memories."""
        clean_memories = self._safe_memories(memories)

        if self._greeting.fullmatch(user_input or ""):
            return "Hello! How can I help?"

        if re.search(
            r"\b(?:are you okay|how are you|how(?:'s| is) it going)\b",
            user_input or "",
            re.IGNORECASE,
        ):
            return "I'm here — thanks for checking in. How are you?"

        teaching = self._teaching_ack(user_input or "")
        if teaching:
            return teaching

        fact_answer = self._answer_from_facts(user_input or "", clean_memories)
        if fact_answer:
            return fact_answer

        if self._gravity.search(user_input or ""):
            return (
                "Gravity is the force of attraction between masses. "
                "It pulls objects toward each other, which is why objects fall toward Earth."
            )
        if self._memory.search(user_input or ""):
            return "Memory is information retained so it can be retrieved and used later."

        intent = understanding.get("intent") if isinstance(understanding, dict) else None
        emo_state = None
        if isinstance(understanding, dict):
            emo_state = understanding.get("emotion_result") or understanding.get("emotional_state")
        empathic = empathic_grounded_reply(user_input or "", emo_state if isinstance(emo_state, dict) else None)
        if empathic:
            return empathic

        if intent in {"question", "request"} or looks_questionish(user_input or ""):
            return (
                "I do not have enough grounded information to answer that. "
                "Please provide more context or a fact I can reason from."
            )
        return "I understand. Please tell me more about what you would like to discuss."
