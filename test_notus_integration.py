import json
from unittest.mock import Mock

from notus import NotusProcess
from thalamus import Thalamus


def make_thalamus(tmp_path):
    return Thalamus(
        socket_path=str(tmp_path / "thalamus.sock"),
        fallback_memory_path=str(tmp_path / "notus-fallback.json"),
    )


def test_error_response_stays_pending_and_survives_restart(tmp_path):
    thalamus = make_thalamus(tmp_path)
    thalamus.send_message = lambda *_: {'status': 'error', 'message': 'Notus is offline'}

    thalamus._record_conversation("hello", "hi", "neutral")

    saved = json.loads((tmp_path / "notus-fallback.json").read_text())
    assert len(saved) == 1
    assert not saved[0]['user_message']['synced_to_notus']
    assert not saved[0]['assistant_message']['synced_to_notus']

    restarted = make_thalamus(tmp_path)
    assert len(restarted._pending_conversations) == 1


def test_partial_write_retries_only_unsynced_message(tmp_path):
    thalamus = make_thalamus(tmp_path)
    responses = iter((
        {'status': 'stored'},
        {'status': 'error', 'message': 'assistant write failed'},
    ))
    thalamus.send_message = lambda *_: next(responses)

    thalamus._record_conversation("hello", "hi", "neutral")

    conversation = thalamus._pending_conversations[0]
    assert conversation['user_message']['synced_to_notus']
    assert not conversation['assistant_message']['synced_to_notus']

    calls = []

    def store_assistant_only(destination, message_type, content):
        calls.append(content)
        return {'status': 'stored'}

    thalamus.send_message = store_assistant_only
    assert thalamus.sync_memory_to_notus()
    assert calls == [{
        'role': 'assistant',
        'content': 'hi',
        'memory_type': 'conversation',
        'idempotency_key': conversation['assistant_message']['idempotency_key'],
    }]
    assert conversation['synced_to_notus']


def test_successful_retrieval_triggers_pending_recovery(tmp_path):
    thalamus = make_thalamus(tmp_path)
    thalamus.send_message = lambda *_: {'status': 'error', 'message': 'Notus is offline'}
    thalamus._record_conversation("hello", "hi", "neutral")

    calls = []

    def recovered_notus(destination, message_type, content):
        calls.append((message_type, content))
        if message_type == 'context':
            return {'status': 'success', 'context': 'recovered memory'}
        return {'status': 'stored'}

    thalamus.send_message = recovered_notus
    context = thalamus.retrieve_relevant_memory("what did I say?")

    assert context['memory_source'] == 'notus'
    assert [content['role'] for message_type, content in calls if message_type == 'store'] == [
        'user', 'assistant'
    ]
    assert not json.loads((tmp_path / "notus-fallback.json").read_text())


def test_root_notus_handler_accepts_flattened_idempotent_store_request():
    notus = NotusProcess()
    notus.memory_ready.set()
    notus.memory_system = Mock()
    notus.memory_system.store_memory.return_value = 'memory-1'

    response = notus.process_message({
        'type': 'store',
        'role': 'user',
        'content': 'hello',
        'memory_type': 'conversation',
        'idempotency_key': 'conversation-1:user',
    })

    assert response['status'] == 'stored'
    notus.memory_system.store_memory.assert_called_once_with(
        'user',
        'hello',
        memory_type='conversation',
        source_id='conversation-1:user',
    )
