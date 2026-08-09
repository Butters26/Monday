"""
Integration test: wire lobes into Thalamus and run end-to-end message flow.
Flow tested:
  sensory_integration.ingest -> perception.sensory_data -> attention.update/select/route -> reasoning -> executive -> motor_action -> output
This uses lightweight stubs for `perception`, `reasoning`, `language`, and `output` to keep the test self-contained.
"""

from thalamus import Thalamus, get_thalamus
import time

# Import real lobes we've implemented
from attention_lobe import AttentionLobe
from motor_action_lobe import MotorActionLobe
from executive_control_lobe import ExecutiveControlLobe
from meta_cognition_lobe import MetaCognitionLobe
from social_context_lobe import SocialContextLobe
from sensory_integration_lobe import SensoryIntegrationLobe
from value_goal_management_lobe import ValueGoalManagementLobe

# Lightweight stub lobes for core components
class PerceptionStub:
    def __init__(self, thalamus=None):
        self.thalamus = thalamus
    def process_message(self, message):
        mtype = message.get('type')
        # Support both Thalamus flattened message and nested 'content'
        if 'content' in message:
            content = message.get('content', {})
        else:
            content = {k: v for k, v in message.items() if k not in ('type', '_message_id', 'message_id')}
        print(f"[PerceptionStub] got {mtype} -> {content}")
        if mtype == 'sensory_data':
            signals = content.get('signals', [])
            # Forward to attention via Thalamus
            self.thalamus.send_message('attention', 'update_salience', {'signals': signals}, source='perception')
            # Ask attention to select focus
            res = self.thalamus.send_message('attention', 'select_focus', {}, source='perception')
            focus = res.get('focus')
            if focus:
                # Trigger routing of focus
                self.thalamus.send_message('attention', 'route_focus', {}, source='perception')
            return {'status': 'success'}
        return {'status': 'error', 'message': 'unknown'}

class ReasoningStub:
    def __init__(self, thalamus=None):
        self.thalamus = thalamus
    def process_message(self, message):
        mtype = message.get('type')
        if 'content' in message:
            content = message.get('content', {})
        else:
            content = {k: v for k, v in message.items() if k not in ('type', '_message_id', 'message_id')}
        print(f"[ReasoningStub] got {mtype} -> {content}")
        if mtype == 'attention_focus' or mtype == 'attention_focus_request':
            focus = content.get('focus', 'unknown')
            # Make a simple decision: produce a motor action intent
            next_action = {'type': 'motor', 'intent': 'move_forward'}
            # Route decision to executive
            self.thalamus.send_message('executive_control', 'add_task', {'task': next_action}, source='reasoning')
            return {'status': 'success', 'content': {'decision': 'act', 'next_action': next_action}}
        elif mtype == 'execute_task':
            task = content.get('task')
            # Simulate doing some reasoning, then if motor, ask exec to handle
            if isinstance(task, dict) and task.get('type') == 'motor':
                self.thalamus.send_message('motor_action', 'plan_action', {'intent': task.get('intent')}, source='reasoning')
            return {'status': 'success'}
        return {'status': 'success'}

class OutputStub:
    def __init__(self, thalamus=None):
        self.thalamus = thalamus
        self.received = []
    def process_message(self, message):
        mtype = message.get('type')
        if 'content' in message:
            content = message.get('content', {})
        else:
            content = {k: v for k, v in message.items() if k not in ('type', '_message_id', 'message_id')}
        print(f"[OutputStub] got {mtype} -> {content}")
        if mtype == 'motor_output':
            self.received.append(content.get('action'))
            return {'status': 'success'}
        return {'status': 'error', 'message': 'unknown'}

class LanguageStub:
    def __init__(self, thalamus=None):
        self.thalamus = thalamus
    def process_message(self, message):
        mtype = message.get('type')
        if 'content' in message:
            content = message.get('content', {})
        else:
            content = {k: v for k, v in message.items() if k not in ('type', '_message_id', 'message_id')}
        print(f"[LanguageStub] got {mtype} -> {content}")
        if mtype == 'generate_reply':
            return {'status': 'success', 'content': {'text': 'hello!'}}
        return {'status': 'success'}


class EnvelopeProbe:
    def process_message(self, message):
        assert set(message) == {'type', 'source', 'content', 'message_id', 'timestamp', 'trace_id'}
        assert message['content'] == {'value': 'preserved'}
        assert message.get('value') == 'preserved'
        return {'status': 'success', 'received': dict(message)}


class ErrorProbe:
    def process_message(self, message):
        return {'status': 'error', 'message': 'intentional failure'}


