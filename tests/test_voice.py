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


class TestStatusVoiceLine:
    def test_voice_line_unavailable(self):
        from core.executor import _voice_status_line
        fake = SimpleNamespace(
            ctrl=SimpleNamespace(is_available=lambda: False,
                                 component_status=lambda: "Vosk: no model path configured"),
            is_active=False)
        assert _voice_status_line(SimpleNamespace(voice=fake)) == \
            "off (Vosk: no model path configured)"

    def test_voice_line_active(self):
        from core.executor import _voice_status_line
        fake = SimpleNamespace(
            ctrl=SimpleNamespace(is_available=lambda: True, component_status=lambda: "x"),
            is_active=True)
        assert _voice_status_line(SimpleNamespace(voice=fake)) == "ON (hold Space to talk)"

    def test_voice_line_ready_off(self):
        from core.executor import _voice_status_line
        fake = SimpleNamespace(
            ctrl=SimpleNamespace(is_available=lambda: True, component_status=lambda: "x"),
            is_active=False)
        assert _voice_status_line(SimpleNamespace(voice=fake)) == "ready (off)"

    def test_full_status_includes_voice(self):
        from services.systeminfo import full_status
        out = full_status(
            SimpleNamespace(state=SimpleNamespace(value="idle")),
            SimpleNamespace(get=lambda k, d=None: "normal"),
            SimpleNamespace(list_pending=lambda *a, **k: []),
            SimpleNamespace(context=lambda: {"time": "10:00", "date": "Mon"}),
            tasks=None, voice="ON (hold Space to talk)")
        assert "Voice:     ON (hold Space to talk)" in out


class TestVoiceSetRoute:
    def test_directory_routes_to_vosk(self, tmp_path):
        from core.slash import _voice_set_route
        d = tmp_path / "vosk-model"
        d.mkdir()
        captured = {}
        voice = SimpleNamespace(set_vosk=lambda p: captured.setdefault("p", p) or "vok",
                                set_piper=lambda p: "should not be called")
        _voice_set_route(voice, str(d))
        assert captured["p"] == str(d)

    def test_onnx_routes_to_piper(self, tmp_path):
        from core.slash import _voice_set_route
        f = tmp_path / "voice.onnx"
        f.write_text("x")
        captured = {}
        voice = SimpleNamespace(set_vosk=lambda p: "should not be called",
                                set_piper=lambda p: captured.setdefault("p", p) or "pok")
        _voice_set_route(voice, str(f))
        assert captured["p"] == str(f)

    def test_zip_gives_extract_guidance(self, tmp_path):
        from core.slash import _voice_set_route
        f = tmp_path / "vosk.zip"
        f.write_text("x")
        voice = SimpleNamespace(set_vosk=lambda p: "x", set_piper=lambda p: "x")
        out = _voice_set_route(voice, str(f))
        assert "Extract" in out

    def test_ambiguous_gives_guidance(self):
        from core.slash import _voice_set_route
        voice = SimpleNamespace(set_vosk=lambda p: "x", set_piper=lambda p: "x")
        out = _voice_set_route(voice, "/some/random/path")
        assert "Vosk" in out


class TestComponentStatus:
    def test_mixed_components(self):
        from voice.ptt import VoiceController

        class C:
            def __init__(self, avail, reason=""):
                self._a = avail
                self._r = reason
            def is_available(self):
                return self._a
            def unavailable_reason(self):
                return self._r
            def device_label(self):
                return "default"

        ctrl = VoiceController()
        ctrl.recorder = C(True)
        ctrl.stt = C(False, "no model path configured")
        ctrl.tts = C(True)
        out = ctrl.component_status()
        assert "Mic: loaded (default)" in out
        assert "Vosk: no model path configured" in out
        assert "Piper: loaded" in out


