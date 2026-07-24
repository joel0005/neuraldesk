"""
SQLite Database — All tables for RagBase.
No Docker needed. Just a single file on your machine.
"""

import sqlite3
import os
from ..config import config


def get_db():
    """Get a database connection."""
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db():
    """Create all tables. Run once on startup."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.executescript("""

    -- Users
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        name TEXT,
        plan TEXT DEFAULT 'free',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Bots
    CREATE TABLE IF NOT EXISTS bots (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        name TEXT NOT NULL,
        slug TEXT UNIQUE,
        description TEXT DEFAULT '',
        status TEXT DEFAULT 'active',

        llm_provider TEXT DEFAULT 'ollama',
        llm_model TEXT DEFAULT 'gemma3:latest',
        llm_api_key TEXT DEFAULT '',
        temperature REAL DEFAULT 0.7,
        max_tokens INTEGER DEFAULT 1024,

        embedding_provider TEXT DEFAULT 'local',
        embedding_model TEXT DEFAULT 'all-MiniLM-L6-v2',

        top_k INTEGER DEFAULT 5,
        similarity_threshold REAL DEFAULT 0.0,
        confidence_threshold REAL DEFAULT 0.5,
        use_reranking INTEGER DEFAULT 0,
        use_query_rewrite INTEGER DEFAULT 0,

        system_prompt TEXT DEFAULT '',
        persona_name TEXT DEFAULT 'Assistant',
        welcome_message TEXT DEFAULT 'Hi! How can I help you?',
        fallback_message TEXT DEFAULT 'I am not sure about that. Would you like to speak with a human?',
        suggested_questions TEXT DEFAULT '[]',
        blocked_words TEXT DEFAULT '[]',
        require_citations INTEGER DEFAULT 1,

        primary_color TEXT DEFAULT '#6366f1',
        position TEXT DEFAULT 'bottom-right',

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    -- Knowledge Sources
    CREATE TABLE IF NOT EXISTS knowledge_sources (
        id TEXT PRIMARY KEY,
        bot_id TEXT NOT NULL,
        type TEXT NOT NULL,
        name TEXT,
        file_path TEXT,
        file_type TEXT,
        file_size_bytes INTEGER,
        url TEXT,
        db_type TEXT,
        db_connection TEXT,
        status TEXT DEFAULT 'pending',
        error_message TEXT,
        chunk_count INTEGER DEFAULT 0,
        ingestion_strategy TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY (bot_id) REFERENCES bots(id) ON DELETE CASCADE
    );

    -- Business Glossary (schema-first output — lifelong)
    CREATE TABLE IF NOT EXISTS business_glossaries (
        id TEXT PRIMARY KEY,
        bot_id TEXT NOT NULL,
        source_id TEXT,
        table_name TEXT,
        glossary_data TEXT NOT NULL,
        context_text TEXT,
        confirmed_by TEXT,
        confirmed_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY (bot_id) REFERENCES bots(id) ON DELETE CASCADE
    );
-- Structured DB sources (Text-to-SQL)
    CREATE TABLE IF NOT EXISTS sql_sources (
        id TEXT PRIMARY KEY,
        bot_id TEXT NOT NULL,
        source_id TEXT NOT NULL,
        db_path TEXT NOT NULL,
        db_type TEXT DEFAULT 'sqlite',
        schema_json TEXT NOT NULL,
        table_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY (bot_id) REFERENCES bots(id) ON DELETE CASCADE
    );

    -- Conversations
    CREATE TABLE IF NOT EXISTS conversations (
        id TEXT PRIMARY KEY,
        bot_id TEXT NOT NULL,
        session_id TEXT,
        channel TEXT DEFAULT 'widget',
        visitor_name TEXT,
        visitor_email TEXT,
        status TEXT DEFAULT 'active',
        message_count INTEGER DEFAULT 0,
        first_message_at TIMESTAMP,
        last_message_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY (bot_id) REFERENCES bots(id) ON DELETE CASCADE
    );

    -- Messages
    CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        sources_used TEXT,
        confidence REAL,
        model_used TEXT,
        provider_used TEXT,
        tokens_input INTEGER,
        tokens_output INTEGER,
        latency_ms INTEGER,
        sql_query_used TEXT,
        feedback TEXT,
        feedback_reason TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
    );

    -- Unanswered Questions
    CREATE TABLE IF NOT EXISTS unanswered_questions (
        id TEXT PRIMARY KEY,
        bot_id TEXT NOT NULL,
        question TEXT NOT NULL,
        frequency INTEGER DEFAULT 1,
        first_asked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_asked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        resolved INTEGER DEFAULT 0,

        FOREIGN KEY (bot_id) REFERENCES bots(id) ON DELETE CASCADE
    );

    -- Leads
    CREATE TABLE IF NOT EXISTS leads (
        id TEXT PRIMARY KEY,
        bot_id TEXT NOT NULL,
        conversation_id TEXT,
        name TEXT,
        email TEXT,
        phone TEXT,
        company TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY (bot_id) REFERENCES bots(id) ON DELETE CASCADE
    );

    -- API Keys
    CREATE TABLE IF NOT EXISTS api_keys (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        key_hash TEXT NOT NULL,
        key_prefix TEXT NOT NULL,
        name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    """)

    conn.commit()
    conn.close()
    print("Database tables created successfully.")