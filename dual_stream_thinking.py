#!/usr/bin/env python3
"""
Dual Stream Thinking - Integration of spontaneous and controlled thought
Monday experiences both streams simultaneously with meta-control
"""

import time
from typing import Optional, Dict, Any
from continuous_thought_generator import ContinuousThoughtGenerator
from controlled_thinking import ControlledThinking
from meta_awareness import MetaAwareness, ThinkingMode


class DualStreamThinking: 
    """
    Manages both spontaneous and controlled thinking streams
    Monday experiences both, with meta-awareness controlling engagement
    """
    
    def __init__(self):
        # Initialize both systems
        self.spontaneous = ContinuousThoughtGenerator()
        self.controlled = ControlledThinking()
        self.meta = MetaAwareness()
        
        # Connect systems to meta-awareness
        self.meta.set_spontaneous_system(self.spontaneous)
        self.meta.set_controlled_system(self.controlled)
        
        # Tracking
        self.running = False
        self.total_thoughts = 0
        self.thought_log = []
    
    def start(self, duration: Optional[float] = None):
        """Start both thought streams"""
        self.running = True
        
        print("=" * 70)
        print("DUAL STREAM THINKING - MONDAY'S MIND")
        print("=" * 70)
        print("Both spontaneous and controlled thinking active")
        print("Meta-awareness managing engagement\n")
        
        start_time = time.time()
        
        # Run integrated loop
        while self.running:
            if duration and (time.time() - start_time) > duration:
                break
            
            # SPONTANEOUS STREAM (always running)
            spontaneous_thought = self.spontaneous.generate_thought()
            self.total_thoughts += 1
            
            # Display spontaneous thought
            elapsed = time.time() - start_time
            print(f"[{elapsed:.1f}s] 💭 [SPONTANEOUS/{spontaneous_thought['trigger']}]")
            print(f"      {spontaneous_thought['text']}")
            
            # META-AWARENESS:  notice and decide
            meta_response = self.meta.notice_spontaneous_thought(spontaneous_thought)
            
            if meta_response.get("meta_comment"):
                print(f"      🔍 Meta:  \"{meta_response['meta_comment']}\"")
            
            # CONTROLLED STREAM (only if engaged or already focused)
            if meta_response["action"] == "engaged": 
                print(f"      ✅ ENGAGING - shifting to focused thinking")
                
                # Start controlled reasoning
                topic = meta_response.get("topic", "unknown")
                question = meta_response.get("question", f"Think about {topic}")
                
                self.controlled.start_reasoning(topic, question, depth=3)
                
                # Take reasoning steps
                for i in range(3):
                    time.sleep(0.8)
                    step = self.controlled.reason_step()
                    if not step: 
                        break
                
                # After controlled reasoning completes, return to wandering
                if self.controlled.current_goal and self.controlled.current_goal.completed:
                    self.meta.shift_to_wandering("Completed reasoning")
            
            elif meta_response["action"] == "dismissed":
                print(f"      ❌ Dismissed:  {meta_response.get('reason', 'Not interesting')}")
            
            elif meta_response["action"] == "unnoticed":
                print(f"      👻 Passed by unnoticed")
            
            # If currently in focused mode and controlled system has active goal
            if self.meta.state.mode == ThinkingMode.FOCUSED and self.controlled.is_focused:
                print(f"      🎯 [FOCUSED] Continuing reasoning...")
                step = self.controlled.reason_step()
                if step:
                    time.sleep(0.5)
            
            print()
            
            # Log thought
            self.thought_log.append({
                "spontaneous":  spontaneous_thought,
                "meta_response": meta_response,
                "timestamp": time.time(),
            })
            
            # Calculate next spontaneous thought interval
            interval = self.spontaneous._calculate_thought_interval()
            
            # Wait before next spontaneous thought
            time.sleep(interval)
        
        # Summary
        self._print_summary(time.time() - start_time)
    
    def stop(self):
        """Stop both thought streams"""
        self.running = False
        print("\n🛑 Stopping dual stream thinking...")
    
    def _print_summary(self, duration: float):
        """Print summary of thinking session"""
        print("\n" + "=" * 70)
        print("SESSION SUMMARY")
        print("=" * 70)
        
        meta_summary = self.meta.get_meta_state_summary()
        
        print(f"Duration: {duration:.1f}s")
        print(f"Total spontaneous thoughts: {self.total_thoughts}")
        print(f"Thoughts noticed: {meta_summary['thoughts_noticed']}")
        print(f"Thoughts engaged: {meta_summary['thoughts_engaged']}")
        print(f"Thoughts dismissed: {meta_summary['thoughts_dismissed']}")
        print(f"Engagement rate: {meta_summary['engagement_rate']:.1%}")
        print(f"Mode shifts: {meta_summary['mode_shifts']}")
        print(f"Final mode: {meta_summary['mode']}")
        print(f"Final awareness level: {meta_summary['awareness_level']:.2f}")
        
        print("\n" + "=" * 70)


def test_dual_stream():
    """Test the integrated dual stream thinking"""
    system = DualStreamThinking()
    
    try:
        # Run for 45 seconds
        system.start(duration=45.0)
    except KeyboardInterrupt:
        system.stop()
        print("\n✅ Test interrupted by user")


if __name__ == "__main__":
    test_dual_stream()
