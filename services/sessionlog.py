from datetime import datetime

from core.events import Event, EventType
from storage.database import Database


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat(sep=" ")


class SessionLogService:
    """Append-only raw archive of every turn (user + assistant), kept separate
    from memory so exact prior wording and nearby context can be recovered
    without loading memory into a prompt. Writes are cheap INSERTs; all logging
    happens via EventBus subscribers, off the request path."""

    def __init__(self, db: Database, bus=None):
        self.db = db
        self._session_id = None
        self._seq = 0
        if bus is not None:
            self.attach(bus)

    def attach(self, bus):
        bus.subscribe(EventType.USER_INPUT_RECEIVED, self._on_user_input)
        bus.subscribe(EventType.COMMAND_COMPLETED, self._on_completed)

    def _on_user_input(self, event: Event):
        text = (event.data or {}).get("text", "")
        if text:
            self.log_turn("user", text)

    def _on_completed(self, event: Event):
        data = event.data or {}
        resp = data.get("response", "")
        if resp:
            self.log_turn("assistant", resp, intent=data.get("intent"))

    def start_session(self) -> int:
        cur = self.db.execute(
            "INSERT INTO sessions (started_at, turn_count) VALUES (?, 0)",
            (_iso(datetime.now()),),
        )
        self._session_id = cur.lastrowid
        self._seq = 0
        return self._session_id

    def _ensure_session(self):
        if self._session_id is None:
            self.start_session()

    def log_turn(self, role: str, content: str, intent=None) -> int:
        self._ensure_session()
        self._seq += 1
        now = _iso(datetime.now())
        cur = self.db.execute(
            "INSERT INTO session_turns (session_id, seq, role, intent, content, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (self._session_id, self._seq, role, intent, content, now),
        )
        tid = cur.lastrowid
        self.db.execute(
            "INSERT INTO session_fts (content, session_turn_id) VALUES (?, ?)",
            (content, tid),
        )
        self.db.execute(
            "UPDATE sessions SET turn_count = turn_count + 1 WHERE id = ?",
            (self._session_id,),
        )
        return tid

    def end_session(self):
        if self._session_id is None:
            return
        self.db.execute(
            "UPDATE sessions SET ended_at = ? WHERE id = ?",
            (_iso(datetime.now()), self._session_id),
        )
        self._session_id = None
        self._seq = 0

    def search(self, query: str, limit: int = 10) -> list:
        phrase = '"' + query.replace('"', '""') + '"'
        try:
            rows = self.db.query(
                "SELECT t.* FROM session_fts f JOIN session_turns t "
                "ON t.id = f.session_turn_id "
                "WHERE session_fts MATCH ? ORDER BY t.created_at DESC LIMIT ?",
                (phrase, limit),
            )
        except Exception:
            rows = []
        if not rows:
            like = f"%{query}%"
            rows = self.db.query(
                "SELECT * FROM session_turns WHERE content LIKE ? "
                "ORDER BY created_at DESC LIMIT ?",
                (like, limit),
            )
        return rows

    def get_nearby(self, turn_id: int, window: int = 2) -> list:
        row = self.db.query(
            "SELECT session_id, seq FROM session_turns WHERE id = ?", (turn_id,)
        )
        if not row:
            return []
        sid, seq = row[0]["session_id"], row[0]["seq"]
        return self.db.query(
            "SELECT * FROM session_turns WHERE session_id = ? "
            "AND seq BETWEEN ? AND ? ORDER BY seq ASC",
            (sid, max(1, seq - window), seq + window),
        )

    def recent(self, n: int = 20) -> list:
        return self.db.query(
            "SELECT * FROM session_turns ORDER BY created_at DESC, seq DESC LIMIT ?",
            (n,),
        )
