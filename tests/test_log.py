import asyncio
import os
from types import SimpleNamespace

import pytest

import services.log as L
from core.events import EventBus
from core.executor import Executor
from core.router import IntentRouter
from core.state import StateManager
from services.log import recent
from services.settings import Settings
from storage.database import Database


def _reset_logger():
    import logging
    lg = logging.getLogger("texx")
    for h in list(lg.handlers):
        lg.removeHandler(h)
        h.close()
    lg.handlers = []
    L._logger = None


def test_log_writes_and_recent(tmp_path):
    os.environ["HOME"] = str(tmp_path)
    _reset_logger()
    from services.log import log_error, log_fault
    log_error("boom", intent="x")
    log_fault("net down", error="OfflineError")
    lines = recent(10)
    assert any("boom" in l for l in lines)
    assert any("FAULT" in l and "net down" in l for l in lines)


def test_executor_logs_fault_on_llm_fallback(tmp_path, monkeypatch):
    import core.executor as EX
    captured = []
    monkeypatch.setattr(EX, "log_fault", lambda msg, **kw: captured.append(msg))

    db = Database(tmp_path / "x.db")
    settings = Settings(db, EventBus())
    states = StateManager(EventBus())
    system = SimpleNamespace(open_map=lambda: {}, close_map=lambda: {})
    executor = Executor(EventBus(), states, settings, system)
    router = IntentRouter(settings)

    command = router.route("a totally random utterance with no deterministic intent")
    assert command.source == "fallback"
    asyncio.run(executor.execute(command))
    assert any("fallback" in m for m in captured)


def test_slash_log_returns_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "recent", lambda n=40: ["2026-01-01 INFO hello", "2026-01-01 FAULT oops"])
    from core import slash
    out = asyncio.run(slash.handle("/log", SimpleNamespace()))
    assert "hello" in out and "oops" in out
    out5 = asyncio.run(slash.handle("/log 5", SimpleNamespace()))
    assert "hello" in out5
