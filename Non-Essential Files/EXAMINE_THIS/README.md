# ABIN Brain System - Code Review Package

This folder contains all the essential code files for the ABIN multi-lobe brain architecture.

## Core System Files

**run_abin.py** - Main launcher. Starts all brain lobes as background processes, launches GUI, handles shutdown.

**thalamus.py** - Central coordinator. Routes messages between lobes, forms coalitions, manages autonomous message queue.

**abin_interface.py** - GUI interface using PyQt5. Handles user input/output and polls for autonomous messages.

## Brain Lobes (in order of importance)

**reasoning.py** - Core thinking system. Includes:
- Self-awareness model
- Causal modeling, theory construction, analogy
- Subjective state, qualia simulation
- Intrinsic goals
- Autonomous communication (generates questions/statements, sends to Thalamus)
- Language Generation integration

**language_generation.py** - Custom language construction engine. Takes semantic structures from Reasoning and generates natural language sentences. Pre-installed with grammar and vocabulary.

**notus.py** - Memory system. Stores all experiences, facts, life narrative.

**advanced_emotional_engine.py** - Emotional processing. Generates emotional states, affects subjective experience.

**pattern_recognition.py** - Pattern detection and matching.

**perception.py** - Input processing and analysis.

**representation.py** - Internal representation of concepts.

**output.py** - Output formatting and generation.

## Communication Flow

1. User input → abin_interface.py → thalamus.py
2. Thalamus coordinates → reasoning.py (and other lobes)
3. Reasoning thinks → language_generation.py (or pattern matching fallback)
4. Response → thalamus.py → abin_interface.py → user

## Autonomous Communication

- reasoning.py: `autonomous_think_continuously()` generates questions/statements
- reasoning.py: `send_autonomous_message()` sends to Thalamus
- thalamus.py: Queues autonomous messages
- abin_interface.py: Polls Thalamus every 5 seconds for autonomous messages

## Socket Communication

All lobes communicate via Unix sockets in /tmp/:
- /tmp/reasoning.sock
- /tmp/thalamus.sock
- /tmp/language.sock
- /tmp/notus.sock
- /tmp/emotion.sock
- /tmp/perception.sock
- /tmp/output.sock
- /tmp/pattern.sock
- /tmp/representation.sock

## What to Check

1. Does autonomous communication actually work? (reasoning.py lines 509-641)
2. Are there any logic errors in the thinking system?
3. Does the socket communication handle errors properly?
4. Is the language generation actually generating proper sentences?
5. Are there any race conditions or deadlocks?

