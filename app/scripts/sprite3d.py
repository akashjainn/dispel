"""Renderer for the 3D look (used by make_3d_sprites.py): smooth, pre-rendered
3D sprites, like a character modeled and lit in a 3D package.

Models
- Sprites (characters, wand, poof) are modeled from their pixel art. Each row
  is a slice of a rounded solid: a run of pixels gets a circular depth
  profile (a robe row is round, a hat brim a disc, a hair lock a tube),
  rounded off near the top and bottom of the silhouette. That solid becomes a
  smoothed signed distance field, so the surface is smooth, not blocky. The
  pixel art, upscaled and softened, is projected onto it from the front as
  its paint.
- The cauldron is an exact distance field: a round belly, a thick rim, a
  hollow inside, handles and feet. Its 2D art looks steeply down into the
  opening, so it gets a steeper camera that puts the rim where the pixel art
  has it and the characters still stand in it.

Rendering: sphere tracing, orthographic, turned 22 degrees. A warm key light
from the top left with soft shadows, a cool fill, a rim light, a soft
highlight, ambient occlusion from the distance field, 2x2 supersampling.
"""
import numpy as np
from scipy import ndimage

YAW = np.radians(22)
PITCH = np.radians(10)
G = 2  # sprite distance-field cells per stage pixel

KEY = np.array([-0.5, -0.62, 0.62])  # from the top left, in front (y is down)
KEY /= np.linalg.norm(KEY)
FILL = np.array([0.7, -0.1, 0.7])
FILL /= np.linalg.norm(FILL)
KEY_COLOR = np.array([1.0, 0.96, 0.9])
FILL_COLOR = np.array([0.55, 0.62, 0.85])


def rotation(yaw, pitch):
    cy, sy, cp, sp = np.cos(yaw), np.sin(yaw), np.cos(pitch), np.sin(pitch)
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])  # front turns right: we see the left side
    rx = np.array([[1, 0, 0], [0, cp, sp], [0, -sp, cp]])  # tops come toward the camera
    return rx @ ry


def scale2x(img):
    """EPX / Scale2x: doubles pixel art, rounding off diagonal steps."""
    p = np.pad(img, ((1, 1), (1, 1), (0, 0)), mode="edge")
    c = p[1:-1, 1:-1]
    a, b, d, e = p[:-2, 1:-1], p[1:-1, 2:], p[1:-1, :-2], p[2:, 1:-1]
    eq = lambda x, y: np.all(x == y, axis=-1)[..., None]
    k = ~eq(a, e) & ~eq(d, b)
    out = np.empty((img.shape[0] * 2, img.shape[1] * 2, img.shape[2]), img.dtype)
    out[0::2, 0::2] = np.where(k & eq(d, a), a, c)
    out[0::2, 1::2] = np.where(k & eq(a, b), b, c)
    out[1::2, 0::2] = np.where(k & eq(d, e), d, c)
    out[1::2, 1::2] = np.where(k & eq(e, b), b, c)
    return out


# ---------- models: each has sdf(p), color(p) and bounds, in stage pixels ----------


