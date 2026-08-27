from datetime import datetime, timedelta

from core.events import Event, EventBus, EventType
from core.permissions import PermissionDenied, check
from core.state import AssistantState, StateManager
from services.memory import MemoryService, classify_memory
from services.reminders import ReminderService
from services.search import OnlineError, WebSearchProvider, WikipediaProvider
from services.settings import Settings
from services.system import SystemService, UnknownApplication
from services.files import FileSearchService
from services.tasks import TaskService
from services.time import TimeService
from services.webcache import WebCache

HANDLERS = {}


def register(intent: str):
    def register(fn):
        HANDLERS[intent] = fn
        return fn
    return register


@register("math.calculate")
async def calculate(command, ctx):
    value = command.slots["result"]
    shown = int(value) if float(value).is_integer() else value
    return f"{command.slots['expression'].rstrip('?')} = {shown}"


@register("assistant.rename")
async def rename(command, ctx):
    ctx.settings.set("assistant_name", command.slots["name"])
    return f"Okay, I'm {command.slots['name']} now."


@register("assistant.get_name")
async def get_name(command, ctx):
    return f"I'm {ctx.settings.get('assistant_name')}."


@register("assistant.help")
async def show_help(command, ctx):
    from pathlib import Path
    help_path = Path(__file__).parent.parent / "HELP.md"
    return help_path.read_text()


@register("time.query")
async def time_query(command, ctx):
    return f"It's {ctx.time.time_str()}."


@register("date.query")
async def date_query(command, ctx):
    return f"Today is {ctx.time.date_str()}."


@register("time.set_timezone")
async def set_timezone(command, ctx):
    tz = command.slots["tz"]
    if ctx.time.set_timezone(tz):
        return f"Timezone set to {tz}."
    return f"'{tz}' is not a valid timezone (e.g. America/New_York)."


@register("date.weekday")
async def weekday_query(command, ctx):
    from datetime import date as _date
    target = _date.fromisoformat(command.slots["date"])
    upcoming = ctx.time.next_occurrence(target.month, target.day)
    day = ctx.time.weekday_of(target)
    if target.year != upcoming.year:
        return f"{target.strftime('%B %d')} falls on a {day}."
    return f"{upcoming.strftime('%B %d, %Y')} falls on a {day}."


@register("date.until")
async def days_until(command, ctx):
    from datetime import date as _date
    target = _date.fromisoformat(command.slots["date"])
    days = ctx.time.days_until(target)
    when = "today" if days == 0 else f"in {days} day{'s' if days != 1 else ''}"
    return f"{target.strftime('%B %d, %Y')} is {when}."


@register("system.open_app")
async def open_app(command, ctx):
    ctx.system.open_app(command.slots["app"])
    return f"Opening {normalize_display(command.slots['app'])}."


@register("system.close_app")
async def close_app(command, ctx):
    ctx.system.close_app(command.slots["app"])
    return f"Closing {normalize_display(command.slots['app'])}."


@register("conversation.chat")
async def chat(command, ctx):
    return (
        "I don't have a conversational brain yet — the local LLM arrives in Phase 5. "
        "Type `help` to see everything I can do right now."
    )


def normalize_display(name: str) -> str:
    return name.strip().capitalize()


class ExecutorContext:
    def __init__(self, settings: Settings, system: SystemService,
                 web=None, wiki=None, files=None, weather=None):
        self.settings = settings
        self.system = system
        self.time = TimeService(settings)
        self.reminders = ReminderService(settings.db)
        self.memory = MemoryService(settings.db)
        self.tasks = TaskService(settings.db)
        self.cache = WebCache(settings.db)
        self.web = web if web is not None else WebSearchProvider()
        self.wiki = wiki if wiki is not None else WikipediaProvider()
        self.files = files if files is not None else FileSearchService()
        from services.weather import WeatherProvider
        self.weather = weather if weather is not None else WeatherProvider()
        self.last_file_results: list = []
        self.last_web_results: list = []


