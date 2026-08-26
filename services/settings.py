import sqlite3

from config import DEFAULT_ASSISTANT_NAME
from core.events import Event, EventBus, EventType
from core.state import now_iso
from storage.database import Database


class Settings:
    def __init__(self, db: Database, bus: EventBus):
        self.db = db
        self.bus = bus
    def get(self, key: str, default: str | None = None) -> str | None:
        rows = self.db.query("SELECT value FROM settings WHERE key = ?", (key,))
        if rows:
            return rows[0]["value"]
        if key == "assistant_name":
            return DEFAULT_ASSISTANT_NAME
        return default

    def set(self, key: str, value: str) -> None:
        self.db.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (key, value, now_iso()),
        )
        self.bus.publish_sync(Event(EventType.SETTING_CHANGED, {"key": key, "value": value}))

    def all(self) -> dict:
        rows = self.db.query("SELECT key, value FROM settings")
        result = {r["key"]: r["value"] for r in rows}
        result.setdefault("assistant_name", DEFAULT_ASSISTANT_NAME)
        return result
