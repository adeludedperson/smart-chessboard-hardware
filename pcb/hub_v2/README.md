# Hub V2 — 88×60mm, ESP32 + Micro-USB + CH340C + TP4056 + 18650

**Status: DONE, DRC-clean.** 0 errors, 0 unconnected items
(`drc_hub.json`). 178 tracks + 340 vias, 2-layer, GND pour both sides.
Gerbers + drill in `gerbers/`, ready to zip and upload.

## What's on it

- ESP32-WROOM-32E (top-left, antenna keepout kept copper-free), Micro-USB
  (top edge — v0 choice; USB-C needs a diagonal fanout), CH340C USB-UART.
- TP4056 charger + 18650 holder (bottom half) — **USE A PROTECTED CELL**
  (there is no DW01 on the board), AMS1117-3.3, SS34 diode-OR (VBUS/VBAT →
  VSYS), PCM12 power slide switch (right edge), EN + BOOT buttons.
- **No autoboot transistors.** Flash manually: hold BOOT, tap EN, release
  BOOT, then upload. After that use OTA, which the firmware already supports.
- LED_5V = VSYS (no boost). LEDs are slightly dimmer on battery; still in
  spec for WS2812C-2020-V1.
- J1 (2×6, top right) mirrors the quadrant pinout: inner row
  /PL CP SER +5V(VSYS) +3V3 LED_DATA, outer row all GND.
- GPIO map: /PL=25, CP=26, SER=14, LED_DATA=27 via a 74AHCT1G125 buffer.

## How it was routed

The generator got placement + ~90% of the copper down but left structural
defects behind (see below). The board was repaired and then fully
auto-routed. Three scripts, run in this order:

```
KP=~/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3.9

$KP ../fix_hub_v2.py                       # repair placement, rip up old copper
$KP -c "import pcbnew; b=pcbnew.LoadBoard('chess_hub_v2.kicad_pcb'); \
        pcbnew.ZONE_FILLER(b).Fill(b.Zones()); b.Save('chess_hub_v2.kicad_pcb'); \
        pcbnew.ExportSpecctraDSN(b,'/tmp/hub.dsn')"
java -jar freerouting-1.9.0.jar -de /tmp/hub.dsn -do /tmp/hub.ses -mp 30
$KP ../route_hub_v2.py /tmp/hub.ses        # import, stitch GND, refill, emit CSVs
```

FreeRouting **1.9.0**, not 2.x — the 2.x jars are built for Java 25 and the
JDK here is Temurin 21. Get it from the freerouting GitHub releases.

`route_hub_v2.py` also drops ~320 GND stitching vias on a 3mm grid (clearance-
and hole-to-hole-checked, and kept out of the antenna area), then hunts down
any leftover isolated F.Cu pour fragment and stitches it to the back plane.

### Net classes (in `chess_hub_v2.kicad_pro`)

| Class | Nets | Track | Via |
|---|---|---|---|
| Default | signals | 0.30mm | 0.6/0.3 |
| Power | GND, VSYS, BATP, VSW, +3V3 | 0.80mm | 0.8/0.4 |
| VBUS | VBUS | 0.40mm | 0.6/0.3 |

VBUS gets its own class because 0.8mm cannot escape the 0.65mm-pitch
micro-USB pad. 0.4mm on 1oz copper still carries the TP4056's 1A with
under 10°C rise.

## What the repair pass changed (`../fix_hub_v2.py`)

1. **U1 antenna keepout.** The stock KiCad ESP32-WROOM-32E footprint carries
   Espressif's full 48×21mm antenna keepout *and* a matching courtyard. With
   the module inline at the top edge of an 88×60 board that region is
   un-satisfiable, and it swallowed USB1 whole (26 DRC errors). The footprint
   keepout and its oversized courtyard were deleted; the explicit board-level
   rule area over the antenna itself (x 6.5–25.5, y 1–9.2) is the rule that
   is actually enforced, and it is respected — no copper there at all.
   *Trade-off:* the antenna radiates over a board with a copper-free window
   rather than off the board edge. Fine for a 2m link to a phone/router;
   if range disappoints in v1, notch the board under the antenna.
2. **C1/C2 were underneath the U1 module body** → moved to the left column
   (x 2.6). The WROOM sits flat on the host PCB; nothing fits under it.
3. **D1 (SS34) pad 1 was shorting SW3 pad 2** and bridging C8's solder mask
   → moved to (56, 11).
4. **U3 (TP4056), R5, C5, C6 were underneath the 18650 cell** → moved up
   into the y 32–37 band. The Keystone 1042 holder spans the whole board
   width from y 38.6 down.
5. **U4 nudged to (16, 32)** to clear the U1 courtyard.
6. **USB1 down 0.25mm** — its shield legs were 0.35mm from the board edge
   against a 0.5mm rule.
7. **U1 pad 39 stitching holes 0.2mm → 0.3mm** (board minimum is 0.3mm,
   which is also JLC's standard).
8. **GND pours: thermal reliefs → solid pad connection**, killing the
   starved-thermal errors. JLC reflows these; thermals bought nothing.
9. **SW1's value was "PWR", same as LED2**, so the BOM generator handed the
   slide switch the LED's LCSC number. Renamed to `PWR_SLIDE`, LCSC left
   blank — pick it in JLC's part picker.
10. The old +3V3 corridor ran along y = −0.7, i.e. **off the board**, and a
    second one ran straight through the antenna keepout. All of it was
    ripped up and re-routed.

## Remaining DRC warnings (4, all cosmetic)

SW1 and BT1 footprint silkscreen crosses the board outline. Both parts
overhang the edge by design (switch actuator, battery holder body). JLC
clips silk at the edge; nothing to do.

## Order at JLCPCB

1. Zip `gerbers/`, upload at jlcpcb.com/quote. 88×60mm, 2-layer, 1.6mm.
2. Enable PCB Assembly (economic, top side). Upload `BOM.csv` +
   `positions.csv`. J1 and BT1 are through-hole and are deliberately left
   out of `positions.csv` — fit them by hand or pay for THT assembly.
3. **Check rotations in the placement preview**: U1 pin 1, U2/U3 pin 1,
   D1/D2 cathode band, LED1/LED2 polarity. JLC's rotation convention differs
   from KiCad's.
4. BOM lines with no LCSC number, pick in their picker: BT1 (Keystone
   1042-compatible SMT 18650 holder), J1 (2×6 2.54mm shrouded box header),
   SW1 (PCM12 SPDT slide switch), SW2/SW3 (PTS645 6mm tactile), USB1
   (Wuerth 629105150521-compatible micro-USB, or swap the footprint).

## Do not re-run the generator

`../generate_hub_v2.py` produced the first draft, but the board has since
moved ahead of it: the placement fixes and the whole routing live in the
`.kicad_pcb`. Re-running it **overwrites this board**. If you ever need to
regenerate, port the `MOVES` table out of `../fix_hub_v2.py` into the
generator's placement section first.

A backup of the pre-repair board is at `chess_hub_v2.kicad_pcb.bak`.
