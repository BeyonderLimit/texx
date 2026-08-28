# Texx — Help & Capabilities

Texx is an offline-first personal assistant. Deterministic commands run instantly without any AI.
Type `help` at any time to see this list.

## What's built so far

| Component | Status |
|---|---|
| Calculator | ✅ Live |
| App launcher / closer (allowlisted) + runtime allowlist management | ✅ Live |
| Assistant identity (rename persona, persisted) | ✅ Live |
| Time & date queries, timezone setting | ✅ Live |
| Reminders — one-time, absolute, recurring (RRULE) | ✅ Live |
| Helper loop — goals with intervals, audible alerts gated by mode | ✅ Live |
| Notification modes — normal / silent / DND | ✅ Live |
| Async timers | ✅ Live |
| Tasks / todos with priority + TTL | ✅ Live |
| Notes (text) | ✅ Live |
| Memory — store / recall / forget, FTS5 search, importance scoring | ✅ Live |
| Status dashboard — battery, volume, brightness, processes, TODO | ✅ Live |
| Web search (DuckDuckGo) + Wikipedia summaries, cached | ✅ Live |
| Local file search + open results | ✅ Live |
| Briefing (`brief`), appointments listing | ✅ Local data only |
| Weather — current conditions + today/tomorrow forecast, location setting | ✅ Live |
| External calendar import (local `.ics` files) | ✅ Live |
| Article extraction (`read result N` / `/read N`) | ✅ Live |
| Local LLM conversation + auto memory extraction | ✅ Live (optional — needs a GGUF model) |
| Voice — push-to-talk input, spoken replies | ✅ Live (optional — needs Vosk model + Piper voice + mic) |

## Commands you can type

### Reminders
| Say | Does |
|---|---|
| `remind me to leave in 10 minutes` | One-time relative reminder |
| `remind me to call Sarah at 5pm` | Reminder today (or tomorrow if 5pm passed) |
| `remind me to pay rent tomorrow at 9am` | Date + time reminder |
| `remind me to take an injection every friday morning` | Recurring reminder |
| `remind me to stretch every day at 8am` | Daily recurring reminder |
| `list reminders` / `/reminders` | Show pending reminders with IDs |
| `mark reminder 3 done` | Complete a reminder |
| `delete reminder 3` / `cancel reminder 3` | Remove a reminder |

Accepted time formats: `in N seconds/minutes/hours/days/weeks`, `at 5pm`, `at 17:30`,
`today/tomorrow at TIME`, weekday names (`friday`, `every monday evening`),
and calendar dates (`december 25`, `2026-12-25`). Day parts: morning = 9am,
afternoon = 1pm, evening = 6pm, night = 8pm.

Reminders fire automatically while Texx is running — a yellow notification panel appears,
including overdue ones from previous sessions. Recurring reminders reschedule themselves.
If you don't say when, Texx asks before saving anything.

### Goals (helper nudges)
Interval-based habits are handled by the helper loop — a background service that checks
due items every minute and can alert audibly.

| Say | Does |
|---|---|
| `goal drink water every 2 hours` | Recurring health/productivity nudge |
| `drink water every 2 hrs` | Same — interval tasks become goals automatically |
| `stand up and stretch every 45 min` | Minute-interval goal |
| `list goals` / `/goals` | Show active goals with IDs |
| `delete goal 3` | Remove a goal |

Goals fire only when no scheduled event fires in the same tick, and are paused in DND mode.

### Notification modes
| Say | Does |
|---|---|
| `dnd` / `do not disturb` | No audio; goals paused; event notifications still shown |
| `silent mode` | Everything shows visually, no audio |
| `normal` / `turn off dnd` | Visual + audible alerts |
| `what mode am I in?` / `/mode` | Show current mode |

Priority: **scheduled events always outrank helper announcements** — if an event and a
goal come due in the same cycle, the event notifies immediately and the goal waits for
the next tick.

### Tasks / Todos
Different from reminders: no scheduled time, but they carry a **priority** and optional **TTL**.
They appear in `/status`, `brief`, and `/todo`, sorted by priority.

