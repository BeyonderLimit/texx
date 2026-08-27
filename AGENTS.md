# AGENTS.md

## What this is

Offline-first deterministic personal assistant for Linux with a Rich TUI. The design law:

> **LLM understands and talks. Deterministic code decides and acts. SQLite remembers.**

No LLM is installed yet (`llm/` is an empty placeholder for Phase 5). Do not introduce AI/network services to solve problems that deterministic code handles today. Full architecture: `texx-build.md`; current status: `Build-Status.md`.

## Commands

```bash
python main.py                          # interactive TUI (runs in repo root)
python -m pytest tests/ -q              # full suite (~122 tests)
python -m pytest tests/test_memory.py   # single file
python -m pytest tests/test_memory.py::test_name  # single test
```

Venv lives at `.venv/`; no linter or formatter is configured. Runtime deps: `rich`, `rapidfuzz`. Dev deps: `pytest`, `pytest-asyncio` (plugin installed but unused).

## Routing — matcher order is load-bearing

The three-stage router (`core/router.py`): Stage 1 = `RuleMatcher` regex matchers; Stage 2 = `FuzzyMatcher`; Stage 3 = fallback `conversation.chat`.

Stage 1's `RuleMatcher.match` tuple in `intents/matcher.py` determines which intent wins when multiple patterns match. **Order matters** — a wrong placement has caused real bugs:
- `match_open_result` ("open result 2") must come **before** `match_open_app` ("open firefox")
- `match_calculator` / `match_close_app` / `match_open_app` must come **after** `match_timer` / `match_open_result` / `match_info_query`

If adding a new matcher, place it where it wins or loses correctly relative to similar-sounding intents. Check the existing tuple order first.

## Adding a feature — the full loop

1. Regex matcher in `intents/rules.py`
2. Register it in the `RuleMatcher.match` tuple at the right priority
3. `@register("intent.name")` handler in `core/executor.py`
4. Tests in `tests/test_<name>.py`
5. **HELP.md** (single source of truth for capabilities; `help` renders it verbatim — update every build)
6. `/slash` command in `core/slash.py` if appropriate
7. Entry in `Build-Status.md`

## Test conventions

- **Sync functions drive async flows** via `asyncio.run(...)` — pytest-asyncio is installed but not used
- Each test gets a fresh temp SQLite DB through the `settings` fixture (`tmp_path`)
- Network-facing providers are tested with **mocked fetches plus recorded fixtures** — keep it that way so the suite stays offline-fast
- When mocking provider objects on `executor.ctx`, assign directly: `executor.ctx.web = FakeWeb()` (not `ctx.web` from `make()` — that's a shadow copy)

## Key gotchas

- **`HELP.md` is rendered verbatim** by the `/help` command — it must stay in sync with actual capabilities
- **Status output is always silent** — `/status` and battery/volume/brightness answers must never go through the alerter
- **Timestamps are naive local ISO strings** — `TimeService.now().replace(tzinfo=None)`, no timezone in DB
- **App open/close requires allowlists** — never `shell=True`, never raw user text into `subprocess`; allowlists merge built-in defaults with `/allow` and `/disallow` entries
- **`conversation.chat` is a stub** when no local model is configured — with a GGUF model set via `/llm set`, it answers via `ctx.llm` (LLMManager); `llama-cpp-python` is NOT a dependency and must never be imported at module top level
- **LLM layer is optional and degrades gracefully** — `llm/local.py` lazy-imports `llama_cpp` and returns an `UnavailableEngine` if missing; never write code that assumes a model is loaded
- **Voice layer is optional and lazy-loaded** — `voice/stt.py` (Vosk), `voice/tts.py` (Piper), `voice/recorder.py` (sounddevice) all import their native libs lazily; `VoiceController.is_available()` gates use. Never import `vosk`/`piper`/`sounddevice` at module top level
- **Network-facing tests stay mocked/offline** — providers (`web.search`, Wikipedia, weather) and the LLM use injected fakes in tests (e.g. `FakeLLM`); the real model is never downloaded in CI

## Environment

Linux-only: `xdg-open` for files/URLs, sysfs/pactl/proc reads in `services/systeminfo.py` (all best-effort). DB at `~/.local/share/texx/texx.db` (override with `HOME` env var).
