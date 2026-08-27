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
    """Play a WAV, raising if no backend succeeds (so the caller can surface it).

    Tries system players first, then falls back to sounddevice (already a voice
    dependency) which uses the same audio stack as the mic. We block until the
    player exits, because the caller deletes the temp file right after return.
    """
    last_err = None
    for player in ("paplay", "aplay", "play"):
        try:
            r = subprocess.run(
                [player, str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                check=False,
            )
            if r.returncode == 0:
                return
            last_err = f"{player} exited {r.returncode}"
        except (FileNotFoundError, OSError) as e:
            last_err = str(e)
            continue
    # Fallback: play directly via sounddevice (lazy import).
    try:
        import wave

        import sounddevice as sd  # type: ignore

        with wave.open(str(path), "rb") as wf:
            data = wf.readframes(wf.getnframes())
            sd.play(data, samplerate=wf.getframerate())
            sd.wait()
        return
    except Exception as e:  # noqa: BLE001
        last_err = f"{last_err}; sounddevice fallback failed: {e}"
    raise RuntimeError(f"no audio backend could play the clip ({last_err})")


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

            wav_file = wave.open(str(wav_path), "wb")
            try:
                # synthesize_wav sets the WAV header params from the model
                # config and writes the audio; the bare `synthesize` API only
                # yields chunks and would leave the header unset. If it raises,
                # close the (headerless) file without masking the real cause.
                self._voice.synthesize_wav(text, wav_file)
            except BaseException:
                try:
                    wav_file.close()
                except Exception:  # noqa: BLE001
                    pass
                raise
            wav_file.close()
            _play_wav(wav_path)
        finally:
            try:
                wav_path.unlink()
            except OSError:
                pass
