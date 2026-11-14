#!/usr/bin/env python3
"""RFID 2x2 test rig — KiCad 10 generator. Mechanical transcription of RIG_PLAN.md.

Run: ~/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3.9 generate_rfid_rig.py
"""
import os, sys, csv, math
import pcbnew
from pcbnew import VECTOR2I, FromMM as MM

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "rfid_test_rig.kicad_pcb")
FPLIB = os.path.expanduser("~/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")

BW, BH = 80.0, 92.0
CLR = 0.15
TRK_SIG, TRK_PWR = 0.3, 0.5
SPIRAL_W = 0.25

def fp(lib, name):
    f = pcbnew.FootprintLoad(os.path.join(FPLIB, lib + ".pretty"), name)
    assert f, f"footprint missing: {lib}:{name}"
    return f

board = pcbnew.NewBoard(OUT)
bds = board.GetDesignSettings()
bds.SetCopperLayerCount(4)
# clearance / track / via defaults
bds.m_MinClearance = MM(CLR)
bds.m_TrackMinWidth = MM(0.2)
bds.m_ViasMinSize = MM(0.6)
bds.m_ViasMinDrill = MM(0.3)

nets = {}
def net(nm):
    if nm not in nets:
        n = pcbnew.NETINFO_ITEM(board, nm); board.Add(n); nets[nm] = n
    return nets[nm]

NETLIST = ["+5V","+3V3","GND","ANT_DRV","DEMOD_IN","DEMOD_OUT","RDY_CLK","SHD",
           "S0","S1","EN0","EN1"]
for i in range(1,5):
    NETLIST += [f"A{i}", f"AM{i}", f"SENS{i}"]
for i in range(5):
    NETLIST.append(f"LEDD{i}")
for nm in NETLIST: net(nm)

# board outline
for a,b2 in zip([(0,0),(BW,0),(BW,BH),(0,BH)], [(BW,0),(BW,BH),(0,BH),(0,0)]):
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

def spiral_pts(r0, n, p=0.5):
    """Square inward spiral per plan formula. Returns list of (x,y) rel points,
    starting at outer corner (+r0,+r0), n turns, pitch p."""
    pts = [(r0, r0)]
    for i in range(n):
        ri = r0 - i*p
        rn = ri - p
        pts += [(-ri, ri), (-ri, -ri), (ri, -ri), (ri, rn)]
    return pts

def mirror_pts(pts, mx=False, my=False):
    return [((-x if mx else x), (-y if my else y)) for (x,y) in pts]

def draw_poly(cx, cy, pts, nm, layer, w=SPIRAL_W):
    """Draw a chain of track segments through abs points (cx+x, cy+y)."""
    for (x1,y1),(x2,y2) in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(VECTOR2I(MM(cx+x1), MM(cy+y1)))
        t.SetEnd(VECTOR2I(MM(cx+x2), MM(cy+y2)))
        t.SetNet(net(nm)); t.SetWidth(MM(w)); t.SetLayer(layer)
        board.Add(t)

def seg(cx, cy, x1, y1, x2, y2, nm, layer, w=SPIRAL_W):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(VECTOR2I(MM(cx+x1), MM(cy+y1)))
    t.SetEnd(VECTOR2I(MM(cx+x2), MM(cy+y2)))
    t.SetNet(net(nm)); t.SetWidth(MM(w)); t.SetLayer(layer)
    board.Add(t)
    if layer in segs:
        segs[layer].append((cx+x1, cy+y1, cx+x2, cy+y2, nm, w))

# Router collision registry -- declared HERE (before coil/inner-zone build)
# so via_at()/seg() calls made during coil construction register themselves
# and get respected by the general router later. Coil spiral copper itself
# (drawn via draw_poly on In1/In2/B) is intentionally NOT added to segs: it's
# single-net and same-net overlaps there are legal per plan; what DOES need
# registering is every via (hot/cold/link) so later F/B routing can't be
# jogged on top of one, which is exactly what caused the A1/A3 shorts.
segs = {pcbnew.F_Cu: [], pcbnew.B_Cu: []}
via_pts, hole_pts = [], []

def via_at(cx, cy, x, y, nm, sz=0.6, dr=0.3):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(VECTOR2I(MM(cx+x), MM(cy+y))); v.SetNet(net(nm))
    v.SetWidth(MM(sz)); v.SetDrill(MM(dr)); v.SetViaType(pcbnew.VIATYPE_THROUGH)
    board.Add(v)
    via_pts.append((cx+x, cy+y, nm))
    return (cx+x, cy+y)

LIN1, LIN2, LB, LF = pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu, pcbnew.F_Cu

def build_coil_stacked(cx, cy, nm, mirror, cold_mx=False):
    """S1/S2: In1+In2+B stacked, 18t each, series chain. mirror negates rel-x
    of all geometry (S2). Returns dict with 'hot' and 'cold_gnd_far' abs pts
    for downstream routing, plus the B-inner-end abs point (already wired)."""
    mx = mirror
    r0 = 14.875; n = 18; p = 0.5

    # In1: normal geometry (no y-mirror). Outer corner (r0,r0); stub to (16.2,r0) = HOT via.
    in1 = spiral_pts(r0, n, p)
    in1 = mirror_pts(in1, mx=mx, my=False)
    # PLAN-DEVIATION: S1's hot via (+16.2) and S2's mirrored hot via (-16.2)
    # both land in the narrow inter-column gap at the same y (both squares'
    # r0 is identical), only 0.6mm apart -- too tight for two vias of
    # different nets. Shorten S2's stub so its via sits further from S1's.
    hotx = 16.2 if not mx else -15.4
    hot_via = via_at(cx, cy, hotx, r0, nm, )
    seg(cx, cy, hotx, r0, in1[0][0], in1[0][1], nm, LIN1)
    draw_poly(cx, cy, in1, nm, LIN1)
    in1_inner = in1[-1]   # (6.375,5.875) or mirrored

    # inner link: In1 stub inner_end -> (4.4,5.5)[mirror x], via
    link_x = 4.4 if not mx else -4.4
    seg(cx, cy, in1_inner[0], in1_inner[1], link_x, 5.5, nm, LIN1)
    link_via = via_at(cx, cy, link_x, 5.5, nm)

    # In2: y-mirrored geometry (independent of square-mirror), same r0/n.
    in2 = spiral_pts(r0, n, p)
    in2 = mirror_pts(in2, mx=mx, my=True)
    in2_outer = in2[0]     # (r0,-r0) or mirrored
    in2_inner = in2[-1]    # (6.375,-5.875) or mirrored
    # In2 inner end -> link_via (straight seg on In2, inner zone is free)
    seg(cx, cy, in2_inner[0], in2_inner[1], link_x, 5.5, nm, LIN2)
    draw_poly(cx, cy, in2, nm, LIN2)
    # In2 outer stub -> (16.1,-16.1), via. PLAN-DEVIATION: S2's mirrored
    # magnitude reduced from 16.1 to 14.0 -- at 16.1 this B-layer connector
    # runs directly through A1's tank-cluster footprint in the inter-column
    # gap (only ~0.6mm clearance, DRC short). 14.0 gives >1mm clearance.
    # TOPOLOGY-FIX: 16.1 -> 15.6 (abs 72.1 for S2) so the B-link vertical
    # clears the E-port vias at rel 16.5 (abs 73.0) with hole clearance.
    stub_mag = 15.6 if not mx else 14.0
    stubx2 = stub_mag if not mx else -stub_mag
    seg(cx, cy, in2_outer[0], in2_outer[1], stubx2, -16.1, nm, LIN2)
    via2 = via_at(cx, cy, stubx2, -16.1, nm)

    # B: normal geometry, r0=14.375 (inset 0.5)
    r0b = 14.375
    b = spiral_pts(r0b, n, p)
    b = mirror_pts(b, mx=mx, my=False)
    b_outer = b[0]
    b_inner = b[-1]
    stubxB = stub_mag if not mx else -stub_mag
    seg(cx, cy, b_outer[0], b_outer[1], stubxB, r0b, nm, LB)
    draw_poly(cx, cy, b, nm, LB)
    # B.Cu vertical from (stubxB, r0b) up to (stubxB,-16.1) meeting In2 via
    seg(cx, cy, stubxB, r0b, stubxB, -16.1, nm, LB)

    # B inner end -> cold via. TOPOLOGY-FIX: cold via follows the INNER-ZONE
    # mirror (cold_mx), not the coil mirror -- the jumper's hot pad is west of
    # its GND pad on mirrored squares, so the via must sit west too, else the
    # hot->via F seg runs through the GND pad (the (58-61,16.6/49.6) shorts).
    coldx = 4.2 if not cold_mx else -4.2
    seg(cx, cy, b_inner[0], b_inner[1], coldx, -3.9, nm, LB)
    cold_via = via_at(cx, cy, coldx, -3.9, nm)

    return {"hot_via": hot_via, "cold_via": cold_via}

def build_coil_bonly(cx, cy, nm, mirror, cold_mx=False):
    """S3/S4: B only, 16t, r0=14.875."""
    mx = mirror
    r0 = 14.875; n = 16; p = 0.5
    b = spiral_pts(r0, n, p)
    b = mirror_pts(b, mx=mx, my=False)
    b_outer = b[0]
    b_inner = b[-1]
    # PLAN-DEVIATION: S3's hot via (+16.1) and S4's mirrored hot via (-16.1)
    # land only 0.8mm apart (same row, y=cy+r0 for both) -- same issue as
    # the S1/S2 pair; shorten S4's stub so the vias sit further apart.
    hotx = 16.1 if not mx else -14.6
    hot_via = via_at(cx, cy, hotx, r0, nm)
    seg(cx, cy, hotx, r0, b_outer[0], b_outer[1], nm, LB)
    draw_poly(cx, cy, b, nm, LB)
    coldx = 4.2 if not cold_mx else -4.2   # TOPOLOGY-FIX: see stacked coil note
    seg(cx, cy, b_inner[0], b_inner[1], coldx, -3.9, nm, LB)
    cold_via = via_at(cx, cy, coldx, -3.9, nm)
    return {"hot_via": hot_via, "cold_via": cold_via}

