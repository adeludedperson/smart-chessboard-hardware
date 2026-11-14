#!/usr/bin/env bash
#
# ota.sh — update the ESP32 over Wi-Fi. No cable, board stays under the table.
#
#   firmware/board_stream_wifi/ota.sh                 # find it by mDNS
#   firmware/board_stream_wifi/ota.sh <board-ip>      # or by address
#
# The sketch pauses its sensor loop while the upload runs (ArduinoOTA.onStart),
# so the daemon sees the board go quiet for ~20 s and then come back. That is
# expected. Do not do this mid-game.
#
# First flash still needs the cable — use flash.sh. This only works once a
# build with ArduinoOTA in it is already on the chip.
set -euo pipefail

export PATH=/opt/homebrew/bin:$PATH

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIRMWARE_DIR="$(cd "$HERE/.." && pwd)"
SKETCH="board_stream_wifi"
FQBN="esp32:esp32:esp32"
OTA_HOST="${1:-chess-sensor.local}"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
die() { printf '\n\033[31mFAIL\033[0m %s\n' "$*" >&2; exit 1; }

[ -f "$HERE/secrets.h" ] || die "$HERE/secrets.h is missing — see flash.sh."

say "1/3  Is the board reachable?"
# Its own status page is the cheapest liveness check and tells you more than
# a ping: Wi-Fi signal, daemon link, last gate result.
if ! curl -fsS --max-time 5 "http://$OTA_HOST/" >/tmp/scb-sensor-status.txt 2>/dev/null; then
  die "no answer from http://$OTA_HOST/
  - powered? (LED off entirely = no power)
  - fast blink = it never joined Wi-Fi. Wrong password, or a 5 GHz-only network.
  - try the address instead of the name: $0 <ip>
  - find the address: arp -a | grep -i espressif"
fi
sed 's/^/  /' /tmp/scb-sensor-status.txt
rm -f /tmp/scb-sensor-status.txt

say "2/3  Compile"
cd "$FIRMWARE_DIR"
arduino-cli compile --fqbn "$FQBN" --output-dir "/tmp/scb-ota-build" "$SKETCH"

say "3/3  Upload over Wi-Fi -> $OTA_HOST"
ESPOTA="$(find "$HOME/Library/Arduino15/packages/esp32/hardware/esp32" -name espota.py -maxdepth 3 2>/dev/null | head -1)"
[ -n "$ESPOTA" ] || die "espota.py not found under ~/Library/Arduino15/packages/esp32/.
  Is the esp32 core installed?  arduino-cli core list"

/usr/bin/python3 "$ESPOTA" \
  -i "$OTA_HOST" -p 3232 \
  -f "/tmp/scb-ota-build/$SKETCH.ino.bin" \
  -d -r

cat <<'NEXT'

Done. The board reboots itself. Confirm it came back:

  curl http://chess-sensor.local/    # want: CHAIN64: PASS

NEXT
