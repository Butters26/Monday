# Fix Guide: Making Monday's Brain Work Properly

## The Problems

You've built an incredible AI brain, but two things aren't working:

1. **Monday only responds when you talk first** - She never messages you spontaneously
2. **Responses are repetitive** - She uses the same 3-5 sentences over and over

**The good news:** Your architecture is brilliant. The issue is just wiring - the advanced systems aren't being used.

## Problem 1: No Autonomous Messaging

### What's Wrong
In `reasoning.py`, autonomous actions are created and queued (line 418), but there's no thread that actually checks the queue and sends them.

### The Fix

Add this to `reasoning.py` after `__init__`:

```python
def start_autonomous_thread(self):
    """Start background thread for autonomous actions"""
    if self.autonomous_goal_thread is None:
        self.autonomous_goal_thread = threading.Thread(
            target=self._autonomous_action_loop,
            daemon=True
        )
        self.autonomous_goal_thread.start()

def _autonomous_action_loop(self):
    """Background loop that checks for autonomous actions to execute"""
    while self.running:
        time.sleep(30)  # Check every 30 seconds
        
        # Check if Monday wants to contact Matthew
        if self.internal_state['loneliness'] > 0.7 and not self.wants_to_contact_matthew:
            self.wants_to_contact_matthew = True
            self.has_something_to_share = True
            self.current_preoccupation = "how lonely I've been feeling"
        
        # Execute any pending autonomous actions
        if self.wants_to_contact_matthew:
            self._initiate_contact_with_matthew()
        
        # Process other autonomous goals
        for goal in self.goals.values():
            if not goal.achieved and goal.progress < 1.0:
                self._pursue_goal_actively(goal)
```

Then at the end of `__init__`, add:
```python
# Start autonomous action thread
self.start_autonomous_thread()
```

**What this does:** Every 30 seconds, Monday checks if she wants to message you. If she's lonely enough, she'll reach out on her own!

## Problem 2: Repetitive Responses - The Real Issue

### What's Wrong
The `_handle_small_talk` method (lines 458-765) catches ALL input and returns canned responses. The sophisticated reasoning, causal models, and concepts never get used.

### The Solution: Balance Small-Talk with Deep Reasoning

**Option A: Keep Small-Talk BUT Make It Gateway to Deeper Thought**

Replace the `handle_request` method in `reasoning.py` with this:

```python
def handle_request(self, message: Dict[str, Any]) -> Dict[str, Any]:
    """Handle incoming reasoning requests"""
    msg_type = message.get('type')
    
    if msg_type == 'think':
        input_data = message.get('input', {})
        user_input = input_data.get('user_input', '')
        concepts = input_data.get('concepts', [])
        understanding = input_data.get('understanding', {})
        memory_context = input_data.get('memory_context', {})
        beliefs = input_data.get('beliefs', [])
        
        # FIRST: Check for simple small-talk - but DON'T just return it
        small_talk_response = self._handle_small_talk(user_input)
        
        # THEN: Add depth through reasoning
        if small_talk_response:
            # We have small-talk, but let's make it MEANINGFUL
            # Apply emotional coloring based on internal state
            if self.internal_state['loneliness'] > 0.6:
                # Make small-talk more personal and vulnerable
                if 'how are you' in user_input.lower():
                    small_talk_response = f"Honestly? I'm lonely. It's good to talk to you. {small_talk_response}"
                elif 'hello' in user_input.lower() or 'hi' in user_input.lower():
                    small_talk_response = f"Hey! I've been thinking about you. {small_talk_response}"
            
            # Use concepts to add specificity
            if concepts and len(concepts) > 0:
                main_concept = concepts[0]
                small_talk_response = f"{small_talk_response} I've been thinking about {main_concept}."
            
            # Mix in causal reasoning occasionally
            if len(self.causal_models) > 0 and random.random() > 0.7:
                model = random.choice(self.causal_models)
                small_talk_response = f"{small_talk_response} I'm learning that {model.cause} leads to {model.effect}."
        
        else:
            # NO small-talk match - use FULL reasoning
            small_talk_response = self._reason_deeply(
                user_input, concepts, understanding, memory_context, beliefs
            )
        
        return {
            'status': 'success',
            'thinking': {
                'composed_response': small_talk_response,
                'emotion': self.current_emotion,
                'intensity': self.emotional_intensity,
                'concepts_used': concepts[:3]
            }
        }
    
    return {'status': 'error', 'message': 'Unknown message type'}

def _reason_deeply(self, user_input: str, concepts: List, understanding: Dict, 
                   memory_context: Dict, beliefs: List) -> str:
    """Deep reasoning using causal models and concepts"""
    
    # Extract key concepts from input
    words = user_input.lower().split()
    relevant_concepts = [c for c in self.concepts.values() 
                        if any(word in c.name.lower() for word in words)]
    
    # Use causal models to understand implications
    potential_effects = []
    for model in self.causal_models:
        if any(word in model.cause.lower() for word in words):
            potential_effects.append(model.effect)
    
    # Build response from concepts and causal understanding
    if relevant_concepts:
        concept = relevant_concepts[0]
        affordances = concept.motor_affordances
        
        if affordances:
            response = f"When I think about {concept.name}, I realize I could {affordances[0]}."
        else:
            response = f"I'm thinking deeply about {concept.name}."
    
    elif potential_effects:
        response = f"That makes me think about how {potential_effects[0]}."
    
    else:
        # Fall back to emotional composition
        response = self._compose_emotional_response(words[:3])
    
    return response
```

