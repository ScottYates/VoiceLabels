"""Line icons for the buttons, drawn with Pillow (no icon font needed).

    icon_image("mic", 32, "#f2f3f5")  ->  PIL RGBA image, 32 x 32

Each icon is drawn on a 24-unit grid at 4x size, then scaled down so the
edges are smooth. Stroke style is consistent across the set (rounded, about
2 units wide), similar to common UI icon sets.
"""

from __future__ import annotations

import math

from PIL import Image, ImageDraw

SS = 4          # supersampling factor
GRID = 24.0     # design grid


def _canvas(size):
    px = size * SS
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img), px / GRID


def _line(d, k, pts, color, w):
    pts = [(x * k, y * k) for x, y in pts]
    d.line(pts, fill=color, width=int(w * k), joint="curve")
    r = w * k / 2
    for x, y in (pts[0], pts[-1]):                    # round caps
        d.ellipse((x - r, y - r, x + r, y + r), fill=color)


def _rrect(d, k, x0, y0, x1, y1, r, color, w, fill=None):
    h = w / 2                        # centre the stroke on the given outline
    d.rounded_rectangle(((x0 - h) * k, (y0 - h) * k, (x1 + h) * k, (y1 + h) * k),
                        radius=(r + h) * k, outline=color, width=int(w * k), fill=fill)


def _arc(d, k, cx, cy, r, start, end, color, w):
    R = r + w / 2                    # Pillow draws the stroke inside the box: centre it on r
    d.arc(((cx - R) * k, (cy - R) * k, (cx + R) * k, (cy + R) * k), start, end,
          fill=color, width=int(w * k))
    rr = w * k / 2
    for a in (start, end):                             # round caps
        x, y = (cx + r * math.cos(math.radians(a))) * k, (cy + r * math.sin(math.radians(a))) * k
        d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=color)


def _circle(d, k, cx, cy, r, color, w):
    R = r + w / 2
    d.ellipse(((cx - R) * k, (cy - R) * k, (cx + R) * k, (cy + R) * k),
              outline=color, width=int(w * k))


def _arrowhead(d, k, x, y, ang, color, w, size=4.2):
    """Chevron with its tip at (x, y), pointing along angle `ang` (radians, screen coords)."""
    pts = []
    for side in (-1, 1):
        a = ang + math.pi + side * math.radians(40)
        pts.append((x + size * math.cos(a), y + size * math.sin(a)))
    _line(d, k, [pts[0], (x, y), pts[1]], color, w)


def _dot(d, k, x, y, r, color):
    d.ellipse(((x - r) * k, (y - r) * k, (x + r) * k, (y + r) * k), fill=color)


