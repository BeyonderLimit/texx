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
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(reminders)")}
        if "category" not in cols:
            self.conn.execute(
                "ALTER TABLE reminders ADD COLUMN category TEXT DEFAULT 'event'"
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
