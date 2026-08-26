import asyncio
from datetime import datetime

from test_reminders import make, ask


def test_delete_goal_does_not_touch_event(tmp_path):
    ctx, router, executor = make(tmp_path)
    asyncio.run(ask(ctx, router, executor, "remind me to call Sarah at 5pm"))  # event id 1
    asyncio.run(ask(ctx, router, executor, "goal drink water every 2 hours"))  # goal id 2
    _, response = asyncio.run(ask(ctx, router, executor, "delete goal 1"))
    assert "isn't an active goal" in response
    assert ctx.reminders.get(1)["status"] == "pending"
    _, response = asyncio.run(ask(ctx, router, executor, "delete reminder 2"))
    assert "isn't a pending reminder" in response
    assert ctx.reminders.get(2)["status"] == "pending"


def test_done_respects_category(tmp_path):
    ctx, router, executor = make(tmp_path)
    asyncio.run(ask(ctx, router, executor, "goal stretch every 45 minutes"))
    _, response = asyncio.run(ask(ctx, router, executor, "mark reminder 1 done"))
    assert "isn't" in response


def test_reminder_list_excludes_goals(tmp_path):
    ctx, router, executor = make(tmp_path)
    asyncio.run(ask(ctx, router, executor, "remind me to call Sarah at 5pm"))
    asyncio.run(ask(ctx, router, executor, "goal drink water every 2 hours"))
    _, response = asyncio.run(ask(ctx, router, executor, "list reminders"))
    assert "Sarah" in response and "drink water" not in response


def test_timer_labels_use_full_words(tmp_path):
    from intents.rules import match_timer
    cases = {
        "start a 1 minute timer": "1 minute",
        "timer 30 seconds": "30 seconds",
        "5 minute timer": "5 minutes",
        "timer for 2 hours": "2 hours",
        "1 hour timer": "1 hour",
    }
    for phrase, label in cases.items():
        command = match_timer(phrase)
        assert command is not None and command.slots["label"] == label, phrase


def test_calculator_whole_numbers_have_no_decimal(tmp_path):
    ctx, router, executor = make(tmp_path)
    _, response = asyncio.run(ask(ctx, router, executor, "what's 15% of 240?"))
    assert "= 36\n" not in response and response.endswith("= 36")


def test_status_reports_idle_not_executing(tmp_path):
    ctx, router, executor = make(tmp_path)
    _, response = asyncio.run(ask(ctx, router, executor, "status"))
    assert "State: idle" in response
