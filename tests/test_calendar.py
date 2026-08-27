import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from core.commands import Command
from core.events import EventBus
from core.executor import Executor
from core.router import IntentRouter
from core.state import StateManager
from services.settings import Settings
from storage.database import Database
from services.calendar import parse_ics


SAMPLE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
DTSTART:20260915T140000
DTEND:20260915T150000
SUMMARY:Team Standup
DESCRIPTION:Daily sync with the team
LOCATION:Conference Room B
UID:evt-001@test
END:VEVENT
BEGIN:VEVENT
DTSTART:20260920T100000
DTEND:20260920T110000
SUMMARY:Dentist Appointment
DESCRIPTION:Regular checkup
UID:evt-002@test
END:VEVENT
BEGIN:VEVENT
DTSTART:20261225T000000
SUMMARY:Christmas
UID:evt-003@test
END:VEVENT
END:VCALENDAR"""


def make(tmp_path):
    db = Database(tmp_path / "t.db")
    settings = Settings(db, EventBus())
    states = StateManager(EventBus())
    router = IntentRouter(settings)
    system = SimpleNamespace(open_map=lambda: {}, close_map=lambda: {})
    executor = Executor(EventBus(), states, settings, system)
    return executor.ctx, router, executor


async def ask(ctx, router, executor, text):
    cmd = router.route(text)
    response = await executor.execute(cmd)
    return cmd, response


class TestCalendarParser:
    def test_parses_events(self, tmp_path):
        ics_path = tmp_path / "test.ics"
        ics_path.write_text(SAMPLE_ICS)
        events = parse_ics(ics_path)
        assert len(events) >= 2
        summaries = [e["summary"] for e in events]
        assert "Team Standup" in summaries
        assert "Dentist Appointment" in summaries

    def test_filters_far_future(self, tmp_path):
        ics_path = tmp_path / "test.ics"
        ics_path.write_text(SAMPLE_ICS)
        events = parse_ics(ics_path, horizon_days=5)
        summaries = [e["summary"] for e in events]
        assert "Christmas" not in summaries

    def test_extracts_location(self, tmp_path):
        ics_path = tmp_path / "test.ics"
        ics_path.write_text(SAMPLE_ICS)
        events = parse_ics(ics_path)
        standup = next(e for e in events if e["summary"] == "Team Standup")
        assert standup["location"] == "Conference Room B"

    def test_empty_file(self, tmp_path):
        ics_path = tmp_path / "empty.ics"
        ics_path.write_text("BEGIN:VCALENDAR\nVERSION:2.0\nEND:VCALENDAR")
        events = parse_ics(ics_path)
        assert events == []


class TestCalendarImportIntent:
    def test_import_calendar_routes(self, tmp_path):
        ctx, router, executor = make(tmp_path)
        cmd, _ = asyncio.run(ask(ctx, router, executor, "import calendar from /tmp/cal.ics"))
        assert cmd.intent == "calendar.import"
        assert cmd.slots["path"] == "/tmp/cal.ics"

    def test_import_calendar_no_path(self, tmp_path):
        ctx, router, executor = make(tmp_path)
        cmd, _ = asyncio.run(ask(ctx, router, executor, "import calendar"))
        assert cmd.intent != "calendar.import"


class TestCalendarImportHandler:
    def test_file_not_found(self, tmp_path):
        ctx, router, executor = make(tmp_path)
        _, response = asyncio.run(ask(ctx, router, executor, "import calendar from /nonexistent.ics"))
        assert "not found" in response.lower() or "no such file" in response.lower()

    def test_not_ics(self, tmp_path):
        ctx, router, executor = make(tmp_path)
        txt = tmp_path / "notes.txt"
        txt.write_text("hello")
        _, response = asyncio.run(ask(ctx, router, executor, f"import calendar from {txt}"))
        assert "not an ics" in response.lower()

    def test_import_success(self, tmp_path):
        ctx, router, executor = make(tmp_path)
        ics_path = tmp_path / "work.ics"
        ics_path.write_text(SAMPLE_ICS)
        _, response = asyncio.run(ask(ctx, router, executor, f"import calendar from {ics_path}"))
        assert "imported" in response.lower()
        assert "team standup" in response.lower()

    def test_import_empty_calendar(self, tmp_path):
        ctx, router, executor = make(tmp_path)
        ics_path = tmp_path / "empty.ics"
        ics_path.write_text("BEGIN:VCALENDAR\nVERSION:2.0\nEND:VCALENDAR")
        _, response = asyncio.run(ask(ctx, router, executor, f"import calendar from {ics_path}"))
        assert "no upcoming events" in response.lower()
