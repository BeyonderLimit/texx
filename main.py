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

    RELEASE_GAP_S = 0.2  # gap in key-repeat chars => Space was released

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

    async def _ptt_loop(self):
        """Hold-Space push-to-talk. Terminal is switched to cbreak so we see each
        key immediately. Space key-down starts a capture; the stop is detected by
        the gap in OS auto-repeat chars while the key is held."""
        import select
        import sys
        import termios
        import tty
        import time

        fd = sys.stdin.fileno()
        old_term = termios.tcgetattr(fd)
        tty.setcbreak(fd)
        recording = False
        last_space = 0.0
        try:
            self.app.console.print(
                "[bold]Voice mode — hold [cyan]Space[/] to talk, [cyan]Esc[/] to exit.[/]")
            while self._running:
                r, _, _ = select.select([sys.stdin], [], [], 0.05)
                if r:
                    ch = sys.stdin.read(1)
                    if ch == " ":
                        now = time.time()
                        if not recording:
                            if self.ctrl.begin_capture():
                                recording = True
                                last_space = now
                                self.app.console.print("[red]●[/] recording… release Space to send")
                        else:
                            last_space = now  # auto-repeat: still held
                    elif ch in ("\x1b",):  # Esc exits PTT
                        self._running = False
                        break
                    # any other key is ignored in PTT mode
                elif recording and (time.time() - last_space) > self.RELEASE_GAP_S:
                    recording = False
                    self.app.console.print("[dim]■ transcribing…[/]")
                    text = await self.ctrl.finish_capture()
                    if text:
                        response = await self._on_utterance(text)
                        self.ctrl.speak(response)
                    else:
                        self.app.console.print("[dim](no speech detected)[/]")
        except Exception as e:  # noqa: BLE001
            self.app.console.print(f"[red]Voice mode error:[/] {e}")
        finally:
            if recording:
                try:
                    await self.ctrl.finish_capture()
                except Exception:
                    pass
            termios.tcsetattr(fd, termios.TCSADRAIN, old_term)
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
        if not self.ctrl.is_available():
            return (f"Voice is not active ({self.ctrl.unavailable_reason()}). "
                    "Install vosk + a model and sounddevice to enable it.")
        return "Voice ready — use /voice on (hold Space to talk)." if not self.active \
            else "Voice mode active — hold Space to talk, Esc to exit."

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
            recorder=SounddeviceRecorder(EnergyVAD()),
            stt=VoskSTT(settings.get("vosk_model_path")),
            tts=PiperTTS(settings.get("piper_voice_path")),
        ),
        app, router, executor, states,
    )

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
