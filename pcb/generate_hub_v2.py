#!/usr/bin/env python3
"""Smart Chessboard V2 hub — ESP32 + Micro-USB + CH340C + TP4056 + 18650 + buffer.

!!! DO NOT RUN THIS ANYMORE — IT WILL OVERWRITE THE FINISHED BOARD !!!

hub_v2/chess_hub_v2.kicad_pcb has moved ahead of this script. It was repaired
by fix_hub_v2.py (placement) and fully auto-routed via FreeRouting by
route_hub_v2.py, and is now DRC-clean (0 errors, 0 unconnected). Running this
file regenerates the old, broken draft on top of it.

Known defects in this generator, for whoever revives it:
  * corridor()/drop() have no board-bounds check — the +3V3 corridor was
    emitted at y = -0.7, i.e. off the board.
  * corridor()/drop() ignore rule areas — +3V3 also ran through the antenna
    keepout.
  * placement puts C1/C2 under the U1 module body, U3/R5/C5/C6 under the
    BT1 18650 cell, and D1 on top of SW3.
  * the BOM LCSC map is keyed on footprint *value*, so SW1 ("PWR") picked up
    LED2's part number.
See fix_hub_v2.py MOVES and hub_v2/README.md for what the fixes were.

Original docstring:

Same generated-board approach as generate_quadrant_v2.py (routing primitives
copied verbatim). 88x60mm 2-layer. LED_5V = VSYS (diode-OR of VBUS/VBAT,
no boost in v0 — LEDs slightly dim on battery, documented in README).

Run:  <kicad python3.9> generate_hub_v2.py
"""
import os, csv, math
import pcbnew
from pcbnew import VECTOR2I, FromMM as MM

BW, BH = 88.0, 60.0
TRK_SIG, TRK_PWR = 0.4, 0.8
ESC = 1.8
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "hub_v2", "chess_hub_v2.kicad_pcb")
FPLIB = os.path.expanduser("~/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")

def fp(lib, name):
    f = pcbnew.FootprintLoad(os.path.join(FPLIB, lib + ".pretty"), name)
    assert f, f"footprint missing: {lib}:{name}"
    return f

os.makedirs(os.path.dirname(OUT), exist_ok=True)
board = pcbnew.NewBoard(OUT)
try:
    board.GetDesignSettings().m_MinClearance = MM(0.15)   # JLC 2-layer limit
except Exception as e:
    print("clearance note:", e)
nets = {}
def net(nm):
    if nm not in nets:
        n = pcbnew.NETINFO_ITEM(board, nm); board.Add(n); nets[nm] = n
    return nets[nm]
for nm in ["GND","VBUS","BATP","VSW","VSYS","+3V3","EN","IO0","DTR","RTS",
           "TXD0","RXD0","UDP","UDM","CC1","CC2","PROG","CHRGK","PWRK",
           "/PL","CP","SER","G27","LEDD"]: net(nm)

for a,b2 in zip([(0,0),(BW,0),(BW,BH),(0,BH)], [(BW,0),(BW,BH),(0,BH),(0,0)]):
    sg = pcbnew.PCB_SHAPE(board); sg.SetShape(pcbnew.SHAPE_T_SEGMENT)
    sg.SetStart(VECTOR2I(MM(a[0]),MM(a[1]))); sg.SetEnd(VECTOR2I(MM(b2[0]),MM(b2[1])))
    sg.SetLayer(pcbnew.Edge_Cuts); sg.SetWidth(MM(0.1)); board.Add(sg)

def pads_of(f, num):
    return [p for p in f.Pads() if p.GetNumber() == str(num)]
def pad_of(f, num):
    ps = pads_of(f, num)
    if not ps: raise KeyError(num)
    return ps[0]
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
    for num, nm in mapping.items():
        for p in pads_of(f, num): p.SetNet(net(nm))

# =============================== placement ===============================
# ESP32 module: antenna at top (rot 0 puts antenna at -y), keepout above pads
esp = place(fp("RF_Module","ESP32-WROOM-32E"), "U1", 16.0, 15.0, value="ESP32-WROOM-32E")
assign(esp, {1:"GND",2:"+3V3",3:"EN",10:"/PL",11:"CP",12:"G27",13:"SER",
             15:"GND",25:"IO0",34:"RXD0",35:"TXD0",38:"GND",39:"GND"})

# J1 header top-right, same column layout as quadrant (inner=signals, outer=GND)
JSIG = ["/PL", "CP", "SER", "VSYS", "+3V3", "LEDD"]   # VSYS feeds quadrant "+5V"
j1 = place(fp("Connector_PinHeader_2.54mm","PinHeader_2x06_P2.54mm_Vertical"), "J1", 60.0, 0, value="OUT")
for rot in (0, 90, 180, 270):
    j1.SetOrientationDegrees(rot)
    ys = [pad_xy(j1,k)[1] for k in range(1,13)]
    if max(ys) - min(ys) < 4: break
ys = [pad_xy(j1,k)[1] for k in range(1,13)]
p = j1.GetPosition(); j1.SetPosition(VECTOR2I(p.x, p.y + MM(1.6 - min(ys))))
pads_sorted = sorted(range(1,13), key=lambda k: (round(pad_xy(j1,k)[0],1), pad_xy(j1,k)[1]))
cols = [pads_sorted[i:i+2] for i in range(0,12,2)]
j1s = {}
for col, snet in zip(cols, JSIG):
    inner = max(col, key=lambda k: pad_xy(j1,k)[1])
    outer = col[0] if col[1]==inner else col[1]
    pad_of(j1, inner).SetNet(net(snet)); pad_of(j1, outer).SetNet(net("GND"))
    j1s[snet] = pad_xy(j1, inner)

