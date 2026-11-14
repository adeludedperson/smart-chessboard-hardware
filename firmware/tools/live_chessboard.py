#!/usr/bin/env python3
"""live_chessboard.py - real 8x8 chessboard view of the 4-quadrant sensor array.

Reads the `sensors raw = 0x...` lines from quadrant_diag64 (NUM_BOARDS = 4),
maps the 64 bits onto an actual chessboard, tracks pieces, and infers moves.

Three things the older live_board*.py dashboards do not do:

  1. **Gate status.** quadrant_diag64 re-runs the shift-only chain test every
     ~4 s and prints CHAIN64: PASS/FAIL. We parse it and show it. A dashboard
     that only shows sensor bits will happily display "all squares empty" when
     a jumper has fallen out, because a dead chain reads as all-ones. Never
     trust an occupancy reading without the gate.
  2. **Board mapping.** Which physical quadrant is which corner of the board
     was never verified. Four magnet touches (the four corner squares) is
     enough to derive it, including each board's rotation. Saved to
     chess_map.json so it only has to be done once.
  3. **Move inference.** Occupancy diffs -> lift/place events -> moves, with
     captures. Enough to watch real pieces move; the real engine lives in
     app/packages/core.

Bit order (proven): the first 16 bits read come from the LAST board in the
chain (the one P27 reads from); boards are numbered 1..4 from the harness end.
Magnet = bit LOW.
"""
import os, re, json, time, termios, select, threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

PORT = 8123
SERIAL = "/dev/cu.usbserial-0001"
NBOARDS = 4
NSQ = NBOARDS * 16
ORDER = [15, 14, 11, 10, 2, 3, 6, 7, 13, 12, 9, 8, 0, 1, 4, 5]
MAPFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chess_map.json")

FILES = "abcdefgh"
DEBOUNCE = 0.12          # seconds a change must hold before it counts

# Standard start position, by rank.
START_PIECES = {
    8: "rnbqkbnr", 7: "pppppppp", 2: "PPPPPPPP", 1: "RNBQKBNR",
}


def start_layout():
    return {f"{FILES[i]}{rank}": ch
            for rank, row in START_PIECES.items()
            for i, ch in enumerate(row)}

# ---------------------------------------------------------------- mapping ---

def sq_name(row, col):
    """row 0 = rank 8 (top), col 0 = file a (left)."""
    return f"{FILES[col]}{8 - row}"


def rotate(r, c, k):
    """Rotate a cell in a 4x4 grid by k*90 degrees clockwise."""
    for _ in range(k % 4):
        r, c = c, 3 - r
    return r, c


