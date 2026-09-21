#!/usr/bin/env python3
"""
Voice Lobe - Speech Synthesis and Audio Output

Live path: synthesize / prepare a voice envelope from text that Output
(or Thalamus) asks to speak. Not a second Language — does not invent
replies. Not Motor — speech output path only.

Honest statuses: synthesized | play_unavailable | played | no_tts_backend
| empty_text. Never claims audio played without evidence.
"""

from __future__ import annotations

import json
import os
import platform
import random
import socket
import struct
import subprocess
import time
import uuid
import wave
from dataclasses import dataclass
from typing import Any, Dict, Optional

try:
    import numpy as np
    _NUMPY_OK = True
except Exception:  # pragma: no cover
    np = None  # type: ignore
    _NUMPY_OK = False


def _recv_all(conn, n, timeout=5.0):
    """Read exactly n bytes or raise IOError on EOF/timeout"""
    conn.settimeout(timeout)
    data = b""
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            raise IOError("Unexpected EOF while reading")
        data += chunk
    return data


# ============================================================================
# VOICE PROFILES
# ============================================================================


@dataclass
class VoiceProfile:
    """Voice characteristics"""

    name: str
    pitch_base: float
    pitch_range: float
    formant_shift: float = 1.0
    speed: float = 1.0
    breathiness: float = 0.1
    nasality: float = 0.05
    warmth: float = 0.5
    clarity: float = 0.7
    resonance: float = 1.0
    vibrato_depth: float = 0.02
    vibrato_rate: float = 5.0


VOICE_PROFILES = {
    "monday": VoiceProfile(
        name="Monday",
        pitch_base=205,
        pitch_range=80,
        formant_shift=1.02,
        speed=0.98,
        breathiness=0.10,
        nasality=0.04,
        warmth=0.85,
        clarity=0.85,
        resonance=1.05,
        vibrato_depth=0.02,
        vibrato_rate=5.2,
    ),
    "shadowheart": VoiceProfile(
        name="Shadowheart",
        pitch_base=308.2,
        pitch_range=28.8,
        formant_shift=1.90,
        speed=0.78,
        breathiness=0.581,
        nasality=0.05,
        warmth=1.10,
        clarity=0.42,
        resonance=1.0,
        vibrato_depth=0.02,
        vibrato_rate=4.5,
    ),
    "mealle": VoiceProfile(
        name="Mealle",
        pitch_base=220,
        pitch_range=95,
        formant_shift=1.05,
        speed=1.05,
        breathiness=0.15,
        nasality=0.08,
        warmth=0.85,
        clarity=0.75,
        resonance=0.9,
        vibrato_depth=0.025,
        vibrato_rate=5.5,
    ),
}


# ============================================================================
# PHONEME DATABASE
# ============================================================================

PHONEME_FREQUENCIES = {
    "aa": {"f1": 700, "f2": 1220, "f3": 2600},
    "ae": {"f1": 660, "f2": 1770, "f3": 2540},
    "ah": {"f1": 640, "f2": 1190, "f3": 2540},
    "ao": {"f1": 570, "f2": 840, "f3": 2250},
    "aw": {"f1": 590, "f2": 920, "f3": 2250},
    "ay": {"f1": 650, "f2": 1780, "f3": 2540},
    "eh": {"f1": 530, "f2": 1840, "f3": 2480},
    "er": {"f1": 490, "f2": 1350, "f3": 1690},
    "ey": {"f1": 500, "f2": 1900, "f3": 2550},
    "ih": {"f1": 400, "f2": 1920, "f3": 2560},
    "iy": {"f1": 270, "f2": 2360, "f3": 3100},
    "oh": {"f1": 570, "f2": 840, "f3": 2250},
    "oy": {"f1": 620, "f2": 1100, "f3": 2250},
    "uh": {"f1": 370, "f2": 990, "f3": 2250},
    "uw": {"f1": 300, "f2": 870, "f3": 2250},
}

TEXT_TO_PHONEMES = {
    "hello": ["h", "eh", "l", "oh"],
    "hi": ["h", "ay"],
    "monday": ["m", "ah", "n", "d", "ay"],
    "matthew": ["m", "ae", "th", "uw"],
    "i": ["ay"],
    "am": ["ae", "m"],
    "the": ["th", "ah"],
    "think": ["th", "ih", "ng", "k"],
    "understand": ["ah", "n", "d", "er", "s", "t", "ae", "n", "d"],
    "you": ["y", "uw"],
    "what": ["w", "ah", "t"],
    "why": ["w", "ay"],
}


