"""
ExecutiveControlLobe: Executive function and control module for the AI brain architecture.
Handles decision-making, inhibition, task management, and coordination of lobe activities.
"""

class ExecutiveControlLobe:
    def __init__(self, thalamus=None):
        self.thalamus = thalamus
        self.task_list = []
        self.inhibition_state = False

    def add_task(self, task):
        """Add a new task to the executive queue."""
        self.task_list.append(task)

    def execute_next_task(self):
        """Execute the next task if not inhibited."""
        if self.inhibition_state or not self.task_list:
            return None
        task = self.task_list.pop(0)
        # TODO: Integrate with other lobes for execution
        if self.thalamus:
            # Route task to reasoning for plan, or to motor_action if actionable
            try:
                if isinstance(task, dict) and task.get('type') == 'motor':
                    self.thalamus.send_message('motor_action', 'plan_action', {'intent': task.get('intent')}, source='executive_control')
                else:
                    self.thalamus.send_message('reasoning', 'execute_task', {'task': task}, source='executive_control')
            except Exception as e:
                print(f"[ExecutiveControlLobe] Error routing task: {e}")
        print(f"[ExecutiveControlLobe] Executed task: {task}")
        return task

    def set_inhibition(self, state: bool):
        """Set inhibition state (e.g., for self-control)."""
        self.inhibition_state = state

    def reset(self):
        self.task_list.clear()
        self.inhibition_state = False

# TODO: Integrate with Thalamus and other lobes
# TODO: Add error handling, logging, and configuration
    def process_message(self, message):
        msg_type = message.get('type')
        if 'content' in message:
            content = message.get('content', {})
        else:
            content = {k: v for k, v in message.items() if k not in ('type', '_message_id', 'message_id')}
        
        if msg_type == 'select_action':
            # Select best candidate from thinking loop
            candidates = content.get('candidates', [])
            context = content.get('context', {})
            
            if not candidates:
                return {'status': 'error', 'message': 'No candidates provided'}
            
            # Select candidate with highest combined score
            # Weight: meta_score (60%), value_alignment (30%), confidence (10%)
            best_candidate = None
            best_score = -1.0
            
            for candidate in candidates:
                meta_score = candidate.get('meta_score', 0.5)
                value_alignment = candidate.get('value_alignment', 0.5)
                confidence = candidate.get('confidence', 0.5)
                risks = candidate.get('risks', [])
                
                # Penalize for risks
                risk_penalty = len(risks) * 0.1
                
                combined_score = (
                    meta_score * 0.6 +
                    value_alignment * 0.3 +
                    confidence * 0.1 -
                    risk_penalty
                )
                
                if combined_score > best_score:
                    best_score = combined_score
                    best_candidate = candidate
            
            if best_candidate:
                return {
                    'status': 'success',
                    'selected_id': best_candidate.get('id'),
                    'score': best_score
                }
            else:
                return {'status': 'error', 'message': 'No candidate could be selected'}
        
        elif msg_type == 'add_task':
            task = content.get('task')
            if task is None:
                return {'status': 'error', 'message': 'Missing task'}
            self.add_task(task)
            return {'status': 'success', 'message': 'Task added'}
        elif msg_type == 'execute_next':
            task = self.execute_next_task()
            if task is None:
                return {'status': 'success', 'message': 'No task executed (inhibited or empty)'}
            return {'status': 'success', 'task': task}
        elif msg_type == 'set_inhibition':
            state = content.get('state', False)
            self.set_inhibition(bool(state))
            return {'status': 'success', 'inhibition': self.inhibition_state}
        elif msg_type == 'reset':
            self.reset()
            return {'status': 'success', 'message': 'ExecutiveControlLobe reset'}
        else:
            return {'status': 'error', 'message': f'Unknown message type: {msg_type}'}
