# RFID 2×2 Test Rig — locked build plan

Every design decision below is final. The board is produced by a pcbnew
generator (`generate_rfid_rig.py`) that implements this plan, iterated to
0 DRC errors / 0 unconnected, then exported to gerbers/BOM/positions.

## Corrections vs DESIGN_V3_RFID.md (decided)

1. **LED cannot sit at +8/+8** — that point is inside the square-annulus coil
   band (band = 5.875 ≤ max(|x|,|y|) ≤ 15.0 mm rel square center). LED moves
   to the inner clear zone at rel (0, +3.9).
2. **4 spiral layers is unroutable** (centered hall could never escape).
   "4-layer antenna" = spirals on **In1 + In2 + B.Cu** (18t each, 54 turns
   series). Predicted L ≈ 83 µH (Wheeler, n=54), tank ≈ 19.6 nF → fit
   2× 10 nF C0G. F.Cu stays component/crossing layer everywhere.
3. **2-layer antenna candidate** = spiral on **B.Cu only**, 16t, 30/14 mm
   (outer half-side 14.875, pitch 0.5) → L ≈ 8.3 µH, tank ≈ 195 nF → fit
   2× 100 nF C0G (README: provisional, refit after L measurement).
4. With these L values V_ANT(peak) computes to ~8 V (83 µH) — mux swing risk
   is far below the doc's 69 V worst case. Zener clamps stay (belt+braces).

## Board

- 80 × 92 mm, **4-layer** (F.Cu, In1.Cu, In2.Cu, B.Cu), clearance 0.15 mm,
  track 0.3 sig / 0.5 pwr, via 0.6/0.3, spiral track 0.25/gap 0.25.
- Square centers: S1 (23.5,20.5), S2 (56.5,20.5), S3 (23.5,53.5), S4 (56.5,53.5).
  S1,S2 = stacked 3-layer coil (83 µH candidate). S3,S4 = B-only coil (8.3 µH).
  S2,S4 are **x-mirrored** layouts (ports face right margin).
- Strip y=70..92 holds EM4095 + muxes + clamps + headers. Margins x<8.5,
  x>71.5, channel y 35.5..38.5 and top y<5.5 are routing corridors.
- GND zone on **F.Cu only**, whole board, with 4 zone-only keepout squares
  (half-side 15.4 per square center) so no pour sits over/inside any coil.
  Thermal relief, min width 0.25.

## Coil construction (per square, all coil copper = net A<n>)

Square spiral point sequence (half-side r0, pitch p=0.5, n turns), drawn as
track segments; start at outer corner (+r,+r), spiral inward:
`pts=[(+r,+r)]; for i in n: ri=r0-i*p; rn=ri-p; pts += [(-ri,+ri),(-ri,-ri),(+ri,-ri),(+ri,+rn)]`

S1/S2 stacked coil, series chain (one net):
- **In1**: normal geometry, r0=14.875, 18t. Outer stub on In1 from
  (14.875,14.875) → (16.2,14.875); **via** there = HOT connection to F.Cu.
- **In2**: **y-mirrored** geometry (y→−y), r0=14.875, 18t. Outer corner is
  (14.875,−14.875); stub on In2 → (16.1,−16.1); **via**.
- **B**: normal, r0=14.375 (0.5 inset), 18t. Outer stub on B east to
  (16.1,14.375), then a single B.Cu line north along x=16.1 to (16.1,−16.1)
  meeting the In2 via. (Path is outside the band, |x|>15.)
- Inner series link In1↔In2: In1 stub (6.375,5.875)→(4.4,5.5) + via at
  (4.4,5.5); In2 routes on its own layer from its inner end (6.375,−5.875)
  straight to that via (In2 is empty in the inner zone).
- B inner end (5.375,4.875-ish) → stub on B to (−4.3,−5.5)? NO — B inner end
  routes on B.Cu (inner zone free) to via at **(3.4,−2.0)**, then F.Cu stub to
  cold jumper pad1. Traversal order HOT→In1(out→in)→In2(in→out)→B(out→in)→cold
  gives matched chirality on all layers (mirror+reversal cancel) — flux adds.
- S3/S4 coil: B only, r0=14.875, 16t; outer stub on B → (16.1,14.875), via =
  HOT; inner end → B.Cu to via (3.4,−2.0) → F stub → jumper pad1.
- Mirrored squares (S2,S4): negate x of ALL coil geometry and via points.

HOT drops (F.Cu verticals to strip): S1 x=40.6, S2 x=73.6, S3: jog west to
x=37.2 then down, S4: jog west to x=68.5. (From each square's hot via, short
F jog to the lane, then straight down to its clamp cluster at y≈71.5.)

## Inner zone per square (rel coords; mirror x for S2/S4)