# Micro-USB top edge (v0: trivially routable 0.65mm pitch; USB-C in v1)
usb = place(fp("Connector_USB","USB_Micro-B_Wuerth_629105150521"),
            "USB1", 36.0, 3.2, rot=0, value="MicroUSB")
assign(usb, {1:"VBUS", 2:"UDM", 3:"UDP", 4:"", 5:"GND", "SH":"GND"})

ch = place(fp("Package_SO","SOIC-16_3.9x9.9mm_P1.27mm"), "U2", 31.0, 24.0, rot=180, value="CH340C")
assign(ch, {1:"GND",2:"RXD0",3:"TXD0",4:"+3V3",5:"UDP",6:"UDM",
            13:"DTR",14:"RTS",16:"+3V3"})

tp = place(fp("Package_SO","SOIC-8_3.9x4.9mm_P1.27mm"), "U3", 34.0, 40.0, value="TP4056")
assign(tp, {1:"GND",2:"PROG",3:"GND",4:"VBUS",5:"BATP",7:"CHRGK",8:"VBUS"})

ldo = place(fp("Package_TO_SOT_SMD","SOT-223-3_TabPin2"), "U4", 16.0, 31.5, value="AMS1117-3.3")
assign(ldo, {1:"GND",2:"+3V3",3:"VSYS"})

d1 = place(fp("Diode_SMD","D_SMA"), "D1", 54.0, 18.0, value="SS34")   # VBUS -> VSYS
assign(d1, {1:"VSYS",2:"VBUS"})
d2 = place(fp("Diode_SMD","D_SMA"), "D2", 54.0, 24.0, rot=180, value="SS34")   # VSW -> VSYS
assign(d2, {1:"VSYS",2:"VSW"})

buf = place(fp("Package_TO_SOT_SMD","SOT-23-5"), "U5", 60.0, 20.0, value="74AHCT1G125")
assign(buf, {1:"GND",2:"G27",3:"GND",4:"LEDD",5:"VSYS"})


sw1 = place(fp("Button_Switch_SMD","SW_SPDT_PCM12"), "SW1", 85.4, 20.0, rot=90, value="PWR")
assign(sw1, {1:"BATP",2:"VSW",3:""})
sw2 = place(fp("Button_Switch_SMD","SW_SPST_PTS645Sx43SMTR92"), "SW2", 46.5, 8.5, value="EN")
assign(sw2, {1:"EN",2:"GND"})
sw3 = place(fp("Button_Switch_SMD","SW_SPST_PTS645Sx43SMTR92"), "SW3", 46.5, 15.5, value="BOOT")
assign(sw3, {1:"IO0",2:"GND"})

bt = place(fp("Battery","BatteryHolder_Keystone_1042_1x18650"), "BT1", 44.0, 49.5, value="18650")
assign(bt, {1:"BATP", 2:"GND"})

def rc(ref, val, x, y, rot, p1, p2, lib="Resistor_SMD", name="R_0603_1608Metric"):
    c = place(fp(lib, name), ref, x, y, rot=rot, value=val)
    assign(c, {1:p1, 2:p2})
    return c

rc("R1","10k", 2.6, 13.5, 90, "EN","+3V3")   # IO0 pullup deleted: ESP32 internal
rc("R5","2k",  33.0, 47.5, 0, "PROG","GND")
rc("R6","1k",  40.0, 35.5, 0, "CHRGK","VBUS")     # charge LED series
rc("R7","1k",  52.0, 33.0, 0, "PWRK","+3V3")      # power LED series
led1 = place(fp("LED_SMD","LED_0603_1608Metric"), "LED1", 44.5, 35.5, value="CHG")
assign(led1, {1:"GND", 2:"CHRGK"})                 # pad1=K per KiCad LED fp
led2 = place(fp("LED_SMD","LED_0603_1608Metric"), "LED2", 56.5, 33.0, value="PWR")
assign(led2, {1:"GND", 2:"PWRK"})

rc("C1","100n", 10.5, 15.5, 90, "+3V3","GND", "Capacitor_SMD","C_0603_1608Metric")
rc("C2","10u",  10.5, 19.5, 90, "+3V3","GND", "Capacitor_SMD","C_0805_2012Metric")
rc("C3","1u",   2.6, 17.0, 90, "EN","GND",  "Capacitor_SMD","C_0603_1608Metric")
rc("C4","100n", 39.0, 13.0, 0, "+3V3","GND", "Capacitor_SMD","C_0603_1608Metric")
rc("C5","10u",  28.5, 44.0, 270, "VBUS","GND", "Capacitor_SMD","C_0805_2012Metric")
rc("C6","10u",  41.5, 40.0, 90, "BATP","GND", "Capacitor_SMD","C_0805_2012Metric")
rc("C7","10u",  40.0, 22.0, 90, "VSYS","GND", "Capacitor_SMD","C_0805_2012Metric")
rc("C8","100n", 56.0, 16.0, 0,  "VSYS","GND", "Capacitor_SMD","C_0603_1608Metric")
rc("C9","10u",  8.0, 31.0, 90, "+3V3","GND", "Capacitor_SMD","C_0805_2012Metric")


# =============================== zones ===============================
def gnd_zone(layer):
    z = pcbnew.ZONE(board); z.SetLayer(layer); z.SetNet(net("GND"))
    pts = pcbnew.VECTOR_VECTOR2I()
    for x,y in [(0.6,0.6),(BW-0.6,0.6),(BW-0.6,BH-0.6),(0.6,BH-0.6)]:
        pts.append(VECTOR2I(MM(x),MM(y)))
    z.AddPolygon(pts)
    z.SetLocalClearance(MM(0.35)); z.SetMinThickness(MM(0.25))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetThermalReliefGap(MM(0.4)); z.SetThermalReliefSpokeWidth(MM(0.5))
    z.SetAssignedPriority(0); board.Add(z)
