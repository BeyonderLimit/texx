import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

from core.events import EventBus
from core.executor import Executor
from core.helper import Helper
from core.router import IntentRouter
from core.state import StateManager
from services.reminders import ReminderService
from services.settings import Settings
from storage.database import Database

from test_reminders import RecordingNotifier, make


async def ask(ctx, router, executor, text):
    command = router.route(text)
    return await executor.execute(command)


def make_helper(tmp_path, mode="normal"):
    reminders = ReminderService(Database(tmp_path / "helper.db"))
    event_notifier = RecordingNotifier()
    goal_notifier = RecordingNotifier()
    alerts = []
    helper = Helper(
        reminders, EventBus(),
        event_notifier=event_notifier,
        goal_notifier=goal_notifier,
        alerter=SimpleNamespace(notify=lambda t, b: alerts.append((t, b))),
        mode_fn=lambda: mode,
        clock=lambda: NOW,
    )
    return reminders, helper, event_notifier, goal_notifier, alerts


NOW = datetime.now().replace(second=0, microsecond=0)


def test_event_reminders_weekly_and_daily(tmp_path):
    ctx, router, executor = make(tmp_path)
    response = asyncio.run(ask(ctx, router, executor, "remind me about team meeting every thursday at 9am"))
    assert "#1" in response and "repeats" in response
    row = ctx.reminders.list_pending(category="event")[0]
    assert row["recurrence_rule"] == "FREQ=WEEKLY;BYDAY=TH"
    from datetime import datetime as dt
    due = dt.fromisoformat(row["due_at"])
    assert due.weekday() == 3 and due.hour == 9

    asyncio.run(ask(ctx, router, executor, "goal take meds every morning at 7am"))
    row = ctx.reminders.list_pending(category="goal")[0]
    assert row["recurrence_rule"] == "FREQ=DAILY"
    due = dt.fromisoformat(row["due_at"])
    assert due.hour == 7


def test_goal_intervals(tmp_path):
    ctx, router, executor = make(tmp_path)
    asyncio.run(ask(ctx, router, executor, "goal drink water every 2 hours"))
    asyncio.run(ask(ctx, router, executor, "stand up and stretch every 45 minutes"))
    rules = {r["recurrence_rule"] for r in ctx.reminders.list_pending(category="goal")}
    assert rules == {"FREQ=HOURLY;INTERVAL=2", "FREQ=MINUTELY;INTERVAL=45"}
    assert all(r["category"] == "goal" for r in ctx.reminders.list_pending())


def test_goal_without_interval_asks(tmp_path):
    ctx, router, executor = make(tmp_path)
    response = asyncio.run(ask(ctx, router, executor, "goal drink more water"))
    assert "How often" in response
    assert ctx.reminders.list_pending(category="goal") == []


def test_goal_list_and_delete(tmp_path):
    ctx, router, executor = make(tmp_path)
    asyncio.run(ask(ctx, router, executor, "goal drink water every 2 hours"))
    rid = ctx.reminders.list_pending(category="goal")[0]["id"]
    response = asyncio.run(ask(ctx, router, executor, "list goals"))
    assert "drink water" in response
    response = asyncio.run(ask(ctx, router, executor, f"delete goal {rid}"))
    assert "removed" in response
    assert ctx.reminders.list_pending(category="goal") == []


def test_mode_set_and_query(tmp_path):
    ctx, router, executor = make(tmp_path)
    response = asyncio.run(ask(ctx, router, executor, "dnd"))
    assert ctx.settings.get("mode") == "dnd"
    response = asyncio.run(ask(ctx, router, executor, "silent mode"))
    assert ctx.settings.get("mode") == "silent"
    response = asyncio.run(ask(ctx, router, executor, "turn off dnd"))
    assert ctx.settings.get("mode") == "normal"
    response = asyncio.run(ask(ctx, router, executor, "what mode am I in?"))
    assert "NORMAL" in response


def test_helper_events_outrank_goals(tmp_path):
    reminders, helper, ev, go, alerts = make_helper(tmp_path)
    reminders.add("meeting", due_at=NOW - timedelta(minutes=1), category="event")
    reminders.add("drink water", due_at=NOW - timedelta(minutes=30),
                  recurrence_rule="FREQ=HOURLY;INTERVAL=2", category="goal")

    summary = helper.tick()

    assert summary["events"] == 1
    assert summary["goals"] == 0
    assert summary["deferred_goals"] is True
    assert len(ev.calls) == 1 and not go.calls

    summary2 = helper.tick()
    assert summary2["goals"] == 1
    assert len(go.calls) == 1


def test_helper_dnd_suppresses_goals_and_audio(tmp_path):
    reminders, helper, ev, go, alerts = make_helper(tmp_path, mode="dnd")
    reminders.add("meeting", due_at=NOW - timedelta(minutes=1),
                  recurrence_rule="FREQ=DAILY", category="event")
    reminders.add("stretch", due_at=NOW - timedelta(minutes=5),
                  recurrence_rule="FREQ=MINUTELY;INTERVAL=45", category="goal")

    summary = helper.tick()

    assert summary["events"] == 1
    assert summary["pending_goals"] == 1
    assert summary["deferred_goals"] is True
    assert alerts == []  # dnd: no audio even for events
    # goal untouched: still pending, never fired
    assert reminders.get_due(NOW + timedelta(days=365), category="goal")


def test_helper_silent_mode_visual_only(tmp_path):
    reminders, helper, ev, go, alerts = make_helper(tmp_path, mode="silent")
    reminders.add("stretch", due_at=NOW - timedelta(minutes=5),
                  recurrence_rule="FREQ=MINUTELY;INTERVAL=45", category="goal")
    reminders.add("meeting", due_at=NOW - timedelta(minutes=1), category="event")

    summary = helper.tick()
    assert summary["events"] == 1
    assert alerts == []

    summary2 = helper.tick()
    assert summary2["goals"] == 1
    assert alerts == []


def test_helper_normal_mode_audible_goals(tmp_path):
    reminders, helper, ev, go, alerts = make_helper(tmp_path, mode="normal")
    reminders.add("drink water", due_at=NOW - timedelta(minutes=10),
                  recurrence_rule="FREQ=HOURLY;INTERVAL=2", category="goal")
    summary = helper.tick()
    assert summary["goals"] == 1
    assert len(alerts) == 1


def test_helper_reschedules_goal_after_fire(tmp_path):
    reminders, helper, ev, go, alerts = make_helper(tmp_path)
    gid = reminders.add("drink water", due_at=NOW - timedelta(minutes=10),
                        recurrence_rule="FREQ=HOURLY;INTERVAL=2", category="goal")
    helper.tick()
    goal = reminders.get(gid)
    next_due = datetime.fromisoformat(goal["due_at"])
    expected = datetime.fromisoformat(goal["due_at"])
    assert next_due > NOW
    assert (next_due - NOW) <= timedelta(hours=2, minutes=1)
