# Smart Chessboard PCB — V2 "Compact" Design Spec

**Status:** Draft. Goal: 30×30cm portable board, factory-assembled electronics,
**zero soldering and zero loose wiring at home**. Everything SMT, JLCPCB PCBA.

**Hard requirements (from v1 lessons):**
1. Full-square triggering — no "place piece on the circle." Fixed by smaller
   squares + sensitive omnipolar sensor + wider magnet.
2. LEDs on-board — opponent moves, promotion picker, errors shown on the board.
3. No-solder assembly — keyed plug connectors only. No Dupont jumpers (loose),
   no solder bridges.
4. Battery powered, USB charged (Micro-USB in v0, USB-C in v1).
   True portable.

---

## Geometry

- `SQUARE_SIZE = 33mm` (Chessnut Air uses 35mm; 33 keeps playfield at 264mm)
- Quadrant PCB: **132×132mm**, 4×4 squares, board outline = 4 × SQUARE_SIZE
  exactly (quadrants butt together under the playfield)
- Full playfield: 264×264mm. Enclosure ~300×300mm with border.
- Pieces: ~30mm base, king ~65mm, **12×2mm N52 magnet** glued in base
  (wider + flatter than v1's 10×3 = bigger trigger footprint, any orientation)

## Boards in the order (2 designs, one JLCPCB cart)

### Design A — Quadrant ×16 (4 per board × 4 board-sets... order 20 for spares)

All SMT, top side (faces the acrylic above). 2-layer, 1.6mm FR4.

Per-square cell (×16):
- **Hall sensor at exact square center**: UHE4913G-AE3-R
  (LCSC C86815, ~$0.05, SOT-23, omnipolar, push-pull, 2.4–5.5V).
  Omnipolar = magnet polarity doesn't matter (v1's A3144 gotcha eliminated).
  VERIFIED by field simulation (2026-08-31): with 12×2 N52
  magnet, worst-case chip (BOP 5.0mT) detects at ~10mm lateral radius at any
  gap 4–10mm. Sensor MUST be at square center — 30mm piece base in 33mm square
  keeps the magnet within ~8mm of center → full-square trigger with margin.
  Adjacent square (33mm) delivers <0.7mT, 2× below worst-case release point →
  cross-talk impossible.
  Push-pull output → drives 74HC165 input directly, **no pull-up resistors**
  (64 resistors deleted vs v1).
- **LED offset 8mm diagonal from center**: WS2812C-2020-V1 (LCSC C2976072,
  ~$0.08). Frosted acrylic diffuses it — offset invisible in practice.
  (LED cedes center to the sensor: detection physics beats aesthetics.)
- 100nF 0603 decoupling per sensor + per LED (X7R, ~$0.0025 each).

Digitizing (same proven v1 architecture):
- 2× 74HC165 SOIC-16 per quadrant (SN74HC165DR clone, LCSC C22384789, ~$0.06),
  chained across quadrants → one 64-bit chain, 4 GPIO reads whole board.
  VCC 3.3V; sensors also run at 3.3V (UHE4913G is 2.4–5.5V) →
  **single 3.3V logic domain, level shifting only for LEDs.**

LED chain:
- WS2812 data daisy-chains through all 16 LEDs, exits to next quadrant via the
  interconnect. LEDs run on 5V rail; data comes level-shifted from hub.
- 1000µF bulk cap per quadrant on the 5V LED rail (footprint for SMT
  electrolytic, JLC-assembled).

Interconnect (the no-solder requirement):
- J1 (IN, top edge) / J2 (OUT, bottom edge): **2×6 shrouded/keyed box headers,
  2.54mm**, JLC-assembled. Inner row carries signals (/PL, CP, SER, 5V, 3V3,
  LED_DATA), outer row all GND — every signal rides over a ground, and the
  all-GND row needs zero routing (pour connects it).
- Quadrants join with **pre-made 12-way IDC ribbon jumpers** — keyed, click in,
  cannot be plugged backwards, cannot work loose. Buy ready-made (AliExpress,
  ~₹30-50 each) or crimp once with a ₹300 vise tool.
- Chain Q1→Q2→Q3→Q4 with alternating 180° board rotation so J2 meets the next
  J1 at each seam.
- STATUS: **quadrant layout DONE and DRC-clean** — see quadrant_v2/README.md.

### Design B — Hub ×5 (**88×60mm**, 2-layer)

Everything that was v1's Mac-mini-adjacent perfboard, now one assembled PCB.
STATUS: **layout DONE and DRC-clean** (0 errors, 0 unconnected) — see
hub_v2/README.md.

- ESP32-WROOM-32E module (C701341, ~$2.79) — module directly on PCB,
  JLC-assembled. No dev board. The antenna sits top-left over a copper-free
  keepout window; the module does not overhang the board edge in v0.
- **Micro-USB port, not USB-C** — charging + serial flash, CH340C USB-UART
  on board. USB-C was dropped for v0: its 0.5mm-pitch dual-row footprint
  needs a diagonal fanout the generator could not produce. Revisit in v1.