gnd_zone(pcbnew.F_Cu); gnd_zone(pcbnew.B_Cu)

# antenna keepout: no copper under/around the antenna end of the module
z = pcbnew.ZONE(board); z.SetIsRuleArea(True); z.SetDoNotAllowZoneFills(True)
for st in ["SetDoNotAllowTracks","SetDoNotAllowVias","SetDoNotAllowPads","SetDoNotAllowFootprints"]:
    getattr(z, st)(False)
z.SetDoNotAllowTracks(True); z.SetDoNotAllowVias(True)
ls = pcbnew.LSET(); ls.AddLayer(pcbnew.F_Cu); ls.AddLayer(pcbnew.B_Cu)
z.SetLayerSet(ls)
pts = pcbnew.VECTOR_VECTOR2I()
for x,y in [(6.5,1.0),(25.5,1.0),(25.5,9.2),(6.5,9.2)]:
    pts.append(VECTOR2I(MM(x),MM(y)))
z.AddPolygon(pts); z.SetAssignedPriority(10); board.Add(z)

# =============================== router (copied from quadrant v2) ===============================
segs = {pcbnew.F_Cu: [], pcbnew.B_Cu: []}
via_pts, hole_pts = [], []
for f in board.GetFootprints():
    for p in f.Pads():
        pos = p.GetPosition(); sz = p.GetSize()
        hx, hy = pcbnew.ToMM(sz.x)/2.0, pcbnew.ToMM(sz.y)/2.0
        if p.GetOrientationDegrees() % 180 > 45: hx, hy = hy, hx
        tht = p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
        hole_pts.append((pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y), p.GetNetname(), hx, hy, tht))
CLR = 0.45
EPS = 0.005
def _hit(a1,a2,b,gap): return min(a1,a2)-gap+EPS < b < max(a1,a2)+gap-EPS
def seg_clear(x1,y1,x2,y2,nm,w,layer):
    horiz = abs(y1-y2) < 1e-9
    for (ox1,oy1,ox2,oy2,onm,ow) in segs[layer]:
        if onm == nm: continue
        gap = (w+ow)/2 + CLR
        oh = abs(oy1-oy2) < 1e-9
        if horiz and oh:
            if abs(y1-oy1) < gap - EPS and max(x1,x2)+gap > min(ox1,ox2) and min(x1,x2)-gap < max(ox1,ox2): return False
        elif (not horiz) and (not oh):
            if abs(x1-ox1) < gap - EPS and max(y1,y2)+gap > min(oy1,oy2) and min(y1,y2)-gap < max(oy1,oy2): return False
        else:
            hx1,hx2,hy = (x1,x2,y1) if horiz else (ox1,ox2,oy1)
            vx,vy1,vy2 = (ox1,oy1,oy2) if horiz else (x1,y1,y2)
            if _hit(hx1,hx2,vx,gap) and _hit(vy1,vy2,hy,gap): return False
    for (vx,vy,vnm) in via_pts:
        if vnm == nm: continue
        gap = w/2 + 0.35 + CLR
        if horiz:
            if abs(y1-vy) < gap - EPS and _hit(x1,x2,vx,gap): return False
        else:
            if abs(x1-vx) < gap - EPS and _hit(y1,y2,vy,gap): return False
    for (px,py,pnm,hx,hy,tht) in hole_pts:
        if pnm == nm: continue
        if layer == pcbnew.B_Cu and not tht: continue
        gx, gy = w/2 + hx + 0.2, w/2 + hy + 0.2
        if horiz:
            if abs(y1-py) < gy - EPS and _hit(x1,x2,px,gx): return False
        else:
            if abs(x1-px) < gx - EPS and _hit(y1,y2,py,gy): return False
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
        if abs(x-px) < 0.35+hx+0.2-EPS and abs(y-py) < 0.35+hy+0.2-EPS: return False
    for (vx,vy,vnm) in via_pts:
        if abs(x-vx) < 1.1-EPS and abs(y-vy) < 1.1-EPS and vnm != nm: return False
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        for (ox1,oy1,ox2,oy2,onm,ow) in segs[layer]:
            if onm == nm: continue
            gap = 0.35 + ow/2 + CLR
            if abs(oy1-oy2) < 1e-9:
                if abs(y-oy1) < gap-EPS and _hit(ox1,ox2,x,gap): return False
            else:
                if abs(x-ox1) < gap-EPS and _hit(oy1,oy2,y,gap): return False
    return True
