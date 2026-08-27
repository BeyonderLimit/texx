from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class TextToSpeech(Protocol):
    def is_available(self) -> bool: ...
    def speak(self, text: str) -> None: ...


class OffTTS:
    """No-op TTS used when Piper is unavailable. Voice still works without speech output."""

    def is_available(self) -> bool:
        return False

    def speak(self, text: str) -> None:
        return None


def _play_wav(path: Path) -> None:
    """Play a WAV via a system player, fully detached (non-blocking, no TUI pollution)."""
    for player in ("paplay", "aplay", "play"):
        try:
            subprocess.Popen(
                [player, str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
            return
        except (FileNotFoundError, OSError):
            continue


class PiperTTS:
    """Local neural TTS via ``piper-tts`` (lazy import). Model file is user-supplied."""

    def __init__(self, voice_path: str | None = None):
        self.voice_path = voice_path
        self._voice = None
        self._error: str | None = None
        if not voice_path:
            self._error = "no voice path configured"
            return
        try:
            from piper import PiperVoice  # type: ignore
        except ImportError:
            self._error = "piper-tts not installed"
            return
        try:
            self._voice = PiperVoice.load(voice_path)
        except Exception as e:  # noqa: BLE001
            self._error = f"failed to load voice: {e}"
            self._voice = None

    def is_available(self) -> bool:
        return self._voice is not None

    def unavailable_reason(self) -> str:
        return self._error or "available"

    def speak(self, text: str) -> None:
        if not self.is_available():
            return
        assert self._voice is not None
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = Path(f.name)
        try:
            import wave

            with wave.open(str(wav_path), "wb") as wav_file:
                # synthesize_wav sets the WAV header params from the model config
                # and writes the audio; the bare `synthesize` API only yields
                # chunks and would leave the header unset (wave close -> error).
                self._voice.synthesize_wav(text, wav_file)
            _play_wav(wav_path)
        except Exception as e:  # noqa: BLE001
            # Playback must never crash the caller (e.g. voice mode).
            import sys
            print(f"[piper] TTS failed: {e}", file=sys.stderr)
        finally:
            try:
                wav_path.unlink()
            except OSError:
                pass
