import sqlite3
from pathlib import Path

from config import DATA_DIR, DB_PATH

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class Database:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.Connection(self.path)
        self.conn.row_factory = sqlite3.Row
        self._migrate()

    def _migrate(self):
        self.conn.executescript(SCHEMA_PATH.read_text())
        mcols = {r[1] for r in self.conn.execute("PRAGMA table_info(memories)")}
        if "layer" not in mcols:
            self.conn.execute(
                "ALTER TABLE memories ADD COLUMN layer TEXT NOT NULL DEFAULT 'persistent'"
            )
        if "role" not in mcols:
            self.conn.execute(
                "ALTER TABLE memories ADD COLUMN role TEXT"
            )
        rcols = {r[1] for r in self.conn.execute("PRAGMA table_info(reminders)")}
        if "category" not in rcols:
            self.conn.execute(
                "ALTER TABLE reminders ADD COLUMN category TEXT DEFAULT 'event'"
            )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memories_layer ON memories(layer, created_at)"
        )
        self.conn.commit()

    def execute(self, sql: str, params: tuple = ()):
        cur = self.conn.execute(sql, params)
        self.conn.commit()
        return cur

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        return list(self.conn.execute(sql, params))

    def close(self):
        self.conn.close()
