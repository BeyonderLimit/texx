#!/usr/bin/env bash
#
# voice-config.sh — one-shot voice setup for Texx.
#
# Pulls a microphone, speech-to-text (Vosk) and text-to-speech (Piper) into
# working order without requiring the user to dig through drivers, model files
# and slash commands. Safe to re-run; everything is idempotent.
#
# What it does (press Enter to accept each step, or run with --yes):
#   1. Installs the Python voice libraries into the project venv
#      (creates .venv with uv or python3 -m venv if missing).
#   2. Installs the system audio packages PortAudio needs (sudo; driver
#      detection itself is delegated to mic-probe.sh).
#   3. Probes the microphone, sets the system default source and does a 10s
#      test recording (runs mic-probe.sh).
#   4. Downloads a small Vosk model and a Piper English voice into
#      ~/.local/share/texx/models/  (~110 MB).
#   5. Points Texx at those files (writes vosk_model_path/piper_voice_path)
#      and prints a summary. Restart Texx (or use /voice set) to pick them up.
#
# Usage:
#   ./voice-config.sh                # interactive
#   ./voice-config.sh -y             # non-interactive: accept every step
#   ./voice-config.sh --no-install   # skip pip/apt installs (existing venv)
#   ./voice-config.sh --no-mic       # skip the mic probe
#   ./voice-config.sh --no-models    # skip model downloads (already present?)
#   ./voice-config.sh --help
#
# Advanced:
#   --vosk-url URL       alternative Vosk model zip
#   --piper-onnx URL     alternative Piper voice (.onnx)
#   --piper-config URL   matching Piper voice config (.onnx.json)
#
set -uo pipefail

REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${HOME}/.local/share/texx"
MODELS_DIR="${DATA_DIR}/models"
PYTHON=""

C_RESET='\033[0m'; C_BOLD='\033[1m'; C_GREEN='\033[32m'; C_YELLOW='\033[33m'; C_RED='\033[31m'; C_CYAN='\033[36m'
info()  { echo -e "${C_CYAN}==>${C_RESET} $*"; }
ok()    { echo -e "${C_GREEN}[ok]${C_RESET} $*"; }
warn()  { echo -e "${C_YELLOW}[warn]${C_RESET} $*"; }
err()   { echo -e "${C_RED}[error]${C_RESET} $*" >&2; }
section() { echo -e "\n${C_BOLD}== $* ==${C_RESET}"; }

# --- flags ---------------------------------------------------------------
AUTO_YES=0; DO_INSTALL=1; DO_MIC=1; DO_MODELS=1
VOSK_URL="https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
PIPER_ONNX_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx"
PIPER_CONFIG_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json"

usage() {
  awk 'NR > 1 && /^#/ { print substr($0, 3); next }
       NR > 1 { exit }' "${BASH_SOURCE[0]}"
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -y|--yes) AUTO_YES=1 ;;
    --no-install) DO_INSTALL=0 ;;
    --no-mic) DO_MIC=0 ;;
    --no-models) DO_MODELS=0 ;;
    --vosk-url) shift; VOSK_URL="${1:-$VOSK_URL}" ;;
    --piper-onnx) shift; PIPER_ONNX_URL="${1:-$PIPER_ONNX_URL}" ;;
    --piper-config) shift; PIPER_CONFIG_URL="${1:-$PIPER_CONFIG_URL}" ;;
    -h|--help) usage ;;
    *) err "Unknown option: $1 (see --help)"; exit 2 ;;
  esac
  shift
done

confirm() {  # confirm "question"
  [[ $AUTO_YES -eq 1 ]] && return 0
  local ans
  while true; do
    read -rp "$1 [y/N] " ans
    case "$ans" in
      [Yy]*) return 0 ;;
      [Nn]*|"") return 1 ;;
      *) echo "  please answer y or n." ;;
    esac
  done
}

SUDO=""
if [[ $EUID -ne 0 ]]; then
  if command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi
fi

