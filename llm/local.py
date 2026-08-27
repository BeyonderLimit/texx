from __future__ import annotations

import json
import re

from llm.engine import ChatMessage, CompletionResult, UnavailableEngine


class LocalLLM:
    """Wrap a local GGUF model via ``llama-cpp-python``.

    Construction is lazy and never raises: if ``llama_cpp`` is not installed or
    ``model_path`` is missing/invalid, ``is_available()`` returns False and the
    engine acts as a no-op. This keeps Texx fully functional without a model.
    """

    def __init__(self, model_path: str | None = None, n_ctx: int = 4096, n_threads: int | None = None):
        self.model_path = model_path
        self._llama = None
        self._error = None
        if not model_path:
            self._error = "no model path configured"
            return
        try:
            from llama_cpp import Llama  # type: ignore
        except ImportError:
            self._error = "llama-cpp-python not installed"
            return
        try:
            kwargs = {"model_path": model_path, "n_ctx": n_ctx, "verbose": False}
            if n_threads:
                kwargs["n_threads"] = n_threads
            self._llama = Llama(**kwargs)
        except Exception as e:  # noqa: BLE001 — surface as unavailable
            self._error = f"failed to load model: {e}"
            self._llama = None

    def is_available(self) -> bool:
        return self._llama is not None

    def unavailable_reason(self) -> str:
        return self._error or "available"

    def chat(self, messages: list[ChatMessage]) -> CompletionResult:
        if not self.is_available():
            return CompletionResult(text="", raw="")
        payload = [{"role": m.role, "content": m.content} for m in messages]
        try:
            out = self._llama.create_chat_completion(
                messages=payload, max_tokens=512, temperature=0.7
            )
            text = out["choices"][0]["message"]["content"]
            usage = out.get("usage", {})
            return CompletionResult(text=text, raw=text, usage=usage)
        except Exception as e:  # noqa: BLE001
            self._error = f"inference error: {e}"
            return CompletionResult(text="", raw="")

    def complete(self, prompt: str, json_mode: bool = False) -> CompletionResult:
        if not self.is_available():
            return CompletionResult(text="", raw="")
        system = ""
        if json_mode:
            system = (
                "You output only valid JSON. No commentary, no markdown fences. "
                "Return a single JSON object and nothing else."
            )
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            out = self._llama.create_chat_completion(
                messages=messages, max_tokens=1024, temperature=0.2
            )
            raw = out["choices"][0]["message"]["content"]
            return CompletionResult(text=self._extract_json(raw) if json_mode else raw,
                                    raw=raw, usage=out.get("usage", {}))
        except Exception as e:  # noqa: BLE001
            self._error = f"inference error: {e}"
            return CompletionResult(text="", raw="")

    @staticmethod
    def _extract_json(raw: str) -> str:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        match = re.search(r"\{.*\}|\[.*\]", raw, re.DOTALL)
        if match:
            return match.group(0)
        return raw


def build_engine(model_path: str | None) -> "LocalLLM | UnavailableEngine":
    """Return a LocalLLM even when it fails to load — it tracks the real
    failure reason internally, so callers can report it honestly instead of
    seeing a generic 'no model configured'."""
    return LocalLLM(model_path)
