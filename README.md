# Texx

**Offline-first, deterministic personal assistant for Linux.**

> LLM understands and talks. Deterministic code decides and acts. SQLite remembers.

Texx is a command-line assistant with a Rich TUI. Routine tasks (timers,
reminders, weather, files, apps, calendar, web search) are handled by
deterministic, fully offline code — no network, no API keys required. An
*optional* local LLM (GGUF via `llama-cpp-python`) and *optional* voice
(Vosk + Piper + sounddevice) can be layered on, and both degrade gracefully
when their native libraries or model files are absent.

## Requirements

- Python 3.11+
- Linux (uses `xdg-open`, sysfs/pactl/proc reads; best-effort elsewhere)
- A terminal that supports ANSI/Rich

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` lists everything, but the heavy pieces are **optional**:

| Capability        | Packages (optional)                    |
|-------------------|----------------------------------------|
| Core (always on)  | `rich`, `rapidfuzz`                    |
| Local LLM         | `llama-cpp-python` + a GGUF model file |
| Voice (STT/TTS)   | `vosk` + `sounddevice` + `piper-tts`   |

You can run Texx with none of the optional deps installed — it just won't
offer LLM conversation or voice.

## Running

```bash
python main.py
```

The venv lives at `.venv/` and the database at
`~/.local/share/texx/texx.db` (override with the `HOME` env var).

Once inside the TUI, type a command or a natural-language request:

```
what's 15% of 240?
open Firefox
set a timer for 10 minutes
/weather
/voice on        # hold Space to talk, Esc to exit
/help            # full command reference (rendered from HELP.md)
```

Slash commands of interest: `/status`, `/reminders`, `/goals`, `/memories`,
`/todo`, `/web`, `/find`, `/read`, `/ical`, `/weather`, `/location`,
`/llm`, `/voice`, `/vosk`, `/piper`, `/mode`, `/brief`, `/clear`, `/exit`.

### Enabling the optional layers

- **Local LLM:** `/llm set /path/to/model.gguf` then talk normally.
- **Voice:** download a [Vosk](https://alphacephei.com/vosk/models) model
  directory and a [Piper](https://github.com/rhasspy/piper) `.onnx` voice,
  then `/vosk set /path/to/vosk-model` and
  `/piper set /path/to/voice.onnx`. Pick a non-default mic with
  `/voice device`.
- **Default mic:** Texx uses the system default input. To use a Bluetooth
  headset or another input, set the `mic_device` setting (by index or name,
  e.g. via the database or a future `/voice device` selector) — the recorder
  reads `settings.get("mic_device")` at startup.

## Project layout

```
main.py              # TUI entry point, wires services + voice + slash/router
config.py            # paths and confidence thresholds
core/                # router, executor, slash commands, state, timers, events
services/            # search, weather, calendar, files, system, memory, settings...
intents/             # regex rules + matcher (order is load-bearing)
llm/                 # optional local LLM engine/manager (lazy imports)
voice/               # optional STT/TTS/VAD/recorder + push-to-talk controller
ui/                  # Rich TUI app
storage/             # SQLite schema + migrations
tests/               # pytest suite (~180 tests, offline)
```

See `texx-build.md` for the full architecture and `Build-Status.md` for the
phase-by-phase status.

## Importing Texx as a library

All modules use absolute, top-level package imports (`voice`, `services`,
`core`, `llm`, …), so you can import them directly from the repository root
without installing a package.

```python
from voice.recorder import SounddeviceRecorder, OffRecorder
from voice.stt import VoskSTT, OffSTT
from voice.tts import PiperTTS, OffTTS
from voice.vad import EnergyVAD
from voice.ptt import VoiceController
```

Build a voice pipeline and capture one utterance:

```python
ctrl = VoiceController(
    recorder=SounddeviceRecorder(EnergyVAD(), device=None),  # None = default mic
    stt=VoskSTT("/path/to/vosk-model"),
    tts=PiperTTS("/path/to/voice.onnx"),
)
print(ctrl.component_status())   # Mic / Vosk / Piper availability
# text = await ctrl.capture_utterance()   # record-until-silence + transcribe
```

Local LLM (optional, lazy — safe to import even without `llama-cpp-python`):

```python
from llm.manager import LLMManager

llm = LLMManager()                 # UnavailableEngine if libs/model absent
reply = llm.respond("Summarize: the quick brown fox.")
memories = llm.extract_memories("My name is Sam and I like tea.")
```

Routing and execution:

```python
from intents.matcher import RuleMatcher, FuzzyMatcher
from core.router import IntentRouter
from services.settings import Settings
from storage.database import Database
from core.events import EventBus

settings = Settings(Database(), EventBus())   # reads ~/.local/share/texx/texx.db
rule = RuleMatcher(settings).match("open firefox")   # Command | None
fuzzy = FuzzyMatcher().match("open firefox")          # Command | None

router = IntentRouter(settings)             # 3-stage: rules -> fuzzy -> LLM fallback
result = router.route("open firefox")       # returns a Command (with .intent, etc.)
```

System status string (used by `/status`):

```python
from services.systeminfo import full_status
# full_status(states, settings, reminders, time_service, tasks=None, voice=None)
```

Settings / persistence:

```python
from services.settings import Settings
from storage.database import Database
from core.events import EventBus

s = Settings(Database(), EventBus())   # ~/.local/share/texx/texx.db by default
s.set("assistant_name", "Athena")
print(s.get("assistant_name"))
```

> Note: native libraries (`vosk`, `sounddevice`, `piper`, `llama_cpp`) are
> imported lazily inside their classes, so importing the modules above never
> requires those packages to be installed.

## Tests

```bash
source .venv/bin/activate
python -m pytest tests/ -q
```

Sync helpers drive async flows via `asyncio.run(...)`; each test gets a fresh
temp SQLite DB. Network-facing providers are exercised with mocked fetches and
recorded fixtures, so the suite stays offline-fast.

## License

See repository for license terms.
