"""Voxel renderer for the 3D look (used by make_3d_sprites.py).

Two kinds of model go through one ray tracer:

- Sprite models (characters, wand, poof): every opaque pixel becomes a column
  of cubes running front to back. Each row is a slice of a rounded solid: a
  run of pixels gets a circular depth profile (a robe row is a cylinder, a hat
  brim a disc, a hair lock a tube), rounded off near the top and bottom of
  the silhouette so heads and shoulders aren't flat.
- The cauldron is built in 3D (a round belly, a thick rim, a hollow inside,
  lugs and feet) in the pixel art's palette. Its 2D art is drawn looking
  steeply down into the opening, which a front-on voxelization can't
  reproduce, so it gets its own steeper camera that puts the rim where the
  pixel art has it.

Rendering: orthographic, turned 22 degrees, a sun from the top left with cast
shadows, per-corner ambient occlusion, a sky fill, a soft bevel on cube edges,
and 2x2 supersampling.
"""
import numpy as np
from scipy import ndimage

YAW = np.radians(22)
PITCH = np.radians(10)  # characters: nearly eye level
SUN = np.array([-0.5, -0.62, 0.62])  # from the top left, in front (y is down)
SUN /= np.linalg.norm(SUN)


def rotation(yaw, pitch):
    cy, sy, cp, sp = np.cos(yaw), np.sin(yaw), np.cos(pitch), np.sin(pitch)
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])  # front turns right: we see the left side
    rx = np.array([[1, 0, 0], [0, cp, sp], [0, -sp, cp]])  # tops come toward the camera
    return rx @ ry


class Grid:
    """Voxels in [0,w) x [0,h) x [z0, z0+d): occupancy and RGBA per cell."""

    def __init__(self, occ, rgba, z0):
        self.occ3, self.rgba3, self.z0 = occ, rgba, z0  # occ: [y, x, z]
        self.h, self.w, self.d = occ.shape
        self.lo = np.array([0, 0, z0])
        self.hi = np.array([self.w, self.h, z0 + self.d])

    def occ(self, x, y, z):
        zi = z - self.z0
        inside = (x >= 0) & (x < self.w) & (y >= 0) & (y < self.h) & (zi >= 0) & (zi < self.d)
        return inside & self.occ3[np.where(inside, y, 0), np.where(inside, x, 0), np.where(inside, zi, 0)]

    def color(self, x, y, z):
        return self.rgba3[y, x, z - self.z0]

    def trace(self, orig, d, max_steps=500):
        """Amanatides-Woo voxel walk for many rays sharing one direction.
        Returns (hit, cell, axis, t) per ray."""
        n = len(orig)
        d = np.where(np.abs(d) < 1e-9, 1e-9, d)
        inv = 1.0 / d
        t0, t1 = (self.lo - orig) * inv, (self.hi - orig) * inv
        tmin = np.minimum(t0, t1)
        t_enter, t_exit = tmin.max(1), np.maximum(t0, t1).min(1)
        hit = np.zeros(n, bool)
        cell = np.zeros((n, 3), np.int64)
        axis = np.zeros(n, np.int64)
        t_hit = np.zeros(n)
        idx = np.flatnonzero(t_exit > np.maximum(t_enter, 0))
        if not len(idx):
            return hit, cell, axis, t_hit
        t = np.maximum(t_enter[idx], 0) + 1e-6
        p = orig[idx] + t[:, None] * d
        c = np.clip(np.floor(p).astype(np.int64), self.lo, self.hi - 1)
        step = np.sign(d).astype(np.int64)
        tdelta = np.abs(inv)
        tnext = t[:, None] + ((c + (step > 0)) - p) * inv
        ax = np.argmax(tmin[idx], axis=1)  # entry face
        tcur = t
        for _ in range(max_steps):
            inside = np.all((c >= self.lo) & (c < self.hi), axis=1)
            occ = inside & self.occ(c[:, 0], c[:, 1], c[:, 2])
            if occ.any():
                j = idx[occ]
                hit[j], cell[j], axis[j], t_hit[j] = True, c[occ], ax[occ], tcur[occ]
            keep = inside & ~occ
            if not keep.any():
                break
            idx, c, tnext, tcur = idx[keep], c[keep], tnext[keep], tcur[keep]
            ax = np.argmin(tnext, axis=1)
            rows = np.arange(len(idx))
            tcur = tnext[rows, ax]
            c[rows, ax] += step[ax]
            tnext[rows, ax] += tdelta[ax]
        return hit, cell, axis, t_hit


