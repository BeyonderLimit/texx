from enum import Enum

from core.events import Event, EventBus, EventType


def now_iso() -> str:
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class AssistantState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    PROCESSING = "processing"
    THINKING = "thinking"
    EXECUTING = "executing"
    SPEAKING = "speaking"
    CONFIRMING = "confirming"
    ERROR = "error"


class StateManager:
    def __init__(self, bus: EventBus):
        self.bus = bus
        self.state = AssistantState.IDLE

    def set(self, state: AssistantState) -> None:
        if state == self.state:
            return
        self.state = state
        self.bus.publish_sync(
            Event(EventType.ASSISTANT_STATE_CHANGED, {"state": state.value})
        )
