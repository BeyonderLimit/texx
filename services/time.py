from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass
class ParsedDate:
    date: object
    kind: str


class TimeService:
    def __init__(self, settings):
        self.settings = settings

    def tz(self):
        name = self.settings.get("timezone")
        if name:
            try:
                return ZoneInfo(name)
            except ZoneInfoNotFoundError:
                pass
        return None

    def now(self) -> datetime:
        return datetime.now(self.tz()) if self.tz() else datetime.now().astimezone()

    def timezone_name(self) -> str:
        return str(self.now().tzinfo)

    def set_timezone(self, name: str) -> bool:
        try:
            ZoneInfo(name)
        except ZoneInfoNotFoundError:
            return False
        self.settings.set("timezone", name)
        return True

    def time_str(self) -> str:
        return self.now().strftime("%I:%M %p").lstrip("0")

    def date_str(self) -> str:
        return self.now().strftime("%A, %B %d, %Y")

    def context(self) -> dict:
        n = self.now()
        return {
            "iso": n.isoformat(timespec="seconds"),
            "time": self.time_str(),
            "date": self.date_str(),
            "weekday": n.strftime("%A"),
            "timezone": self.timezone_name(),
        }

    def weekday_of(self, d) -> str:
        return d.strftime("%A")

    def days_until(self, target) -> int:
        today = self.now().date()
        if isinstance(target, datetime):
            target = target.date()
        if target < today:
            target = target.replace(year=today.year + 1)
        return (target - today).days

    def next_occurrence(self, month: int, day: int):
        today = self.now().date()
        candidate = today.replace(month=month, day=day)
        if candidate < today:
            candidate = candidate.replace(year=today.year + 1)
        return candidate