def build_inner_zone(sn, cx, cy, mx, coilnet, sensnet, din_net, dout_net, cold_via):
    """Hall + LED footprints for one square. mx=True negates rel-x of every
    coordinate (S2/S4 mirror)."""
    M = (lambda x: -x if mx else x)

    # --- Hall UHE4913G SOT-23 @ (0,0) rot0: OUT(-.94,-.95) VDD(-.94,+.95) GND(+.94,0)
    hall = place(fp("Package_TO_SOT_SMD", "SOT-23"), f"U_{sn}H", cx, cy, rot=0, value="UHE4913G")
    want = {"OUT": (M(-0.94), -0.95), "VDD": (M(-0.94), 0.95), "GND": (M(0.94), 0.0)}
    for rot in (0, 90, 180, 270):
        hall.SetOrientationDegrees(rot)
        ok = all(any(abs(pcbnew.ToMM(p.GetPosition().x) - cx - wx) < 0.25 and
                     abs(pcbnew.ToMM(p.GetPosition().y) - cy - wy) < 0.25 for p in hall.Pads())
                  for (wx, wy) in want.values())
        if ok: break
    pin_of = {}
    for role, (wx, wy) in want.items():
        for p in hall.Pads():
            if abs(pcbnew.ToMM(p.GetPosition().x) - cx - wx) < 0.25 and abs(pcbnew.ToMM(p.GetPosition().y) - cy - wy) < 0.25:
                pin_of[role] = p.GetNumber(); break
    assert len(pin_of) == 3, f"{sn} hall pad match failed: {pin_of}"
    assign(hall, {pin_of["OUT"]: sensnet, pin_of["VDD"]: "+3V3", pin_of["GND"]: "GND"})

    # --- LED WS2812 @ (0,+3.9) rot270: DOUT(-.55,4.815) GND(.55,4.815) DIN(.55,2.985) VDD(-.55,2.985)
    lx, ly = cx + M(0.0), cy + 3.9
    led = place(fp("LED_SMD", "LED_WS2812B-2020_PLCC4_2.0x2.0mm"), f"D_{sn}", lx, ly, rot=270, value="WS2812C-2020")
    wantL = {"DOUT": (M(-0.55), 4.815), "GND": (M(0.55), 4.815), "DIN": (M(0.55), 2.985), "VDD": (M(-0.55), 2.985)}
    for rot in (0, 90, 180, 270):
        led.SetOrientationDegrees(rot)
        ok = all(any(abs(pcbnew.ToMM(p.GetPosition().x) - cx - wx) < 0.3 and
                     abs(pcbnew.ToMM(p.GetPosition().y) - cy - wy) < 0.3 for p in led.Pads())
                  for (wx, wy) in wantL.values())
        if ok: break
    lpin = {}
    for role, (wx, wy) in wantL.items():
        for p in led.Pads():
            if abs(pcbnew.ToMM(p.GetPosition().x) - cx - wx) < 0.3 and abs(pcbnew.ToMM(p.GetPosition().y) - cy - wy) < 0.3:
                lpin[role] = p.GetNumber(); break
    assert len(lpin) == 4, f"{sn} LED pad match failed: {lpin}"
    assign(led, {lpin["DOUT"]: dout_net, lpin["GND"]: "GND", lpin["DIN"]: din_net, lpin["VDD"]: "+5V"})

    # --- cold jumper 0R 0603 @ M(-2.6,-3.9) rot0: pad GND at M(-3.375,-3.9), pad A<n> at M(-1.825,-3.9)
    jx, jy = cx + M(-2.6), cy - 3.9
    jump = place(fp("Resistor_SMD", "R_0603_1608Metric"), f"RJ_{sn}", jx, jy, rot=0, value="0R")
    want_j = {"GND": (M(-3.375), -3.9), "HOT": (M(-1.825), -3.9)}
    jpin = {}
    for role, (wx, wy) in want_j.items():
        for p in jump.Pads():
            if abs(pcbnew.ToMM(p.GetPosition().x) - cx - wx) < 0.3 and abs(pcbnew.ToMM(p.GetPosition().y) - cy - wy) < 0.3:
                jpin[role] = p.GetNumber(); break
    assert len(jpin) == 2, f"{sn} jumper pad match failed: {jpin}"
    gnd_pin, hot_pin = jpin["GND"], jpin["HOT"]
    assign(jump, {gnd_pin: "GND", hot_pin: coilnet})
    # jumper HOT pad -> coil cold via (F.Cu, per plan "F seg east y=-3.9 to (4.2,-3.9)")
    hx = pcbnew.ToMM(pad_of(jump, hot_pin).GetPosition().x)
    seg(cx, cy, hx-cx, -3.9, cold_via[0]-cx, cold_via[1]-cy, coilnet, LF, TRK_SIG)
    # jumper GND pad -> west/east into GND zone ring (also acts as zone stitch)
    gx = pcbnew.ToMM(pad_of(jump, gnd_pin).GetPosition().x)
    seg(cx, cy, gx-cx, -3.9, M(-17.0), -3.9, "GND", LF, TRK_SIG)

    # --- F.Cu port crossings (band traversal). End each stub AT the pad center
    # for guaranteed connection (plan's "edge" figures are approximate pad-size
    # derivations; centerpoint landing is electrically identical and DRC-safe).
    hall_out = (cx + M(-0.94), cy - 0.95)
    hall_vdd = (cx + M(-0.94), cy + 0.95)
    hall_gnd = (cx + M(0.94), cy + 0.0)
    # PLAN-DEVIATION (bugfix): the plan's LED pad offsets (4.815/2.985) are
    # already relative to the SQUARE center (matching wantL above, which
    # locates the real pads by the same convention) -- adding the LED's own
    # +3.9 placement offset on top double-counted it, putting these
    # "expected" port-stub endpoints 3.9mm away from the real pads.
    led_dout = (cx + M(-0.55), cy + 4.815)
    led_gnd  = (cx + M(0.55),  cy + 4.815)
    led_din  = (cx + M(0.55),  cy + 2.985)
    led_vdd  = (cx + M(-0.55), cy + 2.985)

    ports = {}
    # W port SENS: y=hall_out.y, from band edge M(-16.5) to hall OUT pad
    wx = cx + M(-16.5)
    seg(cx, cy, M(-16.5), hall_out[1]-cy, hall_out[0]-cx, hall_out[1]-cy, sensnet, LF, TRK_SIG)
    ports["W_SENS"] = via_at(cx, cy, M(-16.5), hall_out[1]-cy, sensnet)
    # W port 3V3
    seg(cx, cy, M(-16.5), hall_vdd[1]-cy, hall_vdd[0]-cx, hall_vdd[1]-cy, "+3V3", LF, TRK_SIG)
    ports["W_3V3"] = via_at(cx, cy, M(-16.5), hall_vdd[1]-cy, "+3V3")
    # W port 5V -> LED VDD pad
    seg(cx, cy, M(-16.5), led_vdd[1]-cy, led_vdd[0]-cx, led_vdd[1]-cy, "+5V", LF, TRK_SIG)
    ports["W_5V"] = via_at(cx, cy, M(-16.5), led_vdd[1]-cy, "+5V")
    # E port GND: hall GND pad east to band ring
    seg(cx, cy, hall_gnd[0]-cx, hall_gnd[1]-cy, M(17.0), 0.0, "GND", LF, TRK_SIG)
    # S port DOUT: vertical from LED DOUT pad south to y=+16.5
    seg(cx, cy, led_dout[0]-cx, led_dout[1]-cy, led_dout[0]-cx, 16.5, dout_net, LF, TRK_SIG)
    ports["S_DOUT"] = via_at(cx, cy, led_dout[0]-cx, 16.5, dout_net)
    # S port GNDled: LED GND pad south to y=+15.9 (zone ring)
    seg(cx, cy, led_gnd[0]-cx, led_gnd[1]-cy, led_gnd[0]-cx, 17.0, "GND", LF, TRK_SIG)
    # S port DIN: vertical x=M(2.2) from y=+16.5 up to LED DIN pad row, then to pad
    seg(cx, cy, M(2.2), 16.5, M(2.2), led_din[1]-cy, din_net, LF, TRK_SIG)
    seg(cx, cy, M(2.2), led_din[1]-cy, led_din[0]-cx, led_din[1]-cy, din_net, LF, TRK_SIG)
    ports["S_DIN"] = via_at(cx, cy, M(2.2), 16.5, din_net)

    return hall, led, lpin, jump, gnd_pin, hot_pin, ports

SQ = {
    "S1": (23.5, 20.5, False, "A1"),
    "S2": (56.5, 20.5, True,  "A2"),
    "S3": (23.5, 53.5, False, "A3"),
    "S4": (56.5, 53.5, True,  "A4"),
}
coil = {}
for sn, (cx, cy, mx, nm) in SQ.items():
    # TOPOLOGY-FIX (root cause of the 3 residual tracks_crossing): coils are
    # NEVER mirrored, even for S2/S4. The coil is x-symmetric except its
    # stubs; only the component/port layout needs mirroring. Unmirrored coils
    # put every hot via on each square's EAST side (S2/S4: abs x~72.6, right
    # margin) instead of stacking S2/S4's hot vias 0.6-1.4mm from S1's in the
    # crowded x~40 inter-column gap. Full-length stubs (16.1/16.2) restored
    # automatically since the mirror branches are no longer taken.
    if sn in ("S1", "S2"):
        coil[sn] = build_coil_stacked(cx, cy, nm, False, cold_mx=mx)
    else:
        coil[sn] = build_coil_bonly(cx, cy, nm, False, cold_mx=mx)

# LEDD chain: J1(LEDD0) -> S3 -> S1 -> S2 -> S4(LEDD4 dangling)
CHAIN = ["S3", "S1", "S2", "S4"]
chain_din = {"S3": "LEDD0", "S1": "LEDD1", "S2": "LEDD2", "S4": "LEDD3"}
chain_dout = {"S3": "LEDD1", "S1": "LEDD2", "S2": "LEDD3", "S4": "LEDD4"}

inner = {}
for sn, (cx, cy, mx, nm) in SQ.items():
    sensnet = {"S1": "SENS1", "S2": "SENS2", "S3": "SENS3", "S4": "SENS4"}[sn]
    inner[sn] = build_inner_zone(sn, cx, cy, mx, nm, sensnet, chain_din[sn], chain_dout[sn], coil[sn]["cold_via"])

# =============================== router (F.Cu/B.Cu general nets) ===============================
def rebuild_hole_pts():
    hole_pts.clear()
    for f in board.GetFootprints():
        for p in f.Pads():
            pos = p.GetPosition(); sz = p.GetSize()
            hx, hy = pcbnew.ToMM(sz.x)/2.0, pcbnew.ToMM(sz.y)/2.0
            if p.GetOrientationDegrees() % 180 > 45: hx, hy = hy, hx
            tht = p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
            hole_pts.append((pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y), p.GetNetname(), hx, hy, tht))

RCLR = 0.2
def _hit(a1,a2,b,gap): return min(a1,a2)-gap < b < max(a1,a2)+gap
def seg_clear(x1,y1,x2,y2,nm,w,layer):
    horiz = abs(y1-y2) < 1e-9
    for (ox1,oy1,ox2,oy2,onm,ow) in segs[layer]:
        if onm == nm: continue
        gap = (w+ow)/2 + RCLR
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
        gap = w/2 + 0.3 + RCLR
        if horiz:
            if abs(y1-vy) < gap and _hit(x1,x2,vx,gap): return False
        else:
            if abs(x1-vx) < gap and _hit(y1,y2,vy,gap): return False
    for (px,py,pnm,hx,hy,tht) in hole_pts:
        if pnm == nm: continue
        if layer == pcbnew.B_Cu and not tht: continue
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
def rvia(x,y,nm,sz=0.6,dr=0.3):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(VECTOR2I(MM(x),MM(y))); v.SetNet(net(nm))
    v.SetWidth(MM(sz)); v.SetDrill(MM(dr)); v.SetViaType(pcbnew.VIATYPE_THROUGH)
    board.Add(v); via_pts.append((x,y,nm))
JOGS = [0.0]+[s*d for d in [0.4,0.8,1.2,1.6,2.0,2.4,2.8,3.2,3.6,4.0,4.4,4.8,5.2,5.6,6.0] for s in (1,-1)]
# Restricted jog sets for verticals that MUST stay in a coil-free margin
# column: the general JOGS list is unaware of coil copper on In1/In2/B, so an
# unconstrained jog can walk a via straight into a square's spiral. West-
# margin jogs may only move further negative (away from the squares);
# east-margin jogs may only move further positive.
JOGS_WMARGIN = [0.0] + [-d for d in [0.4,0.8,1.2,1.6,2.0,2.4,2.8,3.2]]
JOGS_EMARGIN = [0.0] + [d for d in [0.4,0.8,1.2,1.6,2.0,2.4,2.8,3.2]]
# Small-magnitude jogs for the inter-column gap (only ~2.2mm wide) and other
# tight lanes -- keeps a blocked drop from wandering far enough to land
# inside a neighbouring square's coil footprint.
JOGS_SMALL = [0.0]+[s*d for d in [0.3,0.6,0.9,1.2,1.5,1.8,2.1,2.4,2.7,3.0] for s in (1,-1)]

def via_clear(x, y, nm):
    for (px,py,pnm,hx,hy,tht) in hole_pts:
        if pnm == nm: continue
        if abs(x-px) < 0.3+hx+0.2 and abs(y-py) < 0.3+hy+0.2: return False
    for (vx,vy,vnm) in via_pts:
        if abs(x-vx) < 0.9 and abs(y-vy) < 0.9 and vnm != nm: return False
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        for (ox1,oy1,ox2,oy2,onm,ow) in segs[layer]:
            if onm == nm: continue
            gap = 0.3 + ow/2 + RCLR
            if abs(oy1-oy2) < 1e-9:
                if abs(y-oy1) < gap and _hit(ox1,ox2,x,gap): return False
            else:
                if abs(x-ox1) < gap and _hit(oy1,oy2,y,gap): return False
    return True

def hseg(x1,x2,y,nm,w=TRK_SIG,must=True,jogs=None):
    jogs = jogs if jogs is not None else JOGS
    for d in jogs:
        if seg_clear(x1,y+d,x2,y+d,nm,w,pcbnew.F_Cu):
            raw(x1,y+d,x2,y+d,nm,w,pcbnew.F_Cu); return y+d
    if must:
        for (ox1,oy1,ox2,oy2,onm,ow) in segs[pcbnew.F_Cu]:
            if onm == nm: continue
            if abs(oy1-y) < 3 or abs(oy2-y) < 3:
                if max(ox1,ox2) > x1-2 and min(ox1,ox2) < x2+2:
                    print(f"  hseg blocker: {onm} ({ox1:.2f},{oy1:.2f})->({ox2:.2f},{oy2:.2f}) w={ow}")
        raise RuntimeError(f"hseg blocked {nm} y={y} x={x1:.1f}..{x2:.1f}")
    return None
def vseg(y1,y2,x,nm,w=TRK_SIG,must=True):
    for d in JOGS:
        if seg_clear(x+d,y1,x+d,y2,nm,w,pcbnew.B_Cu):
            raw(x+d,y1,x+d,y2,nm,w,pcbnew.B_Cu); return x+d
    if must: raise RuntimeError(f"vseg blocked {nm} x={x} y={y1:.1f}..{y2:.1f}")
    return None

def drop(x, ya, yb, nm, w=TRK_SIG, jogs=None):
    jogs = jogs if jogs is not None else JOGS
    lo, hi = min(ya,yb), max(ya,yb)
    for d in jogs:
        lane = x + d
        if not seg_clear(lane, lo, lane, hi, nm, w, pcbnew.B_Cu): continue
        if abs(d) < 0.01:
            raw(lane, lo, lane, hi, nm, w, pcbnew.B_Cu)
            return lane
        if not seg_clear(min(x,lane), ya, max(x,lane), ya, nm, w, pcbnew.F_Cu): continue
        if not seg_clear(min(x,lane), yb, max(x,lane), yb, nm, w, pcbnew.F_Cu): continue
        if not via_clear(lane, ya, nm) or not via_clear(lane, yb, nm): continue
        raw(lane, lo, lane, hi, nm, w, pcbnew.B_Cu)
        raw(min(x,lane), ya, max(x,lane), ya, nm, w, pcbnew.F_Cu)
        raw(min(x,lane), yb, max(x,lane), yb, nm, w, pcbnew.F_Cu)
        rvia(lane, ya, nm); rvia(lane, yb, nm)
        return lane
    print(f"DROPDBG {nm} x={x:.2f} y {ya:.1f}->{yb:.1f}:")
    lo, hi = min(ya,yb), max(ya,yb)
    for d in JOGS[:12]:
        lane = x + d
        c1 = seg_clear(lane, lo, lane, hi, nm, w, pcbnew.B_Cu)
        c2 = seg_clear(min(x,lane), ya, max(x,lane), ya, nm, w, pcbnew.F_Cu)
        c3 = seg_clear(min(x,lane), yb, max(x,lane), yb, nm, w, pcbnew.F_Cu)
        c4 = via_clear(lane, ya, nm)
        c5 = via_clear(lane, yb, nm)
        print(f"  lane {lane:.2f}: b={c1} fja={c2} fjb={c3} via_a={c4} via_b={c5}")
    lane = x + JOGS[10]
    xx1, xx2 = min(x,lane), max(x,lane)
    for (ox1,oy1,ox2,oy2,onm,ow) in segs[pcbnew.F_Cu]:
        if onm == nm: continue
        if abs(oy1-yb) < 1.0 and abs(oy2-yb) < 1.0 and max(ox1,ox2) > xx1-2 and min(ox1,ox2) < xx2+2:
            print(f"  near F seg at yb: {onm} ({ox1:.2f},{oy1:.2f})->({ox2:.2f},{oy2:.2f}) w={ow}")
    for (px,py,pnm,hx,hy,tht) in hole_pts:
        if pnm == nm: continue
        if abs(py-yb) < 2.0 and xx1-2 < px < xx2+2:
            print(f"  near pad at yb: {pnm} ({px:.2f},{py:.2f}) h=({hx:.2f},{hy:.2f}) tht={tht}")
        if abs(py-ya) < 2.0 and xx1-2 < px < xx2+2:
            print(f"  near pad at ya: {pnm} ({px:.2f},{py:.2f}) h=({hx:.2f},{hy:.2f}) tht={tht}")
    for (vx,vy,vnm) in via_pts:
        if vnm == nm: continue
        if abs(vy-ya) < 2.0 and xx1-2 < vx < xx2+2:
            print(f"  near via at ya: {vnm} ({vx:.2f},{vy:.2f})")
    for (ox1,oy1,ox2,oy2,onm,ow) in segs[pcbnew.B_Cu]:
        if onm == nm: continue
        if abs(ox1-x) < 3 and abs(ox1-ox2) < 1e-9:
            print(f"  B.Cu vertical near x={x}: {onm} x={ox1:.2f} y {oy1:.1f}->{oy2:.1f}")
    for (vx,vy,vnm) in via_pts:
        if vnm == nm: continue
        if abs(vy-yb) < 2.0 and xx1-2 < vx < xx2+2:
            print(f"  near via at yb: {vnm} ({vx:.2f},{vy:.2f})")
    raise RuntimeError(f"drop unroutable {nm} x={x} {ya:.1f}->{yb:.1f}")

