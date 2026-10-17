# Feature Gap Plan

Companion to `AGENTS.md` (house rules), `Build-Status.md` (what shipped) and
`texx-build.md` (full architecture). Every gap below was verified against the
source on 2026-10-16, not against prose docs.

Status vocabulary:

- **PRESENT** — implemented and wired end-to-end
- **PARTIAL** — the machinery exists but the advertised behaviour does not
- **MISSING** — no implementation anywhere in the tree

House rules that constrain every item here (see `AGENTS.md`): add the matcher
in `intents/rules.py`, register it in the `RuleMatcher.match` tuple **at the
right priority**, add the `@register(...)` handler in `core/executor.py`, test
in `tests/test_<name>.py`, then update **`HELP.md`** (rendered verbatim, never
validated automatically), `core/slash.py` if warranted, and `Build-Status.md`.
Optional native deps stay lazily imported; network providers stay
mock-tested and offloaded with `asyncio.to_thread`; LLM calls are synchronous
and currently block the event loop — do not add more of them to the Helper tick
or the chat handler without threading them.

---

## Verified status

| Feature | Status | Evidence |
|---|---|---|
| Push-to-Talk | **PARTIAL** | `voice/ptt.py` + `main.py::_ptt_loop`. Hold-**Space**, not Ctrl+Space, and window-scoped (terminal key events — there is no global hotkey path on Linux). Release inferred from auto-repeat gap, 15 s cap, Esc to exit. |
| Self-Echo Guard | **MISSING** | No echo/reference filtering in `voice/stt.py` or `voice/ptt.py`; `speak()` blocks the recorder only incidentally. |
| Instant Acknowledgment | **MISSING** | No ack path; `main.py::_stop_and_process` shows `■ transcribing…` and waits for the full response. |
| Self-Describing Skills | **MISSING** | No discovery. Registry is the static `@register` dict (`core/executor.py:20`) plus a hardcoded matcher tuple (`intents/matcher.py:80`). A new capability touches 3 files in a fixed order. |
| Recallable Memory | **PARTIAL** | Unlimited SQLite + FTS5 + 3 layers + on-demand `search()` (`services/memory.py:153`). Missing the other half: nothing assembles relevant memories into the LLM prompt — `conversation.chat` passes only `ctx._chat_history` (`core/executor.py:115`). |
| Memory Panel | **PARTIAL** | `/memories` prints `[category] content (#id)`, first 15 rows only (`core/executor.py:459`). No timestamp, no layer shown, no TUI panel, no mouse delete. Natural-language `forget #N` is the only delete path. |
| Undo | **MISSING** | Zero occurrences of undo/backup/restore in the tree. |
| Real Confirmation | **PARTIAL (dead plumbing)** | `Command.requires_confirmation` (`core/commands.py:10`) is set once (`intents/rules.py:517`) and `AssistantState.CONFIRMING` exists (`core/state.py:19`) — **nothing reads either**. No power/wifi intents exist to gate. |
| Audio Device Picker | **PARTIAL** | `SounddeviceRecorder.list_input_devices()` exists (`voice/recorder.py:72`) but no slash command exposes it; `mic_device` is read once at startup, never re-read; no output/speaker list; nothing probes a device to prove it works. |
| Session Continuity | **PARTIAL** | Raw turns persist (`SessionLogService` + `session_fts`), and discussion memory survives restarts. But the actual LLM conversation `ctx._chat_history` is in-memory, capped at 12 messages, and never rehydrated from the session log — restart or device change does lose the conversation. |
| Media on the TUI | **MISSING** | No player, no YouTube/local-file handling, no mute-by-default. |
| Real-time Voice | **PARTIAL** | Piper TTS + Vosk STT work. Turn-based stop-and-wait: no streaming, no barge-in, no per-language model management. "Any language" only insofar as you supply the models. |
| Live Theming | **MISSING** | No theme/hue/accent code; `ui/app.py:46` hardcodes `border_style="blue"`. |
| Reactive TUI | **MISSING** | No waveform, no live render, no amplitude data plumbed to the UI. |
| Voice Picker | **PARTIAL** | `/piper set PATH` only — no list, no bundled voices, no names. A path change does swap `VoiceSession.ctrl.tts` live (`main.py:227`), so live switching is latent but undiscoverable. |
| System Control | **PARTIAL** | Launch/close apps: **PRESENT**, allowlisted (`services/system.py`, `core/permissions.py`). Volume/brightness/battery: **read-only** (`services/systeminfo.py`, pactl + sysfs). Wifi, power, shortcuts, keyboard volume/brightness **setters**: MISSING. |
| Autonomous Tasks | **MISSING** | `services/tasks.py` is a flat todo list; `goal.*` are interval reminders. No planning, decomposition, or multi-step agent loop. |
| Visual Awareness | **MISSING** | Zero occurrences of screenshot/webcam/camera/vision. |
| Persistent Memory | **PRESENT** | Strongest area — 3 layers, FTS5 ranking, compaction, `OWNER.md` curation. |
| Hybrid Input | **PRESENT** | Typed prompt + voice mode share one `route → execute` pipeline (`main.py::VoiceSession._on_utterance`). |
| Morning Briefing | **PARTIAL** | `assistant.brief` / `/brief` gives date, time, tz, mode, cached weather, today's events, tasks, upcoming, counts. Missing: first-boot trigger, greeting, **yesterday recap** (the data already exists via `summarize_yesterday_discussion`), live news. |
| Proactive 2.0 | **PARTIAL** | `core/helper.py` fires due events/goals with mode gating and time awareness. Context beyond reminders/tasks is absent; check-ins are not personalized. |
| Session Memory (recap next morning) | **PARTIAL** | `summarize_yesterday_discussion` folds yesterday into a `daily` memory and deletes the source rows (`services/memory.py:90`). It is date-windowed, so it cannot repeat — but nothing ever *reads* it back into the briefing. The "consumed after use" step is effectively unused. |
| Background Monitoring | **MISSING** | `web.search` exists with a 1 h cache, but no persisted topic watch, no daily poll, no alert. |
| Hardware Monitoring | **MISSING** | No CPU/RAM/GPU/temp collection (no psutil/sensors/`/proc/stat`); battery, volume and brightness only. |
| Weather Report | **PARTIAL** | wttr.in current + today forecast (`services/weather.py`). Location is persisted via `location.set`/`/location` — but it is **not** read back out of memory, so it is not "personalized from memory". |
| Multi-Mode Web Search | **MISSING** | Single DuckDuckGo-lite mode (`services/search.py:35`). Wikipedia is a *separate* intent, not a fallback. No news/research/price/compare modes. |
| Smart Reminders (OS-native) | **MISSING** | In-app 60 s poll only. No `notify-send`, no systemd timer/unit generation. |
| File Processor | **PARTIAL** | `file.find` matches **filenames** under home roots (`services/files.py:20`); `article.read` fetches a **URL** from earlier search results. No local file content read, no summarize, no question answering. |
| Auto-Start on Boot | **MISSING** | No `.desktop` generation, no systemd unit, no autostart registration. |
| Assistant Customization | **PARTIAL** | Assistant name: live (`/name`, `assistant.rename`). Voice: `/piper set`, live. **User's name**: MISSING. **Colour**: MISSING (see Live Theming). |

