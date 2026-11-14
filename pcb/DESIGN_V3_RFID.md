# DESIGN V3 — 125kHz RFID Piece Recognition (Variant B)

Status: **paper design, nothing ordered.** Next physical step is a 2×2
antenna+switching test rig (Section 8), not the 64-square board.

## 1. Summary + cost verdict

**Architecture:** 64 buried 4-layer PCB spiral antennas (147µH, Q≈8,
design in Section 2), switched single-ended through a **74HC4851
flat-pass mux tree** (Section 3 — CD74HC4067 is disqualified on voltage
rating and Q-killing Ron), read by **4× EM4095** — one per existing
quadrant PCB, 16 squares each (Section 4). Halls keep doing fast presence
detection; RFID only fires on squares whose hall bit just changed, so a
normal move costs ~2 reads (~100ms), not a board sweep.

**Cost verdict:** Mid-case estimate **~₹12.5k/board landed**, ₹2.5k over
the ₹10k per-board cost target; best case (2-layer antenna validated + bulk
EM4095 pricing) **~₹9.5k**, under it. Both scenarios are well under
Certabo's retail floor (≈₹37k+), so the project is commercially sound
either way — the open question is margin, and it hinges on two things the
next step (2×2 rig, Section 8) is built to answer: does a 2-layer antenna
read reliably at contact range, and what does EM4095 actually cost in
bulk. Full numbers: Section 6.

**Do not order the 64-square board yet.** Section 7's risk register is
the gate; Section 8 is the rig that clears it.

## 2. Per-square antenna

### 2.1 Constraint

Each square is a fixed 33×33mm footprint, already carrying (from Variant A,
unchanged):
- 1× UHE4913G hall sensor (C86815), dead center.
- 1× WS2812C-2020 LED (C2976072), offset **+8mm/+8mm** from center →
  11.3mm from center on the diagonal.

An RFID antenna is a spiral of copper that has to occupy an annulus around
that center point without touching either part electrically.

### 2.2 Geometry chosen

30mm outer diameter / 12mm inner diameter spiral, centered in the 33mm
square (1.5mm margin all round to the routed square edge). Inner clear
radius = 6mm — enough for the hall sensor's footprint, but the LED at
11.3mm radius sits **inside the annulus**, not outside it. This is why the
spiral must live entirely on inner layers (Section 2.4) — the LED and its
four chain traces stay on the outer (top) layer and simply cross over the
buried coil with no copper conflict.

18 turns/layer × 4 layers, series-connected through vias (same winding
direction each layer — this is what makes stacking worth it: mutual
coupling between layers adds, not just raw turn count). Track 0.25mm /
gap 0.25mm (0.5mm pitch across the 9mm-wide annulus → 18 turns fits with
room for layer-to-layer registration tolerance; JLCPCB's 4-layer minimum
is 0.09mm track/gap, so this has large margin, which matters because
misregistration between the 4 stacked spirals is the main yield risk).

### 2.3 Inductance — modified Wheeler formula, shown

```
L = K1 · μ0 · n² · davg / (1 + K2·ρ)
```
Square-spiral constants: K1 = 2.34, K2 = 2.75.

```
dout = 30mm, din = 12mm
davg = (dout+din)/2 = 21mm = 0.021 m
ρ    = (dout-din)/(dout+din) = 18/42 = 0.4286
n    = 18 turns/layer × 4 layers = 72 (series)
μ0   = 1.25664×10⁻⁶ H/m

L = 2.34 × 1.25664e-6 × 72² × 0.021 / (1 + 2.75×0.4286)
  = 2.34 × 1.25664e-6 × 5184 × 0.021 / 2.1786
  = 3.2015e-4 / 2.1786
  = 147.0 µH
```

This matches an independently computed table from earlier research
exactly, which also gives, for this
same 30/12mm-4-layer geometry: **R_dc ≈ 15Ω, Q@125kHz ≈ 7.8** (Q =
2πfL/R = 2π·125000·147e-6/15 = 7.7, matches). Q of 7–8 is *below* the
~15 ceiling EM4100's Manchester bit rate needs anyway — no damping
resistor required, the coil's own loss is already in the right window.

### 2.4 Tank capacitor