def corridor(nm, y0, pts, w=TRK_SIG, jogs=None):
    jogs = jogs if jogs is not None else JOGS
    xs = [p[0] for p in pts]
    x1, x2 = min(xs), max(xs)
    if abs(x2-x1) < 0.01:
        (px, py1), (_, py2) = pts[0], pts[1]
        drop(px, py1, py2, nm, w, jogs=jogs)
        return py1
    for d in jogs:
        yy = y0 + d
        if not seg_clear(x1, yy, x2, yy, nm, w, pcbnew.F_Cu): continue
        need_via = [(px,py) for (px,py) in pts if abs(py-yy) > 0.01]
        if any(not via_clear(px, yy, nm) for (px,_) in need_via): continue
        raw(x1, yy, x2, yy, nm, w, pcbnew.F_Cu)
        for (px,py) in need_via:
            rvia(px, yy, nm)
            drop(px, py, yy, nm, w, jogs=jogs)
        return yy
    for d in JOGS[:16]:
        yy = y0 + d
        c0 = seg_clear(x1, yy, x2, yy, nm, w, pcbnew.F_Cu)
        need_via = [(px,py) for (px,py) in pts if abs(py-yy) > 0.01]
        vcs = [via_clear(px, yy, nm) for (px,_) in need_via]
        print(f"  corridor yy={yy:.2f}: seg={c0} via_clears={vcs}")
    yy = y0
    for (ox1,oy1,ox2,oy2,onm,ow) in segs[pcbnew.F_Cu]:
        if onm == nm: continue
        if abs(oy1-yy) < 4 or abs(oy2-yy) < 4:
            if max(ox1,ox2) > x1-3 and min(ox1,ox2) < x2+3:
                print(f"  candidate blocker F seg {onm} ({ox1:.2f},{oy1:.2f})->({ox2:.2f},{oy2:.2f}) w={ow}")
    raise RuntimeError(f"corridor unroutable {nm} y0={y0} x={x1:.1f}..{x2:.1f}")

def escape(f, num, dirs, dist=1.6, w=TRK_SIG):
    px, py = pad_xy(f, num)
    nm = pad_of(f, num).GetNetname()
    for (dx,dy) in dirs:
        for dd in (dist, dist+0.7, dist+1.4, dist+2.1, dist+2.8):
            ex, ey = px + dx*dd, py + dy*dd
            if not (0.8 < ex < BW-0.8 and 0.8 < ey < BH-0.8): continue
            if not seg_clear(min(px,ex),py if dy==0 else min(py,ey),
                             max(px,ex),py if dy==0 else max(py,ey), nm, w, pcbnew.F_Cu):
                continue
            if not via_clear(ex, ey, nm): continue
            raw(min(px,ex), min(py,ey), max(px,ex), max(py,ey), nm, w, pcbnew.F_Cu)
            rvia(ex, ey, nm)
            return (ex, ey)
    print(f"ESCDBG {f.GetReference()} pad {num} ({nm}) at ({px:.2f},{py:.2f}):")
    for (dx,dy) in dirs:
        for dd in (dist, dist+0.7, dist+1.4):
            ex, ey = px + dx*dd, py + dy*dd
            inb = (0.8 < ex < BW-0.8 and 0.8 < ey < BH-0.8)
            sc = seg_clear(min(px,ex),py if dy==0 else min(py,ey), max(px,ex),py if dy==0 else max(py,ey), nm, w, pcbnew.F_Cu) if inb else None
            vc = via_clear(ex, ey, nm) if inb else None
            print(f"  ({ex:.2f},{ey:.2f}) inb={inb} sc={sc} vc={vc}")
    for layer, lab in [(pcbnew.F_Cu,"F"),(pcbnew.B_Cu,"B")]:
        for (ox1,oy1,ox2,oy2,onm,ow) in segs[layer]:
            if onm == nm: continue
            if min(ox1,ox2)-3 < px+dist < max(ox1,ox2)+3 and min(oy1,oy2)-3 < py < max(oy1,oy2)+3:
                print(f"  near {lab} seg {onm} ({ox1:.2f},{oy1:.2f})->({ox2:.2f},{oy2:.2f}) w={ow}")
    raise RuntimeError(f"escape blocked {f.GetReference()} pad {num} ({nm})")

E, W_, N_, S_ = (1,0), (-1,0), (0,-1), (0,1)
rebuild_hole_pts()

# =============================== strip components ===============================
def place_by_pos(ftpt, ref, cx, cy, want, tol=0.3, rot0=0):
    """Place footprint, search rot in {rot0,90,180,270} for one matching all
    wanted rel pad positions; return {role: pin_number}."""
    ftpt.SetReference(ref); board.Add(ftpt)
    ftpt.SetPosition(VECTOR2I(MM(cx), MM(cy)))
    for rot in (rot0, rot0+90, rot0+180, rot0+270):
        ftpt.SetOrientationDegrees(rot % 360)
        ok = all(any(abs(pcbnew.ToMM(p.GetPosition().x)-cx-wx) < tol and
                     abs(pcbnew.ToMM(p.GetPosition().y)-cy-wy) < tol for p in ftpt.Pads())
                  for (wx,wy) in want.values())
        if ok: break
    pins = {}
    for role,(wx,wy) in want.items():
        for p in ftpt.Pads():
            if abs(pcbnew.ToMM(p.GetPosition().x)-cx-wx) < tol and abs(pcbnew.ToMM(p.GetPosition().y)-cy-wy) < tol:
                pins[role] = p.GetNumber(); break
    assert len(pins) == len(want), f"{ref} pad match failed: got {pins} want {want}"
    return pins

# --- U1 EM4095 SOIC-16 @ (14,79) rot0
U1X, U1Y = 14.0, 79.0
u1 = place(fp("Package_SO", "SOIC-16_3.9x9.9mm_P1.27mm"), "U1", U1X, U1Y, rot=0, value="EM4095")
U1PIN = {1:"GND",2:"RDY_CLK",3:"ANT1",4:"+5V",5:"GND",6:"GND",7:"+5V",8:"DEMOD_IN",
         9:"CDECO",10:"CDECI",11:"AGND_N",12:"GND",13:"DEMOD_OUT",14:"SHD",15:"FCAP",16:"DC2"}
for nm in ("ANT1","CDECO","CDECI","AGND_N","FCAP","DC2"): net(nm)
assign(u1, {str(k): v for k,v in U1PIN.items()})

# --- R1 33R 0805 @ (8.5,73.2): pad2(E)=ANT1, pad1(W)=ANT_DRV
r1 = fp("Resistor_SMD", "R_0805_2012Metric")
r1.SetValue("33R")
r1p = place_by_pos(r1, "R1", 8.5, 73.2, {"W": (-1.0,0.0), "E": (1.0,0.0)}, rot0=0)
assign(r1, {r1p["W"]: "ANT_DRV", r1p["E"]: "ANT1"})
# R1 pad2(ANT1) -> U1 pin3(ANT1): route north then east, west of U1's body.
_r1e = pad_xy(r1, r1p["E"]); _u1p3 = pad_xy(u1, "3")
# DRC-FIX: the old route's vertical at x=9.41 walled off U1 pin2's west
# escape (RDY_CLK). Go east over the body, down the pad-column gap (x=13.9,
# between columns 12.5..15.5), then west into pin3.
seg(0, 0, _r1e[0], _r1e[1], 10.3, _r1e[1], "ANT1", LF, TRK_SIG)
seg(0, 0, 10.3, _r1e[1], 10.3, 72.9, "ANT1", LF, TRK_SIG)
seg(0, 0, 10.3, 72.9, 13.9, 72.9, "ANT1", LF, TRK_SIG)
seg(0, 0, 13.9, 72.9, 13.9, _u1p3[1], "ANT1", LF, TRK_SIG)
seg(0, 0, 13.9, _u1p3[1], _u1p3[0], _u1p3[1], "ANT1", LF, TRK_SIG)

# --- C_dv1 47pF 0603 r90 @ (5.4,76.0): pad1=ANT_DRV pad2=DEMOD_IN (N/S after r90)
cdv1 = fp("Capacitor_SMD", "C_0603_1608Metric"); cdv1.SetValue("47pF")
cdv1p = place_by_pos(cdv1, "C_dv1", 5.4, 76.0, {"N": (0.0,-0.8), "S": (0.0,0.8)}, rot0=90)
assign(cdv1, {cdv1p["N"]: "ANT_DRV", cdv1p["S"]: "DEMOD_IN"})

# --- C_dv2 1.5nF 0603 rot0 @ (7.6,85.2): pad1 taps DEMOD_IN, pad2 GND
cdv2 = fp("Capacitor_SMD", "C_0603_1608Metric"); cdv2.SetValue("1.5nF")
cdv2p = place_by_pos(cdv2, "C_dv2", 7.6, 85.2, {"W": (-0.8,0.0), "E": (0.8,0.0)}, rot0=0)
assign(cdv2, {cdv2p["W"]: "DEMOD_IN", cdv2p["E"]: "GND"})
# DEMOD_IN chain: cdv1.S -> cdv2.W -> U1 pin8 (net-assigned above but never
# actually wired with copper).
# Routed on B.Cu at cdv2's own x (6.83, clear of the SENS1 west-margin
# column at 4.8) via the router, so later crossings auto-avoid it.
_dv1s = pad_xy(cdv1, cdv1p["S"]); _dv2w = pad_xy(cdv2, cdv2p["W"]); _u1p8 = pad_xy(u1, "8")
_dicol = _dv2w[0]
seg(0, 0, _dv1s[0], _dv1s[1], _dicol, _dv1s[1], "DEMOD_IN", LF, TRK_SIG)
rvia(_dicol, _dv1s[1], "DEMOD_IN")
vseg(_dv1s[1], _dv2w[1], _dicol, "DEMOD_IN")
rvia(_dicol, _u1p8[1], "DEMOD_IN")
vseg(_dv2w[1], _u1p8[1], _dicol, "DEMOD_IN")
seg(0, 0, _dicol, _u1p8[1], _u1p8[0], _u1p8[1], "DEMOD_IN", LF, TRK_SIG)

# --- C_dec 100nF r90 @ (19.4,83.4): bridges pin9(CDECO)/pin10(CDECI)
cdec = fp("Capacitor_SMD", "C_0603_1608Metric"); cdec.SetValue("100nF")
cdecp = place_by_pos(cdec, "C_dec", 19.4, 83.4, {"N": (0.0,-0.8), "S": (0.0,0.8)}, rot0=90)
assign(cdec, {cdecp["N"]: "CDECO", cdecp["S"]: "CDECI"})

# --- C_agnd 220nF rot0 @ (19.4,80.9): pad1->AGND_N(pin11), pad2->GND
cagnd = fp("Capacitor_SMD", "C_0603_1608Metric"); cagnd.SetValue("220nF")
cagndp = place_by_pos(cagnd, "C_agnd", 19.4, 80.9, {"W": (-0.8,0.0), "E": (0.8,0.0)}, rot0=0)
assign(cagnd, {cagndp["W"]: "AGND_N", cagndp["E"]: "GND"})

# --- C_dc2 @ (19.4,74.9): pad1->pin16(DC2), pad2 GND. Value 10nF (AN404
# default; allowed 6.8-22nF) -- 6.8nF has no confirmed JLC part.
cdc2 = fp("Capacitor_SMD", "C_0603_1608Metric"); cdc2.SetValue("10n_0603")
cdc2p = place_by_pos(cdc2, "C_dc2", 19.4, 74.9, {"W": (-0.8,0.0), "E": (0.8,0.0)}, rot0=0)
assign(cdc2, {cdc2p["W"]: "DC2", cdc2p["E"]: "GND"})

# --- C_fcap 10nF rot0 @ (19.4,76.4): pad1->pin15(FCAP), pad2 GND
cfcap = fp("Capacitor_SMD", "C_0603_1608Metric"); cfcap.SetValue("10nF")
cfcapp = place_by_pos(cfcap, "C_fcap", 19.4, 76.4, {"W": (-0.8,0.0), "E": (0.8,0.0)}, rot0=0)
assign(cfcap, {cfcapp["W"]: "FCAP", cfcapp["E"]: "GND"})

# Direct hookups: these caps sit near their U1 pin by placement but were
# never actually wired to it (net name alone doesn't make copper).
def stub_to_u1(pad_pt, pin, nm, approach_x=None, vertical_first=False):
    px, py = pad_pt
    ux, uy = pad_xy(u1, pin)
    ax = approach_x if approach_x is not None else ux
    if vertical_first:
        # move to the pin's own row BEFORE approaching its x -- avoids
        # grazing a neighbouring pin's pad when the two pins are on the
        # same column only ~1.27mm apart.
        seg(0, 0, px, py, px, uy, nm, LF, TRK_SIG)
        seg(0, 0, px, uy, ux, uy, nm, LF, TRK_SIG)
        return
    seg(0, 0, px, py, ax, py, nm, LF, TRK_SIG)
    seg(0, 0, ax, py, ax, uy, nm, LF, TRK_SIG)
    if ax != ux:
        seg(0, 0, ax, uy, ux, uy, nm, LF, TRK_SIG)
