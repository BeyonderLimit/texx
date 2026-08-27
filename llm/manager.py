from __future__ import annotations

import json
from typing import Any

from llm.engine import ChatMessage, UnavailableEngine
from llm.local import LocalLLM, build_engine

SYSTEM_PROMPT = (
    "You are Texx, a concise offline-first personal assistant running on the "
    "user's Linux machine. You speak plainly and briefly. You do not pretend to "
    "control the system — for actions the user should use commands. Answer the "
    "user's question or continue the conversation helpfully."
)

MEMORY_PROMPT = (
    "Read the following exchange and extract any durable facts worth remembering "
    "about the user (preferences, people, projects, commitments, self-descriptions). "
    "Return a JSON array of objects with keys: content (string), category "
    "(one of PROFILE, PREFERENCE, PEOPLE, PROJECT, FACT), importance (integer 1-10). "
    "If nothing is worth remembering, return an empty array []."
)


class LLMManager:
    """Bounded conversational service. Optional — degrades to None when no model."""

    def __init__(self, model_path: str | None = None):
        self.model_path = model_path
        self._engine: Any = build_engine(model_path)

    def set_model(self, model_path: str | None) -> None:
        self.model_path = model_path
        self._engine = build_engine(model_path)

    def is_available(self) -> bool:
        return self._engine is not None and self._engine.is_available()

    def unavailable_reason(self) -> str:
        if self._engine is None:
            return "no engine"
        return self._engine.unavailable_reason()

    def respond(self, user_text: str, history: list[ChatMessage] | None = None) -> str:
        if not self.is_available():
            return ""
        messages = [ChatMessage("system", SYSTEM_PROMPT)]
        if history:
            messages.extend(history)
        messages.append(ChatMessage("user", user_text))
        result = self._engine.chat(messages)
        return result.text.strip()

    def extract_memories(self, text: str) -> list[dict]:
        if not self.is_available():
            return []
        result = self._engine.complete(MEMORY_PROMPT + "\n\n" + text, json_mode=True)
        if not result.text:
            return []
        try:
            data = json.loads(result.text)
        except (json.JSONDecodeError, ValueError):
            return []
        if not isinstance(data, list):
            return []
        cleaned = []
        for item in data:
            if not isinstance(item, dict) or not item.get("content"):
                continue
            cleaned.append({
                "content": str(item["content"]),
                "category": str(item.get("category", "FACT")).upper(),
                "importance": int(item.get("importance", 5)),
            })
        return cleaned
