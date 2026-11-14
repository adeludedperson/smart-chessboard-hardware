from PIL import Image, ImageDraw, ImageFont

W, H = 2200, 1750
img = Image.new("RGB", (W, H), "#1e1e28")
d = ImageDraw.Draw(img)

def font(sz, bold=True):
    return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", sz, index=1 if bold else 0)

F_TITLE = font(62); F_BIG = font(44); F_MED = font(36); F_SM = font(29, False)

d.text((60, 36), "ONE SENSOR TEST — wire it exactly like this", font=F_TITLE, fill="#ffffff")

# ---------------- breadboard (vertical) ----------------
BX, BY, BW, BH = 1500, 170, 620, 1100
d.rounded_rectangle([BX, BY, BX+BW, BY+BH], 18, fill="#f2f0ea", outline="#c8c4ba", width=3)
GX = BX + BW//2
d.rectangle([GX-16, BY+20, GX+16, BY+BH-20], fill="#d8d4cc")

hole = 9; row_gap = 38; col_gap = 44
def hole_xy(side, col, row):
    if side == 'L':
        x = GX - 40 - (4-col)*col_gap
    else:
        x = GX + 40 + col*col_gap
    y = BY + 60 + row*row_gap
    return x, y

for r in range(26):
    for c in range(5):
        for s in ('L','R'):
            x,y = hole_xy(s,c,r)
            d.rectangle([x-hole//2, y-hole//2, x+hole//2, y+hole//2], fill="#3a3a3a")

ROWS = {"VCC": 11, "GND": 12, "OUT": 13}
hl_colors = {"VCC": "#e5484d", "GND": "#888888", "OUT": "#e8842c"}
for name, r in ROWS.items():
    x0,y0 = hole_xy('L',0,r); x1,y1 = hole_xy('L',4,r)
    d.rounded_rectangle([x0-18, y0-16, x1+18, y1+16], 12, outline=hl_colors[name], width=5)

# "row of 5 connected" annotation, top right of breadboard
x5,y5 = hole_xy('R',0,3)
d.rounded_rectangle([x5-18, y5-16, hole_xy('R',4,3)[0]+18, y5+16], 12, outline="#7fd87f", width=4)
d.text((BX+BW+20, y5-40), "one short row of\n5 holes = connected\ninside the plastic", font=F_SM, fill="#7fd87f", align="left")

# ---------------- sensor ----------------
sx, sy = hole_xy('L', 1, ROWS["VCC"])
bx0 = sx - 300; by0 = sy - 20
d.rounded_rectangle([bx0, by0, bx0+160, by0+180], 14, fill="#111111", outline="#555555", width=3)
d.text((bx0+80, by0+62), "A3144", font=F_SM, fill="#cccccc", anchor="mm")
d.text((bx0+80, by0+112), "flat face\ntoward YOU", font=font(22,False), fill="#999999", anchor="mm", align="center")
leg_y = [by0+35, by0+90, by0+145]
for i, name in enumerate(["VCC","GND","OUT"]):
    tx, ty = hole_xy('L', 1, ROWS[name])
    d.line([bx0+160, leg_y[i], tx, ty], fill="#b8b8c0", width=7)
    d.ellipse([tx-9, ty-9, tx+9, ty+9], fill="#ffcf3f")
    lx, lyy = hole_xy('L', 4, ROWS[name])
    d.text((lx+30, lyy), name+" row", font=F_SM, fill=hl_colors[name], anchor="lm")
d.text((bx0+80, by0-100), "SENSOR:\n3 legs → 3 different rows", font=F_SM, fill="#ffcf3f", anchor="ma", align="center")

# ---------------- ESP32 ----------------
EX, EY, EW, EH = 180, 260, 400, 850
d.rounded_rectangle([EX, EY, EX+EW, EY+EH], 16, fill="#26343f", outline="#3d5566", width=3)
d.rounded_rectangle([EX+EW//2-90, EY+30, EX+EW//2+90, EY+190], 8, fill="#8fa3ad")
d.text((EX+EW//2, EY+110), "ESP32", font=F_MED, fill="#26343f", anchor="mm")
d.rectangle([EX+EW//2-55, EY+EH-55, EX+EW//2+55, EY+EH], fill="#8fa3ad")
d.text((EX+EW//2, EY+EH+30), "micro-USB cable → Mac mini\n(already plugged in)", font=F_SM, fill="#8fa3ad", anchor="ma", align="center")

pin_rows = 19
pins = {}
for i in range(pin_rows):
    py = EY + 55 + i * (EH-110)//(pin_rows-1)
    for side, px in (('L', EX+18), ('R', EX+EW-18)):
        d.ellipse([px-7, py-7, px+7, py+7], fill="#d4af37")
        pins[(side,i)] = (px, py)

LBL = {"VIN": ('R', 18), "GND": ('R', 17), "D27": ('R', 8)}
for name,(s,i) in LBL.items():
    px, py = pins[(s,i)]
    d.text((px-40, py), name, font=F_BIG, fill="#ffffff", anchor="rm")
d.text((EX+EW//2, EY-90), "pin names are printed in tiny\nwhite text — find these 3", font=F_SM, fill="#9ab", anchor="ma", align="center")

# ---------------- wires ----------------
wires = [
    ("VCC", "#e5484d", "VIN"),
    ("GND", "#3c3c46", "GND"),
    ("OUT", "#e8842c", "D27"),
]
sag = {"VCC": 300, "GND": 380, "OUT": 120}
for name, color, pin in wires:
    s,i = LBL[pin]; px, py = pins[(s,i)]
    tx, ty = hole_xy('L', 3, ROWS[name])
    d.rounded_rectangle([px-15, py-15, px+15, py+15], 4, outline=color, width=6)
    midy = max(py, ty) + sag[name]
    pts = []
    steps = 50
    for t in range(steps+1):
        t/=steps
        x = (1-t)**2*(px+20) + 2*(1-t)*t*((px+tx)//2) + t*t*tx
        y = (1-t)**2*py + 2*(1-t)*t*midy + t*t*(ty+14)
        pts.append((x,y))
    d.line(pts, fill=color, width=9, joint="curve")
    d.ellipse([tx-9, ty-9, tx+9, ty+9], fill=color)

# socket/pin explainer
d.text((EX+EW+40, EY+70), "socket end of wire\npushes DOWN onto\nan ESP32 pin", font=F_SM, fill="#cccccc")
d.text((BX-380, BY+BH-120), "pin end of wire pushes into a free hole\nIN THE SAME ROW as the sensor leg", font=F_SM, fill="#cccccc")

# ---------------- steps bar (bottom, full width, no overlap) ----------------
SY = 1400
d.rectangle([0, SY-30, W, H], fill="#14141c")
steps_list = [
    ("1", "#ffcf3f", "Sensor in: flat face toward you, legs down → 3 different rows"),
    ("2", "#e5484d", "RED wire:  VIN pin  →  VCC row (left leg)"),
    ("3", "#9a9aa4", "DARK wire:  GND pin  →  GND row (middle leg)"),
    ("4", "#e8842c", "ORANGE wire:  D27 pin  →  OUT row (right leg)"),
    ("5", "#7fd87f", "Magnet to flat face.  Nothing?  FLIP the magnet."),
]
y = SY + 10
for num, col, txt in steps_list:
    d.ellipse([80, y, 132, y+52], fill=col)
    d.text((106, y+26), num, font=F_MED, fill="#111111", anchor="mm")
    d.text((160, y+26), txt, font=F_MED, fill="#eeeeee", anchor="lm")
    y += 66

import pathlib
img.save(str(pathlib.Path(__file__).resolve().parent.parent / "renders" / "sensor_wiring.png"))
print("saved")
