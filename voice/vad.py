from __future__ import annotations

import struct
from typing import Protocol, runtime_checkable


@runtime_checkable
class VoiceActivityDetector(Protocol):
    def is_speech(self, frame: bytes) -> bool: ...


class EnergyVAD:
    """Dependency-free VAD: flags a 16-bit PCM frame as speech when its RMS
    energy exceeds an adaptive-ish threshold. Good enough for PTT endpointing
    and needs no model download."""

    def __init__(self, threshold: int = 300, frame_bytes: int = 4096):
        self.threshold = threshold
        self.frame_bytes = frame_bytes

    def is_speech(self, frame: bytes) -> bool:
        if len(frame) < 2:
            return False
        n = len(frame) // 2
        try:
            samples = struct.unpack("<" + "h" * n, frame[: n * 2])
        except struct.error:
            return False
        if not samples:
            return False
        rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
        return rms >= self.threshold
