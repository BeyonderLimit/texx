import asyncio
from types import SimpleNamespace

import pytest

from core.commands import Command
from core.events import EventBus
from core.executor import Executor
from core.router import IntentRouter
from core.state import StateManager
from services.settings import Settings
from services.search import OnlineError, WebSearchProvider
from services.webcache import WebCache
from storage.database import Database


SAMPLE_DDG = '''
<tr>
<td>1.&nbsp;</td>
<td><a rel="nofollow" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Frust&amp;rut=abc" class='result-link'><b>Rust</b> programming language</a></td>
</tr>
<tr>
<td class='result-snippet'>A language empowering <b>everyone</b> to build reliable software.</td>
</tr>
<tr>
<td>2.&nbsp;</td>
<td><a rel="nofollow" href="https://www.rust-lang.org" class='result-link'>Rust home</a></td>
</tr>
<tr>
<td class='result-snippet'>Official site.</td>
</tr>
'''


def make(tmp_path):
    db = Database(tmp_path / "s.db")
    settings = Settings(db, EventBus())
    states = StateManager(EventBus())
    system = SimpleNamespace(open_map=lambda: {}, close_map=lambda: {})
    executor = Executor(EventBus(), states, settings, system)
    router = IntentRouter(settings)
    ctx = SimpleNamespace(settings=settings, states=states, system=system,
                          reminders=executor.ctx.reminders, time=executor.ctx.time,
                          memory=executor.ctx.memory, tasks=executor.ctx.tasks,
                          cache=executor.ctx.cache, web=executor.ctx.web,
                          wiki=executor.ctx.wiki, files=executor.ctx.files)
    return ctx, router, executor


async def ask(ctx, router, executor, text):
    command = router.route(text)
    return command, await executor.execute(command)


def test_ddg_parser_extracts_results():
    results = WebSearchProvider._parse(SAMPLE_DDG)
    assert len(results) == 2
    assert results[0]["url"] == "https://example.com/rust"
    assert "Rust" in results[0]["title"]
    assert "reliable software" in results[0]["snippet"]
    assert results[1]["url"] == "https://www.rust-lang.org"


def test_web_search_routes_and_formats(tmp_path):
    ctx, router, executor = make(tmp_path)

    class FakeWeb:
        def search(self, q, max_results=6):
            return [{"title": "Result A", "url": "https://a.example",
                     "snippet": "first result"}]

    executor.ctx.web = FakeWeb()

    command, response = asyncio.run(ask(ctx, router, executor, "search for rust vs go"))
    assert command.intent == "web.search"
    assert "[1] Result A" in response and "https://a.example" in response


def test_web_search_offline_message(tmp_path):
    ctx, router, executor = make(tmp_path)

    class DownWeb:
        def search(self, q, max_results=6):
            raise OnlineError("network unavailable (URLError)")

    executor.ctx.web = DownWeb()
    _, response = asyncio.run(ask(ctx, router, executor, "look up penguins"))
    assert "unavailable" in response


def test_web_cache_used_second_time(tmp_path):
    calls = {"n": 0}

    class CountingWeb:
        def search(self, q, max_results=6):
            calls["n"] += 1
            return [{"title": f"r{calls['n']}", "url": "u", "snippet": ""}]

    db = Database(tmp_path / "c.db")
    settings = Settings(db, EventBus())
    states = StateManager(EventBus())
    executor = Executor(EventBus(), states, settings, SimpleNamespace(
        open_map=lambda: {}, close_map=lambda: {}), web=CountingWeb())
    router = IntentRouter(settings)

    r1 = asyncio.run(executor.execute(router.route("google hello")))
    r2 = asyncio.run(executor.execute(router.route("google hello")))
    assert calls["n"] == 1
    assert "(cached)" in r2


def test_wiki_handler_formats_summary(tmp_path):
    ctx, router, executor = make(tmp_path)

    class FakeWiki:
        def summary(self, topic):
            return {"title": "Alan Turing", "extract":
                    "He was a mathematician. He founded computer science. He died young. More.",
                    "url": "https://en.wikipedia.org/wiki/Alan_Turing"}

    executor.ctx.wiki = FakeWiki()
    command, response = asyncio.run(ask(ctx, router, executor, "who was Alan Turing?"))
    assert command.intent == "knowledge.wiki"
    assert response.startswith("Alan Turing — He was a mathematician.")


def test_knowledge_guard_skips_personal_questions(tmp_path):
    ctx, router, _ = make(tmp_path)
    command = router.route("tell me about your name")
    assert command.intent != "knowledge.wiki"