def drop(x, ya, yb, nm, w=TRK_SIG):
    lo, hi = min(ya,yb), max(ya,yb)
    for d in JOGS:
        lane = x + d
        if not seg_clear(lane, lo, lane, hi, nm, w, pcbnew.B_Cu): continue
        if abs(d) < 0.01:
            raw(lane, lo, lane, hi, nm, w, pcbnew.B_Cu); return
        if not seg_clear(min(x,lane), ya, max(x,lane), ya, nm, w, pcbnew.F_Cu): continue
        if not seg_clear(min(x,lane), yb, max(x,lane), yb, nm, w, pcbnew.F_Cu): continue
        if not via_clear(lane, ya, nm) or not via_clear(lane, yb, nm): continue
        raw(lane, lo, lane, hi, nm, w, pcbnew.B_Cu)
        raw(min(x,lane), ya, max(x,lane), ya, nm, w, pcbnew.F_Cu)
        raw(min(x,lane), yb, max(x,lane), yb, nm, w, pcbnew.F_Cu)
        via(lane, ya, nm); via(lane, yb, nm)
        return
    print(f"DROPDBG {nm} x={x:.2f} y {ya:.1f}->{yb:.1f}:")
    for d in JOGS[:16]:
        lane = x + d
        why = None
        if not seg_clear(lane, lo, lane, hi, nm, w, pcbnew.B_Cu):
            for (px,py,pnm,hx,hy,tht) in hole_pts:
                if pnm != nm and tht and abs(lane-px) < w/2+hx+0.2 and lo-2 < py < hi+2:
                    why = f"THTpad {pnm or 'NP'} ({px:.2f},{py:.2f})"; break
            if not why:
                for (vx,vy,vnm) in via_pts:
                    if vnm != nm and abs(lane-vx) < w/2+0.35+CLR and lo-1 < vy < hi+1:
                        why = f"via {vnm} ({vx:.2f},{vy:.2f})"; break
            if not why:
                for (ox1,oy1,ox2,oy2,onm,ow) in segs[pcbnew.B_Cu]:
                    if onm != nm and abs(ox1-ox2) < 1e-9 and abs(lane-ox1) < (w+ow)/2+CLR:
                        why = f"Bseg {onm} x={ox1:.2f}"; break
            why = why or "cross"
        else:
            why = "jog-stitch/via"
        print(f"  lane {lane:.2f}: {why}")
    UNROUTED.append(f"drop {nm} x={x:.2f}")
def corridor(nm, y0, pts, w=TRK_SIG):
    xs = [p[0] for p in pts]
    x1, x2 = min(xs), max(xs)
    if abs(x2-x1) < 0.01:
        (px, py1), (_, py2) = pts[0], pts[1]
        drop(px, py1, py2, nm, w); return py1
    for d in JOGS:
        yy = y0 + d
        if not seg_clear(x1, yy, x2, yy, nm, w, pcbnew.F_Cu): continue
        need_via = [(px,py) for (px,py) in pts if abs(py-yy) > 0.01]
        if any(not via_clear(px, yy, nm) for (px,_) in need_via): continue
        raw(x1, yy, x2, yy, nm, w, pcbnew.F_Cu)
        for (px,py) in need_via:
            via(px, yy, nm); drop(px, py, yy, nm, w)
        return yy
    print(f"CORRDBG {nm} y0={y0} x={x1:.1f}..{x2:.1f}")
    for d in JOGS[:14]:
        yy = y0 + d
        if not seg_clear(x1, yy, x2, yy, nm, w, pcbnew.F_Cu):
            why = "spine:?"
            for (qx,qy,qn,qhx,qhy,qt) in hole_pts:
                if qn != nm and abs(yy-qy) < w/2+qhy+0.2-EPS and _hit(x1,x2,qx,w/2+qhx+0.2-EPS):
                    why = f"spine pad {qn or 'NP'} ({qx:.2f},{qy:.2f})"; break
            else:
                for (ox1,oy1,ox2,oy2,onm,ow) in segs[pcbnew.F_Cu]:
                    if onm != nm and abs(oy1-oy2)<1e-9 and abs(yy-oy1) < (w+ow)/2+CLR and max(x1,ox1) < min(x2,ox2):
                        why = f"spine seg {onm} y={oy1:.1f}"; break
        else:
            bad = [(px,py) for (px,py) in pts if abs(py-yy) > 0.01 and not via_clear(px, yy, nm)]
            why = f"via@{[(round(a,1),round(b,1)) for a,b in [(px,yy) for px,_ in bad]]}" if bad else "drop-fail?"
        print(f"  y={yy:.2f}: {why}")
    UNROUTED.append(f"corridor {nm} y0={y0}"); return y0
def escape(f, num, dirs, dist=ESC, w=TRK_SIG):
    px, py = pad_xy(f, num)
    nm = pad_of(f, num).GetNetname()
    for (dx,dy) in dirs:
        for dd in (dist, dist+0.7, dist+1.4, dist+2.1, dist+2.8):
            ex, ey = px + dx*dd, py + dy*dd
            if not (0.8 < ex < BW-0.8 and 0.8 < ey < BH-0.8): continue
            if not seg_clear(min(px,ex),py if dy==0 else min(py,ey),
                             max(px,ex),py if dy==0 else max(py,ey), nm, w, pcbnew.F_Cu): continue
            if not via_clear(ex, ey, nm): continue
            raw(min(px,ex), min(py,ey), max(px,ex), max(py,ey), nm, w, pcbnew.F_Cu)
            via(ex, ey, nm)
            return (ex, ey)
    print(f"ESCDBG {f.GetReference()} pad {num} ({nm}) at ({px:.2f},{py:.2f})")
    for layer,lab in [(pcbnew.F_Cu,"F"),(pcbnew.B_Cu,"B")]:
        for (ox1,oy1,ox2,oy2,onm,ow) in segs[layer]:
            if onm != nm and abs(ox1-px)<5 and abs(oy1-py)<8:
                print(f"  seg {lab} {onm} ({ox1:.2f},{oy1:.2f})->({ox2:.2f},{oy2:.2f}) w={ow}")
    for (vx,vy,vn) in via_pts:
        if vn != nm and abs(vx-px)<5 and abs(vy-py)<8:
            print(f"  via {vn} ({vx:.2f},{vy:.2f})")
    for (dx,dy) in dirs:
        for dd in (dist, dist+0.7, dist+1.4, dist+2.1, dist+2.8):
            ex, ey = px + dx*dd, py + dy*dd
            if not (0.8 < ex < BW-0.8 and 0.8 < ey < BH-0.8):
                print(f"  ({ex:.2f},{ey:.2f}): off-board"); continue
            x1,y1 = min(px,ex), py if dy==0 else min(py,ey)
            x2,y2 = max(px,ex), py if dy==0 else max(py,ey)
            if not seg_clear(x1,y1,x2,y2,nm,w,pcbnew.F_Cu):
                why = "?"
                horiz = abs(y1-y2) < 1e-9
                for (qx,qy,qn,qhx,qhy,qt) in hole_pts:
                    if qn == nm: continue
                    gx2, gy2 = w/2+qhx+0.2-EPS, w/2+qhy+0.2-EPS
                    hit = (abs(y1-qy)<gy2 and _hit(x1,x2,qx,gx2)) if horiz else (abs(x1-qx)<gx2 and _hit(y1,y2,qy,gy2))
                    if hit: why = f"pad {qn or 'NP'} ({qx:.2f},{qy:.2f}) h=({qhx},{qhy})"; break
                print(f"  ({ex:.2f},{ey:.2f}): stub blocked by {why}")
            elif not via_clear(ex,ey,nm):
                print(f"  ({ex:.2f},{ey:.2f}): via blocked")
            else:
                print(f"  ({ex:.2f},{ey:.2f}): ?? (race)")
    for (qx,qy,qn,qhx,qhy,qt) in hole_pts:
        if abs(qx-px) < 5 and abs(qy-py) < 6 and qn != nm:
            print(f"  pad {qn or '(none)'} ({qx:.2f},{qy:.2f}) h=({qhx:.2f},{qhy:.2f}) tht={qt}")
    raise RuntimeError(f"escape blocked {f.GetReference()} pad {num} ({nm})")
