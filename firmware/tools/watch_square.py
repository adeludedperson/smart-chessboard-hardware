#!/usr/bin/env python3
# watch_square.py - timestamped change log for a single square (or all of them).
#
#   watch_square.py [seconds] [board] [S]
#   watch_square.py 90 3 1        -> log every change of board 3 S1 for 90 s
#   watch_square.py 90            -> log every change of ANY square
#
# Parses the "A  CP-low ..." line from read_audit (or "sensors raw =" from
# quadrant_diag64), so it works with either sketch flashed. Chain length is
# taken from the hex width of the frame, so it never needs configuring.
#
# Prints t=+SS.s  board B SN  clear->OCCUPIED, plus a summary at the end.

import os, re, sys, time, termios, select

PORT = "/dev/cu.usbserial-0001"
ORDER = [15, 14, 11, 10, 2, 3, 6, 7, 13, 12, 9, 8, 0, 1, 4, 5]

dur = float(sys.argv[1]) if len(sys.argv) > 1 else 90.0
want = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) > 3 else None

pat = re.compile(rb'(?:CP-low[^0]*|raw = )0x([0-9A-Fa-f]{8,16})\b')


def decode(v, nbits):
    nb = nbits // 16
    occ = [False] * nbits
    for i in range(nbits):
        trig = not (v >> (nbits - 1 - i)) & 1
        board = nb - (i // 16)
        occ[(board - 1) * 16 + ORDER[i % 16]] = trig
    return occ


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
prev = None
t0 = time.time()
changes = 0
flips = {}          # square index -> number of transitions
lowsamples = {}     # square index -> samples seen reading OCCUPIED
nsamples = 0
label = f"board {want[0]} S{want[1]}" if want else "any square"
print(f"watching {label} for {dur:.0f}s — go\n", flush=True)

while time.time() - t0 < dur:
    r, _, _ = select.select([fd], [], [], 0.2)
    if r:
        try:
            buf += os.read(fd, 4096)
        except OSError:
            pass
    while b'\n' in buf:
        line, buf = buf.split(b'\n', 1)
        m = pat.search(line)
        if not m:
            continue
        h = m.group(1)
        nbits = len(h) * 4
        occ = decode(int(h, 16), nbits)
        if want:
            idx = (want[0] - 1) * 16 + want[1]
            if idx >= len(occ):
                continue
            cur = [occ[idx]]
        else:
            cur = occ
        nsamples += 1
        for i, b in enumerate(cur):
            if b:
                lowsamples[i] = lowsamples.get(i, 0) + 1
        if prev is None:
            prev = cur
            st = "OCCUPIED" if cur[0] else "clear"
            if want:
                print(f"t=+{time.time()-t0:5.1f}s  start: {label} = {st}", flush=True)
            continue
        for i, (a, b) in enumerate(zip(prev, cur)):
            if a != b:
                changes += 1
                flips[i] = flips.get(i, 0) + 1
                if want:
                    nm = label
                else:
                    nm = f"board {i//16+1} S{i%16}"
                arrow = "clear -> OCCUPIED" if b else "OCCUPIED -> clear"
                print(f"t=+{time.time()-t0:5.1f}s  {nm}  {arrow}", flush=True)
        prev = cur

os.close(fd)
final = "OCCUPIED" if prev and prev[0] else "clear"
print(f"\ndone. {changes} change(s).", end=" ")
if want:
    print(f"final: {label} = {final}")
    if changes == 0:
        print("NO RESPONSE to the magnet — this square never moved.")
else:
    print(f"{nsamples} samples\n")
    if not flips:
        print("ROCK SOLID - not one square changed state.")
    else:
        print(f"{'square':>14}  {'flips':>5}  {'% occupied':>10}")
        for i in sorted(flips, key=lambda k: -flips[k]):
            pct = 100.0 * lowsamples.get(i, 0) / max(nsamples, 1)
            print(f"   board {i//16+1} S{i%16:<3} {flips[i]:>8}  {pct:>9.1f}%")
        quiet = len(prev) - len(flips)
        print(f"\n{quiet} squares never changed state, {len(flips)} flipped.")
        if len(flips) == 1:
            print("ONE net misbehaving -> localized fault. Not chain, power or firmware.")
        else:
            print("MULTIPLE nets misbehaving -> global cause (supply or noise).")