def icon_image(name: str, size: int, color: str, w: float = 2.2) -> Image.Image:
    img, d, k = _canvas(size)
    c = color
    if name == "mic":
        _rrect(d, k, 9, 2.5, 15, 14.5, 3, c, w)
        _arc(d, k, 12, 10.5, 6.5, 0, 180, c, w)
        _line(d, k, [(12, 17), (12, 21)], c, w)
        _line(d, k, [(8.5, 21.2), (15.5, 21.2)], c, w)
    elif name == "printer":
        _line(d, k, [(6.5, 8.5), (6.5, 3), (17.5, 3), (17.5, 8.5)], c, w)
        _rrect(d, k, 2.5, 8.5, 21.5, 17, 2.5, c, w)
        _rrect(d, k, 6.5, 13.5, 17.5, 21.5, 0.8, c, w, fill=None)
        _dot(d, k, 18, 11.5, 1.1, c)
    elif name == "rotate":
        cx, cy, r, end = 12, 12.5, 8, 290           # clockwise from 3 o'clock round to 1 o'clock
        _arc(d, k, cx, cy, r, 10, end, c, w)
        t = math.radians(end)
        tx, ty = -math.sin(t), math.cos(t)           # direction of travel at the end
        ex, ey = cx + r * math.cos(t) + 1.2 * tx, cy + r * math.sin(t) + 1.2 * ty
        _arrowhead(d, k, ex, ey, math.atan2(ty, tx), c, w, size=4.6)
    elif name == "clear":
        _circle(d, k, 12, 12, 9.5, c, w)
        _line(d, k, [(8.5, 8.5), (15.5, 15.5)], c, w)
        _line(d, k, [(15.5, 8.5), (8.5, 15.5)], c, w)
    elif name == "gear":                             # solid gear with a round hole
        cx = cy = 12
        pts = []
        for i in range(8):
            a = math.radians(i * 45)
            for da, rr in ((-0.30, 7.6), (-0.17, 10.3), (0.17, 10.3), (0.30, 7.6)):
                pts.append(((cx + rr * math.cos(a + da)) * k, (cy + rr * math.sin(a + da)) * k))
        d.polygon(pts, fill=c)
        d.ellipse(((cx - 7.8) * k, (cy - 7.8) * k, (cx + 7.8) * k, (cy + 7.8) * k), fill=c)
        d.ellipse(((cx - 3.4) * k, (cy - 3.4) * k, (cx + 3.4) * k, (cy + 3.4) * k), fill=(0, 0, 0, 0))
    elif name == "power":
        _arc(d, k, 12, 13, 8, -55, 235, c, w)
        _line(d, k, [(12, 2.5), (12, 11)], c, w)
    elif name == "check":
        _line(d, k, [(4.5, 12.5), (9.5, 17.5), (19.5, 6.5)], c, w + 0.4)
    elif name == "back":
        _line(d, k, [(20, 12), (4.5, 12)], c, w)
        _line(d, k, [(10.5, 6), (4.5, 12), (10.5, 18)], c, w)
    elif name == "calendar":
        _rrect(d, k, 3, 5, 21, 21, 2.5, c, w)
        _line(d, k, [(3.5, 10), (20.5, 10)], c, w)
        _line(d, k, [(8, 2.5), (8, 7)], c, w)
        _line(d, k, [(16, 2.5), (16, 7)], c, w)
        for x in (8, 12, 16):
            for y in (14, 17.5):
                _dot(d, k, x, y, 1.0, c)
    elif name == "qr":
        for x0, y0 in ((3, 3), (14, 3), (3, 14)):
            _rrect(d, k, x0, y0, x0 + 7, y0 + 7, 1.2, c, w * 0.9)
            _dot(d, k, x0 + 3.5, y0 + 3.5, 1.2, c)
        for x, y in ((15, 15), (19.5, 15), (15, 19.5), (19.5, 19.5), (17.25, 17.25)):
            _dot(d, k, x, y, 1.3, c)
    elif name == "sun":
        _circle(d, k, 12, 12, 4, c, w)
        for i in range(8):
            a = math.radians(i * 45)
            _line(d, k, [(12 + 7 * math.cos(a), 12 + 7 * math.sin(a)),
                         (12 + 9.5 * math.cos(a), 12 + 9.5 * math.sin(a))], c, w)
    elif name == "timer":
        _circle(d, k, 12, 13.5, 8, c, w)
        _line(d, k, [(12, 13.5), (12, 9)], c, w)
        _line(d, k, [(9.5, 2.5), (14.5, 2.5)], c, w)
    elif name == "copies":
        _rrect(d, k, 8, 3, 20, 17, 1.8, c, w)
        _line(d, k, [(4.5, 7.5), (4.5, 21), (15.5, 21)], c, w)
    elif name == "monitor":
        _rrect(d, k, 2.5, 3.5, 21.5, 16, 1.8, c, w)
        _line(d, k, [(12, 16.5), (12, 20)], c, w)
        _line(d, k, [(7.5, 20.8), (16.5, 20.8)], c, w)
    elif name == "search":
        _circle(d, k, 10.5, 10.5, 6.5, c, w)
        _line(d, k, [(15.4, 15.4), (20.5, 20.5)], c, w + 0.4)
    elif name == "bookmark":
        _line(d, k, [(6, 21), (6, 4.5), (7.5, 3), (16.5, 3), (18, 4.5), (18, 21), (12, 16.5), (6, 21)], c, w)
    elif name == "image":
        _rrect(d, k, 3, 4, 21, 20, 2.2, c, w)
        _line(d, k, [(4, 17.5), (9.5, 11.5), (13.5, 15.5), (16, 13), (20, 17)], c, w)
        _dot(d, k, 15.5, 8.5, 1.8, c)
    elif name == "trash":
        _line(d, k, [(3.5, 6.5), (20.5, 6.5)], c, w)
        _line(d, k, [(9, 6), (9.5, 3), (14.5, 3), (15, 6)], c, w)
        _line(d, k, [(5.5, 6.5), (6.8, 20), (8, 21), (16, 21), (17.2, 20), (18.5, 6.5)], c, w)
        _line(d, k, [(10, 10.5), (10, 17)], c, w)
        _line(d, k, [(14, 10.5), (14, 17)], c, w)
    elif name in ("arrow-left", "arrow-right", "arrow-up", "arrow-down"):
        ang = {"arrow-right": 0, "arrow-down": 90, "arrow-left": 180, "arrow-up": 270}[name]
        a = math.radians(ang)
        ca, sa = math.cos(a), math.sin(a)
        rot = lambda x, y: (12 + (x - 12) * ca - (y - 12) * sa, 12 + (x - 12) * sa + (y - 12) * ca)  # noqa: E731
        _line(d, k, [rot(4, 12), rot(19.5, 12)], c, w)
        _line(d, k, [rot(13.5, 6), rot(19.5, 12), rot(13.5, 18)], c, w)
    elif name in ("align-left", "align-center", "align-right"):
        for y, half in ((5, 8.5), (9.7, 5.5), (14.3, 8.5), (19, 5.5)):
            if name == "align-left":
                x0, x1 = 3.5, 3.5 + 2 * half
            elif name == "align-right":
                x0, x1 = 20.5 - 2 * half, 20.5
            else:
                x0, x1 = 12 - half, 12 + half
            _line(d, k, [(x0, y), (x1, y)], c, w)
    else:
        raise ValueError(f"no icon named {name!r}")
    return img.resize((size, size), Image.LANCZOS)


NAMES = ["mic", "printer", "rotate", "clear", "gear", "power", "check", "back", "monitor",
         "calendar", "qr", "sun", "timer", "copies", "align-left", "align-center", "align-right",
         "search", "bookmark", "image", "trash", "arrow-left", "arrow-up", "arrow-right", "arrow-down"]


if __name__ == "__main__":       # contact sheet for checking the set
    import sys
    cell = 96
    sheet = Image.new("RGBA", (cell * len(NAMES), cell * 2), "#2b2d31")
    for i, n in enumerate(NAMES):
        sheet.alpha_composite(icon_image(n, 64, "#f2f3f5"), (i * cell + 16, 16))
        sheet.alpha_composite(icon_image(n, 32, "#f2f3f5"), (i * cell + 32, cell + 32))
    sheet.save(sys.argv[1] if len(sys.argv) > 1 else "icons.png")
