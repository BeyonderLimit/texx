import asyncio
from types import SimpleNamespace

from voice.ptt import VoiceController
from voice.recorder import OffRecorder, SounddeviceRecorder
from voice.stt import OffSTT, VoskSTT
from voice.tts import OffTTS, PiperTTS
from voice.vad import EnergyVAD


class FakeRecorder:
    def __init__(self, audio=b"fakeaudio"):
        self.audio = audio
        self.calls = 0
    def is_available(self):
        return True
    def record_until_silence(self, *a, **k):
        self.calls += 1
        return self.audio


class FakeSTT:
    def __init__(self, text="open firefox"):
        self.text = text
        self.calls = 0
    def is_available(self):
        return True
    def transcribe(self, audio):
        self.calls += 1
        return self.text


class FakeTTS:
    def __init__(self):
        self.spoken = []
    def is_available(self):
        return True
    def speak(self, text):
        self.spoken.append(text)


def make_ctrl(recorder=None, stt=None, tts=None):
    return VoiceController(
        recorder=recorder if recorder is not None else FakeRecorder(),
        stt=stt if stt is not None else FakeSTT(),
        tts=tts if tts is not None else FakeTTS(),
    )


class TestVAD:
    def test_silence_is_not_speech(self):
        vad = EnergyVAD()
        assert not vad.is_speech(b"\x00" * 4096)
    def test_loud_is_speech(self):
        vad = EnergyVAD()
        # 16-bit samples at max amplitude
        frame = b"".join(int.to_bytes(30000, 2, "little", signed=True) for _ in range(1000))
        assert vad.is_speech(frame)


class TestAvailability:
    def test_unavailable_without_recorder(self):
        ctrl = VoiceController(recorder=OffRecorder(), stt=FakeSTT(), tts=OffTTS())
        assert not ctrl.is_available()
        assert "recorder" in ctrl.unavailable_reason().lower() or "available" in ctrl.unavailable_reason().lower()
    def test_available_with_fakes(self):
        assert make_ctrl().is_available()


class TestCaptureAndConverse:
    def test_capture_utterance(self):
        ctrl = make_ctrl()
        out = asyncio.run(ctrl.capture_utterance())
        assert out == "open firefox"

    def test_converse_calls_handler_and_speaks(self):
        ctrl = make_ctrl()
        handler = lambda text: asyncio.sleep(0, result=f"opening {text}")
        response = asyncio.run(ctrl.converse(handler, speak=True))
        assert response.startswith("opening open firefox")
        assert ctrl.tts.spoken == [response]

    def test_converse_no_speech_returns_none(self):
        ctrl = make_ctrl(recorder=FakeRecorder(audio=None))
        # record_until_silence returns None -> no speech
        response = asyncio.run(ctrl.converse(lambda t: asyncio.sleep(0, result="x"), speak=True))
        assert response is None


class TestOptionalBackends:
    def test_off_stt(self):
        assert not OffSTT().is_available()
        assert OffSTT().transcribe(b"x") == ""
    def test_vosk_without_model(self):
        v = VoskSTT(None)
        assert not v.is_available()
    def test_off_tts(self):
        assert not OffTTS().is_available()
    def test_piper_without_voice(self):
        p = PiperTTS(None)
        assert not p.is_available()


class TestVoiceSlash:
    def test_status_unavailable(self):
        from core.slash import handle
        fake_voice = SimpleNamespace(
            ctrl=SimpleNamespace(is_available=lambda: False,
                                 unavailable_reason=lambda: "vosk not installed"),
            task=None, status=lambda: "Voice is not active (vosk not installed).",
            start=lambda: "on", stop=lambda: "off")
        ctx = SimpleNamespace(voice=fake_voice)
        out = asyncio.run(handle("/voice", ctx))
        assert "not active" in out.lower()
    def test_start_when_available(self):
        from core.slash import handle
        fake_voice = SimpleNamespace(
            ctrl=SimpleNamespace(is_available=lambda: True, unavailable_reason=lambda: "available"),
            task=SimpleNamespace(done=lambda: True),
            status=lambda: "ready", start=lambda: "Voice mode on.", stop=lambda: "off")
        ctx = SimpleNamespace(voice=fake_voice)
        out = asyncio.run(handle("/voice on", ctx))
        assert "on" in out.lower()


class TestModelSlash:
    def test_vosk_set_updates_path(self):
        from core.slash import handle
        captured = {}
        fake_voice = SimpleNamespace(
            ctrl=SimpleNamespace(is_available=lambda: False, unavailable_reason=lambda: "x"),
            set_vosk=lambda p: captured.setdefault("p", p) or "ok")
        ctx = SimpleNamespace(voice=fake_voice)
        out = asyncio.run(handle("/vosk set /models/vosk-en", ctx))
        assert captured["p"] == "/models/vosk-en"
        assert out == "/models/vosk-en"

    def test_piper_set_updates_path(self):
        from core.slash import handle
        captured = {}
        fake_voice = SimpleNamespace(
            ctrl=SimpleNamespace(is_available=lambda: False, unavailable_reason=lambda: "x"),
            set_piper=lambda p: captured.setdefault("p", p) or "ok")
        ctx = SimpleNamespace(voice=fake_voice)
        out = asyncio.run(handle("/piper set /models/voice.onnx", ctx))
        assert captured["p"] == "/models/voice.onnx"
        assert out == "/models/voice.onnx"


class FakePTTRecorder:
    def __init__(self, audio=b"pttaudio"):
        self.audio = audio
        self.began = False
        self.ended = False
    def is_available(self):
        return True
    def begin(self):
        self.began = True
    def end(self):
        self.ended = True
        return self.audio
    def record_until_silence(self, *a, **k):
        return self.audio


class TestHoldToTalk:
    def test_begin_and_finish(self):
        rec = FakePTTRecorder()
        stt = FakeSTT(text="set a timer")
        ctrl = VoiceController(recorder=rec, stt=stt, tts=OffTTS())
        assert ctrl.begin_capture() is True
        assert rec.began is True
        out = asyncio.run(ctrl.finish_capture())
        assert rec.ended is True
        assert out == "set a timer"

    def test_finish_without_begin_returns_none(self):
        rec = FakePTTRecorder(audio=None)
        ctrl = VoiceController(recorder=rec, stt=FakeSTT(), tts=OffTTS())
        out = asyncio.run(ctrl.finish_capture())
        assert out is None

    def test_begin_unavailable(self):
        ctrl = VoiceController(recorder=OffRecorder(), stt=FakeSTT(), tts=OffTTS())
        assert ctrl.begin_capture() is False
