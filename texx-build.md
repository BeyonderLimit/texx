**Texx as a deterministic personal automation engine with an LLM as a bounded conversational service**, not as an "agent" that decides everything.

The key principle:

> **LLM understands and talks. Deterministic code decides and acts. SQLite remembers.**

## 1. Recommended architecture

```text
                    ┌─────────────────────┐
                    │      TEXX UI        │
                    │ Rich TUI / PTT      │
                    │ Text + Voice        │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │   INPUT PIPELINE    │
                    │ VAD → Vosk → Text   │
                    │ or typed text       │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │  COMMAND ROUTER     │
                    │ deterministic first │
                    └───────┬──────┬──────┘
                            │      │
                 known intent│      │conversation/
                            │      │ambiguous
              ┌─────────────▼┐    ▼──────────────┐
              │ INTENT ENGINE │   │ LOCAL LLM     │
              │ rules + NLP   │   │ llama.cpp     │
              └──────┬───────┘   └──────┬────────┘
                     │                  │
         ┌───────────▼──────────────────▼───────────┐
         │              CORE SERVICES                │
         │ actions • reminders • memory • search     │
         │ knowledge • appointments • scheduler      │
         └───────────────┬───────────────┬──────────┘
                         │               │
                  ┌──────▼─────┐   ┌────▼──────┐
                  │   SQLite    │   │ System /  │
                  │ offline DB  │   │ Web APIs  │
                  └─────────────┘   └───────────┘
```

## 2. The most important design decision: command contracts

Don't let the LLM output arbitrary actions.

Every action should become a validated command object:

```python
@dataclass
class Command:
    intent: str
    slots: dict
    confidence: float
    source: str  # "rule", "nlp", "llm"
    requires_confirmation: bool = False
```

For example:

```text
User:
"open Firefox"

↓ deterministic parser

Command(
    intent="system.open_app",
    slots={"app": "firefox"},
    confidence=0.99,
    source="rule"
)
```

Then:

```python
ALLOWED_INTENTS = {
    "system.open_app",
    "system.close_app",
    "system.open_files",
    "reminder.create",
    "reminder.list",
    "calendar.query",
    "search.web",
    "search.wikipedia",
    "weather.query",
    "memory.store",
    "memory.recall",
    "conversation.chat",
}
```

This is much safer and easier to debug than:

```text
user → LLM → shell command
```

Avoid that architecture entirely.

---

# 3. Intent routing

I would use a **three-stage router**.

### Stage 1: Exact/rule matching

Fast and deterministic.

```text
"open Firefox"
"close Firefox"
"open my files"
"what's 15% of 240?"
"remind me..."
"do I have an appointment..."
```

Regex and simple phrase patterns handle a surprising amount.

### Stage 2: Lightweight intent classifier

Use something lighter than spaCy initially if phone resources matter.

My preference:

* `rapidfuzz` for fuzzy matching
* regex
* keyword/phrase patterns
* optionally spaCy's small model later
* embedding similarity only if you need it

For example:

```python
INTENT_EXAMPLES = {
    "system.open_app": [
        "open firefox",
        "launch chrome",
        "start spotify",
    ],
    "reminder.create": [
        "remind me to call John",
        "set a reminder",
        "remind me tomorrow",
    ],
}
```

A fuzzy similarity layer can catch:

```text
"launch fire fox"
"start my browser"
"open that firefox thing"
```

### Stage 3: LLM fallback

Only when deterministic routing says:

```text
intent = UNKNOWN
```

or:

```text
confidence < 0.75
```

The LLM can return **structured intent**, but Texx validates it against the allowed schema.

For example:

```json
{
  "intent": "reminder.create",
  "slots": {
    "task": "call my friend",
    "datetime": "2026-08-25T17:00:00"
  },
  "needs_clarification": false
}
```

If the LLM says:

```json
{"intent": "delete_everything"}
```

the validator simply rejects it.

---

# 4. Memory should be the heart of Texx

I think your "long-term filtered memory" idea is exactly right.

**Do not save every conversation.**

Instead, have a memory pipeline:

```text
Conversation
      ↓
Memory candidate extraction
      ↓
Is it useful?
      ↓
Is it stable?
      ↓
Is it about the user / preferences / relationships / commitments?
      ↓
Deduplicate
      ↓
Store memory
```

## Memory categories

