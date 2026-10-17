from __future__ import annotations

import json
import threading
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

CONDENSE_PROMPT = (
    "Condense the following notes into a compact summary for future reference. "
    "Keep concrete facts, names, numbers, decisions and open threads. Drop filler "
    "and pleasantries. Use short bullet lines. No preamble, no headings, no "
    "meta-commentary about the summarising. If the notes contain nothing worth "
    "keeping, reply with exactly: (nothing worth keeping)"
)


class LLMManager:
    """Bounded conversational service. Optional — degrades to None when no model.

    Every engine call is serialized on a single lock. Inference is CPU-bound and
    a llama.cpp model handle is not safe for concurrent use, so callers may
    invoke these methods from a worker thread (``asyncio.to_thread``) while the
    Helper tick runs on the event loop — the lock makes that safe rather than a
    corruption hazard.
    """

    def __init__(self, model_path: str | None = None):
        self.model_path = model_path
        self._engine: Any = build_engine(model_path)
        self._lock = threading.Lock()

    def set_model(self, model_path: str | None) -> None:
        with self._lock:
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
        with self._lock:
            result = self._engine.chat(messages)
        return result.text.strip()

    def extract_memories(self, text: str) -> list[dict]:
        if not self.is_available():
            return []
        with self._lock:
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

    def condense(self, text: str) -> str:
        """Summarise free text into compact notes.

        Called by Phase 7 background maintenance (``services/memory.py`` and
        ``services/owner.py``) to fold yesterday's discussion into a ``daily``
        memory and to condense ``OWNER.md``. It has to live on the *manager*:
        those services are handed an ``LLMManager``, and an ``AttributeError``
        here is swallowed into a silent fallback to raw concatenation.
        """
        if not self.is_available() or not text.strip():
            return ""
        with self._lock:
            result = self._engine.complete(CONDENSE_PROMPT + "\n\n" + text)
        out = (result.text or "").strip()
        if out.lower().startswith("(nothing worth keeping)"):
            return ""
        return out
