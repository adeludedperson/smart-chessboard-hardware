#!/usr/bin/env python3
# live_board32.py - live web dashboard for quadrant_diag32 / quadrant_test32.
# Reads "raw = 0xNNNNNNNN" lines from serial, serves TWO 4x4 live grids at
# http://localhost:8123 , logs frames to /tmp/live_board32.log
#
# Bit order (proven chain): ESP32 reads board B (last in chain) first.
#   bits 0..15  = board B, via ORDER
#   bits 16..31 = board A, via ORDER
# Square index in state arrays: 0..15 = board A S0..S15, 16..31 = board B S0..S15.
import os, termios, time, select, re, json, threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

PORT = 8123
SERIAL = "/dev/cu.usbserial-0001"
ORDER = [15,14,11,10,2,3,6,7,13,12,9,8,0,1,4,5]

state = {"now": [False]*32, "seen": [0]*32, "frames": 0, "last": 0.0}
lock = threading.Lock()
log = open("/tmp/live_board32.log", "a")

def open_port():
    fd = os.open(SERIAL, os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK)
    a = termios.tcgetattr(fd); a[0]=a[1]=a[3]=0
    a[2] = termios.CS8|termios.CREAD|termios.CLOCAL; a[4]=a[5]=115200
    a[6][termios.VMIN]=0; a[6][termios.VTIME]=0
    termios.tcsetattr(fd, termios.TCSANOW, a)
    return fd

def serial_loop():
    fd = None
    buf = b''
    while True:
        if fd is None:
            try: fd = open_port()
            except OSError:
                time.sleep(2); continue
        r,_,_ = select.select([fd],[],[],0.2)
        if r:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                chunk = b''
            if chunk == b'':
                # dead/unplugged port: close and retry instead of spinning hot
                try: os.close(fd)
                except OSError: pass
                fd = None; time.sleep(2); continue
            buf += chunk
        while b'\n' in buf:
            line, buf = buf.split(b'\n',1)
            m = re.search(rb'raw = 0x([0-9A-Fa-f]{8})', line)
            if not m: continue
            v = int(m.group(1),16)
            now = [False]*32
            for i in range(32):
                trig = not (v >> (31-i)) & 1
                if i < 16: now[16 + ORDER[i]] = trig      # board B
                else:      now[ORDER[i-16]] = trig        # board A
            with lock:
                state["now"] = now
                state["frames"] += 1
                state["last"] = time.time()
                for sq,t in enumerate(now):
                    if t: state["seen"][sq] += 1
            log.write(f"{time.time():.2f} raw=0x{v:08X}\n"); log.flush()

PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Board check - 32 squares</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
 body{margin:0;background:#0d1117;color:#e6edf3;font-family:-apple-system,sans-serif;
      display:flex;flex-direction:column;align-items:center;min-height:100vh}
 h1{font-size:20px;margin:18px 0 2px}
 #sub{color:#8b949e;font-size:13px;margin-bottom:14px;max-width:520px;text-align:center}
 #boards{display:flex;gap:34px;flex-wrap:wrap;justify-content:center}
 .bwrap{display:flex;flex-direction:column;align-items:center}
 .bname{font-size:14px;font-weight:600;margin-bottom:8px;color:#e6edf3}
 .grid{display:grid;grid-template-columns:repeat(4,min(11vw,92px));gap:8px}
 .sq{aspect-ratio:1;border-radius:12px;background:#1b2330;border:2px solid #2c3542;
     display:flex;flex-direction:column;align-items:center;justify-content:center;
     font-size:14px;color:#8b949e;transition:background .1s, border-color .1s;position:relative}
 .sq.on{background:#1a7f37;border-color:#3fd97a;color:#fff;box-shadow:0 0 20px #3fd97a66}
 .sq .tick{position:absolute;top:4px;right:7px;font-size:14px;visibility:hidden}
 .sq.done .tick{visibility:visible;color:#3fd97a}
 .sq.done{border-color:#3fd97a}
 #count{font-size:30px;font-weight:700;margin:16px 0 4px}
 #count.win{color:#3fd97a}
 #conn{font-size:12px;color:#8b949e;margin-bottom:8px}
 button{background:#21262d;color:#e6edf3;border:1px solid #30363d;border-radius:8px;
        padding:8px 16px;font-size:13px;margin-bottom:22px;cursor:pointer}
 #hint{color:#8b949e;font-size:12.5px;max-width:480px;text-align:center;line-height:1.5;margin-bottom:14px}
</style></head><body>
<h1>Magnet check &mdash; 32 squares, 2 boards</h1>
<div id="sub">Hold each board with its title text nearest you &mdash; each grid matches that view.
Board A = the board wired to the ESP32. Board B = the new board.</div>
<div id="boards">
 <div class="bwrap"><div class="bname">Board A (ESP32 harness)</div><div class="grid" id="gA"></div></div>
 <div class="bwrap"><div class="bname">Board B (new board)</div><div class="grid" id="gB"></div></div>
</div>
<div id="count">0 / 32</div>
<div id="conn">waiting for data&hellip;</div>
<button onclick="fetch('/reset',{method:'POST'})">Start over</button>
<div id="hint">Touch the magnet to each square for a second &mdash; the square turns
green when it feels it and keeps a &#10003; once it has worked. If a square stays dark,
flip the magnet over and try again.</div>
<script>
const gA=document.getElementById('gA'), gB=document.getElementById('gB');
for(let i=0;i<16;i++){const d=document.createElement('div');d.className='sq';
 d.id='sq'+i;d.innerHTML='S'+i+'<span class="tick">&#10003;</span>';gA.appendChild(d);}
for(let i=16;i<32;i++){const d=document.createElement('div');d.className='sq';
 d.id='sq'+i;d.innerHTML='S'+(i-16)+'<span class="tick">&#10003;</span>';gB.appendChild(d);}
async function poll(){
 try{
  const s=await (await fetch('/state')).json();
  let done=0;
  for(let i=0;i<32;i++){const el=document.getElementById('sq'+i);
   el.classList.toggle('on', s.now[i]);
   const ok=s.seen[i]>0; el.classList.toggle('done', ok); if(ok)done++;}
  const c=document.getElementById('count');
  c.textContent=done+' / 32'; c.classList.toggle('win', done===32);
  const age=Date.now()/1000-s.last;
  document.getElementById('conn').textContent =
    s.frames===0 ? 'waiting for data\u2026' :
    age>3 ? 'no data for '+age.toFixed(0)+'s \u2014 check the USB cable' :
    'live \u2014 reading '+s.frames+' frames';
 }catch(e){document.getElementById('conn').textContent='page lost the reader \u2014 restart this script';}
 setTimeout(poll,150);
}
poll();
</script></body></html>"""

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path == "/state":
            with lock: body = json.dumps(state).encode()
            self.send_response(200); self.send_header("Content-Type","application/json")
        else:
            body = PAGE.encode()
            self.send_response(200); self.send_header("Content-Type","text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        if self.path == "/reset":
            with lock: state["seen"] = [0]*32
        self.send_response(204); self.end_headers()

threading.Thread(target=serial_loop, daemon=True).start()
print(f"live at http://localhost:{PORT}")
ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
