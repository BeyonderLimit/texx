from dataclasses import dataclass, field


@dataclass
class Command:
    intent: str
    slots: dict = field(default_factory=dict)
    confidence: float = 1.0
    source: str = "rule"
    requires_confirmation: bool = False


class UnknownIntentError(Exception):
    pass
