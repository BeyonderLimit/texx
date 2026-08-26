import sqlite3
from datetime import datetime, timedelta

from storage.database import Database

PRIORITIES = ("urgent", "high", "normal", "low")
PRIORITY_RANK = {"urgent": 0, "high": 1, "normal": 2, "low": 3}


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat(sep=" ")


class TaskService:
    def __init__(self, db: Database):
        self.db = db

    def add(self, title: str, priority: str = "normal",
            expires_at: datetime | None = None) -> int:
        cur = self.db.execute(
            "INSERT INTO tasks (title, priority, status, created_at, expires_at) "
            "VALUES (?, ?, 'open', ?, ?)",
            (title.strip(), priority if priority in PRIORITIES else "normal",
             _iso(datetime.now()), _iso(expires_at) if expires_at else None),
        )
        return cur.lastrowid

    def get(self, task_id: int) -> sqlite3.Row | None:
        rows = self.db.query("SELECT * FROM tasks WHERE id = ?", (task_id,))
        return rows[0] if rows else None

    def list_open(self) -> list[sqlite3.Row]:
        rows = self.db.query("SELECT * FROM tasks WHERE status = 'open'")
        now_iso = _iso(datetime.now())
        return sorted(
            rows,
            key=lambda r: (PRIORITY_RANK.get(r["priority"], 2), r["created_at"]),
        )

    def complete(self, task_id: int) -> bool:
        cur = self.db.execute(
            "UPDATE tasks SET status = 'done', completed_at = ? "
            "WHERE id = ? AND status = 'open'",
            (_iso(datetime.now()), task_id),
        )
        return cur.rowcount > 0

    def delete(self, task_id: int) -> bool:
        cur = self.db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        return cur.rowcount > 0

    def purge_expired(self, now: datetime | None = None) -> int:
        cur = self.db.execute(
            "DELETE FROM tasks WHERE expires_at IS NOT NULL AND expires_at <= ?",
            (_iso(now or datetime.now()),),
        )
        return cur.rowcount
