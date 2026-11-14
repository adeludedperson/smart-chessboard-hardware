import os,sys,termios,time,select,fcntl,struct
port="/dev/cu.usbserial-0001"; dur=float(sys.argv[1]) if len(sys.argv)>1 else 6.0
TIOCMBIS=0x8004746c; TIOCMBIC=0x8004746b; TIOCM_DTR=0x002; TIOCM_RTS=0x004
fd=os.open(port,os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK)
a=termios.tcgetattr(fd); a[0]=a[1]=a[3]=0
a[2]=termios.CS8|termios.CREAD|termios.CLOCAL; a[4]=a[5]=115200
a[6][termios.VMIN]=0; a[6][termios.VTIME]=0
termios.tcsetattr(fd,termios.TCSANOW,a)
def bits(op,v): fcntl.ioctl(fd,op,struct.pack('I',v))
bits(TIOCMBIC,TIOCM_DTR)           # DTR low  -> IO0 high (normal boot)
bits(TIOCMBIS,TIOCM_RTS); time.sleep(0.12)   # RTS -> EN low  = reset
bits(TIOCMBIC,TIOCM_RTS)
buf=b''; t=time.time()
while time.time()-t<dur:
    r,_,_=select.select([fd],[],[],0.2)
    if r:
        try: buf+=os.read(fd,4096)
        except OSError: pass
os.close(fd)
txt=buf.decode(errors='replace')
i=txt.find("=== QUADRANT")
sys.stdout.write(txt[i:] if i>=0 else txt)