# cdec.N(82.6)->pin9(83.445, below) and cdec.S(84.2)->pin10(82.175, above)
# are on ADJACENT pins only 1.27mm apart AND on the same x column as the
# OTHER cap pad, so a plain vertical_first stub for CDECO grazes CDECI's own
# S pad (0.13mm actual, needs 0.2mm). DRC-FIX clearance: exit CDECO
# horizontally off the cap's own x column (18.0, clear of both cap pads)
# at the N pad's own row *before* dropping to pin9's row.
_cdecn = pad_xy(cdec, cdecp["N"]); _u1p9 = pad_xy(u1, "9")
seg(0, 0, _cdecn[0], _cdecn[1], 18.0, _cdecn[1], "CDECO", LF, TRK_SIG)
seg(0, 0, 18.0, _cdecn[1], 18.0, _u1p9[1], "CDECO", LF, TRK_SIG)
seg(0, 0, 18.0, _u1p9[1], _u1p9[0], _u1p9[1], "CDECO", LF, TRK_SIG)
# CDECI (S pad, y=84.2) targets pin10 (y=82.175) which is ABOVE it -- a
# direct path crosses right through CDECO's own N->pin9 route at x=19.4.
# Detour further south and around instead. DRC-FIX tracks_crossing: the old
# detour column (18.5) sat inside CDECO's new horizontal span [18.0,19.4] at
# y=83.445 -- move the detour column to 15.0 (west of pin9/10's own x=16.475
# and clear of CDECO's [18.0,19.4] span entirely).
_cdecs = pad_xy(cdec, cdecp["S"]); _u1p10 = pad_xy(u1, "10")
seg(0, 0, _cdecs[0], _cdecs[1], _cdecs[0], 84.85, "CDECI", LF, TRK_SIG)
seg(0, 0, _cdecs[0], 84.85, 15.0, 84.85, "CDECI", LF, TRK_SIG)
seg(0, 0, 15.0, 84.85, 15.0, _u1p10[1], "CDECI", LF, TRK_SIG)
seg(0, 0, 15.0, _u1p10[1], _u1p10[0], _u1p10[1], "CDECI", LF, TRK_SIG)
stub_to_u1(pad_xy(cagnd, cagndp["W"]), "11", "AGND_N")
stub_to_u1(pad_xy(cdc2, cdc2p["W"]), "16", "DC2")
stub_to_u1(pad_xy(cfcap, cfcapp["W"]), "15", "FCAP")

# --- C_vdd / C_dvdd 100nF, west of U1, near pin7/pin4 (worker's choice per plan)
# DRC-FIX: centre pulled west 0.5mm (9.0->8.5) -- at 9.0 the cap's east
# courtyard edge (10.505) overlapped U1's west courtyard edge (10.275) by
# 0.23mm. 0.5mm shift gives ~0.27mm clearance instead.
cvdd = fp("Capacitor_SMD", "C_0603_1608Metric"); cvdd.SetValue("100nF")
cvddp = place_by_pos(cvdd, "C_vdd", 8.5, 82.5, {"W": (-0.8,0.0), "E": (0.8,0.0)}, rot0=0)
assign(cvdd, {cvddp["W"]: "+5V", cvddp["E"]: "GND"})
cdvdd = fp("Capacitor_SMD", "C_0603_1608Metric"); cdvdd.SetValue("100nF")
cdvddp = place_by_pos(cdvdd, "C_dvdd", 8.5, 78.4, {"W": (-0.8,0.0), "E": (0.8,0.0)}, rot0=0)
assign(cdvdd, {cdvddp["W"]: "+5V", cdvddp["E"]: "GND"})
# DRC-FIX starved_thermal: both C_vdd's and C_dvdd's GND pads had only 1
# zone spoke connected. Short stub east into open pour gives each a second
# spoke. DRC-FIX clearance: stub shortened to 0.6mm (was 1.0mm) -- U1's
# pin4/pin7 pads are 1.95mm wide (half=0.975mm off their x=11.525 centre,
# i.e. left edge at 10.55), and a 1.0mm stub from x=9.275 reached to
# 10.275, only 0.125mm clear (needs 0.2mm).
_cv_gnd = pad_xy(cvdd, cvddp["E"])
seg(0, 0, _cv_gnd[0], _cv_gnd[1], _cv_gnd[0]+0.6, _cv_gnd[1], "GND", LF, TRK_SIG)
# DRC-FIX starved_thermal (still short a spoke): the east stub runs into
# copper-dense territory near U1's pins -- try south into more open pour.
_cdv_gnd = pad_xy(cdvdd, cdvddp["E"])
seg(0, 0, _cdv_gnd[0], _cdv_gnd[1], _cdv_gnd[0]+0.6, _cdv_gnd[1], "GND", LF, TRK_SIG)
seg(0, 0, _cdv_gnd[0], _cdv_gnd[1], _cdv_gnd[0], _cdv_gnd[1]+0.6, "GND", LF, TRK_SIG)

# --- U2/U3 74HC4851 TSSOP-16 @ (32,79)/(48,79) rot0
MUXPIN = {1:None,2:None,3:"ZTIE",4:None,5:None,6:"EN",7:"GND",8:"GND",
          9:"GND",10:"S1",11:"S0",12:None,13:"Y0",14:"Y1",15:None,16:"+3V3"}
def build_mux(ref, mx, en_net, y0_net, y1_net):
    u = fp("Package_SO", "TSSOP-16_4.4x5mm_P0.65mm")
    u.SetReference(ref); u.SetValue("74HC4851PW"); board.Add(u)
    u.SetPosition(VECTOR2I(MM(mx), MM(79))); u.SetOrientationDegrees(0)
    ROLE = {"ZTIE": "ANT_DRV", "EN": en_net, "Y0": y0_net, "Y1": y1_net}
    mapping = {}
    for pin, role in MUXPIN.items():
        if role is None: continue
        nm = ROLE.get(role, role)   # GND/S0/S1/+3V3 pass through directly
        mapping[str(pin)] = nm
    assign(u, mapping)
    return u
u2 = build_mux("U2", 32.0, "EN0", "A1", "A3")
u3 = build_mux("U3", 48.0, "EN1", "A2", "A4")

# --- clamp/tank clusters per antenna at drop-lane x
# PLAN-DEVIATION: A1/A3 and A2/A4 lanes widened by 0.5mm each (40.6->41.1,
# 37.2->36.7, 73.6->74.1, 68.5->68.0) -- at the plan's spacing the tank-cap
# clusters and the neighbouring square's coil-descent plumbing (S2's B-layer
# In2 connector, S1's own hot-via column) end up under 1mm apart.
# A1 shifted east 0.3 so its 0805 pair clears A3's wider 1206 pair (A3 must
# stay at 36.7 -- moving it west collides with U2's pin16 escape / A3 lane).
CLUSTER = {"A1": (41.6, "10n", u2, "13"), "A3": (36.7, "100n_1206", u2, "14"),
           "A2": (74.1, "10n", u3, "13"), "A4": (68.0, "100n_1206", u3, "14")}
cluster_top = {}
cluster_row = {}   # per-net: placeholder (see cluster build)
cluster_bN = {}    # per-net: the 'b' cap's N pad (for the dynamic tie row)
for an, (lx, tval, mu, mupin) in CLUSTER.items():
    n = an[1]
    amnet = f"AM{n}"
    # tank caps 0805 r90 @ (x-1.1,71.5) and (x+1.1,71.5): top=A<n>, bottom=GND.
    # DRC-FIX courtyards_overlap: 0805 courtyard is 2.01mm wide -- the old
    # 0.8mm offset (1.6mm pitch) overlapped the two tank caps' own courtyards
    # by 0.41mm, and put them only 2.5mm (y) from the zener row (courtyard
    # half-heights 1.725+1.275=3.0mm needed) so every tank/zener pair also
    # overlapped. Widened to 1.1mm offset (2.2mm pitch, 0.19mm clear) and
    # row raised 0.8mm (72.3->71.5, 3.3mm from the zener row, 0.3mm clear).
    # Zener row (74.8) is untouched -- moving it instead risked a NEW
    # overlap against U2/U3's courtyard edge, which the A3/A4 zeners sit
    # close to.
    TANK_Y = 71.2 if tval == "100n_1206" else 71.5   # taller 1206s clear the zener row
    tank_a_N = tank_a_S = None
    # ZERO-SOLDER: S3/S4 tanks use 2x 100nF C0G 1206 (C97946) = 200nF ->
    # 8.3uH resonates at 123.6kHz, inside EM4095's 100-150kHz capture range.
    # Factory-populated; no post-measurement hand-fitting needed. 1206 needs
    # a wider two-cap pitch (+-1.5) than the 0805 tanks (+-1.1).
    _is1206 = tval == "100n_1206"
    _pitch = 1.5 if _is1206 else 1.1
    _pw = 1.475 if _is1206 else 1.0   # rot90 pad y-offset differs per package
    for tag, tx in (("a", lx-_pitch), ("b", lx+_pitch)):
        c = fp("Capacitor_SMD", "C_1206_3216Metric" if _is1206 else "C_0805_2012Metric")
        cp = place_by_pos(c, f"CT{n}{tag}", tx, TANK_Y, {"N": (0.0,-_pw), "S": (0.0,_pw)}, rot0=90)
        c.SetValue(tval)
        assign(c, {cp["N"]: an, cp["S"]: "GND"})
        if tag == "a":
            tank_a_N = pad_xy(c, cp["N"]); tank_a_S = pad_xy(c, cp["S"])
        else:
            cluster_row[an] = None  # placeholder, set below
            cluster_bN[an] = pad_xy(c, cp["N"])
    # zeners SOD-523: Da r90 @ (x-0.8,74.8) top=A<n> bottom=AM<n>; Db r270 @ (x+0.8,74.8) top=AM<n> bottom=GND
    da = fp("Diode_SMD", "D_SOD-523")
    dap = place_by_pos(da, f"D{n}a", lx-0.8, 74.8, {"N": (0.0,-0.75), "S": (0.0,0.75)}, rot0=90)
    da.SetValue("15V_SOD523")
    assign(da, {dap["N"]: an, dap["S"]: amnet})
    da_N = pad_xy(da, dap["N"]); da_S = pad_xy(da, dap["S"])
    db = fp("Diode_SMD", "D_SOD-523")
    dbp = place_by_pos(db, f"D{n}b", lx+0.8, 74.8, {"N": (0.0,-0.75), "S": (0.0,0.75)}, rot0=270)
    db.SetValue("15V_SOD523")
    assign(db, {dbp["N"]: amnet, dbp["S"]: "GND"})
    db_N = pad_xy(db, dbp["N"])
    # AM<n> midpoint stitch: Da.S -> Db.N
    seg(0, 0, da_S[0], da_S[1], db_N[0], db_N[1], amnet, LF, TRK_SIG)
    # A<n> bus: tank-a.N -> zener-a.N. DRC-FIX tracks_crossing + clearance:
    # a same-layer F.Cu jog here either (a) runs through the tank cap's own
    # GND(S) pad (same x column) or (b) a lateral detour big enough to clear
    # that pad lands inside the NEIGHBOURING lane's tank cap (lanes are only
    # 4.4mm apart). Route this short hop on B.Cu instead -- it's genuinely
    # empty copper here (no coil, no pour) so the pad-avoidance geometry
    # doesn't have to fight either neighbour. Two vias: down at tank-a.N,
    # back up at zener-a.N (which also physically lands the via on the
    # zener's own F.Cu pad).
    via_at(0, 0, tank_a_N[0], tank_a_N[1], an)
    seg(0, 0, tank_a_N[0], tank_a_N[1], da_N[0], da_N[1], an, LB, TRK_SIG)
    via_at(0, 0, da_N[0], da_N[1], an)
    # Continue on B.Cu past the AM<n> stitch's row (~75.5) and the zener's
    # own S(AM) pad (same x column as da_N) before resurfacing -- avoids the
    # tracks_crossing against the stitch and the pad-to-pad clearance hit
    # that a same-layer jog through this same footprint would cause.
    feed_y = 78.675 if n in ("1","2") else 78.025
    below_am_y = da_S[1] + 0.4
    seg(0, 0, da_N[0], da_N[1], lx, below_am_y, an, LB, TRK_SIG)
    via_at(0, 0, lx, below_am_y, an)
    # back on F.Cu: straight down through the TP5-8 test-point column (they
    # sit at y=77.5, between below_am_y and feed_y) to the mux-feed row,
    # then west/east to the mux pin.
    seg(0, 0, lx, below_am_y, lx, feed_y, an, LF, TRK_SIG)
    mupinxy = pad_xy(mu, mupin)
    seg(0, 0, lx, feed_y, mupinxy[0], feed_y, an, LF, TRK_SIG)
    seg(0, 0, mupinxy[0], feed_y, mupinxy[0], mupinxy[1], an, LF, TRK_SIG)
    cluster_top[an] = (tank_a_N[0], tank_a_N[1])   # top junction point for the drop-in from the square
    # DRC-FIX starved_thermal (CT4a GND pad, 1 spoke connected): short stub
    # from every tank cap's own GND(S) pad out to its west/east side (away
    # from the other tank cap and the zener row) into open pour.
    stub_dx = -0.9 if tank_a_S[0] < lx else 0.9
    seg(0, 0, tank_a_S[0], tank_a_S[1], tank_a_S[0]+stub_dx, tank_a_S[1], "GND", LF, TRK_SIG)

