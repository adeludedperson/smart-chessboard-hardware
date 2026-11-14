# Chess Quadrant PCB — generated board

**Status: READY TO ORDER.** Pitch finalized at **50.0mm** (2026-07-27) → board is **200×200mm**. DRC clean: 0 violations, 0
unconnected items. Sensor pad mirroring verified against live pcbnew.

> **2026-07-27 — sensor flip bug fixed.** `place()` in `generate_quadrant.py`
> called `SetOrientationDegrees(rot)` *after* `Flip()`, which overwrote the
> mirror and left all 16 A3144 footprints tagged B.Cu with **un-mirrored pad
> geometry** (S0 pads read +5V/GND/SENS at x = 23.73/25.00/26.27 — same order as
> the un-flipped library part, i.e. VCC and OUT swapped on the real board).
> Fix: rotate *before* flipping. S0 now reads 26.27/25.00/23.73 (reversed).
> **Any gerbers exported before 2026-07-27 22:00 are dead — do not fab them.**
> Current `gerbers/chess_quadrant_gerbers_50mm.zip` contains the fix.

## What this is

One 4×4 sensor quadrant (200×200mm at 50mm pitch). The full board = 4 of these
daisy-chained J2→J1 in an S-pattern. 2-layer, all through-hole, GND pour both
sides.

- 16× A3144 hall sensor (TO-92) — **soldered on the BACK** (S0–S15 silk on back),
  at exact square centers, 8mm copper keep-out ring around each
- 16× 10kΩ pull-up (R0–R15), SENS → +3V3
- 2× 74HC165 (U1 serves sensor cols 0-1, U2 cols 2-3), VCC=3.3V, CE=GND
- 10× 100nF (C0–C7 on 5V rails, C8/C9 at registers)
- J1 (IN, left edge) / J2 (OUT, right edge): `5V | 3V3 | GND | /PL | CP | SER`
- 4× M2 mounting holes

## Firmware bit order (per quadrant)

Chain: J1.SER → U1.DS, U1.Q7 → U2.DS, U2.Q7 → J2 (next quadrant / ESP32).
First bit clocked out = U2.D7 … last = U1.D0. Sensor index for each bit:

```python
# bit position in 16-bit read -> sensor number (S0..S15, row*4+col)
CHAIN_ORDER = [15, 14, 11, 10, 2, 3, 6, 7, 13, 12, 9, 8, 0, 1, 4, 5]
```

(Printed by the generator on every run — re-copy it if you change the layout.)

## Regenerate (pitch is already final at 50.0 — only change if the wood changes)

```bash
cd pcb
KPY=~/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9
CLI=~/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli

$KPY generate_quadrant.py 50.0                    # prints CHAIN_ORDER
$KPY verify_flip.py                               # pad-mirror + net audit, must say PASS
$CLI pcb drc --severity-error --format json \
  --output quadrant/drc.json quadrant/chess_quadrant.kicad_pcb
cd quadrant
$CLI pcb export gerbers --output gerbers/ \
  --layers F.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,Edge.Cuts \
  chess_quadrant.kicad_pcb
$CLI pcb export drill --output gerbers/ --format excellon chess_quadrant.kicad_pcb
cd gerbers && zip -X chess_quadrant_gerbers_50mm.zip \
  chess_quadrant-*.gbl chess_quadrant-*.gbs chess_quadrant-*.gbo \
  chess_quadrant-*.gm1 chess_quadrant-*.gtl chess_quadrant-*.gts \
  chess_quadrant-*.gto chess_quadrant-job.gbrjob chess_quadrant.drl
```

Everything derives from that one number. Board outline = 4 × pitch, square.
**Always re-run `verify_flip.py` after regenerating** — it is the guard against
the sensor mirror bug coming back.

## Files

- `chess_quadrant.kicad_pcb` — open in KiCad (PCB Editor.app) to inspect
- `gerbers/chess_quadrant_gerbers_50mm.zip` — upload this to the fab
- `drc.json` — last DRC run (0 violations, 0 unconnected)
- `plots/board_50mm.pdf` — print at 1:1 for the overlay check
- `plots/render_top_50mm.png`, `plots/render_bottom_50mm.png`
- `../verify_flip.py` — pad-mirror / net / edge-cuts / ratsnest audit

## Pre-order checklist

Machine-verified (re-checked 2026-07-27 after the flip fix):

1. [x] Square size finalized at **50.0mm** → regenerated, board 200×200mm
   (Edge_Cuts gerber measured: 200.000 × 200.000mm)
2. [x] **DRC clean** — 0 violations, 0 unconnected (`drc.json`)
3. [x] **Sensor pad mirror verified** — all 16 A3144 on B.Cu with reversed pad
   x-order (`verify_flip.py` → PASS); 10k pull-ups and caps still on the right
   nets, everything else on F.Cu

Still needs a human:

4. [ ] **Print `plots/board_50mm.pdf` at 1:1**, lay it under the actual wooden
   board, confirm sensor circles land at square centers
5. [ ] Re-upload `gerbers/chess_quadrant_gerbers_50mm.zip` to Lion Circuits
   (dimensions unchanged, so the ₹6,728 qty-5 quote should hold) → confirm
   price, then order

## Design notes / gotchas

- Sensor +5V feed tracks are 0.5mm (6mA per sensor — fine); rails are 1.0mm.
- Sensor GND pin escapes the pour keep-out via a stub + via just outside the
  8mm ring.
- The DIP-16s sit in the horizontal center lane; control signals (/PL, CP,
  SER chain) run in corridors between the two DIP pad rows.
- Pull-ups are at `y = square_center + 10mm`, inside the inter-square lane.
- A3144 pinout (flat face toward you, legs down): 1=VCC, 2=GND, 3=OUT.
  On this footprint pad 1 = +5V, pad 2 = GND (center), pad 3 = SENS.
- **Assembly (CORRECTED 2026-08 — this supersedes older text):** sensors mount
  on the BACK. These clones are TRUE MIRROR-PINOUT parts — orient each TO-92
  with its **TEXT/printed side facing the FLAT side of the silkscreen outline**
  (180° rotated vs a genuine part). After soldering, **bend the body 90° flat
  against the PCB, text face touching the board**. See `../DESIGN.md` sensor
  assembly rule.
- The footprint is mirrored onto B.Cu, so on the back side pad 1 (+5V) sits to
  the **right** of center and pad 3 (SENS) to the left (viewed from the back).