# ==========================================================================
# 1. Python voice libraries in the project venv
# ==========================================================================
step_venv() {
  section "Installing Python voice libraries"

  if [[ $DO_INSTALL -eq 0 ]]; then
    if [[ -x "${REPO_DIR}/.venv/bin/python" ]]; then
      ok "Skipping installs (--no-install) — using existing .venv"
      PYTHON="${REPO_DIR}/.venv/bin/python"
    else
      PYTHON="$(command -v python3 || true)"
      warn "--no-install given but no .venv exists — relying on system python: ${PYTHON:-none}"
    fi
    return 0
  fi

  # Prefer a uv-managed venv when uv is present (needs no python3-venv), else
  # a plain python3 -m venv.
  if ! [[ -x "${REPO_DIR}/.venv/bin/python" ]]; then
    if command -v uv >/dev/null 2>&1; then
      info "Creating .venv with uv"
      (cd "$REPO_DIR" && uv venv)
    else
      info "Creating .venv with python3 -m venv"
      python3 -m venv "${REPO_DIR}/.venv" 2>/dev/null \
        || { err "Could not create a venv. Install python3-venv (e.g. '${SUDO:+sudo }apt install python3-venv') or install uv, then re-run me."; return 1; }
    fi
  fi
  PYTHON="${REPO_DIR}/.venv/bin/python"

  info "Installing requirements into .venv (first run can take a few minutes)"
  # requirements.txt is core-only; the voice libs come from the pyproject
  # 'voice' extra so their version pins live in one place.
  if command -v uv >/dev/null 2>&1; then
    (cd "$REPO_DIR" && uv pip install --python "$PYTHON" -r requirements.txt -e '.[voice]') || return 1
  else
    (cd "$REPO_DIR" && "$PYTHON" -m pip install -r requirements.txt -e '.[voice]') || return 1
  fi

  if ! "$PYTHON" -c "import sounddevice, vosk" 2>/dev/null; then
    warn "sounddevice/vosk not importable yet — most often a missing system"
    warn "library, which the next step installs (libportaudio2). Continuing…"
  else
    ok "Python voice libraries installed"
  fi
}

