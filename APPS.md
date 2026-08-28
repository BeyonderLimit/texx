# APPS.md — App allowlist reference

Texx can launch and close GUI applications for you (`open Firefox`, `close Spotify`,
`/apps`, …). Because this drives external processes, it is **locked behind a strict
allowlist**. Nothing is launched with a shell, and no raw user text is ever passed to
`subprocess` — only fixed `argv` lists that you have explicitly approved.

This file is the single rigorous source of truth for how the allowlist works. `HELP.md`
summarizes it; this document is authoritative.

---

## 1. Mental model

There are two independent allowlists:

| Allowlist | Purpose | Stored as `argv` |
|---|---|---|
| **open** | Apps Texx may *launch* | a full command + arguments, e.g. `["firefox", "--new-tab"]` |
| **close** | Apps Texx may *terminate* | a process name passed to `pkill -f`, e.g. `"firefox"` |

Both are keyed by a **normalized name** (see §5). The effective list you can act on is
what `/apps` prints.

**Safety invariants (never violated):**
- No `shell=True`. Ever.
- The launched command is the exact `argv` you approved — user sentences are never
  interpolated into a shell.
- An app not on the effective allowlist is refused with a message that tells you how to
  add it (`/allow open NAME …`).
- Built-in defaults are convenient but can be fully removed (see §4).

---

## 2. Built-in defaults

These ship with Texx and are present until you `/disallow` them.

### Open defaults (`DEFAULT_OPEN_MAP`)

| Name | Launches |
|---|---|
| `firefox` | `firefox` |
| `chrome` | `google-chrome` |
| `chromium` | `chromium` |
| `files` | `xdg-open .` (file manager) |
| `terminal` | `xdg-open .` |
| `calculator` | `gnome-calculator` |
| `text editor` | `gedit` |

### Close defaults (`DEFAULT_CLOSE_MAP`)

| Name | Killed process |
|---|---|
| `firefox` | `firefox` |
| `chrome` | `chrome` |
| `chromium` | `chromium` |
| `spotify` | `spotify` |
| `calculator` | `gnome-calculator` |

### Name aliases

Spoken/abbreviated forms resolve to a canonical name before lookup:

| Alias (any case) | Resolves to |
|---|---|
| `fire fox`, `mozilla`, `firefox browser` | `firefox` |
| `file manager`, `my files` | `files` |

Aliases apply to both the allowlist key **and** to natural-language `open`/`close`
requests.

---

## 3. Adding apps — `/allow`

```
/allow open  NAME [COMMAND...]     # approve launching NAME
/allow close NAME [PROCESS]        # approve terminating NAME (by process name)
```

- `NAME` is a single token (see §6 for multi-word names).
- For **open**, the optional `COMMAND...` is the exact argv. If omitted, Texx uses
  `[NAME]` (i.e. it tries to run a binary with that name). Use `COMMAND...` to pass
  flags or to map a friendly name to a different binary.
- For **close**, the optional `PROCESS` is what `pkill -f` matches. If omitted, it
  defaults to `NAME`.

### Examples

```
/allow open featherpad featherpad
        → opens "featherpad" by running `featherpad`

/allow open code code --disable-gpu
        → opens "code" by running `code --disable-gpu`

/allow open files xdg-open /home/me/docs
        → opens "files" by running `xdg-open /home/me/docs`

/allow close myapp myapp-process
        → closes "myapp" by killing processes matching `myapp-process`
```

Adding a custom entry **overrides** the built-in default for the same normalized name
(your `argv` wins). It also **re-enables** an app you previously disabled with
`/disallow` (see §4).

Custom entries are persisted in the database and survive restarts.

---

## 4. Removing apps — `/disallow` (the important bit)

```
/disallow open  NAME
/disallow close NAME
```

`/disallow` **fully removes** the app from the effective allowlist:

1. It deletes your custom entry for `NAME` (if any).
2. It adds `NAME` to a **disabled set** so the built-in default is also blocked.

