#!/usr/bin/env python3
"""Second-chance GND stitcher for hub_v3.

route_hub_v3.py's grid pass leaves a few F.Cu pour fragments that its coarse
0.15mm scan + 0.35mm extra clearance could not reach.  This pass:

  * scans at 0.05mm with the real DRC margins (0.2mm copper clearance,
    0.25mm hole-to-hole / hole-to-copper) instead of the conservative 0.35,
  * tries three via sizes,
  * if a fragment still cannot take a via, reports exactly which constraint
    blocked it so it can be fixed by hand.

Run with KiCad's python3.9.  Idempotent.
"""
import os, sys, math
import pcbnew
from pcbnew import VECTOR2I, FromMM as MM, ToMM

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "hub_v3_usbc", "chess_hub_v3_usbc.kicad_pcb")

BW, BH = 88.0, 60.0
CLR = 0.24            # rule is 0.20 (Power class) -> 0.04 margin
HOLE_GAP = 0.28       # rule is 0.25
HOLE_CLR = 0.28       # hole-to-copper rule is 0.25
KEEPOUT = (6.5, 1.0, 25.5, 9.2)
SIZES = ((0.7, 0.35), (0.6, 0.3), (0.5, 0.3))

board = pcbnew.LoadBoard(PCB)
gnd = board.FindNet("GND")

# The generator's pours used a 0.35mm zone clearance and a 0.25mm minimum neck.
# The USB-C fanout pushes more copper through the middle of the board, and those
# numbers pinched the F.Cu pour into islands around U2.1 and C5.2.  0.25/0.20 is
# still well above the 0.20mm netclass clearance and JLC's 0.127mm minimum.
for z in board.Zones():
    if z.GetIsRuleArea():
        continue
    z.SetLocalClearance(MM(0.25))
    z.SetMinThickness(MM(0.20))


def seg_dist(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def snapshot():
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pours = {}
    for z in board.Zones():
        if z.GetIsRuleArea() or z.GetNetname() != "GND":
            continue
        for lay in z.GetLayerSet().Seq():
            pours[lay] = z.GetFilledPolysList(lay)
    obst, segs, holes = [], [], []
    for f in board.GetFootprints():
        for p in f.Pads():
            pos = p.GetPosition(); sz = p.GetSize()
            hx, hy = ToMM(sz.x) / 2.0, ToMM(sz.y) / 2.0
            if p.GetOrientationDegrees() % 180 > 45:
                hx, hy = hy, hx
            obst.append((ToMM(pos.x), ToMM(pos.y), hx, hy, p.GetNetname() == "GND"))
            d = max(ToMM(p.GetDrillSize().x), ToMM(p.GetDrillSize().y))
            if d > 0:
                holes.append((ToMM(pos.x), ToMM(pos.y), d / 2.0))
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            pos = t.GetPosition(); r = ToMM(t.GetWidth(pcbnew.F_Cu)) / 2
            obst.append((ToMM(pos.x), ToMM(pos.y), r, r, t.GetNetname() == "GND"))
            holes.append((ToMM(pos.x), ToMM(pos.y), ToMM(t.GetDrill()) / 2.0))
        else:
            s, e = t.GetStart(), t.GetEnd()
            segs.append((ToMM(s.x), ToMM(s.y), ToMM(e.x), ToMM(e.y),
                         ToMM(t.GetWidth()), t.GetNetname() == "GND"))
    return pours, obst, segs, holes


def why(x, y, dia, drill, pours, obst, segs, holes, frag):
    """None if legal, else the name of the failing constraint."""
    if not (1.5 < x < BW - 1.5 and 1.5 < y < BH - 1.5):
        return "edge"
    if (KEEPOUT[0] - 0.8 < x < KEEPOUT[2] + 0.8
            and KEEPOUT[1] - 0.8 < y < KEEPOUT[3] + 0.8):
        return "antenna"
    for (hx0, hy0, hr) in holes:
        if math.hypot(x - hx0, y - hy0) < drill / 2 + hr + HOLE_GAP:
            return "hole2hole"
    r = dia / 2 + CLR
    hr_ = drill / 2 + HOLE_CLR
    for (ox, oy, hx, hy, is_gnd) in obst:
        if is_gnd:
            continue
        if abs(x - ox) < hx + r and abs(y - oy) < hy + r:
            return "pad"
    for (x1, y1, x2, y2, w, is_gnd) in segs:
        if is_gnd:
            continue
        d = seg_dist(x, y, x1, y1, x2, y2)
        if d < r + w / 2 or d < hr_ + w / 2:
            return "track"
    pt = VECTOR2I(MM(x), MM(y))
    rr = dia / 2 + 0.05
    for lay, poly in pours.items():
        if not poly.Contains(pt):
            return "outside-" + board.GetLayerName(lay)
        for k in range(12):
            a = k * math.pi / 6
            q = VECTOR2I(MM(x + rr * math.cos(a)), MM(y + rr * math.sin(a)))
            if not poly.Contains(q):
                return "edge-of-" + board.GetLayerName(lay)
    if frag is not None and not frag.Contains(pt):
        return "not-in-fragment"
    return None


def add_via(x, y, dia, drill):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(VECTOR2I(MM(x), MM(y)))
    v.SetNet(gnd)
    v.SetWidth(MM(dia)); v.SetDrill(MM(drill))
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    board.Add(v)


for rnd in range(8):
    pours, obst, segs, holes = snapshot()
    fcu = pours[pcbnew.F_Cu]
    frags = sorted(((abs(fcu.Outline(i).Area()), i)
                    for i in range(fcu.OutlineCount())), reverse=True)
    stray = []
    for _, i in frags[1:]:
        one = pcbnew.SHAPE_POLY_SET()
        one.AddOutline(fcu.Outline(i))
        if any(isinstance(t, pcbnew.PCB_VIA) and t.GetNetname() == "GND"
               and one.Contains(t.GetPosition()) for t in board.GetTracks()):
            continue
        stray.append((i, one))
    if not stray:
        print("round %d: F.Cu pour has no unstitched fragment" % rnd)
        break
    fixed = 0
    for i, one in stray:
        bb = fcu.Outline(i).BBox()
        x0, y0 = ToMM(bb.GetLeft()), ToMM(bb.GetTop())
        x1, y1 = ToMM(bb.GetRight()), ToMM(bb.GetBottom())
        best, reasons = None, {}
        for dia, drill in SIZES:
            gy = y0
            while gy <= y1 and best is None:
                gx = x0
                while gx <= x1:
                    w = why(gx, gy, dia, drill, pours, obst, segs, holes, one)
                    if w is None:
                        best = (gx, gy, dia, drill); break
                    reasons[w] = reasons.get(w, 0) + 1
                    gx += 0.05
                gy += 0.05
            if best:
                break
        if best:
            add_via(*best)
            print("  fragment #%d %.2fmm2 -> via (%.2f, %.2f) dia %.1f drill %.2f"
                  % (i, abs(fcu.Outline(i).Area()) / 1e12, *best))
            fixed += 1
        else:
            print("  fragment #%d (%.2f,%.2f)-(%.2f,%.2f) %.2fmm2: NO ROOM  %s"
                  % (i, x0, y0, x1, y1, abs(fcu.Outline(i).Area()) / 1e12,
                     sorted(reasons.items(), key=lambda kv: -kv[1])))
    if fixed == 0:
        break

pcbnew.ZONE_FILLER(board).Fill(board.Zones())
board.BuildListOfNets()
board.Save(PCB)
print("saved", PCB)