class PipelineProbe:
    def __init__(self, name, calls):
        self.name = name
        self.calls = calls
        self.pending_speech = None

    def process_message(self, message):
        self.calls.append((self.name, message['type'], message['content'], message['trace_id']))
        if self.name == 'notus':
            return {'status': 'success', 'memory_context': 'remembered'}
        if self.name == 'conversation':
            return {'status': 'success', 'content': {'understanding': {'intent': 'question'}}}
        if self.name == 'reasoning':
            return {'status': 'success', 'thinking': {'composed_response': 'A considered answer.'}}
        if self.name == 'language':
            return {'status': 'success', 'sentence': 'A clear answer.'}
        if self.name == 'output':
            return {'status': 'success', 'text': message['content']['text']}
        if self.name == 'speech':
            if message['type'] == 'evaluate_thought':
                self.pending_speech = message['content']['thought']
                return {
                    'status': 'success',
                    'decision': {'timing': 'now', 'should_speak': True},
                }
            if message['type'] == 'get_pending_speech':
                thought, self.pending_speech = self.pending_speech, None
                return {
                    'status': 'success',
                    'speech': {
                        'content': thought['content'],
                        'priority': thought['intensity'],
                        'thought_id': thought['id'],
                    } if thought else None,
                }
        return {'status': 'success'}


def run_user_pipeline_integration():
    thalamus = Thalamus()
    calls = []
    lobe_names = (
        'notus', 'perception', 'pattern', 'representation', 'social_context', 'emotion',
        'value_goal_management', 'conversation', 'reasoning', 'language',
        'output', 'voice', 'experience', 'reinforcement', 'reflection', 'autonomous', 'speech',
    )
    for name in lobe_names:
        assert thalamus.register_lobe(name, PipelineProbe(name, calls))['status'] == 'success'

    result = thalamus.process_user_input('What changed?')
    assert result == {
        'status': 'success',
        'response': 'A clear answer.',
        'trace_id': result['trace_id'],
    }
    assert {name for name, _, _, _ in calls} == set(lobe_names)
    assert len({trace_id for _, _, _, trace_id in calls}) == 1
    conversation_call = next(call for call in calls if call[0] == 'conversation')
    assert conversation_call[2]['context']['memory']['memory_context'] == 'remembered'
    language_call = next(call for call in calls if call[0] == 'language')
    assert language_call[1] == 'express'
    assert language_call[2]['thought'] == 'A considered answer.'

    autonomous_results = thalamus._route_autonomous_actions(
        [{'type': 'message', 'target': 'interface', 'content': 'An autonomous thought.'}]
    )
    assert autonomous_results[0]['status'] == 'success'
    assert autonomous_results[0]['decision']['timing'] == 'now'
    thalamus._deliver_pending_autonomous_speech()
    autonomous_language_call = [call for call in calls if call[0] == 'language'][-1]
    assert autonomous_language_call[2]['thought'] == 'An autonomous thought.'
    assert [call for call in calls if call[0] == 'voice']
    print('User pipeline integration SUCCESS')


def run_integration():
    th = get_thalamus()

    # Instantiate lobes
    attention = AttentionLobe(thalamus=th)
    motor = MotorActionLobe(thalamus=th)
    executive = ExecutiveControlLobe(thalamus=th)
    meta = MetaCognitionLobe(thalamus=th)
    social = SocialContextLobe(thalamus=th)
    sensory = SensoryIntegrationLobe(thalamus=th)
    value_mgr = ValueGoalManagementLobe(thalamus=th)

    perception = PerceptionStub(thalamus=th)
    reasoning = ReasoningStub(thalamus=th)
    language = LanguageStub(thalamus=th)
    output = OutputStub(thalamus=th)

    # Register lobes
    lobes = {
        'attention': attention,
        'motor_action': motor,
        'executive_control': executive,
        'meta_cognition': meta,
        'social_context': social,
        'sensory_integration': sensory,
        'value_goal_management': value_mgr,
        'perception': perception,
        'reasoning': reasoning,
        'language': language,
        'output': output
    }

    for name, inst in lobes.items():
        r = th.register_lobe(name, inst)
        print(f"Registered {name}: {r}")

    assert th.register_lobe('envelope_probe', EnvelopeProbe())['status'] == 'success'
    envelope_result = th.send_message(
        'envelope_probe', 'probe', {'value': 'preserved'}, source='integration_test'
    )
    assert envelope_result['status'] == 'success'
    assert th.register_lobe('error_probe', ErrorProbe())['status'] == 'success'
    failure = th.send_message('error_probe', 'fail', {}, source='integration_test')
    assert failure['status'] == 'error'
    assert failure['message'] == 'intentional failure'

    # Run the flow: ingest sensory inputs
    print('\n--- Starting flow: sensory ingestion ---')
    result = th.send_message('sensory_integration', 'ingest', {'inputs': ['Important sound', 'visual cue']}, source='test')
    print('Ingest result:', result)

    # Give things a moment for sync messages (all send_message is synchronous in this Thalamus)
    time.sleep(0.5)

    # Now trigger executive to execute next task (which should route to motor)
    print('\n--- Triggering executive to execute next task ---')
    res_exec = th.send_message('executive_control', 'execute_next', {}, source='test')
    print('Execute next result:', res_exec)

    # Trigger motor to execute next
    res_motor = th.send_message('motor_action', 'execute_next', {}, source='test')
    print('Motor execute result:', res_motor)

    # Check output received motor output
    assert output.received, 'Output did not receive motor output'
    print('Integration test SUCCESS: output received:', output.received)
    run_user_pipeline_integration()

if __name__ == '__main__':
    run_integration()
