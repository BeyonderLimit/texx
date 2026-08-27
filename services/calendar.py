import re
from datetime import datetime, timedelta
from pathlib import Path


def parse_ics(filepath: Path, horizon_days: int = 30) -> list[dict]:
    """Parse a local .ics file and return upcoming events within horizon_days."""
    text = filepath.read_text(encoding="utf-8", errors="replace")
    now = datetime.now()
    cutoff = now + timedelta(days=horizon_days)
    events = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, re.DOTALL):
        dtstart = _extract(block, "DTSTART")
        dtend = _extract(block, "DTEND")
        summary = _extract(block, "SUMMARY") or "Untitled event"
        description = _extract(block, "DESCRIPTION") or ""
        location = _extract(block, "LOCATION") or ""
        uid = _extract(block, "UID") or ""
        start = _parse_dt(dtstart)
        if start is None or start > cutoff:
            continue
        events.append({
            "uid": uid,
            "summary": summary,
            "start": start.isoformat(),
            "end": _parse_dt(dtend).isoformat() if dtend else "",
            "description": description.replace("\\n", "\n").replace("\\,", ","),
            "location": location,
            "source": filepath.name,
        })
    events.sort(key=lambda e: e["start"])
    return events


def _extract(block: str, key: str) -> str | None:
    m = re.search(rf"^{key}[^:]*:(.+)$", block, re.MULTILINE | re.IGNORECASE)
    return m.group(1).strip() if m else None


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M%SZ", "%Y%m%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None
