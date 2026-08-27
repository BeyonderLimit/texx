from core.commands import Command
from intents.rules import (
    match_appointments,
    match_brief,
    match_calculator,
    match_close_app,
    match_date_query,
    match_days_until,
    match_goal_create,
    match_goal_delete,
    match_goal_list,
    match_help,
    match_interval_task,
    match_mode_query,
    match_mode_set,
    match_forget,
    match_memory_list,
    match_note_take,
    match_notes_list,
    match_knowledge,
    match_local_find,
    match_open_result,
    match_read_result,
    match_web_search,
    match_open_app,
    match_recall,
    match_reminder_create,
    match_reminder_delete,
    match_reminder_done,
    match_reminder_list,
    match_rename,
    match_info_query,
    match_weather,
    match_set_location,
    match_status,
    match_task_add,
    match_task_delete,
    match_task_done,
    match_task_list,
    match_time_query,
    match_timezone,
    match_timer,
    match_weekday,
    match_remember,
    match_import_calendar,
)

INTENT_EXAMPLES = {
    "system.open_app": [
        "open firefox",
        "launch chrome",
        "start spotify",
        "open my files",
        "start my browser",
    ],
    "system.close_app": [
        "close firefox",
        "quit chrome",
        "close spotify",
    ],
    "math.calculate": [
        "what's 15% of 240",
        "calculate 12 * 8",
        "what is 2 plus 2",
    ],
    "assistant.rename": [
        "call yourself athena",
        "your name is now jarvis",
    ],
}


class RuleMatcher:
    def __init__(self, settings):
        self.settings = settings

    def match(self, text: str) -> Command | None:
        for matcher in (
            lambda t: match_rename(t, self.settings.get("assistant_name")),
            match_help,
            match_timer,
            match_open_result,
            match_read_result,
            match_time_query,
            match_date_query,
            match_weekday,
            match_days_until,
            match_timezone,
            match_mode_query,
            match_mode_set,
            match_brief,
            match_appointments,
            match_status,
            match_weather,
            match_set_location,
            match_info_query,
            match_goal_list,
            match_goal_delete,
            match_goal_create,
            match_task_add,
            match_task_list,
            match_task_done,
            match_task_delete,
            match_note_take,
            match_notes_list,
            match_interval_task,
            match_remember,
            match_recall,
            match_memory_list,
            match_forget,
            match_reminder_list,
            match_reminder_done,
            match_reminder_delete,
            match_reminder_create,
            match_calculator,
            match_close_app,
            match_open_app,
            match_local_find,
            match_web_search,
            match_knowledge,
            match_import_calendar,
        ):
            result = matcher(text)
            if result:
                return result
        return None


class FuzzyMatcher:
    def __init__(self, threshold: float = 0.75):
        self.threshold = threshold

    def match(self, text: str) -> Command | None:
        try:
            from rapidfuzz import fuzz
        except ImportError:
            return None
        normalized = text.strip().lower()
        best: tuple[str, float] = ("", 0.0)
        for intent, examples in INTENT_EXAMPLES.items():
            for example in examples:
                score = fuzz.ratio(normalized, example)
                if score > best[1]:
                    best = (intent, score)
        confidence = best[1] / 100.0
        if confidence < self.threshold:
            return None
        return Command(
            intent=best[0],
            slots=self._extract_slots(best[0], normalized),
            confidence=confidence,
            source="fuzzy",
        )

    def _extract_slots(self, intent: str, text: str) -> dict:
        from intents.rules import OPEN_PATTERN, CLOSE_PATTERN
        if intent == "system.open_app":
            m = OPEN_PATTERN.match(text)
            if m:
                return {"app": m.group("app")}
        if intent == "system.close_app":
            m = CLOSE_PATTERN.match(text)
            if m:
                return {"app": m.group("app")}
        return {}
