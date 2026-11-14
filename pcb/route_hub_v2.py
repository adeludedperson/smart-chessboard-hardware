#!/usr/bin/env python3
"""Import a FreeRouting .ses back into the hub board, stitch the GND pours and
refill.  Run with KiCad's python3.9.

    <kicad-py> route_hub_v2.py /tmp/hub.ses
"""
import os, sys, math
import pcbnew
from pcbnew import VECTOR2I, FromMM as MM, ToMM

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "hub_v2", "chess_hub_v2.kicad_pcb")
SES = sys.argv[1] if len(sys.argv) > 1 else "/tmp/hub.ses"

BW, BH = 88.0, 60.0
VIA_D, VIA_DRILL = 0.7, 0.35
CLR = 0.35                       # extra gap to foreign copper
HOLE_GAP = 0.35                  # hole-to-hole edge gap (rule is 0.2495)
KEEPOUT = (6.5, 1.0, 25.5, 9.2)  # antenna rule area - nothing may go here

board = pcbnew.LoadBoard(PCB)

if os.path.exists(SES):
    ok = pcbnew.ImportSpecctraSES(board, SES)
    print("imported %s ok=%s -> %d tracks/vias"
          % (SES, ok, len(list(board.GetTracks()))))

gnd = board.FindNet("GND")
assert gnd, "no GND net"


def seg_dist(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def snapshot():
    """Refill the pours and re-read every obstacle on the board."""
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
            obst.append((ToMM(pos.x), ToMM(pos.y), hx, hy,
                         p.GetNetname() == "GND"))
            d = max(ToMM(p.GetDrillSize().x), ToMM(p.GetDrillSize().y))
            if d > 0:
                holes.append((ToMM(pos.x), ToMM(pos.y), d / 2.0))
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            pos = t.GetPosition(); r = ToMM(t.GetWidth()) / 2
            obst.append((ToMM(pos.x), ToMM(pos.y), r, r,
                         t.GetNetname() == "GND"))
            holes.append((ToMM(pos.x), ToMM(pos.y), ToMM(t.GetDrill()) / 2.0))
        else:
            s, e = t.GetStart(), t.GetEnd()
            segs.append((ToMM(s.x), ToMM(s.y), ToMM(e.x), ToMM(e.y),
                         ToMM(t.GetWidth()), t.GetNetname() == "GND"))
    return pours, obst, segs, holes


def add_via(x, y, dia, drill):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(VECTOR2I(MM(x), MM(y)))
    v.SetNet(gnd)
    v.SetWidth(MM(dia)); v.SetDrill(MM(drill))
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    board.Add(v)


def legal(x, y, dia, drill, pours, obst, segs, holes, need_inside=None):
    """A `dia` via at x,y: fully inside every GND pour, clear of foreign copper."""
    if not (1.5 < x < BW - 1.5 and 1.5 < y < BH - 1.5):
        return False
    if (KEEPOUT[0] - 0.8 < x < KEEPOUT[2] + 0.8
            and KEEPOUT[1] - 0.8 < y < KEEPOUT[3] + 0.8):
        return False
    # hole-to-hole applies to every drilled hole regardless of net
    for (hx0, hy0, hr) in holes:
        if math.hypot(x - hx0, y - hy0) < drill / 2 + hr + HOLE_GAP:
            return False
    r = dia / 2 + CLR
    for (ox, oy, hx, hy, is_gnd) in obst:
        if is_gnd:
            continue
        if abs(x - ox) < hx + r and abs(y - oy) < hy + r:
            return False
    for (x1, y1, x2, y2, w, is_gnd) in segs:
        if is_gnd:
            continue
        if seg_dist(x, y, x1, y1, x2, y2) < r + w / 2:
            return False
    pt = VECTOR2I(MM(x), MM(y))
    rr = dia / 2 + 0.05
    for lay, poly in pours.items():
        if not poly.Contains(pt):
            return False
        for k in range(8):                       # whole pad inside the pour
            a = k * math.pi / 4
            q = VECTOR2I(MM(x + rr * math.cos(a)), MM(y + rr * math.sin(a)))
            if not poly.Contains(q):
                return False
    if need_inside is not None and not need_inside.Contains(pt):
        return False
    return True


# ---- pass 1: regular stitching grid over the whole board ------------------
pours, obst, segs, holes = snapshot()
print("GND pour layers:", [board.GetLayerName(l) for l in pours])
added, placed = 0, []
STEP = 3.0
y = 3.0
while y < BH - 2.0:
    x = 3.0
    while x < BW - 2.0:
        if (all(math.hypot(x - px, y - py) > 2.0 for px, py in placed)
                and legal(x, y, VIA_D, VIA_DRILL, pours, obst, segs, holes)):
            add_via(x, y, VIA_D, VIA_DRILL)
            placed.append((x, y)); added += 1
        x += STEP
    y += STEP
print("pass 1: %d stitching vias" % added)

# ---- pass 2: hunt down every isolated F.Cu pour fragment ------------------
for attempt in range(6):
    pours, obst, segs, holes = snapshot()
    fcu = pours[pcbnew.F_Cu]
    frags = sorted(((abs(fcu.Outline(i).Area()), i)
                    for i in range(fcu.OutlineCount())), reverse=True)
    stray = [i for _, i in frags[1:]]
    if not stray:
        print("pass 2 round %d: F.Cu pour is a single region" % attempt)
        break
    fixed = 0
    for i in stray:
        one = pcbnew.SHAPE_POLY_SET()
        one.AddOutline(fcu.Outline(i))
        if any(isinstance(t, pcbnew.PCB_VIA) and t.GetNetname() == "GND"
               and one.Contains(t.GetPosition()) for t in board.GetTracks()):
            continue
        bb = fcu.Outline(i).BBox()
        x0, y0 = ToMM(bb.GetLeft()), ToMM(bb.GetTop())
        x1, y1 = ToMM(bb.GetRight()), ToMM(bb.GetBottom())
        best = None
        for dia, drill in ((VIA_D, VIA_DRILL), (0.6, 0.3)):
            gy = y0
            while gy <= y1 and best is None:
                gx = x0
                while gx <= x1:
                    if legal(gx, gy, dia, drill, pours, obst, segs, holes,
                             need_inside=one):
                        best = (gx, gy, dia, drill); break
                    gx += 0.15
                gy += 0.15
            if best:
                break
        if best:
            add_via(*best)
            print("   stitched fragment #%d at (%.2f, %.2f) dia %.1f"
                  % (i, best[0], best[1], best[2]))
            fixed += 1
        else:
            print("   fragment #%d (%.2f,%.2f)-(%.2f,%.2f) %.2fmm2: NO ROOM"
                  % (i, x0, y0, x1, y1, abs(fcu.Outline(i).Area()) / 1e12))
    if fixed == 0:
        break

# ---- drop copper that still cannot reach the net -------------------------
for z in board.Zones():
    if not z.GetIsRuleArea():
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)

