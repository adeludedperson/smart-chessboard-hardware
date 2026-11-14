#!/usr/bin/env python3
"""Smart Chessboard sensor quadrant — KiCad 10 generator (v4).

Key idea: register D-inputs are assigned by PHYSICAL pad row so every SENS
line approaches its pin from its own side (sensors above feed the top row,
sensors below feed the bottom row). Bit order is interleaved; firmware maps
it (table in README). Routing: H on F.Cu, V on B.Cu, via at bends, collision
registry with jog search => no shorts/crossings by construction.

Run:  <kicad python3.9> generate_quadrant.py [SQUARE_SIZE_MM]
"""
import os, sys, math
import pcbnew
from pcbnew import VECTOR2I, FromMM as MM

SQUARE_SIZE = float(sys.argv[1]) if len(sys.argv) > 1 else 45.0
S = SQUARE_SIZE
N = 4
B = N * S
MIDY = B/2
KEEPOUT_R = 8.0
TRK_SIG, TRK_PWR = 0.5, 1.0
RES_OFF = 10.0                     # resistor pad row offset below sensor row
RAIL5_OFF, RAIL3_OFF = -11.0, 13.0

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "quadrant", "chess_quadrant.kicad_pcb")
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
def place(footprint, ref, x, y, rot=0.0, back=False, value=""):
    footprint.SetReference(ref)
    if value: footprint.SetValue(value)
    board.Add(footprint)                       # add BEFORE flip (else segfault)
    footprint.SetPosition(VECTOR2I(MM(x), MM(y)))
    # ORDER MATTERS: rotate FIRST, then flip. Flip() mirrors the pads and folds
    # the mirror into the orientation; calling SetOrientationDegrees() *after*
    # Flip() overwrites that and silently un-mirrors the pad geometry while the
    # footprint stays tagged B.Cu (bug fixed 2026-07-27 — shipped 16 sensors
    # with VCC/OUT swapped in the pre-fix gerbers).
    footprint.SetOrientationDegrees(rot)
    if back: footprint.Flip(footprint.GetPosition(), False)
    return footprint
def move_pad_to(f, num, x, y):
    px, py = pad_xy(f, num)
    p = f.GetPosition()
    f.SetPosition(VECTOR2I(p.x + MM(x-px), p.y + MM(y-py)))
def assign(f, mapping):
    for num, nm in mapping.items(): pad_of(f, num).SetNet(net(nm))
