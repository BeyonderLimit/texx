import re
from datetime import datetime, timedelta

WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

DAY_PART_TIMES = {"morning": (9, 0), "afternoon": (13, 0), "evening": (18, 0), "night": (20, 0)}

DURATION_RE = re.compile(
    r"^in\s+(\d+)\s+(second|minute|hour|day|week)s?$", re.IGNORECASE
)
AT_TIME_RE = re.compile(
    r"^at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", re.IGNORECASE
)
EVERY_DAY_PART_RE = re.compile(r"^(morning|afternoon|evening|night)$", re.IGNORECASE)


def parse_duration(text: str, now: datetime) -> datetime | None:
    m = DURATION_RE.match(text.strip())
    if not m:
        return None
    amount = int(m.group(1))
    unit = m.group(2).lower()
    deltas = {
        "second": timedelta(seconds=amount),
        "minute": timedelta(minutes=amount),
        "hour": timedelta(hours=amount),
        "day": timedelta(days=amount),
        "week": timedelta(weeks=amount),
    }
    return now + deltas[unit]


def parse_clock_time(text: str) -> tuple[int, int] | None:
    m = AT_TIME_RE.match(text.strip())
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    meridiem = (m.group(3) or "").lower()
    if meridiem == "pm" and hour != 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def parse_weekday(text: str) -> int | None:
    text = text.strip().lower()
    text = re.sub(r"^on\s+", "", text)
    return WEEKDAYS.get(text.rstrip("s"))


def next_weekly(now: datetime, weekday: int, hour: int, minute: int) -> datetime:
    days_ahead = (weekday - now.weekday()) % 7
    candidate = (now + timedelta(days=days_ahead)).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate


def next_daily(now: datetime, hour: int, minute: int) -> datetime:
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def split_task_and_when(text: str) -> tuple[str, str]:
    """Split 'call Sarah at 5pm' -> ('call Sarah', 'at 5pm').

    Handles trailing when-phrases and leading ones ('in 10 minutes check the oven').
    """
    leading = _extract_leading_when(text)
    if leading:
        return leading

    triggers = [
        r"\bevery\b",
        r"\bat\b",
        r"\bin\s+\d+\s+(?:second|minute|hour|day|week)s?\b",
        r"\btomorrow\b",
        r"\btoday\b",
        r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?\b",
    ]
    cut = len(text)
    for pattern in triggers:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            start = m.start()
            tail = text[start:].strip()
            if _looks_like_when(tail):
                cut = min(cut, start)
    task = text[:cut].strip().rstrip(",")
    when = text[cut:].strip()
    return task, when


LEADING_WHEN_RE = re.compile(
    r"^(?P<when>in\s+\d+\s+(?:second|minute|hour|day|week)s?"
    r"|at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?"
    r"|every\s+\d+\s+(?:second|minute|hour|day|week)s?"
    r"|every\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
    r"|every\s+(?:morning|afternoon|evening|night)"
    r"|tomorrow|today)"
    r"(?:\s+on\b|\s+at\b)?[,: ]\s*(?:to\s+)?(?P<task>.+)$",
    re.IGNORECASE,
)


def _extract_leading_when(text: str) -> tuple[str, str] | None:
    m = LEADING_WHEN_RE.match(text.strip())
    if not m:
        return None
    when = m.group("when").strip()
    task = m.group("task").strip()
    if not task:
        return None
    return task, when


def _looks_like_when(tail: str) -> bool:
    tail = tail.strip()
    if not tail:
        return False
    lowered = tail.lower()
    if lowered.startswith("every"):
        return True
    if re.match(r"^in\s+\d+\s+(second|minute|hour|day|week)s?$", lowered):
        return True
    if parse_clock_time(lowered):
        return True
    first_word = lowered.split()[0].rstrip("s")
    if first_word in WEEKDAYS and len(lowered.split()) <= 2:
        return True
    if first_word in ("today", "tomorrow"):
        return True
    return False


def parse_when(when_text: str, now: datetime) -> tuple[datetime | None, str | None]:
    """Parse a when-phrase into (due_at, recurrence_rule).

    Returns (None, None) if unparseable.
    """
    text = when_text.strip()
    lowered = text.lower()

    duration = parse_duration(lowered, now)
    if duration:
        return duration, None

    every_match = re.match(r"^every\s+(.+)$", lowered)
    if every_match:
        interval_match = re.match(
            r"^(\d+)\s+(minutes?|mins?|hours?|hrs?)\b", every_match.group(1).strip()
        )
        if interval_match:
            n = int(interval_match.group(1))
            unit = interval_match.group(2)
            freq = "HOURLY" if unit.startswith(("hour", "hr")) else "MINUTELY"
            due = now + timedelta(hours=n) if freq == "HOURLY" else now + timedelta(minutes=n)
            return due.replace(second=0, microsecond=0), f"FREQ={freq};INTERVAL={n}"
        rest = every_match.group(1).strip()
        day_part = None
        for part in DAY_PART_TIMES:
            if part in rest:
                day_part = part
                rest = re.sub(rf"\b{part}\b", "", rest).strip()
                break
        clock_match = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", rest)
        if clock_match:
            clock = parse_clock_time(clock_match.group(0))
            rest = (rest[:clock_match.start()] + " " + rest[clock_match.end():]).strip()
        else:
            clock = None
        hour, minute = clock or DAY_PART_TIMES.get(day_part or "", (9, 0))

        target = re.sub(r"^(?:on|the)\s+", "", rest).strip().rstrip("s")
        if target in ("", "day"):
            due = next_daily(now, hour, minute)
            return due, "FREQ=DAILY"
        if target == "weekday":
            return None, None
        if target in WEEKDAYS:
            due = next_weekly(now, WEEKDAYS[target], hour, minute)
            byday = target[:2].upper()
            return due, f"FREQ=WEEKLY;BYDAY={byday}"
        return None, None

    date_target = _parse_date_part(lowered, now)
    if date_target is not None:
        base_date, remaining = date_target
        clock = parse_clock_time(remaining) if remaining else None
        if remaining and not clock and remaining.strip() not in ("", "on", "at"):
            return None, None
        hour, minute = clock or (9, 0)
        due = base_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if due < now and not clock and remaining == "":
            due += timedelta(days=1)
        return due, None

    clock = parse_clock_time(lowered)
    if clock:
        due = next_daily(now, *clock)
        return due, None

    weekday = parse_weekday(lowered)
    if weekday is not None:
        day_part = next((p for p in DAY_PART_TIMES if p in lowered), None)
        hour, minute = DAY_PART_TIMES.get(day_part, (9, 0))
        due = next_weekly(now, weekday, hour, minute)
        byday = list(WEEKDAYS)[weekday][:2].upper()
        return due, None

    return None, None


def _parse_date_part(text: str, now: datetime):
    """Match leading date words. Returns (date_with_time_00:00, remainder) or None."""
    from intents.rules import parse_date as parse_plain_date

    text = text.strip()
    words = text.split()
    if not words:
        return None
    if words[0] == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0), " ".join(words[1:])
    if words[0] == "tomorrow":
        d = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return d, " ".join(words[1:])
    for take in (len(words), len(words) - 1):
        if take < 1:
            continue
        candidate = " ".join(words[:take])
        parsed = parse_plain_date(candidate.rstrip(","))
        if parsed is not None and parsed.year >= 2000:
            if take == len(words) or words[take] in ("at", "on"):
                d = datetime(parsed.year, parsed.month, parsed.day)
                return d, " ".join(words[take:])
    return None
