import asyncio
import json as _json
import threading
import time
from types import SimpleNamespace

from core.commands import Command
from core.events import EventBus
from core.executor import Executor
from core.router import IntentRouter
from core.state import StateManager
from llm.engine import ChatMessage, CompletionResult
from llm.manager import LLMManager
from services.settings import Settings
from storage.database import Database


class FakeLLM:
    """Stand-in for a loaded local model - deterministic and offline."""

    def __init__(self, reply="Hi there! I'm Texx.", memories=None):
        self.reply = reply
        self.memories = memories if memories is not None else []
        self.respond_calls = 0
        self.extract_calls = 0
        self.thread_idents = []

    def is_available(self) -> bool:
        return True

    def chat(self, messages):
        self.respond_calls += 1
        self.thread_idents.append(threading.get_ident())
        return CompletionResult(text=self.reply, raw=self.reply)

    def complete(self, prompt, json_mode=False):
        self.extract_calls += 1
        self.thread_idents.append(threading.get_ident())
        return CompletionResult(text=_json.dumps(self.memories), raw=_json.dumps(self.memories))


class CondenseEngine:
    """Engine that answers non-JSON completions like a real summariser would."""

    def __init__(self, text="- user dislikes meetings"):
        self.text = text

    def is_available(self) -> bool:
        return True

    def chat(self, messages):
        return CompletionResult(text="ok", raw="ok")

    def complete(self, prompt, json_mode=False):
        if json_mode:
            return CompletionResult(text="[]", raw="[]")
        return CompletionResult(text=self.text, raw=self.text)


class SlowEngine:
    """Simulates multi-second llama.cpp inference without the model."""

    def __init__(self, delay=0.15, reply="done"):
        self.delay = delay
        self.reply = reply

    def is_available(self) -> bool:
        return True

    def chat(self, messages):
        time.sleep(self.delay)
        return CompletionResult(text=self.reply, raw=self.reply)

    def complete(self, prompt, json_mode=False):
        return CompletionResult(text="[]", raw="[]")


class OverlapDetectingEngine:
    """Records how many threads are inside the engine at once."""

    def __init__(self):
        self.calls = 0
        self.active = 0
        self.max_active = 0
        self._guard = threading.Lock()

    def _enter(self):
        with self._guard:
            self.calls += 1
            self.active += 1
            self.max_active = max(self.max_active, self.active)

    def _exit(self):
        with self._guard:
            self.active -= 1

    def is_available(self) -> bool:
        return True

    def chat(self, messages):
        self._enter()
        try:
            time.sleep(0.02)
            return CompletionResult(text="ok", raw="ok")
        finally:
            self._exit()

    def complete(self, prompt, json_mode=False):
        return CompletionResult(text="[]", raw="[]")


def make(tmp_path, engine=None):
    db = Database(tmp_path / "t.db")
    settings = Settings(db, EventBus())
    states = StateManager(EventBus())
    router = IntentRouter(settings)
    system = SimpleNamespace(open_map=lambda: {}, close_map=lambda: {})
    llm = None
    if engine is not None:
        from llm.manager import LLMManager
        llm = LLMManager("dummy")
        llm._engine = engine
    executor = Executor(EventBus(), states, settings, system, llm=llm)
    return executor.ctx, router, executor


async def ask(ctx, router, executor, text):
    cmd = router.route(text)
    response = await executor.execute(cmd)
    return cmd, response


class TestLLMManager:
    def test_unavailable_without_model(self):
        mgr = LLMManager(None)
        assert not mgr.is_available()
        assert mgr.respond("hello") == ""
        assert mgr.extract_memories("x") == []

    def test_respond_uses_engine(self):
        llm = FakeLLM(reply="Hello, human.")
        mgr = LLMManager("dummy")
        mgr._engine = llm
        assert mgr.is_available()
        out = mgr.respond("hi")
        assert out == "Hello, human."

    def test_extract_memories_parses_json(self):
        llm = FakeLLM(memories=[
            {"content": "I prefer dark mode", "category": "PREFERENCE", "importance": 6},
        ])
        mgr = LLMManager("dummy")
        mgr._engine = llm
        result = mgr.extract_memories("User: I prefer dark mode\nTexx: ok")
        assert len(result) == 1
        assert result[0]["content"] == "I prefer dark mode"
        assert result[0]["category"] == "PREFERENCE"


class TestConversationFallback:
    def test_fallback_when_no_llm(self, tmp_path):
        ctx, router, executor = make(tmp_path)  # llm=None -> UnavailableEngine
        _, response = asyncio.run(ask(ctx, router, executor, "tell me a joke"))
        assert "conversational" in response.lower() or "local" in response.lower()

    def test_chat_uses_llm_and_stores_memories(self, tmp_path):
        llm = FakeLLM(
            reply="Noted!",
            memories=[{"content": "User dislikes meetings", "category": "PREFERENCE", "importance": 7}],
        )
        ctx, router, executor = make(tmp_path, engine=llm)
        _, response = asyncio.run(ask(ctx, router, executor, "I really dislike meetings"))
        assert response == "Noted!"
        stored = ctx.memory.search("meetings")
        assert any("meetings" in m["content"].lower() for m in stored)