| Say | Does |
|---|---|
| `task buy milk` | Adds a normal-priority task |
| `task pay rent with high priority` | Priorities: low, normal, high, urgent |
| `todo call accountant urgent priority for 3 days` | Task with a TTL — auto-deletes after it lapses |
| `list tasks` / `todos` / `/todo` / `/tasks` | Show open tasks sorted by priority |
| `complete task 2` / `done with task 2` | Mark a task done |
| `delete task 2` | Remove a task |

### Notes
Deterministic text notes, stored locally and searchable by ID.

| Say | Does |
|---|---|
| `note: wifi password is hunter2` | Saves a note |
| `take a note return library books` | Same thing |
| `list notes` / `notes?` | Shows your notes |

Dictation (spoken notes) needs the voice stack — Phase 6.

### Memory
Texx keeps long-term memories in its local database, searchable and forgettable.

| Say | Does |
|---|---|
| `remember that I'm working on Texx` | Stores a memory (categorized + scored) |
| `remember my name is Sam` | Profile facts get top importance |
| `what do you remember about Texx?` / `recall Texx` | Search your memories |
| `list memories` / `/memories` | Show everything stored |
| `forget about Texx` | Deletes matching memories (asks if ambiguous) |
| `forget #3` | Deletes by ID |

Notes:
- **"remember to X" creates a reminder; "remember that X" stores a memory** — Texx tells them apart.
- Memories are auto-categorized (PROFILE, PREFERENCE, PEOPLE, PROJECT, FACT) with importance scores;
  explicit "remember that" statements score higher than casual mentions.
- Automatic memory extraction from casual conversation arrives with the LLM in Phase 5.

### Web & knowledge search
| Say | Does |
|---|---|
| `search for rust benchmarks` / `google X` / `look up X` | Web search via DuckDuckGo (no API key), cached 1 hour |
| `open result 2` | Opens that result — file in your file manager, web result in your browser |
| `read result 2` / `read article 1` / `/read N` | Fetches and displays article text from a search result |
| `who was Alan Turing?` / `tell me about photosynthesis` / `wikipedia X` | Wikipedia summary (cached 24h) |

Works offline gracefully: if there's no network you get a clear message, and cached
results still answer. `/web QUERY`, `/find NAME`, and `/read N` are slash shortcuts.

### Conversation (local LLM)

Texx can hold a normal chat using a small local GGUF model via `llama-cpp-python`.
The LLM is optional — every command above works without it, and the model only
loads when you configure one.

| Say | Does |
|---|---|
| `tell me a joke` / `explain photosynthesis simply` | Free-form chat answered by the local model |
| `/llm` | Show whether a model is loaded |
| `/llm set /path/to/model.gguf` | Point Texx at a local model (loaded on set) |
| `/llm off` | Disable the LLM |

When a conversation is active, Texx silently extracts durable facts (preferences,
people, projects) and stores them to memory — visible with `memories`.

### Voice (push-to-talk)

Texx can listen and reply out loud. Voice is **opt-in and push-to-talk**, never
always-listening. It needs three local assets (all optional — Texx runs without them):

- `vosk` + a Vosk model directory (speech-to-text)
- `sounddevice` + a microphone (capture)
- `piper-tts` + a Piper `.onnx` voice (speech synthesis)

| Say | Does |
|---|---|
| `/voice` | Voice status (which pieces are present) |
| `/voice on` | Enter voice mode: **hold `Space` to talk, release to send, `Esc` to exit** |
| `/voice off` | Leave voice mode (also `Esc` from within it) |
| `/voice set /path` | Point Texx at a model: a **directory** sets Vosk STT, a **`.onnx`** file sets Piper TTS (auto-routes, hot-reloads) |
| `/vosk set /path/to/model` | Point Texx at a downloaded Vosk model (hot-reloads) |
| `/piper set /path/to/voice.onnx` | Point Texx at a Piper voice (hot-reloads) |
| `/tts <text>` | Speak text aloud to test the TTS voice (reports if unavailable or on error) |
| `/log [N]` | Show the last N log entries — errors and query/network faults (default 40) |
| `/sessions [query]` | Review the raw session archive; with a query, search turns and show nearby context |
| `/owner` | Show the curated OWNER.md owner profile |
| `/compact` | Compact short-term memory and refresh OWNER.md |

