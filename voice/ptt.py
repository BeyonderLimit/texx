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

    async def capture_utterance(self) -> str | None:
        """Record and transcribe one utterance. Returns text, or None on timeout/no speech."""
        if not self.is_available():
            return None
        loop = asyncio.get_event_loop()
        audio = await loop.run_in_executor(None, self.recorder.record_until_silence)
        if not audio:
            return None
        return await loop.run_in_executor(None, self.stt.transcribe, audio)

    def speak(self, text: str) -> None:
        if self.tts.is_available():
            self.tts.speak(text)

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
