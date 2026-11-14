#!/usr/bin/env python3
"""Generate print-ready chessboard decal PDFs (exact 440x440 mm).

Layout:
  - total artwork 440x440 mm (cut size)
  - playing area 400x400 mm centred (8x8 squares of 50 mm)
  - 20 mm coordinate border, a1 dark square at bottom-left
Output: docs/stickers/decal_<scheme>.pdf via headless Chrome.
"""
import subprocess, pathlib

HERE = pathlib.Path(__file__).parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

SIZE = 440          # mm, cut size
BORDER = 20         # mm
SQ = 50             # mm
FILES = "abcdefgh"

SCHEMES = {
    "tournament_green": dict(light="#EDEBD3", dark="#3E7A57", frame="#2C5940"),
    "teal_eggshell":    dict(light="#EDEAE0", dark="#3A7C7B", frame="#275655"),
    "black_white":      dict(light="#F5F5F0", dark="#26262A", frame="#111114"),
}

def build_html(c):
    sq_divs = []
    for r in range(8):          # r = rank index 0..7 (rank 1 at bottom)
        for f in range(8):
            dark = (f + r) % 2 == 0          # a1 (f=0, r=0) is dark
            x = BORDER + f * SQ
            y = BORDER + (7 - r) * SQ        # SVG/CSS y-down
            sq_divs.append(
                f'<div class="sq" style="left:{x}mm;top:{y}mm;'
                f'background:{c["dark"] if dark else c["light"]}"></div>')
    labels = []
    for f in range(8):                        # files a..h, bottom + top
        cx = BORDER + f * SQ + SQ / 2
        for cy in (SIZE - BORDER / 2, BORDER / 2):
            labels.append(
                f'<div class="lab" style="left:{cx}mm;top:{cy}mm">{FILES[f]}</div>')
    for r in range(8):                        # ranks 1..8, left + right
        cy = BORDER + (7 - r) * SQ + SQ / 2
        for cx in (BORDER / 2, SIZE - BORDER / 2):
            labels.append(
                f'<div class="lab" style="left:{cx}mm;top:{cy}mm">{r + 1}</div>')
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
@page {{ size: {SIZE}mm {SIZE}mm; margin: 0; }}
* {{ margin: 0; padding: 0; }}
body {{ width: {SIZE}mm; height: {SIZE}mm; position: relative;
        background: {c['frame']}; -webkit-print-color-adjust: exact; }}
.sq  {{ position: absolute; width: {SQ}mm; height: {SQ}mm; }}
.lab {{ position: absolute; transform: translate(-50%, -50%);
        font: 700 8mm/1 Helvetica, Arial, sans-serif;
        color: {c['light']}; }}
</style></head><body>{''.join(sq_divs)}{''.join(labels)}</body></html>"""

for name, c in SCHEMES.items():
    html = HERE / f"decal_{name}.html"
    pdf = HERE / f"decal_{name}.pdf"
    html.write_text(build_html(c))
    subprocess.run([CHROME, "--headless", "--disable-gpu",
                    "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf}", str(html)],
                   check=True, capture_output=True)
    html.unlink()
    print(f"wrote {pdf.name}")