pcbnew.ZONE_FILLER(board).Fill(board.Zones())
board.BuildListOfNets()
board.Save(PCB)
print("saved", PCB)

# ---- refresh BOM + placement file from the board as it actually is -------
import csv
LCSC = {"ESP32-WROOM-32E": "C701341", "CH340C": "C84681", "TP4056": "C725790",
        "AMS1117-3.3": "C6186", "74AHCT1G125": "C7470", "SS34": "C8678",
        "PWR": "C221904", "100n": "C5137636", "10k": "C25804", "2k": "C22975",
        "1k": "C21190", "1u": "C15849", "10u": "C15850", "CHG": "C2286",
        "PWR_SLIDE": "", "BOOT": "", "EN": "", "18650": "", "OUT": "",
        "MicroUSB": ""}
rows = {}
for f in board.GetFootprints():
    key = (f.GetValue(), f.GetFPID().GetLibItemName().wx_str())
    rows.setdefault(key, []).append(f.GetReference())
with open(os.path.join(HERE, "hub_v2", "BOM.csv"), "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
    for (val, fpname), refs in sorted(rows.items()):
        w.writerow([val, ",".join(sorted(refs)), fpname, LCSC.get(val, "")])
with open(os.path.join(HERE, "hub_v2", "positions.csv"), "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
    for f in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
        if f.GetReference() in ("J1", "BT1"):   # through-hole, fitted by hand
            continue
        p = f.GetPosition()
        w.writerow([f.GetReference(), "%.3fmm" % ToMM(p.x), "%.3fmm" % -ToMM(p.y),
                    "Top", "%.0f" % f.GetOrientationDegrees()])
print("refreshed BOM.csv + positions.csv")
