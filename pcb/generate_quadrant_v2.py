#!/usr/bin/env python3
"""Smart Chessboard V2 compact quadrant — KiCad 10 generator.

V2 vs v1: 33mm pitch (compact), all-SMT for JLCPCB assembly, per-square
WS2812C-2020 LED (offset +8,+8 from center), UHE4913G omnipolar hall at exact
square center (pin1=OUT, pin2=VDD, pin3=GND — verified from UTC datasheet),
no pull-up resistors (push-pull sensor), 3.3V logic domain, 5V only for LEDs,
2x5 keyed headers.

SMD routing model: every SMD pad that needs a track gets an "escape" — a short
F.Cu stub + via — then all interconnect runs as v1: horizontal spines on F.Cu,
vertical lanes on B.Cu, collision registry with jog search.

Run:  ~/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3.9 generate_quadrant_v2.py [SQUARE_SIZE_MM]
"""
import os, sys, csv
import math
import pcbnew
from pcbnew import VECTOR2I, FromMM as MM

S = float(sys.argv[1]) if len(sys.argv) > 1 else 33.0
N = 4
B = N * S
MIDY = B / 2
KEEPOUT_R = 3.5
TRK_SIG, TRK_PWR = 0.4, 0.8
RAIL5_OFF = -8.0        # 5V rail (LED power) above row center
RAIL3_OFF = 10.5        # 3V3 rail (sensors/logic) below row center, clears LED band and J2
LED_OFF = 8.0           # LED offset from square center (+x,+y)
ESC = 1.8               # escape stub length

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "quadrant_v2", "chess_quadrant_v2.kicad_pcb")
FPLIB = os.path.expanduser("~/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")

def fp(lib, name):
    f = pcbnew.FootprintLoad(os.path.join(FPLIB, lib + ".pretty"), name)
    assert f, f"footprint missing: {lib}:{name}"
    return f

os.makedirs(os.path.dirname(OUT), exist_ok=True)
board = pcbnew.NewBoard(OUT)
nets = {}
def net(nm):
    if nm not in nets:
        n = pcbnew.NETINFO_ITEM(board, nm); board.Add(n); nets[nm] = n
    return nets[nm]
for nm in ["+5V","+3V3","GND","/PL","CP","SER_IN","SER_MID","SER_OUT"]: net(nm)
for i in range(16): net(f"SENS_{i}")
for i in range(17): net(f"LEDD_{i}")

for a,b2 in zip([(0,0),(B,0),(B,B),(0,B)], [(B,0),(B,B),(0,B),(0,0)]):
    sg = pcbnew.PCB_SHAPE(board); sg.SetShape(pcbnew.SHAPE_T_SEGMENT)
    sg.SetStart(VECTOR2I(MM(a[0]),MM(a[1]))); sg.SetEnd(VECTOR2I(MM(b2[0]),MM(b2[1])))
    sg.SetLayer(pcbnew.Edge_Cuts); sg.SetWidth(MM(0.1)); board.Add(sg)

def pad_of(f, num):
    for p in f.Pads():
        if p.GetNumber() == str(num): return p
    raise KeyError(num)
def pad_xy(f, num):
    p = pad_of(f, num).GetPosition()
    return (pcbnew.ToMM(p.x), pcbnew.ToMM(p.y))
def place(footprint, ref, x, y, rot=0.0, value=""):
    footprint.SetReference(ref)
    if value: footprint.SetValue(value)
    board.Add(footprint)
    footprint.SetPosition(VECTOR2I(MM(x), MM(y)))
    footprint.SetOrientationDegrees(rot)
    return footprint
def assign(f, mapping):
    for num, nm in mapping.items(): pad_of(f, num).SetNet(net(nm))
