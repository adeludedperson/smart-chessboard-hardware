#!/usr/bin/env python3
"""Silkscreen tidy for hub_v3 (USB-C).  Run with KiCad's python3.9.

The USB-C receptacle sits with its mouth on the top board edge, so three of the
stock footprint's silk segments land exactly on Edge.Cuts, and the new USB1 /
R8 reference fields landed on top of the CC-resistor pads.  This pulls the silk
back inside the board and moves the two reference fields to clear space.

Leaves the board with the same 4 cosmetic silk warnings hub_v2 has
(SW1 + BT1 overhang the edge by design).
"""
import os
import pcbnew
from pcbnew import VECTOR2I, FromMM as MM, ToMM

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "hub_v3_usbc", "chess_hub_v3_usbc.kicad_pcb")
YMIN = 0.25          # keep silk this far inside the y = 0 board edge

board = pcbnew.LoadBoard(PCB)

usb = board.FindFootprintByReference("USB1")
n = 0
for g in usb.GraphicalItems():
    if g.GetLayer() != pcbnew.F_SilkS or not isinstance(g, pcbnew.PCB_SHAPE):
        continue
    s, e = g.GetStart(), g.GetEnd()
    ns, ne = VECTOR2I(s.x, max(s.y, MM(YMIN))), VECTOR2I(e.x, max(e.y, MM(YMIN)))
    if ns.y != s.y or ne.y != e.y:
        g.SetStart(ns); g.SetEnd(ne)
        print("  USB1 silk (%.2f,%.2f)-(%.2f,%.2f) -> y clamped to %.2f"
              % (ToMM(s.x), ToMM(s.y), ToMM(e.x), ToMM(e.y), YMIN))
        n += 1
print("  clamped %d USB1 silk segments" % n)

REFPOS = {
    "USB1": (28.00, 5.00),    # left of the connector, clear of the antenna window
    "R8":   (36.40, 13.60),   # was sitting on R9's body and pads
    "R9":   (32.00, 13.60),
}
for ref, (x, y) in REFPOS.items():
    f = board.FindFootprintByReference(ref)
    f.Reference().SetPosition(VECTOR2I(MM(x), MM(y)))
    print("  %s reference -> (%.2f, %.2f)" % (ref, x, y))

pcbnew.ZONE_FILLER(board).Fill(board.Zones())
board.BuildListOfNets()
board.Save(PCB)
print("saved", PCB)
