#!/usr/bin/env bash
#
# mic-probe.sh — Hardware-agnostic microphone detection, driver install,
# default-source selection, and test recording for Debian systems.
#
# Works across ALSA-only, PulseAudio, and PipeWire(+WirePlumber) setups.
# Safe to re-run; each stage is idempotent and skips what's already fine.
#
# Usage:
#   ./mic-probe.sh              # full interactive run
#   ./mic-probe.sh --list-only  # just show hardware + sources, no changes
#   ./mic-probe.sh --yes        # non-interactive: auto-pick first source
#
set -uo pipefail

# ---------- output helpers ----------
C_RESET='\033[0m'; C_BOLD='\033[1m'; C_GREEN='\033[32m'; C_YELLOW='\033[33m'; C_RED='\033[31m'; C_CYAN='\033[36m'
info()  { echo -e "${C_CYAN}==>${C_RESET} $*"; }
ok()    { echo -e "${C_GREEN}[ok]${C_RESET} $*"; }
warn()  { echo -e "${C_YELLOW}[warn]${C_RESET} $*"; }
err()   { echo -e "${C_RED}[error]${C_RESET} $*" >&2; }
section() { echo -e "\n${C_BOLD}== $* ==${C_RESET}"; }

LIST_ONLY=0
AUTO_YES=0
for arg in "$@"; do
  case "$arg" in
    --list-only) LIST_ONLY=1 ;;
    --yes|-y) AUTO_YES=1 ;;
    -h|--help)
      echo "Usage: $0 [--list-only] [--yes]"; exit 0 ;;
  esac
done

SUDO=""
if [[ $EUID -ne 0 ]]; then
  if command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
  else
    warn "Not running as root and no sudo found — package installs will be skipped."
  fi
fi

# ==========================================================================
# 1. Detect the active sound server
# ==========================================================================
SOUND_SERVER="alsa"

detect_sound_server() {
  section "Detecting active sound stack"

  # PipeWire can itself run the pulse-compat shim, so check for the real
  # pipewire process first, then whether wireplumber (session manager) is up.
  if pgrep -x "pipewire" >/dev/null 2>&1; then
    SOUND_SERVER="pipewire"
    if pgrep -x "wireplumber" >/dev/null 2>&1; then
      ok "PipeWire is running with WirePlumber session management"
    else
      warn "PipeWire is running but WirePlumber isn't detected — session management may be handled by pipewire-media-session (deprecated) or missing entirely"
    fi
  elif pgrep -x "pulseaudio" >/dev/null 2>&1; then
    SOUND_SERVER="pulseaudio"
    ok "PulseAudio is running"
  else
    SOUND_SERVER="alsa"
    warn "Neither PipeWire nor PulseAudio detected — falling back to raw ALSA"
  fi

  info "Active sound server: ${C_BOLD}${SOUND_SERVER}${C_RESET}"
}

# ==========================================================================
# 2. Scan hardware for audio-capable devices and cross-check kernel modules
# ==========================================================================
scan_hardware() {
  section "Scanning hardware for audio input devices"

  echo "-- PCI audio controllers --"
  if command -v lspci >/dev/null 2>&1; then
    lspci -nnk 2>/dev/null | grep -A3 -iE "audio|multimedia" || echo "  none found via lspci"
  else
    warn "lspci not found (pciutils not installed)"
  fi

  echo -e "\n-- USB audio devices (interfaces, headsets, webcam mics, etc.) --"
  if command -v lsusb >/dev/null 2>&1; then
    lsusb | grep -iE "audio|microphone|webcam|headset" || echo "  none found via lsusb (device may not self-describe as audio class — check manually with 'lsusb -v')"
  else
    warn "lsusb not found (usbutils not installed)"
  fi

  echo -e "\n-- Kernel sound modules currently loaded --"
  if lsmod | grep -q "^snd"; then
    lsmod | grep "^snd" | awk '{print "  " $1}'
  else
    warn "No snd_* kernel modules loaded at all — ALSA core may not be initialized"
  fi

  echo -e "\n-- Cards registered with ALSA (/proc/asound/cards) --"
  if [[ -r /proc/asound/cards ]]; then
    cat /proc/asound/cards
    if [[ ! -s /proc/asound/cards ]]; then
      warn "ALSA sees zero cards — this usually means a missing/blacklisted driver module, not a config issue"
    fi
  else
    warn "/proc/asound/cards not readable — ALSA core module (snd) likely isn't loaded"
  fi
}

