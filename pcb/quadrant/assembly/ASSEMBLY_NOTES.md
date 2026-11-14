# chess_quadrant — Assembly Notes (PID 234609)

Board: 200×200mm, 2-layer, **all through-hole**, 46 components per board, 5 boards.

## Files in this folder

- `chess_quadrant_bom.csv` — BOM, 6 line items (LionCircuits column format)
- `chess_quadrant_pos.csv` — pick-and-place / centroid, mm, both sides
- Reference renders: `../plots/render_top_50mm.png` (top), `../plots/render_bottom_50mm.png` (bottom)

## Critical: sensors go on the BOTTOM

- **S0–S15 (A3144, TO-92) mount on the BOTTOM side** of the board. Silkscreen
  for S0–S15 is on the back silkscreen layer. Everything else (R, C, U, J) is
  on the TOP.
- **TO-92 orientation — NON-STANDARD, read carefully.** The supplied A3144
  clones are mirror-pinout parts (pinout follows the TEXT face, which is on the
  curved side). Insert each sensor **rotated 180° vs the normal convention:
  the TEXT/printed side of the package must face the FLAT side of the
  silkscreen outline.** Do NOT insert flat-face-to-flat-outline — that
  reverse-powers and destroys these parts.
- **Before soldering all sensors: solder ONE sensor at position S0 only,
  power the board (5V), touch a magnet to the sensor — output must pull low.
  Confirm with us, then proceed with the rest.**
- After inserting legs, **bend each sensor 90° so the body lies FLAT against
  the PCB, text face touching the board** (the sensing face must be parallel
  to the board — an upright sensor cannot see the magnet above). It reads
  magnets through the PCB + 4mm wooden top plate.

## Polarized / orientation-sensitive parts

| Refs | Part | Orientation cue |
|---|---|---|
| S0–S15 | A3144 TO-92 | **TEXT side faces the flat side of silk outline (180° vs normal)** — bottom side |
| U1, U2 | 74HC165 DIP-16 | Pin-1 notch matches silk notch |
| J1, J2 | 1x6 pin header | Not polarized; solder vertical, pins up on TOP |
| R, C | resistors / ceramic caps | Not polarized |

## No stencil needed

All through-hole — no SMD, no solder paste stencil. Manual assembly.
