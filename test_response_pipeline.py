import unittest

from language_generation import LanguageGenerator
from thalamus import Thalamus


class ResponsePipelineTests(unittest.TestCase):
    def test_language_generation_does_not_deliver_output(self):
        language = LanguageGenerator.__new__(LanguageGenerator)
        language.generate = lambda semantic_input: "A generated response"

        result = language.process_message({
            'type': 'generate',
            'semantic_input': {'intent': 'state_fact'},
            'is_main_response': True,
        })

        self.assertEqual(result['sentence'], "A generated response")
        self.assertNotIn('sent_to_output', result)

    def test_express_preserves_completed_thought(self):
        language = LanguageGenerator.__new__(LanguageGenerator)
        thought = "Reasoning's completed response must remain unchanged."

        result = language.process_message({'type': 'express', 'thought': thought})

        self.assertEqual(result['response'], thought)
        self.assertTrue(result['preserved_thought'])

    def test_thalamus_delivers_normal_response_once(self):
        thalamus = Thalamus.__new__(Thalamus)
        calls = []
        thalamus.monday_memory = {
            'beliefs': {},
            'past_conversations': [],
            'emotional_state': {'loneliness': 0.0, 'curiosity': 0.0},
            'user': 'user',
            'learned_facts': {},
        }
        thalamus.retrieve_relevant_memory = lambda user_input: {
            'emotional_state': {'curiosity': 0.0},
        }
        thalamus._log_conversation = lambda *args: None

        def send_message(destination, message_type, content):
            calls.append((destination, message_type, content))
            if destination == 'conversation':
                return {
                    'status': 'success',
                    'understanding': {'intent': 'statement', 'confidence': 1.0},
                    'response': 'Conversation fallback',
                    'emotion': 'neutral',
                    'intensity': 0.5,
                }
            if destination == 'reasoning':
                return {
                    'status': 'success',
                    'thinking': {
                        'composed_response': 'Language verbalized the reasoning.',
                        'emotion': 'curious',
                        'intensity': 0.7,
                    },
                }
            if destination == 'output':
                return {'status': 'success', 'text': content['content']['text']}
            self.fail(f"Unexpected destination: {destination}")

        thalamus.send_message = send_message

        response = thalamus.process_user_input('Explain the connection.')

        self.assertEqual(response, 'Language verbalized the reasoning.')
        self.assertEqual(
            [(destination, message_type) for destination, message_type, _ in calls],
            [('conversation', 'understand'), ('reasoning', 'think'), ('output', 'generate_output')],
        )
        output_content = calls[-1][2]['content']
        self.assertEqual(output_content['user_input'], 'Explain the connection.')


if __name__ == '__main__':
    unittest.main()
