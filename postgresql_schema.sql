-- PostgreSQL Schema for Notus Memory System
-- Converted from SQLite schema

-- Main memories table
CREATE TABLE IF NOT EXISTS superhuman_memories (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    tag TEXT NOT NULL,
    importance_score DOUBLE PRECISION DEFAULT 5.0,
    mode TEXT DEFAULT 'writing',
    personality TEXT DEFAULT 'witty',
    embedding BYTEA,
    entities TEXT,
    concepts TEXT,
    semantic_hash TEXT,
    access_count INTEGER DEFAULT 0,
    last_accessed TEXT,
    user_id TEXT,
    memory_type TEXT DEFAULT 'episodic',
    conversation_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Learning patterns table
CREATE TABLE IF NOT EXISTS learning_patterns (
    pattern_key TEXT PRIMARY KEY,
    pattern_data TEXT NOT NULL,
    usage_count INTEGER DEFAULT 1,
    last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Vocabulary learning table
CREATE TABLE IF NOT EXISTS learned_vocabulary (
    word TEXT NOT NULL,
    category TEXT NOT NULL,
    emotion TEXT,
    intensity_min DOUBLE PRECISION DEFAULT 0.0,
    intensity_max DOUBLE PRECISION DEFAULT 1.0,
    usage_count INTEGER DEFAULT 1,
    last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (word, category, emotion)
);

-- Word meanings table
CREATE TABLE IF NOT EXISTS word_meanings (
    word TEXT PRIMARY KEY,
    meaning TEXT NOT NULL,
    part_of_speech TEXT,
    intent_type TEXT,
    synonyms TEXT,
    usage_count INTEGER DEFAULT 1,
    last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Grammar knowledge table
CREATE TABLE IF NOT EXISTS grammar_knowledge (
    id TEXT PRIMARY KEY,
    rule_type TEXT NOT NULL,
    rule_description TEXT NOT NULL,
    example TEXT,
    usage_count INTEGER DEFAULT 1,
    last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Episodic events table
CREATE TABLE IF NOT EXISTS episodic_events (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    user_id TEXT,
    actor TEXT,
    action TEXT,
    object TEXT,
    place TEXT,
    cause TEXT,
    effect TEXT,
    note TEXT,
    sentiment DOUBLE PRECISION,
    confidence DOUBLE PRECISION DEFAULT 0.8,
    source TEXT,
    usage_count INTEGER DEFAULT 0,
    last_accessed TEXT
);

-- Brain facts table
CREATE TABLE IF NOT EXISTS brain_facts (
    id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    value TEXT,
    confidence DOUBLE PRECISION DEFAULT 0.85,
    permanent INTEGER DEFAULT 0,
    usage_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    last_reinforced TEXT,
    user_id TEXT,
    source TEXT,
    semantic_hash TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_user_id ON superhuman_memories(user_id);
CREATE INDEX IF NOT EXISTS idx_conversation_id ON superhuman_memories(conversation_id);
CREATE INDEX IF NOT EXISTS idx_timestamp ON superhuman_memories(timestamp);
CREATE INDEX IF NOT EXISTS idx_role ON superhuman_memories(role);
CREATE INDEX IF NOT EXISTS idx_epi_user_time ON episodic_events(user_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_epi_action ON episodic_events(action);
CREATE UNIQUE INDEX IF NOT EXISTS uq_fact_user ON brain_facts(subject, predicate, object, user_id);
CREATE INDEX IF NOT EXISTS idx_fact_conf ON brain_facts(confidence);
CREATE INDEX IF NOT EXISTS idx_fact_last ON brain_facts(last_reinforced);