class TestPTTReleaseLogic:
    def test_no_release_during_initial_repeat_delay(self):
        from main import VoiceSession
        # repeat_interval is still None (first auto-repeat hasn't arrived yet);
        # a 0.5s gap here must NOT be treated as a release.
        assert VoiceSession._should_release(
            None, now=10.5, last_space=10.0, hold_start=10.0, max_hold=15.0) is False

    def test_release_after_repeat_rate_gap(self):
        from main import VoiceSession
        # rate settled at 30ms; a 200ms gap is >> 4*30ms => released.
        assert VoiceSession._should_release(
            0.03, now=10.2, last_space=10.0, hold_start=9.0, max_hold=15.0) is True

    def test_no_release_within_repeat_rate(self):
        from main import VoiceSession
        assert VoiceSession._should_release(
            0.03, now=10.05, last_space=10.0, hold_start=9.0, max_hold=15.0) is False

    def test_max_hold_safety(self):
        from main import VoiceSession
        # stuck key, never gets repeats: max_hold forces release.
        assert VoiceSession._should_release(
            None, now=30.0, last_space=10.0, hold_start=9.0, max_hold=15.0) is True


class TestPiperSpeak:
    def test_speak_uses_synthesize_wav(self, monkeypatch):
        import voice.tts as T
        from voice.tts import PiperTTS

        v = PiperTTS("/fake/model.onnx")  # load fails -> _voice None, _error set

        calls = {}

        class FakeVoice:
            def synthesize_wav(self, text, wav_file, **kw):
                wav_file.setframerate(16000)
                wav_file.setsampwidth(2)
                wav_file.setnchannels(1)
                wav_file.writeframes(b"\x00" * 200)
                calls["text"] = text

        v._voice = FakeVoice()
        v._error = None
        monkeypatch.setattr(T, "_play_wav", lambda p: None)  # no real playback
        v.speak("hello there")
        assert calls.get("text") == "hello there"

    def test_speak_does_not_raise_on_failure(self):
        from voice.tts import PiperTTS

        v = PiperTTS("/fake/model.onnx")

        class BoomVoice:
            def synthesize_wav(self, text, wav_file, **kw):
                raise RuntimeError("boom")

        v._voice = BoomVoice()
        v._error = None
        # must not raise
        v.speak("hi")


class TestControllerSpeakSafe:
    def test_speak_swallows_tts_errors(self):
        from voice.ptt import VoiceController
        from voice.tts import OffTTS

        class BoomTTS:
            def is_available(self):
                return True
            def speak(self, text):
                raise RuntimeError("playback died")

        ctrl = VoiceController(recorder=OffRecorder(), stt=FakeSTT(), tts=BoomTTS())
        # must not raise out of the controller
        ctrl.speak("response")


class TestVoiceSetDirResolution:
    def test_voice_set_dir_with_onnx_routes_piper(self, tmp_path):
        from core.slash import _voice_set_route
        d = tmp_path / "piper"
        d.mkdir()
        (d / "en.onnx").write_text("x")
        captured = {}
        voice = SimpleNamespace(set_vosk=lambda p: "v",
                                set_piper=lambda p: captured.setdefault("p", p) or "pok")
        _voice_set_route(voice, str(d))
        assert captured["p"] == str(d / "en.onnx")

    def test_voice_set_dir_without_onnx_routes_vosk(self, tmp_path):
        from core.slash import _voice_set_route
        d = tmp_path / "vosk"
        d.mkdir()
        (d / "conf.json").write_text("{}")
        captured = {}
        voice = SimpleNamespace(set_vosk=lambda p: captured.setdefault("p", p) or "vok",
                                set_piper=lambda p: "p")
        _voice_set_route(voice, str(d))
        assert captured["p"] == str(d)

    def test_piper_set_dir_passes_through(self, tmp_path):
        from core.slash import handle
        d = tmp_path / "piper"
        d.mkdir()
        (d / "en.onnx").write_text("x")
        captured = {}
        voice = SimpleNamespace(set_piper=lambda p: captured.setdefault("p", p) or "pok")
        ctx = SimpleNamespace(voice=voice)
        asyncio.run(handle("/piper set " + str(d), ctx))
        # real resolution happens inside VoiceSession.set_piper; the slash
        # handler just forwards the path it was given
        assert captured["p"] == str(d)

    def test_resolve_piper_path_finds_onnx(self, tmp_path):
        from main import resolve_piper_path
        d = tmp_path / "piper"
        d.mkdir()
        (d / "en.onnx").write_text("x")
        assert resolve_piper_path(str(d)) == str(d / "en.onnx")
        # a direct file path is returned unchanged
        assert resolve_piper_path(str(d / "en.onnx")) == str(d / "en.onnx")