def test_file_find_and_open_result(tmp_path, monkeypatch):
    docs = tmp_path / "Documents"
    docs.mkdir()
    (docs / "resume_final.pdf").write_text("x")
    (docs / "recipes.txt").write_text("x")
    (docs / ".hidden_secret").write_text("x")
    sub = docs / "projects" / "deep"
    sub.mkdir(parents=True)
    (sub / "resume_draft.md").write_text("x")

    from services.files import FileSearchService
    svc = FileSearchService(home=tmp_path)
    matches = svc.find("resume")
    names = [p.name for p in matches]
    assert "resume_final.pdf" in names and "resume_draft.md" in names
    assert all(p.name != ".hidden_secret" for p in matches)

    ctx, router, executor = make(tmp_path)
    executor.ctx.files = svc
    opened = {}
    import core.executor as ex_mod

    real_popen = None
    command, response = asyncio.run(ask(ctx, router, executor, "find my resume"))
    assert command.intent == "file.find"
    assert "[1]" in response

    import subprocess
    orig = subprocess.Popen
    def fake_popen(*args, **kwargs):
        opened["argv"] = args[0]
        class R:
            pass
        return R()
    subprocess.Popen = fake_popen
    try:
        _, response = asyncio.run(ask(ctx, router, executor, "open result 1"))
        assert "Opening" in response
        assert "resume" in opened["argv"][1]
    finally:
        subprocess.Popen = orig


def test_open_result_without_search(tmp_path):
    ctx, router, executor = make(tmp_path)
    _, response = asyncio.run(ask(ctx, router, executor, "open result 1"))
    assert "find" in response.lower() or "search" in response.lower()


def test_open_result_after_web_search_opens_url(tmp_path):
    ctx, router, executor = make(tmp_path)
    executor.ctx.web = SimpleNamespace(search=lambda q, max_results=6: [
        {"title": "A", "url": "https://example.com/a", "snippet": ""}])
    opened = {}
    import subprocess
    orig = subprocess.Popen
    def fake_popen(*args, **kwargs):
        opened.setdefault("argv", args[0])
        class R:
            pass
        return R()
    subprocess.Popen = fake_popen
    try:
        asyncio.run(ask(ctx, router, executor, "search for test thing"))
        command, response = asyncio.run(ask(ctx, router, executor, "open result 1"))
        assert command.intent == "file.open_result"
        assert "browser" in response.lower()
        assert opened["argv"][1] == "https://example.com/a"
    finally:
        subprocess.Popen = orig


def test_webcache_ttl_expiry(tmp_path):
    cache = WebCache(Database(tmp_path / "cache.db"))
    cache.set("k", {"v": 1}, ttl_seconds=3600)
    assert cache.get("k") == {"v": 1}
    cache.set("expired", [1], ttl_seconds=-1)
    assert cache.get("expired") is None


@pytest.mark.parametrize("text,intent", [
    ("search for rust benchmarks", "web.search"),
    ("google best pizza", "web.search"),
    ("look up quantum computing", "web.search"),
    ("find my resume", "file.find"),
    ("locate taxes.pdf", "file.find"),
    ("search my files for invoice", "file.find"),
    ("open result 2", "file.open_result"),
    ("who was Ada Lovelace?", "knowledge.wiki"),
    ("wikipedia photosynthesis", "knowledge.wiki"),
])
def test_routing_matrix(tmp_path, text, intent):
    ctx, router, _ = make(tmp_path)
    command = router.route(text)
    assert command.intent == intent, text


def test_find_slash_then_open_result_nl_shares_results(tmp_path, monkeypatch):
    # Regression: `/find` (slash) used to store results on a different context
    # than `open result N` (natural language), so opening failed with
    # "Nothing to open yet". The shared results holder fixes that.
    docs = tmp_path / "Documents"
    docs.mkdir()
    (docs / "resume_final.pdf").write_text("x")
    (docs / "recipes.txt").write_text("x")
    from services.files import FileSearchService
    svc = FileSearchService(home=tmp_path)

    ctx, router, executor = make(tmp_path)
    executor.ctx.files = svc
    from core.executor import file_find, file_open_result

    # slash_ctx shares the SAME results holder as executor.ctx
    slash_ctx = SimpleNamespace(files=svc, results=executor.ctx.results)
    asyncio.run(file_find(Command(intent="file.find", slots={"query": "resume"}), slash_ctx))

    opened = {}
    import subprocess
    orig = subprocess.Popen

    def fake_popen(*args, **kwargs):
        opened["argv"] = args[0]
        class R:
            pass
        return R()

    subprocess.Popen = fake_popen
    try:
        response = asyncio.run(file_open_result(
            Command(intent="file.open_result", slots={"n": 1}), executor.ctx))
        assert "Opening" in response
        assert "resume" in opened["argv"][1]
    finally:
        subprocess.Popen = orig
