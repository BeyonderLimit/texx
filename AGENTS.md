# AGENTS.md

## What this is

Offline-first deterministic personal assistant for Linux with a Rich TUI. The design law:

> **LLM understands and talks. Deterministic code decides and acts. SQLite remembers.**

Routing is deterministic-first. The LLM layer and voice stack are **optional, lazy-loaded layers** that degrade gracefully when their libs/model files are absent. Do not introduce AI/network services to solve problems deterministic code handles today. Full architecture: `texx-build.md`; phase status: `Build-Status.md`.

**`CLAUDE.md` in the repo root is stale** (it claims there is no LLM yet, ~110 tests, and that routing thresholds live in `config.py`). Trust this file and the code instead.

## Commands

```bash
python main.py                          # interactive TUI (run from repo root — imports are repo-relative)
python -m pytest tests/ -q              # full suite (~215 test functions, 23 files, offline)
python -m pytest tests/test_memory.py -q            # single file
python -m pytest tests/test_memory.py::test_name   # single test
```

**Use `python -m pytest` from the repo root.** There is no `conftest.py` and no pytest config, so a bare `pytest` binary cannot import `core`/`services`/`intents` unless texx is pip-installed editable (`pip install -e '.[dev]'`); `python -m` puts cwd on `sys.path` and always works.