E, W_, N_, S_ = (1,0), (-1,0), (0,-1), (0,1)

def link(nm, pts, y0=None, w=TRK_SIG):
    """Join a list of already-escaped via points / THT pad points."""
    if y0 is None: y0 = sum(p[1] for p in pts)/len(pts)
    corridor(nm, y0, pts, w)

# =============================== hookup ===============================
# --- escapes (SMD pads that need tracks); THT pads used directly.
def esc(f, num, dirs, **kw): return escape(f, num, dirs, **kw)

espW = {n: esc(esp, n, [W_]) for n in (2, 3)}                 # 3V3, EN (left col)
espW[10] = esc(esp, 10, [E]); espW[11] = esc(esp, 11, [E])    # /PL CP (right col)
espW[12] = esc(esp, 12, [E]); espW[13] = esc(esp, 13, [E])    # G27 SER
espW[25] = esc(esp, 25, [E]); espW[34] = esc(esp, 34, [E]); espW[35] = esc(esp, 35, [E])
for n in (1, 15, 38): esc(esp, n, [W_, E])                    # GND stitches

usbv = {}
_clr_save = CLR; globals()['CLR'] = 0.15       # 0.65mm-pitch fanout zone
for pn in (2, 1, 3):                            # middle pad first: auto-stagger
    usbv[pn] = esc(usb, pn, [S_], w=0.3)
esc(usb, 5, [S_], w=0.3)                        # GND via
globals()['CLR'] = _clr_save
chv = {n: esc(ch, n, [E if pad_xy(ch,n)[0] > 31.0 else W_, N_, S_]) for n in (2,3,4,5,6)}
chv[16] = esc(ch, 16, [S_, W_, N_])
esc(ch, 1, [W_, E, N_, S_])                                               # GND
tpv = {n: esc(tp, n, [W_ if pad_xy(tp,n)[0] < 34.0 else E, N_, S_]) for n in (2,4,5,7,8)}
for n in (1,3): esc(tp, n, [W_ if pad_xy(tp,n)[0] < 34.0 else E, N_, S_])
def escape_pt(nm, px, py, dirs, dist=ESC, w=TRK_SIG):
    for (dx,dy) in dirs:
        for dd in (dist, dist+0.7, dist+1.4, dist+2.1, dist+2.8):
            ex, ey = px + dx*dd, py + dy*dd
            if not (0.8 < ex < BW-0.8 and 0.8 < ey < BH-0.8): continue
            if not seg_clear(min(px,ex),py if dy==0 else min(py,ey),
                             max(px,ex),py if dy==0 else max(py,ey), nm, w, pcbnew.F_Cu): continue
            if not via_clear(ex, ey, nm): continue
            raw(min(px,ex), min(py,ey), max(px,ex), max(py,ey), nm, w, pcbnew.F_Cu)
            via(ex, ey, nm)
            return (ex, ey)
    raise RuntimeError(f"escape_pt blocked {nm} ({px},{py})")
ldov = {n: esc(ldo, n, [S_ if pad_xy(ldo,n)[1] > 31.5 else N_, W_, E]) for n in (1,3)}
_tab = max(pads_of(ldo,2), key=lambda p: pcbnew.ToMM(p.GetSize().x) * pcbnew.ToMM(p.GetSize().y))
ldov[2] = escape_pt("+3V3", pcbnew.ToMM(_tab.GetPosition().x), pcbnew.ToMM(_tab.GetPosition().y), [E, N_, S_], dist=2.4)
d1v = {n: esc(d1, n, [W_ if pad_xy(d1,n)[0] < 54.0 else E, N_, S_]) for n in (1,2)}
d2v = {1: esc(d2, 1, [N_, E, S_]), 2: esc(d2, 2, [S_, W_, N_])}
bufv = {n: esc(buf, n, [W_ if pad_xy(buf,n)[0] < 60.0 else E, N_, S_]) for n in (2,4,5)}
for n in (1,3): esc(buf, n, [N_ if pad_xy(buf,n)[1] < 20.0 else S_, W_ if pad_xy(buf,n)[0] < 60.0 else E])
sw1v = {n: esc(sw1, n, [W_, E, N_, S_]) for n in (1,2)}
sw2v = {1: esc(sw2, 1, [E, W_, S_])}
sw3v = {1: esc(sw3, 1, [E, W_, S_])}
for s in (sw2, sw3): esc(s, 2, [E, W_])                        # GND
rv = {}
for ref in ("R1","R5","R6","R7","C1","C2","C3","C4",
            "C5","C6","C7","C8","C9","LED1","LED2"):
    f = next(ff for ff in board.GetFootprints() if ff.GetReference()==ref)
    for pn in (1,2):
        nmm = pad_of(f,pn).GetNetname()
        if nmm == "GND":
            esc(f, pn, [N_, S_, E, W_])
        else:
            rv[(ref,pn)] = esc(f, pn, [N_, S_, E, W_])

