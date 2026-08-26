import asyncio
from datetime import datetime, timedelta

from core.helper import Helper
from core.events import EventBus

from test_reminders import RecordingNotifier, make, ask


def test_leading_duration_phrase(tmp_path):
    ctx, router, executor = make(tmp_path)
    command, response = asyncio.run(ask(ctx, router, executor, "remind me in 1 minute to go to bathroom"))
    assert "#1" in response and "bathroom" in response
    row = ctx.reminders.list_pending()[0]
    due = datetime.fromisoformat(row["due_at"])
    assert abs(due - (datetime.now() + timedelta(minutes=1))) < timedelta(seconds=15)
    assert row["task"] == "go to bathroom"


def test_leading_at_time_phrase(tmp_path):
    ctx, router, executor = make(tmp_path)
    _, response = asyncio.run(ask(ctx, router, executor, "remind me at 6pm to cook dinner"))
    row = ctx.reminders.list_pending()[0]
    assert row["task"] == "cook dinner"
    assert datetime.fromisoformat(row["due_at"]).hour == 18


def test_timer_starts(tmp_path):
    import re as _re
    ctx, router, executor = make(tmp_path)
    manager = executor.ctx.timers
    for phrase, seconds in [
        ("start a 1 minute timer", 60),
        ("5 minute timer", 300),
        ("timer 30 seconds", 30),
        ("timer for 2 hours", 7200),
    ]:
        command, response = asyncio.run(ask(ctx, router, executor, phrase))
        assert command.intent == "timer.start", phrase
        tid = int(_re.search(r"#(\d+)", response).group(1))
        entry = manager.active[tid]
        assert entry["seconds"] == seconds, phrase


def test_timers_are_async_not_db_rows(tmp_path):
    ctx, router, executor = make(tmp_path)
    before = len(ctx.reminders.list_pending(category="event"))
    asyncio.run(ask(ctx, router, executor, "start a 10 minute timer"))
    assert len(ctx.reminders.list_pending(category="event")) == before


def test_timer_fires_via_helper_as_event(tmp_path):
    """Timers now fire via their own asyncio task, independent of the Helper."""
    ctx, router, executor = make(tmp_path)
    asyncio.run(ask(ctx, router, executor, "start a 10 minute timer"))
    assert len(executor.ctx.timers.active) == 1

    # Helper tick does not consume or fire timers
    helper = Helper(
        ctx.reminders, EventBus(),
        event_notifier=RecordingNotifier(),
        goal_notifier=RecordingNotifier(),
        clock=datetime.now,
    )
    summary = helper.tick()
    assert summary["events"] == 0


def test_appointments_lists_events_only(tmp_path):
    ctx, router, executor = make(tmp_path)
    asyncio.run(ask(ctx, router, executor, "remind me about dentist appointment tomorrow at 10am"))
    asyncio.run(ask(ctx, router, executor, "goal drink water every 2 hours"))

    command, response = asyncio.run(ask(ctx, router, executor, "list appointments"))
    assert command.intent == "calendar.appointments"
    assert "dentist" in response and "Phase 4" in response
    assert "drink water" not in response

    empty_ctx, router2, executor2 = make(tmp_path / "empty")
    _, response = asyncio.run(ask(empty_ctx, router2, executor2, "appointments?"))
    assert "no upcoming" in response


def test_brief_contains_sections(tmp_path):
    ctx, router, executor = make(tmp_path)
    asyncio.run(ask(ctx, router, executor, "remind me about dentist tomorrow at 10am"))
    asyncio.run(ask(ctx, router, executor, "goal drink water every 2 hours"))

    command, response = asyncio.run(ask(ctx, router, executor, "brief"))
    assert command.intent == "assistant.brief"
    assert "TODAY" in response
    assert "UPCOMING" in response
    assert "dentist" in response
    assert "GOALS: 1 active" in response
    assert "Phase 4" in response


def test_good_morning_gives_brief(tmp_path):
    ctx, router, executor = make(tmp_path)
    command, _ = asyncio.run(ask(ctx, router, executor, "good morning"))
    assert command.intent == "assistant.brief"
