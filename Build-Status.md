# Texx — Build Status

Tracking doc for Texx builds: what phase each build is in, what functions have been added, and what remains.

Architecture reference: `texx-build.md`
Core principle: **LLM understands and talks. Deterministic code decides and acts. SQLite remembers.**

---

## Current status

| Item | State |
|---|---|
| Current phase | **Phase 4 — Knowledge services** (search portion done; weather/calendar/extraction remain) |
| Latest build | Build 14 |
| Tests | 110 passed |
| LLM | Not installed (by design until Phase 5) |
| Voice | Not started (Phase 6) |

---

## Component inventory (completed)

| Module | Provides |
|---|---|
| `core/router.py` + `intents/` | 3-stage routing: regex rules → rapidfuzz → fallback; ~25 deterministic intents |
| `core/executor.py` | Handler registry, permission checks, state transitions, error containment |
| `core/events.py`, `core/state.py` | Typed event bus (sync+async), assistant state machine |
| `core/helper.py` | 60s background loop: events > goals priority, mode-gated audio, RRULE rescheduling |
| `core/timers.py` | Per-timer asyncio tasks, exact firing, DND-aware audio |
| `core/slash.py` | 15 slash commands handled by the TUI without intent routing |
| `services/reminders.py` | CRUD, due queries, category filtering, recurrence math (DAILY/WEEKLY/MINUTELY/HOURLY) |
| `services/memory.py` | FTS5 search, spec §5 scoring, access tracking, expiration purge, categorizer |
| `services/tasks.py` | Priority-sorted tasks with TTL auto-purge |
| `services/time.py` | Timezone-aware clock, date parsing context for all other services |
| `services/systeminfo.py` | Battery/volume/brightness/processes via sysfs/pactl//proc — zero dependencies |
| `services/notifier.py` | Notifier protocol: console panels + bell alerter (Piper plugs in at Phase 6) |
| `services/settings.py`, `storage/` | SQLite persistence, idempotent migrations, FTS5 triggers |
| `ui/app.py` + `main.py` | Rich TUI, async prompt (non-blocking), live clock banner |

---

## Phase 0 — Framework / Environment

**Build 1 — Project skeleton** · Status: COMPLETE

- venv + pinned deps (`rich`, `rapidfuzz`, `pytest`); directory structure per spec
- `config.py`, `storage/schema.sql` (settings/memories/FTS5/reminders) + auto-migrating `Database`
- Core primitives: `Command` dataclass, `EventBus`, `AssistantState`/`StateManager`

Functions added: `Database`, `Command`, `EventBus.publish/publish_sync`, `StateManager.set`

---

## Phase 1 — The Bones (text-only deterministic core)

**Build 2 — Deterministic command core** · Status: COMPLETE

- Regex rule layer: calculator (`what's 15% of 240?`), open/close app, rename assistant
- Stage 2 fuzzy matcher (rapidfuzz); three-stage router with confidence thresholds
- Strict allowlists + alias registry (`fire fox` → firefox), no `shell=True`
- SQLite-backed settings; executor handler registry; Rich console TUI

Acceptance: `open Firefox` ✓ · `what's 15% of 240?` = 36 ✓ · `call yourself Athena` persists ✓

Functions added: `IntentRouter.route`, `RuleMatcher.match`, `FuzzyMatcher.match`,
`Executor.execute`, `SystemService.open_app/close_app`, `Settings.get/set`, `normalize`, `eval_math`

**Build 3 — Help system** · Status: COMPLETE

- `HELP.md` as single source of truth for user-facing capabilities (updated every build)
- `help` / `?` / `what can you do?` intent → renders HELP.md as Rich Markdown panel

**Build 4 — Slash commands in the TUI** · Status: COMPLETE

- `core/slash.py`: `/help` quick reference, `/apps`, `/name [new]`, `/status`, `/clear`, `/exit`
- Handled directly by the TUI, bypassing intent routing; unknown commands list available ones