btp = pad_xy(bt, 1)                                            # THT

def bconnect(nm, p1, p2, w=TRK_SIG):
    """Automated all-B.Cu path search between two via points: tries U-shapes
    (vert-horiz-vert) sweeping the horizontal channel y, then Z-shapes with an
    intermediate x. Commits the first fully clear path."""
    (x1,y1),(x2,y2) = p1,p2
    def vclear(x,ya,yb): return abs(ya-yb)<0.01 or seg_clear(x,min(ya,yb),x,max(ya,yb),nm,w,pcbnew.B_Cu)
    def hclear(xa,xb,y): return abs(xa-xb)<0.01 or seg_clear(min(xa,xb),y,max(xa,xb),y,nm,w,pcbnew.B_Cu)
    ys = [1.5 + 0.35*k for k in range(int((BH-3)/0.35))]
    ys.sort(key=lambda yy: abs(yy-(y1+y2)/2))
    for ym in ys:
        if vclear(x1,y1,ym) and hclear(x1,x2,ym) and vclear(x2,ym,y2):
            if abs(ym-y1)>0.01: raw(x1,min(y1,ym),x1,max(y1,ym),nm,w,pcbnew.B_Cu)
            if abs(x1-x2)>0.01: raw(min(x1,x2),ym,max(x1,x2),ym,nm,w,pcbnew.B_Cu)
            if abs(ym-y2)>0.01: raw(x2,min(ym,y2),x2,max(ym,y2),nm,w,pcbnew.B_Cu)
            return
    # hybrid: B risers + F.Cu horizontal channel (vias at both bends)
    def fhclear(xa,xb,y): return abs(xa-xb)<0.01 or seg_clear(min(xa,xb),y,max(xa,xb),y,nm,w,pcbnew.F_Cu)
    for ym in ys:
        if not (vclear(x1,y1,ym) and vclear(x2,ym,y2)): continue
        if not (via_clear(x1,ym,nm) and via_clear(x2,ym,nm)): continue
        if not fhclear(x1,x2,ym): continue
        if abs(ym-y1)>0.01: raw(x1,min(y1,ym),x1,max(y1,ym),nm,w,pcbnew.B_Cu)
        via(x1,ym,nm)
        raw(min(x1,x2),ym,max(x1,x2),ym,nm,w,pcbnew.F_Cu)
        via(x2,ym,nm)
        if abs(ym-y2)>0.01: raw(x2,min(ym,y2),x2,max(ym,y2),nm,w,pcbnew.B_Cu)
        return
    # variant: F.Cu riser from p1 (crosses B-layer belts), then B channel
    def fvclear(x,ya,yb): return abs(ya-yb)<0.01 or seg_clear(x,min(ya,yb),x,max(ya,yb),nm,w,pcbnew.F_Cu)
    ys_fine = [1.5 + 0.05*k for k in range(int((BH-3)/0.05))]
    ys_fine.sort(key=lambda yy: abs(yy-(y1+y2)/2))
    for ym in ys_fine:
        if not fvclear(x1,y1,ym): continue
        if not via_clear(x1,ym,nm): continue
        if not (hclear(x1,x2,ym) and vclear(x2,ym,y2)): continue
        if abs(ym-y1)>0.01: raw(x1,min(y1,ym),x1,max(y1,ym),nm,w,pcbnew.F_Cu)
        via(x1,ym,nm)
        if abs(x1-x2)>0.01: raw(min(x1,x2),ym,max(x1,x2),ym,nm,w,pcbnew.B_Cu)
        if abs(ym-y2)>0.01: raw(x2,min(ym,y2),x2,max(ym,y2),nm,w,pcbnew.B_Cu)
        return
    xs = [1.5 + 0.5*k for k in range(int((BW-3)/0.5))]
    xs.sort(key=lambda xx: abs(xx-(x1+x2)/2))
    for ym in ys:
        if not (vclear(x1,y1,ym)): continue
        for xm in xs:
            if hclear(x1,xm,ym) and vclear(xm,ym,y2) and hclear(xm,x2,y2):
                if abs(ym-y1)>0.01: raw(x1,min(y1,ym),x1,max(y1,ym),nm,w,pcbnew.B_Cu)
                if abs(x1-xm)>0.01: raw(min(x1,xm),ym,max(x1,xm),ym,nm,w,pcbnew.B_Cu)
                if abs(ym-y2)>0.01: raw(xm,min(ym,y2),xm,max(ym,y2),nm,w,pcbnew.B_Cu)
                if abs(xm-x2)>0.01: raw(min(xm,x2),y2,max(xm,x2),y2,nm,w,pcbnew.B_Cu)
                return
    UNROUTED.append(f"bconnect {nm} {p1}->{p2}")