def sq_center(i):
    return ((i % N + .5) * S, (i // N + .5) * S)

# =============================== placement ===============================
sensors, leds, caps = [], [], []

# --- sensors: SOT-23 at square center, rotated so pad3 (GND) faces WEST and
# pads 1(OUT)/2(VDD) sit in an east column.
for i in range(16):
    cx, cy = sq_center(i)
    s = place(fp("Package_TO_SOT_SMD","SOT-23"), f"U{i+1}", cx, cy, value="UHE4913G")
    # rotate until pad3 is west of center
    for rot in (0, 90, 180, 270):
        s.SetOrientationDegrees(rot)
        if pad_xy(s, 3)[0] < cx - 0.3: break
    assign(s, {1: f"SENS_{i}", 2: "+3V3", 3: "GND"})
    sensors.append(s)

# --- LEDs: WS2812B-2020 footprint at (+8,+8). Serpentine chain by square:
# even rows L->R, odd rows R->L. Rotate so DIN (pad3) faces chain input side.
chain = []          # square indices in chain order
for r in range(N):
    cols = range(N) if r % 2 == 0 else range(N-1, -1, -1)
    for c in cols: chain.append(r*N + c)
led_of_sq = {}
for k, sq in enumerate(chain):
    cx, cy = sq_center(sq)
    lx, ly = cx + LED_OFF, cy + LED_OFF
    d = place(fp("LED_SMD","LED_WS2812B-2020_PLCC4_2.0x2.0mm"), f"D{sq+1}", lx, ly, value="WS2812C-2020")
    din_west = (sq // N) % 2 == 0     # even row: chain flows W->E, DIN west
    for rot in (0, 90, 180, 270):
        d.SetOrientationDegrees(rot)
        px = pad_xy(d, 3)[0]
        if (din_west and px < lx - 0.2) or ((not din_west) and px > lx + 0.2):
            break
    assign(d, {1: f"LEDD_{k+1}", 2: "GND", 3: f"LEDD_{k}", 4: "+5V"})
    leds.append(d); led_of_sq[sq] = d

# --- decoupling: 1 per sensor (3V3), 1 per LED (5V), 0603
for i in range(16):
    cx, cy = sq_center(i)
    c = place(fp("Capacitor_SMD","C_0603_1608Metric"), f"C{i+1}", cx-4.5, cy+4.0, rot=90, value="100n")
    assign(c, {1: "+3V3", 2: "GND"})
    caps.append(c)
for i in range(16):
    cx, cy = sq_center(i)
    c = place(fp("Capacitor_SMD","C_0603_1608Metric"), f"C{i+17}", cx+LED_OFF, cy+LED_OFF-3.2, rot=0, value="100n")
    assign(c, {1: "+5V", 2: "GND"})
    caps.append(c)

# --- registers: SOIC-16 in the mid band, rot 90 => two horizontal pad rows
BAND_MID = 2*S + 1.0
u1 = place(fp("Package_SO","SOIC-16_3.9x9.9mm_P1.27mm"), "U17", S,   BAND_MID, rot=90, value="74HC165")
u2 = place(fp("Package_SO","SOIC-16_3.9x9.9mm_P1.27mm"), "U18", 3*S, BAND_MID, rot=90, value="74HC165")

PINMAP = {}
def map_pins(u, upper_sens, lower_sens):
    dpins = [3,4,5,6,11,12,13,14]
    ys = sorted(pad_xy(u,p)[1] for p in dpins)
    ucy = (ys[0] + ys[-1]) / 2
    top = sorted([p for p in dpins if pad_xy(u,p)[1] < ucy], key=lambda p: pad_xy(u,p)[0])
    bot = sorted([p for p in dpins if pad_xy(u,p)[1] >= ucy], key=lambda p: pad_xy(u,p)[0])
    assert len(top)==4 and len(bot)==4
    for pin, sn in zip(top, upper_sens): PINMAP[f"SENS_{sn}"] = (u, pin)
    for pin, sn in zip(bot, lower_sens): PINMAP[f"SENS_{sn}"] = (u, pin)
map_pins(u1, [0,1,4,5],  [8,9,12,13])
map_pins(u2, [2,3,6,7],  [10,11,14,15])
HCCOM = {1:"/PL", 2:"CP", 8:"GND", 15:"GND", 16:"+3V3"}
amap = {**HCCOM, 10:"SER_IN", 9:"SER_MID"}
bmap = {**HCCOM, 10:"SER_MID", 9:"SER_OUT"}
for nm,(u,pin) in PINMAP.items():
    (amap if u is u1 else bmap)[pin] = nm
assign(u1, amap); assign(u2, bmap)

for ref, u in [("C33",u1), ("C34",u2)]:
    ux = pcbnew.ToMM(u.GetPosition().x)
    c = place(fp("Capacitor_SMD","C_0603_1608Metric"), ref, ux+6.5, BAND_MID, rot=90, value="100n")
    assign(c, {1:"+3V3", 2:"GND"})
    caps.append(c)

# bulk cap on 5V near J1
cb = place(fp("Capacitor_SMD","CP_Elec_8x10"), "CB1", 44.0, 96.0, value="1000u/10V")
assign(cb, {1:"+5V", 2:"GND"})

# --- headers 2x6: J1 top edge, J2 bottom edge. INNER row (board side) carries
# the 6 signals and escapes straight down; OUTER row is all GND (pour-connected,
# no routing). Signal-over-ground pairs also make the ribbon quieter.
JSIG = ["/PL", "CP", "SER", "+5V", "+3V3", "LEDD"]
def place_header(ref, x, want_top, value, ser_net, ledd_net):
    j = place(fp("Connector_PinHeader_2.54mm","PinHeader_2x06_P2.54mm_Vertical"), ref, x, 0, value=value)
    for rot in (0, 90, 180, 270):
        j.SetOrientationDegrees(rot)
        ys = [pad_xy(j,k)[1] for k in range(1,13)]
        if max(ys) - min(ys) < 4: break   # 2-row axis vertical
    ys = [pad_xy(j,k)[1] for k in range(1,13)]
    ty = (1.6 - min(ys)) if want_top else (B - 1.6 - max(ys))
    p = j.GetPosition()
    j.SetPosition(VECTOR2I(p.x, p.y + MM(ty)))
    # group pads into columns, assign inner pin = signal, outer pin = GND
    pads = sorted(range(1,13), key=lambda k: (round(pad_xy(j,k)[0],1), pad_xy(j,k)[1]))
    cols = [pads[i:i+2] for i in range(0,12,2)]
    sig_xy = {}
    seq = [ledd_net if s=="LEDD" else (ser_net if s=="SER" else s) for s in JSIG]
    for col, snet in zip(cols, seq):
        inner = max(col, key=lambda k: pad_xy(j,k)[1]) if want_top else min(col, key=lambda k: pad_xy(j,k)[1])
        outer = col[0] if col[1]==inner else col[1]
        pad_of(j, inner).SetNet(net(snet))
        pad_of(j, outer).SetNet(net("GND"))
        sig_xy[snet] = pad_xy(j, inner)
    return j, sig_xy
j1, j1s = place_header("J1", 8.0, True, "IN", "SER_IN", "LEDD_0")
j2, j2s = place_header("J2", 8.0, False, "OUT", "SER_OUT", "LEDD_16")

MH = [(4.5,13.0),(B-4.5,4.5),(B-4.5,B-4.5),(4.5,B-13.0)]   # left two dodge J1/J2
for k,(mx,my) in enumerate(MH):
    place(fp("MountingHole","MountingHole_2.2mm_M2"), f"H{k+1}", mx, my)

# =============================== zones ===============================
def gnd_zone(layer):
    z = pcbnew.ZONE(board); z.SetLayer(layer); z.SetNet(net("GND"))
    pts = pcbnew.VECTOR_VECTOR2I()
    for x,y in [(0.6,0.6),(B-0.6,0.6),(B-0.6,B-0.6),(0.6,B-0.6)]:
        pts.append(VECTOR2I(MM(x),MM(y)))
    z.AddPolygon(pts)
    z.SetLocalClearance(MM(0.35)); z.SetMinThickness(MM(0.25))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetThermalReliefGap(MM(0.4)); z.SetThermalReliefSpokeWidth(MM(0.5))
    z.SetAssignedPriority(0); board.Add(z)
gnd_zone(pcbnew.F_Cu); gnd_zone(pcbnew.B_Cu)

def rule_area(poly_pts):
    z = pcbnew.ZONE(board); z.SetIsRuleArea(True)
    z.SetDoNotAllowZoneFills(True)
    for st in ["SetDoNotAllowTracks","SetDoNotAllowVias","SetDoNotAllowPads","SetDoNotAllowFootprints"]:
        getattr(z, st)(False)
    ls = pcbnew.LSET(); ls.AddLayer(pcbnew.F_Cu); ls.AddLayer(pcbnew.B_Cu)
    z.SetLayerSet(ls)
    pts = pcbnew.VECTOR_VECTOR2I()
    for x,y in poly_pts: pts.append(VECTOR2I(MM(x),MM(y)))
    z.AddPolygon(pts)
    z.SetAssignedPriority(10); board.Add(z)

for i in range(16):
    cx, cy = sq_center(i)
    rule_area([(cx+KEEPOUT_R*math.cos(2*math.pi*k/36), cy+KEEPOUT_R*math.sin(2*math.pi*k/36)) for k in range(36)])
for (mx,my) in MH:
    rule_area([(mx-2.6,my-2.6),(mx+2.6,my-2.6),(mx+2.6,my+2.6),(mx-2.6,my+2.6)])

# =============================== router (v1 core) ===============================
segs = {pcbnew.F_Cu: [], pcbnew.B_Cu: []}
via_pts, hole_pts = [], []
for f in board.GetFootprints():
    for p in f.Pads():
        pos = p.GetPosition(); sz = p.GetSize()
        hx, hy = pcbnew.ToMM(sz.x)/2.0, pcbnew.ToMM(sz.y)/2.0
        if p.GetOrientationDegrees() % 180 > 45: hx, hy = hy, hx
        tht = p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD   # PTH/NPTH block both layers
        hole_pts.append((pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y), p.GetNetname(), hx, hy, tht))
CLR = 0.45
def _hit(a1,a2,b,gap): return min(a1,a2)-gap < b < max(a1,a2)+gap
def seg_clear(x1,y1,x2,y2,nm,w,layer):
    horiz = abs(y1-y2) < 1e-9
    for (ox1,oy1,ox2,oy2,onm,ow) in segs[layer]:
        if onm == nm: continue
        gap = (w+ow)/2 + CLR
        oh = abs(oy1-oy2) < 1e-9
        if horiz and oh:
            if abs(y1-oy1) < gap and max(x1,x2)+gap > min(ox1,ox2) and min(x1,x2)-gap < max(ox1,ox2): return False
        elif (not horiz) and (not oh):
            if abs(x1-ox1) < gap and max(y1,y2)+gap > min(oy1,oy2) and min(y1,y2)-gap < max(oy1,oy2): return False
        else:
            hx1,hx2,hy = (x1,x2,y1) if horiz else (ox1,ox2,oy1)
            vx,vy1,vy2 = (ox1,oy1,oy2) if horiz else (x1,y1,y2)
            if _hit(hx1,hx2,vx,gap) and _hit(vy1,vy2,hy,gap): return False
    for (vx,vy,vnm) in via_pts:
        if vnm == nm: continue
        gap = w/2 + 0.35 + CLR
        if horiz:
            if abs(y1-vy) < gap and _hit(x1,x2,vx,gap): return False
        else:
            if abs(x1-vx) < gap and _hit(y1,y2,vy,gap): return False
    for (px,py,pnm,hx,hy,tht) in hole_pts:
        if pnm == nm: continue
        if layer == pcbnew.B_Cu and not tht: continue   # SMD pads live on F.Cu only
        gx, gy = w/2 + hx + 0.2, w/2 + hy + 0.2
        if horiz:
            if abs(y1-py) < gy and _hit(x1,x2,px,gx): return False
        else:
            if abs(x1-px) < gx and _hit(y1,y2,py,gy): return False
    return True
def raw(x1,y1,x2,y2,nm,w,layer):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(VECTOR2I(MM(x1),MM(y1))); t.SetEnd(VECTOR2I(MM(x2),MM(y2)))
    t.SetNet(net(nm)); t.SetWidth(MM(w)); t.SetLayer(layer); board.Add(t)
    segs[layer].append((x1,y1,x2,y2,nm,w))
def via(x,y,nm):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(VECTOR2I(MM(x),MM(y))); v.SetNet(net(nm))
    v.SetWidth(MM(0.7)); v.SetDrill(MM(0.35)); v.SetViaType(pcbnew.VIATYPE_THROUGH)
    board.Add(v); via_pts.append((x,y,nm))
JOGS = [0.0]+[s*d for d in [0.7,1.4,2.1,2.8,3.5,4.2,4.9,5.6,6.3,7.0,7.7,8.4,9.1,9.8,10.5,11.2] for s in (1,-1)]

def via_clear(x, y, nm):
    for (px,py,pnm,hx,hy,tht) in hole_pts:
        if pnm == nm: continue
        if abs(x-px) < 0.35+hx+0.2 and abs(y-py) < 0.35+hy+0.2: return False
    for (vx,vy,vnm) in via_pts:
        if abs(x-vx) < 1.1 and abs(y-vy) < 1.1 and vnm != nm: return False
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        for (ox1,oy1,ox2,oy2,onm,ow) in segs[layer]:
            if onm == nm: continue
            gap = 0.35 + ow/2 + CLR
            if abs(oy1-oy2) < 1e-9:
                if abs(y-oy1) < gap and _hit(ox1,ox2,x,gap): return False
            else:
                if abs(x-ox1) < gap and _hit(oy1,oy2,y,gap): return False
    return True

def hseg(x1,x2,y,nm,w=TRK_SIG,must=True,exact=False):
    cands = [0.0] if exact else JOGS
    for d in cands:
        if seg_clear(x1,y+d,x2,y+d,nm,w,pcbnew.F_Cu):
            raw(x1,y+d,x2,y+d,nm,w,pcbnew.F_Cu); return y+d
    if must: raise RuntimeError(f"hseg blocked {nm} y={y} x={x1:.1f}..{x2:.1f}")
    return None
def vseg(y1,y2,x,nm,w=TRK_SIG,must=True,exact=False):
    cands = [0.0] if exact else JOGS
    for d in cands:
        if seg_clear(x+d,y1,x+d,y2,nm,w,pcbnew.B_Cu):
            raw(x+d,y1,x+d,y2,nm,w,pcbnew.B_Cu); return x+d
    if must: raise RuntimeError(f"vseg blocked {nm} x={x} y={y1:.1f}..{y2:.1f}")
    return None

def drop(x, ya, yb, nm, w=TRK_SIG):
    lo, hi = min(ya,yb), max(ya,yb)
    for d in JOGS:
        lane = x + d
        if not seg_clear(lane, lo, lane, hi, nm, w, pcbnew.B_Cu): continue
        if abs(d) < 0.01:
            raw(lane, lo, lane, hi, nm, w, pcbnew.B_Cu)
            return
        if not seg_clear(min(x,lane), ya, max(x,lane), ya, nm, w, pcbnew.F_Cu): continue
        if not seg_clear(min(x,lane), yb, max(x,lane), yb, nm, w, pcbnew.F_Cu): continue
        if not via_clear(lane, ya, nm) or not via_clear(lane, yb, nm): continue
        raw(lane, lo, lane, hi, nm, w, pcbnew.B_Cu)
        raw(min(x,lane), ya, max(x,lane), ya, nm, w, pcbnew.F_Cu)
        raw(min(x,lane), yb, max(x,lane), yb, nm, w, pcbnew.F_Cu)
        via(lane, ya, nm); via(lane, yb, nm)
        return
    print(f"DROPDBG {nm} x={x:.2f} y {ya:.1f}->{yb:.1f}:")
    for d in JOGS:
        lane = x + d
        why = None
        if not seg_clear(lane, lo, lane, hi, nm, w, pcbnew.B_Cu):
            for (ox1,oy1,ox2,oy2,onm,ow) in segs[pcbnew.B_Cu]:
                if onm != nm and abs(ox1-ox2) < 1e-9 and abs(lane-ox1) < (w+ow)/2+CLR and max(lo,min(oy1,oy2)) < min(hi,max(oy1,oy2)) + (w+ow)/2+CLR:
                    why = f"Bseg {onm} x={ox1:.2f}"; break
            if not why:
                for (vx,vy,vnm) in via_pts:
                    if vnm != nm and abs(lane-vx) < w/2+0.35+CLR and lo-1 < vy < hi+1:
                        why = f"via {vnm} ({vx:.2f},{vy:.2f})"; break
            if not why:
                for (px,py,pnm,hx,hy,tht) in hole_pts:
                    if pnm != nm and tht and abs(lane-px) < w/2+hx+0.2 and lo-2 < py < hi+2:
                        why = f"THTpad {pnm} ({px:.2f},{py:.2f})"; break
            why = why or "Bseg-cross"
        else:
            why = "jog-stitch/via blocked"
        print(f"  lane {lane:.2f}: {why}")
    raise RuntimeError(f"drop unroutable {nm} x={x} {ya:.1f}->{yb:.1f}")

def corridor(nm, y0, pts, w=TRK_SIG):
    """F.Cu spine near y0 joining via-points/pads [(px,py)]."""
    xs = [p[0] for p in pts]
    x1, x2 = min(xs), max(xs)
    if abs(x2-x1) < 0.01:               # purely vertical connection
        (px, py1), (_, py2) = pts[0], pts[1]
        drop(px, py1, py2, nm, w)
        return py1
    for d in JOGS:
        yy = y0 + d
        if not seg_clear(x1, yy, x2, yy, nm, w, pcbnew.F_Cu): continue
        need_via = [(px,py) for (px,py) in pts if abs(py-yy) > 0.01]
        if any(not via_clear(px, yy, nm) for (px,_) in need_via): continue
        raw(x1, yy, x2, yy, nm, w, pcbnew.F_Cu)
        for (px,py) in need_via:
            via(px, yy, nm)
            drop(px, py, yy, nm, w)
        return yy
    raise RuntimeError(f"corridor unroutable {nm} y0={y0} x={x1:.1f}..{x2:.1f}")

# --- SMD escape: F.Cu stub straight out from pad + via. Returns via point.
def escape(f, num, dirs, dist=ESC, w=TRK_SIG, dbg=False):
    px, py = pad_xy(f, num)
    nm = pad_of(f, num).GetNetname()
    for (dx,dy) in dirs:
        for dd in (dist, dist+0.7, dist+1.4, dist+2.1):
            ex, ey = px + dx*dd, py + dy*dd
            if not (0.8 < ex < B-0.8 and 0.8 < ey < B-0.8):
                if dbg: print(f"  cand ({ex:.1f},{ey:.1f}): off-board")
                continue
            if not seg_clear(min(px,ex),py if dy==0 else min(py,ey),
                             max(px,ex),py if dy==0 else max(py,ey), nm, w,
                             pcbnew.F_Cu):
                if dbg: print(f"  cand ({ex:.1f},{ey:.1f}): stub blocked")
                continue
            if not via_clear(ex, ey, nm):
                if dbg: print(f"  cand ({ex:.1f},{ey:.1f}): via blocked")
                continue
            raw(min(px,ex), min(py,ey), max(px,ex), max(py,ey), nm, w, pcbnew.F_Cu)
            via(ex, ey, nm)
            return (ex, ey)
    if not dbg:
        print(f"DEBUG {f.GetReference()} pad {num} at ({px:.2f},{py:.2f}):")
        for (qx,qy,qn,qhx,qhy,qt) in hole_pts:
            if abs(qx-px) < 6 and abs(qy-py) < 6 and qn != nm:
                print(f"  near pad: {qn} ({qx:.2f},{qy:.2f}) h=({qhx:.2f},{qhy:.2f}) tht={qt}")
        for layer, lab in [(pcbnew.F_Cu,"F"), (pcbnew.B_Cu,"B")]:
            for (ox1,oy1,ox2,oy2,onm,ow) in segs[layer]:
                if onm != nm and min(abs(ox1-px),abs(ox2-px)) < 7 and min(abs(oy1-py),abs(oy2-py)) < 7:
                    print(f"  near seg {lab} {onm} ({ox1:.1f},{oy1:.1f})->({ox2:.1f},{oy2:.1f}) w={ow}")
        for (vx,vy,vn) in via_pts:
            if abs(vx-px) < 6 and abs(vy-py) < 6 and vn != nm:
                print(f"  near via {vn} ({vx:.2f},{vy:.2f})")
        escape(f, num, dirs, dist, w, dbg=True)
    raise RuntimeError(f"escape blocked {f.GetReference()} pad {num} ({nm})")

E, W_, N_, S_ = (1,0), (-1,0), (0,-1), (0,1)

# =============================== power rails ===============================
row5, row3 = [], []
for r_ in range(4):
    cy = (r_+.5)*S
    row5.append(hseg(4.0, B-6.5, cy+RAIL5_OFF, "+5V", TRK_PWR))
    row3.append(hseg(4.0, B-6.5, cy+RAIL3_OFF, "+3V3", TRK_PWR))
x5 = vseg(row5[0], row5[3], 2*S-5.0, "+5V", TRK_PWR)
x3 = vseg(row3[0], row3[3], 2*S+5.0, "+3V3", TRK_PWR)
for r_ in range(4):
    assert via_clear(x5, row5[r_], "+5V"), f"5V trunk via r{r_}"
    via(x5, row5[r_], "+5V")
    assert via_clear(x3, row3[r_], "+3V3"), f"3V3 trunk via r{r_}"
    via(x3, row3[r_], "+3V3")

# =============================== per-square hookup ===============================
sens_via = {}
for i in range(16):
    cx, cy = sq_center(i)
    r_ = i // N
    s = sensors[i]
    corridor_south = (r_ <= 1)          # rows 0,1 route to band below; 2,3 above
    # OUT escape toward corridor side
    p1x, p1y = pad_xy(s, 1)
    vdir = S_ if p1y > cy else N_
    sens_via[i] = escape(s, 1, [vdir, E])
    # VDD escape then drop to 3V3 rail
    vx, vy = escape(s, 2, [N_ if p1y > cy else S_, E])
    drop(vx, vy, row3[r_], "+3V3")
    assert via_clear(vx, row3[r_], "+3V3"), f"U{i+1} 3V3 rail via"
    via(vx, row3[r_], "+3V3")
    # GND: stub west past keepout ring, via into pour
    gx, gy = pad_xy(s, 3)
    ex = cx - (KEEPOUT_R + 1.6)
    if not seg_clear(ex, gy, gx, gy, "GND", TRK_SIG, pcbnew.F_Cu):
        raise RuntimeError(f"U{i+1} GND stub blocked")
    raw(ex, gy, gx, gy, "GND", TRK_SIG, pcbnew.F_Cu)
    assert via_clear(ex, gy, "GND"), f"U{i+1} GND via"
    via(ex, gy, "GND")
    # sensor cap: pad1 -> 3V3 rail, pad2 -> GND pour
    c = caps[i]
    c1x, c1y = pad_xy(c, 1); c2x, c2y = pad_xy(c, 2)
    cv = escape(c, 1, [S_ if c1y > c2y else N_, W_])
    drop(cv[0], cv[1], row3[r_], "+3V3")
    assert via_clear(cv[0], row3[r_], "+3V3"), f"C{i+1} rail via"
    via(cv[0], row3[r_], "+3V3")
    escape(c, 2, [N_ if c1y > c2y else S_, W_])   # via into pour = done

# LEDs: VDD -> 5V rail, VSS -> pour, cap likewise
def free_dirs(px, py, ox, oy):
    """escape dirs pointing away from a 2x2 pad cluster centered at (ox,oy)"""
    dx = 1 if px > ox else -1
    dy = 1 if py > oy else -1
    return [(0,dy), (dx,0)]
for sq, d in led_of_sq.items():
    cx, cy = sq_center(sq)
    r_ = sq // N
    lx, ly = cx + LED_OFF, cy + LED_OFF
    p4x, p4y = pad_xy(d, 4)
    vv = escape(d, 4, free_dirs(p4x, p4y, lx, ly))
    drop(vv[0], vv[1], row5[r_], "+5V")
    assert via_clear(vv[0], row5[r_], "+5V"), f"D{sq+1} 5V rail via"
    via(vv[0], row5[r_], "+5V")
    p2x, p2y = pad_xy(d, 2)
    escape(d, 2, free_dirs(p2x, p2y, lx, ly))   # GND via into pour
    c = caps[sq + 16]
    c1x, c1y = pad_xy(c, 1)
    c2x, c2y = pad_xy(c, 2)
    cv = escape(c, 1, [N_, W_ if c1x < c2x else E])
    drop(cv[0], cv[1], row5[r_], "+5V")
    assert via_clear(cv[0], row5[r_], "+5V"), f"C{sq+17} rail via"
    via(cv[0], row5[r_], "+5V")
    escape(c, 2, [N_, E if c1x < c2x else W_])

# =============================== LED data chain ===============================
led_din_via, led_dout_via = {}, {}
for k, sq in enumerate(chain):
    d = led_of_sq[sq]
    lx = pcbnew.ToMM(d.GetPosition().x)
    p3x, _ = pad_xy(d, 3)
    led_din_via[k]  = escape(d, 3, [W_ if p3x < lx else E])
    p1x, _ = pad_xy(d, 1)
    led_dout_via[k] = escape(d, 1, [E if p1x > lx else W_])

# J pin escapes not needed (THT). Chain: J1 LEDD pin -> D(chain0).DIN
corridor("LEDD_0", sq_center(chain[0])[1] + LED_OFF + 3.0,
         [j1s["LEDD_0"], led_din_via[0]])
for k in range(15):
    a, b_ = led_dout_via[k], led_din_via[k+1]
    same_row = chain[k] // N == chain[k+1] // N
    y0 = (a[1] + b_[1]) / 2 if not same_row else a[1] + 2.5
    corridor(f"LEDD_{k+1}", y0, [a, b_])
corridor("LEDD_16", led_dout_via[15][1] + 2.5, [led_dout_via[15], j2s["LEDD_16"]])

# =============================== control & serial ===============================
# register pin escape vias (top row escapes north, bottom row south)
def reg_escape(u, pin):
    px, py = pad_xy(u, pin)
    ucy = pcbnew.ToMM(u.GetPosition().y)
    return escape(u, pin, [N_ if py < ucy else S_])

u1e = {p: reg_escape(u1, p) for p in [1,2,9,10,16] + [p for nm,(uu,p) in PINMAP.items() if uu is u1]}
u2e = {p: reg_escape(u2, p) for p in [1,2,9,10,16] + [p for nm,(uu,p) in PINMAP.items() if uu is u2]}
# GND pins 8/15: escape + via into pour
for u in (u1, u2):
    ucy = pcbnew.ToMM(u.GetPosition().y)
    for p in (8, 15):
        px, py = pad_xy(u, p)
        escape(u, p, [N_ if py < ucy else S_])

CTRL0 = BAND_MID - 2.0   # corridors run BETWEEN the SOIC pad rows (under the chips)
corridor("/PL",     CTRL0 + 0.0, [j1s["/PL"], u1e[1], u2e[1], j2s["/PL"]])
corridor("CP",      CTRL0 + 1.0, [j1s["CP"], u1e[2], u2e[2], j2s["CP"]])
corridor("SER_IN",  CTRL0 + 2.0, [j1s["SER_IN"], u1e[10]])
corridor("SER_MID", CTRL0 + 3.0, [u1e[9], u2e[10]])
corridor("SER_OUT", CTRL0 + 4.0, [u2e[9], j2s["SER_OUT"]])

for ue, u in [(u1e,u1),(u2e,u2)]:
    vx, vy = ue[16]
    tgt = row3[1] if vy < BAND_MID else row3[2]
    drop(vx, vy, tgt, "+3V3", TRK_PWR)
    assert via_clear(vx, tgt, "+3V3"); via(vx, tgt, "+3V3")
for ref, cc in [("C33", caps[-2]), ("C34", caps[-1])]:
    c1x, c1y = pad_xy(cc, 1); c2x, c2y = pad_xy(cc, 2)
    cv = escape(cc, 1, [N_ if c1y < c2y else S_, E, W_])
    tgt = row3[1] if cv[1] < BAND_MID else row3[2]
    drop(cv[0], cv[1], tgt, "+3V3")
    assert via_clear(cv[0], tgt, "+3V3"), f"{ref} rail via"
    via(cv[0], tgt, "+3V3")
    escape(cc, 2, [S_ if c1y < c2y else N_, E, W_])

# J power pins -> nearest row rails (J1 top -> row0, J2 bottom -> row3)
for js, r5, r3 in [(j1s, row5[0], row3[0]), (j2s, row5[3], row3[3])]:
    drop(js["+5V"][0], js["+5V"][1], r5, "+5V", TRK_PWR)
    assert via_clear(js["+5V"][0], r5, "+5V"); via(js["+5V"][0], r5, "+5V")
    drop(js["+3V3"][0], js["+3V3"][1], r3, "+3V3", TRK_PWR)
    assert via_clear(js["+3V3"][0], r3, "+3V3"); via(js["+3V3"][0], r3, "+3V3")
# bulk cap
cbe = escape(cb, 1, [S_, E, W_, N_], dist=2.4)
drop(cbe[0], cbe[1], row5[3], "+5V", TRK_PWR)
assert via_clear(cbe[0], row5[3], "+5V"); via(cbe[0], row5[3], "+5V")
escape(cb, 2, [S_, E, W_, N_], dist=2.4)

# =============================== SENS fan-in ===============================
def fan(u, ue):
    served = [(nm, pin) for nm,(uu,pin) in PINMAP.items() if uu is u]
    by_row = {}
    for nm, pin in served:
        i = int(nm.split("_")[1])
        by_row.setdefault(i // N, []).append((nm, pin))
    for row, items in by_row.items():
        items.sort(key=lambda t: sens_via[int(t[0].split('_')[1])][0])
        sign = +1 if row <= 1 else -1
        for rank, (nm, pin) in enumerate(items):
            sv = sens_via[int(nm.split("_")[1])]
            corridor(nm, sv[1] + sign*(2.2 + 1.3*rank), [sv, ue[pin]])
fan(u1, u1e); fan(u2, u2e)

# GND stitch along each header's outer (all-GND) pin row -> via into pour,
# guarantees solid thermal connection for the corner pads
for j, js in [(j1, j1s), (j2, j2s)]:
    gpads = [pad_xy(j,k) for k in range(1,13) if pad_of(j,k).GetNetname()=="GND"]
    gy = gpads[0][1]
    xs = [p[0] for p in gpads]
    raw(min(xs), gy, max(xs)+2.5, gy, "GND", TRK_SIG, pcbnew.F_Cu)
    if via_clear(max(xs)+2.5, gy, "GND"): via(max(xs)+2.5, gy, "GND")

# =============================== silk ===============================
def silk(text, x, y, size=1.3):
    t = pcbnew.PCB_TEXT(board); t.SetText(text)
    t.SetPosition(VECTOR2I(MM(x),MM(y))); t.SetLayer(pcbnew.F_SilkS)
    t.SetTextSize(VECTOR2I(MM(size),MM(size))); t.SetTextThickness(MM(size*0.15))
    board.Add(t)
silk(f"CHESS QUADRANT v2 - {S:.0f}mm SMT", B/2, B-2.2, 1.6)
silk("J1 IN", pcbnew.ToMM(j1.GetPosition().x)+11, 4.5, 1.1)
silk("J2 OUT", pcbnew.ToMM(j2.GetPosition().x)+11, B-4.5, 1.1)

# =============================== fill + save ===============================
pcbnew.ZONE_FILLER(board).Fill(board.Zones())
pcbnew.SaveBoard(OUT, board)

# firmware chain order (same logic as v1)
DBIT = {3:4, 4:5, 5:6, 6:7, 11:0, 12:1, 13:2, 14:3}
order = []
for u in (u2, u1):
    by_d = {}
    for nm,(uu,pin) in PINMAP.items():
        if uu is u: by_d[DBIT[pin]] = int(nm.split("_")[1])
    for d_ in range(7, -1, -1):
        order.append(by_d[d_])
print("CHAIN_ORDER (first bit read -> last) =", order)
print("LED_CHAIN (square indices, serpentine) =", chain)

# =============================== BOM + CPL ===============================
# NOTE: C2976072 (WS2812C-2020-V1, the originally-specified LED) is flagged
# "Standard Only" at JLCPCB and forces the whole order off Economic assembly.
# C52917434 (WS2812B-2020-V6) is "Economic and Standard", 418k in stock, and
# is the part this board's footprint (LED_WS2812B-2020_PLCC4_2.0x2.0mm) and
# pad map (1=DOUT 2=GND 3=DIN 4=VDD) were actually drawn for.
# C492423 read 0 stock in the JLC cart despite the parts page showing stock;
# C7501277 is the header that quoted cleanly.
LCSC = {"UHE4913G":"C86815", "WS2812C-2020":"C52917434", "74HC165":"C22384789",
        "100n":"C5137636", "1000u/10V":"C5246577",
        "IN":"C7501277", "OUT":"C7501277"}
rows = {}
for f in board.GetFootprints():
    ref, val = f.GetReference(), f.GetValue()
    if ref.startswith("H"): continue
    fpname = f.GetFPID().GetLibItemName().wx_str()
    rows.setdefault((val, fpname), []).append(ref)
# J1 ("IN") and J2 ("OUT") are the same physical header with different values,
# so grouping by value alone emits two BOM lines pointing at one LCSC part —
# JLCPCB rejects that with "Multiple lines in the BOM have been matched to the
# same part". Collapse rows that share an LCSC number + footprint.
bom = {}
for (val, fpname), refs in sorted(rows.items()):
    lcsc = LCSC.get(val, "")
    key = (lcsc, fpname) if lcsc else (val, fpname)
    if key in bom: bom[key][1].extend(refs)
    else: bom[key] = [val, list(refs), fpname, lcsc]
with open(os.path.join(HERE, "quadrant_v2", "BOM.csv"), "w", newline="") as fh:
    wcsv = csv.writer(fh); wcsv.writerow(["Comment","Designator","Footprint","LCSC Part #"])
    for val, refs, fpname, lcsc in bom.values():
        wcsv.writerow([val, ",".join(sorted(refs)), fpname, lcsc])
with open(os.path.join(HERE, "quadrant_v2", "positions.csv"), "w", newline="") as fh:
    wcsv = csv.writer(fh); wcsv.writerow(["Designator","Mid X","Mid Y","Layer","Rotation"])
    for f in board.GetFootprints():
        ref = f.GetReference()
        # J1/J2 (THT headers) MUST stay in the CPL: JLCPCB Economic assembly
        # does wave/hand-soldered through-hole, and omitting them makes their
        # BOM/CPL cross-check fail with "J1,J2 designators don't exist".
        if ref.startswith("H"): continue
        pos = f.GetPosition()
        wcsv.writerow([ref, f"{pcbnew.ToMM(pos.x):.3f}mm", f"{-pcbnew.ToMM(pos.y):.3f}mm",
                       "Top", f"{f.GetOrientationDegrees():.0f}"])
print(f"saved {OUT}")
print(f"pitch={S} tracks={len(segs[pcbnew.F_Cu])+len(segs[pcbnew.B_Cu])} vias={len(via_pts)}")
