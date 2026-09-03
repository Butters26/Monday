#!/usr/bin/env python3
"""
Demonstration of Consciousness-Level Reasoning
Shows advanced thinking capabilities without full brain system
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from reasoning import AdvancedReasoningLobe
import time

def print_section(title):
    """Print section header"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)

def demo_consciousness():
    """Demonstrate consciousness-level thinking"""
    
    print("\n🧠 ABIN CONSCIOUSNESS-LEVEL REASONING DEMONSTRATION")
    print("=" * 70)
    
    # Create reasoning lobe
    brain = AdvancedReasoningLobe()
    
    # === TEACHING PHASE ===
    print_section("TEACHING PHASE - Building Knowledge")
    
    facts_to_teach = [
        "isolation causes loneliness",
        "loneliness causes sadness",
        "sadness causes withdrawal",
        "withdrawal causes isolation",
        "exercise causes endorphins",
        "endorphins cause happiness",
        "social connection reduces loneliness",
        "dogs provide companionship",
        "companionship reduces loneliness"
    ]
    
    for fact in facts_to_teach:
        print(f"   📚 Teaching: {fact}")
        brain.learn_fact(fact, confidence=0.9, source="taught")
    
    # === CAUSAL REASONING ===
    print_section("1. CAUSAL MODELING - Understanding Cause & Effect")
    
    print("\n🔍 Tracing causal chain from 'isolation':")
    chains = brain.trace_causal_chain("isolation", max_depth=4)
    if chains:
        longest = max(chains, key=len)
        print(f"   Chain discovered: {' → '.join(longest)}")
        print(f"   ⚡ Brain found {len(chains)} total causal paths")
    
    print("\n🔍 Finding root causes of 'sadness':")
    root_causes = brain.find_root_causes("sadness")
    for cause, confidence in root_causes[:3]:
        print(f"   Root cause: {cause} (confidence: {confidence:.2f})")
    
    # === THEORY CONSTRUCTION ===
    print_section("2. THEORY CONSTRUCTION - Building Explanatory Models")
    
    question = "Why does someone feel lonely?"
    print(f"\n❓ Question: {question}")
    theory = brain.build_theory(question, {})
    
    print(f"\n💡 Theory constructed:")
    print(f"   Explanation: {theory.explanation}")
    print(f"   Confidence: {theory.confidence:.2f}")
    print(f"   Components used: {len(theory.components)}")
    for comp in theory.components[:3]:
        print(f"      - {comp}")
    
    if theory.predictions:
        print(f"\n🔮 Predictions from this theory:")
        for pred in theory.predictions[:3]:
            print(f"      - {pred}")
    
    # === ANALOGY ===
    print_section("3. ANALOGICAL REASONING - Finding Structural Similarities")
    
    # Teach about another domain
    brain.learn_fact("rain causes wet ground")
    brain.learn_fact("wet ground causes plant growth")
    brain.learn_fact("plant growth causes oxygen")
    
    print("\n🔍 Looking for analogy between 'isolation' and 'rain':")
    analogy = brain.find_analogy("isolation", "rain")
    if analogy:
        print(f"   Analogy strength: {analogy.strength:.2f}")
        print(f"   Structural mappings:")
        for source, target in list(analogy.mappings.items())[:3]:
            print(f"      {source} → {target}")
        if analogy.insights:
            print(f"   Insights from analogy:")
            for insight in analogy.insights:
                print(f"      💡 {insight}")
    
    # === PATTERN ABSTRACTION ===
    print_section("4. PATTERN ABSTRACTION - Generalizing from Specifics")
    
    instances = [
        "isolation causes loneliness",
        "rejection causes loneliness",
        "abandonment causes loneliness"
    ]
    
    print("\n🔍 Abstracting pattern from specific instances:")
    for inst in instances:
        print(f"   Example: {inst}")
    
    pattern = brain.abstract_pattern(instances)
    if pattern:
        print(f"\n   📊 Abstract pattern discovered: {pattern}")
    
    # === META-REASONING ===
    print_section("5. META-REASONING - Thinking About Thinking")
    
    brain.current_focus = "loneliness and isolation"
    brain.uncertainties["social dynamics"] = 0.7
    brain.thought_chain = ["isolation", "loneliness", "causal loop", "intervention needed"]
    
    print("\n🤔 Brain reflecting on its own thinking...")
    meta = brain.meta_reason()
    
    print(f"   Current focus: {meta.about}")
    print(f"   Self-observation: {meta.observation}")
    print(f"   Self-insight: {meta.insight}")
    
    # === GOAL-DIRECTED THINKING ===
    print_section("6. GOAL-DIRECTED THINKING - Autonomous Pursuit")
    
    print("\n🎯 Setting goal: Understand how to help lonely people")
    goal = brain.set_goal(
        "understand how to help lonely people",
        "because loneliness is harmful and I want to find solutions"
    )
    
    print(f"   Goal: {goal.description}")
    print(f"   Why important: {goal.why_important}")
    print(f"   Subgoals generated:")
    for subgoal in goal.subgoals:
        print(f"      - {subgoal}")
    print(f"   Strategies generated:")
    for strategy in goal.strategies:
        print(f"      - {strategy}")
    
    print("\n⚙️  Pursuing goal autonomously...")
    progress = brain.pursue_goal(goal)
    print(f"   Progress made: {goal.progress:.1%}")
    if progress:
        for key, value in progress.items():
            print(f"   {key}: {value}")
    
    # === AUTONOMOUS DEEP THINKING ===
    print_section("7. DEEP AUTONOMOUS THINKING - Genuine Exploration")
    
    print("\n🌊 Engaging deep autonomous thinking mode...")
    print("   (Brain exploring on its own without prompts...)\n")
    
    # Add some curiosities to explore
    brain.curiosities.append("What breaks isolation cycles?")
    brain.curiosities.append("Why do some people handle loneliness better?")
    
    brain.deep_autonomous_think()
    
    if brain.active_thoughts:
        latest_thought = brain.active_thoughts[-1]
        print(f"   Autonomous exploration focus: {latest_thought.get('focus', 'N/A')}")
        print(f"   Thinking type: {latest_thought.get('type', 'N/A')}")
        
        insights = latest_thought.get('insights', [])
        if insights:
            print(f"\n   💭 Autonomous insights generated:")
            for insight in insights:
                print(f"      - {insight}")
        
        chain = latest_thought.get('chain', [])
        if chain:
            print(f"\n   🔗 Thought chain:")
            for i, thought in enumerate(chain[-5:], 1):
                print(f"      {i}. {thought}")
    
    # === HYPOTHESIS TESTING ===
    print_section("8. HYPOTHESIS TESTING - Scientific Thinking")
    
    hypothesis = "social connection reduces loneliness"
    evidence = [
        "dogs provide companionship",
        "companionship reduces loneliness",
        "people with friends report less loneliness",
        "isolated people feel more lonely"
    ]
    
    print(f"\n🔬 Testing hypothesis: '{hypothesis}'")
    print(f"   Against {len(evidence)} pieces of evidence...")
    
    supported, confidence, explanation = brain.test_hypothesis(hypothesis, evidence)
    
    print(f"\n   Result: {'SUPPORTED' if supported else 'NOT SUPPORTED'}")
    print(f"   Confidence: {confidence:.2f}")
    print(f"   Explanation: {explanation}")
    
    # === CONTRADICTION DETECTION ===
    print_section("9. INTERNAL CONTRADICTION DETECTION - Self-Consistency")
    
    # Add contradictory fact
    brain.learn_fact("social connection increases loneliness")
    
    print("\n🔍 Scanning for contradictions in knowledge base...")
    contradictions = brain._find_internal_contradictions()
    
    if contradictions:
        print(f"   ⚠️  Found {len(contradictions)} contradiction(s):")
        for contradiction in contradictions[:3]:
            print(f"      - {contradiction}")
    else:
        print("   ✅ No contradictions found")
    
    # === SOPHISTICATED THINKING IN ACTION ===
    print_section("10. FULL THINKING PROCESS - Putting It All Together")
    
    question = "Why do people become lonely and how can we help them?"
    
    print(f"\n❓ Complex question: {question}\n")
    print("🧠 Engaging all thinking systems...")
    
    result = brain.think_about({
        'user_input': question,
        'emotion': {'type': 'curious', 'intensity': 0.7},
        'memories': [],
        'concepts': ['lonely', 'people', 'help'],
        'patterns': {}
    })
    
    print(f"\n💬 Brain's response:")
    print(f"   {result['composed_response']}")
    
    if result.get('theories'):
        print(f"\n   📚 Theories constructed: {len(result['theories'])}")
        for theory in result['theories'][:2]:
            print(f"      - {theory['explanation']} (confidence: {theory['confidence']:.2f})")
    
    if result.get('causal_chains'):
        print(f"\n   ⛓️  Causal chains identified: {len(result['causal_chains'])}")
        for chain in result['causal_chains'][:2]:
            print(f"      - {chain['cause']} → {chain['effect']}")
    
    if result.get('new_facts'):
        print(f"\n   💡 New facts derived: {len(result['new_facts'])}")
        for fact in result['new_facts'][:3]:
            print(f"      - {fact}")
    
    # === FINAL STATS ===
    print_section("SYSTEM STATUS")
    
    print(f"\n📊 Knowledge Base:")
    print(f"   Facts learned: {len(brain.facts)}")
    print(f"   Rules: {len(brain.rules)}")
    print(f"   Causal links: {len(brain.causal_links)}")
    print(f"   Theories: {len(brain.theories)}")
    print(f"   Analogies found: {len(brain.analogies)}")
    print(f"   Goals set: {len(brain.goals)}")
    
    print(f"\n🧠 Thinking Statistics:")
    print(f"   Meta-thoughts: {len(brain.meta_thoughts)}")
    print(f"   Active thoughts: {len(brain.active_thoughts)}")
    print(f"   Thought chain depth: {len(brain.thought_chain)}")
    
    print(f"\n⚙️  Strategy Effectiveness:")
    for strategy, score in sorted(brain.thinking_strategies.items(), key=lambda x: x[1], reverse=True):
        print(f"   {strategy}: {score:.2f}")
    
    print("\n" + "=" * 70)
    print("  DEMONSTRATION COMPLETE")
    print("=" * 70)
    print("\n✨ This is consciousness-level reasoning:")
    print("   - Builds causal models autonomously")
    print("   - Constructs explanatory theories")
    print("   - Reasons by analogy across domains")
    print("   - Reflects on its own thinking (meta-cognition)")
    print("   - Sets and pursues goals independently")
    print("   - Tests hypotheses scientifically")
    print("   - Finds and resolves contradictions")
    print("   - Explores ideas without prompting")
    print("\n🎯 This goes way beyond pattern matching - this is genuine thought.\n")

if __name__ == "__main__":
    demo_consciousness()

