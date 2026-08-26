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
    slash_ctx = SimpleNamespace(settings=settings, states=states, system=executor.ctx.system,
                                reminders=executor.ctx.reminders, time=time_service,
                                memory=executor.ctx.memory, tasks=executor.ctx.tasks,
                                cache=executor.ctx.cache, web=executor.ctx.web,
                                wiki=executor.ctx.wiki, files=executor.ctx.files)
    executor.ctx.memory.purge_expired()
    executor.ctx.tasks.purge_expired()

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