# --- J1 1x12 THT @ (8,88.5). PLAN-DEVIATION: plan says rot270 but that runs pins
# WEST with increasing number; rot90 makes them run EAST as the plan's pin table
# ("pads run east, pitch 2.54") requires. Using rot90.
j1 = fp("Connector_PinHeader_2.54mm", "PinHeader_1x12_P2.54mm_Vertical")
j1.SetReference("J1"); j1.SetValue("IN"); board.Add(j1)
j1.SetPosition(VECTOR2I(MM(8.0), MM(88.5))); j1.SetOrientationDegrees(90)
J1PIN = {1:"+5V",2:"GND",3:"+3V3",4:"RDY_CLK",5:"SHD",6:"DEMOD_OUT",7:"LEDD0",
         8:"EN0",9:"S0",10:"S1",11:"EN1",12:"GND"}
assign(j1, {str(k): v for k,v in J1PIN.items()})

# --- J2 1x6 THT @ (58,88.5) rot90 (same deviation as J1)
j2 = fp("Connector_PinHeader_2.54mm", "PinHeader_1x06_P2.54mm_Vertical")
j2.SetReference("J2"); j2.SetValue("OUT"); board.Add(j2)
j2.SetPosition(VECTOR2I(MM(58.0), MM(88.5))); j2.SetOrientationDegrees(90)
J2PIN = {1:"SENS1",2:"SENS3",3:"SENS4",4:"SENS2",5:"GND",6:"GND"}
assign(j2, {str(k): v for k,v in J2PIN.items()})
# DRC-FIX starved_thermal: J2 pin5 GND had only 1 zone spoke connected as a
# bare THT pad -- short stub south into open pour gives it a second spoke.
_j2p5 = pad_xy(j2, "5")
seg(0, 0, _j2p5[0], _j2p5[1], _j2p5[0], _j2p5[1]+1.0, "GND", LF, TRK_SIG)

# --- test points
def tp(ref, x, y, nm):
    t = fp("TestPoint", "TestPoint_Pad_D1.5mm")
    t.SetReference(ref); t.SetValue("TP"); board.Add(t)
    t.SetPosition(VECTOR2I(MM(x), MM(y))); t.SetOrientationDegrees(0)
    assign(t, {"1": nm})
    return t
tp_ant  = tp("TP1", 3.0, 74.5, "ANT_DRV")
# PLAN-DEVIATION: moved off x=22.5 (too close to J1 pin7's THT column at
# x=23.24, blocking via placement across the whole J1-drop y band) into the
# open gap between the two mux ICs (x=39-41.5).
# DRC-FIX courtyards_overlap: pulled up 0.4mm (85.5->85.1) -- at 85.5 TP2's
# courtyard clipped J1's (0.07mm overlap, J1's courtyard spans its whole pin
# row so it reaches under TP2's x).
# DRC-FIX (structural): the 84-88mm y band between J1 and the mux row can
# only fit TWO corridor rows (86.2-87.3 window between the C_dec/CDECI/TP
# walls and J1's pad-hole wall). TPs relocated out of the band; DEMOD_OUT
# routed manually on B.Cu below.
tp_demo = tp("TP2", 21.6, 84.0, "DEMOD_OUT")
tp_rdy = tp("TP3", 38.6, 83.6, "RDY_CLK")
tp_shd = tp("TP4", 40.6, 81.9, "SHD")

# --- J1 pad2 + pad12 + J2 pad5 GND link, registered BEFORE any corridor/
# trunk routing runs so their jog searches must dodge it (placing it after
# them caused an endless whack-a-mole of re-jogged collisions).
seg(0, 0, 10.54, 88.5, 10.54, 89.75, "GND", pcbnew.B_Cu, TRK_SIG)
seg(0, 0, 10.54, 89.75, 32.6, 89.75, "GND", pcbnew.B_Cu, TRK_SIG)
rvia(32.6, 89.75, "GND")
seg(0, 0, 32.6, 89.75, 45.2, 89.75, "GND", LF, TRK_SIG)   # F bridge over the x=33-45 B cage
rvia(45.2, 89.75, "GND")
seg(0, 0, 45.2, 89.75, 68.16, 89.75, "GND", pcbnew.B_Cu, TRK_SIG)
seg(0, 0, 68.16, 89.75, 68.16, 88.5, "GND", pcbnew.B_Cu, TRK_SIG)
seg(0, 0, 35.94, 88.5, 35.94, 89.75, "GND", LF, TRK_SIG)   # pad12 joins on the F bridge
# A<n> test points sit ON the lane's mux-feed vertical (x=lx, y between 74.1
# and feed_y) so they land on existing copper without adding a new obstacle
# in the crowded 68-72mm y band used by the power-spine bridges.
# PLAN-DEVIATION: moved from the exact feed_y point (where the adjacent
# lane's mux-feed horizontal passes close enough to short against the
# TestPoint's own pad radius) up onto the lane's own vertical run at y=76.0,
# which no other net's horizontal crosses.
# y=77.5 (not 76.0): the AM<n> zener midpoint stitch crosses this same x
# column at y=75.5, and a 1.5mm TestPoint pad at 76.0 clips it (0.5mm gap,
# needs >0.75mm). x matches the widened CLUSTER lanes.
tp("TP5", 41.1, 77.5, "A1")
# DRC-FIX courtyards_overlap: TP6 shifted east 0.8mm (36.7->37.5) -- at
# 36.7 (dead on the A3 lane x, same as U1-side U2 pin14) its courtyard
# clipped U2's east edge by 0.45mm. It's now off the lane's own vertical, so
# a short stub ties it back into the A3 track.
tp6 = tp("TP6", 37.5, 77.5, "A3")
seg(0, 0, 37.5, 77.5, 36.7, 77.5, "A3", LF, TRK_SIG)
tp("TP7", 74.1, 77.5, "A2")
tp("TP8", 68.0, 77.5, "A4")

# --- per-side decoupling for hall/LED rails
decap = {}
# CR1/CR2 kept west of the east-margin power/LEDD3 columns (75.0-77.4) and
# clear of the S2/S4 coil radius (71.9) and SENS2/4 columns (78.5+).
for tag, dx, dy in [("L1",6.0,63.0),("L2",6.0,65.0),("R1",73.2,44.0),("R2",73.2,47.0)]:
    c = fp("Capacitor_SMD", "C_0603_1608Metric"); c.SetValue("100nF")
    cp = place_by_pos(c, f"C_{tag}", dx, dy, {"W": (-0.8,0.0), "E": (0.8,0.0)}, rot0=0)
    nm = "+3V3" if tag in ("L1","R1") else "+5V"
    assign(c, {cp["W"]: nm, cp["E"]: "GND"})
    decap[tag] = (c, cp)
cL1, cL1p = decap["L1"]; cL2, cL2p = decap["L2"]; cR1, cR1p = decap["R1"]; cR2, cR2p = decap["R2"]

rebuild_hole_pts()
print("phase2 OK: strip components placed")

# =============================== long-haul routing ===============================
def long_route(nm, x1, y1, x2, y2, w=TRK_SIG, jogs=None, hseg_jogs=None):
    """F.Cu jog from (x1,y1) to column x2, then B.Cu vertical descent to y2."""
    # The F.Cu jog is coil-safe regardless of where it lands (coils never
    # touch F.Cu) so it uses the full JOGS range; only the B.Cu drop is
    # restricted to `jogs` (keeps the vertical out of neighbouring coils).
    if abs(x1-x2) > 0.01:
        yj = hseg(min(x1,x2), max(x1,x2), y1, nm, w, jogs=hseg_jogs)
        rvia(x2, yj, nm)
        y1 = yj
    drop(x2, y1, y2, nm, w, jogs=jogs)

# --- decoupling-cap-to-IC-pin short hookups (same net, need physical copper)
def cap_to_pin(c, cp, pin, safe_y):
    # DRC-FIX clearance: U1's west-column pins are only 1.27mm apart, and
    # the cap's own OTHER pad (GND, ~1.6mm east of this W pad) sits close
    # enough to the target pin's row that a plain dogleg through it grazes
    # one or the other. Cross the cap's own footprint at `safe_y` (clear of
    # its GND pad), then turn onto the pin's exact row from a waypoint
    # column (10.4, east of the cap's GND pad, west of U1's pin pads) so
    # neither the crossing nor the final approach clips anything.
    cw = pad_xy(c, cp["W"]); px, py = pad_xy(u1, pin)
    wpx = 10.4
    seg(0, 0, cw[0], cw[1], cw[0], safe_y, "+5V", LF, TRK_SIG)
    seg(0, 0, cw[0], safe_y, wpx, safe_y, "+5V", LF, TRK_SIG)
    seg(0, 0, wpx, safe_y, wpx, py, "+5V", LF, TRK_SIG)
    seg(0, 0, wpx, py, px, py, "+5V", LF, TRK_SIG)
# safe_y chosen clear of each cap's own GND pad (0.9x0.95mm, so +-0.475mm
# half-height +0.35mm clearance margin = keep >0.825mm from the cap's own
# centre y): cvdd centre 82.5 -> safe_y=81.5 (1.0mm clear); cdvdd centre
# 78.4 -> safe_y=77.3 (1.1mm clear, pin4 sits almost on top of the cap).
cap_to_pin(cvdd, cvddp, "7", safe_y=81.5)
# DRC-FIX clearance: pin4's own neighbours (pin3 ANT1 above, pin5 GND
# below) plus the cap's own GND pad sit in one continuous forbidden band
# (76.4..80.3) with no safe crossing height. pin4 and pin7 are both +5V
# already (same net) -- route to pin7's safe spot instead; electrically
# identical, and pin6 (the only neighbour there) has room past it.
cap_to_pin(cdvdd, cdvddp, "7", safe_y=81.5)

# --- +3V3 / +5V power distribution using FIXED margin columns (per plan's
# "Left/Right margin B verticals" list). PLAN-DEVIATION: exact plan values
# widened slightly (0.7->1.0mm pitch) since 5 different nets (SENS1/3,
# +5V, +3V3, LEDD1 west; LEDD3, +3V3, +5V east) share this ~8.5mm margin and
# 0.7mm centre-to-centre is too tight for 0.3/0.5mm tracks + 0.15mm
# clearance once real pad/via sizes are accounted for. Columns route with
# vertical_trunk() at an EXACT x (no jog search) so nets can't wander into
# each other or into the neighbouring square's coil.
JOGS_NOEDGE = [0.0]+[s*d for d in [0.4,0.8,1.2,1.6,2.0,2.4,2.8,3.2,3.6] for s in (1,-1)]
WCOL = {"SENS3": 1.2, "+5V": 2.4, "+3V3": 3.6, "SENS1": 4.8, "LEDD1": 6.0}
ECOL = {"LEDD3": 75.0, "+3V3": 76.2, "+5V": 77.4}

# LEDD2: S1.S_DOUT and S2.S_DIN are BOTH already at the channel row y=37 --
# plain F.Cu jog (F.Cu never touches coil copper, safe crossing either
# square). Routed FIRST, before anything else claims a row through the
# narrow (35.5-38.5mm) inter-row channel, so it gets first pick of the tiny
# safe window between LEDD1's port via (25.7,37.0, needs 0.9mm clearance)
# and S3's own coil edge (invisible to the router, at y=38.625).
JOGS_CHANNEL = [1.0, 1.05, 1.1, 0.95, 0.0, 0.3,-0.3,0.6,-0.6,0.9,-0.9,1.2,-1.2]
corridor("LEDD2", 37.0, [inner["S1"][6]["S_DOUT"], inner["S2"][6]["S_DIN"]], jogs=JOGS_CHANNEL)

def vertical_trunk(nm, col_x, points, w=TRK_PWR, jogs=None):
    """One B.Cu trunk at an EXACT x, with a short F.Cu jog+via from each
    (x,y) point to the trunk at that point's own y."""
    ys = []
    for (px, py) in points:
        yy = py
        if abs(px - col_x) > 0.01:
            # BUGFIX: hseg() can jog to a different y than requested if the
            # exact row is blocked -- the via MUST go at the y it actually
            # drew the track on, not the original py, or it lands on empty
            # copper (this was the #1 cause of "unconnected" nets).
            yy = hseg(min(px,col_x), max(px,col_x), py, nm, w, must=True, jogs=jogs)
        rvia(col_x, yy, nm)
        # DRC-FIX (generic): when the hseg jogs off a THT pad's own row, the
        # pad->lane riser was missing entirely -- draw it here from the
        # actual jogged y, so lane re-jogs between runs can't orphan pads.
        if abs(px - col_x) > 0.01 and abs(yy - py) > 0.01:
            raw(px, py, px, yy, nm, w, pcbnew.F_Cu)
        ys.append(yy)
    drop(col_x, min(ys), max(ys), nm, w, jogs=[0.0])

# --- U2/U3 VCC pins: escape out of the IC body, cross the one clear gap at
# y=75.5 (between the port stubs' y-max ~74.1 and mux body y-min 76.7), then
# join the +3V3 trunk column.
u2_vcc_x = escape(u2, "16", [N_, E], dist=1.2)
u3_vcc_x = escape(u3, "16", [N_, E], dist=1.2)
# DRC-FIX (structural): the old F lane at y~86 consumed the only corridor
# slot in the 86.1-87.3 window. In2 is empty at y=74.9 -- go west there,
# straight from the escape via onto the WCOL trunk.
seg(0, 0, u2_vcc_x[0], u2_vcc_x[1], u2_vcc_x[0], 74.9, "+3V3", pcbnew.In2_Cu, TRK_SIG)
seg(0, 0, u2_vcc_x[0], 74.9, WCOL["+3V3"], 74.9, "+3V3", pcbnew.In2_Cu, TRK_SIG)
seg(0, 0, WCOL["+3V3"], 74.9, WCOL["+3V3"], 76.6, "+3V3", pcbnew.In2_Cu, TRK_SIG)
rvia(WCOL["+3V3"], 76.6, "+3V3")
u2_vcc_safe = (WCOL["+3V3"], 76.6)
# DRC-FIX: 87.0 lane crossed SENS3's J2 riser at x=60.54 -- moved to 83.8
# (clear of EN1's via at 83.4/x=43.5 since this span starts at 50.86)
long_route("+3V3", u3_vcc_x[0], u3_vcc_x[1], u3_vcc_x[0], 83.8)
yj = hseg(u3_vcc_x[0], ECOL["+3V3"], 83.8, "+3V3")
rvia(ECOL["+3V3"], yj, "+3V3")
u3_vcc_safe = (ECOL["+3V3"], yj)

