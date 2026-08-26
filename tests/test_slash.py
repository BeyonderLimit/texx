import asyncio
from types import SimpleNamespace

from core import slash
from core.events import EventBus
from core.state import AssistantState, StateManager
from services.settings import Settings
from storage.database import Database


def ctx(tmp_path=None):
    import tempfile
    path = tmp_path or "/tmp/opencode"
    settings = Settings(Database(f"{path}/texx-slash-test.db"), EventBus())
    states = StateManager(EventBus())
    from services.system import SystemService
    from services.reminders import ReminderService
    from services.time import TimeService
    from services.tasks import TaskService
    system = SystemService(settings)
    return SimpleNamespace(settings=settings, states=states, system=system,
                           reminders=ReminderService(Database(f"{path}/texx-slash-test.db")),
                           time=TimeService(settings),
                           tasks=TaskService(Database(f"{path}/texx-slash-test.db")))


def test_help_lists_all_commands():
    response = asyncio.run(slash.handle("/help", ctx()))
    for cmd in slash.SLASH_COMMANDS:
        assert cmd in response


def test_unknown_slash_command():
    response = asyncio.run(slash.handle("/frobnicate", ctx()))
    assert "Unknown command" in response
    assert "/help" in response


def test_name_get_and_set(tmp_path):
    c = ctx(tmp_path)
    response = asyncio.run(slash.handle("/name Athena", c))
    assert "Athena" in response
    assert c.settings.get("assistant_name") == "Athena"
    response = asyncio.run(slash.handle("/name", c))
    assert "Athena" in response


def test_status_and_apps():
    c = ctx()
    assert "idle" in asyncio.run(slash.handle("/status", c))
    assert "firefox" in asyncio.run(slash.handle("/apps", c))


def test_clear_and_exit_sentinels():
    assert asyncio.run(slash.handle("/clear", ctx())) == "__CLEAR__"
    assert asyncio.run(slash.handle("/exit", ctx())) == "__EXIT__"


def test_is_slash():
    assert slash.is_slash_command("/help")
    assert not slash.is_slash_command("help me open firefox")
