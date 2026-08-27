from __future__ import annotations

import json
from typing import Protocol, runtime_checkable


@runtime_checkable
class SpeechToText(Protocol):
    def is_available(self) -> bool: ...
    def transcribe(self, audio: bytes) -> str: ...


class OffSTT:
    """No-op STT used when Vosk is unavailable."""

    def is_available(self) -> bool:
        return False

    def transcribe(self, audio: bytes) -> str:
        return ""


class VoskSTT:
    """Offline speech-to-text via ``vosk`` (lazy import). Expects 16 kHz mono 16-bit PCM."""

    def __init__(self, model_path: str | None = None):
        self.model_path = model_path
        self._model = None
        self._error: str | None = None
        if not model_path:
            self._error = "no model path configured"
            return
        try:
            from vosk import Model, SetLogLevel  # type: ignore
        except ImportError:
            self._error = "vosk not installed"
            return
        try:
            SetLogLevel(-1)
            self._model = Model(model_path)
        except Exception as e:  # noqa: BLE001
            self._error = f"failed to load model: {e}"
            self._model = None

    def is_available(self) -> bool:
        return self._model is not None

    def unavailable_reason(self) -> str:
        return self._error or "available"

    def transcribe(self, audio: bytes) -> str:
        if not self.is_available():
            return ""
        assert self._model is not None
        from vosk import KaldiRecognizer

        rec = KaldiRecognizer(self._model, 16000)
        rec.AcceptWaveform(audio)
        result = json.loads(rec.Result())
        return (result.get("text") or "").strip()
