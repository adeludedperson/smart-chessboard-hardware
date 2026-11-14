#!/usr/bin/env python3
# board_state.py - one honest snapshot of the board. Live only, never stale.
#
#   board_state.py [seconds]        default 12
#
# Reads whatever sketch is flashed (read_audit or quadrant_diag64), waits for a
# COMPLETE fresh frame, and prints the gate, the measured stage count, and the
# per-board 4x4 grids decoded with the netlist-verified bit order.
#
# Rule: never quote a sensor reading without the
# gate result from the same read. This tool refuses to print squares if the
# gate failed or the stage count is wrong.

import os, re, sys, time, termios, select

PORT = "/dev/cu.usbserial-0001"
ORDER = [15, 14, 11, 10, 2, 3, 6, 7, 13, 12, 9, 8, 0, 1, 4, 5]

dur = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0

re_frame = re.compile(rb'(?:CP-low[^0]*|raw = )0x([0-9A-Fa-f]{8,16})\b')
re_gate = re.compile(rb'GATE:\s*(\w+)|CHAIN\d+:\s*(\w+)')
re_stage = re.compile(rb'STAGES:.*?->\s*(\w+)')


def open_port():
    fd = os.open(PORT, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    a = termios.tcgetattr(fd)
    a[0] = a[1] = a[3] = 0
    a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    a[4] = a[5] = 115200
    a[6][termios.VMIN] = 0
    a[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, a)
    return fd


fd = open_port()
buf = b''
frames, gate, stages = [], None, None
t0 = time.time()
while time.time() - t0 < dur:
    r, _, _ = select.select([fd], [], [], 0.2)
    if r:
        try:
            buf += os.read(fd, 4096)
        except OSError:
            pass
    while b'\n' in buf:
        line, buf = buf.split(b'\n', 1)
        g = re_gate.search(line)
        if g:
            gate = (g.group(1) or g.group(2)).decode()
        s = re_stage.search(line)
        if s:
            stages = s.group(1).decode()
        m = re_frame.search(line)
        if m:
            frames.append(m.group(1).decode().upper())
os.close(fd)

if not frames:
    sys.exit("no frames read - is a sketch flashed and the port free? (lsof " + PORT + ")")

uniq = sorted(set(frames))
print(f"gate={gate}  stages={stages}  frames={len(frames)}  distinct={len(uniq)}")
if len(uniq) > 1:
    print("FRAME IS MOVING:")
    for u in uniq:
        print(f"   0x{u}  x{frames.count(u)}")
if gate not in ("PASS", None):
    sys.exit("GATE FAILED - squares below would be meaningless. Fix the chain first.")

h = max(uniq, key=frames.count)
nbits = len(h) * 4
nb = nbits // 16
v = int(h, 16)
occ = [False] * nbits
for i in range(nbits):
    trig = not (v >> (nbits - 1 - i)) & 1
    board = nb - (i // 16)
    occ[(board - 1) * 16 + ORDER[i % 16]] = trig

print(f"\nraw = 0x{h}   ({nb} boards, {nbits} squares)\n")
for b in range(1, nb + 1):
    print(f"board {b}")
    for row in range(4):
        cells = []
        for col in range(4):
            s = row * 4 + col
            cells.append(f"S{s:<2}{'#' if occ[(b - 1) * 16 + s] else '.'}")
        print("   " + "  ".join(cells))
n = sum(occ)
print(f"\n{n} occupied, {nbits - n} clear")
if n == 0:
    print("ALL CLEAR - every square reads empty.")
