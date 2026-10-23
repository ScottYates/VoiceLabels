"""Label sizes, per-size print offsets, and the calibration (test) label.

Sizes come from config.LABEL_SIZES: a key like "3x1" -> (inches across the
print head, inches along the feed). The chosen size is applied by setting
config.LABEL_WIDTH_IN / LABEL_LENGTH_IN, which the renderer reads.

Offsets move everything on the label in printer terms: dx across the print
head (+ = right as the label comes out), dy along the feed (+ = further down
the label). They are kept in millimetres, per size, in the app's settings.
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

import config


def sizes() -> dict:
    return dict(getattr(config, "LABEL_SIZES", {"3x2": (config.LABEL_WIDTH_IN, config.LABEL_LENGTH_IN)}))


def default_key() -> str:
    s = sizes()
    k = getattr(config, "LABEL_SIZE", None)
    return k if k in s else next(iter(s))


def apply(key: str) -> None:
    """Make `key` the size the renderer and printer use."""
    w, l = sizes()[key]
    config.LABEL_WIDTH_IN, config.LABEL_LENGTH_IN = float(w), float(l)


def name(key: str) -> str:
    w, l = sizes()[key]
    return f"{w:g} × {l:g} in"


def mm_to_dots(mm: float) -> int:
    return round(mm / 25.4 * config.DPI)


def shift(img: Image.Image, dx_mm: float, dy_mm: float) -> Image.Image:
    """Move the printer-oriented image by the offsets; what goes past an edge
    is cut off, and the space left behind is blank."""
    dx, dy = mm_to_dots(dx_mm), mm_to_dots(dy_mm)
    if not dx and not dy:
        return img
    out = Image.new(img.mode, img.size, 255 if img.mode in ("L", "1") else "white")
    out.paste(img, (dx, dy))
    return out


def measure_command() -> bytes:
    """Zebra media calibration: the printer feeds a few labels and learns
    their length and the gap between them. Run it after changing rolls."""
    return b"~JC"


def _font(size: int, bold: bool = True):
    return ImageFont.truetype(config.FONT_BOLD if bold else config.FONT_REGULAR, size)


def test_label(key: str, dx_mm: float = 0.0, dy_mm: float = 0.0) -> Image.Image:
    """A calibration label for size `key`, as the printer sees it (width across
    the print head). A border 1 mm inside the edge shows whether the print sits
    straight on the label: it should be the same distance from every edge.
    Ruler ticks every 1/4" run along the top and left, with a cross in the middle."""
    w_in, l_in = sizes()[key]
    W, H = round(w_in * config.DPI), round(l_in * config.DPI)
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)
    inset = mm_to_dots(1.0)
    d.rectangle([inset, inset, W - 1 - inset, H - 1 - inset], outline=0, width=3)
    # second, dashed border 2 mm in: if the solid one is cut off, this one shows by how much
    in2 = mm_to_dots(2.0)
    for x in range(in2, W - in2, 12):
        d.line([(x, in2), (min(x + 6, W - in2), in2)], fill=0, width=1)
        d.line([(x, H - 1 - in2), (min(x + 6, W - in2), H - 1 - in2)], fill=0, width=1)
    for y in range(in2, H - in2, 12):
        d.line([(in2, y), (in2, min(y + 6, H - in2))], fill=0, width=1)
        d.line([(W - 1 - in2, y), (W - 1 - in2, min(y + 6, H - in2))], fill=0, width=1)
    # ruler ticks every 1/4 inch, longer every inch
    q = config.DPI / 4
    for i in range(1, int(W / q) + 1):
        x = round(i * q)
        if x >= W - inset:
            break
        n = 16 if i % 4 == 0 else 8
        d.line([(x, inset), (x, inset + n)], fill=0, width=2)
    for i in range(1, int(H / q) + 1):
        y = round(i * q)
        if y >= H - inset:
            break
        n = 16 if i % 4 == 0 else 8
        d.line([(inset, y), (inset + n, y)], fill=0, width=2)
    # centre marks: a notch at the middle of each edge (and a cross on tall labels)
    cx, cy = W // 2, H // 2
    for (x0, y0, x1, y1) in [(cx, inset, cx, inset + 22), (cx, H - 1 - inset - 22, cx, H - 1 - inset),
                             (inset, cy, inset + 22, cy), (W - 1 - inset - 22, cy, W - 1 - inset, cy)]:
        d.line([(x0, y0), (x1, y1)], fill=0, width=3)
    tall = H >= 300
    if tall:
        arm = min(W, H) // 10
        d.line([(cx - arm, cy), (cx + arm, cy)], fill=0, width=2)
        d.line([(cx, cy - arm), (cx, cy + arm)], fill=0, width=2)
    # captions, scaled to fit inside the dashed border
    room = W - 2 * in2 - 60
    def fit(text, size, bold):
        while size > 10:
            f = _font(size, bold)
            b = d.textbbox((0, 0), text, font=f)
            if b[2] - b[0] <= room:
                return f, b
            size -= 1
        f = _font(10, bold)
        return f, d.textbbox((0, 0), text, font=f)
    horiz = ("centered" if dx_mm == 0 else f"{abs(dx_mm):.1f} mm {'right' if dx_mm > 0 else 'left'}")
    vert = ("centered" if dy_mm == 0 else f"{abs(dy_mm):.1f} mm {'down' if dy_mm > 0 else 'up'}")
    moved = "position not adjusted" if dx_mm == 0 and dy_mm == 0 else f"moved: {horiz}, {vert}"
    big, tb = fit(name(key), max(18, min(56, H // 5)), True)
    small, sb = fit(moved, max(12, min(24, H // 9)), False)
    th, sh = tb[3] - tb[1], sb[3] - sb[1]
    if tall:
        top = cy + min(W, H) // 10 + 10
    else:
        top = cy - (th + 8 + sh) // 2
    d.text(((W - (tb[2] - tb[0])) / 2 - tb[0], top - tb[1]), name(key), font=big, fill=0)
    d.text(((W - (sb[2] - sb[0])) / 2 - sb[0], top + th + 8 - sb[1]), moved, font=small, fill=0)
    return shift(img, dx_mm, dy_mm).point(lambda p: 255 if p >= 128 else 0).convert(
        "1", dither=Image.Dither.NONE)
