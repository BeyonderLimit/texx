from __future__ import annotations

from typing import Protocol, runtime_checkable

from voice.vad import EnergyVAD, VoiceActivityDetector


@runtime_checkable
class Recorder(Protocol):
    def is_available(self) -> bool: ...
    def record_until_silence(self, silence_ms: int = 900, max_ms: int = 15000,
                             timeout_ms: int = 20000) -> bytes | None: ...
    def begin(self) -> None: ...
    def end(self) -> bytes | None: ...


class OffRecorder:
    """No-op recorder when no microphone/sounddevice is available."""

    def is_available(self) -> bool:
        return False

    def record_until_silence(self, silence_ms: int = 900, max_ms: int = 15000,
                             timeout_ms: int = 20000) -> bytes | None:
        return None

    def begin(self) -> None:
        return None

    def end(self) -> bytes | None:
        return None


class SounddeviceRecorder:
    """Captures 16 kHz mono 16-bit PCM from the default mic, endpointing on VAD.

    ``sounddevice`` is imported lazily so Texx runs without it. The blocking
    capture is meant to be run in an executor thread by the controller.
    """

    SAMPLERATE = 16000
    BLOCK = 4096  # bytes per read (~128 ms at 16 kHz/16-bit)

    def __init__(self, vad: VoiceActivityDetector | None = None, device=None):
        self.vad = vad or EnergyVAD()
        self._device = device  # None => system default; else index or name
        self._sd = None
        self._error: str | None = None
        self._stream = None
        self._buf = bytearray()
        try:
            import sounddevice  # type: ignore
            self._sd = sounddevice
        except (ImportError, OSError):
            self._error = "sounddevice not available"
            self._sd = None

    def is_available(self) -> bool:
        return self._sd is not None

    def unavailable_reason(self) -> str:
        return self._error or "available"

    def device_label(self) -> str:
        if not self.is_available():
            return self.unavailable_reason()
        if self._device is None:
            return "default"
        return str(self._device)

    @staticmethod
    def list_input_devices() -> list[dict]:
        """Return input-capable devices as [{'index','name','channels'}]."""
        try:
            import sounddevice as sd  # type: ignore
        except (ImportError, OSError):
            return []
        out = []
        try:
            for i, dev in enumerate(sd.query_devices()):
                ch = dev.get("max_input_channels", 0)
                if ch and ch > 0:
                    out.append({
                        "index": i,
                        "name": dev.get("name", f"device {i}"),
                        "channels": ch,
                    })
        except Exception:  # noqa: BLE001
            return out
        return out

    def begin(self) -> None:
        """Open the mic stream and start accumulating audio (hold-to-talk start)."""
        if not self.is_available() or self._stream is not None:
            return
        sd = self._sd
        self._buf = bytearray()
        self._stream = sd.RawInputStream(
            samplerate=self.SAMPLERATE, blocksize=self.BLOCK // 2,
            dtype="int16", channels=1, callback=self._on_audio,
            device=self._device,
        )
        self._stream.start()

    def _on_audio(self, indata, frames, time_info, status):
        self._buf.extend(bytes(indata))

    def end(self) -> bytes | None:
        """Stop the mic stream and return the accumulated 16-bit PCM, or None."""
        if self._stream is None:
            return None
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:  # noqa: BLE001
            pass
        self._stream = None
        buf = bytes(self._buf)
        self._buf = bytearray()
        return buf if buf else None

    def record_until_silence(self, silence_ms: int = 900, max_ms: int = 15000,
                             timeout_ms: int = 20000) -> bytes | None:
        if not self.is_available():
            return None
        sd = self._sd
        bytes_per_ms = self.SAMPLERATE * 2 / 1000  # 16-bit mono
        block_samples = self.BLOCK // 2
        silence_needed = max(1, round(silence_ms * bytes_per_ms / self.BLOCK))
        max_bytes = int(max_ms * bytes_per_ms)
        timeout_bytes = int(timeout_ms * bytes_per_ms)

        audio = bytearray()
        silence_blocks = 0
        heard_speech = False
        try:
            with sd.RawInputStream(
                samplerate=self.SAMPLERATE, blocksize=block_samples,
                dtype="int16", channels=1, device=self._device,
            ) as stream:
                while True:
                    block = bytes(stream.read(block_samples)[0])
                    audio.extend(block)
                    if self.vad.is_speech(block):
                        heard_speech = True
                        silence_blocks = 0
                    elif heard_speech:
                        silence_blocks += 1
                        if silence_blocks >= silence_needed:
                            break
                    if len(audio) >= max_bytes:
                        break
                    if len(audio) >= timeout_bytes:
                        break
        except Exception as e:  # noqa: BLE001
            self._error = f"capture error: {e}"
            return bytes(audio) if audio else None

        if not heard_speech:
            return None
        return bytes(audio)