- Hall UHE4913G SOT-23 @ (0,0) **rot 0**: OUT (−0.94,−0.95), VDD (−0.94,+0.95),
  GND (+0.94,0). Nets: OUT=SENS<n>, VDD=+3V3, GND=GND.
- LED WS2812 @ (0,+3.9) **rot 270**: DOUT (−0.55,4.815), GND (0.55,4.815),
  DIN (0.55,2.985), VDD (−0.55,2.985). (Verify pad numbers→positions at
  runtime via pad_xy; intent: DOUT/GND south row, DIN/VDD north row, chain
  nets LEDD<k> per the chain below.)
- Cold jumper R 0Ω 0603 @ (2.6,−2.0) rot0: pad1 (1.825,−2.0)=A<n> ← via
  (3.4,−2.0)? place via at (3.9,−2.0) east of pad2 — ACTUALLY: pad2
  (3.375,−2.0)=A<n> ← F stub ← via (4.2,−2.0); pad1 (1.825,−2.0)=GND → F stub
  west y=−2.0 to (−0.2,−2.0)?? — NO: pad1=GND routes EAST is blocked; route
  pad1 GND: seg from pad1 down to (1.825,−0.9)?? — SIMPLER, FINAL: jumper @
  (−2.6,−3.9) rot0: pad1 (−3.375,−3.9)=GND, F seg west y=−3.9 out through the
  band to x=−16.0 (W ring, zone territory, mirrored squares: east). pad2
  (−1.825,−3.9)=A<n>, F seg east y=−3.9 to (4.2,−3.9), via @ (4.2,−3.9), B.Cu
  from via to coil inner end. That west GND seg doubles as the zone stitch.
  Check it clears hall pads (y −0.95 row: 2.9 mm away ✓) and LED (north ✓).
- Port crossings (F.Cu straight lines through the band; abs = center+rel):
  - W port SENS: horizontal y=−0.95 from x=−16.5 to hall OUT pad (−1.68 edge).
  - W port 3V3: horizontal y=+0.95 to hall VDD pad.
  - W port 5V: horizontal y=+2.985 to LED VDD pad west edge (−0.9).
  - E port GND: horizontal y=0 from hall GND pad (+1.68) east to x=+16.0
    (ends in zone ring; zone connects).
  - S port DOUT: vertical x=−0.55 from LED DOUT pad south edge to y=+16.5.
  - S port GNDled: vertical x=+0.55 from LED GND pad to y=+15.9 (zone ring).
  - S port DIN: vertical x=+2.2 from y=+16.5 up to y=+2.985, then west to
    DIN pad east edge (+0.9).
  (Mirrored squares: mirror everything; W↔E.)

## Nets

+5V, +3V3, GND, ANT_DRV, DEMOD_IN, DEMOD_OUT, RDY_CLK, SHD, S0, S1, EN0,
EN1, A1..A4 (coil+hot+tank+clamp-top+mux-channel), AM1..AM4 (zener midpoints),
SENS1..SENS4, LEDD0..LEDD4 (chain: J1 → S3 → S1 → S2 → S4; LEDD4 = S4 DOUT,
single-pad net, unrouted).

## Strip components & circuit

- **U1 EM4095 SOIC-16 @ (14,79) rot0.** Pinout (verify vs datasheet PDF and
  note in README): 1 VSS, 2 RDY/CLK, 3 ANT1, 4 DVDD, 5 DVSS, 6 ANT2, 7 VDD,
  8 DEMOD_IN, 9 CDEC_OUT, 10 CDEC_IN, 11 AGND, 12 MOD, 13 DEMOD_OUT, 14 SHD,
  15 FCAP, 16 DC2. ANT2→GND (single-ended, coil cold legs grounded),
  MOD→GND, VSS/DVSS→GND.
- **R1 33Ω 0805 @ (8.5,73.2)**: pad2 (east)=ANT1 wired to U1 pin3 (route
  around U1 north/west, clear of pads); pad1 (west)=ANT_DRV.
- ANT_DRV: from R1 pad1 west/south to **C_dv1 47pF @ (5.4,76.0) r90** pad1;
  and separately north to y≈71.6 then east (F) to the mux Z tie (below).
- **C_dv1 pad2 = DEMOD_IN** → south on x=5.4 to y=83.4 → east to U1 pin8.
  **C_dv2 1.5nF @ (7.6,85.2) rot0**: pad1 taps the DEMOD_IN run, pad2 GND.
