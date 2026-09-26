"""Builds Assets/witch-sprites.png from Assets/wizard-sprites.png.

The witch reuses the wizard's frames (same 5x5 grid of 80x128 frames, same
bob, vanish and smoke timing), so she lines up with the cauldron exactly like
he does. Per frame, the wizard is split into regions by color and
connectivity (hat, face, beard, robe), and each region is redrawn:

- hat: black, stars removed, a wide brim, a purple band and a gold buckle
- face: no beard; the face and chin continue down to the wizard's mouth
- hair: long ginger hair from under the brim onto the shoulders
- robe: dark plum, stars removed; the beard's V becomes a neckline

Run from app/: python3 scripts/make_witch_sprites.py   (needs Pillow)
Re-run it whenever wizard-sprites.png changes; commit the PNG it writes.
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
INK = (24, 20, 37)  # eyes, open-mouth smile
MOUTH_DOT = (38, 43, 68)  # the idle mouth, drawn in a beard color
PURPLE = {ROBE, ROBE_SH, STAR, STAR_SH}

# Witch palette.
HAT, HAT_SH, HAT_HI = (58, 48, 82), (36, 30, 54), (100, 86, 130)
BAND, BUCKLE = (122, 54, 123), (254, 200, 65)
DRESS, DRESS_SH = (66, 45, 88), (45, 31, 62)
HAIR, HAIR_SH, HAIR_HI = (196, 74, 48), (140, 44, 44), (232, 116, 66)
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


def witch_frame(src):
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
    ink = {(x, y) for y in range(FH) for x in range(FW) if rgb(x, y) in (INK, MOUTH_DOT)}

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

    face_top = min(y for _, y in skin)
    # Nothing is drawn at or below the hem line (the vanish frames sink her into it).
    floor = min((y for y in range(FH) for x in range(FW) if rgb(x, y) in HEM), default=FH) - 1
    face_l = min(x for x, y in skin if y > face_top + 3)
    face_r = max(x for x, y in skin if y > face_top + 3 and rgb(x, y) == SKIN)
    cx = (face_l + face_r) // 2

    # Face and chin. The wizard's mouth sits low in his beard; move it up under the eyes, fill the
    # beard down to the chin with skin, and round the chin off.
    eyes = {p for p in ink if p[1] <= face_top + 8}
    mouth = {p for p in ink if p[1] > face_top + 8}
    eyes_bottom = max((y for _, y in eyes), default=face_top + 7)
    lift = (min(y for _, y in mouth) - (eyes_bottom + 4)) if mouth else 0
    mouth = {(x, y - lift) for x, y in mouth}
    chin = min((max(y for _, y in mouth) + 2) if mouth else eyes_bottom + 6, floor)
    rows = {}  # chin row -> (left, right)
    for y in range(face_top + 4, chin + 1):
        inset = (0, 0, 1, 3)[min(3, max(0, y - (chin - 3)))]
        rows[y] = (face_l + inset, face_r - inset)
        for x in range(face_l, face_r + 1):
            if (x, y) in beard or (x, y) in skin or (x, y) in ink:
                if rows[y][0] <= x <= rows[y][1]:
                    edge = y == chin or x in rows[y] and y >= chin - 1
                    put(x, y, SKIN_SH if edge or x >= face_r - 1 else SKIN)
                else:
                    put(x, y, DRESS)
    for p in mouth | eyes:
        put(*p, INK)

    # Below the chin the beard becomes the dress: a shaded V neckline with a small pendant.
    below = [(x, y) for x, y in beard if y > chin]
    for x, y in below:
        put(x, y, DRESS_SH if abs(x - cx) <= max(0, 7 - (y - chin) // 2) else DRESS)
    for p in beard:  # beard beside the face (sinking frames): dress
        if rgb(*p) in BEARD and o[p][:3] in BEARD:
            put(*p, DRESS)
    if below and chin + 6 <= floor:
        py = chin + 3
        for x, y in ((cx, py), (cx - 1, py + 1), (cx, py + 1), (cx + 1, py + 1), (cx, py + 2)):
            put(x, y, PENDANT)
        for x, y in ((cx - 1, py - 1), (cx + 1, py - 1)):
            put(x, y, BUCKLE)

    # Hair: two long locks from under the brim to the shoulders, and a short fringe.
    hair_bottom = min(chin + 8, floor)
    for side, x0 in (("l", face_l - 2), ("r", face_r - 1)):
        for y in range(face_top + 2, hair_bottom + 1):
            w = 4 if y < hair_bottom - 2 else 3
            for i in range(w):
                x = x0 + i if side == "l" else x0 + i
                if y == hair_bottom and i in (0, w - 1):
                    continue
                edge = i == 0 if side == "l" else i == w - 1
                inner = i == w - 1 if side == "l" else i == 0
                c = HAIR_SH if edge else HAIR_HI if (inner and (y + x) % 3 == 0) else HAIR
                put(x, y, c)
    for x in range(face_l, face_r + 1):
        if (x + face_top) % 4 != 0:
            put(x, face_top + 1, HAIR_SH)
        put(x, face_top, HAIR)

    # Brim: wide and flat, lit along the top, tapered at the ends.
    bl, br = face_l - 8, face_r + 9
    for x in range(bl, br + 1):
        if bl + 3 <= x <= br - 3:
            put(x, face_top - 3, HAT_HI)
        if bl + 1 <= x <= br - 1:
            put(x, face_top - 2, HAT)
        put(x, face_top - 1, HAT_SH if x in (bl, br) else HAT)
        if bl + 3 <= x <= br - 3:
            put(x, face_top, HAT_SH)
    # Band and buckle just above the brim, on the crown only.
    band = (face_top - 5, face_top - 4)
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
            out.paste(witch_frame(sheet.crop(box)), box[:2])
    out.save(ASSETS / "witch-sprites.png", optimize=True)
    print("wrote", ASSETS / "witch-sprites.png")


if __name__ == "__main__":
    main()