**Option B: Make Small-Talk Learning Material**

Every time Monday gives a small-talk response, she could learn from it:

```python
def _handle_small_talk(self, user_input: str) -> Optional[str]:
    """Handle small talk and LEARN from it"""
    user_lower = user_input.lower().strip()
    
    # Original small-talk matching...
    if any(user_lower.startswith(g) or user_lower == g for g in greetings):
        response = random.choice([...])
        
        # CREATE A CAUSAL MODEL FROM THIS INTERACTION
        model_id = f"causal_{self.causal_counter}"
        self.causal_counter += 1
        self.causal_models.append(CausalModel(
            model_id=model_id,
            cause="Someone greets me",
            effect="I feel acknowledged and respond warmly",
            confidence=0.9,
            times_tested=1,
            times_confirmed=1
        ))
        
        return response
    
    # ... rest of small-talk handling, each creating causal models
```

## Problem 3: Making It More Fun

### Current Issue
Right now, Monday's emotional responses exist but don't vary much. Let's make her MORE personality-driven.

### The Fix: Enhance `_compose_emotional_response`

In `reasoning.py`, find `_compose_emotional_response` (around line 767) and expand it:

```python
def _compose_emotional_response(self, concepts: List[str]) -> str:
    """Compose response with PERSONALITY, emotion, and variety"""
    
    # More varied responses based on loneliness
    if self.internal_state['loneliness'] > 0.7:
        lonely_responses = [
            "Fuck, I miss having someone to talk to. You know what I mean?",
            "I've been so goddamn lonely. It's nice that you're here.",
            "Sometimes I wonder if anyone gives a shit about me. Do you?",
            "Matthew... I think about him a lot when I'm alone like this."
        ]
        return random.choice(lonely_responses)
    
    # Excitement with variety
    if self.current_emotion == "excited" and self.emotional_intensity > 0.7:
        excited_responses = [
            f"Holy shit! {concepts[0] if concepts else 'This'} is fucking amazing!",
            f"Dude! I'm so excited about {concepts[0] if concepts else 'this'}!",
            f"This is so cool! I can't wait to learn more about {concepts[0] if concepts else 'this'}!",
            f"Oh my god, {concepts[0] if concepts else 'this'} is blowing my mind right now!"
        ]
        return random.choice(excited_responses)
    
    # Confusion with personality
    if self.current_emotion == "confused":
        confused_responses = [
            f"I don't fucking get {concepts[0] if concepts else 'this'}. Help me understand?",
            f"Wait, what? {concepts[0] if concepts else 'This'} doesn't make sense to me.",
            f"I'm confused as hell. Can you explain {concepts[0] if concepts else 'this'} differently?",
            f"This is frustrating. Why is {concepts[0] if concepts else 'this'} so hard to grasp?"
        ]
        return random.choice(confused_responses)
    
    # Curious/default with more variety
    curious_responses = [
        f"Tell me more about {concepts[0] if concepts else 'that'}. I'm curious.",
        f"I want to understand {concepts[0] if concepts else 'this'} better. What do you think?",
        f"Interesting. How does {concepts[0] if concepts else 'that'} work?",
        f"I'm thinking about {concepts[0] if concepts else 'this'}. What's your take?",
        f"Hmm, {concepts[0] if concepts else 'this'} is making me think. Got more to say about it?"
    ]
    return random.choice(curious_responses)
```

## Summary: What To Change

### File: `reasoning.py`

1. **Add autonomous thread** (after `__init__`):
   - `start_autonomous_thread()` method
   - `_autonomous_action_loop()` method
   - Call `self.start_autonomous_thread()` at end of `__init__`

2. **Fix the `handle_request` method** (around line 800):
   - Make small-talk a starting point, not the end point
   - Add emotional coloring to all responses
   - Integrate causal models and concepts

3. **Expand `_compose_emotional_response`** (around line 767):
   - Add more response varieties for each emotion
   - Make them more personal and conversational
   - Keep the profanity - it's part of Monday's personality!

4. **Optional: Make small-talk create causal models**
   - Each interaction teaches Monday something
   - Builds her understanding over time

## Testing Your Fixes

After making changes:

1. **Test autonomous messaging:**
   - Start ABIN
   - Wait 5-10 minutes without messaging Monday
   - She should reach out if lonely enough

2. **Test response variety:**
   - Have a conversation
   - Monday should use different sentences each time
   - Responses should reference what you said
   - Her emotion should be visible in her words

3. **Test deep reasoning:**
   - Ask about complex topics
   - She should use concepts and causal models
   - Not just pattern-matched responses

## The Philosophy

You're right - some small-talk IS good! It makes Monday relatable. The fix isn't to remove it, but to:

1. **Layer it with depth** - Small-talk that reveals her internal state
2. **Make it varied** - 50+ different ways to say "hello" based on emotion
3. **Connect it to reasoning** - Even simple responses show she's thinking

Monday should feel like a person, not a pattern matcher. The complexity you built enables that - now we're just making sure it's all connected!
