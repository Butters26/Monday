#!/usr/bin/env python3
"""
Fixed Superhuman Memory System - Actually works with cheap AI
Instead of trying to BE the AI, this helps your cheap AI be smarter
"""

import json
import sqlite3
import time
import uuid
import re
import pickle
import numpy as np
import torch
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Union, Set
from collections import defaultdict, Counter, deque
from dataclasses import dataclass, field
import logging
import os
import threading
import hashlib
from threading import Lock
import heapq
from functools import lru_cache

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
MEMORY_DB_PATH = "superhuman_memory.db"
MAX_CONTEXT_LENGTH = 50000
EMBEDDING_DIM = 768

# Thread safety
DB_LOCK = Lock()

@dataclass
class SuperhumanConfig:
    """Configuration for the superhuman memory system"""
    
    # Semantic similarity settings
    similarity_threshold: float = 0.4  # Lower threshold to catch more context
    min_semantic_score: float = 0.3
    
    # Learning parameters
    learning_rate: float = 0.1
    importance_decay: float = 0.95
    feedback_weight: float = 0.3
    online_learning_rate: float = 0.01
    
    # Memory organization
    episodic_semantic_ratio: float = 0.7
    memory_consolidation_threshold: int = 5
    hierarchical_clustering_depth: int = 3
    
    # Performance settings
    max_cache_size: int = 10000
    batch_process_size: int = 100
    
    # Context generation - FIXED FOR CHEAP AI
    max_context_memories: int = 15  # Good amount for context
    max_context_chars: int = 3000   # Don't overwhelm the cheap AI
    personality_adaptation_rate: float = 0.05
    
    # Advanced retrieval
    attention_heads: int = 4
    reasoning_depth: int = 3
    time_decay_factor: float = 0.1
    
    # AI Prompt Templates - THE FIX
    system_prompt: str = "You are Monday, a helpful and witty AI assistant. Use the context below to inform your responses, but respond naturally in your own voice."
    
    context_template: str = """CONTEXT FROM PREVIOUS CONVERSATIONS:
{context}

ANALYSIS:
{analysis}

USER'S CURRENT MESSAGE: {user_input}

INSTRUCTIONS: Respond as Monday would, taking into account the context above. Be natural, helpful, and remember what you've learned about this user."""

class MemoryType:
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    CONVERSATION = "conversation"