def _format_due(due, rrule) -> str:
    base = due.strftime("%A, %B %d at %I:%M %p").lstrip("0").replace(" 0", " ")
    if rrule:
        base += f" — repeats ({rrule})"
    return base


@register("reminder.create")
async def reminder_create(command, ctx):
    from intents.dates import parse_when
    task = command.slots["task"]
    when_text = (command.slots.get("when") or "").strip()
    now = ctx.time.now().replace(tzinfo=None)

    if not when_text:
        return (
            f"I'll remind you to {task.rstrip('.')}. When? "
            "Try 'in 10 minutes', 'at 5pm', 'tomorrow at 9am', or 'every friday morning'."
        )

    due, rrule = parse_when(when_text, now)
    if due is None:
        return (
            f"I couldn't understand the time '{when_text}'. "
            "Try 'in 10 minutes', 'at 5pm', 'tomorrow at 9am', or 'every friday morning'."
        )

    category = "goal" if rrule and rrule.startswith(("FREQ=MINUTELY", "FREQ=HOURLY")) else "event"
    rid = ctx.reminders.add(task, due_at=due, recurrence_rule=rrule, category=category)
    label = "Goal" if category == "goal" else "Reminder"
    return f"{label} #{rid} set: {task} — {_format_due(due, rrule)}."


@register("reminder.list")
async def reminder_list(command, ctx):
    rows = ctx.reminders.list_pending(category="event")
    if not rows:
        return "You have no pending reminders. (Goals have their own list — try 'list goals'.)"
    lines = []
    for r in rows:
        when = _format_due(
            datetime.fromisoformat(r["due_at"]), r["recurrence_rule"]
        ) if r["due_at"] else "no time set"
        lines.append(f"#{r['id']}  {r['task']} — {when}")
    return "\n".join(lines)


@register("reminder.done")
async def reminder_done(command, ctx):
    rid = command.slots["id"]
    if ctx.reminders.complete(rid, expected_category="event"):
        return f"Reminder #{rid} marked done."
    return f"Reminder #{rid} isn't a pending reminder."


@register("reminder.delete")
async def reminder_delete(command, ctx):
    rid = command.slots["id"]
    if ctx.reminders.cancel(rid, expected_category="event"):
        return f"Reminder #{rid} cancelled."
    return f"Reminder #{rid} isn't a pending reminder."


MODE_DESCRIPTIONS = {
    "normal": "audible alerts on",
    "silent": "visual notifications only",
    "dnd": "do not disturb — goals are paused, only event notifications show (no audio)",
}


@register("mode.set")
async def mode_set(command, ctx):
    mode = command.slots["mode"]
    ctx.settings.set("mode", mode)
    return f"Mode set to {mode.upper()} ({MODE_DESCRIPTIONS[mode]})."


@register("mode.query")
async def mode_query(command, ctx):
    mode = ctx.settings.get("mode", "normal")
    asked = command.slots.get("asked")
    if asked:
        state = "on" if mode == asked else "off"
        return f"{asked.upper()} is {state}. Current mode: {mode.upper()}."
    return f"Current mode: {mode.upper()} ({MODE_DESCRIPTIONS[mode]})."


@register("goal.create")
async def goal_create(command, ctx):
    from intents.dates import parse_when
    task = command.slots["task"]
    when_text = (command.slots.get("when") or "").strip()
    now = ctx.time.now().replace(tzinfo=None)

    if not when_text:
        return (
            f"How often should I nudge you to {task.rstrip('.')}? "
            "Try 'every 2 hours' or 'every 45 minutes'."
        )

    due, rrule = parse_when(when_text, now)
    if due is None:
        return (
            f"I couldn't understand the interval '{when_text}'. "
            "Try 'every 2 hours', 'every 45 minutes', 'every morning', or 'every day at 8am'."
        )

    rid = ctx.reminders.add(task, due_at=due, recurrence_rule=rrule, category="goal")
    return f"Goal #{rid} set: {task} — {_format_due(due, rrule)}."