class SpriteModel:
    def __init__(self, rgba):
        up = scale2x(rgba) if G == 2 else rgba
        opaque = up[..., 3] > 0
        h, w = opaque.shape
        half = np.zeros((h, w))
        for y in range(h):
            edges = np.flatnonzero(np.diff(np.r_[0, opaque[y].astype(np.int8), 0]))
            for a, b in zip(edges[::2], edges[1::2]):
                r, c = (b - a) / 2, (a + b - 1) / 2
                x = np.arange(a, b)
                half[y, a:b] = np.sqrt(np.maximum(r * r - (x - c) ** 2, 0.25))
        dist = ndimage.distance_transform_edt(opaque)
        half = np.minimum(half * 0.8, 1.3 * dist + 0.8 * G)
        # Smooth mostly across rows: each row's depth is found on its own, and the
        # steps between rows would show as ridges.
        sig = (5.0, 1.5)
        half = ndimage.gaussian_filter(half * opaque, sig) / np.maximum(ndimage.gaussian_filter(opaque * 1.0, sig), 1e-6)
        half = np.where(opaque, np.maximum(half, 0.7 * G), 0)
        kz = int(np.ceil(half.max())) + 3
        z = np.arange(-kz, kz) + 0.5
        solid = opaque[..., None] & (np.abs(z)[None, None, :] < half[..., None])
        pad = 3
        solid = np.pad(solid, pad)
        sdf = ndimage.distance_transform_edt(~solid) - ndimage.distance_transform_edt(solid)
        self.sdf_grid = ndimage.gaussian_filter(sdf.astype(np.float32), 1.4)
        self.grad = np.stack(np.gradient(self.sdf_grid), -1)  # d/dy, d/dx, d/dz
        self.pad, self.kz = pad, kz
        self.lo = np.array([-pad / G, -pad / G, -(kz + pad) / G])
        self.hi = np.array([(w + pad) / G, (h + pad) / G, (kz + pad) / G])

        # Paint: 4x (Scale2x twice), softened a touch, colors carried past the edge.
        tex = scale2x(up).astype(np.float32) / 255
        inside = tex[..., 3] > 0
        _, (iy, ix) = ndimage.distance_transform_edt(~inside, return_indices=True)
        tex = tex[iy, ix]
        tex[..., :3] = ndimage.gaussian_filter(tex[..., :3], (0.7, 0.7, 0))
        self.tex, self.tex_scale = tex, 4

    def _coords(self, p):
        # stage px -> grid index (cell centers at .5): [y, x, z]
        return np.stack([p[:, 1] * G + self.pad - 0.5, p[:, 0] * G + self.pad - 0.5, p[:, 2] * G + self.kz + self.pad - 0.5])

    def sdf(self, p):
        return ndimage.map_coordinates(self.sdf_grid, self._coords(p), order=1, mode="nearest") / G

    def normal(self, p):
        c = self._coords(p)
        g = np.stack([ndimage.map_coordinates(self.grad[..., i], c, order=1, mode="nearest") for i in range(3)], 1)
        n = g[:, [1, 0, 2]]  # -> x, y, z
        return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)

    def color(self, p, n):
        s = self.tex_scale
        c = np.stack([p[:, 1] * s - 0.5, p[:, 0] * s - 0.5])
        return np.stack([ndimage.map_coordinates(self.tex[..., i], c, order=1, mode="nearest") for i in range(4)], 1)


# Cauldron palette, from pot-sheet.png.
POT_BODY, POT_RIM, POT_DARK, POT_INSIDE = (57, 74, 80), (38, 53, 62), (22, 29, 40), (14, 19, 27)
POT_PITCH = np.radians(38)  # the pixel art looks this steeply into the opening
POT_SCREEN = (40.0, 74.5)  # where the rim's center sits on the stage


def _smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b * (1 - h) + a * h - k * h * (1 - h)


def _ellipsoid(q, r):
    k0 = np.linalg.norm(q / r, axis=1)
    k1 = np.linalg.norm(q / (r * r), axis=1)
    return k0 * (k0 - 1) / np.maximum(k1, 1e-9)


class CauldronModel:
    RIM_Y, RIM_R, TUBE = 64.0, 35.5, 3.4
    BELLY_C, BELLY_R = 82.0, np.array([39.0, 26.0, 39.0])

    def __init__(self):
        self.pivot = np.array([40.0, self.RIM_Y, 0.0])
        self.lo = np.array([-2.0, 55.0, -44.0])
        self.hi = np.array([82.0, 120.0, 44.0])

    def parts(self, p):
        x, y, z = p[:, 0] - 40, p[:, 1], p[:, 2]
        rad = np.hypot(x, z)
        q = np.stack([x, y - self.BELLY_C, z], 1)
        belly = _ellipsoid(q, self.BELLY_R)
        belly = np.maximum(belly, self.RIM_Y - y)  # open at the rim
        inner = _ellipsoid(q, self.BELLY_R - 2.6)
        shell = np.maximum(belly, -inner)
        rim = np.hypot(rad - self.RIM_R, y - self.RIM_Y) - self.TUBE
        lugs = np.full_like(x, 1e9)
        for sx in (-1, 1):
            lugs = np.minimum(lugs, np.hypot(np.hypot(x - sx * 38.5, z) - 3.4, y - (self.RIM_Y + 9)) - 1.7)
        feet = np.full_like(x, 1e9)
        for a in np.radians([90, 210, 330]):
            feet = np.minimum(feet, np.linalg.norm(np.stack([x - 17 * np.cos(a), (y - 108) * 1.3, z - 17 * np.sin(a)], 1), axis=1) - 5.0)
        return shell, rim, lugs, feet, rad, y

    def sdf(self, p):
        shell, rim, lugs, feet, *_ = self.parts(p)
        body = _smin(shell, rim, 2.0)
        return np.minimum(np.minimum(body, lugs), _smin(body, feet, 2.5)) * 0.9

    def normal(self, p, e=0.15):
        n = np.stack([self.sdf(p + d) - self.sdf(p - d) for d in np.eye(3) * e], 1)
        return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)

    def color(self, p, n):
        shell, rim, lugs, feet, rad, y = self.parts(p)
        col = np.tile(np.array(POT_BODY, float), (len(p), 1))
        col[rim < 0.6] = POT_RIM
        col[(rad < self.RIM_R - 1.2) & (y > self.RIM_Y - 0.5)] = POT_INSIDE  # inner wall and floor
        col[(lugs < 0.6) | (feet < 0.6)] = POT_DARK
        return np.hstack([col / 255, np.ones((len(p), 1))])


