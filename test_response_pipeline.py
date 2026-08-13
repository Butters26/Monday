from conversation import ConversationSystem
from language_generation import GrammarEngine, LanguageGenerator
from reasoning import MaximumSophisticationReasoning
from thalamus import Thalamus
from types import SimpleNamespace


def test_hello_routes_to_greeting_realization():
    conversation = ConversationSystem()
    understanding = conversation.understand("hello")

    assert understanding["intent"] == "greeting"
    sentence = GrammarEngine().compose_sentence(
        {
            "intent": understanding["intent"],
            "emotion": "curious",
            "greeting": {
                "acknowledgment": "Hello",
                "current_emotion": "curious",
            },
        }
    )
    assert sentence == "Hello I'm glad to connect."


def test_reasoning_conclusion_is_realized_directly():
    sentence = GrammarEngine().compose_sentence(
        {
            "intent": "question",
            "answer": "Plants convert light energy into chemical energy.",
            "concepts": ["plants", "light"],
        }
    )

    assert sentence == "Plants convert light energy into chemical energy."


def test_reasoning_preserves_greeting_and_exposes_conclusion():
    reasoning = MaximumSophisticationReasoning.__new__(MaximumSophisticationReasoning)
    reasoning.subjective_state = SimpleNamespace(
        feels_curious=0.0,
        feels_confused=0.0,
        feels_certain=0.0,
    )

    semantic_input = reasoning._build_semantic_input(
        {
            "key_concepts": ["hello"],
            "theories": [
                {
                    "explanation": "Light enables photosynthesis.",
                    "supporting_facts": ["Plants use light energy."],
                }
            ],
        },
        "hello",
        False,
        {"intent": "greeting", "confidence": 0.9},
    )

    assert semantic_input["intent"] == "greeting"
    assert semantic_input["answer"] == "Light enables photosynthesis."
    assert semantic_input["propositions"] == [
        "Light enables photosynthesis.",
        "Plants use light energy.",
    ]


def test_reasoning_think_message_preserves_top_level_understanding(monkeypatch):
    reasoning = MaximumSophisticationReasoning.__new__(MaximumSophisticationReasoning)
    received = {}
    monkeypatch.setattr(
        reasoning,
        "think_about",
        lambda input_data: received.setdefault("input_data", input_data) or {},
    )

    reasoning.process_message(
        {
            "type": "think",
            "input": {
                "user_input": "hello",
                "understanding": {"intent": "greeting"},
            },
        }
    )

    assert received["input_data"]["understanding"]["intent"] == "greeting"


def test_thalamus_generates_and_delivers_once(monkeypatch):
    thalamus = Thalamus()
    calls = []

    def send_message(destination, msg_type, content):
        calls.append((destination, msg_type, content))
        if destination == "conversation":
            return {
                "status": "success",
                "content": {
                    "understanding": {"intent": "greeting", "confidence": 0.9},
                    "emotion": "curious",
                    "intensity": 0.5,
                },
            }
        if destination == "reasoning":
            assert content["input"]["understanding"]["intent"] == "greeting"
            return {
                "status": "success",
                "thinking": {
                    "semantic_input": {
                        "intent": "greeting",
                        "greeting": {
                            "acknowledgment": "Hello",
                            "current_emotion": "curious",
                        },
                    },
                },
            }
        if destination == "language":
            assert msg_type == "generate"
            assert content["semantic_input"]["intent"] == "greeting"
            return {"status": "success", "sentence": "Hello I'm glad to connect."}
        if destination == "output":
            assert msg_type == "generate_output"
            return {"status": "success", "text": content["content"]["text"]}
        raise AssertionError(f"Unexpected route: {destination}/{msg_type}")

    monkeypatch.setattr(thalamus, "send_message", send_message)
    monkeypatch.setattr(thalamus, "_log_conversation", lambda *args: None)

    assert thalamus.process_user_input("hello") == "Hello I'm glad to connect."
    assert [(destination, msg_type) for destination, msg_type, _ in calls] == [
        ("conversation", "understand"),
        ("reasoning", "think"),
        ("language", "generate"),
        ("output", "generate_output"),
    ]


def test_language_generation_never_delivers_to_output():
    generator = LanguageGenerator()

    result = generator.process_message(
        {
            "type": "generate",
            "semantic_input": {
                "intent": "greeting",
                "greeting": {"acknowledgment": "Hello"},
            },
        }
    )

    assert result["sent_to_output"] is False
    assert not hasattr(generator, "_send_to_output")