No `.venv` exists in a fresh checkout, and the system `python3` (3.11) has `pip`/`ensurepip` but **not** `pytest`/`rich`/`rapidfuzz`, and neither `uv` nor `pipx` is on PATH. Bootstrap with:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
```

`setup.sh` is the scripted path but needs `sudo apt install pipx` + network. Runtime deps: `rich`, `rapidfuzz`. Dev: `pytest`, `pytest-asyncio` (plugin installed but unused). Optional extras: `.[llm]` (`llama-cpp-python`, builds from source), `.[voice]` (`vosk`, `sounddevice`, `piper-tts`), `./voice-config.sh` for guided voice setup. No linter, formatter, typechecker, or CI is configured.

## Request flow

`main.py` owns the loop and wires every service. Two paths out of every prompt:

- **Slash commands** (`core/slash.py`) bypass intent routing and are handled inline; many delegate to executor handlers by importing them and calling with a synthetic `Command`. To add one: a `SLASH_COMMANDS` entry **and** a branch in `handle()`. Slash code runs against a separate `slash_ctx`, but it shares the mutable `results` holder with the executor ctx, so `/find` results are usable by a later natural-language `open result N` (and vice versa).
- **Natural language**: `IntentRouter.route()` → `Executor.execute()`. All shared services hang off `ExecutorContext` (`executor.ctx`). Handlers register via `@register("intent.name")` (46 of them); an intent with no handler logs an error and returns `No handler for intent '...'` — never a silent fallback. `execute()` runs `core/permissions.check()` first and catches handler exceptions, returning `Something went wrong: ...` — so **handlers should raise rather than return error strings**.

### Router (`core/router.py`) — matcher order is load-bearing

Three stages: Stage 1 = `RuleMatcher` regex matchers; Stage 2 = `FuzzyMatcher` (rapidfuzz vs `INTENT_EXAMPLES`, which only covers 4 intents); Stage 3 = fallback `Command("conversation.chat")`. Thresholds are **hardcoded in `core/router.py`** (`>= 0.85` for rules, `FuzzyMatcher(threshold=0.75)`). `config.py` also defines `CONFIDENCE_EXECUTE_THRESHOLD` / `CONFIDENCE_LLM_FALLBACK` with the same values, but nothing imports them — editing `config.py` does not change routing.

Stage 1's `RuleMatcher.match` tuple in `intents/matcher.py` decides which intent wins when multiple patterns match. **Order is load-bearing** — a wrong placement has caused real bugs:
- `match_open_result` ("open result 2") must come **before** `match_open_app` ("open firefox"); `match_read_result` sits immediately after it (both consume result indices)
- `match_calculator` / `match_close_app` / `match_open_app` must come **after** `match_timer` / `match_open_result` / `match_info_query`
- `match_disallow` / `match_allow` sit near the top and route offline — "allow open X" must never fall through to the LLM
- `match_import_calendar` is last (low collision risk)

When adding a matcher, place it where it wins or loses correctly relative to similar-sounding intents. Check the existing tuple first.

## Background machinery — don't break these contracts

- **Helper** (`core/helper.py`) polls every 60s. Scheduled **events outrank goals in the same tick** (goals defer a tick); audio is mode-gated (`normal` = visual+audio, `silent` = visual only, `dnd` = events visual-only, goals paused). It also runs memory maintenance *before* firing events: compact `discussion` (>7d), prune `daily` (>90d), summarize yesterday's discussion into a daily memory, and debounced `OWNER.md` regen — never on the request path. **Maintenance runs before events fire and `run()` swallows exceptions into an `ERROR_OCCURRED` event nobody subscribes to**, so any exception there silently stops every reminder: it must never raise. Note `compact_discussion`/`prune_daily` take `older_than_days` first and `now` second — always pass `now=` as a keyword (`tests/test_helper.py::test_helper_tick_with_memory_fires_events` guards this; getting it wrong broke all of Helper).
- **Timers** (`core/timers.py`) are separate asyncio tasks that fire exactly on time, never waiting on the Helper's tick.
- **Session logging** runs on the request path but is cheap: `main.py` subscribes to `USER_INPUT_RECEIVED` / `COMMAND_COMPLETED` and, in one `db.transaction()`, writes both the raw `session_turns` row (SessionLogService) and the short-term `discussion` memory. `publish_sync` calls subscribers synchronously — do not add slow/blocking work to these handlers.
- **Status output is always silent** — `/status` and battery/volume/brightness answers must never go through the alerter.
- **Blocking-call discipline**: `weather.query`, `web.search`, `knowledge.wiki`, and `article.read` offload HTTP via `asyncio.to_thread(...)`. **LLM inference is threaded the same way** — `conversation.chat` awaits `asyncio.to_thread(llm.respond, ...)` and `asyncio.to_thread(llm.extract_memories, ...)`. Calling either inline freezes the loop for the whole inference (seconds), which stops timers and reminders firing on time and freezes the TUI. `tests/test_llm.py::TestInferenceStaysOffTheEventLoop` fails if anyone drops the `to_thread`. The Helper tick still calls `llm.condense()` inline — see Performance for why that one can't move.

## Performance — measured, so don't "optimize" the wrong thing

Benchmarked on this box (min-of-7 × 2000 iterations). Treat these as the baseline:

| Stage | Cost |
|---|---|
| `RuleMatcher.match`, early hit (`help`, 2nd matcher) | **7.5 µs** |
| `RuleMatcher.match`, full sweep (all 45, no match) | **35.5 µs** |
| `IntentRouter.route`, deterministic hit | **43.7 µs** |
| Full turn: route + execute + DB commit | **~270 µs** |
| `MemoryService.search()` (recall path) | ~1,340 µs |

**The router is not the bottleneck** — it is 0.05 ms against an LLM turn of seconds, four orders of magnitude cheaper. All 60 patterns in `intents/rules.py` are already `re.compile`d at module level, so the usual per-call recompilation trap is avoided. If you are tempted to add a prefix/keyword pre-filter, hoist `text.strip()` into the router, or memoize `route()`, don't: the first two save tens of microseconds while threatening the matcher-order contract above, and the third has a ~0 hit rate on unbounded input and would serve stale results across `/name`.

Three invariants that keep the core fast — protect them:

1. **The `>= 0.85` gate in `core/router.py` is what makes the deterministic path free.** A rule hit returns immediately, so it never invokes `rapidfuzz` and never reaches the LLM. Verified by instrumenting `FuzzyMatcher.match`: deterministic inputs report `fuzzy_ran=0`, fallbacks report `1`. Lowering that threshold makes *every* prompt pay for fuzzy scoring.
2. **`Database` opens a plain `sqlite3.Connection` (`storage/database.py`), so `check_same_thread=True` applies** — DB access from a worker thread raises `ProgrammingError`. This is why `conversation.chat` threads *only* the inference and keeps `ctx.memory.add(...)` on the loop, and why you **cannot** simply wrap `Helper.tick` in `asyncio.to_thread`: the tick interleaves DB reads/writes with the LLM call. Making the tick non-blocking needs either `check_same_thread=False` plus a connection lock, or a split Phase 7 maintenance API so only `llm.condense` crosses a thread boundary. Don't attempt it casually — `Helper.run()` swallows maintenance exceptions into an `ERROR_OCCURRED` event nobody subscribes to, so a `ProgrammingError` inside a worker thread silently stops every reminder. Its current exposure is bounded anyway: `summarize_yesterday_discussion` is date-windowed (first tick after midnight, and it deletes the rows it summarized) and `owner.maybe_regen` needs a `/compact`-driven dirty count, so the inline `condense` runs at most about once a day.
3. **`LLMManager` serializes every engine call on a `threading.Lock`** because llama.cpp model handles are not safe for concurrent use, and the worker thread (chat) and the loop thread (Helper tick) can now both reach the engine. Put any new LLM entry point behind that lock — see `LLMManager.condense`.

`condense()` must exist on `LLMManager`, not just on the engine: `services/memory.py` and `services/owner.py` call `llm.condense(...)` on the manager and swallow the resulting `AttributeError` into a silent fallback to raw concatenation. That shipped broken once — it existed only on test fakes, so every daily summary and `OWNER.md` regeneration silently degraded while the suite stayed green. `tests/test_llm.py::TestCondenseIsOnTheManager` guards it. The general lesson: **a passing test with an injected fake proves nothing about production wiring** — assert against the real manager.

## Adding a feature — the full loop

1. Regex matcher in `intents/rules.py`
2. Register it in the `RuleMatcher.match` tuple at the right priority
3. `@register("intent.name")` handler in `core/executor.py`
4. Tests in `tests/test_<name>.py`
5. **HELP.md** — single source of truth for capabilities; the `assistant.help` handler returns it verbatim via `Path(__file__).parent.parent / "HELP.md"`, so nothing validates it for you. Update it (including its slash tables) every build. Note `/help` is a *different* surface: `quickref_markdown()` builds its table straight from `SLASH_COMMANDS`.
6. `/slash` command in `core/slash.py` if appropriate
7. Entry in `Build-Status.md`

## Test conventions

- **Sync test functions drive async flows** via `asyncio.run(...)` — pytest-asyncio is installed but unused
- Every test builds services on a **fresh temp SQLite DB** (`tmp_path`). There is no `conftest.py`: fixtures are per-module. `settings`/`executor` fixtures + `route_and_execute` live in `tests/test_phase1.py`; most other files define a local `make(tmp_path)` returning `(ctx, router, executor)` plus an `ask(ctx, router, executor, text)` helper — 5 files import them via `from test_reminders import make, ask`
- Network-facing providers (`web.search`, Wikipedia, weather) and the LLM are tested with **mocked fetches / injected fakes plus recorded fixtures** (e.g. `FakeWeb`, `FakeLLM`) — keep it that way so the suite stays offline-fast (there is no CI, so nothing would catch a real network call)
- When mocking provider objects on `executor.ctx`, assign directly: `executor.ctx.web = FakeWeb()` — the `ctx` returned from `make()` is a `SimpleNamespace` **shadow copy**, so mutating it doesn't affect the executor

## Key gotchas

- **Timestamps are naive local ISO strings** — `TimeService.now().replace(tzinfo=None)`, no timezone in DB
- **App open/close requires allowlists** — never `shell=True`, never raw user text into `subprocess`. Allowlists merge built-in defaults with `/allow` entries (`services/system.py`); `/disallow NAME` (or "disallow X") writes a disabled-list that removes even built-in defaults, and a **bare** `/disallow NAME` removes from both open and close lists
- **`conversation.chat` is a stub** when no local model is configured — with a GGUF set via `/llm set` it answers via `ctx.llm` (`LLMManager`), keeping the last 12 messages in `ctx._chat_history` and auto-storing extracted memories
- **Optional layers lazy-import** — `llm/local.py` returns an `UnavailableEngine` when `llama_cpp` or the model path is bad; `voice/stt.py`, `voice/tts.py`, `voice/recorder.py` import vosk/piper/sounddevice inside their classes; `VoiceController.is_available()` gates use. **Never import `llama_cpp`/`vosk`/`piper`/`sounddevice` at module top level** — importing these modules must stay safe with zero optional deps installed (README promises this)
- **Memory has three layers**: `persistent` (explicit `remember that`), `daily` (LLM-summarized), `discussion` (short-term session turns). `MemoryService.search(query, layers=None)` filters by layer only when you pass `layers=[...]`; **the default searches all three** (expired rows always excluded), so `remember`-style recall surfaces discussion turns too
- One `reminders` table serves both events (`category='event'`) and interval goals (`category='goal'`); complete/cancel/delete take `expected_category=` so reminder ops can't touch goals

## Environment & persistence

Linux-only: `xdg-open` for files/URLs, sysfs/pactl/proc reads in `services/systeminfo.py` (all best-effort, degrade to "unknown"). DB at `~/.local/share/texx/texx.db` (override with `HOME`); schema in `storage/schema.sql` applied idempotently on startup by `Database._migrate()`, which also does PRAGMA-checked `ALTER TABLE` migrations (e.g. `memories.layer`, `memories.role`, `reminders.category`, `session_turns` + FTS5). WAL mode (`journal_mode=WAL`, `synchronous=NORMAL`, `cache_size=-16384`). `Database.transaction()` nests and commits once — that is how `log_turn` + discussion memory collapse 4 commits/turn into 1.

## Memory layers (Phase 7)

- `services/memory.py`: `add(layer=...)` default `persistent`; `add_discussion`, `add_daily`; `compact_discussion(older_than_days=7, now=...)`, `prune_daily(older_than_days=90, now=...)`, `summarize_yesterday_discussion(llm, now)`, `persistent()`, `search(layers=...)`
- `services/sessionlog.py`: `SessionLogService` — `log_turn`, `search`, `get_nearby`, `recent` over `session_fts`. Wired to bus events manually in `main.py` (not self-subscribing)
- `services/owner.py`: `OwnerProfile` writes `~/.local/share/texx/OWNER.md`. `build()` renders it; `regen(memories, llm=..., now=..., force=False)` writes it behind a 10-min cooldown + dirty threshold (20); `maybe_regen()` is the debounced wrapper the Helper calls. There is **no `regen_from_memories()`**, and `mark_dirty()` is only called from `/compact` — so the background path effectively regenerates only after `/compact`, which also forces it directly
- Slash: `/sessions [query]`, `/owner`, `/compact`