# ---------- rendering ----------


def _march(model, orig, d, t_start, t_end, max_steps=220, eps=0.02):
    n = len(orig)
    hit = np.zeros(n, bool)
    t = t_start.copy()
    idx = np.flatnonzero(t_end > t_start)
    for _ in range(max_steps):
        if not len(idx):
            break
        s = model.sdf(orig[idx] + t[idx, None] * d)
        done = s < eps
        hit[idx[done]] = True
        t[idx] += np.where(done, 0, np.maximum(s * 0.8, eps * 0.5))
        idx = idx[~done & (t[idx] < t_end[idx])]
    return hit, t


def _box(model, orig, d):
    d = np.where(np.abs(d) < 1e-9, 1e-9, d)
    t0, t1 = (model.lo - orig) / d, (model.hi - orig) / d
    return np.maximum(np.minimum(t0, t1).max(1), 0), np.maximum(t0, t1).min(1)


def _soft_shadow(model, p, L, k=10.0, steps=64):
    res = np.ones(len(p))
    t = np.full(len(p), 0.4)
    for _ in range(steps):
        h = model.sdf(p + t[:, None] * L)
        res = np.minimum(res, np.clip(k * h / t, 0, 1))
        t += np.clip(h * 0.8, 0.08, 1.5)
    return res


def _ao(model, p, n):
    occ, w = np.zeros(len(p)), 1.0
    for i in range(1, 6):
        h = 0.6 * i
        occ += w * np.maximum(h - model.sdf(p + n * h), 0)
        w *= 0.6
    return np.clip(1 - 0.55 * occ, 0, 1)


def render(model, out_w, out_h, scale=4, ss=2, pitch=PITCH, pivot=(40.0, 78.0, 0.0), screen=(40.0, 78.0)):
    rot = rotation(YAW, pitch)
    pivot, screen = np.asarray(pivot, float), np.asarray(screen, float)
    res = scale * ss
    v, u = np.mgrid[0:out_h * res, 0:out_w * res]
    view = np.stack([(u.ravel() + 0.5) / res - screen[0], (v.ravel() + 0.5) / res - screen[1], np.full(u.size, 300.0)], 1)
    orig = view @ rot + pivot
    d = np.array([0.0, 0.0, -1.0]) @ rot
    t0, t1 = _box(model, orig, d)
    hit, t = _march(model, orig, d, t0, t1)

    rgba = np.zeros((u.size, 4))
    j = np.flatnonzero(hit)
    if len(j):
        p = orig[j] + t[j, None] * d
        n = model.normal(p)
        src = model.color(p, n)
        base = np.clip(src[:, :3], 0, 1) ** 2.2
        view_dir = -d
        key = np.clip((n @ KEY + 0.25) / 1.25, 0, 1)  # wrapped: soft terminator
        lit = np.flatnonzero(key > 0)
        shadow = np.ones(len(j))
        if len(lit):
            shadow[lit] = _soft_shadow(model, p[lit] + n[lit] * 0.3, KEY)
        ao = _ao(model, p, n)
        fill = np.clip(n @ FILL, 0, 1)
        sky = 0.5 + 0.5 * np.clip(-n[:, 1], 0, 1)
        half = (KEY + view_dir) / np.linalg.norm(KEY + view_dir)
        spec = np.clip(n @ half, 0, 1) ** 36 * 0.28 * shadow
        fresnel = (1 - np.clip(n @ view_dir, 0, 1)) ** 3
        light = (
            KEY_COLOR * (1.0 * key * (0.25 + 0.75 * shadow))[:, None]
            + FILL_COLOR * (0.28 * fill)[:, None]
            + (0.3 * sky * ao)[:, None]
        ) * (0.55 + 0.45 * ao)[:, None]
        col = base * light + spec[:, None] + 0.22 * fresnel[:, None] * FILL_COLOR * (0.4 + base)
        rgba[j, :3] = np.clip(col, 0, 1) ** (1 / 2.2)
        rgba[j, 3] = np.clip(src[:, 3], 0, 1)

    img = rgba.reshape(out_h * res, out_w * res, 4)
    if ss > 1:
        pre = img.copy()
        pre[..., :3] *= pre[..., 3:4]
        pre = pre.reshape(out_h * scale, ss, out_w * scale, ss, 4).mean((1, 3))
        a = pre[..., 3:4]
        pre[..., :3] = np.where(a > 0, pre[..., :3] / np.maximum(a, 1e-6), 0)
        img = pre
    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)


