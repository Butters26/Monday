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
    def __init__(self, thalamus=None):
        self.thalamus = thalamus
        self.sensory_buffer: List[Any] = []
        self.normalized_signals: List[Any] = []
        self.modality_envelopes: List[Dict[str, Any]] = []
        self.unified_stream: Optional[Dict[str, Any]] = None
        self.shared_context: Dict[str, Any] = {
            "modalities_seen": [],
            "concepts": [],
            "entities": [],
            "novelty_flags": [],
            "recent_texts": [],
            "by_modality": {},
            "updated_at": None,
        }
        self.attention_payload: Dict[str, Any] = {}

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
        self.unified_stream = stream
        self._update_shared_context(stream)

        if route_attention and self.thalamus and stream.get("attention_signals"):
            self.attention_payload = self._route_to_attention(
                stream, user_id=user_id
            )
            if self.attention_payload:
                stream = dict(stream)
                stream["attention_focus"] = self.attention_payload.get("focus")
                stream["attention_priority"] = [
                    str(r.get("id") or "")
                    for r in (self.attention_payload.get("ranked") or [])
                    if isinstance(r, dict)
                ][:8]
                self.unified_stream = stream
                self._update_shared_context(stream)

        return stream

    def absorb_envelope(
        self,
        envelope: Dict[str, Any],
        *,
        user_id: str = "default",
        route_attention: bool = False,
    ) -> Dict[str, Any]:
        """Fold a precomputed Perception envelope into the shared stream.

        Used by the live text path so SI stays warm without re-perceiving.
        Merges with any recent multi-modal context still in shared_context.
        """
        if not isinstance(envelope, dict) or not envelope:
            return dict(self.unified_stream or {})

        envelopes: List[Dict[str, Any]] = [dict(envelope)]
        # Bring forward other modalities still in shared context (not same modality).
        primary = str(envelope.get("modality") or "text").lower()
        prior_by = dict(self.shared_context.get("by_modality") or {})
        for mod, prior_env in prior_by.items():
            if not isinstance(prior_env, dict):
                continue
            if str(mod).lower() == primary:
                continue
            # Keep recent cross-modal context for a short window.
            age = time.time() - float(self.shared_context.get("updated_at") or 0.0)
            if age <= 120.0:
                envelopes.append(dict(prior_env))

        return self.integrate_inputs(
            [],
            user_id=user_id,
            route_attention=route_attention,
            precomputed=envelopes,
            primary_modality=primary,
        )

    def get_unified_stream(self) -> Dict[str, Any]:
        return dict(self.unified_stream or {})

    def get_shared_context(self) -> Dict[str, Any]:
        return dict(self.shared_context)

    def reset(self) -> None:
        self.sensory_buffer.clear()
        self.normalized_signals.clear()
        self.modality_envelopes.clear()
        self.unified_stream = None
        self.attention_payload = {}
        self.shared_context = {
            "modalities_seen": [],
            "concepts": [],
            "entities": [],
            "novelty_flags": [],
            "recent_texts": [],
            "by_modality": {},
            "updated_at": None,
        }

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
            return {
                "status": "success",
                "content": self.get_unified_stream(),
            }

        if msg_type in ("get_context", "get_shared_context"):
            return {
                "status": "success",
                "content": self.get_shared_context(),
            }

        if msg_type == "reset":
            self.reset()
            return {"status": "success", "message": "SensoryIntegrationLobe reset"}

        if msg_type == "get_status":
            stream = self.unified_stream or {}
            return {
                "status": "success",
                "content": {
                    "buffer_size": len(self.sensory_buffer),
                    "last_normalized": len(self.normalized_signals),
                    "envelope_count": len(self.modality_envelopes),
                    "modalities": list(stream.get("modalities") or []),
                    "has_unified_stream": bool(self.unified_stream),
                    "shared_modalities": list(
                        self.shared_context.get("modalities_seen") or []
                    ),
                    "attention_focus": (self.attention_payload or {}).get("focus"),
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

    def _update_shared_context(self, stream: Dict[str, Any]) -> None:
        ctx = self.shared_context
        mods = list(ctx.get("modalities_seen") or [])
        for m in stream.get("modalities") or []:
            if m not in mods:
                mods.append(m)
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
        by_mod = dict(ctx.get("by_modality") or {})
        for m, env in (stream.get("by_modality") or {}).items():
            if isinstance(env, dict):
                by_mod[m] = dict(env)
        self.shared_context = {
            "modalities_seen": mods,
            "concepts": concepts,
            "entities": entities,
            "novelty_flags": flags,
            "recent_texts": texts,
            "by_modality": by_mod,
            "updated_at": time.time(),
            "last_modality": stream.get("modality"),
            "attention_focus": stream.get("attention_focus"),
        }

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