@register("goal.list")
async def goal_list(command, ctx):
    rows = ctx.reminders.list_pending(category="goal")
    if not rows:
        return "You have no active goals."
    lines = []
    for r in rows:
        when = _format_due(
            datetime.fromisoformat(r["due_at"]), r["recurrence_rule"]
        ) if r["due_at"] else "no schedule"
        lines.append(f"#{r['id']}  {r['task']} — {when}")
    return "\n".join(lines)


@register("goal.delete")
async def goal_delete(command, ctx):
    rid = command.slots["id"]
    if ctx.reminders.cancel(rid, expected_category="goal"):
        return f"Goal #{rid} removed."
    return f"Goal #{rid} isn't an active goal."


@register("timer.start")
async def timer_start(command, ctx):
    seconds = command.slots["seconds"]
    label = command.slots["label"]
    tid = ctx.timers.start(seconds, label)
    return f"Timer #{tid} set: {label}. I'll notify you the moment it's up."


@register("system.status")
async def system_status(command, ctx):
    from services.systeminfo import full_status
    return full_status(ctx.states, ctx.settings, ctx.reminders, ctx.time, ctx.tasks)


@register("info.query")
async def info_query(command, ctx):
    from services.systeminfo import battery, brightness, volume
    kind = command.slots["kind"]
    value = {"battery": battery, "volume": volume, "brightness": brightness}[kind]()
    return f"{kind.capitalize()}: {value}"


WEATHER_TTL_SECONDS = 1800


def _weather_key(ctx) -> str:
    loc = (ctx.settings.get("location") or "").strip().lower()
    return f"weather:{loc or '_auto'}"


def _load_weather(ctx):
    """Shared weather lookup for handlers and the briefing.
    Returns (data, from_cache)."""
    key = _weather_key(ctx)
    data = ctx.cache.get(key)
    if data is None:
        loc = (ctx.settings.get("location") or "").strip() or None
        data = ctx.weather.current(loc)
        ctx.cache.set(key, data, ttl_seconds=WEATHER_TTL_SECONDS)
        return data, False
    return data, True


def _pick_forecast(forecasts, day_word):
    idx = 1 if day_word == "tomorrow" else 0
    if not forecasts:
        return None, ""
    if idx >= len(forecasts):
        idx = len(forecasts) - 1
    label = {"tomorrow": "Tomorrow", "tonight": "Tonight"}.get(day_word, "Today")
    return forecasts[idx], label


def _answer_condition(condition: str, entry: dict) -> str:
    desc = (entry.get("desc") or "")
    lowered = desc.lower()
    rain = int(entry.get("rain_pct") or 0)
    maxc = int(entry.get("max_c") or 0)
    chance = f"; rain chance up to {rain}%" if rain else ""

    def has(*words):
        return any(w in lowered for w in words)

    if condition.startswith("rain"):
        yes = rain >= 40 or has("rain", "drizzle", "shower", "thunder")
    elif condition.startswith("snow"):
        yes = has("snow", "sleet")
    elif condition == "sunny":
        yes = has("sun", "clear")
    elif condition in ("cloudy", "overcast"):
        yes = has("cloud", "overcast")
    elif condition in ("hot", "warm"):
        yes = maxc >= (28 if condition == "hot" else 22)
    else:  # cold
        yes = maxc <= 5

    detail = f"{desc or 'no clear sky description'}; high {maxc}°C{chance}"
    return f"Yes — looks {condition}: {detail}." if yes else \
        f"Probably not — forecast says {detail}."


