import json
from datetime import datetime, timedelta

from storage.database import Database


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat(sep=" ")


class WebCache:
    """SQLite-backed response cache with per-entry TTL (spec §12)."""

    def __init__(self, db: Database):
        self.db = db

    def get(self, key: str):
        row = self.db.query(
            "SELECT payload FROM cache WHERE key = ? AND expires_at > ?",
            (key, _iso(datetime.now())),
        )
        if not row:
            return None
        return json.loads(row[0]["payload"])

    def set(self, key: str, data, ttl_seconds: int = 3600) -> None:
        now = datetime.now()
        self.db.execute(
            "INSERT INTO cache (key, payload, created_at, expires_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET payload = excluded.payload, "
            "created_at = excluded.created_at, expires_at = excluded.expires_at",
            (key, json.dumps(data), _iso(now), _iso(now + timedelta(seconds=ttl_seconds))),
        )
