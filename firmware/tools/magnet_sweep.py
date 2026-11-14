import os, sys, termios, time, select, re
port="/dev/cu.usbserial-0001"
dur=float(sys.argv[1]) if len(sys.argv)>1 else 30.0
fd=os.open(port, os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK)
a=termios.tcgetattr(fd); a[0]=a[1]=a[3]=0
a[2]=termios.CS8|termios.CREAD|termios.CLOCAL; a[4]=a[5]=115200
a[6][termios.VMIN]=0; a[6][termios.VTIME]=0
termios.tcsetattr(fd, termios.TCSANOW, a)
seen=[0]*16; buf=b''; t=time.time(); frames=0
print(f"recording {dur:.0f}s - sweep the magnet over every square now...", flush=True)
while time.time()-t<dur:
    r,_,_=select.select([fd],[],[],0.2)
    if r:
        try: buf+=os.read(fd,4096)
        except OSError: pass
    while b'\n' in buf:
        line,buf=buf.split(b'\n',1)
        m=re.search(rb'raw = 0x([0-9A-Fa-f]{4})', line)
        if m:
            frames+=1
            v=int(m.group(1),16)
            # CHAIN_ORDER: bit (15-i) of raw corresponds to CHAIN_ORDER[i]
            order=[15,14,11,10,2,3,6,7,13,12,9,8,0,1,4,5]
            for i,sq in enumerate(order):
                if not (v>>(15-i))&1: seen[sq]+=1
os.close(fd)
print(f"\nframes read: {frames}\n")
print("      c0     c1     c2     c3")
for r_ in range(4):
    row=""
    for c in range(4):
        i=r_*4+c
        row += (" [ OK ]" if seen[i] else "  ----")
    print(f"r{r_} {row}    S{r_*4}..S{r_*4+3}")
dead=[i for i in range(16) if not seen[i]]
print()
if not dead: print("ALL 16 SQUARES RESPONDED")
else: print("no response from: " + ", ".join(f"S{i}" for i in dead))
