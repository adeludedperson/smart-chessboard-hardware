# Smart Chessboard PCB — Design Spec

**Status:** Draft for review. Geometry parameterized on `SQUARE_SIZE` (default 45mm,
confirm by measuring the real board on arrival).

---

## Architecture: 4 identical 4×4 quadrant boards

One design, fabbed ×4 (Lion Circuits Custom service, MOQ 3 — order 5 to get a spare).

Why quadrants, not one 360×360 board:
- Lion Circuits' automated quote flow + handling favors ≤200mm boards; a 360mm+
  board forces manual Custom review and worse yield/pricing.
- One defective board = replace 1 quadrant, not the whole thing.
- 180×180mm at 45mm pitch. At 55mm pitch it becomes 220×220 — still fine.

Each quadrant covers 4×4 = 16 squares. Quadrants daisy-chain with short jumper
cables (2.54mm JST-XH or Dupont headers at matching edges).

## Sensing: NO scanning matrix — 8× 74HC165 parallel-load chain

We bought 10× 74HC165 (DIP-16). Architecture:
- All 64 A3144 sensors permanently powered from 5V. (64 × ~6mA ≈ 0.4A — fine
  on the 5A PSU.)
- Each sensor's open-collector output + 10kΩ pull-up to **3.3V** → one input pin
  of a 74HC165.
- 2 registers per quadrant (16 inputs). Registers chained: Q7' → DS of next,
  across all 4 quadrants = one 64-bit chain.
- ESP32 reads the whole board with 4 wires: /PL (latch), CP (clock), Q7 (data),
  plus one /CE tie. ~64µs per full scan. No PNP column drivers needed (that was
  OpenChess's scanned-matrix bug — we avoid the whole class of problem).

74HC165 runs at **3.3V VCC** (rated 2–6V). Sensor pull-ups to 3.3V rail →
register inputs never see 5V. ESP32-safe by construction.

## Per-square cell (×16 per board)

- A3144 (TO-92, through-hole) centered under the square, **on the BACK of the
  PCB** (sensor face toward the wood above).
- 10kΩ pull-up: sensor OUT → 3.3V.
- Sensor VCC 5V, GND common.
- 100nF decoupling per sensor pair (8 caps/board) + 100nF at each register VCC.

## LEDs: NOT on this PCB

WS2812B strips (already bought, 60LED/m = 16.7mm pitch ≠ 45mm pitch...
strips are cut into 8 rows and spaced; LED lands mid-square by strip placement,
not PCB geometry). PCB carries **zero LED circuitry** — keeps it 2-layer,
low-risk, cheap. LED power/data routes through the wood channels separately.

## Connectors per quadrant

| Ref | Type | Purpose |
|---|---|---|
| J1 | 1×6 2.54mm header | IN: 5V, 3.3V, GND, /PL, CP, SER_IN |
| J2 | 1×6 2.54mm header | OUT: same, SER_OUT → next quadrant's SER_IN |

J1 bottom-left edge, J2 top-right edge so quadrants chain in an S-pattern
(Q1→Q2→Q3→Q4) with short jumpers. Last quadrant's SER_OUT → ESP32 Q7 read pin.

ESP32 itself lives on a small perfboard "hub" (already bought) with the level
shifter, buzzer driver, OLED header — NOT on these quadrant PCBs. Quadrant PCB
= sensors + registers only. Dead simple, hard to get wrong.

## Electrical nets (per quadrant)

- `+5V`, `+3V3`, `GND` — power planes/pours. GND pour both layers, stitched.
- `SENS_00..SENS_15` — sensor out → register input (D0–D7 of U1, U2).
- `/PL`, `CP` — bused to both registers, through J1↔J2.
- `SER` chain: J1.SER_IN → U1.DS; U1.Q7' → U2.DS; U2.Q7 → J2.SER_OUT.
  (74HC165: chain via DS pin 10, output Q7 pin 9, /PL pin 1, CP pin 2,
  CE pin 15 → GND.)

## Layout rules

- Sensor at exact center of each square: pitch = `SQUARE_SIZE`, first at
  (SQUARE_SIZE/2, SQUARE_SIZE/2) from board origin.
- Board outline = 4 × SQUARE_SIZE per side exactly (no margin — quadrants butt
  against each other under the playing area).
- **Keep copper pours 8mm clear of each sensor** (research: ground plane under
  sensor can spread field / cause offset; keep-out ring under each square center).
- Registers + caps in the inter-square "lanes" (the 4–5mm strips between
  keep-out zones), connectors at two board edges.
- 2-layer, 1oz, HASL, 0.3mm min trace/space (very conservative; any fab does it).
- TO-92 pads 1.0mm drill on 2.54mm pitch (bare A3144 legs, straight insert).
- **Sensor assembly rule (CORRECTED 2026-08 — empirically verified on breadboard):**
  these clones are TRUE MIRROR-PINOUT parts: **text side toward you, legs down →
  L→R = VCC, GND, OUT** (confirmed working rig: text facing user, 5V/GND/OUT
  left→right). The footprint follows the standard datasheet convention, so insert
  each sensor **rotated 180° vs a genuine part: TEXT side matches the FLAT side
  of the silkscreen outline.** Copper is unaffected.
  **MANDATORY: before mass-soldering, seat ONE sensor in position S0, power the
  board, magnet test. Only then do the other 63.** Sensor batches can be mixed —
  screen every sensor on the breadboard rig first (dud check + orientation
  confirmation in one 10s step).
- **Bend flat (added 2026-08-13, REASONED — verify at the S0 gate test):** after
  insert + solder, bend each sensor body 90° to lie FLAT against the board,
  **text face touching the PCB** (sensing axis is perpendicular to the package
  faces — an upright sensor is blind to a magnet above; the validated Step-2
  test geometry was a flat-lying sensor). Text face then points up at the
  pieces → consistent with sorting magnet poles so the working face points down (`docs/MECHANICAL.md` §8).
  Bend once only; legs fatigue.
- Mounting: 4× M2 holes at corners inset 5mm (screw/standoff into wood battens).

## Firmware read sequence (for reference)

1. /PL low 5µs → latches all 64 sensor states.
2. /PL high, then 64× (read Q7, pulse CP).
3. 64-bit bitmap → diff against previous scan → piece lift/place events.
4. Scan at 100Hz; debounce 2–3 consecutive identical frames.

## Open items before Gerber export

- [ ] `SQUARE_SIZE` measured from the real board (assume 45.0mm until then)
- [ ] Wood thickness confirmed ≤ ~12mm (else recess plan kicks in — wood-side fix)
- [ ] Lion Circuits instant quote with draft Gerbers (validate ₹2k budget!)
- [ ] DRC clean in KiCad
- [ ] Print 1:1 paper plot of one quadrant, lay on real board, verify alignment
