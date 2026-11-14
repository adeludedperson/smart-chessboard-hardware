#!/usr/bin/env python3
# live_board.py - live web dashboard for quadrant_test firmware.
# Reads "raw = 0xNNNN" lines from serial, serves a 4x4 live grid at
# http://localhost:8123 , logs frames to /tmp/live_board.log
import os, termios, time, select, re, json, threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

PORT = 8123
SERIAL = "/dev/cu.usbserial-0001"
ORDER = [15,14,11,10,2,3,6,7,13,12,9,8,0,1,4,5]

state = {"now": [False]*16, "seen": [0]*16, "frames": 0, "last": 0.0}
lock = threading.Lock()
log = open("/tmp/live_board.log", "a")

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
            m = re.search(rb'raw = 0x([0-9A-Fa-f]{4})', line)
            if not m: continue
            v = int(m.group(1),16)
            now = [False]*16
            for i,sq in enumerate(ORDER):
                trig = not (v >> (15-i)) & 1
                now[sq] = trig
            with lock:
                state["now"] = now
                state["frames"] += 1
                state["last"] = time.time()
                for sq,t in enumerate(now):
                    if t: state["seen"][sq] += 1
            log.write(f"{time.time():.2f} raw=0x{v:04X}\n"); log.flush()

PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Board check</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
 body{margin:0;background:#0d1117;color:#e6edf3;font-family:-apple-system,sans-serif;
      display:flex;flex-direction:column;align-items:center;min-height:100vh}
 h1{font-size:20px;margin:18px 0 2px}
 #sub{color:#8b949e;font-size:13px;margin-bottom:14px}
 #grid{display:grid;grid-template-columns:repeat(4,min(20vw,120px));gap:10px}
 .sq{aspect-ratio:1;border-radius:14px;background:#1b2330;border:2px solid #2c3542;
     display:flex;flex-direction:column;align-items:center;justify-content:center;
     font-size:15px;color:#8b949e;transition:background .1s, border-color .1s;position:relative}
 .sq.on{background:#1a7f37;border-color:#3fd97a;color:#fff;box-shadow:0 0 24px #3fd97a66}
 .sq .tick{position:absolute;top:6px;right:8px;font-size:16px;visibility:hidden}
 .sq.done .tick{visibility:visible;color:#3fd97a}
 .sq.done{border-color:#3fd97a}
 #count{font-size:30px;font-weight:700;margin:16px 0 4px}
 #count.win{color:#3fd97a}
 #conn{font-size:12px;color:#8b949e;margin-bottom:8px}
 button{background:#21262d;color:#e6edf3;border:1px solid #30363d;border-radius:8px;
        padding:8px 16px;font-size:13px;margin-bottom:22px;cursor:pointer}
 #hint{color:#8b949e;font-size:12.5px;max-width:460px;text-align:center;line-height:1.5;margin-bottom:14px}
</style></head><body>
<h1>Magnet check &mdash; 16 squares</h1>
<div id="sub">Hold the board with the title text nearest you &mdash; this grid matches that view</div>
<div id="grid"></div>
<div id="count">0 / 16</div>
<div id="conn">waiting for data&hellip;</div>
<button onclick="fetch('/reset',{method:'POST'})">Start over</button>
<div id="hint">Touch the magnet to each square for a second &mdash; the square turns
green when it feels it and keeps a &#10003; once it has worked. If a square stays dark,
flip the magnet over and try again.</div>
<script>
const g=document.getElementById('grid');
for(let i=0;i<16;i++){const d=document.createElement('div');d.className='sq';
 d.id='sq'+i;d.innerHTML='S'+i+'<span class="tick">&#10003;</span>';g.appendChild(d);}
async function poll(){
 try{
  const s=await (await fetch('/state')).json();
  let done=0;
  for(let i=0;i<16;i++){const el=document.getElementById('sq'+i);
   el.classList.toggle('on', s.now[i]);
   const ok=s.seen[i]>0; el.classList.toggle('done', ok); if(ok)done++;}
  const c=document.getElementById('count');
  c.textContent=done+' / 16'; c.classList.toggle('win', done===16);
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
            with lock: state["seen"] = [0]*16
        self.send_response(204); self.end_headers()

threading.Thread(target=serial_loop, daemon=True).start()
print(f"live at http://localhost:{PORT}")
ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