# ==========================================================================
# 3. Install missing packages / firmware based on what's missing
# ==========================================================================
ensure_packages() {
  section "Checking for missing audio packages"

  if [[ -z "$SUDO" && $EUID -ne 0 ]]; then
    warn "Skipping package installation — need root or sudo"
    return
  fi

  local to_install=()

  # Base ALSA tooling — needed regardless of server, since arecord/pactl
  # both sit on top of it.
  command -v arecord >/dev/null 2>&1 || to_install+=("alsa-utils")

  # Firmware — a lot of "no input devices" cases on laptops (esp. with
  # digital/array mics behind DSPs, e.g. Intel SOF) are actually missing
  # firmware blobs, not missing drivers.
  if ! dpkg -l 2>/dev/null | grep -q "^ii  firmware-sof-signed\|^ii  firmware-linux"; then
    to_install+=("firmware-linux" "firmware-sof-signed")
  fi

  case "$SOUND_SERVER" in
    pipewire)
      command -v pw-cli >/dev/null 2>&1 || to_install+=("pipewire" "pipewire-audio-client-libraries")
      command -v wpctl >/dev/null 2>&1 || to_install+=("wireplumber")
      dpkg -l 2>/dev/null | grep -q "^ii  pipewire-pulse" || to_install+=("pipewire-pulse")
      ;;
    pulseaudio)
      command -v pactl >/dev/null 2>&1 || to_install+=("pulseaudio" "pulseaudio-utils")
      ;;
    alsa)
      # Nothing extra beyond alsa-utils above — but flag that no session
      # manager is present, which is worth knowing even if we don't force it.
      warn "No PulseAudio/PipeWire detected. Staying on raw ALSA is valid but means no per-app mixing — consider installing pipewire-pulse for a modern stack."
      ;;
  esac

  if [[ ${#to_install[@]} -eq 0 ]]; then
    ok "All expected packages for the ${SOUND_SERVER} stack are present"
    return
  fi

  info "Installing: ${to_install[*]}"
  $SUDO apt-get update -qq
  # Don't hard-fail the whole script if one package name doesn't exist on
  # this Debian release (e.g. firmware-sof-signed isn't in every suite).
  for pkg in "${to_install[@]}"; do
    if $SUDO apt-get install -y "$pkg" 2>/dev/null; then
      ok "Installed $pkg"
    else
      warn "Could not install $pkg (may not exist in this release, or needs non-free/contrib enabled in /etc/apt/sources.list)"
    fi
  done

  # Re-detect after install in case pipewire/pulseaudio just got installed
  # but isn't running yet as a user service.
  if [[ "$SOUND_SERVER" == "pipewire" ]] && ! pgrep -x pipewire >/dev/null 2>&1; then
    info "Starting PipeWire user services"
    systemctl --user enable --now pipewire pipewire-pulse wireplumber 2>/dev/null || \
      warn "Couldn't start pipewire user services automatically — try logging out/in, or run: systemctl --user start pipewire pipewire-pulse wireplumber"
  fi
}

# ==========================================================================
# 4. List available input sources through whichever stack is active
# ==========================================================================
declare -a SOURCE_IDS
declare -a SOURCE_NAMES

list_input_sources() {
  section "Available input sources"
  SOURCE_IDS=()
  SOURCE_NAMES=()

  case "$SOUND_SERVER" in
    pipewire)
      if command -v wpctl >/dev/null 2>&1; then
        echo "-- wpctl status (Sources section) --"
        wpctl status 2>/dev/null | sed -n '/Sources:/,/^$/p'
        while IFS= read -r line; do
          local id name
          id=$(echo "$line" | grep -oE '[0-9]+\.' | head -1 | tr -d '.')
          name=$(echo "$line" | sed -E 's/^[ \t]*[*]?[ \t]*[0-9]+\.[ \t]*//; s/[ \t]*\[.*\]$//')
          [[ -n "$id" ]] && SOURCE_IDS+=("$id") && SOURCE_NAMES+=("$name")
        done < <(wpctl status 2>/dev/null | sed -n '/Sources:/,/^$/p' | grep -E '│ *[*]? *[0-9]+\.')
      fi
      # pipewire-pulse exposes the same sources via pactl too — fall through
      # as a backup listing method if wpctl parsing above found nothing.
      if [[ ${#SOURCE_IDS[@]} -eq 0 ]] && command -v pactl >/dev/null 2>&1; then
        list_pactl_sources
      fi
      ;;
    pulseaudio)
      list_pactl_sources
      ;;
    alsa)
      echo "-- arecord -l (raw ALSA capture devices) --"
      arecord -l 2>/dev/null || warn "arecord found no capture hardware"
      while IFS= read -r line; do
        local card dev
        card=$(echo "$line" | grep -oP 'card \K[0-9]+')
        dev=$(echo "$line" | grep -oP 'device \K[0-9]+')
        local label
        label=$(echo "$line" | sed -E 's/^card [0-9]+: //')
        if [[ -n "$card" && -n "$dev" ]]; then
          SOURCE_IDS+=("plughw:${card},${dev}")
          SOURCE_NAMES+=("$label")
        fi
      done < <(arecord -l 2>/dev/null | grep "^card")
      ;;
  esac

  if [[ ${#SOURCE_IDS[@]} -eq 0 ]]; then
    err "No usable input sources found."
    echo "  Things to check:"
    echo "   - Is the mic physically muted (hardware switch, some laptops have one)?"
    echo "   - Run 'dmesg | grep -iE \"audio|snd\"' for driver load errors"
    echo "   - If this is a USB mic, try 'lsusb -v' to confirm it enumerates at all"
    return 1
  fi

  echo -e "\n${C_BOLD}Index  Source${C_RESET}"
  for i in "${!SOURCE_IDS[@]}"; do
    printf "  [%d]  %s  (%s)\n" "$i" "${SOURCE_NAMES[$i]}" "${SOURCE_IDS[$i]}"
  done
  return 0
}

list_pactl_sources() {
  if ! command -v pactl >/dev/null 2>&1; then
    warn "pactl not available"
    return
  fi
  echo "-- pactl list sources short --"
  pactl list sources short 2>/dev/null | grep -v monitor
  while IFS=$'\t' read -r idx name _rest; do
    [[ -z "$idx" ]] && continue
    SOURCE_IDS+=("$name")
    SOURCE_NAMES+=("$name")
  done < <(pactl list sources short 2>/dev/null | grep -v monitor)
}

# ==========================================================================
# 5. Pick and set a default input source
# ==========================================================================
SELECTED_SOURCE=""

select_default_source() {
  section "Setting default input source"

  local choice=0
  if [[ $AUTO_YES -eq 1 ]]; then
    choice=0
    info "Auto-selecting first source (--yes given)"
  elif [[ ${#SOURCE_IDS[@]} -eq 1 ]]; then
    choice=0
    info "Only one source available — using it"
  else
    read -rp "Select source index to set as default [0-$((${#SOURCE_IDS[@]}-1))]: " choice
    if ! [[ "$choice" =~ ^[0-9]+$ ]] || [[ "$choice" -ge ${#SOURCE_IDS[@]} ]]; then
      err "Invalid selection"
      return 1
    fi
  fi

  SELECTED_SOURCE="${SOURCE_IDS[$choice]}"

  case "$SOUND_SERVER" in
    pipewire)
      if command -v wpctl >/dev/null 2>&1; then
        wpctl set-default "$SELECTED_SOURCE" 2>/dev/null && ok "Set default source (id $SELECTED_SOURCE) via wpctl"
      elif command -v pactl >/dev/null 2>&1; then
        pactl set-default-source "$SELECTED_SOURCE" && ok "Set default source via pactl"
      fi
      ;;
    pulseaudio)
      pactl set-default-source "$SELECTED_SOURCE" && ok "Set default source via pactl"
      ;;
    alsa)
      # No session concept in raw ALSA — write a user-level default device
      # override so anything using the "default" PCM picks this up.
      local asoundrc="$HOME/.asoundrc"
      {
        echo "pcm.!default {"
        echo "    type asym"
        echo "    playback.pcm \"plughw:0,0\""
        echo "    capture.pcm \"$SELECTED_SOURCE\""
        echo "}"
      } > "$asoundrc"
      ok "Wrote capture default to $asoundrc (playback left on plughw:0,0 — edit if that's wrong for your output device)"
      ;;
  esac
}

# ==========================================================================
# 6. Record a 10s test and play it back
# ==========================================================================
test_recording() {
  section "Recording 10-second test"

  if ! command -v arecord >/dev/null 2>&1; then
    err "arecord not found — install alsa-utils first"
    return 1
  fi

  local test_file="/tmp/mic-probe-test.wav"
  local device_arg=()

  case "$SOUND_SERVER" in
    alsa) device_arg=(-D "$SELECTED_SOURCE") ;;
    *) device_arg=() ;;  # pulse/pipewire route "default" through their own default source
  esac

  info "Speak into the mic now — recording for 10 seconds..."
  if arecord "${device_arg[@]}" -f cd -d 10 "$test_file" 2>/tmp/mic-probe-arecord.log; then
    ok "Recording saved to $test_file"
  else
    err "arecord failed:"
    cat /tmp/mic-probe-arecord.log >&2
    return 1
  fi

  local size
  size=$(stat -c%s "$test_file" 2>/dev/null || echo 0)
  if [[ "$size" -lt 1000 ]]; then
    warn "File is suspiciously small ($size bytes) — likely recorded silence or failed to open the device"
  fi

  if command -v aplay >/dev/null 2>&1; then
    read -rp "Play back the recording now? [y/N] " play_it
    if [[ "$play_it" =~ ^[Yy]$ ]]; then
      aplay "$test_file"
    fi
  fi

  info "Test file kept at $test_file for manual inspection if needed"
}

# ==========================================================================
# main
# ==========================================================================
main() {
  detect_sound_server
  scan_hardware

  if [[ $LIST_ONLY -eq 1 ]]; then
    list_input_sources
    exit 0
  fi

  ensure_packages
  detect_sound_server   # re-check in case installs changed the running stack
  scan_hardware

  if ! list_input_sources; then
    exit 1
  fi

  select_default_source
  test_recording
}

main