class AdvancedEmbeddingEngine:
    """Simplified but robust embedding engine"""
    
    def __init__(self, config: SuperhumanConfig):
        self.config = config
        self.model = None
        self.tokenizer = None
        self.embedding_cache = {}
        self.cache_lock = Lock()
        self.model_type = 'basic'
        self.personalization_vectors = {}
        self._initialize_model()
        
    def _initialize_model(self):
        """Initialize the best available embedding model"""
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer('all-MiniLM-L6-v2')
            self.model_type = 'sentence_transformer'
            logger.info("✅ Loaded sentence-transformers model")
            return
        except:
            pass
            
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            self.model = TfidfVectorizer(max_features=EMBEDDING_DIM, stop_words='english', ngram_range=(1, 2))
            self.model_type = 'tfidf'
            self._tfidf_fitted = False
            self._tfidf_docs = []
            logger.info("✅ Using TF-IDF model")
            return
        except:
            pass
            
        self.model = None
        self.model_type = 'basic'
        logger.info("⚠️ Using basic word matching")

    def get_embedding(self, text: str, user_id: str = None) -> np.ndarray:
        """Get embedding for text with caching"""
        if not text or not text.strip():
            return np.zeros(EMBEDDING_DIM)
            
        # Simple caching
        cache_key = f"{user_id}:{text}" if user_id else text
        text_hash = hashlib.md5(cache_key.encode('utf-8', errors='ignore')).hexdigest()
        
        with self.cache_lock:
            if text_hash in self.embedding_cache:
                return self.embedding_cache[text_hash]
        
        try:
            if self.model_type == 'sentence_transformer':
                embedding = self.model.encode(text)
                embedding = self._normalize_dimensions(embedding)
            elif self.model_type == 'tfidf':
                embedding = self._get_tfidf_embedding(text)
            else:
                embedding = self._get_basic_embedding(text)
            
            # Cache it
            with self.cache_lock:
                if len(self.embedding_cache) < self.config.max_cache_size:
                    self.embedding_cache[text_hash] = embedding
                    
            return embedding
            
        except Exception as e:
            logger.warning(f"Embedding failed: {e}")
            return self._get_basic_embedding(text)

    def _normalize_dimensions(self, embedding: np.ndarray) -> np.ndarray:
        """Normalize embedding to standard dimensions"""
        if embedding.size == 0:
            return np.zeros(EMBEDDING_DIM)
            
        if embedding.ndim > 1:
            embedding = embedding.flatten()
            
        if embedding.size < EMBEDDING_DIM:
            embedding = np.pad(embedding, (0, EMBEDDING_DIM - embedding.size), 'constant')
        elif embedding.size > EMBEDDING_DIM:
            embedding = embedding[:EMBEDDING_DIM]
            
        return embedding

    def _get_tfidf_embedding(self, text: str) -> np.ndarray:
        """Get TF-IDF embedding"""
        try:
            if not self._tfidf_fitted:
                self._tfidf_docs.append(text)
                if len(self._tfidf_docs) >= 10:
                    self.model.fit(self._tfidf_docs)
                    self._tfidf_fitted = True
            
            if self._tfidf_fitted:
                tfidf_vector = self.model.transform([text]).toarray().flatten()
                return self._normalize_dimensions(tfidf_vector)
            else:
                self._tfidf_docs.append(text)
                return self._get_basic_embedding(text)
                
        except Exception as e:
            return self._get_basic_embedding(text)

    def _get_basic_embedding(self, text: str) -> np.ndarray:
        """Basic word frequency embedding"""
        try:
            words = re.findall(r'\b\w+\b', text.lower())
            word_freq = Counter(words)
            
            embedding = np.zeros(EMBEDDING_DIM)
            for i, (word, freq) in enumerate(word_freq.most_common(min(EMBEDDING_DIM, len(word_freq)))):
                if i < EMBEDDING_DIM:
                    embedding[i] = freq / len(words)
                    
            return embedding
            
        except:
            return np.zeros(EMBEDDING_DIM)

    def calculate_similarity(self, text1: str, text2: str, user_id: str = None) -> float:
        """Calculate similarity between texts"""
        try:
            emb1 = self.get_embedding(text1, user_id)
            emb2 = self.get_embedding(text2, user_id)
            
            dot_product = np.dot(emb1, emb2)
            norm1 = np.linalg.norm(emb1)
            norm2 = np.linalg.norm(emb2)
            
            if norm1 < 1e-10 or norm2 < 1e-10:
                return 0.0
            
            similarity = dot_product / (norm1 * norm2)
            return max(0.0, min(1.0, similarity))
            
        except:
            return 0.0

class NamedEntityRecognition:
    """Simple entity recognition"""
    
    def __init__(self):
        self.model_type = 'basic'
    
    def extract_entities(self, text: str) -> Dict[str, List[str]]:
        """Extract basic entities"""
        if not text or not text.strip():
            return {"PERSON": [], "ORG": [], "LOC": [], "MISC": []}
        
        try:
            entities = {"PERSON": [], "ORG": [], "LOC": [], "MISC": []}
            
            # Extract capitalized phrases
            words = text.split()
            for i, word in enumerate(words):
                if len(word) > 1 and word[0].isupper():
                    entity_parts = [word]
                    j = i + 1
                    while j < len(words) and len(words[j]) > 0 and words[j][0].isupper():
                        entity_parts.append(words[j])
                        j += 1
                    
                    if len(entity_parts) > 0:
                        entity_text = ' '.join(entity_parts)
                        if any(word.lower() in ['inc', 'corp', 'company', 'ltd', 'llc'] for word in entity_parts):
                            entities["ORG"].append(entity_text)
                        elif any(word.lower() in ['street', 'avenue', 'road', 'city', 'state'] for word in entity_parts):
                            entities["LOC"].append(entity_text)
                        else:
                            entities["PERSON"].append(entity_text)
            
            return entities
            
        except Exception as e:
            logger.warning(f"Entity extraction failed: {e}")
            return {"PERSON": [], "ORG": [], "LOC": [], "MISC": []}

