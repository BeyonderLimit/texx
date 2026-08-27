import asyncio
import json as _json
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

    def is_available(self) -> bool:
        return True

    def chat(self, messages):
        self.respond_calls += 1
        return CompletionResult(text=self.reply, raw=self.reply)

    def complete(self, prompt, json_mode=False):
        self.extract_calls += 1
        return CompletionResult(text=_json.dumps(self.memories), raw=_json.dumps(self.memories))


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
