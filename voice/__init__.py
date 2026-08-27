"""Texx voice subsystem (Phase 6).

Pipeline (per spec §8): PTT -> VAD -> Vosk (STT) -> normalize -> router ->
execute -> Piper (TTS). Every backend is optional and lazy-loaded: Texx runs
fully without vosk/piper/sounddevice. Voice is push-to-talk first, never
always-listening.
"""