UNROUTED = []
def must_raw2(x1,y1,x2,y2,nm,w,layer):
    if not seg_clear(x1,y1,x2,y2,nm,w,layer):
        UNROUTED.append(f"{nm} seg ({x1},{y1})->({x2},{y2})"); return
    raw(x1,y1,x2,y2,nm,w,layer)

# --- nets
# VBUS bridge: USB island -> charger island, hand-routed B.Cu
ux, uy = usbv[1]
r6x, r6y = rv[("R6",2)]
must_raw2(ux, uy, ux, 7.3, "VBUS", TRK_SIG, pcbnew.B_Cu)
must_raw2(ux, 7.3, 51.0, 7.3, "VBUS", TRK_SIG, pcbnew.B_Cu)
must_raw2(51.0, 7.3, 51.0, 19.3, "VBUS", TRK_SIG, pcbnew.B_Cu)
must_raw2(42.6, 19.3, 55.5, 19.3, "VBUS", TRK_SIG, pcbnew.B_Cu)
must_raw2(55.5, 18.0, 55.5, 19.3, "VBUS", TRK_SIG, pcbnew.B_Cu)
must_raw2(55.5, 18.0, d1v[2][0], 18.0, "VBUS", TRK_SIG, pcbnew.B_Cu)
must_raw2(42.6, 19.3, 42.6, r6y, "VBUS", TRK_SIG, pcbnew.B_Cu)
must_raw2(r6x, r6y, 42.6, r6y, "VBUS", TRK_SIG, pcbnew.B_Cu)
link("TXD0", [espW[35], chv[3]], y0=35.0)
link("RXD0", [espW[34], chv[2]], y0=36.0)
_c = CLR; globals()["CLR"] = 0.18
bconnect("UDP", usbv[3], chv[5])
bconnect("UDM", usbv[2], chv[6])
globals()["CLR"] = _c
link("VSYS", [rv[("C7",1)], d1v[1], d2v[1]], y0=19.0, w=TRK_PWR)
lx3, ly3 = ldov[3]; c7x, c7y = rv[("C7",1)]
must_raw2(lx3, 33.4, lx3, ly3, "VSYS", TRK_SIG, pcbnew.B_Cu)
must_raw2(lx3, 33.4, 22.6, 33.4, "VSYS", TRK_SIG, pcbnew.B_Cu)
(via(22.6, 33.4, "VSYS") if via_clear(22.6, 33.4, "VSYS") else UNROUTED.append("via VSYS"))
must_raw2(22.6, 33.4, 37.9, 33.4, "VSYS", TRK_SIG, pcbnew.F_Cu)
(via(37.9, 33.4, "VSYS") if via_clear(37.9, 33.4, "VSYS") else UNROUTED.append("via VSYS"))
must_raw2(37.9, 33.4, 37.9, 36.1, "VSYS", TRK_SIG, pcbnew.B_Cu)
must_raw2(37.9, 36.1, 42.1, 36.1, "VSYS", TRK_SIG, pcbnew.B_Cu)
(via(42.1, 36.1, "VSYS") if via_clear(42.1, 36.1, "VSYS") else UNROUTED.append("via VSYS"))
must_raw2(42.1, c7y, 42.1, 36.1, "VSYS", TRK_SIG, pcbnew.F_Cu)
must_raw2(c7x, c7y, 42.1, c7y, "VSYS", TRK_SIG, pcbnew.F_Cu)
link("VSYS", [d1v[1], rv[("C8",1)], bufv[5]], y0=16.5, w=TRK_PWR)
link("VSYS", [bufv[5], j1s["VSYS"]], y0=7.5, w=TRK_PWR)
link("+3V3", [ldov[2], rv[("C9",1)], espW[2], rv[("C1",1)], rv[("C2",1)]], y0=19.0)
chv4b = escape_pt("+3V3", *pad_xy(ch,4), [E], dist=4.3)
bconnect("+3V3", chv4b, rv[("C4",1)])
bconnect("+3V3", chv[16], ldov[2])
bconnect("+3V3", j1s["+3V3"], rv[("C4",1)])
bconnect("+3V3", rv[("C1",1)], rv[("R1",2)])
bconnect("+3V3", rv[("R7",2)], j1s["+3V3"])



link("VBUS", [rv[("C5",1)], tpv[4]], y0=40.0, w=TRK_PWR)
bconnect("VBUS", tpv[4], tpv[8])
link("VBUS", [rv[("C5",1)], rv[("R6",2)]], y0=35.0)

link("BATP", [rv[("C6",1)], tpv[5]], y0=40.0, w=TRK_PWR)
tpv5b = esc(tp, 5, [S_], dist=3.2)
bconnect("BATP", tpv5b, btp)
# BATP: hand-routed down the left board edge (only free lane)
def must_raw(x1,y1,x2,y2,nm,w,layer):
    assert seg_clear(x1,y1,x2,y2,nm,w,layer), f"{nm} manual seg blocked ({x1},{y1})->({x2},{y2})"
    raw(x1,y1,x2,y2,nm,w,layer)