# ============================================================================
# VOICE SYNTHESIZER
# ============================================================================


class VoiceSynthesizer:
    """Synthesize speech from text (formant stub → real WAV file)."""

    def __init__(self, voice_profile: VoiceProfile, sample_rate: int = 22050):
        self.voice = voice_profile
        self.sample_rate = sample_rate
        self.output_dir = "monday_audio"

        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def text_to_phonemes(self, text: str) -> list:
        text = text.lower()
        words = text.split()
        phonemes = []

        for word in words:
            word = "".join(c for c in word if c.isalpha())

            if word in TEXT_TO_PHONEMES:
                phonemes.extend(TEXT_TO_PHONEMES[word])
            else:
                phonemes.extend(self._simple_phonemize(word))

            phonemes.append("sil")

        return phonemes

    def _simple_phonemize(self, word: str) -> list:
        phonemes = []
        vowels = "aeiou"
        for char in word:
            if char in vowels:
                phonemes.append("ah")
            else:
                phonemes.append(char)
        return phonemes

    def generate_sine_wave(
        self, frequency: float, duration_ms: float, amplitude: float = 1.0
    ):
        duration_s = duration_ms / 1000.0
        t = np.linspace(0, duration_s, int(self.sample_rate * duration_s))
        return amplitude * np.sin(2 * np.pi * frequency * t)

    def apply_envelope(
        self, wave_arr, attack_ms: float = 10, decay_ms: float = 50
    ):
        n_samples = len(wave_arr)
        n_attack = int(self.sample_rate * attack_ms / 1000)
        n_decay = int(self.sample_rate * decay_ms / 1000)

        envelope = np.ones(n_samples)

        if n_attack > 0:
            envelope[:n_attack] = np.linspace(0, 1, n_attack)
        if n_decay > 0:
            envelope[-n_decay:] = np.linspace(1, 0, n_decay)

        return wave_arr * envelope

    def generate_formant_vowel(self, phoneme: str, duration_ms: float):
        if phoneme not in PHONEME_FREQUENCIES:
            return self.generate_sine_wave(200, duration_ms)

        freq_data = PHONEME_FREQUENCIES[phoneme]
        f1 = freq_data.get("f1", 500) * self.voice.formant_shift
        f2 = freq_data.get("f2", 1500) * self.voice.formant_shift
        f3 = freq_data.get("f3", 2500) * self.voice.formant_shift

        duration_s = duration_ms / 1000.0
        t = np.linspace(0, duration_s, int(self.sample_rate * duration_s))

        f1_amp = 0.5 + (self.voice.warmth * 0.2)
        f2_amp = 0.3 + (self.voice.clarity * 0.15)
        f3_amp = 0.2

        wave_arr = (
            f1_amp * np.sin(2 * np.pi * f1 * t)
            + f2_amp * np.sin(2 * np.pi * f2 * t)
            + f3_amp * np.sin(2 * np.pi * f3 * t)
        )

        noise = np.random.randn(len(wave_arr)) * self.voice.breathiness * 0.1
        wave_arr = wave_arr + noise
        wave_arr = wave_arr * self.voice.resonance
        wave_arr = wave_arr / (np.max(np.abs(wave_arr)) + 1e-6)

        return self.apply_envelope(wave_arr, attack_ms=5, decay_ms=30)

    def generate_consonant(self, phoneme: str):
        if phoneme not in PHONEME_FREQUENCIES:
            return self.generate_sine_wave(200, 50)

        freq_data = PHONEME_FREQUENCIES[phoneme]
        duration = freq_data.get("duration", 60) / self.voice.speed

        if phoneme in ["s", "sh", "f", "th", "z", "zh"]:
            duration_s = duration / 1000.0
            noise = np.random.randn(int(self.sample_rate * duration_s)) * 0.3
            return self.apply_envelope(noise, attack_ms=2, decay_ms=10)
        frequency = self.voice.pitch_base * 0.8
        wave_arr = self.generate_sine_wave(frequency, duration)
        return self.apply_envelope(wave_arr, attack_ms=2, decay_ms=5)

    def synthesize_phoneme(self, phoneme: str):
        if phoneme == "sil":
            return np.zeros(int(self.sample_rate * 0.1))

        if phoneme in [
            "aa",
            "ae",
            "ah",
            "ao",
            "aw",
            "ay",
            "eh",
            "er",
            "ey",
            "ih",
            "iy",
            "oh",
            "oy",
            "uh",
            "uw",
        ]:
            return self.generate_formant_vowel(phoneme, 100)
        return self.generate_consonant(phoneme)

    def synthesize_speech(
        self, text: str, emotion: str = "neutral", intensity: float = 0.5
    ):
        # Work on a copy of pitch/speed so emotion does not permanently mutate profile.
        pitch = self.voice.pitch_base
        speed = self.voice.speed
        if emotion == "excited":
            pitch *= 1.2
            speed *= 1.1
            intensity = 1.0
        elif emotion == "sad":
            pitch *= 0.8
            speed *= 0.9

        saved_pitch, saved_speed = self.voice.pitch_base, self.voice.speed
        self.voice.pitch_base = pitch
        self.voice.speed = speed
        try:
            phonemes = self.text_to_phonemes(text)
            audio = [self.synthesize_phoneme(p) for p in phonemes]
            if audio:
                speech = np.concatenate(audio)
            else:
                speech = np.array([])
            speech = speech * intensity * 0.8
            return speech
        finally:
            self.voice.pitch_base = saved_pitch
            self.voice.speed = saved_speed

    def save_to_file(self, audio, filename: str = None) -> str:
        if filename is None:
            filename = f"{self.output_dir}/monday_{int(random.random() * 10000)}.wav"

        if not filename.startswith(self.output_dir):
            filename = os.path.join(self.output_dir, filename)

        audio = np.clip(audio, -1, 1)
        audio_int16 = (audio * 32767).astype(np.int16)

        with wave.open(filename, "w") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(audio_int16.tobytes())

        return filename

    def speak(self, text: str, emotion: str = "neutral", intensity: float = 0.5) -> str:
        audio = self.synthesize_speech(text, emotion, intensity)
        return self.save_to_file(audio)