Functions added: `slash.handle`, `slash.is_slash_command`, `slash.quickref_markdown`, `App.clear`

**Build 5 — Time component (context, calendaring groundwork)** · Status: COMPLETE

All deterministic — rules match; the LLM is never asked for time.

- `services/time.py`: timezone-aware `now()` via persisted timezone setting (`zoneinfo`),
  `time_str/date_str/weekday_of/days_until/next_occurrence/set_timezone/context`
- Intents `time.query`, `date.query`, `date.weekday`, `date.until`, `time.set_timezone`
- `parse_date()` accepts natural + numeric formats; `/time [tz]`; live clock in banner

**Build 6 — Dynamic allowlists (runtime app management)** · Status: COMPLETE

- Allowlists merged: built-in defaults + custom entries persisted as JSON settings
- Denial messages now teach: "Add it with: /allow open featherpad [launch command]"
- `/allow open|close NAME [COMMAND...]`, `/disallow open|close NAME`; `/apps` points at them
- Bug fix: Executor's internal SystemService now receives settings (writes were silently dropped)

---

## Phase 2 — Reminder engine

**Build 7 — Reminders, NL time parsing, scheduler** · Status: COMPLETE

- `intents/dates.py`: durations, clock times, day parts (morning=9am…night=8pm),
  today/tomorrow, weekdays, calendar dates; recurrence phrases → RRULE
- Intents `reminder.create/list/done/delete`; ask-when flow when no time given
- `ReminderService` CRUD; due filtering; RRULE next-occurrence math that skips missed cycles
- Async polling scheduler firing `ReminderDue` events through the event bus;
  overdue reminders fire on startup
- Architecture fix: prompt moved to `asyncio.to_thread` (blocking input starved the loop,
  so reminders never fired while idle)

Acceptance: relative ✓ · absolute ("at 5pm") ✓ · recurring ("every Friday morning" → WEEKLY;BYDAY=FR) ✓

**Build 8 — Helper service: goals, audible alerts, notification modes** · Status: COMPLETE

- `core/helper.py` replaces the scheduler: checks due items every 60s
- **Priority contract: scheduled events outrank helper announcements** — goals defer a tick
  when events fire in the same cycle
- Mode-gated audio: `normal` visual+audio · `silent` visual only · `dnd` events visual-only,
  goals paused; modes persisted; intents `mode.set/query`; `/mode`
- Goals: interval habits with `category='goal'`; `goal drink water every 2 hours`
  → `FREQ=HOURLY;INTERVAL=2`; bare interval tasks auto-classify as goals;
  MINUTELY/HOURLY INTERVAL RRULE math
- Storage migration: idempotent `reminders.category` column for existing DBs
- Removed `core/scheduler.py` (subsumed by Helper)

**Build 9 — Parser fix, timers, appointments, mini-briefing** · Status: COMPLETE

User-reported issues triaged as in-phase vs deferred:

- Parser bug fix: leading when-phrases (`remind me in 1 minute to go to bathroom`)
- Timers (`timer.start`): `start a 1 minute timer` no longer misroutes into open-app
- Appointments (`calendar.appointments`): lists local upcoming events; external sync deferred to Phase 4
- Mini-briefing (`assistant.brief`): `brief` / `good morning` / `/brief` — deterministic day
  summary; weather/external calendar explicitly noted Phase 4
- Fallback reply now points users at `help`

**Build 10 — Async timers + full status dashboard** · Status: COMPLETE

