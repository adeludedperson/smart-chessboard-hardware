#!/usr/bin/env python3
"""Hub V2 repair pass — run with KiCad's python3.9.

Fixes the structural defects the generator left behind, then rips up all
routing so an autorouter can redo it against a clean, legal board:

  1. U1 (ESP32-WROOM-32E) ships with Espressif's full antenna keepout
     (48 x 21mm) plus a matching courtyard. On an 88x60 board with the module
     inline at the top edge that region is un-satisfiable and it swallows USB1.
     -> delete the footprint keepout + oversized courtyard, keep the explicit
        board-level antenna keepout (6.5..25.5 x 1..9.2) as the real rule.
  2. U1 pad 39 stitching holes are 0.2mm drill, board min hole is 0.3mm.
     -> 0.3mm drill (JLC standard via size).
  3. C1/C2 sit underneath the U1 module body; D1 shorts SW3; U3/R5/C5/C6 sit
     underneath the BT1 18650 cell.  -> relocate.
  4. GND zones used thermal reliefs and produced starved (1-spoke) pads.
     -> solid pad connection.
  5. Rip up every track/via (the +3V3 corridor ran off-board at y=-0.7 and
     straight through the antenna keepout).
"""
import os, sys
import pcbnew
from pcbnew import VECTOR2I, FromMM as MM, ToMM

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "hub_v2", "chess_hub_v2.kicad_pcb")

board = pcbnew.LoadBoard(PCB)
print("loaded", PCB)


def fpr(ref):
    f = board.FindFootprintByReference(ref)
    assert f, "missing footprint " + ref
    return f


# ---------------------------------------------------------------- 1. U1 keepout
u1 = fpr("U1")
for z in list(u1.Zones()):
    print("  delete U1 footprint zone (rule area=%s)" % z.GetIsRuleArea())
    u1.Remove(z)

# replace the antenna-sized courtyard with the module body outline only
crt = [g for g in u1.GraphicalItems()
       if g.GetLayer() in (pcbnew.F_CrtYd, pcbnew.B_CrtYd)]
for g in crt:
    u1.Remove(g)
print("  removed %d U1 courtyard shapes" % len(crt))

# module body 18 x 25.5 centred on U1, plus pad overhang -> local rect
BODY = (-9.75, -13.0, 9.75, 13.05)
rect = pcbnew.PCB_SHAPE(u1)
rect.SetShape(pcbnew.SHAPE_T_RECT)
rect.SetStart(VECTOR2I(MM(16.0 + BODY[0]), MM(15.0 + BODY[1])))
rect.SetEnd(VECTOR2I(MM(16.0 + BODY[2]), MM(15.0 + BODY[3])))
rect.SetLayer(pcbnew.F_CrtYd)
rect.SetWidth(MM(0.05))
rect.SetFilled(False)
u1.Add(rect)
print("  U1 courtyard -> module body only")

# ---------------------------------------------------------------- 2. drills
n = 0
for f in board.GetFootprints():
    for p in f.Pads():
        d = p.GetDrillSize()
        if 0 < d.x < MM(0.3) or 0 < d.y < MM(0.3):
            nx = max(d.x, MM(0.3)) if d.x else 0
            ny = max(d.y, MM(0.3)) if d.y else 0
            p.SetDrillSize(VECTOR2I(nx, ny))
            sz = p.GetSize()
            p.SetSize(VECTOR2I(max(sz.x, MM(0.6)), max(sz.y, MM(0.6))))
            n += 1
print("  enlarged %d sub-0.3mm drills to 0.3mm" % n)

# ---------------------------------------------------------------- 3. placement
MOVES = {
    # ref : (x, y, rot)   -- rot None keeps existing
    "C1": (2.60, 20.50, 90),    # out from under the ESP32 module body
    "C2": (2.60, 24.50, 90),
    "D1": (56.00, 11.00, 0),    # was shorting SW3 pad 2 / bridging C8
    "U3": (26.50, 34.00, 0),    # TP4056 out from under the 18650 cell
    "R5": (33.50, 32.50, 0),
    "C5": (33.50, 36.00, 0),
    "C6": (48.50, 36.00, 0),
    "U4": (16.00, 32.00, 0),    # clear of the U1 module body courtyard
    "USB1": (36.00, 3.45, 0),   # shield legs were 0.35mm from the board edge
}
for ref, (x, y, rot) in MOVES.items():
    f = fpr(ref)
    f.SetPosition(VECTOR2I(MM(x), MM(y)))
    if rot is not None:
        f.SetOrientationDegrees(rot)
    print("  moved %-4s -> (%.2f, %.2f) rot %s" % (ref, x, y, rot))

# ------------------------------------------------- 3b. silkscreen / BOM tidy
# reference fields that sat over the board edge or over a neighbour's copper
REFPOS = {"U4": (16.0, 36.6), "USB1": (36.0, 9.0), "SW3": (46.5, 19.6)}
for ref, (x, y) in REFPOS.items():
    fpr(ref).Reference().SetPosition(VECTOR2I(MM(x), MM(y)))
    print("  %s reference -> (%.1f, %.1f)" % (ref, x, y))

# SW1 (PCM12 slide switch) shared the value string "PWR" with LED2, so the BOM
# generator handed the switch the LED's LCSC number. Give it its own value.
fpr("SW1").SetValue("PWR_SLIDE")
print("  SW1 value -> PWR_SLIDE (BOM collided with LED2)")

# ---------------------------------------------------------------- 4. zones
for z in board.Zones():
    if z.GetIsRuleArea():
        continue
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
print("  GND zones -> solid pad connection")

# ---------------------------------------------------------------- 5. rip up
tracks = list(board.GetTracks())
for t in tracks:
    board.Remove(t)
print("  ripped up %d tracks/vias" % len(tracks))

# ---------------------------------------------------------------- report
print("\n=== courtyard overlap check ===")
refs = [f.GetReference() for f in board.GetFootprints()]
boxes = {}
for f in board.GetFootprints():
    bb = f.GetCourtyard(pcbnew.F_CrtYd).BBox()
    if bb.GetWidth() <= 0:
        continue
    boxes[f.GetReference()] = (ToMM(bb.GetLeft()), ToMM(bb.GetTop()),
                               ToMM(bb.GetRight()), ToMM(bb.GetBottom()))
bad = 0
ks = sorted(boxes)
for i, a in enumerate(ks):
    for b in ks[i + 1:]:
        ax1, ay1, ax2, ay2 = boxes[a]
        bx1, by1, bx2, by2 = boxes[b]
        if ax1 < bx2 and bx1 < ax2 and ay1 < by2 and by1 < ay2:
            print("  OVERLAP %s %s  %s / %s" % (a, b, boxes[a], boxes[b]))
            bad += 1
print("  %d courtyard bbox overlaps remaining" % bad)

board.BuildListOfNets()
board.Save(PCB)
print("\nsaved", PCB)