# ---------- models ----------


def sprite_model(rgba):
    """Pixel art -> a rounded voxel solid (see the module docstring)."""
    opaque = rgba[..., 3] > 0
    h, w = opaque.shape
    half = np.zeros((h, w))
    for y in range(h):
        edges = np.flatnonzero(np.diff(np.r_[0, opaque[y].astype(np.int8), 0]))
        for a, b in zip(edges[::2], edges[1::2]):
            r, c = (b - a) / 2, (a + b - 1) / 2
            x = np.arange(a, b)
            half[y, a:b] = np.sqrt(np.maximum(r * r - (x - c) ** 2, 0.25))
    dist = ndimage.distance_transform_edt(opaque)
    half = np.minimum(half * 0.8, 1.3 * dist + 0.8)  # round off tops and bottoms
    smooth = ndimage.gaussian_filter(half * opaque, 0.9) / np.maximum(ndimage.gaussian_filter(opaque * 1.0, 0.9), 1e-6)
    k = np.where(opaque, np.maximum(1, np.round(smooth)), 0).astype(np.int32)
    kz = max(1, int(k.max()))
    z = np.arange(-kz, kz)
    occ = opaque[..., None] & (z[None, None, :] >= -k[..., None]) & (z[None, None, :] < k[..., None])
    colors = np.broadcast_to(rgba[:, :, None, :], occ.shape + (4,))
    return Grid(occ, colors, -kz)


# Cauldron palette (from pot-sheet.png): body, body highlight, rim, rim edge, inside.
POT_BODY, POT_RIM, POT_EDGE, POT_INSIDE = (57, 74, 80), (32, 46, 55), (22, 29, 40), (16, 21, 30)
POT_PITCH = np.radians(38)  # the pixel art looks this steeply into the opening
POT_CENTER = (40.0, 74.5)  # where the rim's center sits on the stage (x, y)


def cauldron_model(w=80, h=128):
    """A round cauldron: belly, thick rim, hollow inside, two lugs and three feet.
    World y is up-down in the cauldron's own frame; the rim's center is at
    (40, RIM_Y, 0) and the camera pivots there."""
    rim_y, rim_r, tube = 64, 35.5, 3.6
    zr = 42
    y, x, z = np.mgrid[0:h, 0:w, -zr:zr].astype(float)
    x, z = x + 0.5 - 40, z + 0.5
    rad = np.hypot(x, z)
    # Belly: an ellipsoid hanging below the rim, widest a little under it.
    belly_c, belly_ry, belly_r = rim_y + 18, 26.0, 39.0
    belly = (rad / belly_r) ** 2 + ((y - belly_c) / belly_ry) ** 2 <= 1
    belly &= y >= rim_y
    rim = (np.hypot(rad - rim_r, y - rim_y)) <= tube
    inner = (rad <= rim_r - 2.5) & (y >= rim_y - 1) & (y <= belly_c + 12)  # hollow inside
    lugs = np.zeros_like(belly)
    for sx in (-1, 1):  # small handles on each side, below the rim
        lugs |= np.hypot(np.hypot(x - sx * 38.5, z) - 3.2, y - (rim_y + 9)) <= 1.8
    feet = np.zeros_like(belly)
    for a in np.radians([90, 210, 330]):
        fx, fz = 16 * np.cos(a), 16 * np.sin(a)
        feet |= (np.hypot(x - fx, z - fz) <= 4.2) & (y >= belly_c + 20) & (y <= belly_c + 30)
    solid = ((belly & ~inner) | rim | lugs | feet)
    colors = np.zeros(solid.shape + (4,), np.uint8)
    colors[..., 3] = 255
    colors[...] = (*POT_BODY, 255)
    colors[rim] = (*POT_RIM, 255)
    colors[(rad < rim_r - 1.5) & (y >= rim_y - 1)] = (*POT_INSIDE, 255)  # inner wall and floor
    colors[lugs | feet] = (*POT_EDGE, 255)
    grid = Grid(solid.transpose(0, 1, 2), colors, -zr)
    grid.pivot = np.array([40.0, rim_y, 0.0])
    return grid


# ---------- rendering ----------


