from dataclasses import dataclass
from pathlib import Path


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
    "/read": SlashCommand("/read", "N", "Read article from result N (after search)"),
    "/ical": SlashCommand("/ical", "PATH", "Import events from an .ics calendar file"),
    "/llm": SlashCommand("/llm", "[set PATH | off]", "Show model status, set GGUF path, or disable"),
    "/voice": SlashCommand("/voice", "[on | off | set PATH]", "Voice mode status, start, stop, or set a model"),
    "/vosk": SlashCommand("/vosk", "set PATH", "Point Texx at a Vosk model directory"),
    "/piper": SlashCommand("/piper", "set PATH", "Point Texx at a Piper voice .onnx"),
    "/tts": SlashCommand("/tts", "[text]", "Speak text aloud (tests the TTS voice)"),
    "/log": SlashCommand("/log", "[N]", "Show recent log entries (errors/faults)"),
    "/sessions": SlashCommand("/sessions", "[query]", "Review session log (raw archive); search turns with a query"),
    "/owner": SlashCommand("/owner", "", "Show the curated OWNER.md owner profile"),
    "/compact": SlashCommand("/compact", "", "Compact short-term memory and refresh OWNER.md"),
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
            else f"'{app_name}' wasn't on the open allowlist."
        )
    if action == "close":
        process = rest[0] if rest else app_name
        if add:
            system.add_close(app_name, process)
            return f"'{app_name}' added to the close allowlist (kills process `{process}`)."
        return (
            f"'{app_name}' removed from the close allowlist."
            if system.remove_close(app_name)
            else f"'{app_name}' wasn't on the close allowlist."
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
    if name == "/read":
        from core.executor import article_read
        from core.commands import Command as _Cmd
        if not arg or not arg.isdigit():
            return "Usage: /read <result_number>"
        return await article_read(_Cmd(intent="article.read", slots={"n": int(arg)}), ctx)
    if name == "/ical":
        from core.executor import calendar_import
        from core.commands import Command as _Cmd
        if not arg:
            return "Usage: /ical /path/to/calendar.ics"
        return await calendar_import(_Cmd(intent="calendar.import", slots={"path": arg}), ctx)
    if name == "/llm":
        from llm.manager import LLMManager
        if arg.lower() in ("off", "disable", "none"):
            ctx.settings.set("llm_model_path", "")
            if getattr(ctx, "llm", None) is not None:
                ctx.llm.set_model(None)
            return "Local LLM disabled (no model configured)."
        if arg.lower().startswith("set "):
            arg = arg[4:].strip()
        if arg:
            ctx.settings.set("llm_model_path", arg)
            if getattr(ctx, "llm", None) is not None:
                ctx.llm.set_model(arg)
            else:
                ctx.llm = LLMManager(arg)
            if ctx.llm.is_available():
                return f"Local LLM loaded from {arg}."
            return (f"Set model path to {arg}, but it can't be loaded yet: "
                    f"{ctx.llm.unavailable_reason()}. Conversation will stay disabled "
                    "until a valid GGUF is available.")
        llm = getattr(ctx, "llm", None)
        if llm is None or not llm.is_available():
            reason = llm.unavailable_reason() if llm else "not initialized"
            return (f"Local LLM is not active ({reason}).\n"
                    "Enable it with: /llm set /path/to/model.gguf")
        return "Local LLM is active and ready for conversation."
    if name == "/voice":
        voice = getattr(ctx, "voice", None)
        if voice is None or not hasattr(voice, "status"):
            return "Voice subsystem is not initialized."
        arg = arg.lower()
        if arg.startswith("set "):
            path = arg[4:].strip()
            return _voice_set_route(voice, path)
        if arg in ("off", "stop"):
            return voice.stop()
        if arg in ("on", "start"):
            if not voice.ctrl.is_available():
                return (f"Can't start voice ({voice.ctrl.unavailable_reason()}). "
                        "Install vosk + a model and sounddevice, then re-run Texx.")
            return voice.start()
        return voice.status()
    if name == "/vosk":
        voice = getattr(ctx, "voice", None)
        if voice is None or not hasattr(voice, "set_vosk"):
            return "Voice subsystem is not initialized."
        if not arg:
            return "Usage: /vosk set /path/to/vosk-model"
        if arg.lower().startswith("set "):
            arg = arg[4:].strip()
        return voice.set_vosk(arg)
    if name == "/piper":
        voice = getattr(ctx, "voice", None)
        if voice is None or not hasattr(voice, "set_piper"):
            return "Voice subsystem is not initialized."
        if not arg:
            return "Usage: /piper set /path/to/voice.onnx"
        if arg.lower().startswith("set "):
            arg = arg[4:].strip()
        return voice.set_piper(arg)
    if name == "/tts":
        voice = getattr(ctx, "voice", None)
        if voice is None or not hasattr(voice, "ctrl"):
            return "Voice subsystem is not initialized."
        tts = voice.ctrl.tts
        if not tts.is_available():
            return f"TTS not available: {tts.unavailable_reason()}. Set a voice with /piper set <path>."
        text = arg.strip()
        if not text:
            return "Usage: /tts <text to speak>"
        try:
            tts.speak(text)
        except Exception as e:  # noqa: BLE001
            return f"TTS failed: {e}"
        return f"Spoke: {text}"
    if name == "/log":
        from services.log import recent
        try:
            n = int(arg.strip()) if arg.strip() else 40
        except ValueError:
            n = 40
        entries = recent(n)
        if not entries:
            return "No log entries yet."
        return "\n".join(entries)
    if name == "/sessions":
        sessionlog = getattr(ctx, "sessionlog", None)
        if sessionlog is None:
            return "Session logging is not available."
        q = arg.strip()
        if not q:
            rows = sessionlog.recent(20)
            if not rows:
                return "No session turns recorded yet."
            lines = ["Recent session turns:"]
            for r in reversed(rows):
                lines.append(f"[{r['created_at']}] {r['role']}: {r['content']}")
            return "\n".join(lines)
        matches = sessionlog.search(q, limit=5)
        if not matches:
            return f"No session turns matching '{q}'."
        lines = [f"Session turns matching '{q}':"]
        for m in matches:
            lines.append(f"  match @ {m['created_at']} ({m['role']}): {m['content']}")
            for nb in sessionlog.get_nearby(m["id"], window=2):
                if nb["id"] == m["id"]:
                    continue
                lines.append(f"    [{nb['role']}] {nb['content']}")
        return "\n".join(lines)
    if name == "/owner":
        owner = getattr(ctx, "owner", None)
        if owner is None or not owner.exists():
            return ("OWNER.md not generated yet. It builds automatically in the "
                    "background (or after memory changes); run /compact to force it.")
        return owner.read()
    if name == "/compact":
        memory = getattr(ctx, "memory", None)
        owner = getattr(ctx, "owner", None)
        if memory is None:
            return "Memory service is not available."
        d = memory.compact_discussion()
        dy = memory.prune_daily()
        if owner is not None:
            memory_items = memory.persistent()
            for _ in memory_items:
                owner.mark_dirty()
            owner.regen(memory_items, llm=getattr(ctx, "llm", None), force=True)
            owner_msg = "OWNER.md refreshed."
        else:
            owner_msg = "OWNER.md skipped (no profile service)."
        return f"Compaction complete: {d} discussion + {dy} daily entries pruned. {owner_msg}"
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


def _voice_set_route(voice, path: str) -> str:
    p = Path(path).expanduser()
    if p.is_dir():
        onnx = next((f for f in p.glob("*.onnx")), None)
        if onnx is not None:
            return voice.set_piper(str(onnx))
        return voice.set_vosk(str(p))
    if path.endswith(".onnx"):
        return voice.set_piper(path)
    if path.endswith(".zip"):
        return ("That looks like a Vosk model archive. Extract it first "
                "(e.g. unzip it), then run /voice set <extracted-directory>.")
    return ("Couldn't tell what to set. Use a model directory for Vosk "
            "(/voice set /path/to/vosk-model) or a .onnx file for Piper "
            "(/voice set /path/to/voice.onnx).")

