# V2 Compact Quadrant — 33mm pitch, all-SMT, JLCPCB-assemblable

Generated board. **DRC clean (0 violations, 0 unconnected).**
469+ tracks, 431 vias, fully routed by `../generate_quadrant_v2.py`.

## What it is

132×132mm, 2-layer. One quadrant = 4×4 squares of the compact chessboard.
Order **20 pcs** (5 board-sets + spares), all identical.

Per square: UHE4913G omnipolar hall (C86815) at exact square center,
WS2812C-2020 RGB LED (C2976072) offset +8/+8mm, 100nF each. 2× 74HC165
(C22384789) chain all 16 sensors into the board-wide 64-bit shift chain.

## Regenerate

```
~/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3.9 \
    ../generate_quadrant_v2.py            # emits .kicad_pcb + BOM.csv + positions.csv
~/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli pcb drc --severity-error \
    --format json -o drc_v2.json chess_quadrant_v2.kicad_pcb
~/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli pcb export gerbers -o gerbers/ \
    --layers F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts \
    chess_quadrant_v2.kicad_pcb
~/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli pcb export drill -o gerbers/ \
    chess_quadrant_v2.kicad_pcb
```

## Order at JLCPCB

1. Zip `gerbers/`, upload at jlcpcb.com/quote. 132×132mm, 2-layer, 1.6mm, qty 20.
2. Enable "PCB Assembly" (economic, top side). Upload `BOM.csv` + `positions.csv`.
3. In the part-placement preview, CHECK ROTATIONS of U1-U16 (SOT-23), D1-D16
   (LED polarity dot!), U17/U18 pin-1 — JLC's rotation convention can differ
   from KiCad's. Fix in their viewer if a part looks turned.
4. Two BOM lines have no LCSC number yet — pick in JLC's picker:
   - CB1: 1000µF ≥6.3V SMT electrolytic, 8×10mm
   - J1/J2: 2×6 (12-pin) 2.54mm shrouded box header, through-hole
5. LED (C2976072) stock fluctuates; substitute WS2812B-2020 (same footprint/
   pinout) if dry.

## Interconnect (J1 = IN, top edge; J2 = OUT, bottom edge)

2×6 keyed box header + 12-way IDC ribbon. Inner row (board side) carries
signals, outer row is all GND:

| Col (left→right) | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| Inner | /PL | CP | SER | +5V | +3V3 | LED_DATA |
| Outer | GND | GND | GND | GND | GND | GND |

Chain: hub → J1 of Q1 → (J2 → next J1) ×3. Quadrants tile with alternating
180° rotation so J2/J1 meet at the seams.

## Firmware maps (printed by the generator)

```
CHAIN_ORDER (first bit read -> last) = [15,14,11,10, 2,3,6,7, 13,12,9,8, 0,1,4,5]
LED_CHAIN   (square idx, serpentine) = [0,1,2,3, 7,6,5,4, 8,9,10,11, 15,14,13,12]
```

`CHAIN_ORDER[i]` = which square (0-15, row-major from board origin) produced
the i-th bit shifted out of this quadrant. LED index k in the WS2812 chain
lights square `LED_CHAIN[k]`.

## Still manual / to verify before paying

1. Rotation check in JLC viewer (step 3 above) — the one real risk.
2. Hub PCB (ESP32 + Micro-USB + charger + 18650 holder): DONE and DRC-clean,
   see ../hub_v2/README.md.
3. First article: power one assembled quadrant alone (hub or bench 3V3/5V via
   J1) and run the firmware self-test before building all five sets.
