import asyncio
import sys
from types import SimpleNamespace

import config
from core import slash
from core.events import Event, EventBus, EventType
from core.executor import Executor
from core.helper import Helper
from core.router import IntentRouter
from core.state import AssistantState, StateManager
from services.notifier import BellNotifier, CompositeNotifier, ConsoleNotifier
from services.settings import Settings
from services.time import TimeService
from storage.database import Database
from ui.app import App
from voice.ptt import VoiceController
from voice.recorder import SounddeviceRecorder
from voice.stt import VoskSTT
from voice.tts import PiperTTS
from voice.vad import EnergyVAD


class VoiceSession:
    """Push-to-talk voice mode: hold Space to record, release to send. Bridges the
    VoiceController to the existing route+execute pipeline and the TUI."""

    MAX_HOLD_S = 15.0  # safety: force-stop a stuck hold

    def __init__(self, controller, app, router, executor, states):
        self.ctrl = controller
        self.app = app
        self.router = router
        self.executor = executor
        self.states = states
        self.task = None
        self._running = False
        self.active = False

    @property
    def is_active(self) -> bool:
        return self.active

    async def _on_utterance(self, text: str) -> str:
        self.app.console.print(f"[dim]You (voice):[/] {text}")
        command = self.router.route(text)
        if command.source != "fallback":
            self.states.set(AssistantState.PROCESSING)
        response = await self.executor.execute(command)
        self.app.show_response(response, markdown=(command.intent == "assistant.help"))
        self.states.set(AssistantState.IDLE)
        return response

    async def _read_keys(self, queue: "asyncio.Queue[str]", fd: int):
        """Async stdin reader (yields to the event loop instead of blocking it).
        Terminal is already in cbreak mode; we only read keys here."""
        import sys

        loop = asyncio.get_event_loop()
        try:
            while self._running:
                ch = await loop.run_in_executor(None, sys.stdin.read, 1)
                if not ch:
                    break
                await queue.put(ch)
        except (OSError, ValueError):
            pass

    async def _stop_and_process(self):
        self.app.console.print("[dim]■ transcribing…[/]")
        text = await self.ctrl.finish_capture()
        if text:
            response = await self._on_utterance(text)
            self.ctrl.speak(response)
        else:
            self.app.console.print("[dim](no speech detected)[/]")

    @staticmethod
    def _should_release(repeat_interval, now, last_space, hold_start, max_hold) -> bool:
        """Infer Space release from the key-repeat gap (terminals have no key-up).

        `repeat_interval` is None until the first auto-repeat arrives (after the
        keyboard's repeat-delay). We must not release during that initial gap, else
        recordings collapse to ~200ms. Once known, a gap >> the rate means released.
        `max_hold` is a safety net for taps / stuck keys.
        """
        if repeat_interval is not None and (now - last_space) > repeat_interval * 4:
            return True
        if (now - hold_start) > max_hold:
            return True
        return False

    async def _ptt_loop(self):
        """Hold-Space push-to-talk (true async, non-blocking the event loop).

        Space key-down starts a capture. Terminals never report key-up, so release
        is inferred from the gap between OS auto-repeat chars. The first repeat only
        arrives after the keyboard repeat-delay, so we must NOT treat that initial
        gap as a release — otherwise recordings get cut to ~200ms. We learn the
        repeat interval from the first repeat, then fire release once the gap grows
        well beyond it.
        """
        import sys
        import termios
        import tty
        import time

        fd = sys.stdin.fileno()
        old_term = termios.tcgetattr(fd)
        tty.setcbreak(fd)
        queue: "asyncio.Queue[str]" = asyncio.Queue()
        reader = asyncio.create_task(self._read_keys(queue, fd))
        self.app.console.print(
            "[bold]Voice mode — hold [cyan]Space[/] to talk, [cyan]Esc[/] to exit.[/]")
        recording = False
        last_space = 0.0
        repeat_interval = None  # unknown until first auto-repeat arrives
        hold_start = 0.0
        try:
            while self._running:
                try:
                    ch = await asyncio.wait_for(queue.get(), timeout=0.05)
                except asyncio.TimeoutError:
                    ch = None
                now = time.time()
                if ch == " ":
                    if not recording:
                        if self.ctrl.begin_capture():
                            recording = True
                            last_space = now
                            repeat_interval = None
                            hold_start = now
                            self.app.console.print(
                                "[red]●[/] recording… release Space to send")
                    else:
                        delta = now - last_space
                        # First repeat carries the keyboard repeat-delay; later ones
                        # carry the (much shorter) repeat rate. Track the short rate.
                        if repeat_interval is None:
                            repeat_interval = min(delta, 0.2)
                        else:
                            repeat_interval = min(repeat_interval, max(delta, 0.01))
                        last_space = now
                elif ch == "\x1b":  # Esc exits PTT
                    self._running = False
                    break
                if recording and self._should_release(
                        repeat_interval, now, last_space, hold_start, self.MAX_HOLD_S):
                    recording = False
                    await self._stop_and_process()
        except Exception as e:  # noqa: BLE001
            self.app.console.print(f"[red]Voice mode error:[/] {e}")
        finally:
            if recording:
                try:
                    await self._stop_and_process()
                except Exception:
                    pass
            reader.cancel()
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_term)
            except (OSError, ValueError):
                pass
            self.active = False
            self.ctrl.enabled = False
            self.app.console.print("[dim]Voice mode off.[/]")

    def start(self) -> str:
        if self.active:
            return "Voice mode already on."
        if not self.ctrl.is_available():
            return (f"Can't start voice ({self.ctrl.unavailable_reason()}). "
                    "Install vosk + a model and sounddevice, then re-run Texx.")
        self._running = True
        self.active = True
        self.task = asyncio.create_task(self._ptt_loop())
        return "Voice mode on — hold Space to talk."

    def stop(self) -> str:
        self._running = False
        self.active = False
        if self.task is not None:
            self.task.cancel()
            self.task = None
        return "Voice mode off."

    def status(self) -> str:
        comps = self.ctrl.component_status()
        if self.active:
            return f"Voice mode ACTIVE — {comps}. Hold Space to talk, Esc to exit."
        if not self.ctrl.is_available():
            return (f"Voice not startable — {comps}. "
                    "Need Mic + Vosk loaded; set them with /voice set <path>.")
        return f"Voice ready — {comps}. Use /voice on (hold Space to talk)."

    def set_vosk(self, path: str) -> str:
        self.executor.ctx.settings.set("vosk_model_path", path)
        from voice.stt import VoskSTT
        self.ctrl.stt = VoskSTT(path)
        if self.ctrl.stt.is_available():
            return f"Vosk model loaded from {path}."
        return (f"Set Vosk model path to {path}, but it can't load yet: "
                f"{self.ctrl.stt.unavailable_reason()}.")

    def set_piper(self, path: str) -> str:
        self.executor.ctx.settings.set("piper_voice_path", path)
        from voice.tts import PiperTTS
        self.ctrl.tts = PiperTTS(path)
        if self.ctrl.tts.is_available():
            return f"Piper voice loaded from {path}."
        return (f"Set Piper voice path to {path}, but it can't load yet: "
                f"{self.ctrl.tts.unavailable_reason()}.")