vertical_trunk("+3V3", WCOL["+3V3"], [pad_xy(j1,"3"), u2_vcc_safe,
               inner["S1"][6]["W_3V3"], inner["S3"][6]["W_3V3"], pad_xy(cL1, cL1p["W"])])
vertical_trunk("+3V3", ECOL["+3V3"], [u3_vcc_safe,
               inner["S2"][6]["W_3V3"], inner["S4"][6]["W_3V3"], pad_xy(cR1, cR1p["W"])])
vertical_trunk("+5V", WCOL["+5V"], [pad_xy(j1,"1"), pad_xy(cvdd, cvddp["W"]),
               pad_xy(cdvdd, cdvddp["W"]), inner["S1"][6]["W_5V"], inner["S3"][6]["W_5V"], pad_xy(cL2, cL2p["W"])])
vertical_trunk("+5V", ECOL["+5V"], [inner["S2"][6]["W_5V"], inner["S4"][6]["W_5V"], pad_xy(cR2, cR2p["W"])])

# --- bridge west<->east across the top routing corridor (y<5.5, coil-free
# for the full board width per plan).
def bridge_top(nm, xw, xe, ytop, w=TRK_PWR):
    rvia(xw, ytop, nm)
    yy = hseg(min(xw,xe), max(xw,xe), ytop, nm, w)
    rvia(xe, yy, nm)

bridge_top("+3V3", WCOL["+3V3"], ECOL["+3V3"], 2.0)
bridge_top("+5V", WCOL["+5V"], ECOL["+5V"], 3.0)
# extend each column's trunk up to meet its own bridge riser point
drop(WCOL["+3V3"], 2.0, inner["S1"][6]["W_3V3"][1], "+3V3", jogs=[0.0])
drop(ECOL["+3V3"], 2.0, inner["S2"][6]["W_3V3"][1], "+3V3", jogs=[0.0])
drop(WCOL["+5V"], 3.0, inner["S1"][6]["W_5V"][1], "+5V", jogs=[0.0])
drop(ECOL["+5V"], 3.0, inner["S2"][6]["W_5V"][1], "+5V", jogs=[0.0])

# --- hot via (in-square) -> cluster top (tank-a N pad column). Routed after
# the power spines so it dodges them locally via JOGS.
for sn, an in [("S1","A1"),("S2","A2"),("S3","A3"),("S4","A4")]:
    hv = coil[sn]["hot_via"]
    tx, ty = cluster_top[an]
    # For S1/S2 the hot via sits only ~0.5mm below the OTHER stacked square's
    # B-layer In2 connector (which ends at cy+14.375) -- nudge the descent's
    # start down 0.7mm first so the two verticals don't graze each other.
    # DRC-FIX tracks_crossing/clearance: S1 and S2's hot vias are only
    # 1.4mm apart (same cy) so their F.Cu jogs/B.Cu drops start almost on
    # top of each other -- give S2 (A2) extra separation.
    y0 = hv[1] + 0.7
    if y0 != hv[1]:
        seg(0, 0, hv[0], hv[1], hv[0], y0, an, LF, TRK_SIG)
    # DRC-FIX clearance: for A4, long_route()'s internal x-align hseg (own
    # jog search, unrelated to the JOGS_SMALL passed below) landed its via
    # only 0.975mm south of CT4a's own GND pad. Restrict that search to
    # northward-only offsets so it can't overshoot past the target row into
    # the pad's territory.
    # DRC-FIX clearance: the default hseg jog search only finds clear rows
    # at 71.48/71.58 (0.87-0.97mm from CT4a's GND pad -- needs 1.225mm) or
    # closer, everywhere within +-6mm of y0. The nearest properly-clear row
    # is a full ~18.5mm further north (50.5..51.9), well clear of the pad.
    # DRC-FIX tracks_crossing: A1's hot via is only 0.3mm in x from its own
    # cluster-top target -- an unbounded hseg search still wanders (to a
    # jog that crosses A2's own short initial stub). Force it to connect
    # at exactly y0, no search, since the x span is trivial.
    # TOPOLOGY-FIX: A4's [-18.5] escape hatch removed -- with unmirrored
    # coils A4's hot via sits at (72.6,68.4), ~2mm from its own cluster; the
    # default search is fine. A1 keeps its exact-row connect.
    # A4: pin to exact-row connect too -- the default search wandered ~8mm
    # west into SENS3's J2 descent column (tracks_crossing @ 60.5,51.8).
    _hj = [0.0] if an in ("A1", "A4") else None
    # DRC-FIX tracks_crossing: A1's B.Cu descent lane search (JOGS_SMALL,
    # 0/+-0.3/+-0.6/...) picks +2.7 (x=42.7) as its first clear lane, which
    # runs straight down through S4's coil and SENS3's crossing point.
    # Negative (westward) lanes weren't tried first -- prefer them for A1.
    _dropjogs = ([0.0]+[-d for d in [0.3,0.6,0.9,1.2,1.5,1.8,2.1,2.4,2.7,3.0]]+
                 [d for d in [0.3,0.6,0.9,1.2,1.5,1.8,2.1,2.4,2.7,3.0]]) if an == "A1" else JOGS_SMALL
    long_route(an, hv[0], y0, tx, ty, jogs=_dropjogs, hseg_jogs=_hj)

# --- W/E port vias -> strip. West squares (S1,S3) exit at cx-16.5 (west margin);
# east squares (S2,S4) exit at cx+16.5 (east margin, mirrored).
SENSPORT = {"S1":"SENS1","S2":"SENS2","S3":"SENS3","S4":"SENS4"}
J2PIN_OF_SENS = {"SENS1":"1","SENS3":"2","SENS4":"3","SENS2":"4"}
j2sens_y = {"SENS1": 85.9, "SENS3": 86.4, "SENS4": 86.9, "SENS2": 87.3}
# SENS1/SENS3 use the west margin trunk columns; SENS2/SENS4 use dedicated
# far-east columns (78.6/79.4, past the +3V3/+5V/LEDD3 trunk at 75.0-77.4 and
# clear of CR1/CR2), matching the plan's "SENS2/4 stay on F" east routing.
SENS_COL = {"SENS1": WCOL["SENS1"], "SENS3": WCOL["SENS3"], "SENS4": 78.2, "SENS2": 79.0}
for sn in ("S1","S2","S4"):
    pv = inner[sn][6]["W_SENS"]
    sensnet = SENSPORT[sn]
    j2pin_xy = pad_xy(j2, J2PIN_OF_SENS[sensnet])
    vertical_trunk(sensnet, SENS_COL[sensnet], [pv, j2pin_xy], w=TRK_SIG)
# DRC-FIX copper_edge_clearance: routing SENS3 through the shared west-
# margin trunk column (x=1.2, like SENS1/+5V/+3V3/LEDD1) forces its
# crossing row into the same saturated x=0..25 band those other trunks
# occupy top-to-bottom -- nothing is clear there below the board edge. But
# SENS3's own port via (pv) already sits at x=7.0 (east of every trunk
# column) at y=52.55 -- skip the trunk column entirely and go straight from
# there to J2 pin2 with the general-purpose router (F.Cu jog + B.Cu drop),
# same as the hot-via-to-cluster routes use.
_s3_pv = inner["S3"][6]["W_SENS"]
_s3_j2 = pad_xy(j2, J2PIN_OF_SENS["SENS3"])
# TOPOLOGY-FIX (root cause of the last tracks_crossing): long_route's B.Cu
# descent at x=60.54 ran straight through S4's B-only coil turns and its
# cold-via diagonal -- coil copper is deliberately NOT in the collision
# registry, so drop() couldn't see it. Explicit path instead: stay on F.Cu
# through S4's square (band crossings on F are legal), dive to B.Cu only at
# y=69.95 -- south of the band (68.5), south of LEDD3's B run (69.0) and
# north of the +5V B feeder (69.7 -- crossed on B?? no: 69.7 < 69.95, the
# descent STARTS south of it; verify: 5V feeder y=69.7, descent spans
# 69.95..88.5, no overlap).
# ...and any eastward F descent crosses S4's E-port horizontals (y 52.5-56.5,
# x 55.5-73) or the strip's F lanes, while any B descent x>8 hits the +5V B
# feeder wall at y=69.7. Only clean corridor: the plan's own west-margin
# column (WCOL['SENS3']=1.2, west of the feeder's x=8.0 start), approaching
# J2 pin2 from the SOUTH (y=90.6 lane) like SENS2/SENS4 do, clear of
# SENS1's x=58 descent.
seg(0, 0, _s3_pv[0], _s3_pv[1], WCOL["SENS3"], _s3_pv[1], "SENS3", LF, TRK_SIG)
rvia(WCOL["SENS3"], _s3_pv[1], "SENS3")
seg(0, 0, WCOL["SENS3"], _s3_pv[1], WCOL["SENS3"], 81.4, "SENS3", pcbnew.B_Cu, TRK_SIG)
rvia(WCOL["SENS3"], 81.4, "SENS3")
# Cross the strip on In1.Cu, weaving between the through-via fields
# (EN0@84.5, ANT_DRV@82.0, EN1@83.4, mux escapes@80.0-80.6, Z-tie@76.6,
# GND@78.4), then a clean F riser into J2 pin2 from a via at (60.54,85.5).
seg(0, 0, WCOL["SENS3"], 81.4, 11.2, 81.4, "SENS3", pcbnew.In1_Cu, TRK_SIG)
seg(0, 0, 11.2, 81.4, 11.2, 72.9, "SENS3", pcbnew.In1_Cu, TRK_SIG)
seg(0, 0, 11.2, 72.9, 59.5, 72.9, "SENS3", pcbnew.In1_Cu, TRK_SIG)
seg(0, 0, 59.5, 72.9, 59.5, 85.5, "SENS3", pcbnew.In1_Cu, TRK_SIG)
seg(0, 0, 59.5, 85.5, _s3_j2[0], 85.5, "SENS3", pcbnew.In1_Cu, TRK_SIG)
rvia(_s3_j2[0], 85.5, "SENS3")
seg(0, 0, _s3_j2[0], 85.5, _s3_j2[0], _s3_j2[1], "SENS3", LF, TRK_SIG)

# --- strip-internal signal hookups. All confined to y>=74 (below the square
# rows) so they never need to dodge coil copper; spine rows chosen below
# y=83.45 (U1) / y=81.3 (mux) pad extents so the F.Cu run itself is clear
# (B.Cu drops skip SMD pad clearance entirely, per the router's own rule).
r1w = pad_xy(r1, r1p["W"]); cdv1n = pad_xy(cdv1, cdv1p["N"]); tp1xy = pad_xy(tp_ant, "1")
seg(0, 0, r1w[0], r1w[1], r1w[0], cdv1n[1], "ANT_DRV", LF, TRK_SIG)
seg(0, 0, r1w[0], cdv1n[1], cdv1n[0], cdv1n[1], "ANT_DRV", LF, TRK_SIG)
seg(0, 0, cdv1n[0], cdv1n[1], tp1xy[0], cdv1n[1], "ANT_DRV", LF, TRK_SIG)
seg(0, 0, tp1xy[0], cdv1n[1], tp1xy[0], tp1xy[1], "ANT_DRV", LF, TRK_SIG)
ANT_BYPASS_Y = 72.0  # clear of R1's own ANT1 pad (row y=73.2) and U1 (>=74.555)

# Escape every needed U1/U2/U3 pin sideways out of its cramped IC body FIRST
# (west-column pins escape west, east-column pins escape east), then run
# each net's corridor between the escaped via points -- avoids the router
# having to drop() across a whole IC body's worth of neighbouring pads.
# DRC-FIX: the diagonal escape modes drew a swapped-endpoint floating track
# that grazed pin3's pad -- straight west only.
u1_rdy  = escape(u1, "2",  [W_], dist=2.6)
u1_demo = escape(u1, "13", [E])
# pin14 sits between the CDC2/FCAP decoupling caps at x=19.4 -- dogleg south
# first (clear of both the pin13 stub at y=78.36 and the caps) then east.
# straight-down at p14x would run through pin13's pad (same x column,
# y=78.365, directly between pin14 and the y=79.5 turn) -- nudge east 1.0mm
# first so the vertical run clears pin13's pad entirely.
# PLAN-DEVIATION: a fixed offset kept grazing U1 pin13's own escape via or
# the CDC2/FCAP caps at x=19.4 -- use the router's own hseg (checks real
# clearance against every registered pad/via) instead of a blind seg().
p14x, p14y = pad_xy(u1, "14")
yj2 = hseg(p14x, 22.5, p14y, "SHD")
rvia(22.5, yj2, "SHD")
yj = vseg(yj2, 79.5, 22.5, "SHD")
yjf = hseg(22.5, 25.0, 79.5, "SHD")
rvia(25.0, yjf, "SHD")
u1_shd = (25.0, yjf)
u2_z    = escape(u2, "3",  [W_])
u2_en   = escape(u2, "6",  [W_])
u2_s1   = escape(u2, "10", [E])
u2_s0   = escape(u2, "11", [E])
u3_z    = escape(u3, "3",  [W_])
u3_en   = escape(u3, "6",  [W_])
u3_s1   = escape(u3, "10", [E])
u3_s0   = escape(u3, "11", [E])

