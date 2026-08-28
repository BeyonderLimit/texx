import re

from core.commands import Command

CALC_PATTERNS = [
    re.compile(r"^(?:what(?:'s| is)\s+|calc(?:ulate)?\s+)?(?P<expr>[\d\s\.\+\-\*/%\(\)]+)\??$", re.IGNORECASE),
    re.compile(r"^(?P<expr>\d+(?:\.\d+)?)\s*%\s*of\s*(?P<base>\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"^what(?:'s| is)\s+(?P<expr>.+?)\s*\?$", re.IGNORECASE),
]

OPEN_PATTERN = re.compile(r"^(?:open|launch|start)\s+(?P<app>.+)$", re.IGNORECASE)
CLOSE_PATTERN = re.compile(r"^(?:close|quit|kill)\s+(?P<app>.+)$", re.IGNORECASE)
RENAME_PATTERNS = [
    re.compile(r"^(?:call yourself|i'?ll call you|your name is now)\s+(?P<name>[A-Za-z][\w\- ]{0,30})$", re.IGNORECASE),
    re.compile(r"^your name is\s+(?P<name>[A-Za-z][\w\- ]{0,30})$", re.IGNORECASE),
]
SET_NAME_QUERY = re.compile(r"^(?:what(?:'s| is) your name\??|who are you\??)$", re.IGNORECASE)
HELP_PATTERN = re.compile(r"^(?:help|what can you do\??|commands\??|capabilities\??|\?)$", re.IGNORECASE)

TIME_QUERY = re.compile(
    r"^(?:"
    r"what(?:'s| is)?\s+(?:the\s+|a\s+)?(?:current\s+)?time"
    r"(?:\s+(?:right\s+now|now|today))?"
    r"|what\s+time\s+is\s+it"
    r"(?:\s+(?:right\s+now|now|today))?"
    r"|tell\s+me\s+(?:the\s+)?(?:current\s+)?time"
    r"(?:\s+(?:right\s+now|now|today))?"
    r"|time(?:\s+please)?"
    r")\??$",
    re.IGNORECASE,
)
DATE_QUERY = re.compile(
    r"^(?:what(?:'s| is)? the date(?: today)?\??|what day is it(?: today)?\??|what(?:'s| is) today\??)$",
    re.IGNORECASE,
)
WEEKDAY_QUERY = re.compile(r"^what day (?:is|was|will be)\s+(?P<when>.+?)\??$", re.IGNORECASE)
DAYS_UNTIL = re.compile(r"^how many days (?:until|till|to)\s+(?P<when>.+?)\??$", re.IGNORECASE)
SET_TIMEZONE = re.compile(r"^set (?:my )?timezone to\s+(?P<tz>[\w/\+\-]+)\s*(?:please\??)?$", re.IGNORECASE)

REMIND_RE = re.compile(
    r"^(?:remind me(?:\s+(?:to|about|that))?|reminder(?:\s+to)?)\s+(?P<task>.+)$",
    re.IGNORECASE,
)
LIST_REMINDERS = re.compile(
    r"^(?:list(?: my)? reminders|what(?:'re| are) my reminders\??|show(?: my)? reminders\??|any reminders\??)$",
    re.IGNORECASE,
)
DONE_REMINDER = re.compile(r"^(?:mark\s+)?reminder\s+#?(?P<id>\d+)\s+(?:as\s+)?(?:done|complete[d]?|finished)$", re.IGNORECASE)
DELETE_REMINDER = re.compile(r"^(?:delete|remove|cancel)\s+(?:the\s+)?reminder\s+#?(?P<id>\d+)$", re.IGNORECASE)

TIMER_RE = re.compile(
    r"^(?:start|set|run|create)?\s*(?:a\s+|an\s+)?(?:timer|alarm)?\s*(?:for\s+)?"
    r"(?P<n>\d+)\s*[:\-]?\s*"
    r"(?P<unit>seconds?|secs?|minutes?|mins?|hours?|hrs?)\s*(?:timer|alarm)?$",
    re.IGNORECASE,
)
TIMER_PREFIX_RE = re.compile(
    r"^timer\s+(?:for\s+)?(?P<n>\d+)\s*[:\-]?\s*"
    r"(?P<unit>seconds?|secs?|minutes?|mins?|hours?|hrs?)$",
    re.IGNORECASE,
)
UNIT_SECONDS = {"sec": 1, "min": 60, "hour": 3600, "hr": 3600}
UNIT_WORDS = {"sec": "second", "min": "minute", "hour": "hour", "hr": "hour"}


def _unit_key(unit: str) -> str:
    u = unit.lower()
    if u.startswith("sec"):
        return "sec"
    if u.startswith("hour"):
        return "hour"
    if u == "hr":
        return "hr"
    return "min"


def match_timer(text: str) -> Command | None:
    stripped = text.strip()
    m = TIMER_RE.match(stripped) or TIMER_PREFIX_RE.match(stripped)
    if not m:
        return None
    n = int(m.group("n"))
    key = _unit_key(m.group("unit"))
    seconds = n * UNIT_SECONDS.get(key, 0)
    if seconds <= 0:
        return None
    word = UNIT_WORDS[key]
    label = f"{n} {word}{'' if n == 1 else 's'}"
    return Command(intent="timer.start", slots={"seconds": seconds, "label": label}, confidence=0.95)


APPOINTMENTS_RE = re.compile(
    r"^(?:list |show |what(?:'re| are) my |any |my )?appointments(?:\s+today|\s+tomorrow|\s+upcoming)?\??$",
    re.IGNORECASE,
)


def match_appointments(text: str) -> Command | None:
    if APPOINTMENTS_RE.match(text.strip()):
        return Command(intent="calendar.appointments", confidence=0.95)
    return None


BRIEF_RE = re.compile(
    r"^(?:brief|briefing|daily brief(?:ing)?|give me a (?:briefing|brief)|good morning)$",
    re.IGNORECASE,
)


def match_brief(text: str) -> Command | None:
    if BRIEF_RE.match(text.strip()):
        return Command(intent="assistant.brief", confidence=0.99)
    return None


STATUS_RE = re.compile(r"^(?:status|system status|full status)$", re.IGNORECASE)
WEATHER_DAY = r"(?:today|tonight|tomorrow)"
WEATHER_RES = [
    re.compile(
        rf"^weather(?:\s+(?:forecast|report|update|now|please))?(?:\s+{WEATHER_DAY})?\??$",
        re.IGNORECASE,
    ),
    re.compile(
        rf"^what(?:'s| is)(?:\s+the)?\s+weather(?:\s+(?:like|forecast|report|outside|now))?(?:\s+{WEATHER_DAY})?\??$",
        re.IGNORECASE,
    ),
    re.compile(rf"^how(?:'s| is)\s+(?:the\s+)?weather(?:\s+{WEATHER_DAY})?\??$", re.IGNORECASE),
    # Loose: any utterance that asks for weather with a request cue, allowing
    # conversational filler ("okay norm can you give me the weather"). Never
    # matches command-style leads (remind/task/add/...) so it can't steal them.
    re.compile(
        r"^(?!.*\b(?:remind|remember|reminder|task|todo|add|create|set|goal|note|"
        r"delete|cancel|close|open)\b)"
        r".*\b(?:get|give|tell|show|check|what(?:'s| is)|how(?:'s| is)|latest|current)\b"
        r".*\bweather\b",
        re.IGNORECASE,
    ),
]
CONDITION_RE = re.compile(
    rf"^will it (?:be\s+)?(?P<cond>raining|rainy|rain|sunny|cloudy|overcast|snowing|snowy|hot|cold|warm)"
    rf"(?:\s+{WEATHER_DAY})?\??$",
    re.IGNORECASE,
)
SET_LOCATION_RE = re.compile(
    r"^(?:set |change )?(?:my )?location to (?P<location>.+?)\??$", re.IGNORECASE
)


def match_weather(text: str) -> Command | None:
    stripped = text.strip()
    m = CONDITION_RE.match(stripped)
    if m:
        day_m = re.search(WEATHER_DAY, stripped, re.IGNORECASE)
        return Command(
            intent="weather.query",
            slots={"day": (day_m.group(0) if day_m else ""), "condition": m.group("cond").lower()},
            confidence=0.9,
        )
    for pattern in WEATHER_RES:
        m = pattern.match(stripped)
        if m:
            day_m = re.search(WEATHER_DAY, stripped, re.IGNORECASE)
            return Command(
                intent="weather.query",
                slots={"day": (day_m.group(0) if day_m else ""), "condition": ""},
                confidence=0.95,
            )
    return None


def match_set_location(text: str) -> Command | None:
    m = SET_LOCATION_RE.match(text.strip())
    if m and m.group("location").strip():
        return Command(intent="location.set", slots={"location": m.group("location").strip()}, confidence=0.99)
    return None


INFO_QUERIES = {
    "battery": re.compile(
        r"^(?:what(?:'s| is)(?: the| my)? battery(?: level)?|battery(?: level)?)\??$",
        re.IGNORECASE,
    ),
    "volume": re.compile(
        r"^(?:what(?:'s| is)(?: the)? volume(?: level)?|volume(?: level)?)\??$",
        re.IGNORECASE,
    ),
    "brightness": re.compile(
        r"^(?:what(?:'s| is)(?: the)? brightness(?: level)?|brightness(?: level)?|screen brightness)\??$",
        re.IGNORECASE,
    ),
}


def match_status(text: str) -> Command | None:
    if STATUS_RE.match(text.strip()):
        return Command(intent="system.status", confidence=0.95)
    return None


REMEMBER_RE = re.compile(
    r"^(?:please\s+)?remember(?:\s+that|\s+this|[:,])?\s+(?P<text>.+)$", re.IGNORECASE
)
RECALL_RE = re.compile(
    r"^(?:what do you (?:remember|know) about|recall|what did i tell you about)\s+(?P<q>.+?)\??$",
    re.IGNORECASE,
)
MEMORY_LIST_RE = re.compile(
    r"^(?:what do you remember\??|list memories|show(?: my)? memories|what have you remembered\??)$",
    re.IGNORECASE,
)
FORGET_RE = re.compile(
    r"^(?:forget|delete memory|remove memory)\s*(?:#(?P<id>\d+)|about\s+(?P<q>.+)|that\s+(?P<q2>.+)|(?P<q3>.+))$",
    re.IGNORECASE,
)


def match_remember(text: str) -> Command | None:
    m = REMEMBER_RE.match(text.strip())
    if not m:
        return None
    body = m.group("text").strip()
    if not body:
        return None
    lowered = body.lower()
    if lowered.startswith("to ") or lowered == "to":
        task = body[3:].strip()
        if task:
            from intents.dates import split_task_and_when
            task, when = split_task_and_when(task)
            return Command(
                intent="reminder.create",
                slots={"task": task, "when": when},
                confidence=0.95,
            )
        return None
    if lowered.startswith("my ") and len(body.split()) <= 2:
        return None
    return Command(intent="memory.store", slots={"text": body, "explicit": True}, confidence=0.9)


def match_recall(text: str) -> Command | None:
    m = RECALL_RE.match(text.strip())
    if m:
        return Command(intent="memory.recall", slots={"query": m.group("q").strip()}, confidence=0.9)
    return None


def match_memory_list(text: str) -> Command | None:
    if MEMORY_LIST_RE.match(text.strip()):
        return Command(intent="memory.list", confidence=0.99)
    return None


def match_forget(text: str) -> Command | None:
    m = FORGET_RE.match(text.strip())
    if not m:
        return None
    if m.group("id"):
        return Command(intent="memory.forget", slots={"id": int(m.group("id"))}, confidence=0.95)
    query = m.group("q") or m.group("q2") or m.group("q3")
    if not query:
        return None
    return Command(intent="memory.forget", slots={"query": query.strip()}, confidence=0.85)


TASK_ADD_RE = re.compile(r"^(?:add |new |create |make )?(?:task|todo)\s+(?P<title>.+)$", re.IGNORECASE)
PRIORITY_SUFFIX_RE = re.compile(r"\b(?:with\s+)?(urgent|high|low|normal)\s+priority\b", re.IGNORECASE)
TTL_SUFFIX_RE = re.compile(r"\s+for\s+(\d+)\s+(day|week|hour)s?\b", re.IGNORECASE)
TTL_SECONDS = {"hour": 3600, "day": 86400, "week": 604800}
TASK_LIST_RE = re.compile(
    r"^(?:list |show |my |what are my |what're my )?(?:tasks|todos|to-?dos)(?:\s+list)?\??$",
    re.IGNORECASE,
)
TASK_DONE_RE = re.compile(
    r"^(?:complete|finish|done with|check off)\s+(?:task|todo)\s+#?(?P<id>\d+)$", re.IGNORECASE
)
TASK_DELETE_RE = re.compile(
    r"^(?:delete|remove)\s+(?:task|todo)\s+#?(?P<id>\d+)$", re.IGNORECASE
)


def match_task_add(text: str) -> Command | None:
    m = TASK_ADD_RE.match(text.strip())
    if not m:
        return None
    title = m.group("title").strip()
    priority = "normal"
    pr = PRIORITY_SUFFIX_RE.search(title)
    if pr:
        priority = pr.group(1).lower()
        title = (title[:pr.start()] + title[pr.end():]).strip(" ,-")
    ttl_match = TTL_SUFFIX_RE.search(title)
    ttl_seconds = None
    if ttl_match:
        ttl_seconds = int(ttl_match.group(1)) * TTL_SECONDS[ttl_match.group(2).lower()]
        title = (title[:ttl_match.start()] + title[ttl_match.end():]).strip(" ,-")
    if not title:
        return None
    slots = {"title": title, "priority": priority}
    if ttl_seconds:
        slots["ttl_seconds"] = ttl_seconds
    return Command(intent="task.add", slots=slots, confidence=0.95)


def match_task_list(text: str) -> Command | None:
    if TASK_LIST_RE.match(text.strip()):
        return Command(intent="task.list", confidence=0.99)
    return None


def match_task_done(text: str) -> Command | None:
    m = TASK_DONE_RE.match(text.strip())
    if m:
        return Command(intent="task.done", slots={"id": int(m.group("id"))}, confidence=0.95)
    return None


def match_task_delete(text: str) -> Command | None:
    m = TASK_DELETE_RE.match(text.strip())
    if m:
        return Command(intent="task.delete", slots={"id": int(m.group("id"))}, confidence=0.95)
    return None


NOTE_TAKE_RE = re.compile(
    r"^(?:take |make |write |jot down )?(?:a |quick )?note[:,]?\s+(?P<text>.+)$", re.IGNORECASE
)
NOTES_LIST_RE = re.compile(r"^(?:list |show |my )?notes\??$", re.IGNORECASE)


def match_note_take(text: str) -> Command | None:
    m = NOTE_TAKE_RE.match(text.strip())
    if not m or not m.group("text").strip():
        return None
    return Command(intent="note.take", slots={"text": m.group("text").strip()}, confidence=0.9)


def match_notes_list(text: str) -> Command | None:
    if NOTES_LIST_RE.match(text.strip()):
        return Command(intent="note.list", confidence=0.99)
    return None


WEB_SEARCH_RE = re.compile(
    r"^(?:search(?: the web| online)?(?: for)?|google|look up)\s+(?P<q>.+)$", re.IGNORECASE
)
LOCAL_FIND_RE = re.compile(
    r"^(?:find|locate)\s+(?:my |the |file |files? )?(?P<q>.+)$"
    r"|^local search(?: for)?\s+(?P<q2>.+)$"
    r"|^search my files(?: for)?\s+(?P<q3>.+)$",
    re.IGNORECASE,
)
OPEN_RESULT_RE = re.compile(r"^open (?:result|file|match)\s+#?(?P<n>\d+)$", re.IGNORECASE)
KNOWLEDGE_RE = re.compile(
    r"^(?:wikipedia|wiki)\s+(?P<t1>.+)$"
    r"|^who (?:is|was) (?P<t2>.+?)\??$"
    r"|^tell me about (?P<t3>.+?)\??$",
    re.IGNORECASE,
)


def match_web_search(text: str) -> Command | None:
    stripped = text.strip()
    if LOCAL_FIND_RE.match(stripped):
        return None
    m = WEB_SEARCH_RE.match(stripped)
    if m:
        q = m.group("q").strip().rstrip("?")
        if not q or len(q) < 2:
            return None
        return Command(intent="web.search", slots={"query": q}, confidence=0.9)
    return None


def match_local_find(text: str) -> Command | None:
    m = LOCAL_FIND_RE.match(text.strip())
    if not m:
        return None
    q = (m.group("q") or m.group("q2") or m.group("q3") or "").strip()
    q = re.sub(r"^(?:file|files)\s+", "", q, flags=re.IGNORECASE).rstrip("?")
    if not q:
        return None
    return Command(intent="file.find", slots={"query": q}, confidence=0.9)


def match_open_result(text: str) -> Command | None:
    m = OPEN_RESULT_RE.match(text.strip())
    if m:
        return Command(intent="file.open_result", slots={"n": int(m.group("n"))}, confidence=0.9)
    return None


def match_knowledge(text: str) -> Command | None:
    m = KNOWLEDGE_RE.match(text.strip())
    if not m:
        return None
    topic = (m.group("t1") or m.group("t2") or m.group("t3") or "").strip().rstrip("?")
    if not topic:
        return None
    if re.search(r"\b(you|your|my name)\b", text, re.IGNORECASE):
        return None
    return Command(intent="knowledge.wiki", slots={"topic": topic}, confidence=0.8)


def match_info_query(text: str) -> Command | None:
    stripped = text.strip()
    for kind, pattern in INFO_QUERIES.items():
        if pattern.match(stripped):
            return Command(intent="info.query", slots={"kind": kind}, confidence=0.9)
    return None

GOAL_CREATE_RE = re.compile(r"^(?:add |new |create |set )?goals?\s+(?:to\s+|for\s+)?(?P<task>.+)$", re.IGNORECASE)
GOAL_LIST_RE = re.compile(r"^(?:list(?: my)? goals|what(?:'re| are) my goals\??|show(?: my)? goals\??)$", re.IGNORECASE)
GOAL_DELETE_RE = re.compile(r"^(?:delete|remove|cancel)\s+(?:the\s+)?goal\s+#?(?P<id>\d+)$", re.IGNORECASE)

MODE_SET_RE = re.compile(
    r"^(?:set\s+|switch to\s+|turn on\s+)?(?P<mode>dnd|do not disturb|silent|silence|muted?|normal)(?:\s+mode)?(?P<off>\s+off)?$",
    re.IGNORECASE,
)
MODE_OFF_RE = re.compile(
    r"^(?:turn|switch)\s+(?:off\s+)?(?P<mode>dnd|do not disturb|silent|silence|muted?)$",
    re.IGNORECASE,
)
MODE_QUERY_RE = re.compile(
    r"^(?:what mode (?:am i|are we) in\??|am i (?:on|in) (?P<qmode>dnd|silent|normal)(?: mode)?\??|current mode\??)$",
    re.IGNORECASE,
)

MODE_ALIASES = {
    "dnd": "dnd",
    "do not disturb": "dnd",
    "silent": "silent",
    "silence": "silent",
    "mute": "silent",
    "muted": "silent",
    "normal": "normal",
}


INTERVAL_TASK_RE = re.compile(
    r"^(?P<task>.+?)\s+every\s+(?P<interval>\d+)\s+(?P<unit>minutes?|mins?|hours?|hrs?)\s*$",
    re.IGNORECASE,
)


def match_interval_task(text: str) -> Command | None:
    m = INTERVAL_TASK_RE.match(text.strip())
    if not m:
        return None
    return Command(
        intent="reminder.create",
        slots={
            "task": m.group("task").strip(),
            "when": f"every {m.group('interval')} {m.group('unit')}",
        },
        confidence=0.9,
    )


def match_goal_create(text: str) -> Command | None:
    m = GOAL_CREATE_RE.match(text.strip())
    if not m:
        return None
    from intents.dates import split_task_and_when
    task, when = split_task_and_when(m.group("task"))
    if not task:
        return None
    return Command(intent="goal.create", slots={"task": task, "when": when}, confidence=0.9)


def match_goal_list(text: str) -> Command | None:
    if GOAL_LIST_RE.match(text.strip()):
        return Command(intent="goal.list", confidence=0.99)
    return None


def match_goal_delete(text: str) -> Command | None:
    m = GOAL_DELETE_RE.match(text.strip())
    if m:
        return Command(intent="goal.delete", slots={"id": int(m.group("id"))}, confidence=0.95)
    return None


def match_mode_set(text: str) -> Command | None:
    stripped = text.strip()
    m = MODE_SET_RE.match(stripped)
    if m:
        mode = MODE_ALIASES.get(m.group("mode").lower())
        if m.group("off"):
            mode = "normal"
        return Command(intent="mode.set", slots={"mode": mode}, confidence=0.95)
    off = MODE_OFF_RE.match(stripped)
    if off:
        return Command(intent="mode.set", slots={"mode": "normal"}, confidence=0.95)
    return None


def match_mode_query(text: str) -> Command | None:
    m = MODE_QUERY_RE.match(text.strip())
    if m:
        return Command(intent="mode.query", slots={"asked": m.group("qmode") or ""}, confidence=0.95)
    return None


def match_reminder_create(text: str) -> Command | None:
    m = REMIND_RE.match(text.strip())
    if not m:
        return None
    from intents.dates import split_task_and_when
    task, when = split_task_and_when(m.group("task"))
    if not task:
        return None
    return Command(
        intent="reminder.create",
        slots={"task": task, "when": when},
        confidence=0.95,
        requires_confirmation=not when,
    )


def match_reminder_list(text: str) -> Command | None:
    if LIST_REMINDERS.match(text.strip()):
        return Command(intent="reminder.list", confidence=0.99)
    return None


def match_reminder_done(text: str) -> Command | None:
    m = DONE_REMINDER.match(text.strip())
    if m:
        return Command(intent="reminder.done", slots={"id": int(m.group("id"))}, confidence=0.95)
    return None


def match_reminder_delete(text: str) -> Command | None:
    m = DELETE_REMINDER.match(text.strip())
    if m:
        return Command(intent="reminder.delete", slots={"id": int(m.group("id"))}, confidence=0.95)
    return None

DATE_FORMATS = ["%B %d", "%b %d", "%B %d %Y", "%Y-%m-%d", "%m/%d", "%m/%d/%Y"]


def parse_date(text: str):
    from datetime import datetime
    text = text.strip().rstrip("?").strip()
    normalized = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text, flags=re.IGNORECASE)
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(normalized, fmt).date()
        except ValueError:
            continue
    return None


def match_time_query(text: str) -> Command | None:
    if TIME_QUERY.match(text.strip()):
        return Command(intent="time.query", confidence=0.99)
    return None


def match_date_query(text: str) -> Command | None:
    if DATE_QUERY.match(text.strip()):
        return Command(intent="date.query", confidence=0.99)
    return None


def match_weekday(text: str) -> Command | None:
    m = WEEKDAY_QUERY.match(text.strip())
    if not m:
        return None
    when = m.group("when").strip()
    target = parse_date(when)
    if target is None:
        return None
    return Command(intent="date.weekday", slots={"date": target.isoformat()}, confidence=0.95)


def match_days_until(text: str) -> Command | None:
    m = DAYS_UNTIL.match(text.strip())
    if not m:
        return None
    when = m.group("when").strip()
    target = parse_date(when)
    if target is None:
        return None
    return Command(intent="date.until", slots={"date": target.isoformat()}, confidence=0.95)


def match_timezone(text: str) -> Command | None:
    m = SET_TIMEZONE.match(text.strip())
    if m:
        return Command(intent="time.set_timezone", slots={"tz": m.group("tz")}, confidence=0.99)
    return None


def match_help(text: str) -> Command | None:
    if HELP_PATTERN.match(text.strip()):
        return Command(intent="assistant.help", confidence=0.99)
    return None


def match_calculator(text: str) -> Command | None:
    for pattern in CALC_PATTERNS:
        m = pattern.match(text.strip())
        if not m:
            continue
        groups = m.groupdict()
        if "expr" in groups and "base" in groups:
            expr = f"{groups['expr']} / 100 * {groups['base']}"
        elif "base" in groups:
            expr = f"{groups['percent']} / 100 * {groups['base']}"
        elif "expr" in groups:
            expr = groups["expr"].replace(" of ", " * ")
            if not re.fullmatch(r"[\d\s\.\+\-\*/%\(\)]+", expr):
                continue
            expr = expr.replace("%", "/100")
        else:
            continue
        try:
            value = eval_math(expr)
        except Exception:
            continue
        if value is None:
            continue
        return Command(
            intent="math.calculate",
            slots={"expression": text.strip(), "result": value},
            confidence=0.95,
        )
    return None


def eval_math(expr: str):
    expr = expr.replace("%", "/100")
    if not re.fullmatch(r"[\d\s\.\+\-\*/\(\)/]+", expr):
        return None
    try:
        code = compile(expr, "<calc>", "eval")
        for name in code.co_names:
            return None
        return round(eval(code, {"__builtins__": {}}, {}), 6)
    except Exception:
        return None


def match_open_app(text: str) -> Command | None:
    m = OPEN_PATTERN.match(text.strip())
    if m:
        return Command(intent="system.open_app", slots={"app": m.group("app")}, confidence=0.9)
    return None


def match_close_app(text: str) -> Command | None:
    m = CLOSE_PATTERN.match(text.strip())
    if m:
        return Command(intent="system.close_app", slots={"app": m.group("app")}, confidence=0.9)
    return None


DISALLOW_RE = re.compile(
    r"^(?:please\s+)?disallow\s+(open|close)\s+(?P<name>.+?)\s*$", re.IGNORECASE
)
DISALLOW_BARE_RE = re.compile(
    r"^(?:please\s+)?disallow\s+(?P<name>.+?)\s*$", re.IGNORECASE
)
ALLOW_RE = re.compile(
    r"^(?:please\s+)?allow\s+(open|close)\s+(?P<rest>.+?)\s*$", re.IGNORECASE
)


def match_disallow(text: str) -> Command | None:
    s = text.strip()
    m = DISALLOW_RE.match(s)
    if m:
        return Command(
            intent="app.disallow",
            slots={"action": m.group(1).lower(), "name": m.group("name").strip()},
            confidence=0.95,
        )
    m = DISALLOW_BARE_RE.match(s)
    if m:
        # No open/close qualifier: drop the app from both allowlists.
        return Command(
            intent="app.disallow",
            slots={"action": None, "name": m.group("name").strip()},
            confidence=0.9,
        )
    return None


def match_allow(text: str) -> Command | None:
    s = text.strip()
    m = ALLOW_RE.match(s)
    if m:
        rest = m.group("rest").strip()
        parts = rest.split()
        if not parts:
            return None
        name = parts[0]
        command = parts[1:]
        return Command(
            intent="app.allow",
            slots={"action": m.group(1).lower(), "name": name, "command": command},
            confidence=0.95,
        )
    return None


def match_rename(text: str, current_name: str) -> Command | None:
    stripped = text.strip()
    for pattern in RENAME_PATTERNS:
        m = pattern.match(stripped)
        if m:
            return Command(
                intent="assistant.rename",
                slots={"name": m.group("name").strip()},
                confidence=0.99,
            )
    if SET_NAME_QUERY.match(stripped):
        return Command(
            intent="assistant.get_name",
            slots={"current_name": current_name},
            confidence=0.99,
        )
    return None


READ_RESULT_RE = re.compile(
    r"^read\s+(?:(?:result|article)\s+)?(\d+)$", re.IGNORECASE
)


def match_read_result(text: str) -> Command | None:
    m = READ_RESULT_RE.match(text.strip())
    if m:
        return Command(
            intent="article.read",
            slots={"n": int(m.group(1))},
            confidence=0.85,
        )
    return None


IMPORT_CALENDAR_RE = re.compile(
    r"^(?:import|load|add|sync)\s+calendar\s+(?:from\s+)?(.+)$", re.IGNORECASE
)


def match_import_calendar(text: str) -> Command | None:
    m = IMPORT_CALENDAR_RE.match(text.strip())
    if m and m.group(1).strip():
        return Command(
            intent="calendar.import",
            slots={"path": m.group(1).strip()},
            confidence=0.85,
        )
    return None