```text
PROFILE
- name
- preferred assistant name
- timezone
- recurring preferences

PREFERENCE
- prefers concise answers
- likes Python
- uses Firefox

PEOPLE
- friend: John
- landlord: ...

FACT
- works on project X
- owns Raspberry Pi

PROJECT
- building Texx
- project architecture decisions

EVENT
- appointment next Tuesday

COMMITMENT
- needs to call friend

REMINDER
- explicit scheduled task
```

A SQLite schema could start as:

```sql
CREATE TABLE memories (
    id INTEGER PRIMARY KEY,
    content TEXT NOT NULL,
    category TEXT NOT NULL,
    importance INTEGER DEFAULT 5,
    confidence REAL DEFAULT 1.0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_accessed_at TEXT,
    access_count INTEGER DEFAULT 0,
    expires_at TEXT,
    source TEXT
);
```

And:

```sql
CREATE TABLE memory_entities (
    memory_id INTEGER,
    entity TEXT,
    entity_type TEXT
);
```

## Memory filtering rule

The assistant should distinguish these:

### Don't store

> "I had eggs for breakfast."

Probably useless.

### Maybe store temporarily

> "I'm going to Boston tomorrow."

Useful until tomorrow, then expires.

### Store long term

> "I'm building an offline-first assistant called Texx."

> "I prefer a male voice."

> "Call yourself Athena."

> "Firefox is my preferred browser."

---

# 5. Memory scoring

Use a simple deterministic score first:

```python
score = (
    importance * 0.35 +
    recency * 0.15 +
    frequency * 0.20 +
    explicit_user_request * 0.30
)
```

Explicit statements such as:

```text
"remember that..."
"always..."
"I prefer..."
"my name is..."
"call yourself..."
```

get a high score.

Later you can add semantic retrieval, but for a phone-sized assistant I would **not start with a vector database**.

Start with:

* SQLite FTS5
* entity extraction
* keyword search
* recency
* importance

That's extremely lightweight.

For example:

```sql
CREATE VIRTUAL TABLE memory_fts
USING fts5(content, content='memories');
```

Then retrieval can rank:

```text
keyword relevance
+ importance
+ recency
+ entity match
+ access frequency
```

This will probably get you very far before embeddings become necessary.

---

# 6. Separate memory from reminders

This is important.

A reminder is **not just a memory**.

Use a dedicated table:

```sql
CREATE TABLE reminders (
    id INTEGER PRIMARY KEY,
    task TEXT NOT NULL,
    due_at TEXT,
    recurrence_rule TEXT,
    status TEXT DEFAULT 'pending',
    created_at TEXT NOT NULL,
    completed_at TEXT,
    notification_sent_at TEXT
);
```

Examples:

### One-time

> "Remind me to leave in 10 minutes."

```text
due_at = now + 10 minutes
recurrence_rule = NULL
```

### Absolute

> "Remind me to call my friend today at 5 PM."

```text
due_at = 2026-08-25 17:00
```

### Recurring

> "Remind me to take an injection every Friday morning."

Something like:

```text
RRULE:FREQ=WEEKLY;BYDAY=FR
```

Store recurrence separately rather than trying to represent it as plain text.

---

# 7. Scheduler architecture

For an offline-first system, I'd avoid making the assistant process itself responsible for everything.

Conceptually:

```text
┌──────────────┐
│ Texx process │
└──────┬───────┘
       │ writes
       ▼
┌──────────────┐
│   SQLite     │
│ reminders    │
└──────┬───────┘
       │ reads
       ▼
┌──────────────┐
│ scheduler    │
│ service      │
└──────┬───────┘
       │
       ├── notification
       ├── TTS
       └── marks delivered
```

For the first version, a simple polling loop is enough:

```python
while True:
    due = db.get_due_reminders()
    for reminder in due:
        notify(reminder)
        mark_sent(reminder)

    time.sleep(5)
```

For mobile later, this should eventually integrate with the OS's native background scheduling/notification system. **Don't depend on a Python process staying alive forever on a phone.**

---

# 8. Voice pipeline

Your proposed stack:

```text
PTT
 ↓
VAD
 ↓
Vosk
 ↓
Text normalization
 ↓
Intent router
 ↓
Action / response
 ↓
Piper TTS
```

I like **PTT** as the initial UX much more than always-listening wake-word detection.

Advantages:

* lower battery use
* fewer false activations
* simpler
* better privacy story

I would make VAD optional during PTT:

