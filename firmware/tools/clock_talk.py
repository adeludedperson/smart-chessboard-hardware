"""Talk to the dgt_clock_bridge over USB serial without resetting it.

Usage: python3 clock_talk.py SECONDS [cmd ...]
Each cmd is sent as a line (in order, 300 ms apart), then output is read
for SECONDS. Example: python3 clock_talk.py 6 debug scan wake
"""
import os, sys, termios, time, select, fcntl, struct

port = "/dev/cu.usbserial-0001"
dur = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
cmds = sys.argv[2:]
TIOCMBIC = 0x8004746b; TIOCM_DTR = 0x002; TIOCM_RTS = 0x004
fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
a = termios.tcgetattr(fd); a[0] = a[1] = a[3] = 0
a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL; a[4] = a[5] = 115200
a[6][termios.VMIN] = 0; a[6][termios.VTIME] = 0
termios.tcsetattr(fd, termios.TCSANOW, a)
# keep DTR/RTS low so the board does not reset
fcntl.ioctl(fd, TIOCMBIC, struct.pack('I', TIOCM_DTR | TIOCM_RTS))
time.sleep(0.2)
for c in cmds:
    os.write(fd, (c + "\n").encode()); time.sleep(0.3)
buf = b''; t = time.time()
while time.time() - t < dur:
    r, _, _ = select.select([fd], [], [], 0.2)
    if r:
        try: buf += os.read(fd, 4096)
        except OSError: pass
os.close(fd)
sys.stdout.write(buf.decode(errors='replace'))
