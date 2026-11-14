#!/usr/bin/env python3
"""Verify sensor footprint mirroring + net connectivity on the generated quadrant.

PASS criteria:
  * every sensor Sxx is on B.Cu (IsFlipped == True)
  * pad x-order is REVERSED vs the unflipped library default
    (library default: pad1 lowest x, pad3 highest x  ->  flipped: pad1 highest x)
  * pad2 (GND) stays at the square center
  * 0 unconnected items in the ratsnest

Run: <kicad python3.9> verify_flip.py [path/to/board.kicad_pcb]
"""
import os, sys
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "quadrant", "chess_quadrant.kicad_pcb")

board = pcbnew.LoadBoard(PCB)
S = 50.0
N = 4


def sq_center(i):
    return ((i % N + .5) * S, (i // N + .5) * S)


def pads(f):
    d = {}
    for p in f.Pads():
        pos = p.GetPosition()
        d[p.GetNumber()] = (pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y), p.GetNetname())
    return d


fps = {f.GetReference(): f for f in board.GetFootprints()}

print(f"board: {PCB}")
print(f"footprints: {len(fps)}")
print()

fails = []

print("=== SENSORS (all 16) ===")
print(f"{'ref':<5} {'layer':<6} {'flip':<6} {'rot':>7}  "
      f"{'pad1(+5V) x':>12} {'pad2(GND) x':>12} {'pad3(SENS) x':>13}  {'order':<10} {'nets':<22}")
for i in range(16):
    ref = f"S{i}"
    f = fps[ref]
    p = pads(f)
    x1, x2, x3 = p['1'][0], p['2'][0], p['3'][0]
    cx, cy = sq_center(i)
    mirrored = x1 > x3
    order = "MIRRORED" if mirrored else "unflipped"
    netstr = f"{p['1'][2]}/{p['2'][2]}/{p['3'][2]}"
    print(f"{ref:<5} {board.GetLayerName(f.GetLayer()):<6} {str(f.IsFlipped()):<6} "
          f"{f.GetOrientationDegrees():>7.1f}  "
          f"{x1:>12.2f} {x2:>12.2f} {x3:>13.2f}  {order:<10} {netstr:<22}")
    if not f.IsFlipped():
        fails.append(f"{ref}: not flipped (layer={board.GetLayerName(f.GetLayer())})")
    if not mirrored:
        fails.append(f"{ref}: pad x-order NOT mirrored (pad1={x1:.2f} pad3={x3:.2f})")
    if abs(x2 - cx) > 0.01 or abs(p['2'][1] - cy) > 0.01:
        fails.append(f"{ref}: pad2 off square center ({x2:.2f},{p['2'][1]:.2f}) != ({cx},{cy})")
    if (p['1'][2], p['2'][2], p['3'][2]) != ("+5V", "GND", f"SENS_{i}"):
        fails.append(f"{ref}: net mapping wrong -> {netstr}")

print()
print("=== PULL-UP RESISTORS (10k) ===")
for i in range(16):
    ref = f"R{i}"
    p = pads(fps[ref])
    print(f"{ref:<5} pad1 ({p['1'][0]:>7.2f},{p['1'][1]:>7.2f}) net={p['1'][2]:<9} "
          f"pad2 ({p['2'][0]:>7.2f},{p['2'][1]:>7.2f}) net={p['2'][2]:<6} "
          f"flip={fps[ref].IsFlipped()}")
    if (p['1'][2], p['2'][2]) != (f"SENS_{i}", "+3V3"):
        fails.append(f"{ref}: net mapping wrong -> {p['1'][2]}/{p['2'][2]}")
    if fps[ref].IsFlipped():
        fails.append(f"{ref}: should be on front, is flipped")

print()
print("=== CAPS (100n) ===")
for j in range(10):
    ref = f"C{j}"
    if ref not in fps:
        continue
    p = pads(fps[ref])
    exp = ("+5V", "GND") if j < 8 else ("+3V3", "GND")
    ok = (p['1'][2], p['2'][2]) == exp
    print(f"{ref:<5} pad1 ({p['1'][0]:>7.2f},{p['1'][1]:>7.2f}) net={p['1'][2]:<6} "
          f"pad2 net={p['2'][2]:<6} flip={fps[ref].IsFlipped()} {'ok' if ok else 'MISMATCH'}")
    if not ok:
        fails.append(f"{ref}: nets {p['1'][2]}/{p['2'][2]} != {exp}")
    if fps[ref].IsFlipped():
        fails.append(f"{ref}: should be on front, is flipped")

print()
print("=== REGISTERS / CONNECTORS flip state ===")
for ref in ["U1", "U2", "J1", "J2"]:
    f = fps[ref]
    print(f"{ref:<5} layer={board.GetLayerName(f.GetLayer()):<6} flip={f.IsFlipped()} "
          f"rot={f.GetOrientationDegrees():.1f}")
    if f.IsFlipped():
        fails.append(f"{ref}: should be on front, is flipped")

print()
print("=== EDGE CUTS BOUNDING BOX ===")
bb = board.GetBoardEdgesBoundingBox()
w = pcbnew.ToMM(bb.GetWidth())
h = pcbnew.ToMM(bb.GetHeight())
print(f"origin ({pcbnew.ToMM(bb.GetX()):.3f},{pcbnew.ToMM(bb.GetY()):.3f}) "
      f"size {w:.3f} x {h:.3f} mm")
if abs(w - 200.0) > 0.15 or abs(h - 200.0) > 0.15:
    fails.append(f"edge cuts {w:.3f}x{h:.3f} != 200x200")

print()
print("=== RATSNEST / UNCONNECTED ===")
board.BuildListOfNets()
conn = board.GetConnectivity()
conn.Build(board)
conn.RecalculateRatsnest()
unconn = conn.GetUnconnectedCount(True)
print(f"unconnected items: {unconn}")
if unconn != 0:
    fails.append(f"{unconn} unconnected items")

print()
if fails:
    print(f"RESULT: FAIL ({len(fails)} problems)")
    for m in fails:
        print("  -", m)
    sys.exit(1)
print("RESULT: PASS — all sensors mirrored on B.Cu, nets correct, 0 unconnected")