```text
Press button
↓
Start recording
↓
VAD detects speech
↓
Silence for ~700–1200 ms
↓
Stop
↓
Vosk
```

Then:

```python
async def handle_voice():
    audio = await recorder.capture_ptt()
    speech = await stt.transcribe(audio)
    result = await router.route(speech)
    await executor.execute(result)
```

---

# 9. LLM's actual role

The LLM should have a narrow set of responsibilities.

## Good LLM jobs

### Conversation

> "I'm feeling stuck on this project."

### Explanation

> "Explain photosynthesis simply."

### Writing

> "Write a thank-you note to my landlord."

### Ambiguous intent interpretation

> "Can you make sure I don't forget that thing Friday?"

Texx can ask:

> "What would you like me to remind you about?"

### Memory summarization

It can turn a long interaction into a candidate:

```json
{
  "candidate": "User is developing Texx, an offline-first personal assistant.",
  "category": "PROJECT",
  "importance": 9
}
```

Then deterministic code decides whether to save it.

## Bad LLM jobs

Don't use it directly for:

* launching applications
* killing processes
* filesystem operations
* reminder scheduling
* database writes
* shell execution
* permissions
* arbitrary web access

The LLM may **request** an action through a schema. The core performs it.

---

# 10. A clean project structure

I would start with something like:

```text
texx/
│
├── main.py
├── config.py
│
├── core/
│   ├── router.py
│   ├── commands.py
│   ├── executor.py
│   ├── events.py
│   └── permissions.py
│
├── intents/
│   ├── rules.py
│   ├── matcher.py
│   ├── parser.py
│   └── fallback.py
│
├── services/
│   ├── memory.py
│   ├── reminders.py
│   ├── scheduler.py
│   ├── calendar.py
│   ├── weather.py
│   ├── search.py
│   ├── wikipedia.py
│   ├── system.py
│   └── writer.py
│
├── voice/
│   ├── vad.py
│   ├── stt.py
│   ├── tts.py
│   └── recorder.py
│
├── llm/
│   ├── engine.py
│   ├── prompts.py
│   ├── schemas.py
│   └── context.py
│
├── storage/
│   ├── database.py
│   ├── schema.sql
│   └── migrations/
│
├── ui/
│   ├── app.py
│   └── screens.py
│
└── tests/
```

This separation will save you pain later.

---

# 11. The request flow I would use

For every input:

```python
async def process(text: str):
    context = context_manager.get()

    # 1. Deterministic handling
    result = intent_router.match(text)

    if result.confidence >= 0.85:
        return await executor.execute(result)

    # 2. Known question services
    result = knowledge_router.match(text)

    if result:
        return await executor.execute(result)

    # 3. LLM fallback
    response = llm.chat(
        message=text,
        memories=memory.retrieve(text, limit=8),
        conversation=context.recent()
    )

    # 4. Extract memory candidates
    candidates = memory_extractor.extract(
        text=text,
        response=response
    )

    # 5. Deterministically filter/save
    memory.process_candidates(candidates)

    return response
```

The important thing is that the LLM does **not sit in the middle of every request**.

For:

> "What's 15% of 240?"

Texx shouldn't wake up a 2–4 GB model.

It should do:

```python
0.15 * 240
```

and respond instantly.

---

# 12. Knowledge/search providers

I'd create a provider interface:

```python
class KnowledgeProvider(Protocol):
    async def search(self, query: str) -> KnowledgeResult:
        ...
```

Then:

```text
WeatherProvider
WikipediaProvider
OfflineKnowledgeProvider
WebSearchProvider
NewsProvider
```

Routing could be:

```text
"who was Alan Turing?"
        ↓
Wikipedia first
        ↓
offline cache if available
        ↓
web only if needed
```

For:

> "What's the weather like in New Haven tomorrow?"

```text
Weather intent
↓
weather provider
↓
network check
↓
wttr.in
↓
cache result
```

Keep web results cached with an expiration time.

---

# 13. Web search: don't let `newspaper4k` be the search engine

I would treat article extraction separately:

```text
Search
  ↓
results
  ↓
choose source
  ↓
fetch HTML
  ↓
article extraction
  ↓
clean text
  ↓
optional LLM summary
```

`newspaper4k` can be the extraction layer, but I'd design an interface so you can replace it later:

```python
class ArticleExtractor:
    def extract(self, url: str) -> Article:
        ...
```

Possible fallback implementations can be added without touching the rest of Texx.

---

# 14. "Open/close things" safely

