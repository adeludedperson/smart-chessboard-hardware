# Hub V3 — 88×60mm, ESP32 + **USB-C** + CH340C + TP4056 + 18650

**Status: DONE, DRC-clean.** 0 errors, 0 unconnected items, 4 cosmetic silk
warnings (the same SW1/BT1 overhangs hub_v2 has). 223 tracks + 323 vias,
2-layer, GND pour both sides. Gerbers + drill in `gerbers/`, ready to zip.

This is **hub_v2 with the Micro-USB port replaced by USB-C.** Nothing else on
the board changed — same placement, same GPIO map, same power tree. It was
re-autorouted from scratch because the connector's pad field moved.

`../hub_v2/` is untouched and still valid if you'd rather build the
micro-USB version.

## Ordering note — BT1 is hand-fitted, not assembled by JLC

`BOM.csv` deliberately omits **BT1 (18650 holder)**. The only JLC part matching
the Keystone 1042 land pattern is C5249310: $4.85/pc, **sold in 50-pc reels**
(~$242 for a 5-board run) and flagged **Standard Only**, which would force the
whole order off Economic assembly. Buy a holder locally and solder the two
pads by hand.

Parts picked for the previously-blank BOM lines (verified in stock against
JLCPCB's live parts API, 2026-09-04):

| Ref | Part | LCSC | Stock |
|---|---|---|---|
| SW2, SW3 | C&K PTS645SM43SMTR92LFS tact | C221880 | 4,014 |
| SW1 | C&K PCM12SMTR slide switch | C221841 | 801 |
| J1 | ZX-PZ2.54-2-6PZZ 2x6 header | C7501277 | 35,112 |

SW2/SW3 are one merged BOM line — JLCPCB rejects two lines matched to the same
part ("Multiple lines in the BOM have been matched to the same part").

⚠️ Verify SW1: KiCad's `SW_SPDT_PCM12` says right-angle, JLC's attribute table
says vertical. Check against C&K's `pcm.pdf` land pattern before paying.


---

## What changed vs hub_v2

| | hub_v2 | hub_v3_usbc |
|---|---|---|
| Connector | USB Micro-B, Wuerth 629105150521 land pattern | **USB-C 16-pin receptacle**, HRO `TYPE-C-31-M-12` land pattern |
| Connector position | USB1 @ (36.00, 3.45) rot 0 | USB1 @ (35.50, 3.90) **rot 180** (mouth faces the top edge, 0.25mm inside it) |
| CC pulldowns | n/a | **R8, R9 — 5.1kΩ 0603**, CC1→GND and CC2→GND |
| Net count | — | +2 nets (`CC1`, `CC2`) |
| Net classes | Default / Power / VBUS | + **`USB_C`** (0.20mm track, 0.15mm clearance) for UDP, UDM, CC1, CC2 |
| Zone pours | 0.35mm clearance, 0.25mm min neck | 0.25mm clearance, 0.20mm min neck (see below) |
| BOM | 21 lines | 22 lines (USB-C, 5k1 ×2; MicroUSB gone) |

### Why the 5.1k resistors are not optional

A USB-C **source** keeps VBUS off until it sees a sink advertise itself by
pulling CC to ground through 5.1kΩ (Rd). Without R8/R9 a USB-C charger or a
USB-C laptop port supplies **nothing** — the board would only charge from a
legacy USB-A→C cable, which has its own resistor in the plug. Both CC1 and CC2
get their own resistor (never one shared resistor across both), so the cable
works either way up.

### USB 2.0 wiring, both orientations

The receptacle has duplicate differential pairs so it works flipped. This is a
USB 2.0-only design, so the duplicates are shorted on the board:

| Receptacle pins | Net | Goes to |
|---|---|---|
| A1, B1, A12, B12 + 4 shield legs | GND | pour |
| A4, B4, A9, B9 | VBUS | D1 (SS34), TP4056 IN, C5, R6 |
| A6 + B6 (DP1, DP2) | UDP | CH340C pin 5 |
| A7 + B7 (DN1, DN2) | UDM | CH340C pin 6 |
| A5 | CC1 | R8 → GND |
| B5 | CC2 | R9 → GND |
| A8, B8 (SBU1, SBU2) | *not connected* | — |

No PD, no alt-mode, no SBU. 5V @ whatever the source gives on a plain
Rd-only sink — plenty for the TP4056's 1A charge current.

### How the 0.5mm-pitch fanout was solved

This is the thing that got USB-C deferred out of v2. The escape works because
the connector is a **single-row 12-position** footprint, so nothing needs a
diagonal via fan-out — but D+ and D− still interleave
(`… B6/DP2 · A7/DN1 · A6/DP1 · B7/DN2 …`), so the two duplicate pairs cross.

The crossing is resolved **without a single via**:

* **UDP** (34.75 and 35.75) is shorted *behind* the pad row, at y ≈ 8.9.
* **UDM** (35.25 and 36.25) is shorted *in front of* the pad row, at y ≈ 6.95,
  under the connector's plastic pin block. Safe: the pad row itself already
  extends 0.33mm under the body outline, so nothing conductive presses down
  there, and the trace is under solder mask.

0.20mm tracks out of the 0.30mm pads leave 0.25mm to each neighbouring pad,
against a 0.15mm rule — that's what the `USB_C` net class is for. VBUS keeps
its own 0.40mm class (0.80mm cannot escape a 0.60mm pad).

CC1 drops straight down 1.9mm into R8; CC2 straight down into R9.

### Zone clearance change

hub_v2's pours used a 0.35mm zone clearance and a 0.25mm minimum neck. With
more copper pushed through the middle of the board, that pinched the F.Cu pour
into islands around U2 pad 1 and C5 pad 2 that no stitching via could reach.
Pours are now 0.25mm / 0.20mm — still above the 0.20mm netclass clearance and
far above JLC's 0.127mm minimum. F.Cu is a single connected region again.

---

## Everything else (unchanged from hub_v2)

- ESP32-WROOM-32E top-left, antenna keepout (x 6.5–25.5, y 1–9.2) copper-free
  and still enforced — the USB-C sits at x ≥ 30.1 and does not encroach.
  Espressif's *full* keepout is unsatisfiable on an 88×60 outline; the
  board-level one is the rule that is checked and it passes.
- CH340C USB-UART, TP4056 charger + SMT 18650 holder — **USE A PROTECTED
  CELL**, there is no DW01 on the board.
- AMS1117-3.3, SS34 diode-OR (VBUS/VBAT → VSYS), PCM12 slide switch (right
  edge), EN + BOOT tactile buttons, power + charge LEDs.
- **No autoboot transistors.** First flash: hold BOOT, tap EN, release BOOT,
  then upload. Everything after that is OTA.
- LED_5V = VSYS, no boost.
- J1 (2×6, top right): inner row /PL CP SER +5V(VSYS) +3V3 LED_DATA, outer row
  all GND.
- GPIO map: /PL=25, CP=26, SER=14, LED_DATA=27 via a 74AHCT1G125 buffer.

### Net classes (`chess_hub_v3_usbc.kicad_pro`)

| Class | Nets | Track | Clearance | Via |
|---|---|---|---|---|
| Default | signals | 0.30mm | 0.20mm | 0.6/0.3 |
| Power | GND, VSYS, BATP, VSW, +3V3 | 0.80mm | 0.20mm | 0.8/0.4 |
| VBUS | VBUS | 0.40mm | 0.20mm | 0.6/0.3 |
| USB_C | UDP, UDM, CC1, CC2 | 0.20mm | 0.15mm | 0.6/0.3 |

Board minimums: 0.15mm clearance, 0.20mm track, 0.30mm hole, 0.50mm copper-to-edge.

---

## Parts (new lines only)

| Ref | Value | Footprint | LCSC | JLC library | Price |
|---|---|---|---|---|---|
| USB1 | USB-C | `USB_C_Receptacle_HRO_TYPE-C-31-M-12` | **C165948** | Extended | **$0.185 @1, $0.103 @1k** (≈₹16 each at qty 5) |
| R8, R9 | 5k1 | `R_0603_1608Metric` | **C23186** | Basic | ~$0.002 |

**There is no Basic-library USB-C receptacle at JLCPCB** — a search of their
base library returns zero Type-C parts, so any USB-C here is an Extended part.
C165948 is "Economic and Standard" assembly eligible, 300k+ in stock.

Cheaper drop-in candidate: **C2765186** (SHOU HAN `TYPE-C 16PIN 2MD(073)`,
$0.074 @1, 1M+ stock, also Economic-eligible). Same 16-pin single-row family,
but **check its shield-leg hole positions against this footprint before
substituting** — this board is drawn to the HRO 31-M-12 land pattern.

Net cost delta vs hub_v2: about **+$0.19 per board** (connector + 2 resistors,
minus the micro-USB you no longer buy), plus one more unique part on the feeder.

---

## How it was built

```
KP=~/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3.9

cp -R pcb/hub_v2 pcb/hub_v3_usbc          # then rename chess_hub_v2.* -> chess_hub_v3_usbc.*
$KP ../swap_usbc_v3.py                     # micro-USB out, USB-C + R8/R9 in, rip up all copper
$KP -c "import pcbnew; b=pcbnew.LoadBoard('chess_hub_v3_usbc.kicad_pcb'); \
        pcbnew.ZONE_FILLER(b).Fill(b.Zones()); b.Save('chess_hub_v3_usbc.kicad_pcb'); \
        pcbnew.ExportSpecctraDSN(b,'/tmp/hubc.dsn')"
java -jar freerouting-1.9.0.jar -de /tmp/hubc.dsn -do /tmp/hubc.ses -mp 30
$KP ../route_hub_v3.py /tmp/hubc.ses       # import, 3mm GND stitch grid, refill, emit CSVs
$KP ../stitch_gnd_v3.py                    # loosen pours to 0.25/0.20, stitch the last islands
$KP ../fix_silk_v3.py                      # pull USB1 silk off the board edge, move ref fields
```

FreeRouting **1.9.0**, not 2.x — the 2.x jars need Java 25 and the JDK here is
Temurin 21. Auto-route took 0.9s, optimisation 12s.

Gerbers:

```
CLI=~/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
$CLI pcb export gerbers --output gerbers/ \
     --layers "F.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts" \
     chess_hub_v3_usbc.kicad_pcb
$CLI pcb export drill --output gerbers/ --format excellon --drill-origin absolute \
     --excellon-units mm --excellon-zeros-format decimal chess_hub_v3_usbc.kicad_pcb
$CLI pcb drc --severity-error --format json -o /tmp/drc.json chess_hub_v3_usbc.kicad_pcb
```

### Do not re-run `../generate_hub_v2.py`

It has a DO-NOT-RUN header and four known bugs, and it targets `hub_v2/`
anyway. All hub edits go through load/modify/save scripts like the three above.

## Remaining DRC warnings (4, all cosmetic)

SW1 and BT1 footprint silkscreen crosses the board outline — both parts
overhang the edge by design (switch actuator, battery holder body). JLC clips
silk at the edge. Identical to hub_v2.

## Order at JLCPCB

1. Zip `gerbers/`, upload at jlcpcb.com/quote. 88×60mm, 2-layer, 1.6mm, qty 5.
2. Enable PCB Assembly (economic, top side). Upload `BOM.csv` + `positions.csv`.
   J1 and BT1 are through-hole and are deliberately left out of
   `positions.csv` — fit them by hand or pay for THT assembly.
3. **Check rotations in the placement preview**: U1 pin 1, U2/U3 pin 1,
   D1/D2 cathode band, LED1/LED2 polarity, and **USB1 — it is placed at 180°**,
   mouth toward the board's top edge. JLC's rotation convention differs from
   KiCad's; a flipped USB-C is a dead board.
4. BOM lines with no LCSC number, pick in their picker: BT1 (Keystone
   1042-compatible SMT 18650 holder), J1 (2×6 2.54mm shrouded box header),
   SW1 (PCM12 SPDT slide switch), SW2/SW3 (PTS645 6mm tactile).
5. Enclosure note: the receptacle mouth sits 0.25mm inside the top board edge,
   so the case cutout must be flush with that edge — the plug body cannot be
   recessed behind it.
