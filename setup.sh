#!/usr/bin/env bash
#
# Bootstrap the Texx development environment.
#
# Steps:
#   1. create the project directory scaffold
#   2. install pipx (via apt) and uv (via pipx)
#   3. create a uv-managed virtualenv (.venv)
#   4. activate the venv and install the core Python deps from requirements.txt
#   5. (opt-in) install the optional LLM / voice layers via the pyproject extras
#   6. run a quick sanity check
#
# Usage:
#   ./setup.sh [TARGET_DIR] [--with-llm] [--with-voice]
#
#   TARGET_DIR defaults to ./texx (created if missing). To set up the venv
#   inside an existing checkout, run:  ./setup.sh .
#
#   The LLM and voice layers are optional by design: Texx runs fully without
#   them (they lazy-load and degrade gracefully). They are NOT installed by
#   default because llama-cpp-python compiles from source (needs a C++ toolchain
#   + CMake) and the voice stack leans on system audio libraries. A failed
#   optional install only warns — the core setup still completes.
#
set -euo pipefail

# Positional arg = TARGET_DIR; the --with-* flags opt into the optional layers.
TARGET_DIR="texx"
WITH_LLM=0
WITH_VOICE=0
for arg in "$@"; do
  case "$arg" in
    --with-llm)   WITH_LLM=1 ;;
    --with-voice) WITH_VOICE=1 ;;
    --*)
      echo "Unknown option: $arg (expected --with-llm and/or --with-voice)" >&2
      exit 2
      ;;
    *) TARGET_DIR="$arg" ;;
  esac
done

echo "==> Creating project directory scaffold at ${TARGET_DIR}"
mkdir -p "${TARGET_DIR}"
cd "${TARGET_DIR}"

# Lay down the standard package layout (no-op if the dirs already exist).
for d in core services intents voice ui storage llm tests; do
  mkdir -p "${d}"
done

echo "==> Installing pipx (requires sudo)"
sudo apt update
sudo apt install -y pipx

# Make pipx-installed binaries (uv) available in this shell session.
pipx ensurepath || true
export PATH="${HOME}/.local/bin:${PATH}"

echo "==> Installing uv via pipx"
pipx install uv

echo "==> Ensuring pipx path is set"
# Only source .bashrc if it exists to avoid potential issues
if [ -f ~/.bashrc ]; then
    source ~/.bashrc
fi

echo "==> Creating virtual environment with uv"
uv venv

echo "==> Activating venv and installing dependencies"
# shellcheck disable=SC1091
source .venv/bin/activate
uv pip install -r requirements.txt

# ------------------------------------------------------------------
# Optional layers (opt-in via --with-llm / --with-voice)
# ------------------------------------------------------------------
# Texx runs fully without these; they lazy-load and degrade gracefully.
# Installs go through the pyproject extras so the version pins live in
# one place (pyproject.toml [project.optional-dependencies]). Never fatal:
# a missing compiler or system audio library must not break core setup.
if [[ $WITH_LLM -eq 1 ]]; then
  echo "==> Installing optional LLM layer (extra: llm)"
  # -e = editable, so site-packages points at this checkout (no stale copy).
  if ! uv pip install -e '.[llm]'; then
    echo "WARN: llama-cpp-python failed to install (it compiles from source and"
    echo "      needs a C++ toolchain + CMake). /llm stays unavailable; the core"
    echo "      is unaffected. Retry with:  uv pip install -e '.[llm]'"
  fi
fi

if [[ $WITH_VOICE -eq 1 ]]; then
  echo "==> Installing optional voice layer (extra: voice)"
  # -e = editable, so site-packages points at this checkout (no stale copy).
  if ! uv pip install -e '.[voice]'; then
    echo "WARN: voice libraries failed to install. Voice stays off; the core is"
    echo "      unaffected. For the guided setup (system audio libraries + model"
    echo "      downloads) run:  ./voice-config.sh"
  else
    echo "    Note: voice capture also needs the system package libportaudio2"
    echo "    (./voice-config.sh installs it, or: sudo apt install libportaudio2)"
  fi
fi

# ------------------------------------------------------------------
# Sanity check: import the core modules
# ------------------------------------------------------------------
echo "==> Running sanity check..."
python -c "
import sys
sys.path.insert(0, '.')
from core import executor, slash, router
from services import memory, search, systeminfo
print('  All core modules imported successfully')
"

echo
echo "Setup complete. The venv is at ${TARGET_DIR}/.venv"
echo "Activate it in your shell with:  source ${TARGET_DIR}/.venv/bin/activate"
if [[ $WITH_LLM -eq 0 && $WITH_VOICE -eq 0 ]]; then
  echo "Optional layers (not installed): enable any time with"
  echo "  ./setup.sh . --with-llm      # local LLM (llama-cpp-python, builds from source)"
  echo "  ./setup.sh . --with-voice    # voice libs; then ./voice-config.sh for models"
fi