Consequence: after `/disallow open firefox`, `firefox` no longer appears in `/apps`,
and both `open firefox` (natural language) and `open firefox` via alias are refused with
a permission-denied message. This is the correct, expected behavior — a default is not
"stuck" just because it ships with Texx.

`/disallow` returns:
- `… removed from the open/close allowlist.` — something was actually removed (custom
  override, built-in default, or both).
- `… wasn't on the open/close allowlist.` — neither a custom entry nor a built-in
  default existed for that name, so there was nothing to do.

### Re-enabling

Run `/allow` for the same name again. That clears the disabled flag and (re)adds your
custom `argv`. Example:

```
/disallow open firefox     # firefox gone from /apps, open refused
/allow open firefox firefox --new-tab
                          # firefox back, launched with --new-tab
```

### Examples

```
/disallow open featherpad  → removes custom "featherpad" (if present) and blocks default
/disallow open firefox      → removes any custom override AND blocks the built-in default
/disallow close spotify     → removes custom close entry AND blocks built-in "spotify"
```

---

## 5. Name normalization

- Names are lower-cased: `FeatherPad` → `featherpad`.
- If the lower-cased name is an alias, it is rewritten to the canonical name
  (`Fire Fox` → `firefox`).
- `/allow` and `/disallow` normalize identically, so the same name removes what it added.
- The disabled set is also keyed by normalized name, so `/disallow open Firefox` blocks
  the same key that `/allow open firefox` would have created.

---

## 6. Multi-word names (caveat)

The `NAME` argument is **a single token** — everything after it on the line is treated as
the command/process, not as part of the name.

```
/allow open my app myapp        → registers app "my" (NOT "my app"), launches `myapp`
/disallow open my app            → disables app "my"  (consistent, but easy to mistype)
```

If you need a friendly multi-word label, prefer registering under a single token and
relying on the built-in alias table, or just use the binary/process name directly:

```
/allow open myapp myapp         # single token, unambiguous
```

---

## 7. Listing — `/apps`

```
/apps
```

Prints the **effective** open and close maps — i.e. built-in defaults + your custom
entries, **minus anything you disabled**. This is exactly what `open`/`close` will act
on. If an app you disabled still shows up here, the `/disallow` name did not match the
normalized key (check §5/§6).

---

## 8. Persistence

Allowlist state lives in the Texx SQLite database (same DB as everything else), as JSON
settings values:

| Setting key | Meaning |
|---|---|
| `app_open_map` | Your custom open entries (`dict[name] = argv list`) |
| `app_close_map` | Your custom close entries (`dict[name] = process`) |
| `app_disabled_open` | Names disabled from the open allowlist (`list[str]`) |
| `app_disabled_close` | Names disabled from the close allowlist (`list[str]`) |

You normally never touch these directly — use `/allow` and `/disallow`. Editing the JSON
by hand is supported but not recommended; an invalid value is ignored (treated as empty)
and the built-in defaults always apply.

---

## 9. End-to-end behavior

| You do | Result |
|---|---|
| `open firefox` | Launched (built-in default) |
| `open featherpad` (never allowed) | Refused: *not on the open allowlist — add with `/allow open featherpad`* |
| `/allow open featherpad featherpad` then `open featherpad` | Launched |
| `/disallow open featherpad` then `open featherpad` | Refused again |
| `/disallow open firefox` then `open firefox` | Refused (default blocked) |
| `/allow open firefox firefox` | Re-enabled, launched |
| `close spotify` (default) | `pkill -f spotify` |
| `/disallow close spotify` then `close spotify` | Refused |

---

## 10. Security notes

- Allowlists are the *only* path to launching/killing processes. There is no escape hatch
  that runs arbitrary user text.
- `open` uses `subprocess.Popen(argv, …)` with `start_new_session=True` and detached
  stdio, so launched apps never share the TUI's terminal and survive Ctrl-C.
- `close` uses `pkill -f <process>` (best-effort; a non-matching process is a no-op, not
  an error).
- Because close matches by process name, choose `PROCESS` carefully — a too-broad pattern
  can match unrelated processes. Prefer the exact binary/process name.
