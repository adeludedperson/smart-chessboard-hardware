#!/usr/bin/env bash
#
# flash.sh — put dgt_clock_bridge on the clock ESP32 over USB. ONE cable
# session, then never again: the sketch runs ArduinoOTA, so later updates go
# over Wi-Fi with `ota.sh`.
#
#   firmware/dgt_clock_bridge/flash.sh                        # $SCB_CLOCK_PORT, else newest port
#   firmware/dgt_clock_bridge/flash.sh /dev/cu.usbserial-0001
#
# Careful when the board ESP32 is plugged in too: both show up as
# /dev/cu.usbserial-*. Pass the port (or set SCB_CLOCK_PORT) to be sure you
# flash the clock bridge and not the chessboard.
#
# Why the pkill: exactly one process may hold a /dev/cu.* device. The app
# daemon grabs it (SCB_CLOCK_PORT, or the board auto-discovery), clock_talk.py
# holds it while it runs, and an upload against a held
# port fails with a timeout that reads like dead hardware. Kill the readers
# first.
set -euo pipefail

export PATH=/opt/homebrew/bin:$PATH

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIRMWARE_DIR="$(cd "$HERE/.." && pwd)"
SKETCH="dgt_clock_bridge"
FQBN="esp32:esp32:esp32"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
die() { printf '\n\033[31mFAIL\033[0m %s\n' "$*" >&2; exit 1; }

[ -f "$HERE/secrets.h" ] || die "$HERE/secrets.h is missing.
  cp $HERE/secrets.example.h $HERE/secrets.h
  then put your 2.4 GHz Wi-Fi name and password in it."

grep -q 'YOUR_WIFI_NAME\|YOUR_WIFI_PASSWORD' "$HERE/secrets.h" && die "secrets.h still has the YOUR_... placeholders in it. Fill them in."

PORT="${1:-${SCB_CLOCK_PORT:-$(ls -t /dev/cu.usbserial-* 2>/dev/null | head -1 || true)}}"
[ -n "$PORT" ] || die "no /dev/cu.usbserial-* found. Is the ESP32 plugged in?
  (the CP2102 sometimes vanishes from /dev — unplug and replug the USB cable)"

say "1/4  Releasing the serial port"
pkill -f live_board 2>/dev/null || true
pkill -f "bun run src/index.ts" 2>/dev/null || true
pkill -f board_state.py 2>/dev/null || true
pkill -f watch_square.py 2>/dev/null || true
pkill -f clock_talk.py 2>/dev/null || true
sleep 1
echo "  serial readers stopped"

say "2/4  Compile"
cd "$FIRMWARE_DIR"
arduino-cli compile --fqbn "$FQBN" "$SKETCH"

say "3/4  Upload -> $PORT"
arduino-cli upload -p "$PORT" --fqbn "$FQBN" "$SKETCH"

say "4/4  First 25 s of serial (watch it join Wi-Fi and find the daemon)"
echo "  Looking for:  ready  /  # wifi up  /  # daemon link up  /  clock connected"
echo
stty -f "$PORT" 115200 raw
# macOS has no timeout(1) — read the device for a bounded number of seconds
# with a background killer instead.
( sleep 25; pkill -f "cat $PORT" 2>/dev/null || true ) &
cat "$PORT" 2>/dev/null | head -60 || true

cat <<'NEXT'

Next:
  1. Unplug the USB cable from the laptop.
  2. Plug the ESP32 into any 5 V USB charger.
  3. Watch it arrive:  curl http://localhost:8787/api/clock/status
     You want:  "bridge":{"connected":true,"transport":"wifi"

  No cable, no output? Open http://chess-clock.local in a browser — the
  bridge serves its own status page: Wi-Fi signal, daemon link, clock state.
NEXT
