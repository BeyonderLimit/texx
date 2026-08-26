# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Texx is an offline-first personal assistant for Linux with a Rich TUI. Every input is routed to a deterministic intent; there is deliberately **no LLM yet** (`llm/` and `voice/` are empty placeholders for Phases 5–6). The design law from `texx-build.md`:

> **LLM understands and talks. Deterministic code decides and acts. SQLite remembers.**

Do not introduce AI/network services to solve problems that deterministic code handles today. Current status and build history live in `Build-Status.md` (update it per build); `texx-build.md` is the full architecture spec.

## Commands

```bash
source .venv/bin/activate
python main.py                    # interactive TUI
python -m pytest tests/ -q        # full suite (~110 tests)
python -m pytest tests/test_memory.py -q          # single file
python -m pytest tests/test_memory.py::test_name  # single test
```

No linter/formatter is configured. Runtime deps are just `rich` + `rapidfuzz` (+ pytest/pytest-asyncio for dev).

## Request flow

`main.py` owns the loop. Two paths out of every prompt:

1. **Slash commands** (`core/slash.py`) bypass intent routing entirely and are handled inline. Several delegate back to executor handlers by importing them directly and calling with a synthetic `Command`. To add one: entry in `SLASH_COMMANDS` + a branch in `slash.handle()`.
2. **Natural language**: `IntentRouter.route()` → `Executor.execute()` → response string → Rich panel.

### Three-stage router (`core/router.py`)

- **Stage 1** — `RuleMatcher` (`intents/rules.py`): ~40 independent `match_*` functions, each returning a `Command(intent, slots, confidence)` or None, tried **in the order they appear in `RuleMatcher.match`'s tuple**. That order is load-bearing — e.g. `match_open_result` ("open result 2") must precede `match_open_app` ("open firefox"), timer before open-app, etc. Add new matchers into that tuple where they win or lose correctly.
- **Stage 2** — `FuzzyMatcher`: rapidfuzz against `INTENT_EXAMPLES`; slot extraction reuses rule patterns.
- **Stage 3** — fallback `Command("conversation.chat")` (placeholder reply until Phase 5).

Thresholds live in `config.py`: ≥0.85 executes deterministically, <0.75 would go to the future LLM.

### Executor (`core/executor.py`)

Handlers register themselves with `@register("intent.name")`; an intent with no handler is an error, not a fallback. `Executor.execute()` runs `core/permissions.check()` first (allowlist enforcement for app open/close), manages state transitions on the bus, and contains exceptions — handlers should raise rather than crash the TUI. All shared services hang off `ExecutorContext` (`executor.ctx`). Route-matched commands publish events (`USER_INPUT_RECEIVED`, `INTENT_MATCHED`, …) via the typed sync `EventBus` (`core/events.py`); state lives in `StateManager`.

## Background machinery

- **Helper** (`core/helper.py`) polls every 60s: fires due reminders/events, then goal nudges. Two contracts baked in: **events outrank goals in the same tick** (goals defer a tick), and audio is mode-gated (`normal` = visual+audio, `silent` = visual, `dnd` = events visual-only with goals paused). Recurring items reschedule via the RRULE-lite math in `services/reminders.py` (`FREQ=MINUTELY/HOURLY/DAILY/WEEKLY;BYDAY=…`, skips missed cycles).
- **Timers** (`core/timers.py`) are separate asyncio tasks that fire exactly on time and never wait on the Helper's tick.
- **Status output is always silent** — never route `/status`, battery/volume/brightness answers through the alerter.

## Persistence

Single SQLite DB at `~/.local/share/texx/texx.db` (`storage/schema.sql`, applied idempotently on startup by `Database._migrate()`, which also does ad-hoc `PRAGMA`-checked `ALTER TABLE` migrations). Timestamps are stored as **naive local ISO strings** (`TimeService.now().replace(tzinfo=None)`); the timezone setting feeds everything through `services/time.py`.

Notable table semantics:
- One `reminders` table serves both events (`category='event'`) and interval goals (`category='goal'`, auto-classified when recurrence is MINUTELY/HOURLY). Complete/cancel/delete take `expected_category=` so reminder ops can't touch goals.
- Notes are rows in `memories` with `category='NOTE'`; memories use FTS5 kept in sync by triggers, ranked by importance/recency/frequency/explicitness (`services/memory.py`).
- App allowlists merge built-in defaults with custom entries stored as JSON settings values (`services/system.py`).
- Web results cached 1h, Wikipedia 24h (`cache` table, `services/webcache.py`).

## Adding a capability

The full loop for a new feature: matcher in `intents/rules.py` → register it in the `RuleMatcher.match` tuple at the right priority → `@register(...)` handler in `core/executor.py` → tests → **HELP.md** (single source of truth for what the assistant can do; `help` renders this file verbatim, so update it every build) → slash command if appropriate → entry in `Build-Status.md`.

## Tests

Tests are plain pytest (the asyncio plugin is installed but unused — there is no config enabling markers). Convention: **sync test functions drive async flows through helpers** like `route_and_execute(ctx, ...)` wrapped in `asyncio.run(...)`. Each test gets a fresh temp SQLite DB via the `settings` fixture (`tmp_path`). Network-facing providers (`web.search`, Wikipedia) are tested with mocked fetches plus recorded fixtures — keep it that way so the suite stays offline-fast.

## Environment assumptions

Linux-only integrations: `xdg-open` for files/URLs, sysfs/pactl//proc reads in `services/systeminfo.py` (all best-effort, degrade to "unknown"). App launch/close goes through strict allowlists of argv lists — never `shell=True`, never raw user text into `subprocess`.
