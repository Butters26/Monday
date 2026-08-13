-- Notus PostgreSQL + pgvector schema.
-- Apply with: psql "$MONDAY_NOTUS_DSN" -f postgresql_schema.sql

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS notus_schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS conversation_turns (
    id UUID PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    conversation_id UUID NOT NULL REFERENCES conversations(id),
    user_id TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'general',
    user_text TEXT NOT NULL CHECK (length(trim(user_text)) > 0),
    assistant_text TEXT,
    turn_state TEXT NOT NULL CHECK (turn_state IN ('complete', 'legacy_user_only')),
    importance REAL NOT NULL DEFAULT 0.5 CHECK (importance >= 0 AND importance <= 1),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    access_count INTEGER NOT NULL DEFAULT 0,
    last_accessed_at TIMESTAMPTZ,
    extraction_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (extraction_status IN ('pending', 'complete', 'failed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS conversation_turns_user_scope_created_idx
    ON conversation_turns (user_id, scope, created_at DESC);
CREATE INDEX IF NOT EXISTS conversation_turns_conversation_created_idx
    ON conversation_turns (conversation_id, created_at DESC);
CREATE INDEX IF NOT EXISTS conversation_turns_fts_idx
    ON conversation_turns USING GIN (
        to_tsvector('simple', user_text || ' ' || COALESCE(assistant_text, ''))
    );

CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL,
    conversation_id UUID REFERENCES conversations(id),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'fact', 'note', 'system')),
    memory_type TEXT NOT NULL DEFAULT 'conversation',
    content TEXT NOT NULL CHECK (length(trim(content)) > 0),
    importance REAL NOT NULL DEFAULT 0.5 CHECK (importance >= 0 AND importance <= 1),
    source TEXT NOT NULL DEFAULT 'conversation',
    tags TEXT[] NOT NULL DEFAULT '{}',
    entities JSONB NOT NULL DEFAULT '[]'::jsonb,
    concepts JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding vector(384),
    embedding_model TEXT,
    access_count INTEGER NOT NULL DEFAULT 0,
    last_accessed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS memories_user_conversation_created_idx
    ON memories (user_id, conversation_id, created_at DESC)
    WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS memories_user_created_idx
    ON memories (user_id, created_at DESC)
    WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS memories_fts_idx
    ON memories USING GIN (to_tsvector('simple', content))
    WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS memories_embedding_idx
    ON memories USING hnsw (embedding vector_cosine_ops)
    WHERE embedding IS NOT NULL AND deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS facts (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    value TEXT,
    confidence REAL NOT NULL DEFAULT 0.8 CHECK (confidence >= 0 AND confidence <= 1),
    scope TEXT NOT NULL DEFAULT 'general',
    status TEXT NOT NULL DEFAULT 'candidate'
        CHECK (status IN ('candidate', 'confirmed', 'superseded', 'rejected')),
    permanent BOOLEAN NOT NULL DEFAULT FALSE,
    source_turn_id UUID REFERENCES conversation_turns(id),
    source_memory_id UUID REFERENCES memories(id),
    source_role TEXT NOT NULL DEFAULT 'user',
    supersedes_fact_id UUID REFERENCES facts(id),
    source TEXT NOT NULL,
    reinforcement_count INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_reinforced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    invalidated_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS events (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'general',
    status TEXT NOT NULL DEFAULT 'candidate'
        CHECK (status IN ('candidate', 'confirmed', 'rejected')),
    source_turn_id UUID REFERENCES conversation_turns(id),
    source_memory_id UUID REFERENCES memories(id),
    actor TEXT,
    action TEXT,
    object TEXT,
    place TEXT,
    cause TEXT,
    effect TEXT,
    sentiment REAL,
    confidence REAL NOT NULL DEFAULT 0.7 CHECK (confidence >= 0 AND confidence <= 1),
    occurred_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS vocabulary (
    user_id TEXT NOT NULL,
    word TEXT NOT NULL,
    category TEXT NOT NULL,
    emotion TEXT,
    intensity_min REAL,
    intensity_max REAL,
    usage_count INTEGER NOT NULL DEFAULT 1,
    last_used_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, word, category, emotion)
);

CREATE TABLE IF NOT EXISTS word_meanings (
    word TEXT PRIMARY KEY,
    meaning TEXT NOT NULL,
    part_of_speech TEXT,
    intent_type TEXT,
    synonyms TEXT[] NOT NULL DEFAULT '{}',
    usage_count INTEGER NOT NULL DEFAULT 1,
    last_used_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS grammar_knowledge (
    id UUID PRIMARY KEY,
    rule_type TEXT NOT NULL,
    rule_description TEXT NOT NULL,
    example TEXT,
    usage_count INTEGER NOT NULL DEFAULT 1,
    last_used_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS learning_patterns (
    user_id TEXT NOT NULL,
    pattern_key TEXT NOT NULL,
    pattern_data JSONB NOT NULL,
    usage_count INTEGER NOT NULL DEFAULT 1,
    last_used_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, pattern_key)
);

CREATE TABLE IF NOT EXISTS pattern_evidence (
    pattern_user_id TEXT NOT NULL,
    pattern_key TEXT NOT NULL,
    turn_id UUID NOT NULL REFERENCES conversation_turns(id),
    PRIMARY KEY (pattern_user_id, pattern_key, turn_id)
);

ALTER TABLE conversations ADD COLUMN IF NOT EXISTS scope TEXT NOT NULL DEFAULT 'general';
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE memories ADD COLUMN IF NOT EXISTS scope TEXT NOT NULL DEFAULT 'general';
ALTER TABLE memories ADD COLUMN IF NOT EXISTS legacy_turn_id UUID;
ALTER TABLE facts ADD COLUMN IF NOT EXISTS scope TEXT NOT NULL DEFAULT 'general';
ALTER TABLE facts ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'candidate';
ALTER TABLE facts ADD COLUMN IF NOT EXISTS source_turn_id UUID;
ALTER TABLE facts ADD COLUMN IF NOT EXISTS source_role TEXT NOT NULL DEFAULT 'user';
ALTER TABLE facts ADD COLUMN IF NOT EXISTS supersedes_fact_id UUID;
ALTER TABLE events ADD COLUMN IF NOT EXISTS scope TEXT NOT NULL DEFAULT 'general';
ALTER TABLE events ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'candidate';
ALTER TABLE events ADD COLUMN IF NOT EXISTS source_turn_id UUID;
CREATE INDEX IF NOT EXISTS facts_scoped_lookup_idx
    ON facts (user_id, scope, subject, predicate, last_reinforced_at DESC)
    WHERE invalidated_at IS NULL AND status = 'confirmed';
CREATE INDEX IF NOT EXISTS events_scoped_created_idx
    ON events (user_id, scope, created_at DESC);
ALTER TABLE facts DROP CONSTRAINT IF EXISTS facts_user_id_subject_predicate_object_key;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'facts_user_scope_subject_predicate_object_key'
    ) THEN
        ALTER TABLE facts ADD CONSTRAINT facts_user_scope_subject_predicate_object_key
            UNIQUE (user_id, scope, subject, predicate, object);
    END IF;
END $$;
