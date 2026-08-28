from datetime import datetime

from core.events import Event, EventType
from services.sessionlog import SessionLogService
from storage.database import Database


def test_log_and_recent(tmp_path):
    svc = SessionLogService(Database(tmp_path / "s.db"))
    svc.start_session()
    sid = svc._session_id
    svc.log_turn("user", "hello there")
    svc.log_turn("assistant", "hi, how can I help?")
    turns = svc.recent(10)
    assert [t["role"] for t in turns] == ["assistant", "user"]
    sess = svc.db.query("SELECT * FROM sessions WHERE id = ?", (sid,))
    assert sess[0]["turn_count"] == 2


def test_search_and_nearby(tmp_path):
    svc = SessionLogService(Database(tmp_path / "s.db"))
    svc.start_session()
    svc.log_turn("user", "open the garage door")
    svc.log_turn("assistant", "opening garage now")
    svc.log_turn("user", "what is the weather")
    svc.log_turn("assistant", "sunny, 21 degrees")
    hits = svc.search("garage", limit=3)
    assert hits and "garage" in hits[0]["content"]
    nearby = svc.get_nearby(hits[0]["id"], window=1)
    roles = [t["role"] for t in nearby]
    assert "user" in roles and "assistant" in roles


def test_event_subscription_logs_turn(tmp_path):
    class FakeBus:
        def __init__(self):
            self.handlers = {}

        def subscribe(self, etype, fn):
            self.handlers.setdefault(etype, []).append(fn)

        def publish(self, event):
            for fn in self.handlers.get(event.type, []):
                fn(event)

    bus = FakeBus()
    svc = SessionLogService(Database(tmp_path / "s.db"), bus=bus)
    svc.start_session()
    bus.publish(Event(EventType.USER_INPUT_RECEIVED, {"text": "remind me to call mom"}))
    bus.publish(Event(EventType.COMMAND_COMPLETED, {"intent": "assistant.timer", "response": "ok, timer set"}))
    turns = [t["role"] for t in svc.recent(10)]
    assert "user" in turns and "assistant" in turns
