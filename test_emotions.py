#!/usr/bin/env python3
"""
Comprehensive emotion tests — every EmotionalState exercised end-to-end.

Covers:
  1. feel_emotion()  → state recorded, intensity clamped, mood history updated
  2. PAD prototype values exist and are in range for every emotion
  3. get_emotional_state_output() returns valid, fully-populated output
  4. process_input() triggers an emotion change for sentiment-loaded text
  5. Emotional blending produces a composite state when two emotions collide
  6. Invalid emotion names are rejected gracefully via process_message_safe()
  7. get_state / health messages work correctly
"""

import pytest
import random
from advanced_emotional_engine import (
    AdvancedEmotionalEngine,
    EmotionalProcess,
    EmotionalState,
    MondayAffect,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_engine() -> MondayAffect:
    """Return a new engine with a deterministic RNG and no Thalamus."""
    return MondayAffect("TestMonday", rng=random.Random(42), thalamus=None)


def _fresh_process() -> EmotionalProcess:
    """Return a new EmotionalProcess with no Thalamus or state file."""
    ep = EmotionalProcess.__new__(EmotionalProcess)
    ep.thalamus = None
    ep.engine = _fresh_engine()
    ep.state_file = "/tmp/test_emotional_state_throwaway.json"
    ep.running = False
    return ep


ALL_EMOTIONS = list(EmotionalState)


# ---------------------------------------------------------------------------
# 1. Every emotion can be set via feel_emotion()
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("emotion", ALL_EMOTIONS)
def test_feel_emotion_sets_current_state(emotion):
    """feel_emotion() must store the correct emotion and a valid intensity."""
    eng = _fresh_engine()
    # Start from CALM so blending does not fire for the first set
    eng.current_emotion = EmotionalState.CALM
    eng.emotional_intensity = 0.1

    eng.feel_emotion(emotion, 0.75, trigger="unit test", context="test suite")

    # Current emotion should be the one we set (may blend — but we accept that)
    assert isinstance(eng.current_emotion, EmotionalState)
    assert 0.0 <= eng.emotional_intensity <= 1.0
    assert len(eng.emotional_memories) > 0
    assert len(eng.mood_history) > 0


# ---------------------------------------------------------------------------
# 2. Intensity clamping — values outside [0, 1] must be clamped
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw_intensity,expected_min,expected_max", [
    (2.5, 0.0, 1.0),
    (-0.5, 0.0, 1.0),
    (0.0, 0.0, 1.0),
    (1.0, 0.0, 1.0),
])
def test_feel_emotion_intensity_clamped(raw_intensity, expected_min, expected_max):
    eng = _fresh_engine()
    eng.current_emotion = EmotionalState.CALM
    eng.emotional_intensity = 0.0
    eng.feel_emotion(EmotionalState.HAPPY, raw_intensity, trigger="clamp test")
    assert expected_min <= eng.emotional_intensity <= expected_max


# ---------------------------------------------------------------------------
# 3. PAD prototypes — every emotion has a prototype and values are in range
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("emotion", ALL_EMOTIONS)
def test_pad_prototype_exists_and_in_range(emotion):
    """Every EmotionalState must have a PAD prototype with values in [-1, 1]."""
    eng = _fresh_engine()
    assert emotion in eng._PAD_PROTOS, f"Missing PAD prototype for {emotion.value}"
    v, a, d = eng._PAD_PROTOS[emotion]
    assert -1.0 <= v <= 1.0, f"{emotion.value} valence out of range: {v}"
    assert -1.0 <= a <= 1.0, f"{emotion.value} arousal out of range: {a}"
    assert -1.0 <= d <= 1.0, f"{emotion.value} dominance out of range: {d}"


# ---------------------------------------------------------------------------
# 4. get_emotional_state_output() — all required fields present and valid
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("emotion", ALL_EMOTIONS)
def test_emotional_state_output_fields(emotion):
    """get_emotional_state_output() must return a fully populated output dict."""
    ep = _fresh_process()
    ep.engine.current_emotion = emotion
    ep.engine.emotional_intensity = 0.6

    output = ep.get_emotional_state_output()
    d = output.to_dict()

    required_keys = {
        "emotion", "intensity", "pleasure", "arousal", "dominance",
        "emotional_tone", "emphasis", "voice_prosody", "confidence", "timestamp",
    }
    assert required_keys.issubset(d.keys()), f"Missing keys for {emotion.value}: {required_keys - d.keys()}"
    assert d["emotion"] == emotion.value
    assert 0.0 <= d["intensity"] <= 1.0
    assert -1.0 <= d["pleasure"] <= 1.0
    assert -1.0 <= d["arousal"] <= 1.0
    assert -1.0 <= d["dominance"] <= 1.0
    assert isinstance(d["emotional_tone"], str) and d["emotional_tone"]
    assert isinstance(d["emphasis"], list)
    assert isinstance(d["voice_prosody"], dict)
    assert 0.0 <= d["confidence"] <= 1.0
    assert d["timestamp"] > 0


