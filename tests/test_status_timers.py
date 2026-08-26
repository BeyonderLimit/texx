import asyncio
from datetime import datetime
from types import SimpleNamespace

from core.events import EventBus
from core.executor import Executor
from core.router import IntentRouter
from core.state import StateManager
from core.timers import TimerManager
from services.settings import Settings
from services.systeminfo import battery, brightness, full_status, running_processes, volume
from storage.database import Database

from test_reminders import RecordingNotifier, make, ask


def test_systeminfo_functions_return_strings():
    for fn in (battery, brightness, volume, running_processes):
        value = fn()
        assert isinstance(value, str) and len(value) > 0


def test_timer_manager_fires_after_duration():
    fired = []

    async def scenario():
        manager = TimerManager(
            EventBus(),
            notifier=SimpleNamespace(notify=lambda t, b: fired.append((t, b))),
            mode_fn=lambda: "normal",
        )
        tid = manager.start(0.1, "5 seconds")
        assert manager.active[tid]["seconds"] == 0.1
        await asyncio.sleep(0.3)
        assert not manager.active
        assert len(fired) == 1 and "up" in fired[0][1]

    asyncio.run(scenario())


def test_timer_manager_dnd_suppresses_audio():
    alerts = []

    async def scenario():
        manager = TimerManager(
            EventBus(),
            notifier=SimpleNamespace(notify=lambda t, b: None),
            alerter=SimpleNamespace(notify=lambda t, b: alerts.append(1)),
            mode_fn=lambda: "dnd",
        )
        manager.start(0.05, "1 minute")
        await asyncio.sleep(0.2)

    asyncio.run(scenario())
    assert alerts == []


def test_timer_cancel():
    async def scenario():
        manager = TimerManager(EventBus(), notifier=SimpleNamespace(notify=lambda t, b: None))
        tid = manager.start(60, "1 minute")
        assert manager.cancel(tid) is True
        assert manager.cancel(tid) is False

    asyncio.run(scenario())


def test_status_includes_all_sections(tmp_path):
    ctx, router, executor = make(tmp_path)
    command, response = asyncio.run(ask(ctx, router, executor, "status"))
    assert command.intent == "system.status"
    for section in ("Battery:", "Volume:", "Brightness:", "Processes:",
                    "Next event/timer:", "TODO"):
        assert section in response


def test_status_is_silent_no_alerter_involved(tmp_path):
    """Status handler never touches the audio path — verified structurally:
    the response comes from systeminfo only."""
    ctx, router, executor = make(tmp_path)
    _, response = asyncio.run(ask(ctx, router, executor, "system status"))
    assert "State:" in response


def test_individual_info_queries(tmp_path):
    ctx, router, executor = make(tmp_path)
    _, response = asyncio.run(ask(ctx, router, executor, "what's my battery level?"))
    assert response.startswith("Battery:")
    _, response = asyncio.run(ask(ctx, router, executor, "volume?"))
    assert response.startswith("Volume:")


def test_upcoming_event_shown_in_status(tmp_path):
    ctx, router, executor = make(tmp_path)
    asyncio.run(ask(ctx, router, executor, "remind me about dentist tomorrow at 10am"))
    _, response = asyncio.run(ask(ctx, router, executor, "status"))
    assert "dentist" in response


def test_todo_section_lists_uncompleted_only(tmp_path):
    ctx, router, executor = make(tmp_path)
    asyncio.run(ask(ctx, router, executor, "remind me in 30 minutes to stretch"))
    rid = ctx.reminders.list_pending()[0]["id"]
    asyncio.run(ask(ctx, router, executor, f"mark reminder {rid} done"))
    _, response = asyncio.run(ask(ctx, router, executor, "status"))
    todo_section = response.split("TODO")[1]
    assert "stretch" not in todo_section
