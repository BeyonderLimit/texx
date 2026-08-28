import time
from datetime import datetime, timedelta

from storage.database import Database

CATEGORY_KEYWORDS = [
    ("PROFILE", ["my name is", "call me ", "i am called", "my birthday"]),
    ("PREFERENCE", ["i prefer", "i like", "i love", "i hate", "favorite", "favourite"]),
    ("PROJECT", ["working on", "project", "building "]),
    ("PEOPLE", ["friend", "wife", "husband", "brother", "sister", "mom", "dad",
                "landlord", "boss", "colleague", "daughter", "son"]),
]

BASE_IMPORTANCE = {"PROFILE": 9, "PREFERENCE": 6, "PROJECT": 8, "PEOPLE": 7, "FACT": 5}


def classify_memory(text: str) -> tuple[str, int]:
    lowered = text.lower()
    for category, keywords in CATEGORY_KEYWORDS:
        if any(k in lowered for k in keywords):
            return category, BASE_IMPORTANCE[category]
    return "FACT", 5


class MemoryService:
    def __init__(self, db: Database):
        self.db = db

    def add(self, content: str, category: str | None = None,
            importance: int | None = None, source: str = "user",
            expires_at: datetime | None = None, layer: str = "persistent",
            role: str | None = None, created_at: datetime | None = None) -> int:
        if not category:
            category, importance = classify_memory(content)
        now_iso = _iso(created_at) if created_at else _iso(datetime.now())
        cur = self.db.execute(
            "INSERT INTO memories (content, category, importance, confidence, created_at, "
            "updated_at, access_count, expires_at, source, layer, role) VALUES (?, ?, ?, 1.0, ?, ?, 0, ?, ?, ?, ?)",
            (content.strip(), category, importance or 5, now_iso, now_iso,
             _iso(expires_at) if expires_at else None, source, layer, role),
        )
        return cur.lastrowid

    def add_daily(self, content: str, category: str = "FACT",
                  importance: int = 5, source: str = "auto",
                  expires_at: datetime | None = None, now: datetime | None = None) -> int:
        return self.add(content, category=category, importance=importance,
                        source=source, expires_at=expires_at, layer="daily",
                        created_at=now)

    def add_discussion(self, content: str, category: str = "FACT",
                       importance: int = 4, source: str = "session",
                       expires_at: datetime | None = None, role: str | None = None,
                       now: datetime | None = None) -> int:
        """Short-term working context. Defaults to a 7-day self-expiring entry."""
        if expires_at is None:
            now = now or datetime.now()
            expires_at = now + timedelta(days=7)
        else:
            now = now or datetime.now()
        return self.add(content, category=category, importance=importance,
                        source=source, expires_at=expires_at, layer="discussion",
                        role=role, created_at=now)

    def persistent(self, limit: int = 100) -> list:
        return self.db.query(
            "SELECT * FROM memories WHERE layer = 'persistent' "
            "ORDER BY importance DESC, created_at DESC LIMIT ?",
            (limit,),
        )

    def compact_discussion(self, older_than_days: int = 7, now: datetime | None = None) -> int:
        now = now or datetime.now()
        cutoff = _iso(now - timedelta(days=older_than_days))
        cur = self.db.execute(
            "DELETE FROM memories WHERE layer = 'discussion' AND created_at <= ?",
            (cutoff,),
        )
        return cur.rowcount

    def prune_daily(self, older_than_days: int = 90, now: datetime | None = None) -> int:
        now = now or datetime.now()
        cutoff = _iso(now - timedelta(days=older_than_days))
        cur = self.db.execute(
            "DELETE FROM memories WHERE layer = 'daily' AND created_at <= ?",
            (cutoff,),
        )
        return cur.rowcount

    def summarize_yesterday_discussion(self, llm=None, now: datetime | None = None) -> int:
        """Fold yesterday's discussion entries into one 'daily' memory, then delete
        them (compaction). Uses the LLM to condense if available, else concatenates."""
        now = now or datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start = today_start - timedelta(days=1)
        rows = self.db.query(
            "SELECT id, content, role FROM memories WHERE layer = 'discussion' "
            "AND created_at >= ? AND created_at < ? ORDER BY created_at ASC",
            (_iso(yesterday_start), _iso(today_start)),
        )
        if not rows:
            return 0
        lines = [f"[{r['role']}] {r['content']}" for r in rows]
        if llm is not None:
            try:
                summary = llm.condense("\n".join(lines))
            except Exception:
                summary = None
        else:
            summary = None
        if not summary:
            summary = "Working context:\n" + "\n".join(lines[:50])
        self.add_daily(summary, category="FACT", importance=5, source="auto")
        ids = [r["id"] for r in rows]
        self.db.execute(
            f"DELETE FROM memories WHERE id IN ({','.join('?' * len(ids))})", tuple(ids)
        )
        return len(rows)

    def get(self, memory_id: int):
        rows = self.db.query("SELECT * FROM memories WHERE id = ?", (memory_id,))
        return rows[0] if rows else None

    def forget(self, memory_id: int) -> bool:
        cur = self.db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        return cur.rowcount > 0

    def all(self, limit: int = 50):
        return self.db.query(
            "SELECT * FROM memories ORDER BY importance DESC, created_at DESC LIMIT ?",
            (limit,),
        )

    def list_category(self, category: str, limit: int = 50):
        return self.db.query(
            "SELECT * FROM memories WHERE category = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (category, limit),
        )

    def count(self) -> int:
        rows = self.db.query("SELECT COUNT(*) AS n FROM memories")
        return rows[0]["n"]

    def purge_expired(self, now: datetime | None = None) -> int:
        now_iso = _iso(now or datetime.now())
        cur = self.db.execute(
            "DELETE FROM memories WHERE expires_at IS NOT NULL AND expires_at <= ?",
            (now_iso,),
        )
        return cur.rowcount

    def search(self, query: str, limit: int = 5, now: datetime | None = None,
                layers: list | None = None):
        """FTS match ranked by spec §5 score; bumps access stats for hits.
        `layers` optionally restricts to e.g. ['persistent', 'discussion']."""
        now = now or datetime.now()
        layer_sql = ""
        layer_like_sql = ""
        layer_params: tuple = ()
        if layers:
            placeholders = ",".join("?" * len(layers))
            layer_sql = f" AND m.layer IN ({placeholders})"
            layer_like_sql = f" AND layer IN ({placeholders})"
            layer_params = tuple(layers)
        phrase = '"' + query.replace('"', '""') + '"'
        try:
            rows = self.db.query(
                "SELECT m.* FROM memory_fts f JOIN memories m ON m.id = f.rowid "
                "WHERE memory_fts MATCH ? AND (m.expires_at IS NULL OR m.expires_at > ?)"
                + layer_sql,
                (phrase, _iso(now), *layer_params),
            )
        except Exception:
            rows = []
        if not rows:
            like = f"%{query}%"
            rows = self.db.query(
                "SELECT * FROM memories WHERE content LIKE ? "
                "AND (expires_at IS NULL OR expires_at > ?)" + layer_like_sql,
                (like, _iso(now), *layer_params),
            )
        scored = sorted(rows, key=lambda r: -self._score(r, now))
        top = scored[:limit]
        for row in top:
            self.db.execute(
                "UPDATE memories SET access_count = access_count + 1, last_accessed_at = ? "
                "WHERE id = ?",
                (_iso(now), row["id"]),
            )
        return top

    def _score(self, row, now: datetime) -> float:
        """Spec §5: importance*0.35 + recency*0.15 + frequency*0.20 + explicit*0.30."""
        created = datetime.fromisoformat(row["created_at"])
        days = max((now - created).days, 0)
        recency = 1.0 / (1.0 + days)
        frequency = min(row["access_count"] / 10.0, 1.0)
        explicit = 1.0 if (row["source"] or "") == "explicit" else 0.0
        return (
            (row["importance"] / 10.0) * 0.35
            + recency * 0.15
            + frequency * 0.20
            + explicit * 0.30
        )


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat(sep=" ")