Never do:

```python
subprocess.run(user_text, shell=True)
```

Instead:

```python
APP_MAP = {
    "firefox": ["firefox"],
    "files": ["xdg-open", str(Path.home())],
}
```

Then:

```python
def open_app(name: str):
    command = APP_MAP.get(normalize(name))

    if not command:
        raise UnknownApplication(name)

    subprocess.Popen(command)
```

For closing:

```python
ALLOWED_PROCESSES = {
    "firefox": "firefox",
}
```

Again, allowlists.

This becomes especially important if the LLM ever participates in interpreting commands.

---

# 15. Rename command

Your example:

> "Call yourself Athena."

This is a great example of persistent configuration.

Store separately from generic memory:

```sql
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

Then:

```text
assistant_name = Athena
```

Texx's identity prompt can dynamically use:

```text
You are {assistant_name}, a private offline-first assistant.
```

I would keep the executable/project name **Texx**, while allowing the conversational persona name to change.

So:

```text
Texx = software/system
Athena = current assistant persona
```

That gives you flexibility.

---

# 16. My recommended MVP order

Don't build everything at once.

### Phase 1 — Text-only deterministic core

Build:

* Rich TUI
* SQLite
* settings
* command router
* calculator
* open app
* close app
* rename assistant

Test:

```text
> open Firefox
> what's 15% of 240?
> call yourself Athena
```

### Phase 2 — Reminder engine

Build:

* one-time reminders
* natural-language date parsing
* recurring reminders
* scheduler
* notification abstraction

Test:

```text
> remind me to leave in 10 minutes
> remind me to call Sarah at 5pm
> remind me every Friday morning
```

### Phase 3 — Memory

Build:

* explicit memory
* filtered automatic memory candidates
* SQLite FTS
* importance scoring
* expiration

Test:

```text
> remember I'm working on project Texx
> what project am I working on?
```

### Phase 4 — Local knowledge + web services

Add:

* Wikipedia
* weather
* offline cache
* web search
* article extraction

### Phase 5 — Local LLM

Only now add `llama-cpp-python`.

Use it for:

* chat
* writing
* explanations
* memory extraction
* ambiguous commands

### Phase 6 — Voice

Finally:

* Piper
* Vosk
* VAD
* PTT

This order makes debugging dramatically easier.

---

# 17. Phone constraints

For "light enough to fit on phone," I would target something like:

```text
Python application/core:     relatively small
SQLite + FTS database:       tiny to moderate
Vosk small model:            device-dependent
Piper voice:                 relatively small
LLM:                         biggest component
Memory DB:                   probably tiny initially
```

The LLM is the component that can destroy your size/RAM budget.

So I would design Texx so that it still works extremely well with:

```text
LLM disabled
```

That means Texx can always:

* understand common commands
* launch apps
* manage reminders
* recall memories
* calculate
* search providers
* answer structured queries

The LLM becomes an enhancement:

```text
TEXX CORE = useful without LLM
TEXX CONVERSATION = enhanced by LLM
```

That is the architecture I'd strongly recommend.

---

## My suggested stack, slightly adjusted

```text
Python 3.11

CORE
- asyncio
- SQLite
- SQLite FTS5
- Pydantic or dataclasses
- Rich

INTENTS
- regex
- rapidfuzz
- lightweight custom intent matcher
- optional spaCy later

VOICE
- Vosk
- Piper
- Silero VAD or another lightweight local VAD
- PTT first

LLM
- llama-cpp-python
- small quantized GGUF model
- structured JSON output

MEMORY
- SQLite
- FTS5
- entity/keyword indexing
- deterministic importance scoring
- optional embeddings later

SERVICES
- wttr.in
- Wikipedia
- search provider abstraction
- article extraction abstraction

SYSTEM
- subprocess with strict allowlists
- no shell=True
```

## The one-sentence architecture

**Texx should be a fast offline command-and-memory engine that can survive without an LLM, with a local LLM plugged in only for natural conversation, writing, explanation, and ambiguous language.**

Yes — **all of that is possible**, and it fits your Texx architecture well. I would organize it into a few bounded subsystems rather than making one giant assistant loop.

## Texx capability map

```text
                         ┌──────────────────┐
                         │       TEXX       │
                         │ Text / Voice UI  │
                         └────────┬─────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │     DETERMINISTIC CORE     │
                    │ Router • State • Security  │
                    └───┬───────┬───────┬───────┘
                        │       │       │
             ┌──────────▼┐ ┌────▼────┐ ┌▼───────────┐
             │ System    │ │ Memory  │ │ Research   │
             │ Control   │ │ Engine  │ │ Engine     │
             └───────────┘ └─────────┘ └────────────┘
                        │       │       │
             ┌──────────▼───────▼───────▼───────────┐
             │ Apps • Files • Terminal • Reminders  │
             └───────────────────────────────────────┘