# ============================================================================
# VOICE LOBE (live path)
# ============================================================================


class VoiceLobe:
    """Speech synthesis / voice profile / audio envelope for the live path."""

    def __init__(
        self,
        thalamus: Any = None,
        voice_name: str = "monday",
        socket_path: str = "/tmp/voice.sock",
        auto_play: bool = False,
    ) -> None:
        self.thalamus = thalamus
        self.socket_path = socket_path
        self.running = True
        self.user = "Butters26"

        self.voice_profile = VOICE_PROFILES.get(voice_name, VOICE_PROFILES["monday"])
        self.synthesizer: Optional[VoiceSynthesizer] = None
        self._synth_backend = "none"
        if _NUMPY_OK:
            try:
                self.synthesizer = VoiceSynthesizer(self.voice_profile)
                self._synth_backend = "formant_numpy"
            except Exception:
                self.synthesizer = None
                self._synth_backend = "none"

        self.voice_config = {
            "enabled": True,
            "voice_name": voice_name,
            # Live path default: do not auto-play (box may lack paplay).
            "auto_play": bool(auto_play),
        }
        # Per-user last voice envelope.
        self._last_by_user: Dict[str, Dict[str, Any]] = {}
        self.last_voice: Optional[Dict[str, Any]] = None
        self._speak_count = 0

    @staticmethod
    def _uid(user_id: Optional[str]) -> str:
        return (user_id or "default").strip() or "default"

    def set_voice(self, voice_name: str) -> bool:
        if voice_name not in VOICE_PROFILES:
            return False
        self.voice_profile = VOICE_PROFILES[voice_name]
        self.voice_config["voice_name"] = voice_name
        if _NUMPY_OK:
            try:
                self.synthesizer = VoiceSynthesizer(self.voice_profile)
                self._synth_backend = "formant_numpy"
            except Exception:
                self.synthesizer = None
                self._synth_backend = "none"
        return True

    def _play_audio(self, filename: str) -> Dict[str, Any]:
        """Attempt playback; return honest {played, play_backend, error?}."""
        system = platform.system()
        try:
            if system == "Darwin":
                subprocess.Popen(["afplay", filename])
                return {"played": True, "play_backend": "afplay"}
            if system == "Linux":
                # Prefer paplay; fall back to aplay. Do not claim success if spawn fails.
                for cmd in ("paplay", "aplay"):
                    from shutil import which

                    if which(cmd):
                        subprocess.Popen([cmd, filename])
                        return {"played": True, "play_backend": cmd}
                return {
                    "played": False,
                    "play_backend": None,
                    "error": "no_play_command",
                }
            if system == "Windows":
                os.startfile(filename)  # type: ignore[attr-defined]
                return {"played": True, "play_backend": "startfile"}
        except Exception as exc:
            return {"played": False, "play_backend": None, "error": str(exc)}
        return {"played": False, "play_backend": None, "error": "unsupported_os"}

    def speak_for_output(
        self,
        text: str,
        *,
        user_id: str = "default",
        emotion: str = "neutral",
        intensity: float = 0.5,
        voice_prosody: Optional[Dict[str, Any]] = None,
        try_play: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Synthesize reply text into a voice envelope; surface to Output.

        Does not invent wording. Honest status — never claims played without
        a successful play backend.
        """
        uid = self._uid(user_id)
        text = (text or "").strip()
        envelope: Dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "text": text,
            "user_id": uid,
            "voice_profile": self.voice_config.get("voice_name", "monday"),
            "synth_backend": self._synth_backend,
            "status": "empty_text",
            "audio_file": None,
            "played": False,
            "play_backend": None,
            "emotion": emotion or "neutral",
            "intensity": float(intensity if intensity is not None else 0.5),
            "voice_prosody": dict(voice_prosody or {}),
            "timestamp": time.time(),
        }
        if not text:
            self._store(uid, envelope)
            self._route_voice_output(envelope)
            return dict(envelope)

        if self.synthesizer is None or self._synth_backend == "none":
            envelope["status"] = "no_tts_backend"
            self._store(uid, envelope)
            self._route_voice_output(envelope)
            return dict(envelope)

        try:
            filename = self.synthesizer.speak(
                text, emotion=envelope["emotion"], intensity=envelope["intensity"]
            )
            envelope["audio_file"] = filename
            envelope["status"] = "synthesized"
            self._speak_count += 1
        except Exception as exc:
            envelope["status"] = "no_tts_backend"
            envelope["error"] = str(exc)
            self._store(uid, envelope)
            self._route_voice_output(envelope)
            return dict(envelope)

        do_play = (
            self.voice_config.get("auto_play", False)
            if try_play is None
            else bool(try_play)
        )
        if do_play and envelope.get("audio_file"):
            play_info = self._play_audio(str(envelope["audio_file"]))
            envelope["played"] = bool(play_info.get("played"))
            envelope["play_backend"] = play_info.get("play_backend")
            if play_info.get("error"):
                envelope["play_error"] = play_info["error"]
            if envelope["played"]:
                envelope["status"] = "played"
            else:
                envelope["status"] = "play_unavailable"
        elif envelope.get("audio_file"):
            # Synthesized but not asked to play — still honest.
            envelope["status"] = "synthesized"
            envelope["played"] = False

        self._store(uid, envelope)
        self._route_voice_output(envelope)
        return dict(envelope)

    def _store(self, user_id: str, envelope: Dict[str, Any]) -> None:
        self._last_by_user[user_id] = dict(envelope)
        self.last_voice = dict(envelope)

    def _route_voice_output(self, envelope: Dict[str, Any]) -> None:
        th = self.thalamus
        if th is None:
            return
        try:
            th.send_message(
                "output",
                "voice_output",
                {"voice": envelope},
                source="voice",
            )
        except Exception:
            pass

    def get_status(self, user_id: str = "default") -> Dict[str, Any]:
        uid = self._uid(user_id)
        # Per-user only — never fall back to global last_voice (isolates users).
        last = self._last_by_user.get(uid)
        return {
            "voice_enabled": bool(self.voice_config.get("enabled")),
            "current_voice": self.voice_config.get("voice_name"),
            "auto_play": bool(self.voice_config.get("auto_play")),
            "synth_backend": self._synth_backend,
            "speak_count": self._speak_count,
            "last_voice": dict(last) if last else None,
            "users": sorted(self._last_by_user.keys()),
        }

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Thalamus live-path handler (no socket)."""
        msg_type = message.get("type")
        if "content" in message and isinstance(message.get("content"), dict):
            content = message["content"]
        else:
            content = {
                k: v
                for k, v in message.items()
                if k not in ("type", "_message_id", "message_id", "source")
            }

        if msg_type == "health":
            return {"status": "success", "healthy": True}

        if msg_type in ("speak_for_output", "speak", "synthesize", "play"):
            text = str(
                content.get("text")
                or content.get("reply")
                or message.get("text")
                or ""
            )
            try_play = None
            if msg_type == "play":
                try_play = True
            elif msg_type == "synthesize":
                try_play = False
            elif "try_play" in content:
                try_play = bool(content.get("try_play"))
            env = self.speak_for_output(
                text,
                user_id=str(content.get("user_id") or "default"),
                emotion=str(content.get("emotion") or "neutral"),
                intensity=float(content.get("intensity", 0.5) or 0.5),
                voice_prosody=content.get("voice_prosody")
                if isinstance(content.get("voice_prosody"), dict)
                else {},
                try_play=try_play,
            )
            return {
                "status": "success",
                "content": {"voice": env},
                "voice": env,
                "audio_file": env.get("audio_file"),
                "played": env.get("played"),
            }

        if msg_type == "set_voice":
            voice_name = str(
                content.get("voice_name") or content.get("profile") or "monday"
            )
            ok = self.set_voice(voice_name)
            return {
                "status": "success" if ok else "error",
                "voice_changed": ok,
                "current_voice": self.voice_config["voice_name"],
                "content": {
                    "voice_changed": ok,
                    "current_voice": self.voice_config["voice_name"],
                },
            }

        if msg_type in ("get_status", "status"):
            body = self.get_status(str(content.get("user_id") or "default"))
            return {"status": "success", "content": body, **body}

        if msg_type == "reset":
            uid = content.get("user_id")
            if uid is None:
                self._last_by_user.clear()
                self.last_voice = None
                self._speak_count = 0
            else:
                self._last_by_user.pop(self._uid(str(uid)), None)
            return {"status": "success", "message": "VoiceLobe reset"}

        return {"status": "error", "message": f"Unknown type: {msg_type}"}

    # ------------------------------------------------------------------
    # Legacy socket server (NOT used on live prompted path)
    # ------------------------------------------------------------------

    def handle_request(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Legacy socket API → process_message."""
        if "type" not in message and "content" not in message:
            message = dict(message)
        return self.process_message(message)

    def synthesize_and_play(
        self, text: str, emotion: str = "neutral", intensity: float = 0.5
    ) -> bool:
        env = self.speak_for_output(
            text, emotion=emotion, intensity=intensity, try_play=True
        )
        return bool(env.get("audio_file"))

    def start(self):
        """Legacy Unix-socket server — not started by create_core_systems."""
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(self.socket_path)
        sock.listen(5)
        sock.settimeout(1.0)

        print(f"🎤 Voice Lobe: Online at {self.socket_path}")
        print(f"   Voice: {self.voice_config['voice_name']}")
        print(f"   Auto-play: {self.voice_config['auto_play']}\n")

        while self.running:
            try:
                try:
                    conn, _ = sock.accept()
                except socket.timeout:
                    continue

                try:
                    conn.settimeout(5)

                    length_data = _recv_all(conn, 4, timeout=5)
                    msg_length = struct.unpack("!I", length_data)[0]

                    if msg_length <= 0 or msg_length > 10_000_000:
                        raise ValueError(f"Invalid length: {msg_length}")

                    data = _recv_all(conn, msg_length, timeout=5)
                    message = json.loads(data.decode("utf-8"))

                    result = self.handle_request(message)

                    response_data = json.dumps(result).encode("utf-8")
                    response_length = struct.pack("!I", len(response_data))
                    conn.sendall(response_length + response_data)

                except Exception as e:
                    try:
                        err = {"status": "error", "message": str(e)}
                        resp = json.dumps(err).encode("utf-8")
                        conn.sendall(struct.pack("!I", len(resp)) + resp)
                    except Exception:
                        pass
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass

            except Exception as e:
                print(f"❌ Error: {e}")

    def shutdown(self):
        self.running = False
        if os.path.exists(self.socket_path):
            try:
                os.remove(self.socket_path)
            except Exception:
                pass


if __name__ == "__main__":
    lobe = VoiceLobe(auto_play=True)
    try:
        lobe.start()
    except KeyboardInterrupt:
        print("\n🛑 Voice lobe shutting down...")
        lobe.shutdown()
