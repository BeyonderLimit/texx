import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

from test_reminders import make, ask


def test_add_task_default_priority(tmp_path):
    ctx, router, executor = make(tmp_path)
    command, response = asyncio.run(ask(ctx, router, executor, "task buy milk"))
    assert command.intent == "task.add"
    assert "#1" in response and "[NORMAL]" in response
    row = ctx.tasks.get(1)
    assert row["title"] == "buy milk" and row["priority"] == "normal"


def test_task_with_priority(tmp_path):
    ctx, router, executor = make(tmp_path)
    for phrase in ("task pay rent with high priority", "todo urgent priority call boss",
                   "add task x low priority"):
        asyncio.run(ask(ctx, router, executor, phrase))
    rows = ctx.tasks.list_open()
    assert rows[0]["priority"] == "urgent"
    assert rows[0]["title"] == "call boss"
    assert rows[1]["priority"] == "high"
    assert rows[2]["priority"] == "low"


def test_task_ttl_expiration(tmp_path):
    from services.tasks import TaskService
    from storage.database import Database
    service = TaskService(Database(tmp_path / "ttl.db"))
    past = datetime.now() - timedelta(hours=1)
    service.add("temp task", expires_at=past)
    service.add("lasting task")

    purged = service.purge_expired()
    assert purged == 1 and service.list_open()[0]["title"] == "lasting task"

    ctx, router, executor = make(tmp_path / "add")
    _, response = asyncio.run(ask(ctx, router, executor, "task water plants for 3 days"))
    assert "expires" in response


def test_task_list_done_delete(tmp_path):
    ctx, router, executor = make(tmp_path)
    asyncio.run(ask(ctx, router, executor, "task buy milk"))
    rid = ctx.tasks.list_open()[0]["id"]

    _, response = asyncio.run(ask(ctx, router, executor, "list tasks"))
    assert "buy milk" in response

    _, response = asyncio.run(ask(ctx, router, executor, f"complete task {rid}"))
    assert "completed" in response

    asyncio.run(ask(ctx, router, executor, "task second thing"))
    _, response = asyncio.run(ask(ctx, router, executor, "delete task 2"))
    assert "deleted" in response
    assert ctx.tasks.list_open() == []


def test_tasks_sorted_by_priority_then_age(tmp_path):
    ctx, router, executor = make(tmp_path)
    asyncio.run(ask(ctx, router, executor, "task low priority zzz"))
    asyncio.run(ask(ctx, router, executor, "task first normal"))
    asyncio.run(ask(ctx, router, executor, "task high priority aaa"))
    order = [r["priority"] for r in ctx.tasks.list_open()]
    assert order == ["high", "normal", "low"]


def test_notes_take_and_list(tmp_path):
    ctx, router, executor = make(tmp_path)
    _, response = asyncio.run(ask(ctx, router, executor, "note: wifi password is hunter2"))
    assert response.startswith("Note #1:")
    _, response = asyncio.run(ask(ctx, router, executor, "take a note return library books"))
    _, response = asyncio.run(ask(ctx, router, executor, "list notes"))
    assert "hunter2" in response and "library books" in response


def test_note_stored_as_memory_category(tmp_path):
    ctx, router, executor = make(tmp_path)
    asyncio.run(ask(ctx, router, executor, "note: idea for later"))
    row = ctx.memory.get(1)
    assert row["category"] == "NOTE"


def test_brief_excludes_past_due_today(tmp_path):
    ctx, router, executor = make(tmp_path)
    # overdue event reminder (due 1 hour ago, already notified)
    ctx.reminders.add("stale event", due_at=datetime.now() - timedelta(hours=1))
    future = datetime.now() + timedelta(hours=3)
    ctx.reminders.add("real event", due_at=future)

    command, response = asyncio.run(ask(ctx, router, executor, "brief"))
    assert command.intent == "assistant.brief"
    assert "real event" in response
    assert "stale event" not in response.split("UPCOMING")[0].split("TODAY")[1]


def test_status_todo_uses_tasks_not_reminders(tmp_path):
    ctx, router, executor = make(tmp_path)
    asyncio.run(ask(ctx, router, executor, "remind me to stretch in 30 minutes"))
    asyncio.run(ask(ctx, router, executor, "task actually a todo"))
    _, response = asyncio.run(ask(ctx, router, executor, "status"))
    todo_section = response.split("TODO")[1]
    assert "actually a todo" in todo_section