# u2_z/u3_z land at the exact same y (pin3 offset is identical on both
# muxes) -- join them directly, then bring r1w in with its own short hop.
# DRC-FIX: every corridor row near the Z-escape height is walled, and the
# drop lanes are via-choked. Manual B.Cu tie one row NORTH (76.55) instead
# -- that band is empty on B between the mux tops and the A-lane stubs.
rvia(u2_z[0], u2_z[1], "ANT_DRV")
rvia(u3_z[0], u3_z[1], "ANT_DRV")
seg(0, 0, u2_z[0], u2_z[1], u2_z[0], 76.55, "ANT_DRV", pcbnew.B_Cu, TRK_SIG)
seg(0, 0, u2_z[0], 76.55, u3_z[0], 76.55, "ANT_DRV", pcbnew.B_Cu, TRK_SIG)
seg(0, 0, u3_z[0], 76.55, u3_z[0], u3_z[1], "ANT_DRV", pcbnew.B_Cu, TRK_SIG)
# Bypass R1's own ANT1 pad (east of r1w, same row) by dropping to a clear
# row first, then traverse the whole width (still above U1's 74.555 pad
# block) before dropping straight down to u2_z.
seg(0, 0, r1w[0], r1w[1], r1w[0], ANT_BYPASS_Y, "ANT_DRV", LF, TRK_SIG)
seg(0, 0, r1w[0], ANT_BYPASS_Y, u2_z[0], ANT_BYPASS_Y, "ANT_DRV", LF, TRK_SIG)
seg(0, 0, u2_z[0], ANT_BYPASS_Y, u2_z[0], u2_z[1], "ANT_DRV", LF, TRK_SIG)
# Rows pinned to the two available slots (86.3 / 87.05).
corridor("RDY_CLK", 85.5, [pad_xy(j1, "4"), u1_rdy, pad_xy(tp_rdy, "1")], jogs=[0.8, 0.7, 0.9, 0.6, 1.0])
# SHD: no corridor slot left (RDY@86.3, SENS1 lane@87.3, J1 pad wall).
# Manual B.Cu: west under the DEMOD_OUT walls (cross x=20.7 at y=77.5,
# north at x=18.5, into pad5), east branch at y=78.9 to TP4.
# pad5 leg on In2, landing on the escape chain's existing via (22.5,79.5)
seg(0, 0, 18.16, 88.5, 18.16, 80.0, "SHD", pcbnew.In2_Cu, TRK_SIG)
seg(0, 0, 18.16, 80.0, 19.0, 80.0, "SHD", pcbnew.In2_Cu, TRK_SIG)
seg(0, 0, 19.0, 80.0, 19.0, 79.5, "SHD", pcbnew.In2_Cu, TRK_SIG)
seg(0, 0, 19.0, 79.5, 22.5, 79.5, "SHD", pcbnew.In2_Cu, TRK_SIG)
# TP4 branch on B
seg(0, 0, 25.0, 79.5, 25.0, 78.9, "SHD", pcbnew.B_Cu, TRK_SIG)
seg(0, 0, 25.0, 78.9, 40.6, 78.9, "SHD", pcbnew.B_Cu, TRK_SIG)
seg(0, 0, 40.6, 78.9, 40.6, 81.9, "SHD", pcbnew.B_Cu, TRK_SIG)
# DEMOD_OUT: manual B.Cu route pin13-escape -> TP2 -> J1 pad6 (no corridor
# slot left; B.Cu is empty along this path).
_dm = u1_demo
rvia(_dm[0], _dm[1], "DEMOD_OUT")
seg(0, 0, _dm[0], _dm[1], 20.7, _dm[1], "DEMOD_OUT", pcbnew.B_Cu, TRK_SIG)
seg(0, 0, 20.7, _dm[1], 20.7, 82.6, "DEMOD_OUT", pcbnew.B_Cu, TRK_SIG)
seg(0, 0, 20.7, 82.6, 21.6, 82.6, "DEMOD_OUT", pcbnew.B_Cu, TRK_SIG)
seg(0, 0, 21.6, 82.6, 21.6, 84.0, "DEMOD_OUT", pcbnew.B_Cu, TRK_SIG)
rvia(21.6, 84.0, "DEMOD_OUT")   # lands on TP2's pad
seg(0, 0, 21.6, 84.0, 21.6, 87.9, "DEMOD_OUT", pcbnew.B_Cu, TRK_SIG)
seg(0, 0, 21.6, 87.9, 20.7, 87.9, "DEMOD_OUT", pcbnew.B_Cu, TRK_SIG)
seg(0, 0, 20.7, 87.9, 20.7, 88.5, "DEMOD_OUT", pcbnew.B_Cu, TRK_SIG)
corridor("EN0", 86.5, [pad_xy(j1, "8"), u2_en])
corridor("EN1", 87.0, [pad_xy(j1, "11"), u3_en])
# DRC-FIX: F.Cu corridor()/vertical_trunk() for S0, S1 and (further above)
# SENS3 are all unroutable on F.Cu in this crowded strip without wandering
# past the board edge. Route all on B.Cu, stacked at three heights chosen
# so NO net's vertical branch has to cross through another net's row: S1
# (shortest reach) lowest, S0 next (searched strictly above S1), SENS3
# (already placed above, spans the full board width) highest.
_j1p9 = pad_xy(j1, "9")
_j1p10 = pad_xy(j1, "10")
def _row_search(y0, dset, x0, x1, nm):
    for _d in dset:
        _yy = y0 + _d
        if seg_clear(x0, _yy, x1, _yy, nm, TRK_SIG, pcbnew.B_Cu):
            return _yy
    return None
_SMALL = [0.0,0.1,-0.1,0.2,-0.2,0.3,-0.3,0.4,-0.4,0.5,-0.5,0.6,-0.6,0.7,-0.7]
_UP_ONLY = [0.0,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1.0,1.2,1.4]

# TOPOLOGY-FIX: the B.Cu row band 89-91.5 is now fully walled (RDY/SHD
# corridor drops + vias landed there). J1 legs go up on In2.Cu instead --
# In2 is EMPTY in the strip; THT header pads connect on every layer, and
# each leg lands on the mux escape's existing through-via.
seg(0, 0, _j1p10[0], _j1p10[1], _j1p10[0], 81.25, "S1", pcbnew.In2_Cu, TRK_SIG)
seg(0, 0, _j1p10[0], 81.25, u3_s1[0], 81.25, "S1", pcbnew.In2_Cu, TRK_SIG)
seg(0, 0, u3_s1[0], 81.25, u3_s1[0], u3_s1[1], "S1", pcbnew.In2_Cu, TRK_SIG)
# DRC-FIX shorting_items/clearance: a plain B.Cu vertical for u2_s1's
# branch runs into J1 pin12's THT pad, S0's own vertical, TP2's pad+via,
# RDY_CLK's via or SHD's own drop() column depending which x/y it tries --
# this whole corridor is saturated from every direction. u2_s1 and u3_s1
# sit at the SAME y (80.625) already, so skip the row entirely for this
# branch: jump straight to u3_s1's own point on In1.Cu (empty this far
# south) and let u3_s1's own already-working vertical carry it up.
# DRC-FIX: 82.8 sat exactly 0.15 from EN1's via at (43.54,83.4) -- strict
# inequality DRC fails exact margins; moved to 82.5.
seg(0, 0, u2_s1[0], u2_s1[1], u2_s1[0], 82.7, "S1", pcbnew.In1_Cu, TRK_SIG)
seg(0, 0, u2_s1[0], 82.7, u3_s1[0], 82.7, "S1", pcbnew.In1_Cu, TRK_SIG)
seg(0, 0, u3_s1[0], 82.7, u3_s1[0], u3_s1[1], "S1", pcbnew.In1_Cu, TRK_SIG)
# S0's J1 leg: same In2 trick, one row lower, landing on u3_s0's via.
seg(0, 0, _j1p9[0], _j1p9[1], _j1p9[0], 86.2, "S0", pcbnew.In2_Cu, TRK_SIG)
seg(0, 0, _j1p9[0], 86.2, 23.9, 86.2, "S0", pcbnew.In2_Cu, TRK_SIG)
seg(0, 0, 23.9, 86.2, 23.9, 78.8, "S0", pcbnew.In2_Cu, TRK_SIG)
seg(0, 0, 23.9, 78.8, u3_s0[0], 78.8, "S0", pcbnew.In2_Cu, TRK_SIG)
seg(0, 0, u3_s0[0], 78.8, u3_s0[0], u3_s0[1], "S0", pcbnew.In2_Cu, TRK_SIG)
# DRC-FIX clearance: u2_s0's plain vertical (x=37.86) ran within 0.36mm of
# TP2's own DEMOD_OUT via (x=37.5, y=85.5) -- detour east first.
# DRC-FIX tracks_crossing: x=39.5 sat inside S1's row span (30.86..52.46)
# -- any vertical there crosses S1's row on the way up. Move the detour
# past S1's east edge instead (also keeps it clear of TP2's via, which was
# the original reason for detouring off x=37.86 at all).
# DRC-FIX: a plain vertical (any single x) or a wide horizontal detour both
# ended up crossing +3V3/EN1/ANT_DRV copper that saturates this x/y block.
# Use drop()'s own lane search (varies x, keeps F.Cu jog stubs local to
# ya/yb only, rather than sweeping one y across the whole span).
# DRC-FIX: every lane/height combo tried for a u2_s0 detour crossed EN1's
# own jog stub, S1's escape via, or TP2's via somewhere along the way --
# this x/y block is saturated from every direction. Route u2_s0 down into
# the genuinely open territory below the strip (y<80 here is clear all the
# way to the tank clusters) then east and up on B.Cu at u3_s0's own column,
# joining u3_s0's already-working vertical instead of building a second one.
# DRC-FIX: every F.Cu/B.Cu combination for this hop crosses EN1's jog,
# S1's row, or TP2's via somewhere in this saturated x/y block. In1.Cu is
# completely unused this far south of the squares (coil copper only exists
# near the squares themselves, y<~68) -- route the whole hop there, via a
# through-via at each end, bypassing the F.Cu/B.Cu congestion entirely.
# land back on u3_s0's OWN already-verified pad/via (79.975) instead of at
# the row height (91.3) directly -- a NEW via at (53.86,91.3) sits too close
# to SENS1's row (90.9) and to the board edge; u3_s0's existing vertical
# (built below) already carries the signal the rest of the way, and this
# via reuses u3_s0's own escape via (same net, same point).
via_at(0, 0, u2_s0[0], u2_s0[1], "S0")
# DRC-FIX shorting_items: a straight run lands exactly on EN1's own escape
# via (same y, 79.975) -- offset the crossing height off that row.
# DRC-FIX: 78.5/76.0 both sat too close to ANT_DRV's or +3V3's own vias.
# 77.0 clears EN1 (79.97/83.8), ANT_DRV (78.03) and +3V3 (75.53) alike.
seg(0, 0, u2_s0[0], u2_s0[1], u2_s0[0], 77.0, "S0", pcbnew.In1_Cu, TRK_SIG)
seg(0, 0, u2_s0[0], 77.0, u3_s0[0], 77.0, "S0", pcbnew.In1_Cu, TRK_SIG)
seg(0, 0, u3_s0[0], 77.0, u3_s0[0], u3_s0[1], "S0", pcbnew.In1_Cu, TRK_SIG)


# --- LEDD chain: J1(LEDD0)->S3.DIN, S3.DOUT->S1.DIN, S1.DOUT->S2.DIN,
# S2.DOUT->S4.DIN. S3.DOUT/S1.DIN and S2.DOUT/S4.DIN pairs are in the SAME
# square column but different y (one at the strip edge y=70, one at the
# inter-row channel y=37) -- a direct vertical there would cross straight
# through the intervening square's B.Cu coil, so those two hops detour via
# the coil-free margin (x<8.5 west, x>71.5 east), same trick as the power
# bridges. S1.DOUT/S2.DIN are BOTH already at the channel row y=37 (different
# columns, same row) so that hop is a plain F.Cu jog -- F.Cu never touches
# coil copper (per plan correction #2) so crossing over both squares is safe.
def same_col_margin(nm, pa, pb, xcol, ya_y=None, yb_y=None):
    """Both endpoints jog sideways to the SAME margin column (coil-free for
    its full height), then one vertical run connects them directly -- no
    need to detour via the top corridor when both hops are on one side.
    ya_y/yb_y override the jog row when the endpoint's own y is too congested
    (e.g. sitting exactly on a power spine row) -- a short extra vertical
    hop moves to a clear row first."""
    mjogs = [0.0]
    if ya_y is not None and abs(ya_y - pa[1]) > 0.01:
        drop(pa[0], pa[1], ya_y, nm, jogs=JOGS_SMALL)
        pa = (pa[0], ya_y)
    if yb_y is not None and abs(yb_y - pb[1]) > 0.01:
        drop(pb[0], pb[1], yb_y, nm, jogs=JOGS_SMALL)
        pb = (pb[0], yb_y)
    ya = hseg(min(pa[0],xcol), max(pa[0],xcol), pa[1], nm)
    rvia(xcol, ya, nm)
    yb = hseg(min(pb[0],xcol), max(pb[0],xcol), pb[1], nm)
    rvia(xcol, yb, nm)
    drop(xcol, ya, yb, nm, jogs=mjogs)

# LEDD0: J1.pin7 (y=88.5) -> S3.S_DIN port via (y=70.0) -- both already below
# S3's coil radius (68.4), so a plain corridor works with no margin detour.
# S3.S_DIN's own column (x=25.7) sits within 0.9mm of EN0's already-routed
# vias (25.78/25.94 @ y=84.5), and the generic corridor() couldn't find a
# clear row across the crowded 82-88 signal-corridor band. Route directly
# to J1 pin7's own x (23.24) instead -- no final lateral jog needed there.
j1p7 = pad_xy(j1, "7")
_s3din = inner["S3"][6]["S_DIN"]
# DRC-FIX: the B.Cu descent now crosses SHD's manual y=77.5 run -- go
# straight up In2 from the THT pad to the S_DIN port area, then F.
seg(0, 0, j1p7[0], j1p7[1], j1p7[0], 75.8, "LEDD0", pcbnew.In2_Cu, TRK_SIG)
rvia(j1p7[0], 75.8, "LEDD0")
seg(0, 0, j1p7[0], 75.8, j1p7[0], 72.2, "LEDD0", pcbnew.B_Cu, TRK_SIG)
seg(0, 0, j1p7[0], 72.2, 23.6, 72.2, "LEDD0", pcbnew.B_Cu, TRK_SIG)
seg(0, 0, 23.6, 72.2, 23.6, 71.34, "LEDD0", pcbnew.B_Cu, TRK_SIG)
rvia(23.6, 71.34, "LEDD0")   # threaded between the GND run (70.675) and ANT_DRV (72.0), 0.21+ each
seg(0, 0, 23.6, 71.34, _s3din[0], 71.34, "LEDD0", LF, TRK_SIG)
seg(0, 0, _s3din[0], 71.34, _s3din[0], _s3din[1], "LEDD0", LF, TRK_SIG)

