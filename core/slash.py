from dataclasses import dataclass


@dataclass
class SlashCommand:
    name: str
    args_hint: str
    description: str


SLASH_COMMANDS: dict[str, SlashCommand] = {
    "/help": SlashCommand("/help", "", "Show this quick reference"),
    "/time": SlashCommand("/time", "[timezone]", "Show time/date, or set timezone"),
    "/weather": SlashCommand("/weather", "[place]", "Weather now + forecast today"),
    "/location": SlashCommand("/location", "[place]", "Get or set your location"),
    "/apps": SlashCommand("/apps", "", "List allowlisted apps (open/close)"),
    "/allow": SlashCommand("/allow", "open|close NAME [COMMAND...]", "Add an app to an allowlist"),
    "/disallow": SlashCommand("/disallow", "open|close NAME", "Remove an app from an allowlist"),
    "/name": SlashCommand("/name", "[new_name]", "Get or set the assistant persona name"),
    "/status": SlashCommand("/status", "", "Full system status (always silent)"),
    "/reminders": SlashCommand("/reminders", "", "List pending reminders"),
    "/goals": SlashCommand("/goals", "", "List active goals"),
    "/memories": SlashCommand("/memories", "", "List long-term memories"),
    "/todo": SlashCommand("/todo", "", "List open tasks (alias: /tasks)"),
    "/web": SlashCommand("/web", "QUERY", "Search the web (cached 1h)"),
    "/find": SlashCommand("/find", "NAME", "Search local files"),
    "/tasks": SlashCommand("/tasks", "", "List open tasks"),
    "/mode": SlashCommand("/mode", "[normal|silent|dnd]", "Get or set notification mode"),
    "/brief": SlashCommand("/brief", "", "Show a summary of your day"),
    "/clear": SlashCommand("/clear", "", "Clear the screen"),
    "/exit": SlashCommand("/exit", "", "Shut Texx down"),
}


def is_slash_command(text: str) -> bool:
    return text.startswith("/")


def parse(text: str) -> tuple[str, str]:
    parts = text.split(maxsplit=1)
    return parts[0].lower(), parts[1].strip() if len(parts) > 1 else ""


def quickref_markdown() -> str:
    lines = ["## Texx Quick Reference", "", "| Command | Description |", "|---|---|"]
    for cmd in SLASH_COMMANDS.values():
        usage = f"{cmd.name} {cmd.args_hint}".strip().replace("|", "/")
        lines.append(f"| `{usage}` | {cmd.description} |")
    lines += [
        "",
        "**Natural language** also works: `what's 15% of 240?` · `open Firefox` · "
        "`call yourself Athena` · `help`",
    ]
    return "\n".join(lines)


def _time_report(ctx) -> str:
    from services.time import TimeService
    c = TimeService(ctx.settings).context()
    return f"**{c['time']}** — {c['date']} · Timezone: {c['timezone']}"


def _manage_allowlist(ctx, arg: str, add: bool) -> str:
    parts = arg.split()
    usage = "Usage: `/allow open NAME [COMMAND...]` or `/allow close NAME [PROCESS]`"
    if len(parts) < 2:
        return usage
    action, app_name = parts[0].lower(), " ".join(parts[1:2])
    rest = parts[2:]
    system = ctx.system
    if action == "open":
        argv = rest if rest else [app_name]
        if add:
            system.add_open(app_name, argv)
            return f"'{app_name}' added to the open allowlist (launches `{' '.join(argv)}`)."
        return (
            f"'{app_name}' removed from the open allowlist."
            if system.remove_open(app_name)
            else f"'{app_name}' wasn't on the custom open allowlist."
        )
    if action == "close":
        process = rest[0] if rest else app_name
        if add:
            system.add_close(app_name, process)
            return f"'{app_name}' added to the close allowlist (kills process `{process}`)."
        return (
            f"'{app_name}' removed from the close allowlist."
            if system.remove_close(app_name)
            else f"'{app_name}' wasn't on the custom close allowlist."
        )
    return usage


