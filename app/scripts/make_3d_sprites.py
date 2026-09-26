"""Builds the 3D look: Assets/3d/<sheet>.png for every sprite sheet the stage draws.

Each 80x128 pixel-art frame becomes a 320x512 pre-rendered "clay" frame, in the
same grid, so the 3D sheets line up with each other exactly like the pixel ones:

1. Scale2x twice (4x) to smooth the staircase edges while keeping the palette.
2. A height map: one soft dome for the whole silhouette, plus a dome per part.
   Parts are split wherever neighboring colors differ a lot (hat vs face vs
   beard), so they bulge separately with creases between them; small shading
   steps inside a part stay smooth.
3. Lighting from the top left: diffuse, a soft highlight, ambient occlusion in
   the creases and a cool rim light on the shadow side.

The app recolors some pixel sheets as they load (the empty cauldron, the
wizard's hem). The 3D sheets are baked from the recolored pixels, using the
same JavaScript (src/renderer/sprites.js, run in node), so both looks match.

Run from app/: python3 scripts/make_3d_sprites.py   (needs numpy, scipy, Pillow, node)
Re-run after changing any sheet in Assets/ (including after make_witch_sprites.py).
"""
import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

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

LIGHT = np.array([-0.55, -0.65, 0.75])
LIGHT /= np.linalg.norm(LIGHT)
RIM_TINT = np.array([0.55, 0.65, 1.0])


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


def scale2x(img):
    """EPX / Scale2x on an HxWx4 array: doubles size, rounds off diagonal steps."""
    p = np.pad(img, ((1, 1), (1, 1), (0, 0)), mode="edge")
    c = p[1:-1, 1:-1]
    a, b, d, e = p[:-2, 1:-1], p[1:-1, 2:], p[1:-1, :-2], p[2:, 1:-1]  # up, right, left, down
    eq = lambda x, y: np.all(x == y, axis=-1)[..., None]
    k = ~eq(a, e) & ~eq(d, b)
    out = np.empty((img.shape[0] * 2, img.shape[1] * 2, 4), img.dtype)
    out[0::2, 0::2] = np.where(k & eq(d, a), a, c)
    out[0::2, 1::2] = np.where(k & eq(a, b), b, c)
    out[1::2, 0::2] = np.where(k & eq(d, e), d, c)
    out[1::2, 1::2] = np.where(k & eq(e, b), b, c)
    return out


def render(frame):
    """frame: 128x80x4 uint8 -> 512x320x4 uint8, lit."""
    up = scale2x(scale2x(frame))
    alpha = up[..., 3].astype(float) / 255
    painted = alpha > 0
    if not painted.any():
        return np.zeros_like(up)
    # A smoothed silhouette: pixel steps along shallow curves would otherwise show as ridges.
    solid = ndimage.gaussian_filter(painted.astype(float), 1.6) > 0.5
    solid |= ndimage.binary_erosion(painted, iterations=2)
    rgb = up[..., :3].astype(float) / 255

    # Part boundaries: neighbors whose colors differ a lot.
    lum = rgb @ np.array([0.3, 0.55, 0.15])
    diff = np.zeros(solid.shape, bool)
    for axis in (0, 1):
        dc = np.abs(np.diff(rgb, axis=axis)).sum(-1) + np.abs(np.diff(lum, axis=axis)) * 2
        edge = dc > 0.55
        if axis == 0:
            diff[:-1] |= edge
            diff[1:] |= edge
        else:
            diff[:, :-1] |= edge
            diff[:, 1:] |= edge

    d_all = ndimage.distance_transform_edt(solid)
    d_part = ndimage.distance_transform_edt(solid & ~diff)
    # Part domes get more smoothing than the overall shape, so pixel steps inside don't ripple.
    height = ndimage.gaussian_filter(1.6 * np.sqrt(np.minimum(d_all, 60)) * solid, 2.0)
    height += ndimage.gaussian_filter(1.1 * np.sqrt(np.minimum(d_part, 14)) * solid, 3.0)

    gy, gx = np.gradient(height)
    n = np.dstack([-gx * 1.3, -gy * 1.3, np.ones_like(height)])
    n /= np.linalg.norm(n, axis=-1, keepdims=True)

    diffuse = np.clip(n @ LIGHT, 0, 1)
    half = LIGHT + np.array([0, 0, 1.0])
    half /= np.linalg.norm(half)
    spec = np.clip(n @ half, 0, 1) ** 28 * 0.22
    cavity = ndimage.gaussian_filter(height, 5) - height
    ao = np.clip(1 - cavity * 0.09, 0.55, 1)
    rim = np.clip(1 - n[..., 2], 0, 1) ** 2 * np.clip(n[..., 0] * 0.8 + n[..., 1] * 0.6, 0, 1) * 0.5

    # Colors: fill outside the silhouette with the nearest inside color, so soft edges don't go dark.
    _, (iy, ix) = ndimage.distance_transform_edt(~painted, return_indices=True)
    rgb = rgb[iy, ix]
    shade = (0.52 + 0.7 * diffuse) * ao
    lit = rgb * shade[..., None] + spec[..., None] + rim[..., None] * RIM_TINT * rgb.mean(-1, keepdims=True) * 1.6
    # Soft, anti-aliased silhouette.
    soft = np.clip(ndimage.gaussian_filter(solid.astype(float), 0.7) * 1.6 - 0.3, 0, 1)
    see_through = ndimage.maximum_filter(np.where(painted, alpha, 0), 5)  # keeps smoke see-through
    a = np.minimum(soft, see_through)
    out = np.dstack([np.clip(lit, 0, 1), a])
    return (out * 255 + 0.5).astype(np.uint8)


def build(name, recolor):
    sheet = np.array(Image.open(ASSETS / name).convert("RGBA"))
    sheet = recolor_like_the_app(sheet, recolor)
    rows, cols = sheet.shape[0] // FH, sheet.shape[1] // FW
    out = np.zeros((rows * FH * S, cols * FW * S, 4), np.uint8)
    for r in range(rows):
        for c in range(cols):
            f = sheet[r * FH:(r + 1) * FH, c * FW:(c + 1) * FW]
            out[r * FH * S:(r + 1) * FH * S, c * FW * S:(c + 1) * FW * S] = render(f)
    OUT.mkdir(exist_ok=True)
    Image.fromarray(out).save(OUT / name, optimize=True)
    print("wrote", OUT / name, out.shape[1], "x", out.shape[0])


def main():
    for name, recolor in SHEETS.items():
        build(name, recolor)


if __name__ == "__main__":
    main()