@register("weather.query")
async def weather_query(command, ctx):
    try:
        data, from_cache = _load_weather(ctx)
    except OnlineError as e:
        return f"Weather unavailable: {e}."
    note = "(cached)\n" if from_cache else ""

    cur = data["current"]
    header = f"{data['place']}: {cur['desc']}, {cur['temp_c']}°C ({cur['temp_f']}°F)" \
             f", feels like {cur['feels_c']}°C."
    if not ctx.settings.get("location"):
        header += "\n(That's a rough guess from your IP — set one with 'set location to New Haven'.)"

    entry, label = _pick_forecast(data["forecasts"], command.slots.get("day") or "today")

    condition = (command.slots.get("condition") or "").strip().lower()
    if condition and entry is not None:
        return f"{note}{header}\n{_answer_condition(condition, entry)}"
    if entry is None:
        return f"{note}{header}"

    days = (datetime.strptime(entry["date"], "%Y-%m-%d").strftime("%a %b %d")
            if entry.get("date") else "")
    rain = f"; rain chance up to {entry['rain_pct']}%" if entry.get("rain_pct") else ""
    when = f"{label} ({days}): " if days else f"{label}: "
    body = (f"{when}{entry['desc']}, high {entry['max_c']}°C ({entry['max_f']}°F)"
            f" / low {entry['min_c']}°C ({entry['min_f']}°F){rain}.")
    return f"{note}{header}\n{body}"


@register("location.set")
async def location_set(command, ctx):
    place = command.slots["location"].rstrip(".!")
    ctx.settings.set("location", place)
    return f"Location set to {place}."


@register("memory.store")
async def memory_store(command, ctx):
    text = command.slots["text"].rstrip(".")
    explicit = command.slots.get("explicit", False)
    category, importance = classify_memory(text)
    source = "user"
    if explicit:
        source = "explicit"
        importance = min(importance + 2, 10)
    mid = ctx.memory.add(text, category=category, importance=importance, source=source)
    return f'Remembered #{mid} [{category}]: "{text}".'


@register("memory.recall")
async def memory_recall(command, ctx):
    query = command.slots["query"]
    results = ctx.memory.search(query)
    if not results:
        return f"Nothing in memory about '{query}'."
    lines = [f"[{r['category']}] {r['content']} (#{r['id']})" for r in results]
    return "\n".join(lines)


@register("memory.list")
async def memory_list(command, ctx):
    rows = ctx.memory.all()
    if not rows:
        return "My long-term memory is empty. Tell me things with 'remember that...'"
    lines = [f"[{r['category']}] {r['content']} (#{r['id']})" for r in rows[:15]]
    total = ctx.memory.count()
    if total > len(lines):
        lines.append(f"... and {total - len(lines)} more.")
    return "\n".join(lines)


@register("memory.forget")
async def memory_forget(command, ctx):
    rid = command.slots.get("id")
    if rid is not None:
        row = ctx.memory.get(rid)
        if row and ctx.memory.forget(rid):
            return f'Forgot: "{row["content"]}" ({rid}).'
        return f"Memory #{rid} doesn't exist."

    query = command.slots.get("query")
    matches = ctx.memory.search(query)
    if not matches:
        return f"I don't remember anything about '{query}'."
    if len(matches) == 1:
        row = matches[0]
        ctx.memory.forget(row["id"])
        return f'Forgot: "{row["content"]}" ({row["id"]}).'
    listing = ", ".join(f"#{r['id']} \"{r['content']}\"" for r in matches[:5])
    return f"I found several memories about that. Forget which one? {listing}"


@register("task.add")
async def task_add(command, ctx):
    title = command.slots["title"]
    priority = command.slots["priority"]
    expires_at = None
    if command.slots.get("ttl_seconds"):
        expires_at = ctx.time.now().replace(tzinfo=None) + timedelta(
            seconds=command.slots["ttl_seconds"]
        )
    tid = ctx.tasks.add(title, priority=priority, expires_at=expires_at)
    ttl_note = f" — expires {_iso_date(expires_at)}" if expires_at else ""
    return f"Task #{tid} [{priority.upper()}]: {title}{ttl_note}."


