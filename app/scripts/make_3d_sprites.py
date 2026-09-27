"""Builds the 3D look: Assets/3d/<sheet>.png for every sprite sheet the stage draws.

Each 80x128 pixel-art frame becomes a 320x512 pre-rendered 3D frame in the
same grid, so the 3D sheets line up with each other like the pixel ones. The
characters, wand and poof are modeled from their pixel art; the cauldron is
built in 3D. See scripts/sprite3d.py for how.

The app recolors some pixel sheets as they load (the empty cauldron, the
wizard's hem). The 3D sheets are made from the recolored pixels, using the
same JavaScript (src/renderer/sprites.js, run in node), so both looks match.

Run from app/: python3 scripts/make_3d_sprites.py   (needs numpy, scipy, Pillow, node; ~2.5 min)
Re-run after changing any sheet in Assets/ (including after make_witch_sprites.py).
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sprite3d  # noqa: E402

APP = Path(__file__).resolve().parents[1]
ASSETS = APP / "Assets"
OUT = ASSETS / "3d"
FW, FH, S = 80, 128, 4  # frame size and 3D scale

# sheet -> the recolor sprites.js applies to it at load time (or None)
SHEETS = {
    "wizard-sprites.png": "noStewShadow",
    "witch-sprites.png": "noStewShadow",
    "pot-sheet.png": "emptyPot",
    "wand-hand.png": None,
    "wizard-poof.png": None,
}


def recolor_like_the_app(rgba, fn):
    """Runs the named recolor from sprites.js on the pixels, exactly as the app does."""
    if not fn:
        return rgba
    h, w, _ = rgba.shape
    js = f"""
const vm = require('node:vm');
const fs = require('node:fs');
const ctx = {{}};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync({json.dumps(str(APP / 'src/renderer/sprites.js'))}, 'utf8') + ';this.fn = {fn};', ctx);
const data = new Uint8ClampedArray(fs.readFileSync(0));
ctx.fn({{ data, width: {w}, height: {h} }});
process.stdout.write(Buffer.from(data.buffer));
"""
    out = subprocess.run(["node", "-e", js], input=rgba.tobytes(), capture_output=True, check=True).stdout
    return np.frombuffer(out, np.uint8).reshape(h, w, 4).copy()


def build(name, recolor):
    t0 = time.time()
    sheet = np.array(Image.open(ASSETS / name).convert("RGBA"))
    sheet = recolor_like_the_app(sheet, recolor)
    rows, cols = sheet.shape[0] // FH, sheet.shape[1] // FW
    out = np.zeros((rows * FH * S, cols * FW * S, 4), np.uint8)
    cauldron = sprite3d.render_cauldron(FW, FH, S) if name == "pot-sheet.png" else None
    for r in range(rows):
        for c in range(cols):
            f = sheet[r * FH:(r + 1) * FH, c * FW:(c + 1) * FW]
            if cauldron is not None:  # the empty pot: every frame is the same cauldron
                img = cauldron if f[..., 3].any() else np.zeros_like(cauldron)
            else:
                img = sprite3d.render_sprite(f, S)
            out[r * FH * S:(r + 1) * FH * S, c * FW * S:(c + 1) * FW * S] = img
    OUT.mkdir(exist_ok=True)
    Image.fromarray(out).save(OUT / name, optimize=True)
    print(f"wrote {OUT / name} {out.shape[1]}x{out.shape[0]} in {time.time() - t0:.0f}s")


def main():
    names = sys.argv[1:] or list(SHEETS)  # e.g. `make_3d_sprites.py witch-sprites.png` rebuilds one
    for name in names:
        build(name, SHEETS[name])


if __name__ == "__main__":
    main()
