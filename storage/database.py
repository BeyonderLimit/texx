import sqlite3
from contextlib import contextmanager
from pathlib import Path

from config import DATA_DIR, DB_PATH

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class Database:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.Connection(self.path)
        self.conn.row_factory = sqlite3.Row
        self._tx_depth = 0
        self._optimize()
        self._migrate()

    def _optimize(self):
        # WAL + synchronous=NORMAL trade one fsync-per-write for a single log
        # append that is checkpointed in bulk — a large latency win on flash
        # storage (SD/eMMC). Power-loss risk is limited to the most recent
        # writes (no corruption); fine for a local assistant DB.
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA cache_size=-16384")  # 16 MiB page cache
        self.conn.execute("PRAGMA temp_store=MEMORY")
        self.conn.commit()

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

    @contextmanager
    def transaction(self):
        """Run a group of writes as a single commit.

        Nested `transaction()` blocks flatten: the outermost one owns the
        commit (and rolls everything back on an exception), inner frames just
        track nesting so `execute` stays in the batch. Outside any transaction,
        `execute` still commits per statement.
        """
        if self._tx_depth == 0:
            self._tx_depth = 1
            try:
                yield self
                self.conn.commit()
            except BaseException:
                self.conn.rollback()
                raise
            finally:
                self._tx_depth = 0
        else:
            self._tx_depth += 1
            try:
                yield self
            finally:
                self._tx_depth -= 1

    def execute(self, sql: str, params: tuple = ()):
        cur = self.conn.execute(sql, params)
        if self._tx_depth == 0:
            self.conn.commit()
        return cur

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        return list(self.conn.execute(sql, params))

    def close(self):
        self.conn.close()
