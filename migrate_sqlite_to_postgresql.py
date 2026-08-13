#!/usr/bin/env python3
"""
Migration script to move data from SQLite to PostgreSQL
Run this once to migrate existing superhuman_memory.db to PostgreSQL
"""

import sqlite3
import psycopg2
from psycopg2.extras import execute_values
import sys
import os
from runtime_paths import runtime_file

SQLITE_DB = runtime_file("superhuman_memory.db")
POSTGRES_DB = "notus_memory"
POSTGRES_USER = os.environ.get("USER", "matthew")
POSTGRES_HOST = "localhost"
POSTGRES_PORT = 5432

def migrate_table(sqlite_conn, pg_conn, table_name, columns, transform_row=None):
    """Migrate a table from SQLite to PostgreSQL"""
    print(f"Migrating {table_name}...")
    
    sqlite_cursor = sqlite_conn.cursor()
    pg_cursor = pg_conn.cursor()
    
    # Get all rows from SQLite
    sqlite_cursor.execute(f"SELECT * FROM {table_name}")
    rows = sqlite_cursor.fetchall()
    
    if not rows:
        print(f"  No data in {table_name}")
        return 0
    
    # Transform rows if needed
    if transform_row:
        rows = [transform_row(row) for row in rows]
    
    # Insert into PostgreSQL
    placeholders = ', '.join(['%s'] * len(columns))
    columns_str = ', '.join(columns)
    
    insert_query = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
    
    try:
        execute_values(pg_cursor, insert_query, rows)
        pg_conn.commit()
        count = len(rows)
        print(f"  ✅ Migrated {count} rows")
        return count
    except Exception as e:
        print(f"  ❌ Error migrating {table_name}: {e}")
        pg_conn.rollback()
        return 0

def main():
    print("=" * 60)
    print("SQLite to PostgreSQL Migration")
    print("=" * 60)
    
    # Check if SQLite database exists
    if not os.path.exists(SQLITE_DB):
        print(f"❌ SQLite database {SQLITE_DB} not found. Nothing to migrate.")
        return
    
    # Connect to SQLite
    print(f"Connecting to SQLite: {SQLITE_DB}")
    sqlite_conn = sqlite3.connect(SQLITE_DB)
    
    # Connect to PostgreSQL
    print(f"Connecting to PostgreSQL: {POSTGRES_DB}")
    try:
        pg_conn = psycopg2.connect(
            dbname=POSTGRES_DB,
            user=POSTGRES_USER,
            host=POSTGRES_HOST,
            port=POSTGRES_PORT
        )
    except Exception as e:
        print(f"❌ Failed to connect to PostgreSQL: {e}")
        print("Make sure PostgreSQL is running: brew services start postgresql@15")
        return
    
    print("✅ Connected to both databases\n")
    
    total_migrated = 0
    
    # Migrate superhuman_memories
    columns = ['id', 'timestamp', 'role', 'content', 'tag', 'importance_score', 'mode', 
               'personality', 'embedding', 'entities', 'concepts', 'semantic_hash', 
               'access_count', 'last_accessed', 'user_id', 'memory_type', 'conversation_id', 'created_at']
    total_migrated += migrate_table(sqlite_conn, pg_conn, 'superhuman_memories', columns)
    
    # Migrate learning_patterns
    columns = ['pattern_key', 'pattern_data', 'usage_count', 'last_used', 'created_at']
    total_migrated += migrate_table(sqlite_conn, pg_conn, 'learning_patterns', columns)
    
    # Migrate learned_vocabulary
    columns = ['word', 'category', 'emotion', 'intensity_min', 'intensity_max', 
               'usage_count', 'last_used', 'created_at']
    total_migrated += migrate_table(sqlite_conn, pg_conn, 'learned_vocabulary', columns)
    
    # Migrate word_meanings
    columns = ['word', 'meaning', 'part_of_speech', 'intent_type', 'synonyms', 
               'usage_count', 'last_used', 'created_at']
    total_migrated += migrate_table(sqlite_conn, pg_conn, 'word_meanings', columns)
    
    # Migrate grammar_knowledge
    columns = ['id', 'rule_type', 'rule_description', 'example', 'usage_count', 
               'last_used', 'created_at']
    total_migrated += migrate_table(sqlite_conn, pg_conn, 'grammar_knowledge', columns)
    
    # Migrate episodic_events
    columns = ['id', 'timestamp', 'user_id', 'actor', 'action', 'object', 'place', 
               'cause', 'effect', 'note', 'sentiment', 'confidence', 'source', 
               'usage_count', 'last_accessed']
    total_migrated += migrate_table(sqlite_conn, pg_conn, 'episodic_events', columns)
    
    # Migrate brain_facts
    columns = ['id', 'subject', 'predicate', 'object', 'value', 'confidence', 'permanent', 
               'usage_count', 'created_at', 'last_reinforced', 'user_id', 'source', 'semantic_hash']
    total_migrated += migrate_table(sqlite_conn, pg_conn, 'brain_facts', columns)
    
    # Close connections
    sqlite_conn.close()
    pg_conn.close()
    
    print("\n" + "=" * 60)
    print(f"✅ Migration complete! Migrated {total_migrated} total rows")
    print("=" * 60)
    print("\nNote: Your SQLite database is still intact at:", SQLITE_DB)
    print("You can delete it after verifying PostgreSQL works correctly.")

if __name__ == "__main__":
    main()