- **C_dec 100nF @ (19.4,83.4) r90** pads diag-linked to pins 9/10.
  **C_agnd 220nF @ (19.4,80.9) rot0** pad1→pin11, pad2→GND stub east.
  **C_dc2 6.8nF @ (19.4,74.9) rot0** pad1→pin16 (16.475,74.555), pad2 GND.
  **C_fcap 10nF @ (19.4,76.4)? rot0** pad1→pin15, pad2 GND — adjust y to
  clear each other, DRC decides.
  **C_vdd 100nF @ (14,73.0) rot0** VDD(pin7 left col!)—pin7 is at
  (11.525,81.905)... place C_vdd @ (8.2,81.9) instead, pad2=+5V feed, pad1
  wait — put VDD cap adjacent to pin7 on the west side, GND pad into zone.
  **C_dvdd 100nF** adjacent to pin4 (11.525,78.365) west side. Exact spots:
  worker's choice, west of U1, DRC-clean.
- +5V to U1 VDD/DVDD: short F runs on the west side from the 5V spine
  (see power section).
- **U2 74HC4851 TSSOP-16 @ (32,79) rot0**, **U3 @ (48,79) rot0**.
  4051-family pinout: 1 Y4, 2 Y6, 3 Z, 4 Y7, 5 Y5, 6 /E, 7 VEE, 8 GND,
  9 S2, 10 S1, 11 S0, 12 Y3, 13 Y0, 14 Y1, 15 Y2, 16 VCC.
  U2: Y0=A1, Y1=A3, /E=EN0. U3: Y0=A2, Y1=A4, /E=EN1. S2→GND both.
  S0/S1 shared. VEE→GND, GND→GND, VCC=+3V3 (so 3.3V ESP32 drives select
  lines legally; flat-pass handles the swing). 100nF at each VCC.
  Z tie: U2 pin3 + U3 pin3 → ANT_DRV: F stub north from each pin3 to y≈76.6,
  via, B.Cu horizontal y=76.6 between them, and B.Cu/F west to the ANT_DRV
  run from R1. Unused Y channels: leave unconnected (note in README).
- **Clamp/tank clusters** per antenna at drop lane bottom (x = drop lane):
  tank caps C0G 0805 r90 @ (x−1.3, 72.3) and (x+1.3, 72.3): top pads=A<n>
  stubbed to the lane, bottom pads=GND (zone). Zeners SOD-523:
  D<n>a r90 @ (x−1.3,74.8): pad1(K, top)=A<n> stub to lane, pad2(A)=AM<n>;
  D<n>b r270 @ (x+1.3,74.8): pad2(A, top)=AM<n> (diag seg to D<n>a pad2),
  pad1(K, bottom)=GND (zone). Lane continues from y=74.1 to the mux feed:
  A1 (40.6): → (40.6,78.675) → west to U2 pin13. A3 (37.2): → (37.2,78.025)
  → west to U2 pin14. A2 (73.6): → (73.6,78.675) → long west run to U3
  pin13. A4 (68.5): → (68.5,78.025) → west to U3 pin14.
  Tank values: S1/S2 clusters 2×10nF; S3/S4 clusters 2×100nF.
- **J1 1×12 THT @ (8,88.5) rot270** (pads run east, pitch 2.54):
  1 +5V, 2 GND, 3 +3V3, 4 RDY_CLK, 5 SHD, 6 DEMOD_OUT, 7 LED_IN(LEDD0),
  8 EN0, 9 S0, 10 S1, 11 EN1, 12 GND.
- **J2 1×6 THT @ (58,88.5) rot270**: 1 SENS1, 2 SENS3, 3 SENS4, 4 SENS2,
  5 GND, 6 GND.
- **Test points** (TestPoint_Pad_D1.5mm, F.Cu): ANT_DRV, DEMOD_OUT, RDY_CLK,
  SHD near U1/J1; one per A<n> next to each cluster (net A<n>); place clear
  of routes, DRC decides exact spots.
- Per-side decoupling for hall/LED rails (rig-grade, note in README):
  2× 100nF 0603 near (6,64) left margin (one 3V3-GND, one 5V-GND) and
  2× near (74,64) right margin.

## Routing conventions (critical — this is how it stays clean)

- **F.Cu**: all horizontal-ish runs, ALL band crossings (ports), inner-zone
  stubs, strip short hookups. **B.Cu**: long verticals in margins/strip and
  the designated B runs listed below. Vias at every layer turn.
- Left margin B verticals (top of board down to strip): x=2.0 SENS3,
  x=2.6 +5V, x=3.3 +3V3, x=4.0 SENS1, x=4.7 LEDD1 (S3-DOUT→S1-DIN link).
- W-port F horizontals for S1/S3 tap those verticals through vias at the
  port y. S3 taps the same 5V/3V3 verticals en route (same net).
- LEDD1 path: S3 DOUT S-port F vert (x=22.95) down to via (22.95,70.8) →
  B west y=70.8 → B north x=4.7 → B east y=37.0 (channel) → via (25.7,37.0)
  → F north x=25.7 through S1's band → west at y=2.985+20.5 to S1 DIN pad.
  Wait — S1 DIN port is S-side x=cx+2.2=25.7 ✓ consistent.
