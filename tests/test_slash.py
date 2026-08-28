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


def test_sessions_owner_compact(tmp_path):
    from services.memory import MemoryService
    from services.sessionlog import SessionLogService
    from services.owner import OwnerProfile

    db_path = tmp_path / "texx-slash-phase7.db"
    db = Database(str(db_path))
    c = ctx(tmp_path)
    c.memory = MemoryService(db)
    c.sessionlog = SessionLogService(db)
    c.owner = OwnerProfile(path=tmp_path / "OWNER.md")

    # seed a session turn and a memory
    c.sessionlog.start_session()
    c.sessionlog.log_turn("user", "remind me to buy milk")
    c.sessionlog.log_turn("assistant", "ok, milk reminder set")
    c.memory.add("I prefer tea over coffee", category="PREFERENCE")

    out = asyncio.run(slash.handle("/sessions", c))
    assert "milk" in out

    out = asyncio.run(slash.handle("/sessions milk", c))
    assert "milk" in out

    out = asyncio.run(slash.handle("/owner", c))
    assert "not generated yet" in out or "OWNER" in out

    out = asyncio.run(slash.handle("/compact", c))
    assert "Compaction complete" in out
    # after compact, OWNER.md should now exist
    out = asyncio.run(slash.handle("/owner", c))
    assert "OWNER" in out

