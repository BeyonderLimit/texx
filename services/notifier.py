from typing import Protocol

from rich.console import Console


class Notifier(Protocol):
    def notify(self, title: str, body: str) -> None: ...


class ConsoleNotifier:
    def __init__(self, console: Console | None = None):
        self.console = console or Console()

    def notify(self, title: str, body: str) -> None:
        from rich.panel import Panel
        self.console.print(Panel(body, title=f"[yellow]⏰ {title}[/yellow]", border_style="yellow"))


class BellNotifier:
    """Audible terminal alert. Replaced by Piper TTS in Phase 6."""

    def __init__(self, console: Console | None = None):
        self.console = console or Console()

    def notify(self, title: str, body: str) -> None:
        self.console.bell()


class CompositeNotifier:
    def __init__(self, notifiers: list[Notifier]):
        self.notifiers = notifiers

    def notify(self, title: str, body: str) -> None:
        for n in self.notifiers:
            n.notify(title, body)