def sq_center(i):
    return ((i%N + .5)*S, (i//N + .5)*S)

# =============================== placement ===============================
sensors, resistors, caps = [], [], []
for i in range(16):
    cx, cy = sq_center(i)
    s = place(fp("Package_TO_SOT_THT","TO-92_Inline"), f"S{i}", cx, cy, back=True, value="A3144")
    move_pad_to(s, 2, cx, cy)
    assign(s, {1:"+5V", 2:"GND", 3:f"SENS_{i}"})
    sensors.append(s)
    rr = place(fp("Resistor_THT","R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal"),
               f"R{i}", cx, cy, value="10k")
    move_pad_to(rr, 1, cx-5.5, cy+RES_OFF)
    assign(rr, {1:f"SENS_{i}", 2:"+3V3"})
    resistors.append(rr)

# sensor decoupling caps: edge columns, pad1 on the row +5V rail, pad2 below (GND pour)
for r_ in range(4):
    cy = (r_+.5)*S
    for k,x in enumerate([11.5, B-11.5]):
        c = place(fp("Capacitor_THT","C_Disc_D5.0mm_W2.5mm_P5.00mm"),
                  f"C{2*r_+k}", x, cy, rot=90, value="100n")
        move_pad_to(c, 1, x, cy+RAIL5_OFF)
        assign(c, {1:"+5V", 2:"GND"})
        caps.append(c)

BAND_TOP = 1.5*S + RAIL3_OFF     # +3V3 rail row1
BAND_BOT = 2.5*S + RAIL5_OFF     # +5V rail row2
BAND_MID = (BAND_TOP + BAND_BOT) / 2
def place_centered(footprint, ref, x, value, rot=0):
    f = place(footprint, ref, x, BAND_MID, rot=rot, value=value)
    ys = [pcbnew.ToMM(p.GetPosition().y) for p in f.Pads()]
    dy = BAND_MID - (min(ys)+max(ys))/2
    pos = f.GetPosition()
    f.SetPosition(VECTOR2I(pos.x, pos.y + MM(dy)))
    return f
u1 = place_centered(fp("Package_DIP","DIP-16_W7.62mm"), "U1", S,   "74HC165", rot=90)
u2 = place_centered(fp("Package_DIP","DIP-16_W7.62mm"), "U2", 3*S, "74HC165", rot=90)

# horizontal DIP-16: two pad ROWS. D-inputs: 3,4,5,6,11,12,13,14.
# Top-row D-pins serve the chip's upper sensors (rows 0,1), bottom-row the lower (rows 2,3),
# ordered left-to-right by pad x. U1 = sensor cols 0,1; U2 = cols 2,3.
PINMAP = {}
def map_pins(u, upper_sens, lower_sens):
    dpins = [3,4,5,6,11,12,13,14]
    ys = sorted(pad_xy(u,p)[1] for p in dpins)
    ucy = (ys[0] + ys[-1]) / 2
    top = sorted([p for p in dpins if pad_xy(u,p)[1] < ucy], key=lambda p: pad_xy(u,p)[0])
    bot = sorted([p for p in dpins if pad_xy(u,p)[1] >= ucy], key=lambda p: pad_xy(u,p)[0])
    assert len(top)==4 and len(bot)==4, (len(top), len(bot))
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

# register decoupling
for ref, u in [("C8",u1), ("C9",u2)]:
    ux = pcbnew.ToMM(u.GetPosition().x)
    c = place(fp("Capacitor_THT","C_Disc_D5.0mm_W2.5mm_P5.00mm"), ref, ux, BAND_MID+8.0, rot=0, value="100n")
    move_pad_to(c, 1, ux-2.5, BAND_MID+8.0)
    assign(c, {1:"+3V3", 2:"GND"})
    caps.append(c)

j1 = place(fp("Connector_PinHeader_2.54mm","PinHeader_1x06_P2.54mm_Vertical"), "J1", 4.5, MIDY, rot=90, value="IN")
move_pad_to(j1, 1, 4.5, BAND_MID-6.35)
assign(j1, {1:"+5V",2:"+3V3",3:"GND",4:"/PL",5:"CP",6:"SER_IN"})
j2 = place(fp("Connector_PinHeader_2.54mm","PinHeader_1x06_P2.54mm_Vertical"), "J2", B-4.5, MIDY, rot=270, value="OUT")
move_pad_to(j2, 1, B-4.5, BAND_MID-6.35)
assign(j2, {1:"+5V",2:"+3V3",3:"GND",4:"/PL",5:"CP",6:"SER_OUT"})

for k,(mx,my) in enumerate([(6,6),(B-6,6),(B-6,B-6),(6,B-6)]):
    place(fp("MountingHole","MountingHole_2.2mm_M2"), f"H{k+1}", mx, my)
MH_KEEPOUT = [(6,6),(B-6,6),(B-6,B-6),(6,B-6)]

# =============================== zones ===============================
def gnd_zone(layer):
    z = pcbnew.ZONE(board); z.SetLayer(layer); z.SetNet(net("GND"))
    pts = pcbnew.VECTOR_VECTOR2I()
    for x,y in [(0.6,0.6),(B-0.6,0.6),(B-0.6,B-0.6),(0.6,B-0.6)]:
        pts.append(VECTOR2I(MM(x),MM(y)))
    z.AddPolygon(pts)
    z.SetLocalClearance(MM(0.4)); z.SetMinThickness(MM(0.3))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetThermalReliefGap(MM(0.5)); z.SetThermalReliefSpokeWidth(MM(0.6))
    z.SetAssignedPriority(0); board.Add(z)
gnd_zone(pcbnew.F_Cu); gnd_zone(pcbnew.B_Cu)

for i in range(16):
    cx, cy = sq_center(i)
    z = pcbnew.ZONE(board); z.SetIsRuleArea(True)
    z.SetDoNotAllowZoneFills(True)
    for st in ["SetDoNotAllowTracks","SetDoNotAllowVias","SetDoNotAllowPads","SetDoNotAllowFootprints"]:
        getattr(z, st)(False)
    ls = pcbnew.LSET(); ls.AddLayer(pcbnew.F_Cu); ls.AddLayer(pcbnew.B_Cu)
    z.SetLayerSet(ls)
    pts = pcbnew.VECTOR_VECTOR2I()
    for k in range(36):
        a = 2*math.pi*k/36
        pts.append(VECTOR2I(MM(cx+KEEPOUT_R*math.cos(a)), MM(cy+KEEPOUT_R*math.sin(a))))
    z.AddPolygon(pts)
    z.SetAssignedPriority(10); board.Add(z)

# pour keep-outs around mounting holes (hole edge to pour < hole_clearance otherwise)
for (mx,my) in MH_KEEPOUT:
    z = pcbnew.ZONE(board); z.SetIsRuleArea(True)
    z.SetDoNotAllowZoneFills(True)
    for st in ["SetDoNotAllowTracks","SetDoNotAllowVias","SetDoNotAllowPads","SetDoNotAllowFootprints"]:
        getattr(z, st)(False)
    ls = pcbnew.LSET(); ls.AddLayer(pcbnew.F_Cu); ls.AddLayer(pcbnew.B_Cu)
    z.SetLayerSet(ls)
    pts = pcbnew.VECTOR_VECTOR2I()
    for dx,dy in [(-2.6,-2.6),(2.6,-2.6),(2.6,2.6),(-2.6,2.6)]:
        pts.append(VECTOR2I(MM(mx+dx), MM(my+dy)))
    z.AddPolygon(pts)
    z.SetAssignedPriority(10); board.Add(z)

# =============================== router ===============================
segs = {pcbnew.F_Cu: [], pcbnew.B_Cu: []}
via_pts, hole_pts = [], []
for f in board.GetFootprints():
    for p in f.Pads():
        pos = p.GetPosition()
        sz = p.GetSize()
        half = max(pcbnew.ToMM(sz.x), pcbnew.ToMM(sz.y)) / 2.0
        hole_pts.append((pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y), p.GetNetname(), half))
CLR = 0.50
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
        gap = w/2 + 0.4 + CLR
        if horiz:
            if abs(y1-vy) < gap and _hit(x1,x2,vx,gap): return False
        else:
            if abs(x1-vx) < gap and _hit(y1,y2,vy,gap): return False
    for (px,py,pnm,half) in hole_pts:
        if pnm == nm: continue
        gap = w/2 + half + 0.22
        if horiz:
            if abs(y1-py) < gap and _hit(x1,x2,px,gap): return False
        else:
            if abs(x1-px) < gap and _hit(y1,y2,py,gap): return False
    return True
def raw(x1,y1,x2,y2,nm,w,layer):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(VECTOR2I(MM(x1),MM(y1))); t.SetEnd(VECTOR2I(MM(x2),MM(y2)))
    t.SetNet(net(nm)); t.SetWidth(MM(w)); t.SetLayer(layer); board.Add(t)
    segs[layer].append((x1,y1,x2,y2,nm,w))
def via(x,y,nm):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(VECTOR2I(MM(x),MM(y))); v.SetNet(net(nm))
    v.SetWidth(MM(0.8)); v.SetDrill(MM(0.4)); v.SetViaType(pcbnew.VIATYPE_THROUGH)
    board.Add(v); via_pts.append((x,y,nm))
JOGS = [0.0]+[s*d for d in [0.8,1.6,2.4,3.2,4.0,4.8,5.6,6.4,7.2,8.0,8.8,9.6,10.4,11.2,12.0] for s in (1,-1)]

def via_clear(x, y, nm):
    """can a via (0.8mm annulus, both layers) live at (x,y)?"""
    for (px,py,pnm,half) in hole_pts:
        if pnm == nm: continue
        g = 0.4 + half + 0.22
        if abs(x-px) < g and abs(y-py) < g: return False
    for (vx,vy,vnm) in via_pts:
        if vnm == nm: continue
        if abs(x-vx) < 1.3 and abs(y-vy) < 1.3: return False
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        for (ox1,oy1,ox2,oy2,onm,ow) in segs[layer]:
            if onm == nm: continue
            gap = 0.4 + ow/2 + CLR
            if abs(oy1-oy2) < 1e-9:   # horizontal
                if abs(y-oy1) < gap and _hit(ox1,ox2,x,gap): return False
            else:
                if abs(x-ox1) < gap and _hit(oy1,oy2,y,gap): return False
    return True

def hseg(x1,x2,y,nm,w=TRK_SIG,must=True,exact=False):
    cands = [0.0] if exact else JOGS
    for d in cands:
        if seg_clear(x1,y+d,x2,y+d,nm,w,pcbnew.F_Cu):
            raw(x1,y+d,x2,y+d,nm,w,pcbnew.F_Cu); return y+d
    if must:
        for d in [0.0]:
            for (px,py,pnm) in hole_pts:
                if pnm != nm and abs(y-py) < 9.5 and x1-1.5 < px < x2+1.5:
                    pass
        near = {}
        for (px,py,pnm,_h) in hole_pts:
            if pnm != nm and abs(py-y) < 9.0 and x1-1.5 < px < x2+1.5:
                near.setdefault(f"pad {pnm} y={py:.1f}", 0); near[f"pad {pnm} y={py:.1f}"] += 1
        for layer in (pcbnew.F_Cu,):
            for (ox1,oy1,ox2,oy2,onm,ow) in segs[layer]:
                if onm != nm and abs(oy1-oy2)<1e-9 and abs(oy1-y) < 9.0 and max(x1,ox1) < min(x2,ox2):
                    near.setdefault(f"seg {onm} y={oy1:.1f}", 0); near[f"seg {onm} y={oy1:.1f}"] += 1
        for k2 in sorted(near): print(f"  HBLOCK {k2} x{near[k2]}")
        raise RuntimeError(f"hseg blocked {nm} y={y} x={x1:.1f}..{x2:.1f}")
    return None

def vseg(y1,y2,x,nm,w=TRK_SIG,must=True,exact=False):
    cands = [0.0] if exact else JOGS
    for d in cands:
        if seg_clear(x+d,y1,x+d,y2,nm,w,pcbnew.B_Cu):
            raw(x+d,y1,x+d,y2,nm,w,pcbnew.B_Cu); return x+d
    if must: raise RuntimeError(f"vseg blocked {nm} x={x} y={y1:.1f}..{y2:.1f}")
    return None

def drop(x, ya, yb, nm, w=TRK_SIG):
    """Atomic vertical connection (x,ya)->(x,yb): B.Cu lane, F.Cu stitches.
    Only commits a candidate when lane + stitches + vias are ALL clear."""
    lo, hi = min(ya,yb), max(ya,yb)
    for d in JOGS:
        lane = x + d
        if not seg_clear(lane, lo, lane, hi, nm, w, pcbnew.B_Cu): continue
        if abs(d) < 0.01:
            raw(lane, lo, lane, hi, nm, w, pcbnew.B_Cu)
            return
        # jogged lane: need exact stitches + vias at both ends
        if not seg_clear(min(x,lane), ya, max(x,lane), ya, nm, w, pcbnew.F_Cu): continue
        if not seg_clear(min(x,lane), yb, max(x,lane), yb, nm, w, pcbnew.F_Cu): continue
        if not via_clear(lane, ya, nm) or not via_clear(lane, yb, nm): continue
        raw(lane, lo, lane, hi, nm, w, pcbnew.B_Cu)
        raw(min(x,lane), ya, max(x,lane), ya, nm, w, pcbnew.F_Cu)
        raw(min(x,lane), yb, max(x,lane), yb, nm, w, pcbnew.F_Cu)
        via(lane, ya, nm); via(lane, yb, nm)
        return
    # debug: report blockers for the straight lane
    lo2, hi2 = min(ya,yb), max(ya,yb)
    for layer,lname in [(pcbnew.B_Cu,'B')]:
        for (ox1,oy1,ox2,oy2,onm,ow) in segs[layer]:
            if onm == nm: continue
            gap = (0.5+ow)/2 + CLR
            if abs(ox1-ox2)<1e-9 and abs(x-ox1) < gap+8 and max(lo2,min(oy1,oy2)) < min(hi2,max(oy1,oy2))+gap:
                print(f"  BLOCKER seg {lname} {onm} x={ox1:.2f} y={oy1:.1f}..{oy2:.1f}")
    for (px,py,pnm) in hole_pts:
        if pnm != nm and abs(x-px) < 9.5 and lo2-1.5 < py < hi2+1.5:
            print(f"  BLOCKER pad {pnm} ({px:.2f},{py:.2f})")
    for (vx,vy,vnm) in via_pts:
        if vnm != nm and abs(x-vx) < 9.5 and lo2-1.5 < vy < hi2+1.5:
            print(f"  BLOCKER via {vnm} ({vx:.2f},{vy:.2f})")
    raise RuntimeError(f"drop unroutable {nm} x={x} {ya:.1f}->{yb:.1f}")

def corridor(nm, y0, xs_pads, w=TRK_SIG):
    """Route horizontal corridor near y0 joining pad points [(px,py)].
    Tries each jog candidate; commits only when spine AND all vias fit."""
    xs = [p[0] for p in xs_pads]
    x1, x2 = min(xs), max(xs)
    for d in JOGS:
        yy = y0 + d
        if not seg_clear(x1, yy, x2, yy, nm, w, pcbnew.F_Cu): continue
        need_via = [(px,py) for (px,py) in xs_pads if abs(py-yy) > 0.01]
        if any(not via_clear(px, yy, nm) for (px,_) in need_via): continue
        raw(x1, yy, x2, yy, nm, w, pcbnew.F_Cu)
        for (px,py) in need_via:
            via(px, yy, nm)
            drop(px, py, yy, nm, w)
        return yy
    raise RuntimeError(f"corridor unroutable {nm} y0={y0} x={x1:.1f}..{x2:.1f}")

# =============================== power ===============================
row5, row3 = [], []
for r_ in range(4):
    cy = (r_+.5)*S
    row5.append(hseg(4.0, B-4.0, cy+RAIL5_OFF, "+5V", TRK_PWR, exact=True))
    row3.append(hseg(4.0, B-4.0, cy+RAIL3_OFF, "+3V3", TRK_PWR))
x5 = vseg(row5[0], row5[3], 2*S-4.0, "+5V", TRK_PWR)
x3 = vseg(row3[0], row3[3], 2*S+4.0, "+3V3", TRK_PWR)
for r_ in range(4):
    assert via_clear(x5, row5[r_], "+5V"); via(x5, row5[r_], "+5V")
    assert via_clear(x3, row3[r_], "+3V3"); via(x3, row3[r_], "+3V3")

for i in range(16):
    s, rr = sensors[i], resistors[i]
    r_ = i//N
    s5x,s5y = pad_xy(s,1); sox,soy = pad_xy(s,3)
    r1x,r1y = pad_xy(rr,1); r2x,r2y = pad_xy(rr,2)
    drop(s5x, s5y, row5[r_], "+5V", TRK_SIG)
    if via_clear(s5x, row5[r_], "+5V"): via(s5x, row5[r_], "+5V")
    else: raise RuntimeError(f"S{i} 5V via blocked")
    # SENS: sensor pad3 -> resistor pad1 (small vertical + horizontal, same cell)
    if abs(sox-r1x) > 0.01:
        corridor(f"SENS_{i}", (soy+r1y)/2, [(sox,soy),(r1x,r1y)])
    else:
        drop(sox, soy, r1y, f"SENS_{i}")
    # GND escape: pad2 sits inside the pour keepout; stub out and via into pour
    sgx, sgy = pad_xy(s, 2)
    gy = sgy + KEEPOUT_R + 1.5
    drop(sgx, sgy, gy, "GND")
    assert via_clear(sgx, gy, "GND"), f"S{i} GND via blocked"
    via(sgx, gy, "GND")
    drop(r2x, r2y, row3[r_], "+3V3", TRK_SIG)
    if via_clear(r2x, row3[r_], "+3V3"): via(r2x, row3[r_], "+3V3")
    else: raise RuntimeError(f"R{i} 3V3 via blocked")

for j,c in enumerate(caps):
    p1x,p1y = pad_xy(c,1)
    if j < 8:
        r_ = j//2
        assert abs(row5[r_] - p1y) < 0.01, f"C{j} pad1 off rail (rail jogged?)"
        # rail passes through pad (same net) -> connected; nothing to add
    else:
        drop(p1x, p1y, row3[1], "+3V3", TRK_PWR)
        assert via_clear(p1x, row3[1], "+3V3"), f"C{j} 3V3 via blocked"
        via(p1x, row3[1], "+3V3")

# =============================== control & serial ===============================
j1p = {k: pad_xy(j1,k) for k in range(1,7)}
j2p = {k: pad_xy(j2,k) for k in range(1,7)}
u1p = {k: pad_xy(u1,k) for k in [1,2,9,10,16]}
u2p = {k: pad_xy(u2,k) for k in [1,2,9,10,16]}
# 5 corridors, 1.0mm apart, centered between DIP pad rows (BAND_MID +/- 3.81)
CTRL0 = BAND_MID - 2.0
corridor("/PL",     CTRL0 + 0.0, [j1p[4], u1p[1], u2p[1], j2p[4]])
corridor("CP",      CTRL0 + 1.0, [j1p[5], u1p[2], u2p[2], j2p[5]])
corridor("SER_IN",  CTRL0 + 2.0, [j1p[6], u1p[10]])
corridor("SER_MID", CTRL0 + 3.0, [u1p[9], u2p[10]])
corridor("SER_OUT", CTRL0 + 4.0, [u2p[9], j2p[6]])

for u in (u1,u2):
    px,py = pad_xy(u,16)
    tgt = row3[1] if py < BAND_MID else row3[2]
    drop(px, py, tgt, "+3V3", TRK_PWR)
    assert via_clear(px, tgt, "+3V3"); via(px, tgt, "+3V3")
for jp in (j1p,j2p):
    drop(jp[1][0], jp[1][1], row5[2], "+5V", TRK_PWR)
    assert via_clear(jp[1][0], row5[2], "+5V"); via(jp[1][0], row5[2], "+5V")
    drop(jp[2][0], jp[2][1], row3[1], "+3V3", TRK_PWR)
    assert via_clear(jp[2][0], row3[1], "+3V3"); via(jp[2][0], row3[1], "+3V3")

# =============================== SENS fan-in ===============================
def fan(u):
    served = [(nm,pin) for nm,(uu,pin) in PINMAP.items() if uu is u]
    ys = sorted(pad_xy(u,p)[1] for _,p in served)
    ucy = (ys[0] + ys[-1]) / 2
    upper = [(nm,pin) for nm,pin in served if pad_xy(u,pin)[1] < ucy]
    lower = [(nm,pin) for nm,pin in served if pad_xy(u,pin)[1] >= ucy]
    # inner sensors (nearer the DIP) get corridors closest to the DIP
    upper.sort(key=lambda t: -pad_xy(resistors[int(t[0].split('_')[1])],1)[1])
    lower.sort(key=lambda t:  pad_xy(resistors[int(t[0].split('_')[1])],1)[1])
    top_row_y = min(pad_xy(u,p)[1] for _,p in served)
    bot_row_y = max(pad_xy(u,p)[1] for _,p in served)
    # corridor lives next to the line's RESISTOR row (sparse area); long
    # vertical drop reaches the register pin. Two lines share a resistor row
    # per chip side -> rank_in_row 0/1, corridors 2.0/3.4mm off the row.
    def route_side(lines, sign):
        by_row = {}
        for nm, pin in lines:
            i = int(nm.split("_")[1])
            by_row.setdefault(i//N, []).append((nm, pin))
        for row, items in by_row.items():
            items.sort(key=lambda t: pad_xy(resistors[int(t[0].split('_')[1])],1)[0])
            for rank,(nm,pin) in enumerate(items):
                px,py = pad_xy(u,pin)
                r1x,r1y = pad_xy(resistors[int(nm.split("_")[1])],1)
                corridor(nm, r1y + sign*(2.0 + 1.4*rank), [(r1x,r1y),(px,py)])
    route_side(upper, +1)   # chip below these resistors -> corridor below row
    route_side(lower, -1)   # chip above -> corridor above row
    return
    top_row_y = min(pad_xy(u,p)[1] for _,p in served)
fan(u1); fan(u2)

# =============================== silk ===============================
def silk(text, x, y, size=1.5):
    t = pcbnew.PCB_TEXT(board); t.SetText(text)
    t.SetPosition(VECTOR2I(MM(x),MM(y))); t.SetLayer(pcbnew.F_SilkS)
    t.SetTextSize(VECTOR2I(MM(size),MM(size))); t.SetTextThickness(MM(size*0.15))
    board.Add(t)
silk(f"SMART CHESS QUADRANT v1 - pitch {S:.1f}mm", B/2, B-2.5, 1.8)
for i in range(16):
    cx, cy = sq_center(i)
    silk(f"S{i}", cx+KEEPOUT_R+4.5, cy, 1.6)
for jp, side in [(j1p,1),(j2p,-1)]:
    for k, nm in {1:"5V",2:"3V3",3:"GND",4:"PL",5:"CP",6:"SER"}.items():
        silk(nm, jp[k][0]+4.2*side, jp[k][1], 0.9)

# =============================== fill + save ===============================
pcbnew.ZONE_FILLER(board).Fill(board.Zones())
pcbnew.SaveBoard(OUT, board)
# firmware bit-order map: chain J1.SER->U1.DS, U1.Q7->U2.DS, U2.Q7->OUT.
# Reading: OUT bit arrives first from U2.D7, then U2.D6..D0, then U1.D7..D0.
DBIT = {3:4, 4:5, 5:6, 6:7, 11:0, 12:1, 13:2, 14:3}   # pin -> D index
order = []
for u in (u2, u1):                                     # U2 shifts out first
    by_d = {}
    for nm,(uu,pin) in PINMAP.items():
        if uu is u: by_d[DBIT[pin]] = int(nm.split("_")[1])
    for d in range(7, -1, -1):                         # D7 first
        order.append(by_d[d])
print("CHAIN_ORDER (first bit read -> last) =", order)
print(f"saved {OUT}")
print(f"pitch={S} tracks={len(segs[pcbnew.F_Cu])+len(segs[pcbnew.B_Cu])} vias={len(via_pts)}")
