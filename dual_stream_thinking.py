import os
from datetime import datetime
from typing import Any, Dict

try:
    import anthropic
except ImportError:
    anthropic = None

class DualStreamThinking:
    def __init__(self):
        self.running = True
        self.client = (
            anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
            if anthropic is not None
            else None
        )
        self.model = "claude-3-7-sonnet-20250219"
        self.max_reasoning_depth = 5

        from thalamus import get_thalamus
        self.thalamus = get_thalamus()
        
    def start_reasoning(self, user_query):
        """
        Start the reasoning process with extended thinking enabled.
        """
        print(f"\n{'='*80}")
        print(f"Starting reasoning for query: {user_query}")
        print(f"{'='*80}\n")
        
        if self.client is None:
            return None
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=16000,
                thinking={
                    "type": "enabled",
                    "budget_tokens": 10000
                },
                messages=[{
                    "role": "user",
                    "content": user_query
                }]
            )
            
            return self._process_response(response)
            
        except Exception as e:
            print(f"Error in reasoning: {str(e)}")
            return None

    def start(self):
        self.thalamus.register_lobe("dual_stream", self)

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        message_type = message.get("type")
        if message_type == "health":
            return {
                "status": "success",
                "healthy": True,
                "anthropic_available": self.client is not None,
            }
        if message_type == "think":
            if self.client is None:
                return {
                    "status": "error",
                    "message": "Dual-stream reasoning requires the anthropic package",
                }
            result = self.start_reasoning(message.get("content", {}).get("user_input", ""))
            if result is None:
                return {"status": "error", "message": "Dual-stream reasoning failed"}
            return {"status": "success", "content": result}
        return {"status": "error", "message": f"Unknown message type: {message_type}"}

    def shutdown(self):
        self.running = False
    
    def _process_response(self, response):
        """
        Process the API response and extract thinking and text blocks.
        """
        thinking_content = []
        text_content = []
        
        for block in response.content:
            if block.type == "thinking":
                thinking_content.append(block.thinking)
            elif block.type == "text":
                text_content.append(block.text)
        
        result = {
            "thinking": "\n".join(thinking_content),
            "response": "\n".join(text_content),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return result
    
    def display_results(self, result):
        """
        Display the reasoning process and final response.
        """
        if not result:
            print("No results to display")
            return
            
        print(f"\n{'='*80}")
        print("THINKING PROCESS:")
        print(f"{'='*80}")
        print(result["thinking"])
        
        print(f"\n{'='*80}")
        print("FINAL RESPONSE:")
        print(f"{'='*80}")
        print(result["response"])
        print(f"\nTimestamp: {result['timestamp']}")

def main():
    # Initialize the dual stream thinking system
    system = DualStreamThinking()
    
    # Example query
    query = "Explain the concept of recursion in programming and provide a practical example."
    
    # Start reasoning and get results - using default max_reasoning_depth
    results = system.start_reasoning(query)
    
    # Display results
    system.display_results(results)

if __name__ == "__main__":
    main()
