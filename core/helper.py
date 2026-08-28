import asyncio
from datetime import datetime

from core.events import Event, EventBus, EventType


MODE_NORMAL = "normal"
MODE_SILENT = "silent"
MODE_DND = "dnd"


class Helper:
    """Background assistant loop.

    Priority contract: scheduled events always outrank helper announcements.
    In a given tick, if any events fired, goal announcements are deferred to
    the next tick. Audio is gated by mode:
      normal -> visual + audio; silent -> visual only; dnd -> events visual
      only, goals fully paused.
    """

    def __init__(self, reminders, bus: EventBus, event_notifier, goal_notifier,
                 alerter=None, mode_fn=None, interval: float = 60.0, clock=None,
                 memory=None, owner=None, llm=None):
        self.reminders = reminders
        self.bus = bus
        self.event_notifier = event_notifier
        self.goal_notifier = goal_notifier
        self.alerter = alerter
        self.mode_fn = mode_fn or (lambda: MODE_NORMAL)
        self.interval = interval
        self.clock = clock or datetime.now
        self.memory = memory
        self.owner = owner
        self.llm = llm

    async def run(self):
        while True:
            await asyncio.sleep(self.interval)
            try:
                self.tick()
            except Exception as e:
                self.bus.publish_sync(Event(EventType.ERROR_OCCURRED, {"error": str(e)}))

    def tick(self) -> dict:
        now = self.clock()
        mode = self.mode_fn()

        events = self.reminders.get_due(now, category="event")
        goals = self.reminders.get_due(now, category="goal")

        # Phase 7 background maintenance: compact short-term memory and refresh
        # the curated OWNER.md. Purely bookkeeping — never touches the request path.
        if self.memory is not None:
            self.memory.compact_discussion(now)
            self.memory.prune_daily(now)
            self.memory.summarize_yesterday_discussion(self.llm, now)
        if self.owner is not None and self.memory is not None:
            self.owner.maybe_regen(self.memory.persistent(), self.llm, now)

        for row in events:
            self._fire_event(row, mode)

        fired_events = len(events)
        deferred = False
        fired_goals = 0

        if goals and not fired_events:
            if mode != MODE_DND:
                audio = mode == MODE_NORMAL
                for row in goals:
                    self._fire_goal(row, audio)
                    fired_goals += 1
            else:
                deferred = True
        elif goals:
            deferred = True

        return {
            "events": fired_events,
            "goals": fired_goals,
            "deferred_goals": deferred,
            "pending_goals": len(goals),
        }

    def _fire_event(self, row, mode: str):
        self._announce(row, self.event_notifier, recurring_tag=row["recurrence_rule"])
        if mode == MODE_NORMAL and self.alerter is not None:
            self.alerter.notify("Event alert", row["task"])
        self._post_fire(row)

    def _fire_goal(self, row, audio: bool):
        self._announce(row, self.goal_notifier, prefix="Goal nudge")
        if audio and self.alerter is not None:
            self.alerter.notify("Goal nudge", row["task"])
        self._post_fire(row)

    def _announce(self, row, notifier, prefix="Reminder", recurring_tag=None):
        tag = " (recurring)" if recurring_tag else ""
        self.bus.publish_sync(
            Event(
                EventType.REMINDER_DUE,
                {"id": row["id"], "task": row["task"], "due_at": row["due_at"],
                 "category": row["category"]},
            )
        )
        notifier.notify(f"{prefix} #{row['id']}{tag}", row["task"])

    def _post_fire(self, row):
        if row["recurrence_rule"]:
            nxt = self._next_after_missed(row["recurrence_rule"], row["due_at"])
            if nxt is not None:
                self.reminders.reschedule(row["id"], nxt)
        self.reminders.mark_notified(row["id"], self.clock())

    def _next_after_missed(self, rule: str, due_str: str):
        cursor = datetime.fromisoformat(due_str)
        now = self.clock()
        for _ in range(1000):
            nxt = self.reminders.next_from_recurrence(rule, cursor)
            if nxt is None:
                return None
            if nxt > now:
                return nxt
            cursor = nxt
        return None
