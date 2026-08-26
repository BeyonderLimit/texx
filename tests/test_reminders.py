import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

from core.commands import Command
from core.events import EventBus
from core.executor import Executor
from core.helper import Helper
from core.router import IntentRouter
from core.state import StateManager
from services.reminders import ReminderService
from services.settings import Settings
from storage.database import Database


class RecordingNotifier:
    def __init__(self):
        self.calls = []

    def notify(self, title, body):
        self.calls.append((title, body))


def make(tmp_path):
    db = Database(tmp_path / "rem.db")
    settings = Settings(db, EventBus())
    states = StateManager(EventBus())
    system = SimpleNamespace(open_map=lambda: {}, close_map=lambda: {})
    executor = Executor(EventBus(), states, settings, system)
    router = IntentRouter(settings)
    ctx = SimpleNamespace(settings=settings, states=states, system=system,
                          reminders=executor.ctx.reminders, time=executor.ctx.time,
                          memory=executor.ctx.memory, tasks=executor.ctx.tasks)
    return ctx, router, executor


async def ask(ctx, router, executor, text):
    command = router.route(text)
    response = await executor.execute(command)
    return command, response


def test_relative_reminder(tmp_path):
    ctx, router, executor = make(tmp_path)
    command, response = asyncio.run(ask(ctx, router, executor, "remind me to leave in 10 minutes"))
    assert command.intent == "reminder.create"
    assert "#1" in response and "leave" in response
    rows = ctx.reminders.list_pending()
    assert len(rows) == 1
    due = datetime.fromisoformat(rows[0]["due_at"])
    expected = datetime.now() + timedelta(minutes=10)
    assert abs(due - expected) < timedelta(seconds=15)


def test_absolute_time_reminder(tmp_path):
    ctx, router, executor = make(tmp_path)
    _, response = asyncio.run(ask(ctx, router, executor, "remind me to call Sarah at 5pm"))
    row = ctx.reminders.list_pending()[0]
    due = datetime.fromisoformat(row["due_at"])
    assert (due.hour, due.minute) == (17, 0)
    now = datetime.now()
    if now.hour >= 17:
        assert due.date() > now.date()


def test_recurring_reminder(tmp_path):
    ctx, router, executor = make(tmp_path)
    _, response = asyncio.run(ask(ctx, router, executor, "remind me to take an injection every friday morning"))
    row = ctx.reminders.list_pending()[0]
    assert row["recurrence_rule"] == "FREQ=WEEKLY;BYDAY=FR"
    due = datetime.fromisoformat(row["due_at"])
    assert due.weekday() == 4 and due.hour == 9


def test_reminder_without_time_asks_when(tmp_path):
    ctx, router, executor = make(tmp_path)
    _, response = asyncio.run(ask(ctx, router, executor, "remind me to call John"))
    assert "When?" in response
    assert ctx.reminders.list_pending() == []


def test_list_done_and_delete(tmp_path):
    ctx, router, executor = make(tmp_path)
    asyncio.run(ask(ctx, router, executor, "remind me to stretch in 2 hours"))
    rid = ctx.reminders.list_pending()[0]["id"]
    _, response = asyncio.run(ask(ctx, router, executor, f"mark reminder {rid} done"))
    assert "marked done" in response
    assert ctx.reminders.list_pending() == []

    rid2 = asyncio.run(_create(ctx, router, executor, "remind me to eat in 1 hour"))
    _, response = asyncio.run(ask(ctx, router, executor, f"delete reminder {rid2}"))
    assert "cancelled" in response


async def _create(ctx, router, executor, text):
    command = router.route(text)
    await executor.execute(command)
    return ctx.reminders.list_pending()[0]["id"]


def test_scheduler_fires_and_reschedules(tmp_path):
    ctx, _, _ = make(tmp_path)
    reminders = ReminderService(Database(tmp_path / "sched.db"))
    now = datetime.now().replace(second=0, microsecond=0)

    one_shot = reminders.add("one shot", due_at=now - timedelta(minutes=1))
    recurring = reminders.add("recurring", due_at=now - timedelta(minutes=1),
                              recurrence_rule="FREQ=DAILY")

    event_notifier = RecordingNotifier()
    helper = Helper(
        reminders, EventBus(), event_notifier=event_notifier,
        goal_notifier=RecordingNotifier(),
        mode_fn=lambda: "normal",
        clock=lambda: now + timedelta(seconds=30),
    )
    summary = helper.tick()

    assert summary["events"] == 2
    one = reminders.get(one_shot)
    rec = reminders.get(recurring)
    assert one["notification_sent_at"] is not None
    assert rec["notification_sent_at"] is not None
    next_due = datetime.fromisoformat(rec["due_at"])
    assert next_due > now
    assert reminders.get_due(now + timedelta(days=2)) == []
    assert len(event_notifier.calls) == 2


def test_daily_recurrence_next_occurrence(tmp_path):
    service = ReminderService(Database(tmp_path / "rec.db"))
    after = datetime(2026, 8, 25, 9, 0)
    nxt = service.next_from_recurrence("FREQ=DAILY", after)
    assert (nxt.year, nxt.month, nxt.day) == (2026, 8, 26)


def test_weekly_recurrence_next_occurrence(tmp_path):
    service = ReminderService(Database(tmp_path / "rec2.db"))
    friday = datetime(2026, 8, 28, 9, 0)
    assert friday.weekday() == 4
    nxt = service.next_from_recurrence("FREQ=WEEKLY;BYDAY=FR", friday)
    assert (nxt - friday).days == 7


def test_parser_units():
    from intents.dates import parse_when, split_task_and_when
    now = datetime(2026, 8, 25, 14, 0)

    task, when = split_task_and_when("call Sarah at 5pm")
    assert task == "call Sarah" and when.lower() == "at 5pm"

    due, rule = parse_when("in 10 minutes", now)
    assert due == now + timedelta(minutes=10) and rule is None

    due, rule = parse_when("tomorrow at 9am", now)
    assert (due.month, due.day) == (8, 26) and (due.hour, due.minute) == (9, 0)

    due, rule = parse_when("every day at 8am", now)
    assert rule == "FREQ=DAILY" and due.hour == 8

    due, rule = parse_when("at 17:30", now)
    assert (due.hour, due.minute) == (17, 30)

    due, rule = parse_when("gibberish nonsense", now)
    assert due is None and rule is None
