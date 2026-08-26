import asyncio

from core.events import Event, EventBus, EventType


MODE_NORMAL = "normal"


class TimerManager:
    """Per-timer asyncio tasks — fire exactly on time without touching the DB
    or waiting for the Helper's polling tick, so they never block new requests."""

    def __init__(self, bus: EventBus, notifier, alerter=None, mode_fn=None):
        self.bus = bus
        self.notifier = notifier
        self.alerter = alerter
        self.mode_fn = mode_fn or (lambda: MODE_NORMAL)
        self.active: dict[int, dict] = {}
        self._tasks: set[asyncio.Task] = set()
        self._next_id = 1

    def start(self, seconds: float, label: str) -> int:
        tid = self._next_id
        self._next_id += 1
        task = asyncio.create_task(self._run(tid, seconds, label))
        self.active[tid] = {"label": label, "seconds": seconds, "task": task}
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return tid

    def cancel(self, tid: int) -> bool:
        entry = self.active.pop(tid, None)
        if entry is None:
            return False
        entry["task"].cancel()
        return True

    async def cancel_all(self):
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self.active.clear()

    async def _run(self, tid: int, seconds: float, label: str):
        try:
            await asyncio.sleep(seconds)
        except asyncio.CancelledError:
            return
        self.active.pop(tid, None)
        title = f"Timer ({label})"
        body = f"Your {label} timer is up!"
        self.bus.publish_sync(
            Event(EventType.REMINDER_DUE, {"id": tid, "task": body, "category": "timer"})
        )
        self.notifier.notify(title, body)
        if self.mode_fn() == MODE_NORMAL and self.alerter is not None:
            self.alerter.notify(title, body)
