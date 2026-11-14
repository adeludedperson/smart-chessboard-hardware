#!/usr/bin/env python3
"""Hub V3 — swap the Micro-USB receptacle for a USB-C one.  Run with KiCad python3.9.

Operates on pcb/hub_v3_usbc/chess_hub_v3_usbc.kicad_pcb (a copy of the finished
hub_v2 board).  hub_v2 itself is never touched.

What it does:
  1. Deletes USB1 (USB_Micro-B_Wuerth_629105150521).
  2. Drops in USB_C_Receptacle_HRO_TYPE-C-31-M-12 (HRO TYPE-C-31-M-12,
     LCSC C165948) at (35.5, 3.9) rotated 180 so the receptacle mouth faces
     the top board edge, same as the micro-USB did.
  3. Nets the pads for a USB 2.0-only, both-orientations connection:
        A1/B1/A12/B12 + 4 shield legs -> GND
        A4/B4/A9/B9                   -> VBUS
        A6 + B6  (DP1, DP2)           -> UDP     (duplicate pins shorted)
        A7 + B7  (DN1, DN2)           -> UDM     (duplicate pins shorted)
        A5 -> CC1, B5 -> CC2
        A8/B8 (SBU1/SBU2)             -> no net
  4. Adds R8 (CC1->GND) and R9 (CC2->GND), 5.1k 0603.  Without these a USB-C
     source never turns VBUS on, so the board would not charge at all.
  5. Rips up every track/via so the whole board can be re-autorouted against
     the new pad field.

After this run:
    <kp> -c "import pcbnew; b=pcbnew.LoadBoard(PCB); \
             pcbnew.ZONE_FILLER(b).Fill(b.Zones()); b.Save(PCB); \
             pcbnew.ExportSpecctraDSN(b,'/tmp/hubc.dsn')"
    java -jar freerouting-1.9.0.jar -de /tmp/hubc.dsn -do /tmp/hubc.ses -mp 30
    <kp> route_hub_v3.py /tmp/hubc.ses
"""
import os
import pcbnew
from pcbnew import VECTOR2I, FromMM as MM, ToMM

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "hub_v3_usbc", "chess_hub_v3_usbc.kicad_pcb")
FPLIB = os.path.expanduser(
    "~/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")

USBC_LIB = os.path.join(FPLIB, "Connector_USB.pretty")
USBC_FP = "USB_C_Receptacle_HRO_TYPE-C-31-M-12"
RES_LIB = os.path.join(FPLIB, "Resistor_SMD.pretty")
RES_FP = "R_0603_1608Metric"

USBC_POS = (35.5, 3.9)      # rot 180 -> mouth at y = 3.9 - 3.65 = 0.25
USBC_ROT = 180

board = pcbnew.LoadBoard(PCB)
print("loaded", PCB)


def net(name):
    n = board.FindNet(name)
    if n is None:
        n = pcbnew.NETINFO_ITEM(board, name)
        board.Add(n)
        print("  new net", name)
    return n


# ------------------------------------------------------------ 1. remove USB1
old = board.FindFootprintByReference("USB1")
assert old, "no USB1"
print("  removing %s" % old.GetFPID().GetLibItemName())
board.Remove(old)

# ------------------------------------------------------------ 2. add USB-C
usb = pcbnew.FootprintLoad(USBC_LIB, USBC_FP)
assert usb, "cannot load " + USBC_FP
usb.SetParent(board)
board.Add(usb)
usb.SetPosition(VECTOR2I(MM(USBC_POS[0]), MM(USBC_POS[1])))
usb.SetOrientationDegrees(USBC_ROT)
usb.SetReference("USB1")
usb.SetValue("USB-C")
usb.Reference().SetLayer(pcbnew.F_SilkS)
usb.Reference().SetPosition(VECTOR2I(MM(USBC_POS[0]), MM(USBC_POS[1] + 5.4)))
usb.Reference().SetTextAngleDegrees(0)
usb.Value().SetLayer(pcbnew.F_Fab)

# ------------------------------------------------------------ 3. pad nets
PADNET = {
    "A1": "GND",  "B1": "GND",  "A12": "GND", "B12": "GND", "SH": "GND",
    "A4": "VBUS", "B4": "VBUS", "A9": "VBUS", "B9": "VBUS",
    "A6": "UDP",  "B6": "UDP",          # DP1 / DP2 shorted -> USB 2.0 either way up
    "A7": "UDM",  "B7": "UDM",          # DN1 / DN2
    "A5": "CC1",  "B5": "CC2",
    "A8": None,   "B8": None,           # SBU1 / SBU2 unused
}
for p in usb.Pads():
    name = p.GetNumber()
    if name == "":            # the two 0.65mm mechanical NPTH
        continue
    assert name in PADNET, "unexpected USB-C pad " + name
    nn = PADNET[name]
    p.SetNet(net(nn) if nn else board.FindNet(""))
    if nn is None:
        p.SetNetCode(0)
print("  USB-C pads netted")

for p in sorted(usb.Pads(), key=lambda p: (ToMM(p.GetPosition().y),
                                           ToMM(p.GetPosition().x))):
    print("    %-3s %-5s (%.3f, %.3f)" % (p.GetNumber(), p.GetNetname(),
                                          ToMM(p.GetPosition().x),
                                          ToMM(p.GetPosition().y)))

# ------------------------------------------------------------ 4. CC pulldowns
CC = [("R8", "CC1", 36.40, 11.00), ("R9", "CC2", 33.75, 11.00)]
for ref, ccnet, x, y in CC:
    r = pcbnew.FootprintLoad(RES_LIB, RES_FP)
    assert r, "cannot load " + RES_FP
    r.SetParent(board)
    board.Add(r)
    r.SetPosition(VECTOR2I(MM(x), MM(y)))
    r.SetOrientationDegrees(270)        # pad 1 towards the connector (-y)
    r.SetReference(ref)
    r.SetValue("5k1")
    r.Reference().SetLayer(pcbnew.F_SilkS)
    r.Reference().SetPosition(VECTOR2I(MM(x - 1.6), MM(y)))
    for p in r.Pads():
        p.SetNet(net(ccnet if p.GetNumber() == "1" else "GND"))
    print("  %s 5k1 %s->GND at (%.2f, %.2f)  pad1 %s pad2 %s"
          % (ref, ccnet, x, y,
             tuple(round(ToMM(v), 2) for v in (r.FindPadByNumber("1").GetPosition().x,
                                               r.FindPadByNumber("1").GetPosition().y)),
             tuple(round(ToMM(v), 2) for v in (r.FindPadByNumber("2").GetPosition().x,
                                               r.FindPadByNumber("2").GetPosition().y))))

# ------------------------------------------------------------ 5. rip up copper
tracks = list(board.GetTracks())
for t in tracks:
    board.Remove(t)
print("  ripped up %d tracks/vias" % len(tracks))

# ------------------------------------------------------------ report
print("\n=== courtyard overlap check ===")
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
print("  %d courtyard bbox overlaps" % bad)
print("  USB1 courtyard:", boxes.get("USB1"))
print("  R8 courtyard:  ", boxes.get("R8"))
print("  R9 courtyard:  ", boxes.get("R9"))

board.BuildListOfNets()
board.Save(PCB)
print("\nsaved", PCB)