- `core/timers.py` — `TimerManager`: each timer is its own asyncio task; fires exactly on
  time (no waiting on the Helper's 60s tick), never blocks new requests, respects DND/silent
  for audio; timers are cancelled cleanly at shutdown; no longer stored as DB reminders
- `services/systeminfo.py` — best-effort hardware reads, zero new dependencies:
  battery (`/sys/class/power_supply`), volume (`pactl`/`amixer`), brightness
  (`/sys/class/backlight`), running processes (top by RSS from `/proc`)
- Full status (`system.status` intent, `/status`, natural `status`):
  state · mode · time · battery · volume · brightness · processes · next upcoming event/timer ·
  TODO list of uncompleted items
- **Status listings are silent by design** — they never touch the audio path in any mode
- Individual queries: `battery?`, `volume?`, `brightness level?`
- Fixed: "next event" now filters out past-due items

Functions added (B9–B10): `_extract_leading_when`, `match_timer/appointments/brief/status/info_query`,
handlers `timer.start/calendar.appointments/assistant.brief/system.status/info.query`,
`TimerManager.start/cancel/cancel_all`, `full_status/battery/volume/brightness/running_processes/upcoming_event/todo_items`
**Build 11 — Full UX audit of all documented functions** · Status: COMPLETE

Ran every function in HELP.md through a scripted clean-DB session and fixed all inconsistencies found:

- Cross-category bug: `delete goal N` could cancel an event reminder (and vice versa);
  complete/cancel/delete are now category-checked (`mark reminder` → event only, `delete goal` → goal only)
- `list reminders` no longer mixes goals into the list (goals have their own command)
- Timer labels use full words ("2 seconds", not "2 secs"), preserving spoken unit
- Calculator prints whole numbers without ".0"
- Status reports `idle` instead of the transient `executing` state while it runs
- `/time` renders on one line (markdown newline collapse)
- Quick-reference table no longer breaks on `|` characters in `/allow` and `/mode` hints
- HELP.md slash-table `/status` description updated; Phase 2 removed from "Coming soon"

Functions added: category-guarded `ReminderService.complete/cancel(expected_category)`,
`UNIT_WORDS` timer labels, quickref pipe sanitization
---

## Phase 3 — Memory engine

**Build 12 — Deterministic memory: store, recall, forget, FTS5, scoring, expiration**

Status: COMPLETE

Scope note: automatic memory extraction from casual conversation requires the LLM (Phase 5);
this build delivers the full deterministic memory engine.

- [x] `services/memory.py` — `MemoryService`:
  - `add/get/forget/all/count` over the `memories` table
  - `search()`: SQLite FTS5 phrase match with LIKE fallback; expired memories excluded;
    results ranked by the spec §5 score (importance*0.35 + recency*0.15 + frequency*0.20 + explicit*0.30)
  - access tracking (access_count, last_accessed_at) bumped on recall hits
  - `purge_expired()` runs at startup; `classify_memory()` deterministic categorizer
    (PROFILE/PREFERENCE/PEOPLE/PROJECT/FACT with per-category importance baselines)
- [x] Intent disambiguation: **"remember to X" → reminder.create; "remember that X" → memory.store**
- [x] Intents: `memory.store` (explicit source gets +2 importance), `memory.recall`,
  `memory.list`, `memory.forget` (by ID or keyword; ambiguous matches list candidates instead of guessing)
- [x] Schema: idempotent FTS5 sync triggers (insert/delete/update content)
- [x] `/memories` slash command; slash output no longer force-rendered as markdown
  (only `/help`) — fixes collapsed multi-line responses
- [x] 13 new tests (`tests/test_memory.py`)

Functions added: `MemoryService.add/search/forget/purge_expired/_score/classify_memory`,
handlers `memory.store/recall/list/forget`, matchers `match_remember/match_recall/match_memory_list/match_forget`
---

**Build 13 — Tasks/Todos with priority + TTL, notes**

Status: COMPLETE

User request: todo/task items distinct from reminders and appointments, with priority levels
and optional TTL. Also: notes are deterministic (built now); dictation needs the voice
stack (Phase 6).

- [x] New `tasks` table + `services/tasks.py` (`TaskService.add/get/list_open/complete/delete/purge_expired`)
- [x] Priority levels: low / normal / high / urgent; list sorted by priority then age;
      inline parsing ("with high priority", "urgent priority") stripped from the title
- [x] TTL: "task X for 3 days" sets expires_at; expired tasks auto-purged at startup and on list
- [x] Intents `task.add/task.list/task.done/task.delete`; natural triggers: task/todo,
      complete/finish/done with, delete/remove; slash `/todo` + `/tasks`
- [x] Notes: stored via memory engine with `category='NOTE'`; intents `note.take`
      ("note: X", "take a note X") and `note.list` ("list notes")
- [x] Briefing fixes: TODAY section now excludes past-due items; new TASKS section;
      footer counts include open tasks
- [x] Status TODO section now reads real tasks instead of event reminders

Functions added: `TaskService.*`, matchers `match_task_add/list/done/delete`,
`match_note_take/match_notes_list`, handlers `task.add/list/done/delete`, `note.take/list`
---

## Phase 4 — Knowledge services (in progress)

**Build 14 — Online search + local file search**

Status: COMPLETE (search aside of Phase 4; weather/calendar/article-extraction remain)

- [x] `services/webcache.py` — SQLite response cache with per-entry TTL (`cache` table)
- [x] `services/search.py`:
  - `WebSearchProvider` — DuckDuckGo Lite endpoint, no API key; order/quote-agnostic HTML
    parser with uddg redirect unwrapping (validated against live responses);
    `fetch_page_text()` stub implements the spec's ArticleExtractor interface for later newspaper4k swap
  - `WikipediaProvider` — search-resolve + REST summary
  - graceful `OnlineError` → user-facing offline message
- [x] `services/files.py` — `FileSearchService`: fuzzy filename match (rapidfuzz) across
  Documents/Downloads/Desktop/home, depth-limited walk, hidden dirs and junk skipped
- [x] Intents: `web.search` (`search for X`, `google X`, `look up X`),
  `knowledge.wiki` (`who was X`, `tell me about X`, `wikipedia X` — guarded against
  personal questions like "tell me about your name"), `file.find` (`find my X`,
  `locate X`, `search my files for X`), `file.open_result` (`open result N`)
- [x] `open result N` opens files via xdg-open after `find`, or URLs in the browser after `search`
- [x] Web results cached 1h, Wikipedia 24h; "(cached)" noted in replies
- [x] Slash `/web QUERY`, `/find NAME`
- [x] Routing-order fix: `open result N` no longer hijacked by the open-app rule
- [x] 19 new tests (`tests/test_search.py`) — network fully mocked; parser validated against live fixture

Functions added: `WebCache.get/set`, `WebSearchProvider.search/_parse/fetch_page_text`,
`WikipediaProvider.summary`, `FileSearchService.find`, handlers
`web.search/knowledge.wiki/file.find/file.open_result`, matchers
`match_web_search/match_local_find/match_open_result/match_knowledge`

---

## Roadmap

| Phase | Scope | Status |
|---|---|---|
| 0 | Framework / environment | ✅ Complete |
| 1 | Text-only deterministic core | ✅ Complete |
| 2 | Reminder engine (one-time, NL dates, recurrence, helper loop, timers, modes) | ✅ Complete |
| 3 | Memory engine (explicit memory, filtered candidates, FTS5 retrieval, importance scoring, expiration) | ✅ Complete |
| 3.5 | Extensions delivered alongside: tasks with priority + TTL, notes | ✅ Complete |
| 4 | Knowledge: ✅ web search + Wikipedia + caching + local file search · ⬜ weather, external calendar, article extraction | 🔶 In progress |
| 5 | Local LLM (`llama-cpp-python`, structured JSON output, schema validation, automatic memory extraction) | ⬜ |
| 6 | Voice (Piper TTS, Vosk STT, VAD, PTT, dictation) | ⬜ |

---

## How to run

```bash
source .venv/bin/activate
python main.py          # interactive TUI
python -m pytest tests/ -q   # test suite
```

Database lives at `~/.local/share/texx/texx.db`.
