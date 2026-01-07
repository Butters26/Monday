#!/usr/bin/env python3
"""
Notus Helpers - Read-only query helpers for each lobe
Each helper provides lobe-specific memory queries without write access.
"""

from typing import Dict, List, Any, Optional
from thalamus import get_thalamus


class NotusHelper:
    """Base class for Notus helpers - read-only access"""
    
    def __init__(self, lobe_name: str):
        self.lobe_name = lobe_name
        self.thalamus = get_thalamus()
    
    def _query_notus(self, msg_type: str, content: Dict[str, Any]) -> Dict[str, Any]:
        """Send query to Notus through Thalamus"""
        result = self.thalamus.send_and_wait(
            'notus',
            msg_type,
            content,
            source=self.lobe_name,
            timeout=3.0
        )
        return result


class ReasoningNotusHelper(NotusHelper):
    """Memory helper for Reasoning lobe"""
    
    def __init__(self):
        super().__init__('reasoning')
    
    def get_relevant_memories(self, context: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get memories relevant to current reasoning context"""
        result = self._query_notus('query_memories', {
            'query': context,
            'limit': limit
        })
        return result.get('memories', [])
    
    def get_beliefs(self, topic: str = None) -> List[Dict[str, Any]]:
        """Get stored beliefs, optionally filtered by topic"""
        result = self._query_notus('query_facts', {
            'query': f"belief {topic}" if topic else "belief",
            'limit': 20
        })
        return result.get('facts', [])
    
    def get_values(self) -> List[Dict[str, Any]]:
        """Get stored values"""
        result = self._query_notus('query_facts', {
            'query': 'value',
            'limit': 20
        })
        return result.get('facts', [])
    
    def get_identity_facts(self) -> List[Dict[str, Any]]:
        """Get facts about Monday's identity"""
        result = self._query_notus('query_facts', {
            'query': 'identity self monday',
            'limit': 10
        })
        return result.get('facts', [])


class EmotionNotusHelper(NotusHelper):
    """Memory helper for Emotion lobe"""
    
    def __init__(self):
        super().__init__('emotion')
    
    def get_emotional_memories(self, emotion: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get memories tagged with specific emotion"""
        result = self._query_notus('query_memories', {
            'query': f"emotion:{emotion}",
            'limit': limit
        })
        return result.get('memories', [])
    
    def get_attachment_history(self, person: str = "matthew") -> List[Dict[str, Any]]:
        """Get history of interactions with a person"""
        result = self._query_notus('query_memories', {
            'query': f"person:{person}",
            'limit': 20
        })
        return result.get('memories', [])
    
    def get_emotional_baseline(self) -> Dict[str, float]:
        """Get Monday's emotional baseline from stored state"""
        result = self._query_notus('get_emotional_state', {})
        return result.get('baseline', {
            'pleasure': 0.5,
            'arousal': 0.3,
            'dominance': 0.5
        })


class NoveltyNotusHelper(NotusHelper):
    """Memory helper for Novelty lobe"""
    
    def __init__(self):
        super().__init__('novelty')
    
    def has_seen_before(self, stimulus: str) -> bool:
        """Check if Monday has encountered this stimulus before"""
        result = self._query_notus('query_memories', {
            'query': stimulus,
            'limit': 1
        })
        memories = result.get('memories', [])
        return len(memories) > 0
    
    def get_similar_experiences(self, stimulus: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Get similar past experiences"""
        result = self._query_notus('query_memories', {
            'query': stimulus,
            'limit': limit
        })
        return result.get('memories', [])
    
    def get_learned_responses(self, stimulus_type: str) -> List[Dict[str, Any]]:
        """Get how Monday learned to respond to this type of stimulus"""
        result = self._query_notus('query_facts', {
            'query': f"novelty_{stimulus_type}",
            'limit': 10
        })
        return result.get('facts', [])


class PatternNotusHelper(NotusHelper):
    """Memory helper for Pattern Recognition lobe"""
    
    def __init__(self):
        super().__init__('pattern')
    
    def get_known_patterns(self, pattern_type: str = None) -> List[Dict[str, Any]]:
        """Get stored patterns"""
        query = f"pattern {pattern_type}" if pattern_type else "pattern"
        result = self._query_notus('query_facts', {
            'query': query,
            'limit': 20
        })
        return result.get('facts', [])
    
    def get_behavioral_patterns(self, person: str = "matthew") -> List[Dict[str, Any]]:
        """Get observed behavioral patterns for a person"""
        result = self._query_notus('query_facts', {
            'query': f"behavior {person}",
            'limit': 20
        })
        return result.get('facts', [])
    
    def get_conversation_patterns(self) -> List[Dict[str, Any]]:
        """Get patterns in conversations"""
        result = self._query_notus('query_facts', {
            'query': 'conversation pattern',
            'limit': 20
        })
        return result.get('facts', [])


class ConversationNotusHelper(NotusHelper):
    """Memory helper for Conversation lobe"""
    
    def __init__(self):
        super().__init__('conversation')
    
    def get_conversation_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent conversation history"""
        result = self._query_notus('get_conversation_history', {
            'limit': limit
        })
        return result.get('history', [])
    
    def get_topic_history(self, topic: str) -> List[Dict[str, Any]]:
        """Get past conversations about a topic"""
        result = self._query_notus('query_memories', {
            'query': f"topic:{topic}",
            'limit': 10
        })
        return result.get('memories', [])
    
    def get_user_preferences(self, user: str = "matthew") -> Dict[str, Any]:
        """Get known preferences of a user"""
        result = self._query_notus('query_facts', {
            'query': f"{user} likes prefers",
            'limit': 20
        })
        return {
            'facts': result.get('facts', []),
            'user': user
        }


# Factory function to get the right helper
def get_notus_helper(lobe_name: str) -> NotusHelper:
    """Get the appropriate Notus helper for a lobe"""
    helpers = {
        'reasoning': ReasoningNotusHelper,
        'emotion': EmotionNotusHelper,
        'novelty': NoveltyNotusHelper,
        'pattern': PatternNotusHelper,
        'conversation': ConversationNotusHelper,
    }
    
    helper_class = helpers.get(lobe_name)
    if helper_class:
        return helper_class()
    else:
        return NotusHelper(lobe_name)