def _iso_date(dt) -> str:
    return dt.strftime("%a %b %d %I:%M %p").lstrip("0").replace(" 0", " ")


@register("task.list")
async def task_list(command, ctx):
    ctx.tasks.purge_expired()
    rows = ctx.tasks.list_open()
    if not rows:
        return "No open tasks. Add one with 'task buy milk' or 'todo file taxes with high priority'."
    lines = []
    for r in rows[:15]:
        pr = r["priority"].upper()
        exp = ""
        if r["expires_at"]:
            from datetime import datetime as _dt
            exp = f" (expires {_iso_date(_dt.fromisoformat(r['expires_at']))})"
        lines.append(f"#{r['id']} [{pr}] {r['title']}{exp}")
    return "\n".join(lines)


@register("task.done")
async def task_done(command, ctx):
    tid = command.slots["id"]
    row = ctx.tasks.get(tid)
    if row and ctx.tasks.complete(tid):
        return f"Task #{tid} completed: {row['title']}."
    return f"Task #{tid} isn't open."


@register("task.delete")
async def task_delete(command, ctx):
    tid = command.slots["id"]
    row = ctx.tasks.get(tid)
    if row and ctx.tasks.delete(tid):
        return f"Task #{tid} deleted: {row['title']}."
    return f"Task #{tid} doesn't exist."


@register("note.take")
async def note_take(command, ctx):
    text = command.slots["text"].rstrip(".")
    nid = ctx.memory.add(text, category="NOTE", importance=5, source="note")
    return f"Note #{nid}: {text}"


@register("note.list")
async def note_list(command, ctx):
    rows = ctx.memory.list_category("NOTE")
    if not rows:
        return "No notes yet. Save one with 'note: buy stamps'."
    lines = [f"#{r['id']}  {r['content']} — {_short_date(r['created_at'])}" for r in rows]
    return "\n".join(lines)


def _short_date(iso_str) -> str:
    from datetime import datetime as _dt
    return _dt.fromisoformat(iso_str).strftime("%b %d")


@register("web.search")
async def web_search(command, ctx):
    query = command.slots["query"]
    key = f"web:{query.lower()}"
    results = ctx.cache.get(key)
    cached_note = ""
    if results is None:
        try:
            results = ctx.web.search(query)
        except OnlineError as e:
            return f"Web search unavailable: {e}."
        ctx.cache.set(key, results, ttl_seconds=3600)
    else:
        cached_note = " (cached)"
    ctx.last_web_results = [r["url"] for r in results]
    lines = [f"Results for '{query}'{cached_note}:", ""]
    for i, r in enumerate(results, 1):
        snippet = (r.get("snippet") or "")[:140]
        lines.append(f"[{i}] {r['title']}")
        lines.append(f"    {r['url']}")
        if snippet:
            lines.append(f"    {snippet}")
    lines.append("")
    lines.append("Open one with 'open result N'.")
    return "\n".join(lines)


@register("knowledge.wiki")
async def knowledge_wiki(command, ctx):
    topic = command.slots["topic"]
    key = f"wiki:{topic.lower()}"
    data = ctx.cache.get(key)
    if data is None:
        try:
            data = ctx.wiki.summary(topic)
        except OnlineError as e:
            return f"Wikipedia unavailable: {e}."
        ctx.cache.set(key, data, ttl_seconds=86400)
    extract = data["extract"].split(". ")
    short = ". ".join(extract[:3]).strip()
    if not short.endswith("."):
        short += "."
    return f"{data['title']} — {short}\n{data['url']}"


@register("file.find")
async def file_find(command, ctx):
    query = command.slots["query"]
    matches = ctx.files.find(query)
    ctx.last_file_results = matches
    if not matches:
        return f"No local files matching '{query}'."
    lines = [f"{len(matches)} local match(es) for '{query}':"]
    for i, path in enumerate(matches, 1):
        lines.append(f"[{i}] {path}")
    lines.append("")
    lines.append("Open one with 'open result N'.")
    return "\n".join(lines)


