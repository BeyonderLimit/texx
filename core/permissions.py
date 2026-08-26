from core.commands import Command
from services.system import normalize

BLOCKED_INTENTS: set[str] = set()


class PermissionDenied(Exception):
    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message)
        self.hint = hint


def _allow_hint(action: str, name: str, argv_hint: str) -> str:
    return f"Add it with: /allow {action} {name} {argv_hint}".rstrip()


def check(command: Command, system=None) -> None:
    if command.intent in BLOCKED_INTENTS:
        raise PermissionDenied(f"intent '{command.intent}' is not allowed")
    if command.intent == "system.open_app":
        name = command.slots["app"]
        if system is None or normalize(name) not in system.open_map():
            raise PermissionDenied(
                f"app '{name}' is not on the open allowlist",
                hint=_allow_hint("open", normalize(name), "[launch command]"),
            )
    if command.intent == "system.close_app":
        name = command.slots["app"]
        if system is None or normalize(name) not in system.close_map():
            raise PermissionDenied(
                f"app '{name}' is not on the close allowlist",
                hint=_allow_hint("close", normalize(name), "[process name]"),
            )