```

# 1. Text/Voice assistant

Absolutely. Both inputs should converge immediately into the same pipeline:

```text
VOICE
PTT
 ↓
VAD
 ↓
Speech-to-text
 ↓
Normalized text ─────────┐
                         ▼
TEXT ─────────────────→ Request Router
```

Everything after transcription should not care whether the user typed:

> open Firefox

or said it.

That keeps the system much simpler.

---

# 2. Files

Yes, but use a **file service abstraction**, not direct LLM filesystem access.

Supported commands could be:

```text
"show my downloads"
"find my resume"
"open taxes.pdf"
"move this file to Documents"
"rename report.txt to final-report.txt"
"delete old-notes.txt"
```

Internally:

```text
FileRequest
├── action: FIND
├── query: "resume"
└── location: ~/Documents
```

Then:

```text
FileRequest
├── action: DELETE
├── path: /home/user/Documents/old-notes.txt
└── confirmation_required: True
```

### Confirm-before-delete

I strongly recommend a two-step system:

```text
User:
"Delete old notes"

Texx:
"I found 3 matching files:
1. old_notes.txt
2. old_notes_2024.txt
3. old_notes_backup.txt

Which one should I delete?"
```

Then:

```text
User:
"the backup one"

Texx:
"Delete old_notes_backup.txt? This will move it to Trash."
```

Only then:

```text
User:
"yes"
```

Texx executes.

Even better: **default to Trash instead of permanent deletion**.

---

# 3. Apps and system control

Yes.

I would split this into adapters:

```text
services/
├── apps.py
├── files.py
├── system.py
├── terminal.py
└── power.py
```

Commands:

```text
open Firefox
close Spotify
open my files
mute the volume
set volume to 30 percent
lower brightness
what's my battery level?
lock the screen
```

Your deterministic router translates these into typed actions:

```python
SystemCommand(
    action="set_volume",
    value=30
)
```

Not:

```text
LLM → "amixer set Master 30%"
```

The service implementation can use the appropriate platform command/API.

That makes Texx portable later.

---

# 4. Terminal + CLI synthesis

This is possible and potentially one of the coolest features.

But I would treat **CLI synthesis as a separate security domain**.

Example:

> "Find all Python files modified in the last 7 days."

The LLM could produce:

```json
{
  "explanation": "Finds .py files modified within the past 7 days.",
  "command": "find . -name '*.py' -mtime -7",
  "risk": "low"
}
```

Texx shows:

```text
┌ CLI PROPOSAL ───────────────────────────────┐
│ find . -name '*.py' -mtime -7               │
│                                             │
│ Finds Python files modified in the last     │
│ 7 days.                                     │
│                                             │
│ [Run] [Edit] [Cancel]                       │
└─────────────────────────────────────────────┘
```

Then the user explicitly approves.

## I would define risk levels

### Low — potentially auto-run

```text
pwd
ls
git status
python --version
df -h
```

### Medium — show and confirm

```text
pip install package
git pull
mkdir project
mv file destination
```

### High — always explicit confirmation

```text
rm
sudo
chmod
chown
dd
mkfs
shutdown
reboot
kill
```

And some commands should simply be blocked or require a special mode.

The LLM should return a **command proposal**, never execute the command itself.

```text
User
 ↓
LLM synthesizes proposal
 ↓
Command validator
 ↓
Risk classifier
 ↓
TUI preview
 ↓
User approval
 ↓
Executor
```

That is much safer than an autonomous shell agent.

---

# 5. Spoken-name resolution

Yes, and I think this is essential for voice UX.

Speech recognition might produce:

```text
open fire fox
open firefox
open firebox
```

You need an alias registry:

```python
APP_ALIASES = {
    "firefox": [
        "fire fox",
        "firefox browser",
        "mozilla",
    ],
    "files": [
        "file manager",
        "my files",
        "files",
    ]
}
```

For contacts:

```text
"Call John"
```

might find:

```text
John Smith
John Williams
Johnny Brown
```

Texx should not guess.

```text
I found three matches:

1. John Smith
2. John Williams
3. Johnny Brown

Which John?
```

For one strong match:

```text
"Did you mean Firefox?"
```

You can implement scoring with:

```text
exact alias match
+ normalized text match
+ fuzzy similarity
+ phonetic similarity
+ speech recognition confidence
```

This can start without a heavy NLP model.

---

# 6. Live research

Definitely possible, though I'd separate **research** from a simple web search.

```text
SEARCH
query → results

RESEARCH
question
 ↓
plan search queries
 ↓
search multiple sources
 ↓
fetch relevant pages
 ↓
extract content
 ↓
deduplicate
 ↓
compare claims
 ↓
summarize
 ↓
save optional research memory
```

Example:

> "Research the cheapest Raspberry Pi Zero 2 W prices and tell me the best options."

Texx could display:

```text
RESEARCHING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✓ Finding sellers
✓ Comparing prices
✓ Checking availability
⟳ Verifying results

Sources: 6
Relevant: 4
```

Then return the answer with source information and timestamps.

I would **not automatically put research results into permanent memory**. They become stale.

Instead:

```text
Research cache
├── query
├── results
├── fetched_at
└── expires_at
```

The user can say:

> "Remember that supplier."

That becomes long-term memory.

---

# 7. Reminders and briefings

Very possible, and this is where Texx could become genuinely useful.

## Briefing engine

A morning briefing might combine:

```text
GOOD MORNING
Tuesday, August 25

WEATHER
72°F, partly cloudy

TODAY
• Dentist — 10:00 AM
• Team call — 2:00 PM

REMINDERS
• Call John at 5:00 PM

MEMORY / FOCUS
You're currently working on Texx.

SYSTEM
Battery: 84%
```

Each section is a separate provider.

```python
BriefingProvider:
    weather()
    calendar()
    reminders()
    tasks()
    system_status()
    relevant_memory()
```

Then:

```python
async def morning_briefing():
    results = await gather(
        weather(),
        calendar(),
        reminders(),
        system_status(),
        focus_memory()
    )
    return briefing_renderer.render(results)
```

This is better than asking the LLM to "figure out a briefing."

The LLM can optionally make the final briefing sound natural.

---

# 8. Rich TUI system dashboard

This is an excellent use of Rich.

I imagine a dashboard roughly like:

```text
╭──────────────── TEXX ────────────────╮
│ Athena                         10:42 │
│ SYSTEM: ● IDLE                           │
╰─────────────────────────────────────╯

╭──── SYSTEM ────╮ ╭──── AUDIO ───────╮
│ Battery  84%   │ │ Volume      62%   │
│ Charging  No   │ │ Mic         PTT   │
│ CPU       12%  │ │ Voice      Norman │
│ RAM      1.8G  │ ╰───────────────────╯
│ Network   ON   │
╰────────────────╯

╭──── DISPLAY ─────────────────────────╮
│ Brightness                     70%   │
╰─────────────────────────────────────╯

╭──── TEXX STATUS ─────────────────────╮
│ ● IDLE                              │
│                                      │
│ Last: "open Firefox"                 │
│ Memory: 247 entries                  │
│ Next reminder: Call John, 5:00 PM    │
╰──────────────────────────────────────╯

Texx >
```

The exact system metrics available will depend on the OS and eventually how you package it for mobile, but architecturally this is straightforward.

## State machine

Don't represent assistant status as random strings throughout the code.

Use a state manager:

```python
class AssistantState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    THINKING = "thinking"
    SPEAKING = "speaking"
    EXECUTING = "executing"
    ERROR = "error"
```

Then every subsystem publishes state changes:

```text
IDLE
 ↓ PTT
LISTENING
 ↓ speech complete
PROCESSING
 ↓
EXECUTING
 ↓
SPEAKING
 ↓
IDLE
```

For LLM conversation:

```text
IDLE
 ↓
PROCESSING
 ↓
THINKING
 ↓
SPEAKING
 ↓
IDLE
```

Your TUI simply observes the central state.

---

# 9. I would add an event bus

Once you have all these capabilities, an event bus becomes useful:

```text
EventBus
│
├── UserInputReceived
├── SpeechStarted
├── SpeechEnded
├── IntentMatched
├── CommandProposed
├── CommandConfirmed
├── CommandExecuting
├── CommandCompleted
├── MemoryStored
├── ReminderDue
├── AssistantStateChanged
└── ErrorOccurred
```

Then your components remain loosely coupled.

For example:

```text
Reminder scheduler
       │
       ▼
