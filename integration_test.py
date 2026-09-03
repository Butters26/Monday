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

if __name__ == '__main__':
    run_integration()
