from core.commands import Command
from intents.matcher import FuzzyMatcher, RuleMatcher


class IntentRouter:
    def __init__(self, settings):
        self.rules = RuleMatcher(settings)
        self.fuzzy = FuzzyMatcher()

    def route(self, text: str) -> Command:
        result = self.rules.match(text)
        if result and result.confidence >= 0.85:
            return result
        fuzzy = self.fuzzy.match(text)
        if fuzzy and (not result or fuzzy.confidence > result.confidence):
            return fuzzy
        if result:
            return result
        return Command(intent="conversation.chat", slots={"text": text}, confidence=0.0, source="fallback")