class TestCondenseIsOnTheManager:
    """Regression guard for a bug the fakes hid.

    ``services/memory.py`` and ``services/owner.py`` call ``llm.condense(...)``
    on whatever object they are handed, which in production is an
    ``LLMManager``. ``condense`` used to exist only on the *test* fakes, so the
    real manager raised ``AttributeError`` — swallowed by ``except Exception`` —
    and every daily summary and OWNER.md regeneration silently degraded to raw
    concatenation while the suite stayed green.
    """

    def test_manager_exposes_condense(self):
        assert callable(getattr(LLMManager, "condense", None))

    def test_condense_returns_engine_text(self):
        mgr = LLMManager("dummy")
        mgr._engine = CondenseEngine()
        assert mgr.condense("long ramble about meetings") == "- user dislikes meetings"

    def test_condense_swallows_nothing_worth_keeping(self):
        mgr = LLMManager("dummy")
        mgr._engine = CondenseEngine(text="(nothing worth keeping)")
        assert mgr.condense("hi") == ""

    def test_condense_empty_when_unavailable(self):
        assert LLMManager(None).condense("anything") == ""

    def test_daily_summary_uses_real_manager_not_a_fallback(self, tmp_path):
        from datetime import datetime
        from services.memory import MemoryService

        ms = MemoryService(Database(tmp_path / "m.db"))
        yest = datetime(2026, 2, 28, 10, 0, 0)
        ms.add_discussion("user said alpha", role="user", now=yest)

        mgr = LLMManager("dummy")
        mgr._engine = CondenseEngine()
        assert ms.summarize_yesterday_discussion(llm=mgr, now=datetime(2026, 3, 1, 9, 0, 0)) == 1

        daily = ms.db.query("SELECT * FROM memories WHERE layer='daily'")
        assert daily[0]["content"] == "- user dislikes meetings"
        assert not daily[0]["content"].startswith("Working context:")

    def test_owner_regen_uses_real_manager(self, tmp_path):
        from datetime import datetime
        from services.owner import OwnerProfile

        owner = OwnerProfile(path=tmp_path / "OWNER.md")
        mgr = LLMManager("dummy")
        mgr._engine = CondenseEngine()
        assert owner.regen([{"content": "User dislikes meetings", "category": "PREFERENCE"}],
                           llm=mgr, now=datetime(2026, 3, 1, 9, 0, 0), force=True) is True
        assert owner.read() == "- user dislikes meetings"


class TestInferenceStaysOffTheEventLoop:
    """Inference is seconds of CPU-bound llama.cpp work. Called inline it
    freezes the loop, so timers/reminders stop firing on time and the TUI stops
    repainting. These tests fail if anyone drops the ``asyncio.to_thread``."""

    def test_chat_inference_runs_on_a_worker_thread(self, tmp_path):
        llm = FakeLLM(reply="threaded")
        ctx, router, executor = make(tmp_path, engine=llm)
        loop_thread = threading.get_ident()
        _, response = asyncio.run(ask(ctx, router, executor, "hello there"))
        assert response == "threaded"
        assert llm.thread_idents, "engine was never called"
        assert loop_thread not in llm.thread_idents, "inference ran inline on the event loop"

    def test_event_loop_keeps_ticking_during_inference(self, tmp_path):
        llm = SlowEngine(delay=0.15)
        ctx, router, executor = make(tmp_path, engine=llm)
        stamps = []

        async def scenario():
            # Stamp before the task exists: with inline inference the very first
            # sleep overshoots by the whole inference duration, which is exactly
            # the stall we are detecting.
            stamps.append(time.perf_counter())
            task = asyncio.create_task(ask(ctx, router, executor, "hello there"))
            for _ in range(10):
                await asyncio.sleep(0.01)
                stamps.append(time.perf_counter())
            return await task

        _, response = asyncio.run(scenario())
        assert response == "done"
        gaps = [b - a for a, b in zip(stamps, stamps[1:])]
        assert len(stamps) == 11
        assert max(gaps) < 0.06, (
            f"loop stalled for {max(gaps):.3f}s while the model ran "
            f"(gaps: {[round(g, 3) for g in gaps]})"
        )

    def test_concurrent_calls_are_serialized(self):
        """The worker thread and the Helper tick can both reach the engine, and
        a llama.cpp handle is not safe for concurrent use."""
        engine = OverlapDetectingEngine()
        mgr = LLMManager("dummy")
        mgr._engine = engine
        threads = [threading.Thread(target=mgr.respond, args=(f"q{i}",)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert engine.calls == 4
        assert engine.max_active == 1, "engine entered concurrently despite the lock"


class TestLLMSlash:
    def test_status_unavailable(self, tmp_path):
        ctx, router, executor = make(tmp_path)
        from core.slash import handle
        out = asyncio.run(handle("/llm", ctx))
        assert "not active" in out.lower() or "not initialized" in out.lower()

    def test_set_path_updates_settings(self, tmp_path):
        ctx, router, executor = make(tmp_path)
        from core.slash import handle
        model_file = tmp_path / "model.gguf"
        model_file.write_text("fake")
        out = asyncio.run(handle(f"/llm set {model_file}", ctx))
        assert ctx.settings.get("llm_model_path") == str(model_file)
        assert "can't be loaded" in out.lower() or "disabled" in out.lower()