SPECK = 6  # parts this small (in pixels) are sparkles: too small to model, drawn as glowing points


def render_sprite(frame, scale=4, ss=2):
    h, w = frame.shape[:2]
    opaque = frame[..., 3] > 0
    if not opaque.any():
        return np.zeros((h * scale, w * scale, 4), np.uint8)
    labels, n = ndimage.label(opaque, structure=np.ones((3, 3)))
    sizes = np.bincount(labels.ravel(), minlength=n + 1)
    speck = (sizes[labels] <= SPECK) & opaque
    body = frame.copy()
    body[speck] = 0
    img = render(SpriteModel(body), w, h, scale, ss) if (body[..., 3] > 0).any() else np.zeros((h * scale, w * scale, 4), np.uint8)
    return _glow_specks(img, frame, speck, scale)


def _glow_specks(img, frame, speck, scale, pitch=PITCH, pivot=(40.0, 78.0, 0.0), screen=(40.0, 78.0)):
    """Draws sparkle pixels as small glowing points, placed by the same camera (at z = 0)."""
    ys, xs = np.nonzero(speck)
    if not len(ys):
        return img
    rot = rotation(YAW, pitch)
    world = np.stack([xs + 0.5, ys + 0.5, np.zeros(len(xs))], 1) - np.asarray(pivot)
    sc = world @ rot.T + [screen[0], screen[1], 0]
    out = img.astype(float) / 255
    H, W = out.shape[:2]
    yy, xx = np.mgrid[0:H, 0:W]
    glow = np.zeros((H, W, 3))
    alpha = np.zeros((H, W))
    for (sx, sy, _), (y, x) in zip(sc, zip(ys, xs)):
        cx, cy = sx * scale, sy * scale
        x0, x1, y0, y1 = int(max(cx - 12, 0)), int(min(cx + 12, W)), int(max(cy - 12, 0)), int(min(cy + 12, H))
        if x0 >= x1 or y0 >= y1:
            continue
        r2 = (xx[y0:y1, x0:x1] - cx) ** 2 + (yy[y0:y1, x0:x1] - cy) ** 2
        core = np.clip(1.6 - np.sqrt(r2) / 2.2, 0, 1)
        halo = np.exp(-r2 / 30.0) * 0.55
        a = np.clip(core + halo, 0, 1) * frame[y, x, 3] / 255
        c = frame[y, x, :3] / 255
        glow[y0:y1, x0:x1] = np.maximum(glow[y0:y1, x0:x1], (c * 0.7 + 0.3)[None, None, :] * a[..., None])
        alpha[y0:y1, x0:x1] = np.maximum(alpha[y0:y1, x0:x1], a)
    a0 = out[..., 3]
    a_new = alpha + a0 * (1 - alpha)
    rgb = (glow + out[..., :3] * a0[..., None] * (1 - alpha[..., None])) / np.maximum(a_new, 1e-6)[..., None]
    out = np.dstack([np.clip(rgb, 0, 1), a_new])
    return (out * 255 + 0.5).astype(np.uint8)


def render_cauldron(w=80, h=128, scale=4, ss=2):
    m = CauldronModel()
    return render(m, w, h, scale, ss, pitch=POT_PITCH, pivot=m.pivot, screen=POT_SCREEN)