- Right margin B verticals: x=76.7 LEDD3 (S2-DOUT→S4-DIN: from S2 DOUT S-port
  via at (57.05,37.1) B east y=37.1 → B south x=76.7 → B west y=69.0 →
  via (54.3,69.0) → F north x=54.3 to S4 DIN), x=77.4 +3V3, x=78.1 +5V.
  E-port F horizontals for S2/S4 tap via vias at port y.
- SENS2/SENS4 exit E ports and stay on F: SENS4 → F east to x=78.4 → F south
  → F west lane y=86.9 → J2 pad3. SENS2 → F east to x=79.6 → F south → F west
  lane y=87.3 → J2 pad4. (Nesting verified: SENS4's vertical ends at 86.9,
  so SENS2's 87.3 lane clears it.)
- SENS1: via (4.0,85.9) → F east lane y=85.9 → x=58 → south into J2 pad1.
  SENS3: via (2.0,86.4) → F east lane y=86.4 → x=60.54 → J2 pad2.
- J1 signals: B verticals at their pad x-columns: RDY pin2 → F stub between
  U1 pad columns → via (14.8,75.8) → B to pad4 col; SHD pin14 → via
  (18.16,77.1) → B down; DEMOD_OUT pin13 → F to (20.7,78.4) → via → B down;
  EN0 → B up x=25.78 to via ~(25.78,75.5)?? then F to U2 pin6 west col —
  route /E from the SOUTH-west: B up to y=80.6, via, F west y≈79.975+0.65
  offsets — worker: use the collision router, target U2 pin6 (29.138,79.975).
  S0/S1: B up x=28.32/30.86 to vias south of U2, F to pins 11/10 east col
  (34.862, 79.975/80.625) approaching from the south-east. EN1: B up x=33.4,
  then B east y=84.6 to x=41.9, via, F north to U3 pin6 (45.138,79.975).
- +5V spine: J1 pad1 → B x=8.0 up to (8.0,71.2) via → F west to (2.6,71.2)
  via → B north (left margin). East branch: B run y=69.7 from (8.0,69.7)
  east to (78.1,69.7) → feeds right margin. Also F stubs to U1 VDD/DVDD caps.
- +3V3 spine: J1 pad3 → B x=13.08 up to via (13.08,70.45) → F west y=70.45
  to (3.3,70.45) via → B north. East branch: B run y=69.55 x 13.08..77.4.
  (Verify 0.15 clearance vs the 5V run y=69.7 — 0.15 gap between 0.3 tracks
  at 0.15 pitch FAILS; use y=69.55 vs 69.7 → edge gap 0.15−0.3 = NEGATIVE.
  SPREAD: 5V y=69.7, 3V3 y=69.2. Re-dodge: LED_IN via at (23.24,69.85),
  LEDD3 B run y=69.0, 5V feeder 69.7, 3V3 feeder 69.2 — check crossings with
  the router, adjust ±0.3 as needed.)
- LED_IN (LEDD0): J1 pad7 → B x=23.24 up to via (23.24,69.85) → F north/east
  to (25.7,69.85)?? — S3 DIN port is x=cx+2.2=25.7: F north x=25.7 through
  S3 band to DIN pad. Keep clear of S3's GNDled stub (x=24.05, ends y 69.2).
- GND: zone-served. Every GND pad in the strip/margins sits in pour. The only
  GND traces are: per-square E-port stub, GNDled stub, jumper pad1 stub —
  each ends inside pour territory (outside the 15.4 keepouts).

## Generator implementation notes

1. Copy the collision-registry router helpers from generate_quadrant_v2.py
   (seg_clear/raw/via/hseg/vseg/corridor/escape as useful) — but coordinates
   above are pre-planned; prefer explicit raw()/via() with the plan's coords,
   and use the registry only to catch mistakes early.
2. bds.SetCopperLayerCount(4). Add In1.Cu/In2.Cu handling to any helper that
   assumes 2 layers. Spiral tracks: width 0.25.
3. Same-net overlaps (coil stubs near own turns) are legal — don't fight them.
4. Iterate: run generator → kicad-cli DRC → read JSON → fix coords → repeat
   until 0 violations / 0 unconnected. Silk warnings acceptable.
5. Exports as quadrant_v2 (gerbers incl. In1/In2, BOM.csv, positions.csv).
   BOM LCSC: 74HC4851PW=C458225, WS2812C-2020=C2976072, UHE4913G=C86815,
   0603 100n=C5137636. EM4095 (SOIC-16), zeners 15V SOD-523, C0G caps:
   fill value + package, LCSC# = TBD-verify (note in README).
6. README.md: bring-up steps, §8.3 measurements from DESIGN_V3_RFID.md,
   predicted L values (83µH / 8.3µH), tank refit instructions, EM4095 pinout
   verification warning, cost estimate (~₹1.5k incl. 10 tags).
