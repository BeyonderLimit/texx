import subprocess
from pathlib import Path


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def battery() -> str:
    base = Path("/sys/class/power_supply")
    try:
        supplies = sorted(base.iterdir())
    except OSError:
        return "unknown"
    for supply in supplies:
        if not supply.name.startswith(("BAT", "bat")):
            continue
        capacity = _read(str(supply / "capacity"))
        if capacity is None:
            continue
        status = (_read(str(supply / "status")) or "").lower()
        state = "charging" if status == "charging" else "discharging"
        return f"{capacity}% ({state})"
    if any(s.name.startswith("AC") for s in supplies):
        return "on AC power (no battery)"
    return "unknown"


def volume() -> str:
    try:
        out = subprocess.run(
            ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
            capture_output=True, text=True, timeout=2,
        )
        m = out.stdout.split()[0] if out.stdout else ""
        if "%" in m:
            left = m.lstrip("|")
            muted_out = subprocess.run(
                ["pactl", "get-sink-mute", "@DEFAULT_SINK@"],
                capture_output=True, text=True, timeout=2,
            )
            muted = "yes" in muted_out.stdout.lower()
            return f"{left}{' (muted)' if muted else ''}"
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        out = subprocess.run(
            ["amixer", "get", "Master"], capture_output=True, text=True, timeout=2
        )
        import re
        m = re.search(r"\[(\d+%)\]", out.stdout)
        if m:
            return m.group(1)
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "unknown"


def brightness() -> str:
    base = Path("/sys/class/backlight")
    try:
        devices = list(base.iterdir())
    except OSError:
        devices = []
    for dev in devices:
        cur = _read(str(dev / "brightness"))
        mx = _read(str(dev / "max_brightness"))
        if cur and mx and int(mx) > 0:
            pct = round(int(cur) / int(mx) * 100)
            return f"{pct}%"
    return "unknown"


def running_processes(limit: int = 6) -> str:
    procs = []
    proc_dir = Path("/proc")
    try:
        pids = [p for p in proc_dir.iterdir() if p.name.isdigit()]
    except OSError:
        return "unknown"
    for pid_dir in pids:
        try:
            stat = {}
            for line in (pid_dir / "status").read_text().splitlines():
                if line.startswith(("Name:", "VmRSS:", "State:")):
                    key, _, val = line.partition(":")
                    stat[key.strip()] = val.strip()
            if not stat.get("Name"):
                continue
            rss_kb = 0
            rss_raw = stat.get("VmRSS", "")
            if rss_raw:
                rss_kb = int(rss_raw.split()[0])
            procs.append((rss_kb, stat["Name"], stat.get("State", "?")))
        except (OSError, ValueError, IndexError):
            continue
    total = len(procs)
    running = [p for p in procs if p[2].startswith("R")]
    procs.sort(reverse=True)
    names = []
    seen = set()
    for _, name, _state in procs:
        if name not in seen:
            seen.add(name)
            names.append(name)
        if len(names) >= limit:
            break
    detail = ", ".join(names) if names else "n/a"
    extra = f"; {len(running)} actively running" if running else ""
    return f"{total} processes{extra} — top: {detail}"


def upcoming_event(reminders) -> str:
    from datetime import datetime
    rows = [
        r for r in reminders.list_pending(category="event")
        if r["due_at"] and datetime.fromisoformat(r["due_at"]) >= datetime.now()
    ]
    if not rows:
        return "none scheduled"
    row = min(rows, key=lambda r: r["due_at"])
    due = datetime.fromisoformat(row["due_at"])
    time_str = due.strftime("%I:%M %p").lstrip("0")
    day = "" if due.date() == datetime.now().date() else f" {due.strftime('%a %b %d')}"
    return f"{row['task']} at {time_str}{day}"


def todo_items(tasks_service, limit: int = 8) -> list[str]:
    tasks_service.purge_expired()
    rows = tasks_service.list_open()
    out = []
    for r in rows[:limit]:
        pr = f" [{r['priority'].upper()}]" if r["priority"] != "normal" else ""
        out.append(f"#{r['id']} {r['title']}{pr}")
    return out


def full_status(states, settings, reminders, time_service, tasks=None, voice=None) -> str:
    from datetime import datetime
    from core.state import AssistantState
    c = time_service.context()
    mode = settings.get("mode", "normal").upper()
    state = states.state.value if states.state != AssistantState.EXECUTING else "idle"
    todos = todo_items(tasks) if tasks is not None else []
    lines = [
        f"State: {state} · Mode: {mode}",
        f"Time: {c['time']} — {c['date']}",
        "",
        f"Battery:    {battery()}",
        f"Volume:     {volume()}",
        f"Brightness: {brightness()}",
        f"Processes:  {running_processes()}",
        f"Voice:     {voice}",
        "",
        f"Next event/timer: {upcoming_event(reminders)}",
        "",
        "TODO (not completed):",
    ]
    if todos:
        lines += [f"• {t}" for t in todos]
    else:
        lines.append("• nothing outstanding")
    return "\n".join(lines)
