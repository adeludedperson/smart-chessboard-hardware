# Firmware

Arduino sketches for the ESP32 (fqbn `esp32:esp32:esp32`, port
`/dev/cu.usbserial-0001`). One folder per sketch.

## The two that matter day-to-day

| Sketch | Purpose |
|---|---|
| `board_stream/` | **PRODUCTION — currently flashed. This is what the app talks to.** Measures chain length at boot (never configured — unplug a board, hit reset, it re-sizes), streams `raw = 0xNNNNNNNNNNNNNNNN` at ~50 fps, re-gates every 5 s |
| `read_audit/` | Reads the same board state four ways (CP-low vs CP-high across the PL rise, 3 µs vs 200 µs clock) and diffs them. Run this **before** blaming a sensor: it proves or clears the whole read path in one go |

Why 50 fps: the daemon's move inference uses an 80 ms debounce, so the old
400 ms cadence could not see a clean lift/place pair. The daemon's parser is
`/raw = 0x([0-9A-Fa-f]{4,16})/` — `board_stream` matches it, `quadrant_diag64`
also matches but is far too slow for gameplay.

| Sketch | Purpose |
|---|---|
| `dgt_clock_bridge/` | DGT 3000 chess clock ↔ USB serial bridge (separate ESP32; jack on GPIO21/22 bit-banged master + GPIO18/19 hardware slave; 5 k pull-ups required). Prints `clk L=… R=…` / `btn …`, accepts `disp`, `set`, `end`, `wake`. Tested on the real clock. For feeding real clock times to the daemon (daemon side not built yet) |
| `quadrant_diag64/` | 4-board gate test, 400 ms cadence. Superseded by `board_stream` for anything app-facing |
| `quadrant_diag32/` | 2-board (32-bit) gate test, `sensors raw = 0xNNNNNNNN` every 400 ms |
| `quadrant_test/` | Single-board 16-square reader with ASCII grid — use for solo board bring-up |
| `chain_len/` | Injects a single 1 and counts clocks until it appears. The count *is* the stage count. The only tool that detects a chain that is too SHORT |

## Diagnostics (kept for history / reuse)

| Sketch | Purpose |
|---|---|
| `quadrant_diag/` | Single-board gate test (16-bit shift test + sensor read). Solo bring-up gate for new boards |
| `quadrant_diag2/`, `quadrant_diag3/` | Earlier debug iterations (diag3 = print-on-change) |
| `quad_probe/` | ESP32-as-multimeter: P34/P35 + 10k rail-clamp measurements |
| `adc_diag/`, `rail_test/`, `short_meter/`, `wiring_diag/`, `sensor_test/` | One-off rigs from the Aug '26 debugging sessions |

Scale-up pattern proven by diag32: copy, widen the integer, double the loop
count, print wider hex. 64-bit version: `uint64_t`, 64 clocks, `0x%016llX`.

## Flash

```bash
export PATH=/opt/homebrew/bin:$PATH
cd firmware
pkill -f live_board                      # ONE serial reader at a time — always
pkill -f "bun run src/index.ts"          # the app daemon grabs the port too
arduino-cli compile --fqbn esp32:esp32:esp32 <sketch>
arduino-cli upload -p /dev/cu.usbserial-0001 --fqbn esp32:esp32:esp32 <sketch>
```

## `tools/` — serial readers + dashboards (no pyserial; raw termios)

| Tool | Purpose |
|---|---|
| `live_board32.py` | 2-board live dashboard, two 4×4 grids → http://localhost:8123 |
| `live_board.py` | 1-board version, one 4×4 grid, same port |
| `board_state.py [N]` | **One honest snapshot**: gate + measured stage count + per-board 4×4 grids. Refuses to print squares if the gate failed. Use this instead of hand-decoding hex |
| `watch_square.py [N] [board] [S]` | Timestamped change log. `90` = watch all 64, `90 3 1` = watch board 3 S1 only. Ends with per-square flip counts and says whether ONE net or MANY are misbehaving — the fastest way to tell a loose wire from a dead part |
| `read_serial.py N` | Dump serial for N seconds (no reset). **Drops bytes above ~10 fps** — written for the old 2.5 fps sketches. Mangled output from `board_stream` is this tool's fault, not the ESP32's |
| `read_serial_reset.py N` | Pulse RTS (hard reset) then dump — also unwedges a flooding CP2102 stream |
| `magnet_sweep.py N` | Record N seconds, summarize which squares responded |

Gotchas: **macOS has no `timeout(1)`** — a diagnostic prefixed with it silently
produces zero output and reads as "the device answered nothing"; that has caused
wrong conclusions twice. **An all-clear frame `0xFFFF…FF` is indistinguishable
from a dead chain or unpowered sensors** — always confirm with pieces on the
board. **The gate cannot see a sensor-supply fault** (chips are on 3V3, sensors
on 5V), so `CHAIN64: PASS` says nothing about whether the sensors have power.
Check the dashboard's staleness line before believing anything;
a USB replug kills a running reader's port handle (restart it); a healthy
diag32 stream is ~2.5 lines/s — hundreds/s means the stream is wedged,
RTS-reset it.