- TP4056-class Li-ion charge IC + **SMT 18650 holder** (Keystone 1042 style).
  There is **no protection IC on the board**, so the cell must be a
  **protected 18650**. Cell bought locally (lithium can't ship installed),
  clicks in like a TV remote.
- **LED_5V = VSYS, no boost.** VSYS is a diode-OR (2× SS34) of VBUS and the
  battery, so the LED rail is ~5V on USB and ~3.7–4.2V on battery. That is
  in spec for WS2812C-2020-V1; the LEDs are simply a little dimmer on
  battery. MT3608 boost deferred to v1 if brightness disappoints.
- SN74AHCT1G125 buffer: 3.3V ESP32 data → 5V-clean WS2812 data.
- J1: 2×6 keyed box header → ribbon to Quadrant 1 (inner row /PL CP SER
  +5V(VSYS) +3V3 LED_DATA, outer row all GND).
- **PCM12 slide power switch on the right edge**, EN + BOOT tactile buttons,
  power LED + charge LED.
- **No autoboot transistors.** The DTR/RTS auto-reset pair was dropped, so
  the first flash is manual: hold BOOT, tap EN, release BOOT, upload. Every
  flash after that is OTA, which the firmware already supports.

## Home assembly procedure (target: 1 evening, no iron)

1. Screw 4 quadrants + hub onto MDF base plate (M2 standoffs, pre-drilled).
2. Click 4 ribbon jumpers: hub→Q1→Q2→Q3→Q4.
3. Insert 18650 cell into holder.
4. Flash firmware over Micro-USB: hold BOOT, tap EN, release BOOT, then run
   the upload. Everything after that is OTA.
5. Glue 34 magnets into piece bases (use a tape-strip jig; polarity
   doesn't matter — omnipolar).
6. Drop UV-printed frosted acrylic top onto the frame, screw corners.

Total solder joints performed at home: **0**.

## Enclosure (India-sourced, ~₹450)

- Base: 4mm MDF laser-cut 300×300 with standoff holes (₹50/sqft)
- Frame walls: laser-cut MDF ring, ~20mm total stack height
- Top: 3mm frosted acrylic, UV-printed 33mm checkerboard + coordinates
  (acrylic ₹60/sqft + UV print ₹46–80/sqft)
- 2–3mm air gap between LED and acrylic for diffusion

## Cost (verified pricing, order of 5 board-sets)

| | ₹/board |
|---|---|
| Quadrant PCBs (JLCPCB $47/20, verified) | 790 |
| Hub PCB + assembly | ~400 |
| Parts (sensors ₹280, LEDs ₹450, regs ₹40, ESP32 ₹240, passives ₹45, charge+holder ₹150) | 1,205 |
| Quadrant assembly fees (setup+stencil+joints, split ÷5) | 500 |
| Ribbons, standoffs, switch | 150 |
| Shipping ($26.45 ÷ 5) + customs (~38%, estimate) | 1,400 |
| India: acrylic+print, MDF, magnets (AliExpress 12×2), pieces, protected 18650, USB brick | 1,500 |
| **Per finished board** | **≈ ₹5,900** |

## Deltas vs v1 (what changed and why)

| v1 | v2 | Why |
|---|---|---|
| A3144 TO-92 through-hole, unipolar | UHE4913G SOT-23 SMT, omnipolar | Full-square trigger, no polarity errors, machine-assembled, 4× cheaper |
| 64× 10k pull-ups | none | push-pull sensor output |
| No LEDs (scope cut) | WS2812C-2020 per square | opponent moves, promotion picker on-board |
| 10×3mm magnets | 12×2mm N52 | wider/flatter field cone |
| 57mm squares, 460mm board | 33mm, 300mm | portable; smaller square = better sensor coverage |
| ESP32 dev board on perfboard hub | ESP32 module on assembled hub PCB | no hand wiring |
| 1×6 unkeyed headers + Dupont | 2×5 keyed IDC ribbons | can't misplug, can't work loose |
| 5V 5A wall SMPS | 18650 + Micro-USB charge | portable |
| Mac-mini daemon (unchanged for now) | same | port to phone/ESP32 later; not a v2 goal |

## Open items before layout

1. ~~LED rail: direct Li-ion vs boost~~ DECIDED for v0: direct VSYS, no
   boost. Still worth a brightness/colour-shift check with one LED on a
   breakout before committing to five board sets.
2. ~~Sensor coverage~~ RESOLVED by simulation: sensor at center, ~10mm
   worst-case detect radius, no cross-talk. Optional enhancement if edge cases
   appear in testing: 12×1mm soft-iron disc glued at each square center under
   the acrylic (OpenChess-proven flux concentrator; also self-centers pieces
   with a satisfying magnetic snap). ~₹250/board, adds 64-disc gluing step —
   deferred, not in base build.
3. Keep magnet→sensor gap in the 5–8mm band (acrylic 3mm + air 2–3mm + piece
   base wall). Below 4mm the detect radius *shrinks* (peaky field); above 10mm
   margins thin.
4. Battery life target: 64 LEDs mostly-off + ESP32 WiFi ≈ 80–150mA avg →
   ~15–25h on 2500mAh. BLE port later doubles this.
5. Promotion picker + LED UX = firmware and app work, tracked with the app.