Net: 3 present, 17 partial, 11 missing.

---

## Phase A — Revive dead plumbing and close cheap gaps

Small, low-risk, mostly finishing work someone already started.

1. **Real Confirmation.** Give `requires_confirmation` a consumer in
   `Executor.execute()`: when set, emit a `CONFIRMING` state and return a
   prompt; accept the literal confirmation on the next turn via a pending-
   command slot on the ctx. Then add the irreversible intents it was meant for
   — `system.shutdown`, `system.restart`, `network.wifi` — behind a **power**
   allowlist in `core/permissions.py` (argv lists only, never `shell=True`).
   Wire `/shutdown`, `/restart`, `/wifi`. Tests: confirm-issued/confirm-cancelled
   in `tests/test_allowlist.py`.
2. **Memory Panel.** Extend `memory.list` to include `created_at`, `layer` and
   `source`, raise the 15-row cap behind an explicit limit, and make
   `memory.forget` accept a title substring as well as `#id` so deletion does
   not require copying an id out of a list. No TUI panel yet — that is Phase F.
3. **Voice Picker.** Add `/voices` listing `*.onnx` under the Piper voice
   directory, plus `/piper set NAME` resolution by filename. Live switching
   already works via `VoiceSession.set_piper`.
4. **Assistant Customization (partial).** Add an `owner_name` setting, an
   `assistant.set_owner_name` intent and `/name me <n>`; keep the "takes effect
   immediately" property by reading from `ctx.settings` at render time.