# ==========================================================================
# 2. System audio packages (PortAudio + ALSA tooling)
# ==========================================================================
step_system_audio() {
  section "System audio packages"

  if [[ $DO_INSTALL -eq 0 ]]; then
    warn "Skipping system packages (--no-install)"
    return 0
  fi
  if [[ -z "$SUDO" && $EUID -ne 0 ]]; then
    warn "No sudo available — cannot install packages. If sounddevice later"
    warn "fails with 'PortAudio library not found', run:  sudo apt install libportaudio2"
    return 0
  fi

  local to_install=()
  command -v arecord >/dev/null 2>&1 || to_install+=("alsa-utils")
  dpkg -s libportaudio2 >/dev/null 2>&1 || to_install+=("libportaudio2")

  if [[ ${#to_install[@]} -eq 0 ]]; then
    ok "Alsa tooling and libportaudio2 already present"
    return 0
  fi

  if ! confirm "Install system audio packages (${to_install[*]})?"; then
    warn "Skipped. Run '${SUDO:+sudo }apt install ${to_install[*]}' yourself if the mic fails."
    return 0
  fi
  if ${SUDO:-} apt-get install -y "${to_install[@]}" >/dev/null 2>&1; then
    ok "System audio packages installed"
  else
    warn "apt install reported a problem (maybe no passwordless sudo, or the"
    warn "packages are named differently here). You can install them yourself"
    warn "with:  ${SUDO:+sudo }apt install ${to_install[*]}"
  fi

  # Re-check after install: a fresh python process picks up a newly installed
  # libportaudio2, so a previously-failing sounddevice import now works.
  if [[ -n "${PYTHON:-}" ]] && "$PYTHON" -c "import sounddevice" 2>/dev/null; then
    ok "sounddevice now imports — PortAudio is installed and working"
  elif [[ -n "${PYTHON:-}" ]] && ! "$PYTHON" -c "import sounddevice" 2>/dev/null; then
    warn "sounddevice still can't import (likely no PortAudio). Voice capture"
    warn "will stay off until libportaudio2 is installed."
  fi
}

# ==========================================================================
# 3. Microphone probe (delegates to mic-probe.sh where present)
# ==========================================================================
step_mic() {
  section "Microphone"

  if [[ $DO_MIC -eq 0 ]]; then
    warn "Skipping mic probe (--no-mic)"
    return 0
  fi
  if ! [[ -r "${REPO_DIR}/mic-probe.sh" ]]; then
    warn "mic-probe.sh not found beside this script — skipping the mic step."
    return 0
  fi
  if ! confirm "Probe the microphone now (installs drivers if needed, tests a 10s recording)?"; then
    warn "Skipped mic probe. Texx will just use the system default microphone."
    return 0
  fi
  local mic_args=()
  [[ $AUTO_YES -eq 1 ]] && mic_args+=("-y")
  bash "${REPO_DIR}/mic-probe.sh" "${mic_args[@]}"
}

# ==========================================================================
# 4. Model downloads (Vosk + Piper)
# ==========================================================================
step_models() {
  section "Downloading speech models"

  if [[ $DO_MODELS -eq 0 ]]; then
    warn "Skipping model downloads (--no-models)"
    return 0
  fi
  if ! command -v curl >/dev/null 2>&1; then
    err "curl is needed to download models; install it (${SUDO:+sudo }apt install curl) then re-run."
    return 1
  fi
  command -v unzip >/dev/null 2>&1 || { err "unzip is needed to extract the Vosk model."; return 1; }

  if ! confirm "Download the Vosk speech model + Piper voice (~110 MB) to ${MODELS_DIR}?"; then
    warn "Skipped downloads. You can later download them manually and run '/voice set <path>'."
    return 0
  fi
  mkdir -p "${MODELS_DIR}/vosk" "${MODELS_DIR}/piper"

  # --- Vosk ---
  local vosk_dir="${MODELS_DIR}/vosk"
  if find "$vosk_dir" -maxdepth 1 -type d -name 'vosk-model*' | grep -q .; then
    ok "Vosk model already present in $vosk_dir — skipping"
  else
    info "Downloading Vosk model..."
    local zip="${MODELS_DIR}/vosk-model.zip"
    if curl -fsSL --retry 2 -o "$zip" "$VOSK_URL"; then
      if unzip -q -o "$zip" -d "$vosk_dir"; then
        rm -f "$zip"
        ok "Vosk model downloaded to $vosk_dir"
      else
        err "Unzip failed for Vosk model — extract it manually and '/voice set <dir>'."
      fi
    else
      err "Download failed for Vosk model (${VOSK_URL}). Check your internet or use --vosk-url."
    fi
  fi

  # --- Piper ---
  local piper_dir="${MODELS_DIR}/piper"
  if compgen -G "${piper_dir}/*.onnx" > /dev/null; then
    ok "Piper voice already present in $piper_dir — skipping"
  else
    info "Downloading Piper voice (English voice 'lessac')..."
    if curl -fsSL --retry 2 -o "${piper_dir}/en_US-lessac-medium.onnx" "$PIPER_ONNX_URL" \
       && curl -fsSL --retry 2 -o "${piper_dir}/en_US-lessac-medium.onnx.json" "$PIPER_CONFIG_URL"; then
      ok "Piper voice downloaded to $piper_dir"
    else
      err "Download failed for the Piper voice. Check your internet or use --piper-onnx."
    fi
  fi
}

# ==========================================================================
# 5. Point Texx at the models (settings persist to the SQLite DB)
# ==========================================================================
step_settings() {
  section "Configuring Texx"

  local vosk_dir="$(find "${MODELS_DIR}/vosk" -maxdepth 1 -type d -name 'vosk-model*' 2>/dev/null | head -1)"
  local piper_onnx="$(compgen -G "${MODELS_DIR}/piper/*.onnx" | head -1 || true)"

  local pairs=()
  if [[ -n "$vosk_dir" ]]; then pairs+=("vosk_model_path" "$vosk_dir"); fi
  if [[ -n "$piper_onnx" ]]; then pairs+=("piper_voice_path" "$piper_onnx"); fi
  if [[ ${#pairs[@]} -eq 0 ]]; then
    warn "No models found — nothing to configure. Run without --no-models, or set paths in Texx with '/voice set <path>'."
    return 0
  fi

  "${PYTHON:-python3}" - "$REPO_DIR" "${pairs[@]}" <<'PY'
import sys

repo, args = sys.argv[1], sys.argv[2:]
pairs = dict(zip(args[::2], args[1::2]))
sys.path.insert(0, repo)

try:
    # Preferred: the app's own persistence layer (runs migrations, WAL, etc.).
    from storage.database import Database
    from services.settings import Settings
    from core.events import EventBus
    db = Database()
    settings = Settings(db, EventBus())
    for key, value in pairs.items():
        settings.set(key, value)
    db.close()
except Exception:
    # Fallback (deps not installed yet): writing straight to the table works
    # because the schema is tiny and stable; the app's schema.sql re-creates it.
    import os, sqlite3
    path = os.path.join(os.path.expanduser("~"), ".local", "share", "texx", "texx.db")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS settings ("
                 "key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)")
    for key, value in pairs.items():
        conn.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (key, value, "now"),
        )
    conn.commit()
    conn.close()

for key, value in pairs.items():
    print(f"[ok] {key} = {value}")
PY
}

# ==========================================================================
# 6. Summary
# ==========================================================================
step_summary() {
  section "Done"
  ok "Voice is configured. Next steps:"
  echo "  1. Start Texx:   python3 main.py"
  echo "  2. Check status: /voice          (all three pieces should say 'loaded')"
  echo "  3. Talk:         /voice on  — hold SPACE to speak, release to send,"
  echo "                  ESC to leave voice mode."
  echo
  echo "The settings are written to ${DATA_DIR}/texx.db. They are read at"
  echo "startup — if you made changes while Texx is running, use /voice set"
  echo "or restart."
}

main() {
  echo -e "${C_BOLD}Texx voice setup${C_RESET} — this installs, downloads and configures"
  echo "everything needed for push-to-talk voice. Press Enter to run each step,"
  echo "or use -y to accept everything."
  [[ $DO_INSTALL -eq 1 ]] && step_venv
  [[ $DO_INSTALL -eq 1 ]] && step_system_audio
  [[ $DO_MIC -eq 1 ]] && step_mic
  [[ $DO_MODELS -eq 1 ]] && step_models
  step_settings
  step_summary
}

main