ReminderDue event
       │
       ├── TUI updates
       ├── Notification service
       └── Piper speaks
```

The reminder engine doesn't need to know anything about Rich or Piper.

---

# 10. Overall architecture I'd now recommend

```text
                        TEXX
                          │
             ┌────────────▼────────────┐
             │       INPUT LAYER       │
             │ Text │ PTT │ Voice      │
             └────────────┬────────────┘
                          │
             ┌────────────▼────────────┐
             │ NORMALIZE + RESOLVE      │
             │ aliases │ names │ dates  │
             └────────────┬────────────┘
                          │
             ┌────────────▼────────────┐
             │      INTENT ROUTER       │
             │ deterministic first      │
             └──────┬─────────────┬─────┘
                    │             │
             Known command     Unknown/
                    │          conversational
                    │             │
         ┌──────────▼───┐    ┌────▼─────┐
         │ COMMAND CORE │    │ LOCAL LLM │
         └──────┬───────┘    └────┬─────┘
                │                 │
                └────────┬────────┘
                         ▼
               ┌────────────────────┐
               │ VALIDATION LAYER   │
               │ schema + risk      │
               │ permissions        │
               └─────────┬──────────┘
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
      FILES             APPS           TERMINAL
      MEMORY           SYSTEM          RESEARCH
      REMINDERS        WEATHER         CALENDAR
        │                │                │
        └────────────────┼────────────────┘
                         ▼
                    EVENT BUS
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
         TUI            TTS         Notifications
```

Yes—that's a very good choice for Texx. **PTT should be the primary voice input**, especially for an offline-first, phone-friendly assistant.

### Recommended voice flow

```text
User holds PTT
     ↓
Texx state: LISTENING
     ↓
Start microphone capture
     ↓
VAD detects actual speech
     ↓
User releases PTT
     ↓
Stop capture
     ↓
Vosk transcribes
     ↓
Texx state: PROCESSING
     ↓
Intent/router handles request
     ↓
Action or LLM response
     ↓
Piper speaks response
     ↓
Texx state: IDLE
```

### Why both PTT and VAD?

PTT is the **hard boundary**: Texx only uses the microphone while you intentionally hold the button.

VAD is an optimization:

* Ignore silence at the beginning.
* Trim trailing silence.
* Optionally detect when you've stopped talking before button release.
* Improve the audio sent to Vosk.

So you avoid the overhead of:

```text
always listening
→ wake-word detection
→ false activations
→ continuous microphone processing
```

Instead:

```text
IDLE = essentially no voice-processing workload
PTT pressed = microphone + VAD active
PTT released = processing stops
```

## I would use these states

```python
class AssistantState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    PROCESSING = "processing"
    THINKING = "thinking"       # only when LLM is active
    EXECUTING = "executing"
    SPEAKING = "speaking"
    CONFIRMING = "confirming"
    ERROR = "error"
```

That maps nicely onto your TUI:

```text
╭────────────── TEXX ──────────────╮
│ Status: ● IDLE                   │
│ Voice:  PTT READY                │
│ Mic:    OFF                      │
│ Model:  STANDBY                  │
╰──────────────────────────────────╯
```

While holding PTT:

```text
│ Status: ● LISTENING              │
│ Voice:  RECORDING                │
│ Mic:    ON                       │
│ [██████████░░░░] Speech          │
```

Then:

```text
│ Status: ● PROCESSING             │
│ "open Firefox"                   │
```

And if it needs the local LLM:

```text
│ Status: ● THINKING               │
│ Local model generating...        │
```

For a deterministic command such as **"open Firefox"**, it should ideally go:

```text
PTT → Vosk → route → execute → Piper
```

**No LLM involved at all.**

For:

> "Explain why photosynthesis is important as if I'm 10."

Then:

```text
PTT → Vosk → route → LLM → Piper
```

This gives Texx a nice resource model: **the microphone is off until PTT, the LLM is idle until needed, and deterministic commands remain fast and cheap.**


## My biggest recommendation

**Don't build Texx as "an LLM assistant with tools."**

Build it as:

> **A local personal operating environment with deterministic services, memory, scheduling, and system control — with an LLM available as one of its intelligence modules.**

That distinction will make Texx faster, safer, much easier to run on limited hardware, and still useful when the model is unavailable.