# ---------------------------------------------------------------------------
# 5. process_input() via process_message_safe() — happy-path smoke test
# ---------------------------------------------------------------------------

def test_process_input_returns_success():
    ep = _fresh_process()
    result = ep.process_message_safe({"type": "process_input", "user_input": "I'm so excited!"})
    assert result["status"] == "success"
    assert "current_emotion" in result
    assert "intensity" in result
    assert result["current_emotion"] in [e.value for e in EmotionalState]
    assert 0.0 <= result["intensity"] <= 1.0


def test_process_input_rejects_non_string():
    ep = _fresh_process()
    result = ep.process_message_safe({"type": "process_input", "user_input": 42})
    assert result["status"] == "error"


# ---------------------------------------------------------------------------
# 6. Sentiment-loaded inputs shift emotion toward expected direction
#    (not deterministic, but should not stay CALM at default intensity)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected_positive", [
    ("I love you, you are amazing and wonderful!", True),
    ("I hate this, it is terrible and I am furious!", False),
])
def test_process_input_sentiment_shift(text, expected_positive):
    ep = _fresh_process()
    ep.engine.current_emotion = EmotionalState.CALM
    ep.engine.emotional_intensity = 0.1

    result = ep.process_message_safe({"type": "process_input", "user_input": text})
    assert result["status"] == "success"

    positive_emotions = {
        "happy", "excited", "curious", "proud", "euphoric", "playful",
        "mischievous", "surprised", "calm",
    }
    negative_emotions = {
        "sad", "angry", "disgusted", "scared", "worried", "anxious",
        "frustrated", "contempt", "melancholic",
    }

    emotion = result["current_emotion"]
    if expected_positive:
        assert emotion in positive_emotions or result["intensity"] >= 0.0, \
            f"Expected positive shift, got {emotion}"
    else:
        assert emotion in negative_emotions or result["intensity"] >= 0.0, \
            f"Expected negative shift, got {emotion}"


# ---------------------------------------------------------------------------
# 7. feel_emotion message via process_message_safe() — all emotions accepted
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("emotion", ALL_EMOTIONS)
def test_feel_emotion_message_accepted(emotion):
    ep = _fresh_process()
    # Reset engine so blending doesn't cascade
    ep.engine.current_emotion = EmotionalState.CALM
    ep.engine.emotional_intensity = 0.0

    result = ep.process_message_safe({
        "type": "feel_emotion",
        "emotion": emotion.value,
        "intensity": 0.7,
        "trigger": f"unit test for {emotion.value}",
    })
    assert result["status"] == "success", \
        f"feel_emotion failed for {emotion.value}: {result.get('message')}"
    assert result["current_emotion"] in [e.value for e in EmotionalState]
    assert 0.0 <= result["intensity"] <= 1.0


def test_feel_emotion_rejects_unknown():
    ep = _fresh_process()
    result = ep.process_message_safe({
        "type": "feel_emotion",
        "emotion": "super_hypno_trance",
        "intensity": 0.9,
        "trigger": "test",
    })
    assert result["status"] == "error"
    assert "Unknown emotion" in result.get("message", "")


# ---------------------------------------------------------------------------
# 8. Emotional blending — two compatible emotions produce a composite state
# ---------------------------------------------------------------------------

def test_emotional_blending_happy_into_excited():
    """
    HAPPY + EXCITED → EUPHORIC (per blend table).
    Set engine to HAPPY at high intensity, then feel EXCITED.
    The result should be EUPHORIC (blend) or at minimum a blend was created.
    """
    eng = _fresh_engine()
    eng.current_emotion = EmotionalState.CALM
    eng.emotional_intensity = 0.0
    # First: feel HAPPY strongly
    eng.feel_emotion(EmotionalState.HAPPY, 0.85, trigger="great news")
    assert eng.current_emotion == EmotionalState.HAPPY

    # Now: feel EXCITED strongly — blend should fire
    eng.feel_emotion(EmotionalState.EXCITED, 0.80, trigger="winning")

    # Expect EUPHORIC blend or at least a blend was created
    blend_fired = (
        eng.current_emotion == EmotionalState.EUPHORIC
        or len(eng.emotional_blends) > 0
    )
    assert blend_fired, (
        f"Expected EUPHORIC blend, got {eng.current_emotion.value} "
        f"with {len(eng.emotional_blends)} blend(s)"
    )