```
C_RES = 1 / ((2π·f0)² · L) = 1 / ((2π·125000)² × 147e-6) = 11.03 nF
```
Built from two in-stock LCSC C0G/NP0 0805 parts already priced in prior
research: **4.7nF (C77063, Murata GRM2165C1H472JA01D) + 5.6nF (C77067,
Murata GRM2195C1H562JA01D) = 10.3nF**, within 7% of the 11.03nF target —
acceptable given the coil's own L tolerance (±30% across the 4-layer
registration stack) dominates the resonance error budget anyway. C0G/NP0
is mandatory here; X7R's DC-bias and temperature drift would detune the
tank more than the manufacturing tolerance does.

### 2.5 2-layer vs 4-layer — decision

| | 2-layer (30/14mm, 16t) | 4-layer (30/12mm, 72t, chosen) |
|---|---|---|
| L | ~33µH | 147µH |
| Q@125kHz | 3.8 | 7.8 |
| Read range (tag flat on surface) | unproven — likely marginal | comfortable margin |
| JLCPCB fab premium vs Variant A | none | ~2.5–3× 2-layer fab cost [est.] |

**Decision: 4-layer, for margin.** A 2-layer coil is 4.5× lower L and
half the Q — for a chessboard the tag never leaves contact distance
(0–2mm), so 2-layer *might* be entirely sufficient, but nobody has
measured it. Going 4-layer now buys read-range margin at a real but
bounded fab cost; the 2×2 rig (Section 8) should build **one panel of
each** so this decision is validated with a NanoVNA/scope, not assumed.
If 2-layer reads reliably, it is the single biggest lever to pull Variant
B's landed cost down (Section 6, Low scenario).

## 3. Antenna switching — the critical section

A 125kHz LC tank swinging unloaded rings to tens of volts — EM4095's own
application note works an example at **V_ANT(peak) = 69.2V** even with the
series resistor chosen to cap current at 120mA (AN404 §4.1.4). Whatever switches the antenna sits directly in
that swing. This decides the whole subsystem.

### 3.1 Why CD74HC4067 is inadequate

CD74HC4067 is the obvious first choice (it's already on the Variant A
quadrant board for hall/LED addressing) and it is **wrong** for this job,
for three independent reasons:

1. **Voltage rating.** HC-family inputs are rated to VCC+0.5V / GND−0.5V
   before the internal ESD/clamp diodes start conducting. A 69V swing is
   ~14× over that. Even after clamping (Section 3.3), a clamped ~15V
   swing is still 3× over what a 5V-supplied HC4067 tolerates — clamp
   current would flow into the VCC rail, which can latch up or destroy
   the die.
2. **On-resistance.** HC4067 R_on ≈ 70–100Ω (LCSC C179326 datasheet). The
   antenna's own R_dc is already 15Ω giving Q≈8; adding 70–100Ω in
   series with the tank drags Q down to ~1–2 — too broad to resolve the
   EM4100 carrier from noise.
3. **Off-isolation / crosstalk.** With 15 other unselected channels
   floating on the same mux die, their combined off-capacitance loads the
   selected line and couples energy into neighboring squares' coils —
   exactly the sneak-path problem the EEVblog RF-designer thread flags
   for row/column matrices.

### 3.2 What actually works: single-ended flat-pass mux tree

Standard practice per the sourced EEVblog recommendation: **ground one
leg of every antenna coil, switch only the other ("hot") leg with a
1:N analog mux**, ±bipolar-tolerant supply. This halves the switch count
(1 signal/square, not 2) and is exactly what a flat-pass mux family is
built for.

**Chosen part: 74HC4851 (Nexperia), TSSOP-16 — LCSC C458225
(74HC4851PW) or C547079 (74HC4851BQ, QFN).** This is an 8-channel
single-ended mux with "injection-current effect control" / flat-pass
architecture: it's explicitly designed to pass analog signals that swing
*outside* its own supply rails without injecting fault current into VDD/
VSS — the exact failure mode that kills HC4067 here. Datasheet-rated for
signal excursions up to ±20V beyond the rails at controlled injection
current (Nexperia 74HC4851 series page). R_on is comparable to HC4067
(~70–80Ω typ) — not free, but the part *survives* the swing HC4067
cannot, which is the actual requirement here.

**16:1 tree with zero extra parts:** two 74HC4851 with their `OUT` pins
tied together, `EN` pins driven complementary. A disabled 74HC4851 puts
all 8 channels in true high-Z, so tying two outputs together and
selecting which die is "live" via EN is a standard mux-tree trick — no
additional switch IC needed to go from 8:1 to 16:1. This maps one 16-
square quadrant to exactly 2× 74HC4851 (Section 4).