def _ao(grid, cell, normal, frac):
    """Per-corner ambient occlusion on the hit face, bilinear across it (1 = open)."""
    n = len(cell)
    a = np.argmax(np.abs(normal), axis=1)
    b, c = (a + 1) % 3, (a + 2) % 3
    rows = np.arange(n)
    q = cell + normal.astype(np.int64)
    eb = np.zeros((n, 3), np.int64)
    ec = np.zeros((n, 3), np.int64)
    eb[rows, b] = 1
    ec[rows, c] = 1
    o = lambda v: grid.occ(v[:, 0], v[:, 1], v[:, 2]).astype(float)
    corner = {}
    for sb in (-1, 1):
        for sc in (-1, 1):
            s1, s2, cc = o(q + sb * eb), o(q + sc * ec), o(q + sb * eb + sc * ec)
            corner[(sb, sc)] = np.where((s1 > 0) & (s2 > 0), 0.0, 3.0 - (s1 + s2 + cc)) / 3.0
    fb, fc = frac[rows, b], frac[rows, c]
    top = corner[(-1, -1)] * (1 - fb) + corner[(1, -1)] * fb
    bot = corner[(-1, 1)] * (1 - fb) + corner[(1, 1)] * fb
    return top * (1 - fc) + bot * fc, fb, fc


def render(grid, out_w, out_h, scale=4, ss=2, pitch=PITCH, pivot=None, screen_pivot=None):
    """Ray traces the grid into an (out_h*scale)x(out_w*scale) RGBA image.
    `pivot` (world) lands on `screen_pivot` (stage px); both default to (40, 78)."""
    rot = rotation(YAW, pitch)
    pivot = np.array([40.0, 78.0, 0.0]) if pivot is None else pivot
    sp = np.array([40.0, 78.0]) if screen_pivot is None else np.asarray(screen_pivot)
    res = scale * ss
    v, u = np.mgrid[0:out_h * res, 0:out_w * res]
    view = np.stack([(u.ravel() + 0.5) / res - sp[0], (v.ravel() + 0.5) / res - sp[1], np.full(u.size, 300.0)], 1)
    orig = view @ rot + pivot  # view -> world (rot is orthonormal)
    d = np.array([0.0, 0.0, -1.0]) @ rot
    hit, cell, axis, t = grid.trace(orig, d)

    rgba = np.zeros((u.size, 4))
    j = np.flatnonzero(hit)
    if len(j):
        c, ax = cell[j], axis[j]
        normal = np.zeros((len(j), 3))
        normal[np.arange(len(j)), ax] = -np.sign(d[ax])
        p = orig[j] + t[j, None] * d
        frac = p - np.floor(p)
        src = grid.color(c[:, 0], c[:, 1], c[:, 2]).astype(float) / 255
        base = src[:, :3] ** 2.2  # to linear light

        lam = np.clip(normal @ SUN, 0, 1)
        shadow = np.ones(len(j))
        lit = np.flatnonzero(lam > 0)
        if len(lit):
            blocked, *_ = grid.trace(p[lit] + normal[lit] * 1e-3, SUN, max_steps=300)
            shadow[lit] = np.where(blocked, 0.0, 1.0)
        shadow = 0.3 + 0.7 * shadow  # shade from the sun, not black
        ao, fb, fc = _ao(grid, c, normal, frac)
        sky = 0.5 + 0.5 * np.clip(-normal[:, 1], 0, 1)  # tops catch more sky
        edge = np.minimum(np.minimum(fb, 1 - fb), np.minimum(fc, 1 - fc))
        bevel = 0.86 + 0.14 * np.clip(edge / 0.12, 0, 1)
        light = (0.62 * sky * (0.45 + 0.55 * ao) + 0.8 * lam * shadow) * bevel
        rgba[j, :3] = np.clip(base * light[:, None], 0, 1) ** (1 / 2.2)
        rgba[j, 3] = src[:, 3]

    img = rgba.reshape(out_h * res, out_w * res, 4)
    if ss > 1:  # average premultiplied subpixels
        pre = img.copy()
        pre[..., :3] *= pre[..., 3:4]
        pre = pre.reshape(out_h * scale, ss, out_w * scale, ss, 4).mean((1, 3))
        a = pre[..., 3:4]
        pre[..., :3] = np.where(a > 0, pre[..., :3] / np.maximum(a, 1e-6), 0)
        img = pre
    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)


def render_sprite(frame, scale=4, ss=2):
    h, w = frame.shape[:2]
    if not (frame[..., 3] > 0).any():
        return np.zeros((h * scale, w * scale, 4), np.uint8)
    return render(sprite_model(frame), w, h, scale, ss)


def render_cauldron(w=80, h=128, scale=4, ss=2):
    grid = cauldron_model(w, h)
    return render(grid, w, h, scale, ss, pitch=POT_PITCH, pivot=grid.pivot, screen_pivot=POT_CENTER)