# BATP: battery+ via the empty bottom strip, up the empty right side
s1x, s1y = sw1v[1]
must_raw(btp[0], 49.5, btp[0], 49.4, "BATP", TRK_SIG, pcbnew.B_Cu)
must_raw(btp[0], 49.4, 78.0, 49.4, "BATP", TRK_SIG, pcbnew.B_Cu)
must_raw(78.0, s1y, 78.0, 49.4, "BATP", TRK_SIG, pcbnew.B_Cu)
must_raw(78.0, s1y, s1x, s1y, "BATP", TRK_SIG, pcbnew.B_Cu)
# VSW: hand-routed B.Cu channel at y=19.9 straight under the ESP32 pads
# (SMD pads only exist on F.Cu; the B side there is open highway)
sx, sy = sw1v[2]; dx, dy = d2v[2]
must_raw2(76.0, sy, sx, sy, "VSW", TRK_SIG, pcbnew.B_Cu)
must_raw2(76.0, sy, 76.0, 29.9, "VSW", TRK_SIG, pcbnew.B_Cu)
must_raw2(54.4, 29.9, 76.0, 29.9, "VSW", TRK_SIG, pcbnew.B_Cu)
(via(54.4, 29.9, "VSW") if via_clear(54.4, 29.9, "VSW") else UNROUTED.append("via VSW"))
must_raw2(54.4, dy, 54.4, 29.9, "VSW", TRK_SIG, pcbnew.F_Cu)
(via(54.4, dy, "VSW") if via_clear(54.4, dy, "VSW") else UNROUTED.append("via VSW"))
must_raw2(dx, dy, 54.4, dy, "VSW", TRK_SIG, pcbnew.B_Cu)

ex3, ey3 = espW[3]; swx, swy = sw2v[1]
must_raw2(ex3, ey3, 39.3, ey3, "EN", TRK_SIG, pcbnew.F_Cu)
(via(39.3, ey3, "EN") if via_clear(39.3, ey3, "EN") else UNROUTED.append("via EN"))
must_raw2(39.3, ey3, swx, ey3, "EN", TRK_SIG, pcbnew.B_Cu)
(via(swx, ey3, "EN") if via_clear(swx, ey3, "EN") else UNROUTED.append("via EN"))
must_raw2(swx, swy, swx, ey3, "EN", TRK_SIG, pcbnew.F_Cu)
bconnect("EN", espW[3], rv[("R1",1)])
bconnect("EN", rv[("R1",1)], rv[("C3",1)])
bconnect("IO0", espW[25], sw3v[1])
link("PROG", [tpv[2], rv[("R5",1)]], y0=44.0)
link("CHRGK", [tpv[7], rv[("R6",1)], rv[("LED1",2)]], y0=36.5)
link("PWRK", [rv[("R7",1)], rv[("LED2",2)]], y0=33.0)

link("/PL", [espW[10], j1s["/PL"]], y0=12.0)
link("CP",  [espW[11], j1s["CP"]], y0=13.0)
link("SER", [espW[13], j1s["SER"]], y0=14.0)
link("G27", [espW[12], bufv[2]], y0=15.0)
link("LEDD",[bufv[4], j1s["LEDD"]], y0=11.0)
link("+3V3",[rv[("C9",1)], j1s["+3V3"]], y0=10.5)

# GND stitch along J1 outer row
gpads = [pad_xy(j1,k) for k in range(1,13) if pad_of(j1,k).GetNetname()=="GND"]
gy = gpads[0][1]; xs = [p[0] for p in gpads]
raw(min(xs), gy, max(xs)+2.5, gy, "GND", TRK_SIG, pcbnew.F_Cu)
if via_clear(max(xs)+2.5, gy, "GND"): via(max(xs)+2.5, gy, "GND")

# =============================== silk / save ===============================
def silk(text, x, y, size=1.3):
    t = pcbnew.PCB_TEXT(board); t.SetText(text)
    t.SetPosition(VECTOR2I(MM(x),MM(y))); t.SetLayer(pcbnew.F_SilkS)
    t.SetTextSize(VECTOR2I(MM(size),MM(size))); t.SetTextThickness(MM(size*0.15))
    board.Add(t)
silk("CHESS HUB v2", 74.0, 12.0, 1.6)
silk("18650 + protected cell only", 44.0, 42.0, 1.1)

pcbnew.ZONE_FILLER(board).Fill(board.Zones())
pcbnew.SaveBoard(OUT, board)

LCSC = {"ESP32-WROOM-32E":"C701341","CH340C":"C84681","TP4056":"C725790",
        "AMS1117-3.3":"C6186","74AHCT1G125":"C7470","S8050":"C2150","SS34":"C8678",
        "PWR":"C221904","100n":"C5137636","10k":"C25804","5k1":"C25905","2k":"C22975",
        "1k":"C21190","1u":"C15849","10u":"C15850","CHG":"C2286","PWR2":"C2286"}
rows = {}
for f in board.GetFootprints():
    ref, val = f.GetReference(), f.GetValue()
    fpname = f.GetFPID().GetLibItemName().wx_str()
    rows.setdefault((val, fpname), []).append(ref)
with open(os.path.join(HERE, "hub_v2", "BOM.csv"), "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["Comment","Designator","Footprint","LCSC Part #"])
    for (val, fpname), refs in sorted(rows.items()):
        w.writerow([val, ",".join(sorted(refs)), fpname, LCSC.get(val, "")])
with open(os.path.join(HERE, "hub_v2", "positions.csv"), "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["Designator","Mid X","Mid Y","Layer","Rotation"])
    for f in board.GetFootprints():
        ref = f.GetReference()
        if ref in ("J1","BT1"): continue
        pos = f.GetPosition()
        w.writerow([ref, f"{pcbnew.ToMM(pos.x):.3f}mm", f"{-pcbnew.ToMM(pos.y):.3f}mm",
                    "Top", f"{f.GetOrientationDegrees():.0f}"])
print("UNROUTED (finish in KiCad GUI):")
for u_ in UNROUTED: print("  -", u_)
print(f"saved {OUT}")
print(f"tracks={len(segs[pcbnew.F_Cu])+len(segs[pcbnew.B_Cu])} vias={len(via_pts)}")
