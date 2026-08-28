#!/usr/bin/env bash
#
# Bootstrap the Texx development environment.
#
# Steps:
#   1. create the project directory scaffold
#   2. install pipx (via apt) and uv (via pipx)
#   3. create a uv-managed virtualenv (.venv)
#   4. activate the venv and install Python deps from requirements.txt
#
# Usage:
#   ./setup.sh [TARGET_DIR]
#
#   TARGET_DIR defaults to ./texx (created if missing). To set up the venv
#   inside an existing checkout, run:  ./setup.sh .
#
set -euo pipefail

TARGET_DIR="${1:-texx}"

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

echo "==> Creating virtual environment with uv"
uv venv

echo "==> Activating venv and installing dependencies"
# shellcheck disable=SC1091
source .venv/bin/activate
uv pip install -r requirements.txt

echo
echo "Setup complete. The venv is at ${TARGET_DIR}/.venv"
echo "Activate it in your shell with:  source ${TARGET_DIR}/.venv/bin/activate"