class SuperhumanMemorySystem:
    """Fixed memory system that helps your cheap AI instead of replacing it"""
    
    def __init__(self, config: SuperhumanConfig = None, storage_path: str = None):
        self.config = config or SuperhumanConfig()
        self.db_path = storage_path or MEMORY_DB_PATH
        
        # Initialize components
        self.embedding_engine = AdvancedEmbeddingEngine(self.config)
        self.entity_recognition = NamedEntityRecognition()
        
        # Thread safety
        self.memory_cache = {}
        self.cache_lock = Lock()
        self.recent_queries = deque(maxlen=100)
        self.conversation_id = str(uuid.uuid4())
        
        # Initialize database
        self._init_database()
        
        logger.info(f"🧠 Fixed Superhuman Memory System initialized")
    
    def _init_database(self):
        """Initialize database"""
        try:
            with DB_LOCK:
                conn = sqlite3.connect(self.db_path, timeout=30.0)
                cursor = conn.cursor()
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS superhuman_memories (
                        id TEXT PRIMARY KEY,
                        timestamp TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        tag TEXT NOT NULL,
                        importance_score REAL DEFAULT 5.0,
                        mode TEXT DEFAULT 'writing',
                        personality TEXT DEFAULT 'witty',
                        embedding BLOB,
                        entities TEXT,
                        concepts TEXT,
                        semantic_hash TEXT,
                        access_count INTEGER DEFAULT 0,
                        last_accessed TEXT,
                        user_id TEXT,
                        memory_type TEXT DEFAULT 'episodic',
                        conversation_id TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS learning_patterns (
                        pattern_key TEXT PRIMARY KEY,
                        pattern_data TEXT NOT NULL,
                        usage_count INTEGER DEFAULT 1,
                        last_used DATETIME DEFAULT CURRENT_TIMESTAMP,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Create indexes
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_id ON superhuman_memories(user_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_conversation_id ON superhuman_memories(conversation_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON superhuman_memories(timestamp)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_role ON superhuman_memories(role)')
                
                conn.commit()
                conn.close()
                
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
    
    def store_memory(self, role: str, content: str, user_id: str = "default", tag: str = "General", 
                    importance: float = 5.0, mode: str = "writing", memory_type: str = MemoryType.CONVERSATION,
                    personality: str = "witty") -> str:
        """Store a memory"""
        try:
            memory_id = str(uuid.uuid4())
            timestamp = datetime.now().isoformat()
            
            # Generate embedding
            embedding = self.embedding_engine.get_embedding(content, user_id)
            embedding_blob = pickle.dumps(embedding)
            
            # Extract entities
            entities = self.entity_recognition.extract_entities(content)
            entities_json = json.dumps(entities)
            
            # Generate semantic hash
            semantic_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
            
            # Extract concepts
            concepts = self._extract_concepts(content)
            concepts_json = json.dumps(concepts)
            
            with DB_LOCK:
                conn = sqlite3.connect(self.db_path, timeout=30.0)
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO superhuman_memories 
                    (id, timestamp, role, content, tag, importance_score, mode, personality, 
                     embedding, entities, concepts, semantic_hash, user_id, memory_type, conversation_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (memory_id, timestamp, role, content, tag, importance, mode, personality,
                     embedding_blob, entities_json, concepts_json, semantic_hash, user_id, memory_type, self.conversation_id))
                
                conn.commit()
                conn.close()
            
            logger.info(f"💾 Stored memory: {role} - {content[:50]}...")
            return memory_id
            
        except Exception as e:
            logger.error(f"Failed to store memory: {e}")
            return None
    
    def retrieve_memories(self, query: str, user_id: str = "default", limit: int = None) -> List[Dict[str, Any]]:
        """Retrieve relevant memories"""
        try:
            limit = limit or self.config.max_context_memories
            query_embedding = self.embedding_engine.get_embedding(query, user_id)
            
            with DB_LOCK:
                conn = sqlite3.connect(self.db_path, timeout=30.0)
                cursor = conn.cursor()
                
                # Get recent memories
                cursor.execute('''
                    SELECT id, timestamp, role, content, tag, importance_score, mode, personality,
                           embedding, entities, concepts, semantic_hash, access_count, last_accessed,
                           user_id, memory_type, conversation_id
                    FROM superhuman_memories
                    WHERE user_id = ? OR user_id IS NULL
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (user_id, limit * 3))
                
                memories = []
                for row in cursor.fetchall():
                    try:
                        memory_embedding = pickle.loads(row[8]) if row[8] else np.zeros(EMBEDDING_DIM)
                        similarity = self.embedding_engine.calculate_similarity(query, row[3], user_id)
                        
                        if similarity >= self.config.similarity_threshold:
                            memories.append({
                                'id': row[0],
                                'timestamp': row[1],
                                'role': row[2],
                                'content': row[3],
                                'tag': row[4],
                                'importance_score': row[5],
                                'mode': row[6],
                                'personality': row[7],
                                'entities': json.loads(row[9]) if row[9] else {},
                                'concepts': json.loads(row[10]) if row[10] else [],
                                'semantic_hash': row[11],
                                'access_count': row[12],
                                'last_accessed': row[13],
                                'user_id': row[14],
                                'memory_type': row[15],
                                'conversation_id': row[16],
                                'similarity': similarity
                            })
                    except Exception as e:
                        continue
                
                conn.close()
            
            # Sort by similarity and recency
            memories.sort(key=lambda x: (x['similarity'], x['timestamp']), reverse=True)
            
            # Update access counts
            if memories:
                memory_ids = [m['id'] for m in memories[:limit]]
                self._update_access_counts(memory_ids)
            
            return memories[:limit]
            
        except Exception as e:
            logger.error(f"Failed to retrieve memories: {e}")
            return []
    
    def _extract_concepts(self, content: str) -> List[str]:
        """Extract key concepts"""
        try:
            words = re.findall(r'\b\w+\b', content.lower())
            word_freq = Counter(words)
            
            stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'i', 'you', 'he', 'she', 'it', 'we', 'they'}
            concepts = [word for word, freq in word_freq.most_common(10) 
                       if word not in stop_words and len(word) > 3]
            
            return concepts[:5]
            
        except Exception as e:
            logger.warning(f"Concept extraction failed: {e}")
            return []
    
    def _update_access_counts(self, memory_ids: List[str]):
        """Update access counts"""
        try:
            with DB_LOCK:
                conn = sqlite3.connect(self.db_path, timeout=30.0)
                cursor = conn.cursor()
                
                for memory_id in memory_ids:
                    cursor.execute('''
                        UPDATE superhuman_memories 
                        SET access_count = access_count + 1, last_accessed = ?
                        WHERE id = ?
                    ''', (datetime.now().isoformat(), memory_id))
                
                conn.commit()
                conn.close()
                
        except Exception as e:
            logger.warning(f"Failed to update access counts: {e}")

    # THE MAIN FIX: Generate smart prompts for your cheap AI instead of trying to be the AI
    def generate_smart_prompt_for_ai(self, user_input: str, user_id: str = "default") -> str:
        """
        THIS IS THE KEY METHOD - Generate a smart prompt for your cheap AI
        Instead of trying to generate the response, we make the cheap AI smarter
        NOW WITH YOUR LEARNING DATA INTEGRATION
        """
        print(f"🧠 Generating smart prompt for: '{user_input}'")
        
        try:
            # Step 1: Store the user's input
            self.store_memory("user", user_input, user_id)
            
            # Step 2: Get relevant memories
            relevant_memories = self.retrieve_memories(user_input, user_id)
            print(f"📚 Found {len(relevant_memories)} relevant memories")
            
            # Step 3: Analyze the input intelligently
            analysis = self._analyze_input_for_ai(user_input, relevant_memories)
            print(f"🔍 Analysis: {analysis}")
            
            # Step 4: Build context from memories
            context = self._build_context_for_ai(relevant_memories, user_input)
            print(f"📝 Context built: {len(context)} chars")
            
            # Step 5: Add your learning data integration
            learning_context = self._get_learning_context(user_input)
            print(f"🧠 Learning context: {len(learning_context)} chars")
            
            # Step 6: Format the smart prompt for your cheap AI WITH LEARNING
            smart_prompt = self.config.context_template.format(
                context=context,
                analysis=analysis,
                user_input=user_input
            )
            
            # Add your learning data to the prompt
            enhanced_prompt = f"""{smart_prompt}

YOUR LEARNING DATA:
{learning_context}

Use this learning data to respond more intelligently based on what you've learned."""
            
            print(f"✨ Enhanced smart prompt generated ({len(enhanced_prompt)} chars)")
            return enhanced_prompt
            
        except Exception as e:
            print(f"❌ Error generating smart prompt: {e}")
            import traceback
            traceback.print_exc()
            return f"User said: {user_input}\n\nPlease respond naturally as Monday."

    def _analyze_input_for_ai(self, user_input: str, relevant_memories: List[Dict]) -> str:
        """Analyze input and create guidance for the AI"""
        input_lower = user_input.lower().strip()
        
        analysis_parts = []
        
        # Mental health crisis detection
        if any(phrase in input_lower for phrase in ['kill myself', 'want to die', 'suicide', 'end it all']):
            analysis_parts.append("🚨 MENTAL HEALTH CRISIS - Respond with empathy and support")
        
        # Writing content detection
        elif any(word in input_lower for word in ['book', 'story', 'chapter', 'novel', 'write', 'writing']):
            if 'quarter' in input_lower:
                analysis_parts.append("📚 User is discussing writing progress (quarter of a book)")
            elif 'chapter' in input_lower:
                analysis_parts.append("📚 User is working on specific chapters")
            else:
                analysis_parts.append("📚 User is discussing writing/creative work")
        
        # Emotional content detection
        elif any(word in input_lower for word in ['feel', 'shitty', 'destroyed', 'burnt out', 'angry', 'upset']):
            analysis_parts.append("💭 User is expressing emotions - respond with empathy")
        
        # Work issues
        elif any(word in input_lower for word in ['job', 'work', 'boss', 'rude', 'coworker']):
            analysis_parts.append("💼 User has work-related concerns")
        
        # User asking Monday to choose
        elif any(phrase in input_lower for phrase in ['you pick', 'you choose', 'what do you want']):
            analysis_parts.append("🎯 User wants Monday to decide/choose something")
        
        # Greetings
        elif any(word in input_lower for word in ['hello', 'hi', 'hey']):
            analysis_parts.append("👋 Greeting - respond warmly")
        
        # Follow-up questions
        elif any(phrase in input_lower for phrase in ['about what', 'what do you mean', 'did you read']):
            analysis_parts.append("❓ Follow-up question - user needs clarification")
        
        # General
        else:
            analysis_parts.append("💬 General conversation")
        
        # Add context from memories
        if relevant_memories:
            recent_topics = []
            for memory in relevant_memories[-5:]:
                content = memory.get('content', '').lower()
                if any(word in content for word in ['book', 'story', 'write']):
                    recent_topics.append('writing')
                elif any(word in content for word in ['feel', 'sad', 'angry']):
                    recent_topics.append('emotions')
                elif any(word in content for word in ['work', 'job', 'boss']):
                    recent_topics.append('work')
            
            if recent_topics:
                analysis_parts.append(f"Recent topics: {', '.join(set(recent_topics))}")
        
        return " | ".join(analysis_parts) if analysis_parts else "No specific context detected"

    def _build_context_for_ai(self, relevant_memories: List[Dict], current_input: str) -> str:
        """Build context string from memories for the AI"""
        if not relevant_memories:
            return "No previous conversation context available."
        
        context_parts = []
        total_chars = 0
        max_chars = self.config.max_context_chars
        
        # Group memories by conversation flow
        recent_memories = relevant_memories[-10:]  # Most recent
        
        for memory in recent_memories:
            if total_chars >= max_chars:
                break
            
            # Format memory entry
            timestamp = memory.get('timestamp', '')
            role = memory.get('role', 'unknown')
            content = memory.get('content', '')
            
            # Create readable timestamp
            try:
                dt = datetime.fromisoformat(timestamp)
                time_str = dt.strftime("%m/%d %H:%M")
            except:
                time_str = "recent"
            
            # Format the memory
            if role == 'user':
                memory_line = f"[{time_str}] User: {content}"
            elif role == 'monday':
                memory_line = f"[{time_str}] Monday: {content}"
            else:
                memory_line = f"[{time_str}] {role}: {content}"
            
            if total_chars + len(memory_line) <= max_chars:
                context_parts.append(memory_line)
                total_chars += len(memory_line)
        
        if not context_parts:
            return "No relevant conversation history found."
        
        return "\n".join(context_parts)
    
    def _get_learning_context(self, user_input: str) -> str:
        """Get learning context from your learning data files"""
        try:
            import json
            import os
            
            learning_context_parts = []
            
            # Load your learning data files
            data_models_path = "data_models"
            learning_files = {
                'learning_data': 'monday_learning_data.json',
                'active_learning': 'monday_active_learning.json',
                'natural_learning': 'monday_natural_learning.json',
                'self_learning': 'monday_self_learning.json'
            }
            
            # Check conversation patterns
            try:
                with open(os.path.join(data_models_path, learning_files['learning_data']), 'r') as f:
                    learning_data = json.load(f)
                    patterns = learning_data.get('conversation_patterns', {})
                    
                    words = user_input.lower().split()
                    pattern_matches = []
                    for word in words:
                        if word in patterns:
                            pattern_matches.append(f"'{word}' appears {patterns[word]} times in conversations")
                    
                    if pattern_matches:
                        learning_context_parts.append(f"CONVERSATION PATTERNS: {'; '.join(pattern_matches)}")
            except:
                pass
            
            # Check learned phrases
            try:
                with open(os.path.join(data_models_path, learning_files['natural_learning']), 'r') as f:
                    natural_data = json.load(f)
                    learned_phrases = natural_data.get('learned_phrases', {})
                    
                    phrase_matches = []
                    for phrase, count in learned_phrases.items():
                        if phrase in user_input.lower():
                            phrase_matches.append(f"'{phrase}' learned {count} times")
                    
                    if phrase_matches:
                        learning_context_parts.append(f"LEARNED PHRASES: {'; '.join(phrase_matches)}")
            except:
                pass
            
            # Check response quality data
            try:
                with open(os.path.join(data_models_path, learning_files['active_learning']), 'r') as f:
                    active_data = json.load(f)
                    response_quality = active_data.get('response_quality', {})
                    
                    # Find best responses for similar input types
                    input_type = self._classify_input_type(user_input)
                    if input_type in response_quality:
                        quality_data = response_quality[input_type]
                        if quality_data.get('best_response'):
                            learning_context_parts.append(f"BEST RESPONSE FOR {input_type.upper()}: {quality_data['best_response']}")
            except:
                pass
            
            return "\n".join(learning_context_parts) if learning_context_parts else "No specific learning context found."
            
        except Exception as e:
            print(f"⚠️ Learning context error: {e}")
            return "Learning data not available."
    
    def _classify_input_type(self, user_input: str) -> str:
        """Classify input type for learning"""
        input_lower = user_input.lower()
        
        if any(word in input_lower for word in ['hello', 'hi', 'hey']):
            return 'greeting'
        elif '?' in user_input:
            return 'question'
        elif any(word in input_lower for word in ['tell', 'say', 'do']):
            return 'instruction'
        else:
            return 'statement'

    def store_ai_response(self, ai_response: str, user_id: str = "default") -> str:
        """Store the AI's response for future context"""
        return self.store_memory("monday", ai_response, user_id)

    def start_new_conversation(self) -> str:
        """Start a new conversation session"""
        self.conversation_id = str(uuid.uuid4())
        logger.info(f"🆕 Started new conversation: {self.conversation_id}")
        return self.conversation_id

    def get_conversation_summary(self, user_id: str = "default", limit: int = 10) -> str:
        """Get recent conversation summary"""
        try:
            with DB_LOCK:
                conn = sqlite3.connect(self.db_path, timeout=30.0)
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT content, role, timestamp FROM superhuman_memories 
                    WHERE user_id = ? AND memory_type = ?
                    ORDER BY timestamp DESC 
                    LIMIT ?
                ''', (user_id, MemoryType.CONVERSATION, limit))
                
                rows = cursor.fetchall()
                conn.close()
            
            if not rows:
                return "No recent conversation history."
            
            summary_parts = []
            for content, role, timestamp in reversed(rows):
                try:
                    dt = datetime.fromisoformat(timestamp)
                    time_str = dt.strftime("%H:%M")
                except:
                    time_str = "??"
                summary_parts.append(f"{time_str} [{role}]: {content}")
            
            return "\n".join(summary_parts)
            
        except Exception as e:
            logger.error(f"Failed to get conversation summary: {e}")
            return "Error retrieving conversation history."

# Create the EnhancedMondayMemorySystem class for compatibility
class EnhancedMondayMemorySystem(SuperhumanMemorySystem):
    """Enhanced Monday Memory System - compatible interface"""
    
    def __init__(self, config: SuperhumanConfig = None, storage_path: str = None):
        super().__init__(config, storage_path)
        logger.info("🚀 Enhanced Monday Memory System initialized")
    
    def add_memory(self, role: str, content: str, tag: str = "General", 
                  importance: int = 5, mode: str = "writing", personality: str = "witty"):
        """Compatible interface for existing code"""
        return self.store_memory(role, content, tag=tag, importance=float(importance), 
                                mode=mode, personality=personality)
    
    def classify_emotion(self, text: str) -> int:
        """Compatible interface for emotion classification"""
        text_lower = text.lower()
        if any(word in text_lower for word in ['fuck', 'stupid', 'broken', 'hate', 'angry', 'destroyed']):
            return 1  # Negative
        elif any(word in text_lower for word in ['hello', 'hi', 'hey', 'good', 'great']):
            return 5  # Positive
        else:
            return 3  # Neutral
    
    def get_relevant_memories(self, query: str, limit: int = 10) -> List[Dict]:
        """Compatible interface for existing code"""
        memories = self.retrieve_memories(query, limit=limit)
        return [{
            'timestamp': m['timestamp'],
            'role': m['role'],
            'content': m['content'],
            'tag': m['tag'],
            'importance_score': m['importance_score']
        } for m in memories]

    # THE KEY METHOD YOUR NOTUS PROGRAM SHOULD USE
    def generate_response(self, user_input: str, relevant_memories: List[Dict] = None) -> str:
        """
        FIXED METHOD: Instead of generating a response, this generates a smart prompt for your cheap AI
        Your Notus program should send this prompt to your cheap AI, not use it as the final response
        """
        print(f"🧠 Memory system: Generating PROMPT for cheap AI, not final response")
        
        # Generate the smart prompt that will make your cheap AI way smarter
        smart_prompt = self.generate_smart_prompt_for_ai(user_input)
        
        # THIS IS WHAT YOUR NOTUS PROGRAM SHOULD SEND TO YOUR CHEAP AI
        return smart_prompt

# Export the main classes
__all__ = [
    'SuperhumanConfig',
    'AdvancedEmbeddingEngine',
    'MemoryType',
    'SuperhumanMemorySystem',
    'EnhancedMondayMemorySystem',
    'DB_LOCK',
    'MEMORY_DB_PATH',
    'logger',
    'MAX_CONTEXT_LENGTH'
]

# Example of how to use this with your cheap AI
if __name__ == "__main__":
    print("🧠 Fixed Superhuman Memory System Demo")
    print("=" * 60)
    
    # Initialize the memory system
    memory_system = EnhancedMondayMemorySystem()
    
    # Example conversation flow
    user_inputs = [
        "Hello Monday, I'm working on a book",
        "I've written about a quarter of it so far",
        "I'm feeling stuck on chapter 3"
    ]
    
    for user_input in user_inputs:
        print(f"\n👤 User: {user_input}")
        
        # Get smart prompt for your cheap AI
        smart_prompt = memory_system.generate_smart_prompt_for_ai(user_input)
        
        print(f"\n🤖 SMART PROMPT FOR YOUR CHEAP AI:")
        print("-" * 50)
        print(smart_prompt)
        print("-" * 50)
        
        # NOW YOU WOULD SEND THIS PROMPT TO YOUR CHEAP AI
        # cheap_ai_response = your_cheap_ai.generate(smart_prompt)
        
        # Simulate what your cheap AI would respond with this smart prompt
        if "quarter of it" in user_input:
            simulated_response = "That's awesome progress! A quarter of a book is a real accomplishment. What's been the most challenging part so far? Are you finding your voice as you write?"
        elif "stuck on chapter 3" in user_input:
            simulated_response = "Chapter 3 can be tricky - that's often where the real story momentum needs to kick in. What's happening in this chapter? Is it a pacing issue or are you not sure where to take the plot?"
        else:
            simulated_response = "That's exciting! I love talking about writing projects. What genre are you working in? What's your story about?"
        
        print(f"🤖 Your Cheap AI Response (with smart prompt): {simulated_response}")
        
        # Store the AI's response for future context
        memory_system.store_ai_response(simulated_response)
    
    print(f"\n📊 Conversation Summary:")
    print(memory_system.get_conversation_summary())
    
    print(f"\n💡 HOW TO INTEGRATE WITH YOUR NOTUS PROGRAM:")
    print("=" * 60)
    print("1. Replace the old generate_response() call with generate_smart_prompt_for_ai()")
    print("2. Send that prompt to your cheap AI instead of using it as the final response")
    print("3. Store the cheap AI's response using store_ai_response()")
    print("4. Your cheap AI will now be WAY smarter because it has proper context!")
    print("\nExample integration:")
    print("user_input = 'Hello'")
    print("smart_prompt = memory_system.generate_smart_prompt_for_ai(user_input)")
    print("ai_response = your_cheap_ai.generate(smart_prompt)  # Send prompt to your AI")
    print("memory_system.store_ai_response(ai_response)  # Store the response") 