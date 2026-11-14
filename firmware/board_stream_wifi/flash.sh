#!/usr/bin/env bash
#
# flash.sh — put board_stream_wifi on the ESP32 over USB. ONE cable session,
# then never again: the sketch runs ArduinoOTA, so later updates go over Wi-Fi
# with `ota.sh`.
#
#   firmware/board_stream_wifi/flash.sh                       # auto-pick port
#   firmware/board_stream_wifi/flash.sh /dev/cu.usbserial-0001
#
# Why the pkill: exactly one process may hold a /dev/cu.* device. The app
# daemon grabs it the moment a board appears, and an upload against a held
# port fails with a timeout that reads like dead hardware. Kill the readers
# first.
set -euo pipefail

export PATH=/opt/homebrew/bin:$PATH

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIRMWARE_DIR="$(cd "$HERE/.." && pwd)"
SKETCH="board_stream_wifi"
FQBN="esp32:esp32:esp32"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
die() { printf '\n\033[31mFAIL\033[0m %s\n' "$*" >&2; exit 1; }

[ -f "$HERE/secrets.h" ] || die "$HERE/secrets.h is missing.
  cp $HERE/secrets.example.h $HERE/secrets.h
  then put your 2.4 GHz Wi-Fi name and password in it."

grep -q 'YOUR_WIFI_NAME\|YOUR_WIFI_PASSWORD' "$HERE/secrets.h" && die "secrets.h still has the YOUR_... placeholders in it. Fill them in."

PORT="${1:-$(ls -t /dev/cu.usbserial-* 2>/dev/null | head -1 || true)}"
[ -n "$PORT" ] || die "no /dev/cu.usbserial-* found. Is the ESP32 plugged in?
  (the CP2102 sometimes vanishes from /dev — unplug and replug the USB cable)"

say "1/4  Releasing the serial port"
pkill -f live_board 2>/dev/null || true
pkill -f "bun run src/index.ts" 2>/dev/null || true
pkill -f board_state.py 2>/dev/null || true
pkill -f watch_square.py 2>/dev/null || true
sleep 1
echo "  serial readers stopped"

say "2/4  Compile"
cd "$FIRMWARE_DIR"
arduino-cli compile --fqbn "$FQBN" "$SKETCH"

say "3/4  Upload -> $PORT"
arduino-cli upload -p "$PORT" --fqbn "$FQBN" "$SKETCH"

say "4/4  First 25 s of serial (watch it join Wi-Fi and find the daemon)"
echo "  Looking for:  wifi up  /  daemon link up  /  CHAIN64: PASS"
echo
stty -f "$PORT" 115200 raw
# macOS has no timeout(1) — read the device for a bounded number of seconds
# with a background killer instead.
( sleep 25; pkill -f "cat $PORT" 2>/dev/null || true ) &
cat "$PORT" 2>/dev/null | head -60 || true

cat <<'NEXT'

Next:
  1. Unplug the USB cable from the laptop.
  2. Plug the ESP32 into a 5 V USB charger (2 A or better — 64 Hall sensors
     draw ~350 mA on top of the ESP32).
  3. Watch it arrive on the host that receives the stream (SCB_HOST in
     secrets.h).

  No cable, no output? Open http://chess-sensor.local in a browser — the
  board serves its own status page: Wi-Fi signal, daemon link, gate result.
NEXT
