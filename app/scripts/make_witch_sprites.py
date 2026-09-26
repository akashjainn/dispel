"""Builds Assets/witch-sprites.png from Assets/wizard-sprites.png.

The witch reuses the wizard's frames (same 5x5 grid of 80x128 frames, same
bob, vanish and smoke timing), so she lines up with the cauldron exactly like
he does. Per frame, the wizard is split into regions by color and
connectivity (hat, face, beard, robe), and each region is redrawn:

- hat: black, stars removed, a wide brim, a purple band and a gold buckle
- face: redrawn (eyes with lashes, brows, blush, lips; a tapered chin and neck),
  one expression per sheet row
- hair: side-swept bangs and long ginger hair past the shoulders
- robe: dark plum, stars removed; the beard's V becomes a neckline

Run from app/: python3 scripts/make_witch_sprites.py   (needs Pillow)
Re-run it whenever wizard-sprites.png changes, then scripts/make_3d_sprites.py
for the 3D look; commit the PNGs they write.
"""
from collections import deque
from pathlib import Path

from PIL import Image

ASSETS = Path(__file__).resolve().parents[1] / "Assets"
FW, FH, COLS, ROWS = 80, 128, 5, 5

# Wizard palette (RGB).
ROBE, ROBE_SH = (104, 56, 108), (81, 43, 82)
STAR, STAR_SH = (254, 231, 97), (254, 174, 52)
BEARD = {(139, 155, 180), (192, 203, 220), (90, 105, 136), (38, 43, 68)}
SKIN, SKIN_SH = (184, 111, 80), (115, 62, 57)
HEM = {(37, 86, 46), (38, 92, 66)}  # the stew shadow under the robe
INK = (24, 20, 37)
PURPLE = {ROBE, ROBE_SH, STAR, STAR_SH}

# Witch palette.
HAT, HAT_SH, HAT_HI = (58, 48, 82), (36, 30, 54), (100, 86, 130)
BAND, BUCKLE = (122, 54, 123), (254, 200, 65)
DRESS, DRESS_SH = (66, 45, 88), (45, 31, 62)
HAIR, HAIR_SH, HAIR_HI = (196, 74, 48), (140, 44, 44), (232, 116, 66)
LIP, LIP_SH, MOUTH_IN = (214, 76, 92), (160, 44, 70), (96, 24, 44)
BLUSH, EYE_HI = (222, 126, 112), (250, 240, 228)
# Face per sheet row: idle, smiling, focused, and eyes shut while sinking / as smoke.
EXPRESSIONS = ["open", "happy", "closed", "closed", "closed"]
PENDANT = (223, 132, 165)  # not green: the app turns green pixels into the pot (noStewShadow)
OUTLINE = (24, 20, 37)


def components(px, keep):
    """8-connected components of pixels where keep(x, y). Returns a list of sets."""
    seen, out = set(), []
    for y in range(FH):
        for x in range(FW):
            if (x, y) in seen or not keep(x, y):
                continue
            comp, q = set(), deque([(x, y)])
            seen.add((x, y))
            while q:
                cx, cy = q.popleft()
                comp.add((cx, cy))
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        n = (cx + dx, cy + dy)
                        if 0 <= n[0] < FW and 0 <= n[1] < FH and n not in seen and keep(*n):
                            seen.add(n)
                            q.append(n)
            out.append(comp)
    return out


