from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from voice.recorder import OffRecorder, Recorder, SounddeviceRecorder
from voice.stt import OffSTT, SpeechToText, VoskSTT
from voice.tts import OffTTS, PiperTTS, TextToSpeech
from voice.vad import EnergyVAD, VoiceActivityDetector

UtteranceHandler = Callable[[str], Awaitable[str]]


class VoiceController:
    """Push-to-talk orchestration (spec §8): record -> VAD -> STT -> handler -> TTS.

    All backends are optional. Voice is usable as long as a recorder + STT exist;
    TTS is a bonus (responses still print without it). The capture call is
    blocking, so it runs in an executor thread when called from async code.
    """

    def __init__(self, recorder: Recorder | None = None, stt: SpeechToText | None = None,
                 tts: TextToSpeech | None = None, vad: VoiceActivityDetector | None = None):
        self.recorder = recorder if recorder is not None else SounddeviceRecorder(vad or EnergyVAD())
        self.stt = stt if stt is not None else VoskSTT()
        self.tts = tts if tts is not None else OffTTS()
        self.enabled = False

    def is_available(self) -> bool:
        return self.recorder.is_available() and self.stt.is_available()

    def unavailable_reason(self) -> str:
        if not self.recorder.is_available():
            return getattr(self.recorder, "unavailable_reason", lambda: "no recorder")()
        if not self.stt.is_available():
            return getattr(self.stt, "unavailable_reason", lambda: "no STT")()
        return "available"

    def component_status(self) -> str:
        def _part(label, comp):
            if comp.is_available():
                label_extra = ""
                if label == "Mic":
                    label_extra = f" ({comp.device_label()})"
                return f"{label}: loaded{label_extra}"
            reason = getattr(comp, "unavailable_reason", lambda: "unavailable")()
            return f"{label}: {reason}"
        return " · ".join([
            _part("Mic", self.recorder),
            _part("Vosk", self.stt),
            _part("Piper", self.tts),
        ])

    async def capture_utterance(self) -> str | None:
        """Record and transcribe one utterance. Returns text, or None on timeout/no speech."""
        if not self.is_available():
            return None
        loop = asyncio.get_event_loop()
        audio = await loop.run_in_executor(None, self.recorder.record_until_silence)
        if not audio:
            return None
        return await loop.run_in_executor(None, self.stt.transcribe, audio)

    def begin_capture(self) -> bool:
        """Hold-to-talk start: open the mic and begin accumulating audio."""
        if not self.is_available():
            return False
        self.recorder.begin()
        return True

    async def finish_capture(self) -> str | None:
        """Hold-to-talk end: stop the mic, transcribe the captured audio, return text."""
        if not self.is_available():
            return None
        loop = asyncio.get_event_loop()
        audio = await loop.run_in_executor(None, self.recorder.end)
        if not audio:
            return None
        return await loop.run_in_executor(None, self.stt.transcribe, audio)

    def speak(self, text: str) -> None:
        if not self.tts.is_available():
            return
        try:
            self.tts.speak(text)
        except Exception as e:  # noqa: BLE001
            import sys
            print(f"[voice] TTS error (ignored): {e}", file=sys.stderr)

    async def converse(self, handler: UtteranceHandler, speak: bool = True) -> str | None:
        """Capture one utterance, run it through `handler` (route+execute), then
        optionally speak the response. Returns the response text."""
        text = await self.capture_utterance()
        if not text:
            return None
        response = await handler(text)
        if speak:
            await asyncio.get_event_loop().run_in_executor(None, self.speak, response)
        return response
