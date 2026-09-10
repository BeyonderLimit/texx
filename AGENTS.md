# AGENTS.md

## What this is

Offline-first deterministic personal assistant for Linux with a Rich TUI. The design law:

> **LLM understands and talks. Deterministic code decides and acts. SQLite remembers.**

Routing is deterministic-first. The LLM layer (Phase 5) and voice stack (Phase 6) are **optional, lazy-loaded layers** that degrade gracefully when their libs/model files are absent; Phase 7 (memory layers, session log, OWNER profile) is committed. Do not introduce AI/network services to solve problems deterministic code handles today. Full architecture: `texx-build.md`; phase status: `Build-Status.md`.

## Commands

```bash
python main.py                          # interactive TUI (run from repo root — imports are repo-relative)
python -m pytest tests/ -q              # full suite (~206 tests, offline)
python -m pytest tests/test_memory.py   # single file
python -m pytest tests/test_memory.py::test_name  # single test
```

Venv lives at `.venv/` (gitignored); no linter or formatter is configured. Runtime deps: `rich`, `rapidfuzz`. Dev deps: `pytest`, `pytest-asyncio` (plugin installed but unused).

## Request flow

`main.py` owns the loop. Two paths out of every prompt:

- **Slash commands** (`core/slash.py`) bypass intent routing and are handled inline; several delegate to executor handlers by calling them with a synthetic `Command`. Slash code runs against a separate `slash_ctx`, but it shares the mutable `results` holder with the executor ctx, so `/find` results are usable by a later natural-language `open result N` (and vice versa).
- **Natural language**: `IntentRouter.route()` → `Executor.execute()`. `ExecutorContext` (`executor.ctx`) holds all shared services; handlers register via `@register("intent.name")` and an intent with no handler is an **error**, never a silent fallback.

### Router (`core/router.py`) — matcher order is load-bearing

Three stages: Stage 1 = `RuleMatcher` regex matchers; Stage 2 = `FuzzyMatcher` (rapidfuzz vs `INTENT_EXAMPLES`); Stage 3 = fallback `Command("conversation.chat")`. Confidence thresholds live in `config.py`: `>=0.85` executes deterministically, `<0.75` would go to the LLM.

Stage 1's `RuleMatcher.match` tuple in `intents/matcher.py` decides which intent wins when multiple patterns match. **Order is load-bearing** — a wrong placement has caused real bugs:
- `match_open_result` ("open result 2") must come **before** `match_open_app` ("open firefox"); `match_read_result` sits immediately after it (both consume result indices)
- `match_calculator` / `match_close_app` / `match_open_app` must come **after** `match_timer` / `match_open_result` / `match_info_query`
- `match_allow` / `match_disallow` live near the top and route offline — "allow open X" must never fall through to the LLM
- `match_import_calendar` sits at the end (low collision risk)

If adding a new matcher, place it where it wins or loses correctly relative to similar-sounding intents. Check the existing tuple order first.

## Background machinery — don't break these contracts

- **Helper** (`core/helper.py`) polls every 60s. Scheduled **events outrank goals in the same tick** (goals defer a tick); audio is mode-gated (`normal` = visual+audio, `silent` = visual only, `dnd` = events visual-only, goals paused). It also runs Phase 7 memory maintenance: compact `discussion` (>7d), prune `daily` (>90d), summarize yesterday's discussion into a daily memory, and debounced `OWNER.md` regen — purely on the background loop, never on the request path.
- **Timers** (`core/timers.py`) are separate asyncio tasks that fire exactly on time, never waiting on the Helper's tick.
- **Session logging** is fire-and-forget: `main.py` subscribes to `USER_INPUT_RECEIVED` / `COMMAND_COMPLETED` and writes both the raw `session_turns` row (SessionLogService) and the short-term `discussion` memory — sub-ms INSERTs off the response path.
- **Status output is always silent** — `/status` and battery/volume/brightness answers must never go through the alerter.

## Adding a feature — the full loop

1. Regex matcher in `intents/rules.py`
2. Register it in the `RuleMatcher.match` tuple at the right priority
3. `@register("intent.name")` handler in `core/executor.py`
4. Tests in `tests/test_<name>.py`
5. **HELP.md** (single source of truth for capabilities; the `help` handler renders it verbatim — update every build)
6. `/slash` command in `core/slash.py` if appropriate
7. Entry in `Build-Status.md`

## Test conventions

- **Sync test functions drive async flows** via `asyncio.run(...)` — pytest-asyncio is installed but not used
- Every test builds services on a **fresh temp SQLite DB** (`tmp_path`): most files define a local `make(tmp_path)` helper; the `settings`/`executor` fixtures live in `tests/test_phase1.py`
- Network-facing providers (`web.search`, Wikipedia, weather) and the LLM are tested with **mocked fetches / injected fakes plus recorded fixtures** (e.g. `FakeWeb`, `FakeLLM`) — keep it that way so the suite stays offline-fast
- When mocking provider objects on `executor.ctx`, assign directly: `executor.ctx.web = FakeWeb()` (not `ctx.web` returned from `make()` — that's a shadow copy)

## Key gotchas

- **`HELP.md` is rendered verbatim** by the `help` handler — it must stay in sync with actual capabilities
- **Timestamps are naive local ISO strings** — `TimeService.now().replace(tzinfo=None)`, no timezone in DB
- **App open/close requires allowlists** — never `shell=True`, never raw user text into `subprocess`. Allowlists merge built-in defaults with `/allow` entries; `/disallow NAME` (or natural-language "disallow X") fully removes even built-in defaults by writing a disabled-list, and a **bare** `/disallow NAME` removes from both open and close lists
- **`conversation.chat` is a stub** when no local model is configured — with a GGUF set via `/llm set`, it answers via `ctx.llm` (LLMManager); `llama-cpp-python` is NOT a dependency and must never be imported at module top level
- **LLM layer is optional and degrades gracefully** — `llm/local.py` lazy-imports `llama_cpp` and returns an `UnavailableEngine` when missing (or a bad path); never write code that assumes a model is loaded
- **Voice layer is optional and lazy-loaded** — `voice/stt.py` (Vosk), `voice/tts.py` (Piper), `voice/recorder.py` (sounddevice) all import their native libs lazily; `VoiceController.is_available()` gates use. Never import `vosk`/`piper`/`sounddevice` at module top level
- **Network-facing tests stay mocked/offline** — the real model is never downloaded in CI

## Environment

Linux-only: `xdg-open` for files/URLs, sysfs/pactl/proc reads in `services/systeminfo.py` (all best-effort, degrade to "unknown"). DB at `~/.local/share/texx/texx.db` (override with `HOME` env var); schema in `storage/schema.sql` applied idempotently on startup, plus PRAGMA-checked `ALTER TABLE` migrations (e.g. `memories.layer`, `reminders.category`).