@register("file.open_result")
async def file_open_result(command, ctx):
    n = command.slots["n"]
    import subprocess
    if ctx.last_file_results:
        if not 1 <= n <= len(ctx.last_file_results):
            return f"Result {n} doesn't exist ({len(ctx.last_file_results)} matches). Try 'find' again."
        path = ctx.last_file_results[n - 1]
        subprocess.Popen(["xdg-open", str(path)])
        return f"Opening {path.name}."
    urls = getattr(ctx, "last_web_results", [])
    if urls:
        if not 1 <= n <= len(urls):
            return f"Result {n} doesn't exist ({len(urls)} matches). Try 'search' again."
        url = urls[n - 1]
        subprocess.Popen(["xdg-open", url])
        return f"Opening {url} in your browser."
    return "Nothing to open yet — use 'find <name>' or 'search for <query>' first."


@register("article.read")
async def article_read(command, ctx):
    n = command.slots["n"]
    urls = getattr(ctx, "last_web_results", [])
    if not urls:
        return "No search results to read — use 'search for <query>' first."
    if not 1 <= n <= len(urls):
        return f"Result {n} doesn't exist ({len(urls)} results). Try 'search' again."
    url = urls[n - 1]
    try:
        text = ctx.web.fetch_page_text(url)
    except OnlineError as e:
        return f"Could not fetch the article: {e}."
    if not text.strip():
        return "No readable text found at that URL."
    title_m = text[:80].split("\n")
    return f"{url}\n\n{text[:3000]}"


@register("calendar.appointments")
async def calendar_appointments(command, ctx):
    rows = [r for r in ctx.reminders.list_pending(category="event") if r["due_at"]]
    if not rows:
        return "You have no upcoming appointments on your local schedule."
    lines = []
    for r in rows[:8]:
        due = datetime.fromisoformat(r["due_at"])
        when = due.strftime("%A, %B %d at %I:%M %p").replace(" at 0", " at ").replace(" 0", " ", 1)
        lines.append(f"#{r['id']}  {r['task']} — {when}")
    note = "\n(Local schedule only — external calendar sync arrives in Phase 4.)"
    return "\n".join(lines) + note


@register("calendar.import")
async def calendar_import(command, ctx):
    path_str = command.slots["path"]
    from pathlib import Path
    from services.calendar import parse_ics
    filepath = Path(path_str).expanduser().resolve()
    if not filepath.exists():
        return f"File not found: {filepath}"
    if not filepath.suffix.lower() == ".ics":
        return f"Not an ICS file: {filepath.name}"
    events = parse_ics(filepath)
    if not events:
        return f"No upcoming events found in {filepath.name}."
    lines = [f"Imported {len(events)} event(s) from {filepath.name}:", ""]
    for ev in events[:8]:
        start = datetime.fromisoformat(ev["start"])
        when = start.strftime("%A, %B %d at %I:%M %p").replace(" at 0", " at ").replace(" 0", " ", 1)
        loc = f" @ {ev['location']}" if ev["location"] else ""
        lines.append(f"• {ev['summary']} — {when}{loc}")
    if len(events) > 8:
        lines.append(f"\n... and {len(events) - 8} more.")
    lines.append(f"\nTotal: {len(events)} events in the next 30 days.")
    return "\n".join(lines)


