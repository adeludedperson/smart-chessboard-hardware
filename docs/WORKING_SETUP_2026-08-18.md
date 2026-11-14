# WORKING SETUP — 32-square chain (2 boards) — 2026-08-18, 4:25 AM

**Status: 32/32 squares verified on the live dashboard. CHAIN32 PASS.
Do not change any wire below without re-running the gate test.**

- Board A = board #1 (socketed chips, shop-reworked sensors). Wired to ESP32.
- Board B = new board (populated at shop with corrected orientation). End of chain.

## Orientation convention (use this when describing wiring)

As the boards sit on the desk, reading each header LEFT → RIGHT:

- **J1: 5V, 3V3, GND, PL, CP, SER** (SER on the right)
- **J2: SER, CP, PL, GND, 3V3, 5V** (SER on the left)

Same for both boards. Every pin also has its name on the silk beside it —
labels are the ground truth, always match label-to-label.

## Wiring (13 wires total)

### 1. ESP32 → board A J1 (6 wires, unchanged from 17/8)

| J1 pin (left→right) | wire |
|---|---|
| 5V | ESP32 VIN/5V |
| 3V3 | blue, via breadboard col 10 (3V3→a10, c10→J1 3V3) |
| GND | grey |
| PL | GPIO25 |
| CP | GPIO26 |
| SER | GPIO14 (test-pattern injection for diag) |

Breadboard extras (from 17/8, still in place): 10k e10↔e20 with P34→a20,
10k e30↔e40 with P35→a40. Optional a30 probe wire REMOVED from A J2.

### 2. Board A J2 → board B J1 bridge (6 F-F jumpers, label-to-label)

Mirror flip — leftmost on A J2 goes to rightmost on B J1:

| A J2 (from left) | color used | B J1 (from left) |
|---|---|---|
| 1st SER | white | 6th SER |
| 2nd CP | green | 5th CP |
| 3rd PL | yellow | 4th PL |
| 4th GND | black | 3rd GND |
| 5th 3V3 | orange | 2nd 3V3 |
| 6th 5V | red | 1st 5V |

Keep housings vertical and parallel — touching sleeves on adjacent pins
caused a phantom 3V3↔GND short on 17/8.

### 3. Board B J2 → ESP32 (1 wire)

- B J2 far-LEFT pin (SER) → GPIO27. This is the read point of the whole chain.

Full 4-board build repeats pattern 2 twice more and moves the P27 wire to the
last board's J2 SER. Total will be 25 wires.

## Firmware + tools (all working, in repo)

- `firmware/quadrant_diag32/` — flashed now. Boot + every ~4 s: shift-only
  gate test (0s→0x00000000, 1s→0xFFFFFFFF = "CHAIN32: PASS"), plus
  `sensors raw = 0xNNNNNNNN` every 400 ms.
- `firmware/tools/live_board32.py` → http://localhost:8123 — two 4×4 grids,
  ✓ per square, n/32, staleness warning. Launch:
  `(python3 firmware/tools/live_board32.py > /tmp/live_board32_server.log 2>&1 &)`
- Only ONE serial reader at a time: `pkill -f live_board` before any
  upload or read script.

## Bit order (EMPIRICALLY PROVEN 32/32)

32-bit word, MSB = first bit read:

- **bits 31..16 (first 16 read) = board B** (last in chain), via CHAIN_ORDER
- **bits 15..0 (next 16) = board A**, via same CHAIN_ORDER

`CHAIN_ORDER = [15,14,11,10,2,3,6,7,13,12,9,8,0,1,4,5]` per board
(first bit read → square). Magnet = bit LOW.

## ~~OPEN ISSUE~~ RESOLVED 19/8 — board B S2 stuck low

RESOLVED: next day S2 read clear and passed a full 32/32 re-sweep. Cause: something magnetic near that desk corner on 18/8. Sensor is healthy.
Not the frozen-feed ghost from 17/8. First test next time: lift board B
into the air and tilt it — clears = magnet on/under the desk near that
corner; stays on = swap that one sensor (spares ~70).

## Gotchas confirmed again

- CP2102 can vanish from `/dev` entirely — unplug/replug USB fixes it.
- Serial stream can wedge and flood garbage (impossible >baud line rates);
  RTS reset via `read_serial_reset.py` cleared it. Check line cadence
  (~2.5 lines/s from diag32) before believing data.
- A magnet placed on a square with the stream wedged reads as "nothing" —
  freshness check first, always.