def witch_frame(src, expression):
    px = src.load()
    rgb = lambda x, y: px[x, y][:3] if px[x, y][3] else None
    out = src.copy()
    o = out.load()
    put = lambda x, y, c: o.__setitem__((x, y), (*c, 255))

    skin = {(x, y) for y in range(FH) for x in range(FW) if rgb(x, y) in (SKIN, SKIN_SH)}
    beard_parts = components(px, lambda x, y: rgb(x, y) in BEARD)
    # Beard = beard-colored parts touching the face; the rest is vanish smoke, kept as is.
    near_skin = lambda comp: any((x + dx, y + dy) in skin for x, y in comp for dx in (-1, 0, 1) for dy in (-1, 0, 1))
    beard = set().union(*[c for c in beard_parts if near_skin(c)]) if skin else set()

    # Hat vs robe: purple parts, split by connectivity. The hat is the part with the topmost pixel.
    purple = components(px, lambda x, y: rgb(x, y) in PURPLE)
    purple.sort(key=lambda c: min(y for _, y in c))
    hat = purple[0] if purple and skin and min(y for _, y in purple[0]) < min(y for _, y in skin) else set()
    if not skin and purple:  # smoke-only frames: whatever purple is left is the hat
        hat = purple[0]
    robe = set().union(*[c for c in purple if c is not hat]) if purple else set()

    def fill_from_neighbors(region, base, shade):
        """Stars -> the surrounding base/shade color, by majority vote, repeated until covered."""
        todo = {p for p in region if rgb(*p) in (STAR, STAR_SH)}
        colors = {p: (base if rgb(*p) in (ROBE, STAR, STAR_SH) else shade) for p in region}
        for p in todo:
            colors[p] = None
        for _ in range(12):
            left = set()
            for x, y in todo:
                votes = {}
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        c = colors.get((x + dx, y + dy))
                        if c:
                            votes[c] = votes.get(c, 0) + 1
                if votes:
                    colors[(x, y)] = max(votes, key=votes.get)
                else:
                    left.add((x, y))
            todo = left
            if not todo:
                break
        for p, c in colors.items():
            put(*p, c or base)

    def recolor(region, base, shade):
        m = {ROBE: base, ROBE_SH: shade}
        for p in region:
            c = rgb(*p)
            if c in m:
                put(*p, m[c])

    recolor(robe, DRESS, DRESS_SH)
    fill_from_neighbors(robe, DRESS, DRESS_SH)
    recolor(hat, HAT, HAT_SH)
    fill_from_neighbors(hat, HAT, HAT_SH)

    if not skin:
        return out

    ft = min(y for _, y in skin)  # face top, hidden under the brim
    # Nothing is drawn at or below the hem line (the vanish frames sink her into it).
    floor = min((y for y in range(FH) for x in range(FW) if rgb(x, y) in HEM), default=FH) - 1
    fl = min(x for x, y in skin if y > ft + 3)
    fr = max(x for x, y in skin if y > ft + 3 and rgb(x, y) == SKIN)
    face = lambda x, y, c: y <= floor and put(x, y, c)
    cx = fl + 10  # between the eyes (mouth columns are cx - 1, cx)
    chin = ft + 14

    # Face: the wizard's eyes, brows and beard are all replaced. Hair covers the
    # outer two columns on each side; the jaw tapers to a narrow chin.
    taper = {chin - 3: 1, chin - 2: 2, chin - 1: 3, chin: 5}
    for y in range(ft + 1, chin + 1):
        lo, hi = fl + 2 + taper.get(y, 0), fr - 2 - taper.get(y, 0)
        for x in range(fl, fr + 1):
            if lo <= x <= hi:
                face(x, y, SKIN_SH if y == chin or x == hi else SKIN)
            else:
                face(x, y, HAIR_SH)  # hair behind her head
    for y in (chin + 1, chin + 2):  # neck, in the chin's shadow
        for x in range(cx - 2, cx + 2):
            face(x, y, SKIN_SH)
    face(cx, ft + 9, SKIN_SH)  # nose
    for x in (fl + 3, fl + 4, fl + 15, fl + 16):  # blush
        face(x, ft + 9, BLUSH)

    le, re = fl + 5, fl + 13  # inner-left column of each eye
    for x in (le - 1, le, le + 1, re, re + 1, re + 2):  # thin brows
        face(x, ft + 5, HAIR_SH)
    if expression == "open":
        for x0, out_x in ((le, le - 1), (re, re + 2)):  # out_x: the eye's outer corner
            for x in sorted({x0, x0 + 1, out_x}):
                face(x, ft + 6, INK)  # upper lid
            face(out_x + (out_x - x0 > 0 or -1), ft + 5, INK)  # lash flick
            for x in (x0, x0 + 1):
                face(x, ft + 7, INK)
                face(x, ft + 8, INK)
            face(x0 + 1, ft + 7, EYE_HI)
    else:  # "happy": ^ arcs; "closed": u arcs with lashes
        arc = (ft + 8, ft + 7, ft + 7, ft + 8) if expression == "happy" else (ft + 7, ft + 8, ft + 8, ft + 7)
        for x0 in (le - 1, re):
            for i, y in enumerate(arc):
                face(x0 + i, y, INK)
        if expression == "closed":
            face(le - 2, ft + 8, INK)
            face(re + 4, ft + 8, INK)

    if expression == "happy":  # open smile
        face(cx - 3, ft + 11, LIP_SH)
        face(cx + 2, ft + 11, LIP_SH)
        for x in range(cx - 2, cx + 2):
            face(x, ft + 12, MOUTH_IN)
        for x in (cx - 1, cx):
            face(x, ft + 13, LIP)
    else:
        for x in (cx - 1, cx):
            face(x, ft + 11, LIP_SH)
            face(x, ft + 12, LIP)

    # Below the chin the beard becomes the dress: a shaded V neckline with a small pendant.
    for x, y in beard:
        if y > chin + (2 if cx - 2 <= x < cx + 2 else 0) or not (fl <= x <= fr):
            put(x, y, DRESS_SH if abs(x - cx) <= max(0, 6 - (y - chin) // 2) else DRESS)
    if chin + 8 <= floor:
        py = chin + 4
        for x, y in ((cx, py), (cx - 1, py + 1), (cx, py + 1), (cx + 1, py + 1), (cx, py + 2)):
            put(x, y, PENDANT)
        for x, y in ((cx - 2, py - 1), (cx + 2, py - 1), (cx - 1, py - 1), (cx + 1, py - 1)):
            put(x, y, BUCKLE)

    # Hair: side-swept bangs, and long locks past the shoulders.
    for y, (a, b) in ((ft + 1, (fl, fr)), (ft + 2, (fl, fr - 4)), (ft + 3, (fl, fl + 8)), (ft + 4, (fl, fl + 3))):
        for x in range(a, b + 1):
            face(x, y, HAIR_HI if (x - y) % 5 == 0 else HAIR)
        face(b, y, HAIR_SH)
    hair_bottom = min(ft + 25, floor)
    for side in (-1, 1):
        inner = fl + 1 if side < 0 else fr - 1  # the lock's edge on the face
        for y in range(ft + 1, hair_bottom + 1):
            flare = 1 if y >= ft + 16 else 0  # fans out over the shoulders
            width = 5 + flare - (1 if y >= hair_bottom - 1 else 0)
            for i in range(width):
                x = inner - i if side < 0 else inner + i
                if y == hair_bottom and i in (0, width - 1):
                    continue  # rounded ends
                if i == 0 and y < chin:
                    c = HAIR_SH  # shadow where hair meets the face
                elif i == width - 1:
                    c = HAIR_SH
                elif i == 2 and (y - ft) % 7 < 4 or i == 1 and (y - ft) % 7 == 5:
                    c = HAIR_HI  # soft strands running down the lock
                else:
                    c = HAIR
                face(x, y, c)

    for p in beard:  # anything of the beard still showing (at the hem while sinking): dress shadow
        if o[p][:3] in BEARD:
            put(*p, DRESS_SH)

    # Brim: wide and flat, lit along the top, tapered at the ends.
    bl, br = fl - 8, fr + 9
    for x in range(bl, br + 1):
        if bl + 3 <= x <= br - 3:
            put(x, ft - 3, HAT_HI)
        if bl + 1 <= x <= br - 1:
            put(x, ft - 2, HAT)
        put(x, ft - 1, HAT_SH if x in (bl, br) else HAT)
        if bl + 3 <= x <= br - 3:
            put(x, ft, HAT_SH)
    # Band and buckle just above the brim, on the crown only.
    band = (ft - 5, ft - 4)
    crown = [x for x in range(FW) if any((x, y) in hat for y in band)]
    if crown:
        for x in crown:
            for y in band:
                if (x, y) in hat:
                    put(x, y, BAND)
        bx = (min(crown) + max(crown)) // 2
        for x in range(bx - 2, bx + 2):
            for y in band:
                put(x, y, BUCKLE if x in (bx - 2, bx + 1) or y == band[0] else HAT_SH)
    return out


def main():
    sheet = Image.open(ASSETS / "wizard-sprites.png").convert("RGBA")
    out = Image.new("RGBA", sheet.size)
    for r in range(ROWS):
        for c in range(COLS):
            box = (c * FW, r * FH, (c + 1) * FW, (r + 1) * FH)
            out.paste(witch_frame(sheet.crop(box), EXPRESSIONS[r]), box[:2])
    out.save(ASSETS / "witch-sprites.png", optimize=True)
    print("wrote", ASSETS / "witch-sprites.png")


if __name__ == "__main__":
    main()
