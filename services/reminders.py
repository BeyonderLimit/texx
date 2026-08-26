import sqlite3
from datetime import datetime, timedelta

from storage.database import Database


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat(sep=" ")


class ReminderService:
    def __init__(self, db: Database):
        self.db = db

    def add(self, task: str, due_at: datetime | None = None,
            recurrence_rule: str | None = None, created_at: datetime | None = None,
            category: str = "event") -> int:
        created = _iso(created_at or datetime.now())
        cur = self.db.execute(
            "INSERT INTO reminders (task, due_at, recurrence_rule, status, category, created_at) "
            "VALUES (?, ?, ?, 'pending', ?, ?)",
            (task, _iso(due_at) if due_at else None, recurrence_rule, category, created),
        )
        return cur.lastrowid

    def get(self, reminder_id: int) -> sqlite3.Row | None:
        rows = self.db.query("SELECT * FROM reminders WHERE id = ?", (reminder_id,))
        return rows[0] if rows else None

    def list_pending(self, category: str | None = None) -> list[sqlite3.Row]:
        if category:
            return self.db.query(
                "SELECT * FROM reminders WHERE status = 'pending' AND category = ? "
                "ORDER BY due_at IS NULL, due_at",
                (category,),
            )
        return self.db.query(
            "SELECT * FROM reminders WHERE status = 'pending' ORDER BY due_at IS NULL, due_at"
        )

    def complete(self, reminder_id: int, completed_at: datetime | None = None,
                 expected_category: str | None = None) -> bool:
        return self._set_status(reminder_id, "completed", completed_at or datetime.now(),
                                expected_category)

    def cancel(self, reminder_id: int, expected_category: str | None = None) -> bool:
        return self._set_status(reminder_id, "cancelled", expected_category=expected_category)

    def _set_status(self, reminder_id: int, status: str, when: datetime | None = None,
                    expected_category: str | None = None) -> bool:
        completed = _iso(when) if when else None
        sql = ("UPDATE reminders SET status = ?, completed_at = COALESCE(?, completed_at) "
               "WHERE id = ? AND status = 'pending'")
        params: list = [status, completed, reminder_id]
        if expected_category:
            sql += " AND category = ?"
            params.append(expected_category)
        cur = self.db.execute(sql, tuple(params))
        return cur.rowcount > 0

    def get_due(self, now: datetime | None = None,
                category: str | None = None) -> list[sqlite3.Row]:
        now_iso = _iso(now or datetime.now())
        sql = ("SELECT * FROM reminders WHERE status = 'pending' AND due_at IS NOT NULL "
               "AND notification_sent_at IS NULL AND due_at <= ?")
        params: list = [now_iso]
        if category:
            sql += " AND category = ?"
            params.append(category)
        sql += " ORDER BY due_at"
        return self.db.query(sql, tuple(params))

    def mark_notified(self, reminder_id: int, when: datetime | None = None) -> None:
        self.db.execute(
            "UPDATE reminders SET notification_sent_at = ? WHERE id = ?",
            (_iso(when or datetime.now()), reminder_id),
        )

    def next_from_recurrence(self, rule: str, after: datetime) -> datetime | None:
        parts = dict(p.split("=") for p in rule.split(";") if "=" in p)
        freq = parts.get("FREQ")
        if freq == "MINUTELY":
            return after + timedelta(minutes=int(parts.get("INTERVAL", 1)))
        if freq == "HOURLY":
            return after + timedelta(hours=int(parts.get("INTERVAL", 1)))
        if freq == "DAILY":
            candidate = (after + timedelta(days=1)).replace(
                hour=after.hour, minute=after.minute, second=0, microsecond=0
            )
            if candidate <= after:
                candidate += timedelta(days=1)
            return candidate
        if freq == "WEEKLY" and "BYDAY" in parts:
            weekdays = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
            target = weekdays.get(parts["BYDAY"])
            if target is None:
                return None
            days_ahead = (target - after.weekday()) % 7 or 7
            return (after + timedelta(days=days_ahead)).replace(
                hour=after.hour, minute=after.minute, second=0, microsecond=0
            )
        return None

    def reschedule(self, reminder_id: int, next_due: datetime) -> None:
        self.db.execute(
            "UPDATE reminders SET due_at = ?, notification_sent_at = NULL WHERE id = ?",
            (_iso(next_due), reminder_id),
        )