async def handle(text: str, ctx) -> str:
    name, arg = parse(text)
    if name not in SLASH_COMMANDS:
        known = ", ".join(sorted(SLASH_COMMANDS))
        return f"Unknown command `{name}`. Available: {known}"
    if name == "/help":
        return quickref_markdown()
    if name == "/time":
        if arg:
            from services.time import TimeService
            ok = TimeService(ctx.settings).set_timezone(arg)
            return f"Timezone set to {arg}." if ok else f"'{arg}' is not a valid timezone (e.g. America/New_York)."
        return _time_report(ctx)
    if name == "/weather":
        from core.executor import weather_query
        from core.commands import Command as _Cmd
        slots = {"day": "", "condition": ""}
        if arg:
            slots["location"] = arg.strip()
        return await weather_query(_Cmd(intent="weather.query", slots=slots), ctx)
    if name == "/location":
        if arg:
            place = arg.strip()
            ctx.settings.set("location", place)
            return f"Location set to {place}."
        current = ctx.settings.get("location")
        return f"Location: {current}" if current else "No location set. Try '/location New Haven'."
    if name == "/apps":
        open_map, close_map = ctx.system.open_map(), ctx.system.close_map()
        openable = ", ".join(sorted(open_map))
        closeable = ", ".join(sorted(close_map))
        return f"Openable: {openable}\nCloseable: {closeable}\n\nManage with `/allow` and `/disallow`."
    if name == "/allow":
        return _manage_allowlist(ctx, arg, add=True)
    if name == "/disallow":
        return _manage_allowlist(ctx, arg, add=False)
    if name == "/reminders":
        from core.executor import reminder_list
        from core.commands import Command as _Cmd
        return await reminder_list(_Cmd(intent="reminder.list"), ctx)
    if name == "/goals":
        from core.executor import goal_list
        from core.commands import Command as _Cmd
        return await goal_list(_Cmd(intent="goal.list"), ctx)
    if name == "/mode":
        from core.executor import MODE_DESCRIPTIONS, mode_query, mode_set
        from core.commands import Command as _Cmd
        if arg:
            mode = arg.strip().lower()
            if mode not in MODE_DESCRIPTIONS:
                return f"Unknown mode '{arg}'. Use normal, silent, or dnd."
            return await mode_set(_Cmd(intent="mode.set", slots={"mode": mode}), ctx)
        return await mode_query(_Cmd(intent="mode.query", slots={"asked": ""}), ctx)
    if name == "/brief":
        from core.executor import assistant_brief
        from core.commands import Command as _Cmd
        return await assistant_brief(_Cmd(intent="assistant.brief"), ctx)
    if name == "/memories":
        from core.executor import memory_list
        from core.commands import Command as _Cmd
        return await memory_list(_Cmd(intent="memory.list"), ctx)
    if name in ("/todo", "/tasks"):
        from core.executor import task_list
        from core.commands import Command as _Cmd
        return await task_list(_Cmd(intent="task.list"), ctx)
    if name == "/web":
        from core.executor import web_search
        from core.commands import Command as _Cmd
        if not arg:
            return "Usage: /web <query>"
        return await web_search(_Cmd(intent="web.search", slots={"query": arg}), ctx)
    if name == "/find":
        from core.executor import file_find
        from core.commands import Command as _Cmd
        if not arg:
            return "Usage: /find <name>"
        return await file_find(_Cmd(intent="file.find", slots={"query": arg}), ctx)
    if name == "/name":
        if arg:
            ctx.settings.set("assistant_name", arg)
            return f"Okay, I'm {arg} now."
        return f"I'm {ctx.settings.get('assistant_name')}."
    if name == "/status":
        from core.executor import system_status
        from core.commands import Command as _Cmd
        return await system_status(_Cmd(intent="system.status"), ctx)
    if name == "/clear":
        return "__CLEAR__"
    if name == "/exit":
        return "__EXIT__"
    return "Not implemented."
