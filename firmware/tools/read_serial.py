import os, sys, termios, time, select
port = "/dev/cu.usbserial-0001"
dur = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
a = termios.tcgetattr(fd)
a[0] = a[1] = a[3] = 0
a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
a[4] = a[5] = 115200
a[6][termios.VMIN] = 0; a[6][termios.VTIME] = 0
termios.tcsetattr(fd, termios.TCSANOW, a)
buf = b''; t = time.time()
while time.time() - t < dur:
    r, _, _ = select.select([fd], [], [], 0.2)
    if r:
        try: buf += os.read(fd, 4096)
        except OSError: pass
os.close(fd)
sys.stdout.write(buf.decode(errors='replace'))
