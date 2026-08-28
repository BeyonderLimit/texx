CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY,
    content TEXT NOT NULL,
    category TEXT NOT NULL,
    importance INTEGER DEFAULT 5,
    confidence REAL DEFAULT 1.0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_accessed_at TEXT,
    access_count INTEGER DEFAULT 0,
    expires_at TEXT,
    source TEXT,
    layer TEXT NOT NULL DEFAULT 'persistent',
    role TEXT
);

-- prior wording and nearby context can be recovered without loading memory.
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    turn_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS session_turns (
    id INTEGER PRIMARY KEY,
    session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    role TEXT NOT NULL,
    intent TEXT,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_session_turns_session ON session_turns(session_id);
CREATE INDEX IF NOT EXISTS idx_session_turns_created ON session_turns(created_at);

CREATE VIRTUAL TABLE IF NOT EXISTS session_fts USING fts5(
    content,
    session_turn_id UNINDEXED
);

CREATE TABLE IF NOT EXISTS memory_entities (
    memory_id INTEGER REFERENCES memories(id) ON DELETE CASCADE,
    entity TEXT NOT NULL,
    entity_type TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
    content,
    content='memories'
);

CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memory_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memory_fts(memory_fts, rowid, content) VALUES ('delete', old.id, old.content);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE OF content ON memories BEGIN
    INSERT INTO memory_fts(memory_fts, rowid, content) VALUES ('delete', old.id, old.content);
    INSERT INTO memory_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE TABLE IF NOT EXISTS cache (
    key TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    priority TEXT DEFAULT 'normal',
    status TEXT DEFAULT 'open',
    created_at TEXT NOT NULL,
    completed_at TEXT,
    expires_at TEXT
);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY,
    task TEXT NOT NULL,
    due_at TEXT,
    recurrence_rule TEXT,
    status TEXT DEFAULT 'pending',
    category TEXT DEFAULT 'event',
    created_at TEXT NOT NULL,
    completed_at TEXT,
    notification_sent_at TEXT
);