async def main() -> int:
    db = Database()
    bus = EventBus()
    states = StateManager(bus)
    settings = Settings(db, bus)
    time_service = TimeService(settings)
    router = IntentRouter(settings)

    from core.timers import TimerManager
    timer_manager = TimerManager(
        bus,
        notifier=CompositeNotifier([ConsoleNotifier()]),
        alerter=BellNotifier(),
        mode_fn=lambda: settings.get("mode", "normal"),
    )
    executor = Executor(bus, states, settings, timers=timer_manager)
    app = App(states, lambda: settings.get("assistant_name"), lambda: time_service.context())

    voice = VoiceSession(
        VoiceController(
            recorder=SounddeviceRecorder(EnergyVAD(), device=settings.get("mic_device")),
            stt=VoskSTT(settings.get("vosk_model_path")),
            tts=PiperTTS(settings.get("piper_voice_path")),
        ),
        app, router, executor, states,
    )
    executor.ctx.voice = voice

    slash_ctx = SimpleNamespace(settings=settings, states=states, system=executor.ctx.system,
                                reminders=executor.ctx.reminders, time=time_service,
                                memory=executor.ctx.memory, tasks=executor.ctx.tasks,
                                cache=executor.ctx.cache, web=executor.ctx.web,
                                wiki=executor.ctx.wiki, files=executor.ctx.files,
                                weather=executor.ctx.weather, llm=executor.ctx.llm,
                                voice=voice)

    helper = Helper(
        executor.ctx.reminders,
        bus,
        event_notifier=CompositeNotifier([ConsoleNotifier(console=app.console)]),
        goal_notifier=CompositeNotifier([ConsoleNotifier(console=app.console)]),
        alerter=BellNotifier(console=app.console),
        mode_fn=lambda: settings.get("mode", "normal"),
        interval=60,
    )
    helper_task = asyncio.create_task(helper.run())

    app.banner()

    try:
        while True:
            if voice.is_active:
                # Push-to-talk loop owns the terminal while voice mode is on.
                await voice.task
                voice.task = None
                continue
            try:
                text = (await app.prompt_async()).strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not text:
                continue
            if text.lower() in {"exit", "quit", "goodbye"}:
                break

            if slash.is_slash_command(text):
                response = await slash.handle(text, slash_ctx)
                if response == "__EXIT__":
                    break
                if response == "__CLEAR__":
                    app.clear()
                    continue
                app.show_response(response, markdown=(text.strip().lower() == "/help"))
                states.set(AssistantState.IDLE)
                continue

            bus.publish_sync(Event(EventType.USER_INPUT_RECEIVED, {"text": text}))
            states.set(AssistantState.PROCESSING)
            command = router.route(text)
            if command.source != "fallback":
                bus.publish_sync(Event(EventType.INTENT_MATCHED, {"intent": command.intent}))

            response = await executor.execute(command)
            app.show_response(response, markdown=(command.intent == "assistant.help"))
            states.set(AssistantState.IDLE)
    finally:
        await timer_manager.cancel_all()
        helper_task.cancel()
        await asyncio.gather(helper_task, return_exceptions=True)

    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
