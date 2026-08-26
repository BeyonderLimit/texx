from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from core.state import AssistantState, StateManager

console = Console()


class App:
    def __init__(self, states: StateManager, assistant_name_fn, time_fn=None):
        self.states = states
        self.assistant_name_fn = assistant_name_fn
        self.time_fn = time_fn
        self.console = console
        self.last_response: str | None = None

    def banner(self):
        name = self.assistant_name_fn()
        line = f"[bold cyan]{name}[/bold cyan]  ·  offline personal assistant"
        if self.time_fn:
            t = self.time_fn()
            line += f"\n[dim]{t['weekday']} · {t['date']} · {t['time']} ({t['timezone']})[/dim]"
        console.print(
            Panel(
                f"{line}\n"
                f"Status: [green]● {self.states.state.value.upper()}[/green]",
                title="TEXX",
                border_style="cyan",
            )
        )
        console.print("Type a command, or 'exit' to quit.\n")

    def status_line(self):
        state = self.states.state
        style = "red" if state == AssistantState.ERROR else "green"
        console.print(f"\n[dim]{self.assistant_name_fn()} is [bold {style}]{state.value}[/bold {style}][/dim]")

    def clear(self):
        console.clear()
        self.banner()

    def show_response(self, response: str, markdown: bool = False):
        self.last_response = response
        body = Markdown(response) if markdown else response
        console.print(Panel(body, border_style="blue"))

    def prompt(self) -> str:
        return console.input("[bold cyan]> [/bold cyan]")

    async def prompt_async(self) -> str:
        import asyncio
        return await asyncio.to_thread(self.prompt)