## Phase B — Voice hardening

All three items are the same subsystem and should land together.

1. **Self-Echo Guard.** Record the PCM the TTS plays (`voice/tts.py::speak`
   already renders to a temp wav) and, in `VoiceSession`, drop the first
   `len(played_samples)/sample_rate` seconds of any capture that overlaps a
   playback window — cross-correlate against the played buffer rather than
   blindly trimming, so a user who talks over the assistant is not muted.
   No new dependency; reuses `SounddeviceRecorder`'s stream.
2. **Instant Acknowledgment.** On release, speak a short context-aware filler
   (`"On it"`, `"Looking that up"`) derived from the routed intent, then speak
   the real answer when `execute()` resolves. Must respect `mode` gating and the
   existing "status output is always silent" rule.
3. **Real-time Voice.** Replace stop-and-wait with a streaming STT pass
   (Vosk partial results are already available on the same stream) and barge-in:
   cancel the in-flight TTS when the VAD sees speech. This is the largest item
   in the phase; sequence it last and behind a `/voice realtime on|off` flag.

## Phase C — Audio Device Picker

`list_input_devices()` is already written and unused. Add `/mic` and
`/speaker` slash commands listing devices through the same call, add a
`SounddeviceRecorder.rebind(device)` plus a matching speaker path, **measure**
each entry (open the stream, read one buffer) and mark failures rather than
listing dead devices, and have the Helper re-read `mic_device` so a change
applies without a restart. Watch the PTT loop: stdin is in cbreak mode and
must not be disturbed by device changes.

## Phase D — Recallable memory, properly

1. **Prompt assembly.** Add `MemoryService.recall_for_prompt(query, budget)`
   that ranks by the existing `_score` and returns as many rows as fit a
   character budget; have `conversation.chat` prepend them to the history sent
   to `llm.respond`. This completes the "prompt carries what fits, the rest is
   looked up on demand" half of the feature and reuses existing scoring.
2. **Weather personalization.** Fall back to `location` memory when no
   location setting exists.
3. **Briefing completion.** Add the greeting, the yesterday recap read from
   the `daily` layer, and a first-boot trigger (a `booted_at` setting compared
   in `main.py`) — deliberately *cached* news only, so the briefing still never
   blocks on the network, which is the invariant the current code comments
   protect.

## Phase E — Session continuity

Persist `_chat_history` to the session log (it is already being written there
raw) and rehydrate it on startup and on voice/device change; lift the 12-message
cap into a token/char budget. Add a `session.reset` path that is explicit rather
than incidental, and keep `SessionLogService.log_turn` inside one
`db.transaction()` with the discussion memory so commits per turn stay at one.

## Phase F — File processor

Add `services/files.py::read_text(path)` with an extension allowlist and size
cap, a `file.read` intent, and a `file.summarize` / `file.ask` handler that
answers over the extracted text via `ctx.llm` (threaded — the LLM is currently
synchronous and will block the loop). Reuse the existing `results` holder and
`open result N` path so `read` composes with search. Watch for the recursive
`web.search` self-match trap: local files and URLs share one result namespace.

## Phase G — Search modes and background monitoring

1. **Multi-mode Web Search.** Add a `mode` slot to `web.search`
   (news/research/price/compare/search) that changes query construction and
   result shaping, and make Wikipedia an actual fallback: on `OnlineError` or an
   empty result set, fall through to `knowledge.wiki` rather than returning an
   error string. Add an RSS-backed news mode for the briefing.
