"""
SensoryIntegrationLobe — unify Perception modality envelopes into one live stream.

Perception owns per-sense intake (text / audio / vision). This lobe fuses those
envelopes into a single multi-modal stream the live path uses for Attention
salience and shared context handed to Conversation. Not a Perception rebuild;
not mic/webcam theater — honest when hardware is unavailable.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence, Union


InputItem = Union[str, Dict[str, Any]]


class SensoryIntegrationLobe:
    CONTEXT_WINDOW_SEC = 120.0

    def __init__(self, thalamus=None):
        self.thalamus = thalamus
        self.sensory_buffer: List[Any] = []
        self.normalized_signals: List[Any] = []
        self.modality_envelopes: List[Dict[str, Any]] = []
        # Per-user live state (isolation: user A vision must not fold into user B).
        self._unified_by_user: Dict[str, Dict[str, Any]] = {}
        self._shared_by_user: Dict[str, Dict[str, Any]] = {}
        self._attention_by_user: Dict[str, Dict[str, Any]] = {}
        # Backward-compat aliases for "default" user (tests / status).
        self.unified_stream: Optional[Dict[str, Any]] = None
        self.shared_context: Dict[str, Any] = self._empty_shared_context()
        self.attention_payload: Dict[str, Any] = {}

    def _empty_shared_context(self) -> Dict[str, Any]:
        return {
            "modalities_seen": [],
            "concepts": [],
            "entities": [],
            "novelty_flags": [],
            "recent_texts": [],
            "by_modality": {},
            "updated_at": None,
            "user_id": None,
        }

    def _uid(self, user_id: Optional[str] = None) -> str:
        return str(user_id or "default")

    def _shared_for(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        uid = self._uid(user_id)
        if uid not in self._shared_by_user:
            ctx = self._empty_shared_context()
            ctx["user_id"] = uid
            self._shared_by_user[uid] = ctx
        return self._shared_by_user[uid]

    def _set_unified(self, user_id: Optional[str], stream: Optional[Dict[str, Any]]) -> None:
        uid = self._uid(user_id)
        if stream is None:
            self._unified_by_user.pop(uid, None)
        else:
            self._unified_by_user[uid] = stream
        if uid == "default":
            self.unified_stream = stream

    def _set_attention(self, user_id: Optional[str], payload: Dict[str, Any]) -> None:
        uid = self._uid(user_id)
        self._attention_by_user[uid] = dict(payload or {})
        if uid == "default":
            self.attention_payload = self._attention_by_user[uid]

    def _modality_observed_at(self, env: Dict[str, Any]) -> float:
        """Per-modality timestamp; do not use shared_context.updated_at."""
        for key in ("observed_at", "updated_at"):
            raw = env.get(key)
            if raw is not None:
                try:
                    return float(raw)
                except (TypeError, ValueError):
                    pass
        meta = env.get("raw_meta") if isinstance(env.get("raw_meta"), dict) else {}
        for key in ("observed_at", "fused_at", "timestamp"):
            raw = meta.get(key) if isinstance(meta, dict) else None
            if raw is not None:
                try:
                    return float(raw)
                except (TypeError, ValueError):
                    pass
        return 0.0

    def _stamp_modality(self, env: Dict[str, Any], *, now: Optional[float] = None) -> Dict[str, Any]:
        """Ensure envelope carries its own observed_at (preserve if already set)."""
        out = dict(env)
        existing = self._modality_observed_at(out)
        ts = existing if existing > 0.0 else float(now if now is not None else time.time())
        out["observed_at"] = ts
        out["updated_at"] = ts
        return out

    def _prune_stale_modalities(
        self, by_modality: Dict[str, Any], *, now: Optional[float] = None
    ) -> Dict[str, Dict[str, Any]]:
        """Drop modalities whose own observed_at is older than the window."""
        now = float(now if now is not None else time.time())
        kept: Dict[str, Dict[str, Any]] = {}
        for mod, env in (by_modality or {}).items():
            if not isinstance(env, dict):
                continue
            age = now - self._modality_observed_at(env)
            if age <= self.CONTEXT_WINDOW_SEC:
                kept[str(mod)] = dict(env)
        return kept

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def integrate_inputs(
        self,
        inputs: Sequence[InputItem],
        *,
        user_id: str = "default",
        route_attention: bool = True,
        precomputed: Optional[Sequence[Dict[str, Any]]] = None,
        primary_modality: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Normalize inputs, perceive via Perception, fuse, optionally Attention.

        Returns the unified stream envelope (always a dict).
        """
        items = list(inputs or [])
        self.sensory_buffer.extend(items)
        self.normalized_signals = self._normalize(items)

        envelopes: List[Dict[str, Any]] = []
        if precomputed:
            for env in precomputed:
                if isinstance(env, dict) and env:
                    envelopes.append(dict(env))
        elif self.normalized_signals:
            envelopes = self._perceive_normalized(
                self.normalized_signals, user_id=user_id
            )

        stream = self._fuse_envelopes(
            envelopes, user_id=user_id, primary_modality=primary_modality
        )
        self.modality_envelopes = list(envelopes)
        self._set_unified(user_id, stream)
        self._update_shared_context(stream, user_id=user_id)

        if route_attention and self.thalamus and stream.get("attention_signals"):
            attn = self._route_to_attention(stream, user_id=user_id)
            self._set_attention(user_id, attn)
            if attn:
                stream = dict(stream)
                stream["attention_focus"] = attn.get("focus")
                stream["attention_priority"] = [
                    str(r.get("id") or "")
                    for r in (attn.get("ranked") or [])
                    if isinstance(r, dict)
                ][:8]
                self._set_unified(user_id, stream)
                self._update_shared_context(stream, user_id=user_id)

        return stream

    def absorb_envelope(
        self,
        envelope: Dict[str, Any],
        *,
        user_id: str = "default",
        route_attention: bool = False,
    ) -> Dict[str, Any]:
        """Fold a precomputed Perception envelope into this user's shared stream.

        Used by the live text path so SI stays warm without re-perceiving.
        Merges with any recent multi-modal context still in *this* user_id's
        shared_context. Each prior modality expires on its own observed_at
        (~120s), not on a shared updated_at refreshed by other modalities.
        """
        uid = self._uid(user_id)
        if not isinstance(envelope, dict) or not envelope:
            return dict(self._unified_by_user.get(uid) or self.unified_stream or {})

        now = time.time()
        fresh = self._stamp_modality(dict(envelope), now=now)
        envelopes: List[Dict[str, Any]] = [fresh]
        # Bring forward OTHER modalities still fresh for THIS user only.
        primary = str(envelope.get("modality") or "text").lower()
        prior_by = self._prune_stale_modalities(
            dict(self._shared_for(uid).get("by_modality") or {}), now=now
        )
        for mod, prior_env in prior_by.items():
            if not isinstance(prior_env, dict):
                continue
            if str(mod).lower() == primary:
                continue
            # Keep recent cross-modal context for this modality's own window.
            age = now - self._modality_observed_at(prior_env)
            if age <= self.CONTEXT_WINDOW_SEC:
                # Preserve prior observed_at (do not refresh on absorb).
                envelopes.append(dict(prior_env))

        return self.integrate_inputs(
            [],
            user_id=uid,
            route_attention=route_attention,
            precomputed=envelopes,
            primary_modality=primary,
        )

    def get_unified_stream(self, user_id: str = "default") -> Dict[str, Any]:
        uid = self._uid(user_id)
        stream = self._unified_by_user.get(uid)
        if stream is None and uid == "default":
            stream = self.unified_stream
        return dict(stream or {})

    def get_shared_context(self, user_id: str = "default") -> Dict[str, Any]:
        """Return this user_id's shared context with stale modalities pruned."""
        uid = self._uid(user_id)
        ctx = dict(self._shared_for(uid))
        now = time.time()
        by_mod = self._prune_stale_modalities(ctx.get("by_modality") or {}, now=now)
        ctx["by_modality"] = by_mod
        ctx["modalities_seen"] = list(by_mod.keys())
        ctx["user_id"] = uid
        # Persist prune so shared state stays honest.
        stored = self._shared_for(uid)
        stored["by_modality"] = by_mod
        stored["modalities_seen"] = list(by_mod.keys())
        if uid == "default":
            self.shared_context = stored
        return dict(ctx)

    def reset(self, user_id: Optional[str] = None) -> None:
        """Reset one user (user_id=...) or all users (default)."""
        self.sensory_buffer.clear()
        self.normalized_signals.clear()
        self.modality_envelopes.clear()
        if user_id is None:
            self._unified_by_user.clear()
            self._shared_by_user.clear()
            self._attention_by_user.clear()
            self.unified_stream = None
            self.attention_payload = {}
            self.shared_context = self._empty_shared_context()
            return
        uid = self._uid(user_id)
        self._unified_by_user.pop(uid, None)
        self._shared_by_user.pop(uid, None)
        self._attention_by_user.pop(uid, None)
        if uid == "default":
            self.unified_stream = None
            self.attention_payload = {}
            self.shared_context = self._empty_shared_context()

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = message.get("type")
        if "content" in message:
            content = message.get("content", {})
        else:
            content = {
                k: v
                for k, v in message.items()
                if k not in ("type", "_message_id", "message_id")
            }
        if not isinstance(content, dict):
            content = {}

        if msg_type in ("ingest", "integrate", "integrate_inputs"):
            inputs = content.get("inputs", [])
            if not isinstance(inputs, list):
                inputs = [inputs] if inputs else []
            precomputed = content.get("precomputed")
            primary = content.get("primary_modality")
            if not primary and inputs:
                first = inputs[0]
                if isinstance(first, dict):
                    primary = first.get("modality") or first.get("type")
                elif isinstance(first, str):
                    primary = "text"
            stream = self.integrate_inputs(
                inputs,
                user_id=str(content.get("user_id") or "default"),
                route_attention=bool(content.get("route_attention", True)),
                precomputed=precomputed if isinstance(precomputed, list) else None,
                primary_modality=str(primary) if primary else None,
            )
            return {
                "status": "success",
                "content": stream,
                "stream": stream,
                "signals": self.normalized_signals,
            }

        if msg_type in ("absorb", "absorb_envelope"):
            envelope = content.get("envelope") or content.get("perception") or {}
            if not isinstance(envelope, dict):
                envelope = {}
            stream = self.absorb_envelope(
                envelope,
                user_id=str(content.get("user_id") or "default"),
                route_attention=bool(content.get("route_attention", False)),
            )
            return {"status": "success", "content": stream, "stream": stream}

        if msg_type in ("get_stream", "get_unified_stream"):
            uid = str(content.get("user_id") or "default")
            return {
                "status": "success",
                "content": self.get_unified_stream(user_id=uid),
            }

        if msg_type in ("get_context", "get_shared_context"):
            uid = str(content.get("user_id") or "default")
            return {
                "status": "success",
                "content": self.get_shared_context(user_id=uid),
            }

        if msg_type == "reset":
            raw_uid = content.get("user_id")
            self.reset(user_id=str(raw_uid) if raw_uid else None)
            return {"status": "success", "message": "SensoryIntegrationLobe reset"}

        if msg_type == "get_status":
            uid = str(content.get("user_id") or "default")
            stream = self._unified_by_user.get(uid) or (
                self.unified_stream if uid == "default" else None
            ) or {}
            shared = self.get_shared_context(user_id=uid)
            attn = self._attention_by_user.get(uid) or (
                self.attention_payload if uid == "default" else {}
            )
            return {
                "status": "success",
                "content": {
                    "buffer_size": len(self.sensory_buffer),
                    "last_normalized": len(self.normalized_signals),
                    "envelope_count": len(self.modality_envelopes),
                    "modalities": list(stream.get("modalities") or []),
                    "has_unified_stream": bool(stream),
                    "shared_modalities": list(shared.get("modalities_seen") or []),
                    "attention_focus": (attn or {}).get("focus"),
                    "user_id": uid,
                },
            }

        return {"status": "error", "message": f"Unknown message type: {msg_type}"}

    # ------------------------------------------------------------------
    # Normalize / perceive / fuse
    # ------------------------------------------------------------------

    def _normalize(self, inputs: Sequence[InputItem]) -> List[Any]:
        normalized: List[Any] = []
        for item in inputs:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    normalized.append(
                        {"modality": "text", "text": text, "type": "text"}
                    )
            elif isinstance(item, dict):
                out = dict(item)
                if isinstance(out.get("text"), str):
                    out["text"] = out["text"].strip()
                if "modality" not in out and out.get("type"):
                    out["modality"] = out["type"]
                if not out.get("modality"):
                    if out.get("path") or out.get("audio_bytes") or out.get("bytes"):
                        # Ambiguous file — leave as-is; Perception path may fail honestly.
                        out["modality"] = out.get("modality") or "text"
                    elif out.get("text"):
                        out["modality"] = "text"
                normalized.append(out)
            else:
                normalized.append(item)
        return normalized

    def _perceive_normalized(
        self, signals: List[Any], *, user_id: str = "default"
    ) -> List[Dict[str, Any]]:
        """Ask Perception to process normalized signals; return envelopes."""
        if not self.thalamus:
            return []
        try:
            resp = self.thalamus.send_and_wait(
                "perception",
                "sensory_data",
                {"signals": signals, "user_id": user_id},
                source="sensory_integration",
            )
        except Exception as e:
            print(f"[SensoryIntegrationLobe] Perception sensory_data failed: {e}")
            return []
        if not isinstance(resp, dict) or resp.get("status") != "success":
            # Fall back: try per-signal so one bad modality does not kill the batch.
            return self._perceive_one_by_one(signals, user_id=user_id)

        body = resp.get("content") if isinstance(resp.get("content"), dict) else resp
        fused = body.get("fused") if isinstance(body, dict) else None
        if isinstance(fused, list) and fused:
            envelopes = [dict(e) for e in fused if isinstance(e, dict)]
            # Perception.sensory_data skips mic/camera-only signals (no path/bytes).
            # Fill gaps so honesty about unavailable hardware still surfaces.
            if len(envelopes) < len(signals):
                extras = self._perceive_one_by_one(signals, user_id=user_id)
                seen_mods = {
                    str(e.get("modality") or "").lower() for e in envelopes
                }
                for env in extras:
                    mod = str(env.get("modality") or "").lower()
                    if mod and mod not in seen_mods:
                        envelopes.append(env)
                        seen_mods.add(mod)
            return envelopes
        return self._perceive_one_by_one(signals, user_id=user_id)

    def _perceive_one_by_one(
        self, signals: List[Any], *, user_id: str = "default"
    ) -> List[Dict[str, Any]]:
        envelopes: List[Dict[str, Any]] = []
        if not self.thalamus:
            return envelopes
        for sig in signals:
            try:
                if isinstance(sig, str) and sig.strip():
                    resp = self.thalamus.send_and_wait(
                        "perception",
                        "perceive_text",
                        {"text": sig, "user_id": user_id},
                        source="sensory_integration",
                    )
                elif isinstance(sig, dict):
                    modality = str(sig.get("modality") or sig.get("type") or "text").lower()
                    if modality in ("audio", "hearing", "sound"):
                        content: Dict[str, Any] = {"user_id": user_id}
                        if sig.get("path"):
                            content["path"] = sig["path"]
                        if sig.get("audio_bytes") is not None:
                            content["audio_bytes"] = sig["audio_bytes"]
                        elif sig.get("bytes") is not None:
                            content["audio_bytes"] = sig["bytes"]
                        if "path" not in content and "audio_bytes" not in content:
                            content["use_mic"] = True
                        resp = self.thalamus.send_and_wait(
                            "perception",
                            "perceive_audio",
                            content,
                            source="sensory_integration",
                        )
                    elif modality in ("vision", "visual", "image", "sight"):
                        content = {"user_id": user_id}
                        if sig.get("path"):
                            content["path"] = sig["path"]
                        if sig.get("image_bytes") is not None:
                            content["image_bytes"] = sig["image_bytes"]
                        elif sig.get("bytes") is not None:
                            content["image_bytes"] = sig["bytes"]
                        if "path" not in content and "image_bytes" not in content:
                            content["use_camera"] = True
                        resp = self.thalamus.send_and_wait(
                            "perception",
                            "perceive_vision",
                            content,
                            source="sensory_integration",
                        )
                    elif sig.get("text"):
                        resp = self.thalamus.send_and_wait(
                            "perception",
                            "perceive_text",
                            {"text": str(sig["text"]), "user_id": user_id},
                            source="sensory_integration",
                        )
                    else:
                        continue
                else:
                    continue
                if isinstance(resp, dict) and resp.get("status") == "success":
                    body = resp.get("content")
                    if isinstance(body, dict):
                        envelopes.append(dict(body))
                    else:
                        # Some handlers flatten fields onto resp
                        envelopes.append(
                            {
                                k: v
                                for k, v in resp.items()
                                if k not in ("status", "message", "_message_id")
                            }
                        )
                elif isinstance(resp, dict):
                    # Honest disabled envelope when Perception returns error.
                    content = resp.get("content")
                    if isinstance(content, dict) and content.get("modality"):
                        envelopes.append(dict(content))
                    else:
                        envelopes.append(
                            {
                                "modality": str(
                                    (sig.get("modality") if isinstance(sig, dict) else "unknown")
                                ),
                                "concepts": [],
                                "entities": [],
                                "novelty_flags": [],
                                "confidence": 0.0,
                                "raw_meta": {
                                    "available": False,
                                    "error": resp.get("message") or "perception failed",
                                },
                            }
                        )
            except Exception as e:
                envelopes.append(
                    {
                        "modality": "unknown",
                        "concepts": [],
                        "entities": [],
                        "novelty_flags": [],
                        "confidence": 0.0,
                        "raw_meta": {"available": False, "error": str(e)},
                    }
                )
        return envelopes

    def _fuse_envelopes(
        self,
        envelopes: List[Dict[str, Any]],
        *,
        user_id: str = "default",
        primary_modality: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Merge modality envelopes into one stream for Attention / Conversation."""
        usable: List[Dict[str, Any]] = []
        by_modality: Dict[str, Dict[str, Any]] = {}
        modalities: List[str] = []
        concepts: List[str] = []
        entities: List[str] = []
        novelty_flags: List[str] = []
        texts: List[str] = []
        confidences: List[float] = []
        honesty: Dict[str, Any] = {}
        attention_signals: List[Dict[str, Any]] = []

        for env in envelopes:
            if not isinstance(env, dict):
                continue
            mod = str(env.get("modality") or "unknown").lower()
            meta = dict(env.get("raw_meta") or {})
            err = meta.get("error")
            available = meta.get("available")
            # Treat as present when concepts/text exist even if confidence low.
            has_signal = bool(
                (env.get("concepts") or env.get("entities") or env.get("text"))
                and not (
                    available is False
                    and not env.get("concepts")
                    and not (isinstance(env.get("text"), str) and env["text"].strip())
                )
            )
            honesty[mod] = {
                "available": False if available is False else bool(has_signal or available),
                "confidence": env.get("confidence"),
                "error": err,
                "intake": meta.get("intake"),
            }
            if available is False and not has_signal:
                # Keep honesty only — do not invent a modality stream.
                by_modality[mod] = dict(env)
                if mod not in modalities:
                    modalities.append(mod)
                continue

            usable.append(env)
            by_modality[mod] = dict(env)
            if mod not in modalities:
                modalities.append(mod)

            for c in env.get("concepts") or []:
                cs = str(c)
                if cs and cs not in concepts:
                    concepts.append(cs)
            for e in env.get("entities") or []:
                es = str(e)
                if es and es not in entities:
                    entities.append(es)
            for f in env.get("novelty_flags") or []:
                fs = str(f)
                if fs and fs not in novelty_flags:
                    novelty_flags.append(fs)
            text = env.get("text") or env.get("normalized_text")
            if isinstance(text, str) and text.strip():
                texts.append(text.strip())
            try:
                confidences.append(float(env.get("confidence") or 0.0))
            except (TypeError, ValueError):
                confidences.append(0.0)

            # Per-modality attention competitor.
            label = text if isinstance(text, str) and text.strip() else (
                ", ".join(str(c) for c in (env.get("concepts") or [])[:6]) or mod
            )
            priority = 0.35
            if mod in ("audio", "hearing", "sound"):
                priority = 0.45
            elif mod in ("vision", "visual", "image", "sight"):
                priority = 0.40
            elif mod in ("text", "chat", "language"):
                priority = 0.55
            attention_signals.append(
                {
                    "id": f"si:{mod}",
                    "text": label[:240],
                    "source": "sensory_integration",
                    "modality": mod,
                    "priority": priority,
                    "concepts": list(env.get("concepts") or [])[:12],
                    "entities": list(env.get("entities") or [])[:8],
                    "novelty_flags": list(env.get("novelty_flags") or [])[:6],
                    "user_id": user_id,
                }
            )

        # Primary text: honor explicit primary_modality (live text turn), else
        # prefer speech transcript, then plain text, then vision note.
        primary_text = ""
        pref = str(primary_modality or "").lower()
        order = ["audio", "hearing", "text", "chat", "language", "vision", "visual", "image"]
        if pref:
            # Put the live turn's modality first so absorb does not overwrite
            # fresh user text with a stale audio/vision caption.
            order = [pref] + [m for m in order if m != pref]
        for preferred in order:
            env = by_modality.get(preferred)
            if not env:
                continue
            t = env.get("text") or env.get("normalized_text")
            if isinstance(t, str) and t.strip():
                primary_text = t.strip()
                break
        if not primary_text and texts:
            primary_text = texts[0]

        active = [m for m in modalities if honesty.get(m, {}).get("available")]
        if len(active) > 1:
            stream_modality = "multimodal"
        elif active:
            stream_modality = active[0]
        elif modalities:
            stream_modality = modalities[0]
        else:
            stream_modality = "empty"

        confidence = max(confidences) if confidences else 0.0

        stream: Dict[str, Any] = {
            "modality": stream_modality,
            "modalities": list(modalities),
            "modalities_active": list(active),
            "text": primary_text,
            "normalized_text": primary_text,
            "concepts": concepts,
            "entities": entities,
            "novelty_flags": novelty_flags,
            "confidence": confidence,
            "by_modality": by_modality,
            "attention_signals": attention_signals,
            "raw_meta": {
                "source": "sensory_integration",
                "envelope_count": len(envelopes),
                "usable_count": len(usable),
                "honesty": honesty,
                "user_id": user_id,
                "fused_at": time.time(),
            },
        }
        if primary_text:
            stream["words"] = list(concepts)
        return stream

    def _update_shared_context(
        self, stream: Dict[str, Any], *, user_id: str = "default"
    ) -> None:
        uid = self._uid(user_id)
        now = time.time()
        ctx = self._shared_for(uid)
        # Start from prior by_modality, prune stale on *their* timestamps, then merge.
        by_mod = self._prune_stale_modalities(ctx.get("by_modality") or {}, now=now)
        for m, env in (stream.get("by_modality") or {}).items():
            if not isinstance(env, dict):
                continue
            # Fresh observation from this stream: stamp now unless already stamped
            # (carried-forward prior keeps its observed_at).
            stamped = self._stamp_modality(dict(env), now=now)
            # If prior existed and stream env lacks its own observed_at originally,
            # _stamp_modality may have set now — but absorb copies prior with stamp.
            # Prefer explicit observed_at on env when > 0.
            prior_ts = self._modality_observed_at(env)
            if prior_ts > 0.0:
                stamped["observed_at"] = prior_ts
                stamped["updated_at"] = prior_ts
            by_mod[str(m)] = stamped
        by_mod = self._prune_stale_modalities(by_mod, now=now)

        mods = list(by_mod.keys())
        concepts = list(ctx.get("concepts") or [])
        for c in stream.get("concepts") or []:
            if c not in concepts:
                concepts.append(c)
        concepts = concepts[-64:]
        entities = list(ctx.get("entities") or [])
        for e in stream.get("entities") or []:
            if e not in entities:
                entities.append(e)
        entities = entities[-32:]
        flags = list(ctx.get("novelty_flags") or [])
        for f in stream.get("novelty_flags") or []:
            if f not in flags:
                flags.append(f)
        flags = flags[-24:]
        texts = list(ctx.get("recent_texts") or [])
        t = stream.get("text")
        if isinstance(t, str) and t.strip():
            texts.append(t.strip()[:240])
        texts = texts[-8:]
        updated = {
            "modalities_seen": mods,
            "concepts": concepts,
            "entities": entities,
            "novelty_flags": flags,
            "recent_texts": texts,
            "by_modality": by_mod,
            "updated_at": now,  # bookkeeping only; expiry uses per-modality observed_at
            "last_modality": stream.get("modality"),
            "attention_focus": stream.get("attention_focus"),
            "user_id": uid,
        }
        self._shared_by_user[uid] = updated
        if uid == "default":
            self.shared_context = updated

    def _route_to_attention(
        self, stream: Dict[str, Any], *, user_id: str = "default"
    ) -> Dict[str, Any]:
        if not self.thalamus:
            return {}
        signals = list(stream.get("attention_signals") or [])
        # Ambient competitor so ranking is real when only one modality arrives.
        signals.append(
            {
                "id": "ambient_noise",
                "text": "ambient room tone",
                "source": "ambient",
                "modality": "text",
                "priority": 0.0,
                "user_id": user_id,
            }
        )
        try:
            resp = self.thalamus.send_and_wait(
                "attention",
                "evaluate",
                {"signals": signals, "user_id": user_id},
                source="sensory_integration",
            )
        except Exception as e:
            print(f"[SensoryIntegrationLobe] Attention route failed: {e}")
            return {}
        if not isinstance(resp, dict) or resp.get("status") != "success":
            return {}
        body = resp.get("content") if isinstance(resp.get("content"), dict) else {}
        if not body:
            body = {
                k: v
                for k, v in resp.items()
                if k not in ("status", "message", "_message_id")
            }
        focus = body.get("focus")
        if focus:
            try:
                self.thalamus.send_and_wait(
                    "attention",
                    "route_focus",
                    {},
                    source="sensory_integration",
                )
            except Exception:
                pass
        return body if isinstance(body, dict) else {}
