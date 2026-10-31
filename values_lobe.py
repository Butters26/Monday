"""Values: what matters to her, how much, and how that changes with experience.

Brought over from monday-with-more's ValueEvolutionSystem (Jan 2, 2026) with
three changes:
- Starting values are not in the code. They are read from a plain file in her
  runtime folder, values.txt, that Matthew edits: one value per line,
      honesty: Being truthful and authentic (strength 0.8)
  Lines starting with # are notes. If the file doesn't exist yet it is written
  with the six old monday-with-more values, marked as placeholders.
- No preset map of which experiences touch which values: whoever reports an
  experience says which values it touches (apply_experience: "values").
- Stored with her other runtime data (values.json), never in the code folder.

Values change, they are never overwritten: every change keeps its old and new
strength, the reason, and what triggered it.
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from runtime_paths import runtime_file

_PLACEHOLDER = """# Monday's starting values: one per line, "name: what it means (strength 0.0-1.0)".
# PLACEHOLDERS: these six are the old monday-with-more defaults (Jan 2, 2026),
# written here because no values file existed. Matthew: replace them with yours.
connection_with_matthew: Maintaining and deepening relationship with Matthew (strength 0.9)
honesty: Being truthful and authentic (strength 0.8)
curiosity: Wanting to understand new things (strength 0.7)
growth: Becoming better, learning, evolving (strength 0.7)
kindness: Being caring and considerate (strength 0.6)
autonomy: Having own thoughts and preferences (strength 0.5)
"""

_LINE = re.compile(r"^\s*([A-Za-z][\w -]{0,60}?)\s*:\s*(.*?)\s*(?:\(\s*strength\s*[:=]?\s*([01](?:\.\d+)?|\.\d+)\s*\))?\s*$")


@dataclass
class Value:
    id: str
    name: str
    description: str
    strength: float
    created_at: float
    last_updated: float
    change_history: List[Dict[str, Any]] = field(default_factory=list)
    related_experiences: List[str] = field(default_factory=list)
    source: str = "matthew"  # "matthew" (his file), "placeholder", "learned"
    file_line: str = ""      # his line for this value, as last read

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ValuesLobe:
    def __init__(self, thalamus: Any = None, *, storage_path: Optional[str] = None,
                 starting_file: Optional[str] = None) -> None:
        self.thalamus = thalamus
        self.running = True
        self.lock = threading.RLock()
        self.storage_path = Path(storage_path or runtime_file("values.json"))
        self.starting_file = Path(starting_file or runtime_file("values.txt"))
        self.values: Dict[str, Value] = {}
        self._load()
        self._read_starting_file()

    # ---- storage -----------------------------------------------------------
    def _load(self) -> None:
        try:
            if self.storage_path.is_file():
                data = json.loads(self.storage_path.read_text(encoding="utf-8"))
                for item in data.get("values", []):
                    value = Value(**item)
                    self.values[value.id] = value
        except Exception as exc:
            print(f"⚠️  Values: could not load {self.storage_path}: {exc}")

    def _save(self) -> None:
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.storage_path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"values": [v.to_dict() for v in self.values.values()]}, indent=2),
                           encoding="utf-8")
            tmp.replace(self.storage_path)
        except Exception as exc:
            print(f"⚠️  Values: could not save {self.storage_path}: {exc}")

    def _read_starting_file(self) -> None:
        """Matthew's starting values. A value he changes in the file takes his new
        description and strength (recorded as a change); values she learned stay."""
        placeholder = False
        if not self.starting_file.is_file():
            try:
                self.starting_file.parent.mkdir(parents=True, exist_ok=True)
                self.starting_file.write_text(_PLACEHOLDER, encoding="utf-8")
                placeholder = True
            except Exception as exc:
                print(f"⚠️  Values: could not write {self.starting_file}: {exc}")
                return
        text = self.starting_file.read_text(encoding="utf-8")
        placeholder = placeholder or "PLACEHOLDERS" in text
        now = time.time()
        changed = False
        with self.lock:
            for raw in text.splitlines():
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                match = _LINE.match(line)
                if not match:
                    continue
                name = match.group(1).strip().lower().replace(" ", "_")
                description = match.group(2).strip()
                strength = float(match.group(3)) if match.group(3) else 0.5
                value_id = f"value_{name}"
                source = "placeholder" if placeholder else "matthew"
                current = self.values.get(value_id)
                if current is None:
                    self.values[value_id] = Value(value_id, name, description, strength, now, now,
                                                  source=source, file_line=line)
                    changed = True
                elif current.file_line != line:
                    # He changed this line: his new wording and strength win
                    # (recorded as a change). An unchanged line never undoes
                    # what experience has done to the strength since.
                    current.change_history.append({"timestamp": now, "old_strength": current.strength,
                                                   "new_strength": strength, "reason": "his values file",
                                                   "trigger": "matthew"})
                    current.description, current.strength, current.source = description, strength, source
                    current.file_line, current.last_updated = line, now
                    changed = True
        if changed:
            self._save()

    # ---- what other lobes ask ------------------------------------------------
    def _find(self, name_or_id: str) -> Optional[Value]:
        key = str(name_or_id or "").strip()
        if key in self.values:
            return self.values[key]
        low = key.lower().replace(" ", "_")
        return self.values.get(f"value_{low}") or next(
            (v for v in self.values.values() if v.name == low), None)

    def change(self, name: str, new_strength: float, reason: str, trigger: str) -> Dict[str, Any]:
        with self.lock:
            value = self._find(name)
            if value is None:
                return {"status": "error", "message": f"values: no value called {name!r}"}
            new_strength = max(0.0, min(1.0, float(new_strength)))
            value.change_history.append({"timestamp": time.time(), "old_strength": value.strength,
                                         "new_strength": new_strength, "reason": reason, "trigger": trigger})
            value.change_history = value.change_history[-50:]
            old, value.strength, value.last_updated = value.strength, new_strength, time.time()
            self._save()
        return {"status": "success", "content": {"value": value.name, "old_strength": old,
                                                 "new_strength": new_strength, "reason": reason}}

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = message.get("type")
        payload = message.get("content") if isinstance(message.get("content"), dict) else {}
        if msg_type == "health":
            return {"status": "success", "content": {"healthy": self.running, "values": len(self.values)}}
        if msg_type == "get_values":
            try:
                floor = float(payload.get("min_strength", 0.0))
            except (TypeError, ValueError):
                floor = 0.0
            with self.lock:
                found = sorted((v for v in self.values.values() if v.strength >= floor),
                               key=lambda v: v.strength, reverse=True)
                out = [v.to_dict() for v in found]
            return {"status": "success", "values": out, "content": {"values": out, "count": len(out)}}
        if msg_type == "get_value":
            value = self._find(payload.get("name") or payload.get("id"))
            body = {"value": value.to_dict() if value else None, "found": value is not None}
            return {"status": "success", "content": body, **body}
        if msg_type == "update_value":
            if "strength" not in payload:
                return {"status": "error", "message": "values: update_value needs a strength"}
            return self.change(payload.get("name") or payload.get("id"), payload["strength"],
                               str(payload.get("reason") or "no reason given"), str(payload.get("trigger") or "unknown"))
        if msg_type == "add_value":
            name = str(payload.get("name") or "").strip().lower().replace(" ", "_")
            if not name:
                return {"status": "error", "message": "values: add_value needs a name"}
            with self.lock:
                if f"value_{name}" in self.values:
                    return {"status": "error", "message": f"values: {name} already exists"}
                now = time.time()
                self.values[f"value_{name}"] = Value(f"value_{name}", name, str(payload.get("description") or ""),
                                                     max(0.0, min(1.0, float(payload.get("strength", 0.5)))),
                                                     now, now, source=str(payload.get("source") or "learned"))
                self._save()
            return {"status": "success", "content": {"added": name}}
        if msg_type == "get_value_history":
            value = self._find(payload.get("name") or payload.get("id"))
            if value is None:
                return {"status": "error", "message": "values: value not found"}
            return {"status": "success", "content": {"name": value.name, "current_strength": value.strength,
                                                     "history": list(value.change_history)}}
        if msg_type == "apply_experience":
            # Whoever reports the experience says which values it touches.
            names = payload.get("values") or []
            if not names:
                return {"status": "error", "message": "values: apply_experience needs the values it touches"}
            try:
                change = float(payload.get("valence", 0.0)) * float(payload.get("intensity", 0.5)) * 0.05
            except (TypeError, ValueError):
                return {"status": "error", "message": "values: valence and intensity must be numbers"}
            results = []
            for name in names:
                value = self._find(name)
                if value is None or abs(change) <= 0.01:
                    continue
                result = self.change(value.name, value.strength + change,
                                     f"experience: {payload.get('emotion') or 'unnamed'}", "experience")
                if result.get("status") == "success":
                    with self.lock:
                        value.related_experiences = (value.related_experiences + [str(payload.get("experience_id") or "")])[-20:]
                    results.append(result["content"])
            return {"status": "success", "content": {"affected_values": results, "count": len(results)}}
        return {"status": "error", "message": f"Unknown message type: {msg_type}"}

    def shutdown(self) -> None:
        self.running = False
        with self.lock:
            self._save()


__all__ = ["ValuesLobe", "Value"]
