from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class CompletionResult:
    text: str
    raw: str = ""
    usage: dict = field(default_factory=dict)


@runtime_checkable
class LLMEngine(Protocol):
    """Minimal contract every LLM backend must satisfy."""

    def is_available(self) -> bool: ...

    def chat(self, messages: list[ChatMessage]) -> CompletionResult: ...

    def complete(self, prompt: str, json_mode: bool = False) -> CompletionResult: ...


class UnavailableEngine:
    """Used when no model is configured; every call explains the situation."""

    def is_available(self) -> bool:
        return False

    def chat(self, messages: list[ChatMessage]) -> CompletionResult:
        return CompletionResult(text="", raw="")

    def complete(self, prompt: str, json_mode: bool = False) -> CompletionResult:
        return CompletionResult(text="", raw="")
