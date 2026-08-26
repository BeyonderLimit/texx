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
            expires_at: datetime | None = None) -> int:
        if not category:
            category, importance = classify_memory(content)
        now_iso = _iso(datetime.now())
        cur = self.db.execute(
            "INSERT INTO memories (content, category, importance, confidence, created_at, "
            "updated_at, access_count, expires_at, source) VALUES (?, ?, ?, 1.0, ?, ?, 0, ?, ?)",
            (content.strip(), category, importance or 5, now_iso, now_iso,
             _iso(expires_at) if expires_at else None, source),
        )
        return cur.lastrowid

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

    def search(self, query: str, limit: int = 5, now: datetime | None = None):
        """FTS match ranked by spec §5 score; bumps access stats for hits."""
        now = now or datetime.now()
        phrase = '"' + query.replace('"', '""') + '"'
        try:
            rows = self.db.query(
                "SELECT m.* FROM memory_fts f JOIN memories m ON m.id = f.rowid "
                "WHERE memory_fts MATCH ? AND (m.expires_at IS NULL OR m.expires_at > ?)",
                (phrase, _iso(now)),
            )
        except Exception:
            rows = []
        if not rows:
            like = f"%{query}%"
            rows = self.db.query(
                "SELECT * FROM memories WHERE content LIKE ? "
                "AND (expires_at IS NULL OR expires_at > ?) LIMIT 20",
                (like, _iso(now)),
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