### 3.3 Mandatory per-square clamp (belt-and-suspenders)

±20V injection tolerance still isn't enough headroom against a 69V
unclamped peak. Every antenna gets a **local clamp before the mux**, not
relying on the switch's own protection:

- 2× back-to-back Zener (e.g. 15V SOD-523, ~$0.01 each) from the hot leg
  to ground, sized so the clamped swing (~15V) sits inside the 74HC4851's
  ±20V injection-tolerant window with margin.
- This clamp also caps the voltage the tag itself sees, which is
  desirable — protects the tag chip and prevents the tank from ringing so
  hard that it stays "on" into the next mux channel's settling time.

**Per-square switching+protection cost:** 74HC4851 amortized over 8
channels ($0.373÷8 ≈ $0.047) + 2× clamp Zener ($0.02) + optional series R
($0.005) ≈ **$0.07–$0.08/square (~₹6–7)** [est., LCSC qty-1 pricing used
as ceiling — true qty-100+ price should be lower].

### 3.4 Rejected alternatives

| Option | Verdict |
|---|---|
| CD74HC4067 | Rejected — Section 3.1 |
| DG408/DG409 (Vishay) | Works (±15V-rated analog switch, standard for this), but DG408 itself isn't stocked at LCSC — only DG409 (dual 4-ch, C142533, $0.735 [qty-1 price]) is, at 2× the 74HC4851 unit cost with no flat-pass advantage. Fallback if 74HC4851 stock dries up. |
| Back-to-back discrete MOSFET per square | Ron can be tuned lower (dual N-FET SOT-363, $0.037, from prior research) but needs an isolated gate-drive tree per square — same address-decode problem as a mux, reinvented in discretes, for a part that's already cheaper as an IC. Not worth the layout complexity at this scale. |
| Relay tree | Rejected — 64 relays: slow (ms), bulky, mechanical wear, cost. |
| Row/column resistive matrix | Rejected — bipolar LF signal breaks diode isolation; sneak paths. |

## 4. Reader topology

### 4.1 4 readers, mapped 1:1 to the existing quadrant boards

**4× EM4095, one per quadrant PCB** (not 8). Each quadrant already carries
16 squares in the Variant A layout — giving each quadrant its own reader
keeps the RFID subsystem self-contained per board, reuses the existing
quadrant/hub split, and needs no new inter-board signal beyond what's
listed in 4.3.

Per quadrant (16 squares): 2× 74HC4851 in the 16:1 tree (Section 3.2) →
1× EM4095 → DEMOD_OUT back to the hub.

**Why not 8 (one per 8 squares, as the background research sized it)?**
Eight readers halve full-board resync time (~400ms vs ~800ms) but double
reader+mux silicon cost for a benefit that only matters at power-on/
resync. Section 4.2's rescan strategy means a normal move reads 2 squares
regardless of zone count (~100ms either way) — 4 readers is the
cost-optimized choice; 8 is a documented fallback if scan latency proves
to matter more than expected on the 2×2 rig.

### 4.2 Hall-triggered rescan (why RFID barely runs)

Halls stay in Variant B for exactly this reason: fast,
cheap, always-on presence detection. Firmware logic:

1. Poll all 64 hall bits continuously (existing 74HC165 shift-in chain,
   unchanged from Variant A).
2. On any bit's rising or falling edge, mark that square "dirty."
3. RFID only scans dirty squares — a normal move touches 2 squares (lift +
   place), so per-move latency is ~2 reads ≈ 100ms, not a board sweep.
4. Full 64-square RFID resync (all squares, ignore dirty flags) runs once
   at power-on/reconnect to seed piece identity, and optionally on demand
   (e.g. "resync board" button) — this is the ~800ms case.
5. SHD is pulled high (sleep, ~1µA) on all 4 EM4095s between scans; a scan
   burst pulls SHD low, waits T_SET (25ms typ, 35ms max per datasheet) for
   PLL lock, then reads. This matters for the battery-powered hub.

### 4.3 ESP32 pin budget

RFID adds these signals, on top of Variant A's unchanged hall (74HC165)
and LED (WS2812 RMT) buses:

| Signal | Count | How it's carried |
|---|---|---|
| DEMOD_OUT (per EM4095, timing-critical — needs direct GPIO, not shifted in) | 4 | 4× direct GPIO, ideally RMT/PCNT-capable pins for bit timing |
| SHD (per EM4095) | 4 | packed into a shift-out register (below) |
| Mux address (2 bits × 2 muxes' shared A0/A1 + 1 bank-select EN per quadrant) | 3/quadrant × 4 = 12 | packed into shift-out register |
| **Shift-out control bus** (SHD×4 + mux addr×12 = 16 bits → 2× 74HC595) | — | **3 new pins**: SER, SRCLK, RCLK (new bus, separate from the existing hall-in / LED-out buses) |

**Net new ESP32 GPIO: 4 (DEMOD_OUT) + 3 (595 bus) = 7 pins.** Comfortable
within ESP32-WROOM-32E's ~34 usable GPIO, but **not yet checked against
the actual hub_v2 pinout** (`/PL=25, CP=26, SER=14, LED_DATA=27` plus
UART/charge-IC/button pins already committed) — flagged in Section 7.

### 4.4 The unresolved part: quadrant↔hub connector

Variant A's J1/J2 headers (2×6, keyed, inner row `/PL CP SER +5V +3V3
LED_DATA`, outer row all-GND) are already fully assigned. RFID needs, per
quadrant: 1× DEMOD_OUT (dedicated wire, can't share timing with the slow
hall-poll clock) + a tap into the new 3-wire 595 bus. That's **at least 2
more pins per quadrant connector**, meaning J1/J2 grow from 2×6 to 2×7 or
2×8, or the 595 bus daisy-chains hub→quadrant→quadrant (shared 3 wires)
while DEMOD_OUT still needs 1 dedicated wire back per quadrant. **This is
not solved in this document** — it's a connector/PCB layout task for
whoever builds the 64-square board, and the 2×2 rig should prove the
signal path end-to-end (Section 8), not just the antenna.

## 5. BOM

Prices are LCSC qty-1 list price unless noted; qty-20/100 tiers are
typically 20–40% lower and should be re-checked before ordering. USD→₹
at **₹87/$** (stated assumption, Section 6).

### 5.1 Per-quadrant (16 squares = 1 zone = 1 EM4095)

| Part | LCSC # | Qty/quadrant | Unit $ | Line $ | Source |
|---|---|---|---|---|---|
| EM4095 reader IC | C11356 (0 stock; source via AliExpress/Mouser) | 1 | $1.50–$2.50 [est., sourcing risk] | ~$2.00 | earlier research |
| 74HC4851PW mux | C458225 | 2 | $0.373 | $0.746 | web search, this doc |
| EM4095 support passives (Rser 33Ω, Cdec 100nF, Cdc2 6.8nF, Cfcap 10nF, Cagnd 220nF, Cdv1 47pF, Cdv2 1.5nF, 2×100nF decoupling) | generic 0805/0603 C0G/X7R | 1 set | ~$0.035 total | $0.035 | AN404 values |
| Tank cap 4.7nF C0G 0805 | C77063 | 16 | $0.042 | $0.672 | earlier research |
| Tank cap 5.6nF C0G 0805 | C77067 | 16 | $0.041 | $0.656 | earlier research |
| Clamp Zener 15V SOD-523 (pair/square) | generic, e.g. BZT52C15S | 32 | $0.01 | $0.32 | [est.] |
| Series damping R, 0805 | generic | 16 | $0.005 | $0.08 | [est.] |
| 74HC595 (mux addr + SHD shift-out, 16 bits = 2 chips) | C5947 | 2 | $0.095 | $0.19 | earlier research |
| **Quadrant RFID subtotal** | | | | **~$4.70** | |

### 5.2 Per board-set (4 quadrants + tags)

| Item | Qty | Line $ |
|---|---|---|
| Quadrant RFID subtotal × 4 | 4 | $18.80 |
| RFID tags, 125kHz EM4100/TK4100 adhesive coin, 25mm | 34 (32 pieces + 2 spare queens) | $5.10 ($0.15/tag [est. midpoint of $0.08–$0.21 range]) |
| **Board-set RFID component total** | | **~$23.90** |

This excludes PCB fab (2-layer→4-layer premium) and JLCPCB assembly
delta — covered in Section 6 as a separately-estimated, higher-uncertainty
line.

## 6. Cost table (₹)

Assumptions: $1 = ₹87. Component costs get a **1.3× overhead** (customs/
small-parcel shipping/forex spread on LCSC+AliExpress orders, consistent
with how the Variant A ₹6.2k baseline was built). PCB fab+assembly costs
get a smaller **1.1×** (JLCPCB invoice already bundles manufacture+
assembly; India-side handling on the finished board is lighter than
re-importing loose parts).

### 6.1 Three scenarios, per board-set (5-board run, JLCPCB qty-20
quadrants + qty-5 hubs, matching the Variant A ordering pattern)

| | **Low** (2-layer confirmed viable, bulk EM4095 $1.20) | **Mid** (4-layer, EM4095 $2.00 — default assumption) | **High** (4-layer, EM4095 sourcing friction $3.00, wide assembly estimate) |
|---|---|---|---|
| RFID parts (Section 5.2), 4×EM4095 re-priced | $20.44 | $23.90 | $27.64 |
| × 1.3 overhead → ₹ | ₹2,314 | ₹2,701 | ₹3,127 |
| PCB fab premium (2→4 layer, 4 quadrants, amortized/board) [est.] | $0 (no layer change) | $22 | $40 |
| Extra SMT assembly (new placements: mux/reader/caps/zeners per quadrant) [est.] | $10 | $18 | $30 |
| Fab+assembly × 1.1 → ₹ | ₹958 | ₹3,637 | ₹6,700 |
| **RFID delta/board** | **₹3,272** | **₹6,338** | **₹9,827** |
| **Variant B landed/board** (₹6.2k baseline + delta) | **₹9.5k** | **₹12.5k** | **₹16.0k** |

### 6.2 5-board run totals

| | Low | Mid | High |
|---|---|---|---|
| Variant B landed × 5 boards | ₹47.4k | ₹62.7k | ₹80.2k |
| vs. Variant A ×5 (₹31k) | +₹16.4k | +₹31.7k | +₹49.2k |

### 6.3 Verdict against the ₹10k ceiling

**Mid-case estimate lands at ~₹12.5k/board — ₹2.5k over the
₹10k ceiling.** The Low scenario hits ₹9.5k, under ceiling, but depends
on two things not yet proven:

1. **2-layer antenna works at contact range** (Section 2.5) — this alone
   is worth ~₹2.7k/board (kills the 4-layer fab+assembly premium
   entirely). This is the single biggest lever, and exactly what the 2×2
   rig (Section 8) should settle.
2. **EM4095 bought in bulk (~$1.20 vs $2.00 placeholder)** — worth
   ~₹450/board. Requires a real AliExpress/Mouser quote for 20+ units
   ahead of the 64-square order (LCSC itself is out of stock on every
   EM4095 SKU as of the prior research pass).

Even without either lever, Mid-case ₹12.5k is still comfortably under
Certabo's own retail floor (≈₹37k for the cheapest Vittoria Reloaded at
current EUR/INR), so Variant B is commercially viable either way — the
question is margin, not go/no-go. **Recommendation: build the 2×2 rig,
resolve levers 1 and 2, then re-quote before ordering the 64-square
board.**

## 7. Risk register

What the 2×2 rig must prove before a 64-square board is ordered, ranked
by cost/schedule impact if wrong:

1. **2-layer vs 4-layer antenna read reliability** (Section 2.5). If
   2-layer (33µH, Q3.8) reads EM4100 tags reliably at 0–2mm contact
   distance, that's the single biggest cost lever in this doc (~₹2.7k/
   board). If it doesn't, 4-layer is confirmed as the floor — either way,
   this must be measured, not assumed.
2. **74HC4851 survives real tank ringing.** The ±20V injection-tolerance
   spec plus Zener clamp (Section 3.3) is a paper design. The rig must
   scope the actual clamped waveform at the mux input across
   worst-case Q/coupling (e.g. two coins stacked, or a tag lifted mid-
   read) and confirm no damage after sustained cycling.
3. **Quadrant↔hub connector signal budget** (Section 4.4) is explicitly
   unsolved here. The rig must route DEMOD_OUT + the 595 bus through an
   actual connector (not bench wires) to size J1/J2 correctly before the
   64-square PCB is laid out.
4. **Cross-talk between adjacent live and dead squares.** With a piece on
   one square and the mux scanning its neighbor, does the neighbor's
   antenna field couple enough into the occupied square's tag to cause a
   false/duplicate read? The 4-layer buried-spiral geometry should
   help (denser field near-field, less spread) but hasn't been measured
   against a real 33mm pitch.
5. **EM4095 sourcing.** Every LCSC SKU is out of stock (Section 5). The
   rig should be built with whatever's sourced (AliExpress bare IC or a
   reader breakout module) and that sourcing channel + price should be
   locked in before committing to 64× units for the real board.

## 8. Test rig spec (2×2)

Goal: answer risk register items 1–4 with one small board, before ordering
any 64-square PCB. This is the next step — schematic-level only, no
layout here.

### 8.1 Board outline

- 4 squares, 33mm pitch, 66×66mm PCB (plus panel edge margin for JLCPCB
  handling — round up to ~80×80mm with tooling holes).
- **Squares 1 and 2: 4-layer antenna** (Section 2.2 geometry, 30/12mm,
  18t×4 layers, 147µH target).
- **Squares 3 and 4: 2-layer antenna** (30/14mm, 16t×2 layers, ~33µH
  target) — this is the A/B test that resolves risk #1.
- Each square keeps the Variant A hall (UHE4913G, center) and LED
  (WS2812C-2020, +8/+8mm) footprints, populated, so the connector/routing
  interaction (risk #3) is exercised too, not just the antenna in
  isolation.

### 8.2 Reader/switch circuit (one instance, shared by all 4 squares)

- **1× EM4095** (SOIC-16), AN404 reference values: R_ser 33Ω, C_dec 100nF,
  C_dc2 6.8nF, C_fcap 10nF, C_agnd 220nF, C_dv1 47pF, C_dv2 1.5nF, VDD/DVDD
  decoupling 100nF each. SHD wired to a GPIO (not tied low) so T_SET
  timing can be measured. MOD tied to VSS (read-only design, per AN404).
- **2× 74HC4851** (TSSOP-16) in the tree config: since this rig only has 4
  antennas, wire both chips as a true 4:1-of-8 tree (2 channels each,
  EN-selected) even though a plain 4:1 would suffice — that's the actual
  thing being validated for the 16:1 tree Section 3.2 specifies.
- Each antenna: hot leg → 2× back-to-back 15V Zener (SOD-523) → mux
  channel input. Cold leg → common ground plane (single-ended switching,
  Section 3.2).
- Tank cap per antenna: 4.7nF + 5.6nF C0G 0805 in parallel (C77063 +
  C77067) for the 4-layer squares; recompute for the 2-layer squares once
  their L is measured — Section 2.5 flags the 2-layer C_RES as
  provisional, and prior antenna research explicitly recommends measuring
  L before picking the cap.
- DEMOD_OUT → direct GPIO, with a scope test point in parallel — this is
  the signal to characterize.
- Mux address (A0, A1) + EN0/EN1 → 4 GPIO direct (no shift register
  needed at this scale; label headers to match the eventual 74HC595 bit
  assignment so rig firmware ports to the real board with a lookup-table
  change only).

### 8.3 What to measure

1. NanoVNA (or LCR meter) on each antenna, unpopulated, before any tag is
   present: confirm L and Q against Section 2.3/2.5 predictions for both
   the 4-layer and 2-layer squares.
2. Scope DEMOD_OUT and the clamped antenna-hot-leg waveform (post-Zener)
   during a live read, for both layer counts, with a tag at 0mm and at
   2mm standoff (worst case for a piece with a slightly recessed base
   magnet+tag pocket).
3. Cycle the mux tree through all 4 channels repeatedly (≥10,000 cycles)
   with a tag present on one square and absent on its neighbor — check
   for false reads / bleed-through (risk #4).
4. Confirm T_SET (SHD low → PLL lock) and full single-square read latency
   match the ~33–60ms budgeted in prior research.
5. Route DEMOD_OUT + SHD + mux address through an actual small connector
   (even a basic 1×6 header standing in for J1/J2) rather than bench
   wires, to get a real pin count for risk #3.

Expected output of the rig: L/Q measurements for both layer counts, a
go/no-go on 2-layer, a confirmed BOM for the mux/clamp/tank-cap stage,
and a firmed-up connector pin count — all direct inputs to the 64-square
PCB layout that follows.
