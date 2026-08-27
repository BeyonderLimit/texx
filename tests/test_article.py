import asyncio
from types import SimpleNamespace
from core.commands import Command
from core.events import EventBus
from core.executor import Executor
from core.router import IntentRouter
from core.state import StateManager
from services.settings import Settings
from storage.database import Database
from services.search import OnlineError


def make(tmp_path):
    db = Database(tmp_path / "t.db")
    settings = Settings(db, EventBus())
    states = StateManager(EventBus())
    router = IntentRouter(settings)
    system = SimpleNamespace(open_map=lambda: {}, close_map=lambda: {})
    executor = Executor(EventBus(), states, settings, system,
                        web=SimpleNamespace(
                            search=lambda q, max_results=6: [],
                            fetch_page_text=lambda url, max_chars=4000: "")),
    executor = executor[0]
    return executor.ctx, router, executor


async def ask(ctx, router, executor, text):
    cmd = router.route(text)
    response = await executor.execute(cmd)
    return cmd, response


class TestReadResultRouting:
    def test_read_result_pattern(self, tmp_path):
        ctx, router, executor = make(tmp_path)
        cmd, response = asyncio.run(ask(ctx, router, executor, "read result 3"))
        assert cmd.intent == "article.read"
        assert cmd.slots["n"] == 3

    def test_read_article_pattern(self, tmp_path):
        ctx, router, executor = make(tmp_path)
        cmd, response = asyncio.run(ask(ctx, router, executor, "read article 1"))
        assert cmd.intent == "article.read"
        assert cmd.slots["n"] == 1


class TestReadResultHandler:
    def test_no_search_context(self, tmp_path):
        ctx, router, executor = make(tmp_path)
        _, response = asyncio.run(ask(ctx, router, executor, "read result 1"))
        assert "search" in response.lower()

    def test_out_of_range(self, tmp_path):
        ctx, router, executor = make(tmp_path)
        ctx.last_web_results = ["https://a.com"]
        _, response = asyncio.run(ask(ctx, router, executor, "read result 5"))
        assert "5" in response
        assert "doesn't exist" in response

    def test_fetches_article_text(self, tmp_path):
        ctx, router, executor = make(tmp_path)
        ctx.last_web_results = ["https://example.com/article"]
        fetched = {}
        executor.ctx.web = SimpleNamespace(
            fetch_page_text=lambda url, max_chars=4000: (
                fetched.setdefault("url", url),
                "This is the article body with real content about something."
            )[1])
        _, response = asyncio.run(ask(ctx, router, executor, "read result 1"))
        assert fetched["url"] == "https://example.com/article"
        assert "article body" in response.lower()

    def test_network_error(self, tmp_path):
        ctx, router, executor = make(tmp_path)
        ctx.last_web_results = ["https://offline.com"]
        executor.ctx.web = SimpleNamespace(
            fetch_page_text=lambda url, max_chars=4000: (_ for _ in ()).throw(
                OnlineError("network down")))
        _, response = asyncio.run(ask(ctx, router, executor, "read result 1"))
        assert "network down" in response or "could not fetch" in response.lower()

    def test_empty_text(self, tmp_path):
        ctx, router, executor = make(tmp_path)
        ctx.last_web_results = ["https://blank.com"]
        executor.ctx.web = SimpleNamespace(
            fetch_page_text=lambda url, max_chars=4000: "")
        _, response = asyncio.run(ask(ctx, router, executor, "read result 1"))
        assert "no readable text" in response.lower()
