import asyncio

import pytest

from core.events import EventBus
from core.executor import Executor
from core.router import IntentRouter
from core.state import AssistantState, StateManager
from services.settings import Settings
from services.system import UnknownApplication, SystemService
from storage.database import Database


@pytest.fixture
def settings(tmp_path):
    return Settings(Database(tmp_path / "test.db"), EventBus())


@pytest.fixture
def executor(settings):
    bus = EventBus()
    states = StateManager(bus)
    system = SystemService()
    system.open_app = lambda name: None
    system.close_app = lambda name: None
    return Executor(bus, states, settings, system), states


async def route_and_execute(router, executor_tuple, text):
    ex, _states = executor_tuple
    command = router.route(text)
    response = await ex.execute(command)
    return command, response


def test_open_firefox(settings, executor):
    router = IntentRouter(settings)
    command, _ = _run(route_and_execute(router, executor, "open Firefox"))
    assert command.intent == "system.open_app"
    assert command.slots["app"] == "Firefox"
    assert command.source == "rule"


def test_percent_calculation(settings, executor):
    router = IntentRouter(settings)
    command, response = _run(route_and_execute(router, executor, "what's 15% of 240?"))
    assert command.intent == "math.calculate"
    assert command.slots["result"] == 36
    assert "36" in response


def test_rename_assistant(settings, executor):
    router = IntentRouter(settings)
    _, response = _run(route_and_execute(router, executor, "call yourself Athena"))
    assert settings.get("assistant_name") == "Athena"
    _, response = _run(route_and_execute(router, executor, "what's your name?"))
    assert "Athena" in response


def test_unknown_goes_to_chat_fallback(settings):
    router = IntentRouter(settings)
    command = router.route("tell me a joke about penguins")
    assert command.intent == "conversation.chat"


def test_permission_denied_unknown_app(settings, executor):
    router = IntentRouter(settings)
    _, response = _run(route_and_execute(router, executor, "open nuclear_launch_console"))
    assert "Permission denied" in response or "allowlist" in response


def test_close_app_routes(settings, executor):
    router = IntentRouter(settings)
    command, _ = _run(route_and_execute(router, executor, "close Firefox"))
    assert command.intent == "system.close_app"


def test_alias_resolution(settings, executor):
    from services.system import normalize
    assert normalize("fire fox") == "firefox"
    assert normalize("my files") == "files"


def _run(coro):
    return asyncio.run(coro)


def test_help_command(settings, executor):
    router = IntentRouter(settings)
    command, response = _run(route_and_execute(router, executor, "help"))
    assert command.intent == "assistant.help"
    assert "Calculator" in response
    for phrase in ("?", "what can you do", "commands", "capabilities"):
        command, response = _run(route_and_execute(router, executor, phrase))
        assert command.intent == "assistant.help"


def test_states_return_to_idle(executor):
    ex, states = executor
    from core.commands import Command
    asyncio.run(ex.execute(Command(intent="assistant.get_name", slots={})))
    assert states.state == AssistantState.IDLE
