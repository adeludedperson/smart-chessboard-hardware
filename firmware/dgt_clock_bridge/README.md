# dgt_clock_bridge — DGT 3000 clock ↔ daemon (USB serial 115200 + Wi-Fi)

Separate ESP32 that drives a DGT 3000 through its 3.5 mm jack and speaks a
line protocol on USB serial and, at the same time, over a TCP link it dials
into the daemon over Wi-Fi. Tested on the real clock 2026-09-26: connect, text,
set/run, live times, lever, 5 buttons, recovery after clock off/on, 10 min soak.

| Clock jack | ESP32 |
|---|---|
| L / tip = SCL | GPIO22 (bit-banged master) + GPIO19 (hardware slave, Wire1) |
| R / ring = SDA | GPIO21 (bit-banged master) + GPIO18 (hardware slave, Wire1) |
| sleeve | GND |

**Pull-ups required:** 5 kΩ (2 × 10 kΩ in parallel) from each line to 3V3.
Boot line `pins sda21=1 scl22=1 sda18=1 scl19=1` = bus idle and healthy.
3.3 V only; never plug into a real DGT board.

Flash (from repo root), first time over USB:
```
firmware/dgt_clock_bridge/flash.sh /dev/cu.usbserial-0001   # compile + upload + 25 s of serial
firmware/dgt_clock_bridge/ota.sh                            # later: over Wi-Fi (chess-clock.local)
```
Or by hand:
```
export PATH=/opt/homebrew/bin:$PATH
arduino-cli compile --fqbn esp32:esp32:esp32 firmware/dgt_clock_bridge
arduino-cli upload -p /dev/cu.usbserial-0001 --fqbn esp32:esp32:esp32 firmware/dgt_clock_bridge
```

Out: `ready`, `clock connected|disconnected`, `clk L=h:mm:ss R=h:mm:ss run=lr,rr`
(on change, max 4/s, plus 1/s heartbeat), `btn back|minus|play|plus|fwd|onoff|lever_left|lever_right`,
`err …`, `pong`, `version dgt_clock_bridge 1.1.0`, `hello …` (Wi-Fi only, see below).
In: `disp <text>[|beep]`, `end`, `set lh lm ls rh rm rs lr rr` (run 0 stop/1 down/2 up),
`ping`, `version`, `wake` (force full reconnect), `debug` (toggle hex packet log, Serial only).
Every protocol line goes to USB serial AND the Wi-Fi socket. Lines starting
with `#` are local Serial-only notes (Wi-Fi/link up/down); ignore them.

## Wi-Fi

1. `cp firmware/dgt_clock_bridge/secrets.example.h firmware/dgt_clock_bridge/secrets.h`
   and fill in `WIFI_SSID` / `WIFI_PASS` (2.4 GHz). Same values as
   `board_stream_wifi`; the port is `SCB_CLOCK_PORT 8796`. `secrets.h` is gitignored.
2. Flash once over USB. The bridge then:
   - joins Wi-Fi in the background (USB works from boot, with or without Wi-Fi),
   - finds the daemon: mDNS `SCB_HOST` / `SCB_HOST_ALT` → last good IP (NVS
     `scbclk/hostip`) → `SCB_FALLBACK_IP`, and connects to TCP port **8796**,
   - sends `hello dgt_clock_bridge <ver> <mac> <ip>`, then `clock connected|disconnected`,
     then a `clk` line if the clock is connected,
   - answers the daemon's `ping` (every 2 s) with `pong`. Nothing from the daemon
     for 10 s → drop and redial (1 s → 5 s backoff).
3. Status page: <http://chess-clock.local/> (uptime, RSSI, daemon link, clock,
   last `clk`, lines sent/dropped, reconnects, heap, OTA).
4. OTA: hostname `chess-clock`, no password (`ota.sh`). The clock loop pauses
   during the upload; do not update mid-game.

LED (GPIO2): fast blink = no Wi-Fi, slow blink = no daemon, solid = linked.
Wi-Fi down for 60 s after it was up once → the bridge reboots. The clock
reconnects showing 0:00:00 until the daemon sends a new `set`.

Notes:
- In remote mode the lever does not switch sides; the host must send a new `set`.
- `run=` is what the host last set, not read back from the clock.
- Clock switched off/on is detected (time broadcast byte 16 = 0x00) and the
  last times are restored automatically.

Try it: `python3 firmware/tools/clock_talk.py 5 "disp HELLO|10"`.