@register("assistant.brief")
async def assistant_brief(command, ctx):
    c = ctx.time.context()
    mode = ctx.settings.get("mode", "normal").upper()
    now = ctx.time.now().replace(tzinfo=None)

    events = [
        r for r in ctx.reminders.list_pending(category="event")
        if r["due_at"] and datetime.fromisoformat(r["due_at"]) >= now
    ]
    today_events = [
        r for r in events
        if datetime.fromisoformat(r["due_at"]).date() == now.date()
    ]
    upcoming = [r for r in events if r not in today_events][:3]
    goals = ctx.reminders.list_pending(category="goal")
    tasks = ctx.tasks.list_open()

    lines = [f"{c['date']} — {c['time']} ({c['timezone']})", f"Mode: {mode}", ""]

    # Current conditions appear once you've asked for weather recently —
    # the briefing itself never blocks on the network.
    try:
        wdata = ctx.cache.get(_weather_key(ctx))
        cur = wdata.get("current") if isinstance(wdata, dict) else None
        if cur:
            where = f" in {wdata['place']}" if wdata.get("place") else ""
            lines.append(
                f"Weather{where}: {cur['desc']}, {cur['temp_c']}°C ({cur['temp_f']}°F)"
            )
            lines.append("")
    except Exception:
        pass

    if today_events:
        lines.append("TODAY")
        for r in today_events[:5]:
            due = datetime.fromisoformat(r["due_at"])
            lines.append(f"• {r['task']} — {due.strftime('%I:%M %p').lstrip('0')}")
        lines.append("")
    else:
        lines.append("TODAY: nothing scheduled.")
        lines.append("")

    if tasks:
        lines.append("TASKS")
        for t in tasks[:5]:
            pr = f" [{t['priority'].upper()}]" if t["priority"] != "normal" else ""
            lines.append(f"• {t['title']}{pr}")
        lines.append("")

    if upcoming:
        lines.append("UPCOMING")
        for r in upcoming:
            due = datetime.fromisoformat(r["due_at"])
            lines.append(f"• {r['task']} — {due.strftime('%a %b %d, %I:%M %p').lstrip('0')}")
        lines.append("")

    one_time = [r for r in ctx.reminders.list_pending(category="event") if not r["recurrence_rule"]]
    lines.append(
        f"REMINDERS: {len(one_time)} pending · GOALS: {len(goals)} active · "
        f"TASKS: {len(tasks)} open"
    )
    return "\n".join(lines)


class Executor:
    def __init__(self, bus: EventBus, states: StateManager, settings: Settings,
                 system: SystemService | None = None, timers=None, web=None, wiki=None,
                 files=None, weather=None):
        self.bus = bus
        self.states = states
        self.ctx = ExecutorContext(
            settings,
            system if system is not None else SystemService(settings),
            web=web, wiki=wiki, files=files, weather=weather,
        )
        if timers is None:
            from core.timers import TimerManager
            from services.notifier import ConsoleNotifier
            timers = TimerManager(bus, notifier=ConsoleNotifier())
        self.ctx.timers = timers
        self.ctx.states = states

    async def execute(self, command) -> str:
        try:
            check(command, self.ctx.system)
        except PermissionDenied as e:
            self.states.set(AssistantState.ERROR)
            response = f"Permission denied: {e}"
            if e.hint:
                response += f"\n{e.hint}"
            return response
        fn = HANDLERS.get(command.intent)
        if fn is None:
            self.states.set(AssistantState.ERROR)
            return f"No handler for intent '{command.intent}'."
        self.states.set(AssistantState.EXECUTING)
        self.bus.publish_sync(Event(EventType.COMMAND_EXECUTING, {"intent": command.intent}))
        try:
            response = await fn(command, self.ctx)
        except UnknownApplication as e:
            self.states.set(AssistantState.IDLE)
            self._completed(command)
            return f"I don't know how to open '{e}'."
        except Exception as e:
            self.states.set(AssistantState.IDLE)
            self.bus.publish_sync(Event(EventType.COMMAND_FAILED, {"intent": command.intent, "error": str(e)}))
            return f"Something went wrong: {e}"
        self.states.set(AssistantState.IDLE)
        self._completed(command)
        return response

    def _completed(self, command):
        self.bus.publish_sync(
            Event(EventType.COMMAND_COMPLETED, {"intent": command.intent})
        )