# LEDD1: S3.S_DOUT (y=70, below S3) -> S1.S_DIN (y=37, channel) -- this span
# crosses straight through S3's square, so detour via the west margin.
same_col_margin("LEDD1", inner["S3"][6]["S_DOUT"], inner["S1"][6]["S_DIN"], WCOL["LEDD1"])

# LEDD3: S2.S_DOUT (y=37, channel) -> S4.S_DIN (y=70, below S4) -- crosses
# S4's square, detour via the east margin.
# S4's DIN port (y=70) sits exactly on the crowded +3V3/+5V/A2/A4 row --
# drop a short extra hop to y=76.0 (below the tank/zener clusters, above
# the mux TSSOP bodies) before jogging out to the east margin.
same_col_margin("LEDD3", inner["S2"][6]["S_DOUT"], inner["S4"][6]["S_DIN"], ECOL["LEDD3"], yb_y=76.0)

print("phase1 OK, nets:", len(nets), "coils:", list(coil.keys()), "inner:", list(inner.keys()))

# =============================== GND zone + keepouts ===============================
def gnd_zone():
    z = pcbnew.ZONE(board); z.SetLayer(pcbnew.F_Cu); z.SetNet(net("GND"))
    pts = pcbnew.VECTOR_VECTOR2I()
    for x, y in [(0.6,0.6),(BW-0.6,0.6),(BW-0.6,BH-0.6),(0.6,BH-0.6)]:
        pts.append(VECTOR2I(MM(x), MM(y)))
    z.AddPolygon(pts)
    z.SetLocalClearance(MM(0.2)); z.SetMinThickness(MM(0.25))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)  # DRC-FIX starved_thermal (rig: hand-solder OK)
    z.SetThermalReliefGap(MM(0.4)); z.SetThermalReliefSpokeWidth(MM(0.5))
    z.SetAssignedPriority(0); board.Add(z)
gnd_zone()

def keepout_sq(cx, cy, half):
    z = pcbnew.ZONE(board); z.SetIsRuleArea(True)
    z.SetDoNotAllowZoneFills(True)
    for st in ["SetDoNotAllowTracks","SetDoNotAllowVias","SetDoNotAllowPads","SetDoNotAllowFootprints"]:
        getattr(z, st)(False)
    ls = pcbnew.LSET(); ls.AddLayer(pcbnew.F_Cu)
    z.SetLayerSet(ls)
    pts = pcbnew.VECTOR_VECTOR2I()
    for x, y in [(cx-half,cy-half),(cx+half,cy-half),(cx+half,cy+half),(cx-half,cy+half)]:
        pts.append(VECTOR2I(MM(x), MM(y)))
    z.AddPolygon(pts)
    z.SetAssignedPriority(10); board.Add(z)
for sn, (cx, cy, mx, nm) in SQ.items():
    keepout_sq(cx, cy, 15.4)

# ================= FIXUPS: close the residual unconnected gaps =================
# Each item verified against probed track endpoints; all same-net extensions,
# junction vias, or pour stitches.
BC = pcbnew.B_Cu
# SHD: bridge the missing vseg piece; via where the F run starts; via on TP4
seg(0, 0, 22.5, 77.495, 22.5, 79.5, "SHD", BC, TRK_SIG); rvia(22.5, 79.5, "SHD")
rvia(40.6, 81.9, "SHD")
# RDY_CLK: via on TP3 (escape now handles the pin2 stub itself)
rvia(38.6, 83.6, "RDY_CLK")
# GND: U1 pin1 + C_dvdd GND pad are pour-orphans (ANT1/RDY tracks fence
# them). Tie both to the strip-top pour through a small B.Cu network.
seg(0, 0, 11.9, 74.5, 11.9, 73.8, "GND", LF, TRK_SIG)   # pin1 pad exit north
rvia(11.9, 73.8, "GND")
seg(0, 0, 11.9, 73.8, 11.9, 72.6, "GND", BC, TRK_SIG)   # joins the x-run below
# (no via on the C_dvdd stub end -- it sat 0.55 from RDY's roaming escape
# vertical; the FULL zone connection now reaches the stub's F copper)
seg(0, 0, 10.4, 78.4, 10.4, 72.6, "GND", BC, TRK_SIG)
seg(0, 0, 10.4, 72.6, 22.2, 72.6, "GND", BC, TRK_SIG)
seg(0, 0, 22.2, 72.6, 22.2, 70.675, "GND", BC, TRK_SIG)
seg(0, 0, 22.2, 70.675, 30.0, 70.675, "GND", BC, TRK_SIG)
rvia(30.0, 70.675, "GND")                                 # lands in strip-top pour
# S3's GNDled stub floats too -- same inner-zone B.Cu jump to the pour-
# stitched hall row as S1/S2
rvia(24.05, 58.6, "GND")
seg(0, 0, 24.05, 58.6, 24.85, 53.5, "GND", BC, TRK_SIG)
rvia(24.85, 53.5, "GND")
# DEMOD_IN: B arrives dead-on C_dv2 pad1 (F-only) -- land it with a via
rvia(6.825, 85.2, "DEMOD_IN")
# +3V3: J1 pad3 riser; U2-VCC B/F junction bridge+via; U3-VCC junction via

rvia(50.8625, 83.8, "+3V3")
# right-margin rail caps: pad -> trunk stubs
seg(0, 0, 72.425, 44.0, 72.425, 45.2, "+3V3", LF, TRK_SIG)
seg(0, 0, 72.425, 47.0, 72.425, 48.2, "+5V", LF, TRK_SIG)
# +5V: DVDD (U1 pin4) spur -- C_dvdd's GND stub blocks the direct west
# approach, so run north of pin3's pad, down the free half of the U1
# pad-column gap (x=15.1; ANT1 owns 13.9 but its vertical ends at pin3's
# row), and back west into pin4.
# west F approaches are all fenced (C_dvdd, its GND stub, pin3's pad) --
# escape east through the pad-column gap, then In2 back to the +5V riser.
seg(0, 0, 11.525, 78.365, 14.7, 78.365, "+5V", LF, TRK_SIG)
seg(0, 0, 14.7, 78.365, 14.7, 77.8, "+5V", LF, TRK_SIG)
rvia(14.7, 77.8, "+5V")
seg(0, 0, 14.7, 77.8, 14.7, 79.2, "+5V", pcbnew.In2_Cu, TRK_SIG)
seg(0, 0, 14.7, 79.2, 7.725, 79.2, "+5V", pcbnew.In2_Cu, TRK_SIG)
seg(0, 0, 7.725, 79.2, 7.725, 80.6, "+5V", pcbnew.In2_Cu, TRK_SIG)
rvia(7.725, 80.6, "+5V")   # lands on the existing +5V F riser at x=7.725
# LED chain gaps: LEDD0 riser; LEDD1 channel->margin link on B (dodges the
# LEDD2 corridor at y=38 and the port vias at y=37); LEDD3 B tail + via
# (junction dropped to y=79.5 so the via clears the A2 feed at y=78.675)
seg(0, 0, 22.95, 70.8, 22.95, 70.0, "LEDD1", LF, TRK_SIG)  # lane->port-via riser
seg(0, 0, 25.7, 37.0, 25.7, 36.3, "LEDD1", BC, TRK_SIG)
seg(0, 0, 25.7, 36.3, 6.0, 36.3, "LEDD1", BC, TRK_SIG)
seg(0, 0, 6.0, 36.3, 6.0, 39.0, "LEDD1", BC, TRK_SIG)
seg(0, 0, 54.3, 76.0, 54.3, 78.0, "LEDD3", BC, TRK_SIG)
seg(0, 0, 54.3, 78.0, 56.0, 78.0, "LEDD3", BC, TRK_SIG)
seg(0, 0, 56.0, 78.0, 56.0, 79.35, "LEDD3", BC, TRK_SIG)
rvia(56.0, 79.35, "LEDD3")
seg(0, 0, 56.0, 79.35, 56.0, 79.2, "LEDD3", LF, TRK_SIG)
# A-node descents: land each B vertical with a via at the 'a' cap's N pad
# (= long_route's drop target) and tie both tank-cap N pads along their
# actual pad row (dynamic -- 0805 and 1206 tanks sit at different rows).
for _an in ("A1", "A2", "A3", "A4"):
    _pa = cluster_top[_an]; _pb = cluster_bN[_an]
    rvia(_pa[0], _pa[1], _an)
    seg(0, 0, _pa[0], _pa[1], _pb[0], _pb[1], _an, LF, TRK_SIG)
# (SENS/J-pad risers now drawn generically inside vertical_trunk)
# GND pour stitches: the inter-square keepout slivers choke the F pour, so
# the merged GND stub rows (y=20.5 / y=53.5, x 24.4..55.6) get explicit ties
# to large pour regions (top margin / strip)
seg(0, 0, 40.6, 20.5, 40.6, 4.0, "GND", LF, TRK_SIG)
seg(0, 0, 40.6, 53.5, 40.6, 69.6, "GND", LF, TRK_SIG)
# J1 pad2 GND: fenced from the F pour on all sides -- tie it to J2 pad5
# (also GND, THT=all layers) with a pure B.Cu run at y=90.0, south of every
# J1/J2 B descent (all end at y=88.5) and under the F sense lanes.
# short B hop west to a pour via at (6.4,89.4) -- the long J1->J2 B run
# crossed S0's under-connector dip at x=28.32
# (J1/J2 GND link moved EARLY -- right after header placement -- so the
# corridor/trunk routers register and avoid it instead of re-jogging into
# it on every regeneration.)
# C_dv2 GND pad (pour-orphaned): F stub east + B drop joining the U1-area
# GND B network at (9.875,78.4)
seg(0, 0, 8.375, 85.2, 11.0, 85.2, "GND", LF, TRK_SIG)
rvia(11.0, 85.2, "GND")
seg(0, 0, 11.0, 85.2, 11.0, 78.4, "GND", BC, TRK_SIG)
seg(0, 0, 11.0, 78.4, 10.4, 78.4, "GND", BC, TRK_SIG)
# GNDled stubs S1/S2 (x=24.05/55.95, floating in the choked channel): jump
# each to its square's hall-GND row (y=20.5, pour-stitched) through the
# coil's INNER clear zone on B.Cu -- both via points are inside max(|x|,|y|)
# < 5.875 rel, so they miss every coil turn; paths verified against the
# B-layer cold-via diagonals.
rvia(24.05, 25.6, "GND")   # y=25.6: via edge clears the B coil inner turn (rel 5.75)
seg(0, 0, 24.05, 25.6, 24.85, 20.5, "GND", BC, TRK_SIG)
rvia(24.85, 20.5, "GND")
rvia(55.95, 25.6, "GND")
seg(0, 0, 55.95, 25.6, 55.15, 20.5, "GND", BC, TRK_SIG)
rvia(55.15, 20.5, "GND")

pcbnew.ZONE_FILLER(board).Fill(board.Zones())
pcbnew.SaveBoard(OUT, board)
print("saved", OUT)

# =============================== BOM + positions ===============================
LCSC = {
    "74HC4851PW": "C458225", "WS2812C-2020": "C2976072", "UHE4913G": "C86815",
    "100n": "C5137636",
    # Verified 2026-09-01 against LCSC listings:
    "0R": "C21189",            # Basic, 1M+ stock
    "33R": "C17634",           # Basic
    "47pF": "C1671",           # Basic, C0G 50V (verified live)
    "1.5nF": "C5360827",       # Extended C0G 50V (X7R fallback: C37788)
    "10n_0603": "C57112",      # Basic X7R (C_fcap PLL + C_dc2)
    "10nF": "C57112",
    "100nF": "C14663",         # Basic X7R 50V
    "220nF": "C21120",         # Basic X7R 25V
    "10n": "C342877",          # 0805 C0G 50V TDK (tank, S1/S2) -- Extended
    "15V_SOD523": "C2891782",  # BZT52C15 SOD-523 -- Extended
    "100n_1206": "C97946",     # Murata GRM31C5C1H104JA01L C0G 1206, 196k stock
    # EM4095: zero LCSC stock. Order via JLCPCB Global Sourcing Parts
    # (Mouser EM4095HMSO16B+) BEFORE the PCBA order; 9-20 business days.
    "EM4095": "GLOBAL-SOURCING: EM4095HMSO16B+",
    "IN": "C725243",           # BOOMELE 1x12 2.54mm male header, THT assembly
    "OUT": "C37208",           # BOOMELE 1x6 2.54mm male header, THT assembly
    "TP": "NO-PART",           # bare copper test pads, nothing to place
}
rows = {}
for f in board.GetFootprints():
    ref = f.GetReference()
    val = f.GetValue()
    fpname = f.GetFPID().GetLibItemName().wx_str()
    rows.setdefault((val, fpname), []).append(ref)
with open(os.path.join(HERE, "BOM.csv"), "w", newline="") as fh:
    wcsv = csv.writer(fh)
    wcsv.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
    for (val, fpname), refs in sorted(rows.items()):
        wcsv.writerow([val, ",".join(sorted(refs, key=lambda r: (len(r), r))), fpname, LCSC.get(val, "TBD-verify")])
with open(os.path.join(HERE, "positions.csv"), "w", newline="") as fh:
    wcsv = csv.writer(fh)
    wcsv.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
    for f in board.GetFootprints():
        pos = f.GetPosition()
        wcsv.writerow([f.GetReference(), f"{pcbnew.ToMM(pos.x):.3f}mm", f"{pcbnew.ToMM(pos.y):.3f}mm",
                       "Top", f"{f.GetOrientationDegrees():.0f}"])
print("BOM.csv and positions.csv written")