2. **Background Monitoring.** New `services/monitor.py` with a `topics` table
   (topic, query, cadence, last_checked), a daily check in the Helper tick
   *after* events are fetched but guarded so it cannot raise into the reminder
   path, and an alert phrased as a natural check-in. Everything network-facing
   goes through `asyncio.to_thread` plus the existing `services/webcache.py`.

## Phase H — OS integration

1. **Hardware Monitoring.** Read `/proc/stat`, `/proc/meminfo`, sysfs thermal
   zones and, best-effort, `nvidia-smi`; threshold alerts that respect `mode`
   gating and never fire through the alerter for status-style reads.
2. **Smart Reminders.** Generate a systemd user timer/unit per reminder
   (or one timer with a calendar spec) and emit `notify-send`, keeping the
   Helper as the in-app fallback so a missing systemd unit degrades silently.
3. **Auto-Start.** Write a `.desktop` entry into `~/.config/autostart` and a
   `systemd --user` unit from `/autostart on|off`, reusing `resolve_piper_path`
   -style path handling in `main.py`.

## Phase I — Undo

Every mutating action needs a journal row before it acts: `settings.set`
(pre-image), app open/close (already reversible by definition), and the file
mutations once Phase F/F-adjacent write operations exist. Add an `undo_log`
table with an inverse descriptor, an `/undo` slash command and an
`undo.last` intent that pops one entry. Non-invertible actions (delete) must
record a restore-from-copy step, not a no-op — the whole point is that undo is
real.

## Phase J — TUI polish: theming, waveform, media, memory panel

1. **Live Theming.** A theme dict in `ui/app.py` read at render time (so changes
   are immediate), `/theme hue <0-360>` mapping to a Rich style, replacing the
   hardcoded `border_style="blue"`. Note `main.py::VoiceSession` and the banner
   also carry styles that must read from the same source.
2. **Reactive TUI.** Plumb RMS levels from the recorder/VAD and the TTS player
   into a `rich.live.Live` region; render a waveform while listening and
   speaking. Only viable once Phase B exists (the stream is currently opened
   per utterance).
3. **Memory Panel.** A real overlay listing every fact with its learned-at date
   and layer, with keyboard navigation to delete. Requires mouse/key handling
   that does not fight the PTT cbreak stdin loop.
4. **Media on the TUI.** Delegate playback to an external player (`mpv`/`ffplay`)
   started muted, with unmute on request. Keep it an argv list through the
   permission layer, never a shell string.

## Phase K — Autonomous tasks

Multi-step planning on top of the existing todo list: an `agent.plan` intent
that decomposes a goal into `tasks` rows, an executor loop with a step budget
and a hard stop on the first failure, and progress events on the bus. Must be
bounded and observable — this is the one place where autonomy can burn tokens
or touch the filesystem, so every step goes through the same permission check
as a typed command.

## Phase L — Visual awareness

Screenshot and webcam capture as new **optional** services with the same lazy
import discipline, each frame labelled with its source before entering the
chat, plus explicit intents (`screen.describe`, `camera.describe`). Vision
models are a different class of optional dependency than the current GGUF path
— scope this only after the GGUF story is stable, and keep the local-model path
working with no vision extras installed.

---

## Deliberately last: self-describing skills

The advertised "TOOL dict + auto-discovery, adding a skill is one file" model
**conflicts with two contracts this codebase depends on**:

- `RuleMatcher.match`'s tuple order is load-bearing and has caused real routing
  bugs; auto-discovery has to replace that ordering discipline with explicit
  priority metadata.
- The design law is "deterministic code decides and acts". A discovery mechanism
  that loads arbitrary handler modules at startup weakens the guarantee that
  routing is closed and inspectable.

If this is wanted, do it as a **registration helper, not a loader**: keep
`HANDLERS` and the matcher tuple authoritative, but let a new capability declare
`intent`, `priority`, `patterns` and `handler` in one dataclass that a test
asserts is *registered in both* the tuple and the handler dict. That keeps
"one file" ergonomics while making the priority explicit and testable, and it
degrades to today's behaviour if the declaration is missing. Land it after
Phase A, and land the invariant test with it.