While voice mode is on, the terminal switches to raw key mode: hold the **Space**
bar and speak — recording stops the moment you release (detected via the gap in
key auto-repeats), then the audio is transcribed, routed, executed, and spoken
back. If only some pieces exist (e.g. STT but no TTS), the reply still prints —
it just isn't spoken. VAD is a dependency-free energy detector used only as a
fallback for the continuous path.

### Weather

Current conditions plus a short forecast, via wttr.in (no API key) and cached 30 min.
Status answers stay silent, as always.

| Say | Does |
|---|---|
| `weather` / `weather?` | Current conditions + today's forecast |
| `weather tomorrow` / `weather tonight` | Forecast for the chosen day |
| `will it rain tomorrow?` / `will it be sunny today?` | Yes/no answer from the forecast data |
| `set location to New Haven` / `change my location to Boston` | Persist your place |
| `/weather [place]` | Slash shortcut (optionally for another city right now) |

Without a saved location Texx uses an approximate IP-based guess and tells you how to
set something precise. Ask `weather` once and your `brief` starts including conditions.

### Local file search
Searches Documents, Downloads, Desktop, and your home folder by fuzzy name match.

| Say | Does |
|---|---|
| `find my resume` / `locate taxes.pdf` | Lists matching files with full paths |
| `search my files for invoice` | Same |
| `open result 1` | Opens the listed match |

Hidden folders, `.git`, `node_modules`, caches etc. are skipped.

### Timers
| Say | Does |
|---|---|
| `start a 5 minute timer` | Countdown that fires exactly on time (runs async — never blocks new requests) |
| `timer for 30 seconds` | Same |
| `10 minute timer` | Same |

Timers are independent background tasks: they notify the instant they expire, regardless
of what else is happening, and respect DND/silent mode for audio.

### Status & system info
| Say | Does |
|---|---|
| `/status` or `status` | Full dashboard: battery, volume, brightness, processes, next event/timer, open TODO items |
| `what's my battery level?` / `battery?` | Battery charge + charging state |
| `volume?` | System volume |
| `brightness level?` | Screen brightness |

Status listings are **always silent** — they never trigger audio, in any mode.

### Appointments & briefing
| Say | Does |
|---|---|
| `list appointments` / `appointments today` | Your upcoming scheduled events |
| `brief` / `good morning` / `/brief` | Day summary: time, mode, today's events, upcoming, reminders + goals counts |

Appointments and briefings run off your local schedule. Import external calendars with `/ical`.

### Calendar import
| Say | Does |
|---|---|
| `import calendar from ~/work.ics` / `load calendar from /path/to/cal.ics` | Parses a local `.ics` file and shows upcoming events (30-day window) |
| `/ical ~/work.ics` | Same — slash shortcut |

Events from imported calendars are displayed for reference but don't modify your local reminders.

### Time & dates
| Say | Does |
|---|---|
| `what time is it?` | Current time in your timezone |
| `what's the date today?` / `what day is it?` | Full current date |
| `what day is december 25?` | Weekday a date falls on |
| `how many days until 2026-12-25?` | Countdown to a date |
| `set timezone to America/New_York` | Change your timezone (persisted) |

Date formats accepted: `december 25`, `Dec 25th`, `2026-12-25`, `12/25`, `12/25/2026`.
The banner always shows the current date/time, and this context feeds calendaring and reminders (Phase 2).

### Calculator
| Say | Result |
|---|---|
| `what's 15% of 240?` | 36 |
| `what's 12 * 8?` | 96 |
| `calculate 100 / 4` | 25 |
| `(2 + 3) * 10` | 50 |

Supports `+ - * / %`, parentheses, and "X% of Y". Runs instantly, no LLM involved.

