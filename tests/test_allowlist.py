import asyncio
from types import SimpleNamespace

from core.commands import Command
from core.events import EventBus
from core.executor import Executor
from core.router import IntentRouter
from core.state import AssistantState, StateManager
from services.settings import Settings
from services.system import SystemService
from storage.database import Database


def make(tmp_path):
    settings = Settings(Database(tmp_path / "allow.db"), EventBus())
    states = StateManager(EventBus())
    system = SystemService(settings)
    executor = Executor(EventBus(), states, settings, system)
    router = IntentRouter(settings)
    ctx = SimpleNamespace(settings=settings, states=states, system=system)
    return ctx, router, executor


async def ask(ctx, router, executor, text):
    command = router.route(text)
    return command, await executor.execute(command)


def test_deny_message_includes_hint(tmp_path):
    ctx, router, executor = make(tmp_path)
    _, response = asyncio.run(ask(ctx, router, executor, "open featherpad"))
    assert "not on the open allowlist" in response
    assert "/allow open featherpad" in response


def test_allow_then_open_custom_app(tmp_path):
    ctx, router, executor = make(tmp_path)
    launched = {}
    ctx.system.open_app = lambda name: launched.__setitem__("name", name)
    response = asyncio.run(_slash(ctx, "/allow open featherpad featherpad"))
    assert "added to the open allowlist" in response
    _, response = asyncio.run(ask(ctx, router, executor, "open featherpad"))
    assert launched["name"] == "featherpad"
    assert "Opening" in response


def test_disallow_removes(tmp_path):
    ctx, _, _ = make(tmp_path)
    asyncio.run(_slash(ctx, "/allow close myapp myproc"))
    response = asyncio.run(_slash(ctx, "/disallow close myapp"))
    assert "removed" in response
    assert "myapp" not in ctx.system.close_map()


def test_defaults_survive_and_persist(tmp_path):
    ctx, _, _ = make(tmp_path)
    asyncio.run(_slash(ctx, "/allow open editor gedit"))
    assert ctx.system.open_map()["firefox"] == ["firefox"]
    fresh = SystemService(ctx.settings)
    assert fresh.open_map()["editor"] == ["gedit"]


def test_disallow_removes_default_open_app(tmp_path):
    ctx, _, _ = make(tmp_path)
    asyncio.run(_slash(ctx, "/allow open firefox firefox --new-tab"))
    assert "firefox" in ctx.system.open_map()
    response = asyncio.run(_slash(ctx, "/disallow open firefox"))
    assert "removed" in response
    # The built-in default must actually be gone, not just the custom override.
    assert "firefox" not in ctx.system.open_map()
    # and survive a fresh service reading the same settings
    assert "firefox" not in SystemService(ctx.settings).open_map()


def test_disallow_then_reallow_default(tmp_path):
    ctx, _, _ = make(tmp_path)
    asyncio.run(_slash(ctx, "/disallow open firefox"))
    assert "firefox" not in ctx.system.open_map()
    asyncio.run(_slash(ctx, "/allow open firefox firefox"))
    assert "firefox" in ctx.system.open_map()


def test_disallow_close_default_app(tmp_path):
    ctx, _, _ = make(tmp_path)
    asyncio.run(_slash(ctx, "/allow close spotify spotify"))
    assert "spotify" in ctx.system.close_map()
    response = asyncio.run(_slash(ctx, "/disallow close spotify"))
    assert "removed" in response
    assert "spotify" not in ctx.system.close_map()


def test_disallow_unknown_reports_not_on_list(tmp_path):
    ctx, _, _ = make(tmp_path)
    response = asyncio.run(_slash(ctx, "/disallow open doesnotexist"))
    assert "wasn't on the open allowlist" in response


async def _slash(ctx, text):
    from core import slash
    return await slash.handle(text, ctx)