def build_map(corners):
    """corners: {'a8': (board, S), 'h8': ..., 'a1': ..., 'h1': ...}

    Each corner sits in a different quadrant, so it identifies that quadrant's
    board. The local square index at that corner pins down the board's
    rotation. Returns {"<board>.<S>": "e4", ...} or raises ValueError.
    """
    want = {"a8": (0, 0), "h8": (0, 7), "a1": (7, 0), "h1": (7, 7)}
    if set(corners) != set(want):
        raise ValueError("need exactly the four corners a8 h8 a1 h1")

    boards = [b for b, _ in corners.values()]
    if len(set(boards)) != 4:
        raise ValueError(
            "the four corners landed on only %d different boards - the corners "
            "were not all touched, or two quadrants are the same board"
            % len(set(boards)))

    mapping = {}
    for name, (board, S) in corners.items():
        grow, gcol = want[name]
        R0, C0 = (grow // 4) * 4, (gcol // 4) * 4      # quadrant origin
        tr, tc = grow - R0, gcol - C0                  # target cell in quadrant
        r, c = S // 4, S % 4                           # board-local cell

        for k in range(4):
            if rotate(r, c, k) == (tr, tc):
                break
        else:
            raise ValueError(f"no rotation puts {name}'s sensor S{S} in place")

        for s in range(16):
            rr, cc = rotate(s // 4, s % 4, k)
            mapping[f"{board}.{s}"] = sq_name(R0 + rr, C0 + cc)

    if len(set(mapping.values())) != 64:
        raise ValueError("mapping is not one-to-one - recalibrate")
    return mapping


def rot_square(name, times=1):
    """Rotate a square name 90 degrees clockwise, `times` times."""
    col, row = FILES.index(name[0]), 8 - int(name[1])   # row 0 = rank 8
    for _ in range(times % 4):
        row, col = col, 7 - row
    return sq_name(row, col)


def flip_square(name):
    """Mirror left-to-right. Only needed if a quadrant sits face-flipped."""
    col, row = FILES.index(name[0]), 8 - int(name[1])
    return sq_name(row, 7 - col)


def save_map(mp):
    with open(MAPFILE, "w") as f:
        json.dump(mp, f, indent=1, sort_keys=True)


def quadrant_map(board, R0, C0, k):
    """All 16 entries for one board placed at quadrant (R0,C0) with rotation k."""
    return {f"{board}.{s}": sq_name(R0 + rr, C0 + cc)
            for s in range(16)
            for rr, cc in [rotate(s // 4, s % 4, k)]}


QUADRANTS = [(0, 0), (0, 4), (4, 0), (4, 4)]


def verify_map(mp, occupied, slack=2):
    """Check a mapping against a full starting position.

    The four corner touches alone were too easy to get wrong: one
    mis-registered touch silently rotated a single quadrant, and no global
    rotation can undo that. Cross-checking the result against all 32 men
    catches it immediately. `slack` tolerates a couple of stuck sensors
    (b3.S1 is the known one) rather than failing the whole calibration.
    """
    target = set(start_layout())
    names = {mp[f"{b}.{s}"] for b, s in occupied if f"{b}.{s}" in mp}
    missing = target - names
    if missing:
        raise ValueError(
            "that layout does not match the pieces on the board "
            f"({len(missing)} starting squares read empty). Re-seat the pieces "
            "and calibrate again")
    if len(names - target) > slack:
        raise ValueError(
            f"{len(names - target)} squares read occupied that should be empty "
            "- clear the middle of the board and calibrate again")
    return True


def load_map():
    try:
        with open(MAPFILE) as f:
            return json.load(f)
    except Exception:
        return None


# ------------------------------------------------------------------ state ---

state = {
    "occupied": [],       # square names currently occupied
    "pieces": {},         # square -> glyph letter (uppercase = white)
    "moves": [],          # human-readable move log
    "events": [],         # recent lift/place events
    "gate": None,         # True / False / None(unknown)
    "gate_age": 0.0,
    "frames": 0,
    "last": 0.0,
    "mapped": False,
    "calibrating": False,
    "autocal": False,
    "cal_msg": "",
    "cal_step": 0,
    "cal_corners": {},
    "raw": "",
    "unmapped": [],       # (board,S) seen while uncalibrated
}
lock = threading.Lock()
CAL_ORDER = ["a1", "h1", "a8", "h8"]
ROOK_PROMPT = [
    "the rook on WHITE's LEFT (a1)",
    "the rook on WHITE's RIGHT (h1)",
    "the rook diagonally opposite the first one (a8)",
    "the last rook (h8)",
]


def decode(v):
    """64-bit word -> list of (board, S) that are occupied."""
    out = []
    for i in range(NSQ):
        if not (v >> (NSQ - 1 - i)) & 1:            # LOW = magnet
            board = NBOARDS - (i // 16)
            out.append((board, ORDER[i % 16]))
    return out


def infer(prev, now):
    """Turn an occupancy change into lift/place events and moves."""
    lifted = sorted(prev - now)
    placed = sorted(now - prev)
    evs = []
    for s in lifted:
        evs.append(("lift", s))
    for s in placed:
        evs.append(("place", s))
    return evs


class Tracker:
    """Minimal lift/place -> move inference. Captures handled, castling not."""

    def __init__(self):
        self.pending = []          # squares lifted and not yet accounted for

    def feed(self, evs, pieces, moves):
        for kind, sq in evs:
            if kind == "lift":
                self.pending.append(sq)
            else:                                   # place
                if not self.pending:
                    moves.append(f"?? piece appeared on {sq}")
                    continue
                # a piece placed on a square someone just left = a move;
                # placed on a square still held by another colour = capture
                src = self.pending.pop(0)
                glyph = pieces.pop(src, None)
                victim = pieces.get(sq)
                pieces[sq] = glyph if glyph else "?"
                if victim:
                    moves.append(f"{src}x{sq}")
                else:
                    moves.append(f"{src}-{sq}")
        # a lift with no matching place yet = piece in hand, that is fine


tracker = Tracker()


# ----------------------------------------------------------------- serial ---

def open_port():
    fd = os.open(SERIAL, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    a = termios.tcgetattr(fd)
    a[0] = a[1] = a[3] = 0
    a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    a[4] = a[5] = 115200
    a[6][termios.VMIN] = 0
    a[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, a)
    return fd


RAW_RE = re.compile(r"raw = 0x([0-9A-Fa-f]{16})")
GATE_RE = re.compile(r"CHAIN\d+:\s+(PASS|FAIL)")


def serial_loop():
    fd, buf = None, ""
    prev = set()
    cand, cand_since = set(), 0.0
    while True:
        if fd is None:
            try:
                fd = open_port()
            except OSError:
                time.sleep(2)
                continue
        r, _, _ = select.select([fd], [], [], 0.2)
        if r:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                chunk = b""
            if chunk == b"":
                try:
                    os.close(fd)
                except OSError:
                    pass
                fd = None
                time.sleep(2)
                continue
            buf += chunk.decode(errors="replace")

        # Consume COMPLETE lines only, once each. Scanning a retained buffer
        # re-matches old text forever: the frame counter climbs while the value
        # is frozen, which looks like a live feed and is not one.
        last_raw = None
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            g = GATE_RE.search(line)
            if g:
                with lock:
                    state["gate"] = (g.group(1) == "PASS")
                    state["gate_age"] = time.time()
            m = RAW_RE.search(line)
            if m:
                last_raw = m.group(1)
        if len(buf) > 4096:                 # runaway line, drop it
            buf = ""
        if last_raw is None:
            continue

        v = int(last_raw, 16)
        t = time.time()

        # Debounce: a new occupancy set must repeat for DEBOUNCE seconds before
        # we act on it. A piece sliding across a square trips neighbours for a
        # frame or two, and that would otherwise show up as phantom moves.
        now = set(decode(v))
        if now != cand:
            cand, cand_since = now, t
        if t - cand_since < DEBOUNCE:
            continue
        cells = sorted(now)

        with lock:
            state["frames"] += 1
            state["last"] = t
            state["raw"] = last_raw
            if state["autocal"]:
                gone = prev - now
                if len(gone) > 1:
                    state["cal_msg"] = "Lift ONE rook at a time."
                elif len(gone) == 1 and len(prev) >= 28:
                    corner = CAL_ORDER[state["cal_step"]]
                    state["cal_corners"][corner] = next(iter(gone))
                    state["cal_step"] += 1
                    if state["cal_step"] >= 4:
                        try:
                            mp = build_map(state["cal_corners"])
                            verify_map(mp, prev)
                            save_map(mp)
                            state["map"] = mp
                            state["mapped"] = True
                            state["pieces"] = {}
                            state["cal_msg"] = ("Calibrated and checked against "
                                                "all 32 pieces. Put the rook back.")
                            state["moves"].append("calibrated (verified)")
                        except ValueError as e:
                            state["cal_msg"] = f"FAILED: {e}"
                            state["mapped"] = bool(state.get("map"))
                        state["autocal"] = False
                        state["cal_step"] = 0
                    else:
                        state["cal_msg"] = (
                            "Got it - put that rook back, then lift "
                            + ROOK_PROMPT[state["cal_step"]])
                prev = now
                continue

            if state["calibrating"]:
                fresh = now - prev
                if len(fresh) == 1:
                    b, s = next(iter(fresh))
                    corner = CAL_ORDER[state["cal_step"]]
                    state["cal_corners"][corner] = (b, s)
                    state["cal_step"] += 1
                    if state["cal_step"] >= 4:
                        try:
                            mp = build_map(
                                {k: tuple(x) for k, x in state["cal_corners"].items()})
                            with open(MAPFILE, "w") as f:
                                json.dump(mp, f, indent=1, sort_keys=True)
                            state["map"] = mp
                            state["mapped"] = True
                            state["moves"].append("calibrated - mapping saved")
                        except ValueError as e:
                            state["moves"].append(f"calibration failed: {e}")
                        state["calibrating"] = False
                prev = now
                continue

            mp = state.get("map")
            if mp:
                names, unmapped = [], []
                for b, s in cells:
                    n = mp.get(f"{b}.{s}")
                    (names if n else unmapped).append(n or f"b{b}.S{s}")
                state["occupied"] = sorted(names)
                state["unmapped"] = unmapped
                # If the board is sitting in the standard opening setup and we
                # have no pieces yet, adopt it. Saves a button press, and makes
                # a wrong rotation obvious at a glance.
                if not state["pieces"] and set(names) == set(start_layout()):
                    state["pieces"] = start_layout()
                    state["moves"].append("start position detected")
                if now != prev:
                    evs = infer(
                        {mp.get(f"{b}.{s}") for b, s in prev if mp.get(f"{b}.{s}")},
                        set(names))
                    tracker.feed(evs, state["pieces"], state["moves"])
                    for kind, sq in evs:
                        state["events"].insert(0, f"{kind} {sq}")
                    del state["events"][40:]
                    del state["moves"][:-40]
            else:
                state["unmapped"] = [f"b{b}.S{s}" for b, s in cells]
            prev = now


# ------------------------------------------------------------------- page ---

PAGE = r"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Chessboard - live</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
 :root{--lt:#e8d3b0;--dk:#a97a52;--on:#3fd97a}
 body{margin:0;background:#0d1117;color:#e6edf3;font-family:-apple-system,sans-serif;
      display:flex;flex-direction:column;align-items:center;padding-bottom:40px}
 h1{font-size:19px;margin:16px 0 6px}
 #gate{font-size:13px;padding:6px 14px;border-radius:20px;margin-bottom:10px;font-weight:600}
 .ok{background:#12331e;color:#3fd97a;border:1px solid #1a7f37}
 .bad{background:#3a1416;color:#ff7b72;border:1px solid #a4232b}
 .unk{background:#21262d;color:#8b949e;border:1px solid #30363d}
 #wrap{display:flex;gap:26px;flex-wrap:wrap;justify-content:center;align-items:flex-start}
 #boardwrap{display:flex}
 #ranks{display:flex;flex-direction:column;justify-content:space-around;
        font-size:11px;color:#8b949e;padding-right:6px}
 #files{display:flex;justify-content:space-around;font-size:11px;color:#8b949e;padding-top:4px}
 #board{display:grid;grid-template-columns:repeat(8,min(9vw,64px));
        border:3px solid #2c3542;border-radius:4px;overflow:hidden}
 .sq{aspect-ratio:1;display:flex;align-items:center;justify-content:center;
     font-size:min(6vw,38px);position:relative;transition:box-shadow .08s}
 .sq.l{background:var(--lt)}.sq.d{background:var(--dk)}
 .sq.on{box-shadow:inset 0 0 0 4px var(--on)}
 .sq .dot{position:absolute;width:26%;height:26%;border-radius:50%;background:#1a7f37;opacity:.85}
 .sq .nm{position:absolute;bottom:2px;right:3px;font-size:9px;color:#00000055}
 #side{min-width:230px;max-width:300px}
 .card{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:12px 14px;margin-bottom:12px}
 .card h2{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:#8b949e;margin:0 0 8px}
 #moves,#events{font-family:ui-monospace,Menlo,monospace;font-size:12.5px;line-height:1.65;
                max-height:230px;overflow:auto}
 button{background:#21262d;color:#e6edf3;border:1px solid #30363d;border-radius:8px;
        padding:8px 14px;font-size:13px;cursor:pointer;margin:0 6px 6px 0}
 button:hover{background:#30363d}
 #calbox{background:#1b2330;border:1px solid #3fd97a;border-radius:10px;padding:14px;margin-bottom:12px}
 #caltarget{font-size:30px;font-weight:700;color:#3fd97a}
 #raw{font-family:ui-monospace,monospace;font-size:11px;color:#8b949e;word-break:break-all}
 .warn{color:#e3b341;font-size:12px;line-height:1.5}
</style></head><body>
<h1>Chessboard &mdash; live sensors</h1>
<div id="gate" class="unk">checking chain&hellip;</div>
<div id="wrap">
 <div>
  <div id="boardwrap"><div id="ranks"></div><div><div id="board"></div><div id="files"></div></div></div>
 </div>
 <div id="side">
  <div id="calbox" style="display:none">
   <h2 style="margin-top:0">Calibration</h2>
   <div>Put the magnet on this square, then take it away:</div>
   <div id="caltarget">a1</div>
   <div class="warn" id="calhint">Touch the corner square you want to be a1
     (white's bottom-left). The rest is worked out from it.</div>
  </div>
  <div class="card">
   <h2>Board</h2>
   <button onclick="fetch('/autocal',{method:'POST'})"><b>Auto-calibrate</b></button>
   <button onclick="fetch('/rotate',{method:'POST'})">&#8635; Rotate 90&deg;</button>
   <button onclick="fetch('/flip',{method:'POST'})">&#8646; Mirror</button>
   <button onclick="fetch('/start',{method:'POST'})">Set start position</button>
   <button onclick="fetch('/clearpieces',{method:'POST'})">Clear pieces</button>
   <button onclick="fetch('/calibrate',{method:'POST'})">Recalibrate corners</button>
   <div class="warn" id="calmsg">Set all 32 pieces up in the normal starting
     position, hit <b>Auto-calibrate</b>, then lift the rook on White's left.
     It works out all four quadrants from that.</div>
   <div class="warn" id="mapwarn"></div>
  </div>
  <div class="card"><h2>Moves</h2><div id="moves">&mdash;</div></div>
  <div class="card"><h2>Raw events</h2><div id="events">&mdash;</div></div>
  <div class="card"><h2>Raw word</h2><div id="raw">&mdash;</div></div>
 </div>
</div>
<script>
const FILES="abcdefgh";
const board=document.getElementById('board');
for(let r=0;r<8;r++)for(let c=0;c<8;c++){
 const d=document.createElement('div');
 d.className='sq '+(((r+c)%2)?'d':'l');
 d.id='sq-'+FILES[c]+(8-r);
 d.innerHTML='<span class="nm">'+FILES[c]+(8-r)+'</span>';
 board.appendChild(d);
}
const ranks=document.getElementById('ranks'),files=document.getElementById('files');
for(let r=8;r>=1;r--){const e=document.createElement('div');e.textContent=r;ranks.appendChild(e);}
for(let c=0;c<8;c++){const e=document.createElement('div');e.textContent=FILES[c];files.appendChild(e);}
const GLYPH={K:'\u2654',Q:'\u2655',R:'\u2656',B:'\u2657',N:'\u2658',P:'\u2659',
             k:'\u265A',q:'\u265B',r:'\u265C',b:'\u265D',n:'\u265E',p:'\u265F','?':'\u25CF'};
async function poll(){
 try{
  const s=await(await fetch('/state')).json();
  const g=document.getElementById('gate');
  const age=Date.now()/1000-s.last;
  if(s.frames===0){g.className='unk';g.textContent='waiting for the board\u2026';}
  else if(age>3){g.className='bad';g.textContent='no data for '+age.toFixed(0)+'s \u2014 check the USB cable';}
  else if(s.gate===false){g.className='bad';g.textContent='CHAIN FAIL \u2014 a jumper is loose. Squares below mean nothing.';}
  else if(s.gate===true){g.className='ok';g.textContent='chain OK \u2014 '+s.frames+' frames';}
  else {g.className='unk';g.textContent='chain state unknown';}

  const occ=new Set(s.occupied);
  for(let r=0;r<8;r++)for(let c=0;c<8;c++){
   const n=FILES[c]+(8-r), el=document.getElementById('sq-'+n);
   el.classList.toggle('on',occ.has(n));
   const pc=s.pieces[n];
   let inner='<span class="nm">'+n+'</span>';
   if(pc) inner+=GLYPH[pc]||pc;
   else if(occ.has(n)) inner+='<span class="dot"></span>';
   el.innerHTML=inner;
  }
  document.getElementById('moves').innerHTML =
    s.moves.length?s.moves.slice(-30).reverse().join('<br>'):'&mdash;';
  document.getElementById('events').innerHTML =
    s.events.length?s.events.slice(0,25).join('<br>'):'&mdash;';
  document.getElementById('raw').textContent='0x'+(s.raw||'');
  document.getElementById('calbox').style.display=s.calibrating?'block':'none';
  if(s.calibrating){
   document.getElementById('caltarget').textContent=['a1','h1','a8','h8'][s.cal_step]||'done';
   document.getElementById('calhint').textContent=
     'Corner '+(s.cal_step+1)+' of 4. Touch the magnet to it, then lift the magnet away.';
  }
  if(s.cal_msg) document.getElementById('calmsg').innerHTML=s.cal_msg;
  document.getElementById('mapwarn').innerHTML = s.mapped ? '' :
    'Not calibrated yet \u2014 squares cannot be named. Hit <b>Calibrate corners</b>.'
    + (s.unmapped.length? '<br>sensors reading now: '+s.unmapped.join(', ') : '');
 }catch(e){}
 setTimeout(poll,140);
}
poll();
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/state":
            with lock:
                pub = {k: v for k, v in state.items() if k != "map"}
                pub["cal_corners"] = {k: list(v) for k, v in state["cal_corners"].items()}
            self._send(json.dumps(pub).encode(), "application/json")
        else:
            self._send(PAGE.encode(), "text/html")

    def do_POST(self):
        with lock:
            if self.path == "/autocal":
                state["autocal"] = True
                state["calibrating"] = False
                state["cal_step"] = 0
                state["cal_corners"] = {}
                state["cal_msg"] = ("All 32 pieces set up? Lift "
                                    + ROOK_PROMPT[0])
            elif self.path == "/calibrate":
                state["calibrating"] = True
                state["cal_step"] = 0
                state["cal_corners"] = {}
                state["moves"].append("calibration started")
            elif self.path in ("/rotate", "/flip"):
                mp = state.get("map")
                if mp:
                    fn = rot_square if self.path == "/rotate" else flip_square
                    mp = {k: fn(v) for k, v in mp.items()}
                    state["map"] = mp
                    save_map(mp)
                    state["pieces"] = {}
                    state["moves"].append(
                        "rotated" if self.path == "/rotate" else "mirrored")
            elif self.path == "/start":
                state["pieces"] = start_layout()
                state["moves"] = ["start position set"]
                state["events"] = []
            elif self.path == "/clearpieces":
                state["pieces"] = {}
                state["moves"] = []
                state["events"] = []
        self.send_response(204)
        self.end_headers()


mp = load_map()
if mp:
    state["map"] = mp
    state["mapped"] = True

threading.Thread(target=serial_loop, daemon=True).start()
print(f"live chessboard at http://localhost:{PORT}"
      + ("" if mp else "  (not calibrated - use the Calibrate button)"))
ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