### Applications
| Say | Does |
|---|---|
| `open Firefox` | Launches an allowlisted app |
| `launch chrome` | Same thing, different phrasing |
| `open my files` | Opens your file manager / home folder |
| `close Firefox` | Closes an allowlisted app |

Understood apps by default: firefox, chrome, chromium, files, calculator, text editor (open), spotify (close).
Aliases work too: "fire fox", "mozilla", "my files", "file manager".

### Managing the allowlist

New apps are blocked by default for safety. Add them yourself:

| Say | Does |
|---|---|
| `/allow open featherpad featherpad` | Allow opening `featherpad` via launch command `featherpad` |
| `/allow open files xdg-open /home/me/docs` | Custom launch command |
| `/allow close myapp myapp-process` | Allow closing by process name |
| `/disallow open featherpad` | Fully remove `featherpad` from the open allowlist (custom entry **and** built-in default) |
| `/disallow close myapp` | Fully remove `myapp` from the close allowlist |
| `/disallow featherpad` | Drop `featherpad` from **both** the open and close allowlists |
| `/apps` | See everything currently allowed (what `open`/`close` will actually act on) |

The command after the name is optional — if omitted, Texx tries launching/closing by the app name itself.
Custom entries persist in the database and merge with the built-in defaults. **`/disallow` truly removes an app**: it deletes your custom entry *and* blocks the built-in default, so the app disappears from `/apps` and `open`/`close` will be denied for it. `/allow` re-enables a previously disabled app. See `APPS.md` for the full reference.

You can also use natural language (routed offline, never to the chat fallback):
`allow open myapp myapp`, `disallow open myapp`, or `disallow myapp` (removes from both).

### Assistant identity
| Say | Does |
|---|---|
| `call yourself Athena` | Renames the assistant persona (persisted) |
| `your name is now Jarvis` | Same thing |
| `what's your name?` | Tells you its current name |

The software stays *Texx*; the conversational persona name is yours to choose and survives restarts.

## System

| Say | Does |
|---|---|
| `help` | Shows this capability list |
| `/help` | Quick-reference of slash commands (rendered as a table) |
| `exit` / `quit` / `/exit` | Shuts Texx down |

## Slash commands (TUI reference)

Slash commands are handled instantly by the TUI — no intent routing involved.

| Command | Description |
|---|---|
| `/help` | Show quick reference of all slash commands |
| `/goals` | List active goals |
| `/memories` | List long-term memories |
| `/todo` / `/tasks` | List open tasks sorted by priority |
| `/mode [normal\|silent\|dnd]` | Get or set notification mode |
| `/weather [place]` | Weather now for your saved location (or a given one) |
| `/location [place]` | Get or set your location |
| `/brief` | Show a summary of your day |
| `/time [timezone]` | Show time/date, or set your timezone |
| `/apps` | List allowlisted apps that can be opened/closed |
| `/allow open\|close NAME [COMMAND...]` | Add an app to an allowlist |
| `/disallow open\|close NAME` | Remove an app from an allowlist |
| `/name [new_name]` | Get or set the assistant persona name |
| `/reminders` | List pending reminders |
| `/status` | Full dashboard: battery, volume, brightness, processes, next event/timer, TODO (always silent) |
| `/clear` | Clear the screen |
| `/exit` | Shut Texx down |

## Coming soon (by phase)

| Phase | Capability |
|---|---|
| 4 remainder | Weather provider, external calendar sync, article extraction (`read result N`) |
| 5 | Local LLM conversation — writing, explanations, ambiguous requests, automatic memory extraction from conversation |
| 6 | Voice — push-to-talk input (Vosk) and spoken replies (Piper), incl. dictation |

Already delivered ahead of schedule: memory store/recall/forget, tasks with priority/TTL,
notes, timers, briefing skeleton, web search + Wikipedia, local file search.

## Notes

- Everything above runs 100% offline and deterministically.
- Unknown input falls through to a placeholder chat reply until Phase 5 adds the local LLM.
- Nothing you say is sent anywhere; the database lives at `~/.local/share/texx/texx.db`.
