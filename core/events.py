from dataclasses import dataclass
from enum import Enum
from typing import Callable


class EventType(Enum):
    USER_INPUT_RECEIVED = "user_input_received"
    INTENT_MATCHED = "intent_matched"
    COMMAND_EXECUTING = "command_executing"
    COMMAND_COMPLETED = "command_completed"
    COMMAND_FAILED = "command_failed"
    ASSISTANT_STATE_CHANGED = "assistant_state_changed"
    SETTING_CHANGED = "setting_changed"
    REMINDER_DUE = "reminder_due"
    ERROR_OCCURRED = "error_occurred"


@dataclass
class Event:
    type: EventType
    data: dict | None = None


class EventBus:
    def __init__(self):
        self._subscribers: dict[EventType, list[Callable]] = {}

    def subscribe(self, event_type: EventType, handler: Callable):
        self._subscribers.setdefault(event_type, []).append(handler)

    async def publish(self, event: Event):
        for handler in self._subscribers.get(event.type, []):
            await _call(handler, event)

    def publish_sync(self, event: Event):
        for handler in self._subscribers.get(event.type, []):
            handler(event)


async def _call(handler: Callable, event: Event):
    result = handler(event)
    if hasattr(result, "__await__"):
        await result
