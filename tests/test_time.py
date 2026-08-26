import asyncio
from datetime import date
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from core.commands import Command
from core.events import EventBus
from core.executor import Executor, ExecutorContext
from core.router import IntentRouter
from core.state import AssistantState, StateManager
from services.settings import Settings
from services.time import TimeService
from storage.database import Database


def make(tmp_path):
    settings = Settings(Database(tmp_path / "time.db"), EventBus())
    states = StateManager(EventBus())
    executor = Executor(EventBus(), states, settings)
    router = IntentRouter(settings)
    return SimpleNamespace(settings=settings, states=states, executor=executor, router=router)


async def ask(c, text):
    command = c.router.route(text)
    response = await c.executor.execute(command)
    return command, response


def test_time_query(tmp_path):
    c = make(tmp_path)
    command, response = asyncio.run(ask(c, "what time is it?"))
    assert command.intent == "time.query"
    assert ":" in response and ("AM" in response.upper() or "PM" in response.upper())


def test_date_query(tmp_path):
    c = make(tmp_path)
    _, response = asyncio.run(ask(c, "what's the date today?"))
    assert response.startswith("Today is ")
    assert any(d in response for d in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])


def test_weekday_of_known_date(tmp_path):
    c = make(tmp_path)
    _, response = asyncio.run(ask(c, "what day is December 25 2025?"))
    assert "Thursday" in response  # Dec 25 2025 was a Thursday


def test_days_until_future_this_year(tmp_path):
    c = make(tmp_path)
    future = date.today() + __import__("datetime").timedelta(days=10)
    _, response = asyncio.run(ask(c, f"how many days until {future.isoformat()}?"))
    assert "10 days" in response


def test_set_timezone_valid_and_invalid(tmp_path):
    c = make(tmp_path)
    _, response = asyncio.run(ask(c, "set timezone to America/New_York"))
    assert "Timezone set" in response
    assert c.settings.get("timezone") == "America/New_York"
    _, response = asyncio.run(ask(c, "set timezone to Mars/Olympus"))
    assert "not a valid timezone" in response


def test_timezone_changes_reported_time(tmp_path):
    c = make(tmp_path)
    asyncio.run(ask(c, "set timezone to UTC"))
    service = TimeService(c.settings)
    assert service.now().tzinfo == ZoneInfo("UTC")


def test_time_context_shape(tmp_path):
    c = make(tmp_path)
    context = TimeService(c.settings).context()
    for key in ("iso", "time", "date", "weekday", "timezone"):
        assert key in context


def test_parse_date_formats():
    from intents.rules import parse_date
    assert parse_date("december 25") == date(1900, 12, 25)
    assert parse_date("2026-01-15") == date(2026, 1, 15)
    assert parse_date("3/4") == date(1900, 3, 4)
    assert parse_date("March 3rd") == date(1900, 3, 3)
    assert parse_date("gibberish") is None
