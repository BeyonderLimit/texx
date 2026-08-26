import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

from core.commands import Command
from core.events import EventBus
from core.executor import Executor
from core.router import IntentRouter
from core.state import StateManager
from services.settings import Settings
from storage.database import Database


def make(tmp_path):
    db = Database(tmp_path / "mem.db")
    settings = Settings(db, EventBus())
    states = StateManager(EventBus())
    system = SimpleNamespace(open_map=lambda: {}, close_map=lambda: {})
    executor = Executor(EventBus(), states, settings, system)
    router = IntentRouter(settings)
    ctx = SimpleNamespace(settings=settings, states=states, system=system,
                          reminders=executor.ctx.reminders, time=executor.ctx.time,
                          memory=executor.ctx.memory)
    return ctx, router, executor


async def ask(ctx, router, executor, text):
    command = router.route(text)
    return command, await executor.execute(command)


def test_remember_that_stores_memory(tmp_path):
    ctx, router, executor = make(tmp_path)
    command, response = asyncio.run(
        ask(ctx, router, executor, "remember that I'm working on project Texx"))
    assert command.intent == "memory.store"
    assert "[PROJECT]" in response and "#1" in response
    assert ctx.memory.count() == 1


def test_remember_to_routes_to_reminder(tmp_path):
    ctx, router, executor = make(tmp_path)
    command, response = asyncio.run(
        ask(ctx, router, executor, "remember to call John in 1 hour"))
    assert command.intent == "reminder.create"
    assert ctx.memory.count() == 0
    assert len(ctx.reminders.list_pending()) == 1


def test_category_classification():
    from services.memory import classify_memory
    assert classify_memory("My name is Sam")[0] == "PROFILE"
    assert classify_memory("I prefer concise answers")[0] == "PREFERENCE"
    assert classify_memory("John is my friend")[0] == "PEOPLE"
    assert classify_memory("I own a Raspberry Pi")[0] == "FACT"


def test_explicit_boosts_importance_and_source(tmp_path):
    ctx, router, executor = make(tmp_path)
    asyncio.run(ask(ctx, router, executor, "remember that my name is Sam"))
    row = ctx.memory.get(1)
    assert row["source"] == "explicit"
    assert row["category"] == "PROFILE"
    assert row["importance"] >= 9


def test_recall_finds_and_bumps_access(tmp_path):
    ctx, router, executor = make(tmp_path)
    asyncio.run(ask(ctx, router, executor, "remember that I'm building Texx offline"))
    command, response = asyncio.run(ask(ctx, router, executor, "what do you remember about Texx?"))
    assert command.intent == "memory.recall"
    assert "building Texx" in response
    assert ctx.memory.get(1)["access_count"] == 1


def test_recall_empty_state(tmp_path):
    ctx, router, executor = make(tmp_path)
    _, response = asyncio.run(ask(ctx, router, executor, "recall penguins"))
    assert "Nothing in memory" in response


def test_forget_by_id_and_query(tmp_path):
    ctx, router, executor = make(tmp_path)
    asyncio.run(ask(ctx, router, executor, "remember that I own a Raspberry Pi"))
    _, response = asyncio.run(ask(ctx, router, executor, "forget #1"))
    assert "Forgot" in response and ctx.memory.count() == 0

    asyncio.run(ask(ctx, router, executor, "remember that my landlord is Bob"))
    _, response = asyncio.run(ask(ctx, router, executor, "forget about landlord"))
    assert "Forgot" in response and ctx.memory.count() == 0


def test_forget_ambiguous_lists_options(tmp_path):
    ctx, router, executor = make(tmp_path)
    asyncio.run(ask(ctx, router, executor, "remember that project Alpha uses rust"))
    asyncio.run(ask(ctx, router, executor, "remember that project Beta uses go"))
    _, response = asyncio.run(ask(ctx, router, executor, "forget about project"))
    assert "Forget which one?" in response
    assert "#1" in response and "#2" in response


def test_memory_list(tmp_path):
    ctx, router, executor = make(tmp_path)
    _, response = asyncio.run(ask(ctx, router, executor, "what do you remember?"))
    assert "empty" in response.lower()
    asyncio.run(ask(ctx, router, executor, "remember that I like python"))
    _, response = asyncio.run(ask(ctx, router, executor, "list memories"))
    assert "[PREFERENCE]" in response and "python" in response


def test_expired_memories_purged_and_hidden(tmp_path):
    from services.memory import MemoryService
    service = MemoryService(Database(tmp_path / "exp.db"))
    past = datetime.now() - timedelta(days=1)
    service.add("temp note", expires_at=past)
    service.add("lasting note")

    purged = service.purge_expired()
    assert purged == 1
    assert service.count() == 1
    results = service.search("temp note")
    assert results == []


def test_fts_search_matches_words(tmp_path):
    from services.memory import MemoryService
    service = MemoryService(Database(tmp_path / "fts.db"))
    service.add("The Raspberry Pi Zero 2 W is tiny")
    service.add("Completely unrelated fact about coffee")
    results = service.search("raspberry")
    assert len(results) == 1


def test_ranking_prefers_explicit_and_recent(tmp_path):
    from services.memory import MemoryService
    service = MemoryService(Database(tmp_path / "rank.db"))
    old_id = service.add("old fact about pizza", source="user")
    new_id = service.add("new fact about pizza", source="explicit")
    results = service.search("pizza")
    assert results[0]["id"] in (old_id, new_id)
    scores = [service._score(r, datetime.now()) for r in results]
    by_id = {r["id"]: s for r, s in zip(results, scores)}
    assert by_id[new_id] >= by_id[old_id]


def test_remember_my_name_is_two_words_not_dropped(tmp_path):
    ctx, router, executor = make(tmp_path)
    _, response = asyncio.run(ask(ctx, router, executor, "remember my cat is called Whiskers"))
    assert "#1" in response