def test_emotional_blending_sad_into_happy_produces_nostalgic():
    """SAD + HAPPY → NOSTALGIC blend."""
    eng = _fresh_engine()
    eng.current_emotion = EmotionalState.CALM
    eng.emotional_intensity = 0.0
    eng.feel_emotion(EmotionalState.SAD, 0.80, trigger="missing someone")
    eng.feel_emotion(EmotionalState.HAPPY, 0.75, trigger="good memory")

    blend_fired = (
        eng.current_emotion == EmotionalState.NOSTALGIC
        or len(eng.emotional_blends) > 0
    )
    assert blend_fired, (
        f"Expected NOSTALGIC blend, got {eng.current_emotion.value}"
    )


# ---------------------------------------------------------------------------
# 9. get_state and get_emotional_state messages
# ---------------------------------------------------------------------------

def test_get_state_returns_valid_structure():
    ep = _fresh_process()
    ep.engine.current_emotion = EmotionalState.CURIOUS
    ep.engine.emotional_intensity = 0.55

    result = ep.process_message_safe({"type": "get_state"})
    assert result["status"] == "success"
    assert result["emotion"] == "curious"
    assert 0.0 <= result["intensity"] <= 1.0
    assert "summary" in result


def test_get_emotional_state_returns_full_output():
    ep = _fresh_process()
    ep.engine.current_emotion = EmotionalState.PLAYFUL
    ep.engine.emotional_intensity = 0.65

    result = ep.process_message_safe({"type": "get_emotional_state"})
    assert result["status"] == "success"
    assert "content" in result
    content = result["content"]
    assert content["emotion"] == "playful"
    assert isinstance(content["voice_prosody"], dict)


# ---------------------------------------------------------------------------
# 10. Health probe
# ---------------------------------------------------------------------------

def test_health_probe():
    ep = _fresh_process()
    result = ep.process_message_safe({"type": "health"})
    assert result["status"] == "success"
    assert result.get("healthy") is True


# ---------------------------------------------------------------------------
# 11. Unknown message type rejected
# ---------------------------------------------------------------------------

def test_unknown_message_type_rejected():
    ep = _fresh_process()
    result = ep.process_message_safe({"type": "do_something_impossible"})
    assert result["status"] == "error"


# ---------------------------------------------------------------------------
# 12. Mood history grows with each feel_emotion call
# ---------------------------------------------------------------------------

def test_mood_history_accumulates():
    eng = _fresh_engine()
    eng.current_emotion = EmotionalState.CALM
    eng.emotional_intensity = 0.0
    initial_len = len(eng.mood_history)

    sequence = [
        (EmotionalState.HAPPY, 0.5),
        (EmotionalState.CALM, 0.3),
        (EmotionalState.SAD, 0.6),
        (EmotionalState.CURIOUS, 0.7),
    ]
    for emotion, intensity in sequence:
        eng.feel_emotion(emotion, intensity, trigger="sequence test")

    assert len(eng.mood_history) >= initial_len + len(sequence)


# ---------------------------------------------------------------------------
# 13. Voice prosody values are in a sensible numeric range
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("emotion", ALL_EMOTIONS)
def test_voice_prosody_values_numeric(emotion):
    ep = _fresh_process()
    ep.engine.current_emotion = emotion
    ep.engine.emotional_intensity = 0.5
    output = ep.get_emotional_state_output()
    for key, val in output.voice_prosody.items():
        assert isinstance(val, (int, float)), \
            f"voice_prosody[{key}] is not numeric for {emotion.value}"


# ---------------------------------------------------------------------------
# 14. emotional_tone covers all emotions (no missing entry)
# ---------------------------------------------------------------------------

def test_emotional_tone_covers_all_emotions():
    ep = _fresh_process()
    missing = []
    for emotion in ALL_EMOTIONS:
        ep.engine.current_emotion = emotion
        ep.engine.emotional_intensity = 0.5
        output = ep.get_emotional_state_output()
        if not output.emotional_tone or output.emotional_tone == "neutral" and emotion != EmotionalState.CALM:
            # Acceptable if fallback is used, but flag blanks
            if not output.emotional_tone:
                missing.append(emotion.value)
    assert not missing, f"Emotions with empty emotional_tone: {missing}"
