"""Voice Labels logo as a 3D-printable plaque (python3 make_logo.py).

A dark base plate with the logo raised on top: the speech bubble (with the
sound wave and the text lines cut through it, so the plate shows), "Voice",
"Labels" and the tagline. Written to ./stl:

  logo_plaque.stl       everything as one piece (print in one colour, or swap
                        filament at the top of the base: RAISE_Z)
  logo_1_base_dark.stl  \\
  logo_2_yellow.stl      |  the same plaque split by colour, all in the same
  logo_3_white.stl       |  place: load them together as one multi-part
  logo_4_gray.stl       /   object and give each part its own filament

Laid out from assets/logo.svg (760 x 240 units).
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont
from manifold3d import CrossSection, FillRule, JoinType, Manifold

MM = 0.25                 # mm per logo unit: the plaque is 190 x 60 mm
BASE_T = 3.0              # base plate thickness
RAISE = 1.0               # height of the raised logo
RAISE_Z = BASE_T          # where the raised parts start (filament swap height)
FONT_DIR = Path("/usr/share/fonts/opentype/inter")
TITLE_FONT = FONT_DIR / "InterDisplay-ExtraBold.otf"
TAG_FONT = FONT_DIR / "InterDisplay-SemiBold.otf"
SEG = 48
OUT = Path(__file__).with_name("stl")


# ------------------------------------------------------------------ 2D helpers
def P(x, y):
    """Logo units (SVG: y down) to mm (y up)."""
    return (x * MM, (240 - y) * MM)


def rrect(x, y, w, h, r):
    core = CrossSection.square([w - 2 * r, h - 2 * r]).translate([x + r, y + r])
    return core.offset(r, JoinType.Round, circular_segments=SEG)


def capsule(a, b, width):
    """A stroked line with round caps, from a to b (mm)."""
    c1 = CrossSection.circle(width / 2, SEG).translate(list(a))
    c2 = CrossSection.circle(width / 2, SEG).translate(list(b))
    return CrossSection.batch_hull([c1, c2])


class FlatPen(BasePen):
    """Collects glyph outlines as flattened polygons."""
    def __init__(self, glyphset, steps=12):
        super().__init__(glyphset)
        self.contours, self.cur, self.steps = [], [], steps

    def _moveTo(self, p):
        self.cur = [p]

    def _lineTo(self, p):
        self.cur.append(p)

    def _curveToOne(self, p1, p2, p3):
        p0 = self.cur[-1]
        for i in range(1, self.steps + 1):
            t = i / self.steps
            mt = 1 - t
            self.cur.append((mt ** 3 * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t ** 3 * p3[0],
                             mt ** 3 * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t ** 3 * p3[1]))

    def _qCurveToOne(self, p1, p2):
        p0 = self.cur[-1]
        for i in range(1, self.steps + 1):
            t = i / self.steps
            mt = 1 - t
            self.cur.append((mt * mt * p0[0] + 2 * mt * t * p1[0] + t * t * p2[0],
                             mt * mt * p0[1] + 2 * mt * t * p1[1] + t * t * p2[1]))

    def _closePath(self):
        if len(self.cur) >= 3:
            self.contours.append(self.cur)
        self.cur = []

    _endPath = _closePath


def text(s, font_path, size, x, baseline, spacing=0.0):
    """Text outline (mm) as the SVG would place it: left at x, on `baseline`,
    font `size` in logo units, with SVG letter-spacing `spacing`."""
    font = TTFont(str(font_path))
    gs, cmap, hmtx = font.getGlyphSet(), font.getBestCmap(), font["hmtx"]
    upm = font["head"].unitsPerEm
    k = size / upm
    polys, pen_x = [], x
    for ch in s:
        gname = cmap.get(ord(ch))
        if gname is None:
            pen_x += size * 0.3
            continue
        pen = FlatPen(gs)
        gs[gname].draw(pen)
        for c in pen.contours:
            polys.append([P(pen_x + gx * k, baseline - gy * k) for gx, gy in c])
        pen_x += hmtx[gname][0] * k + spacing
    return CrossSection(polys, FillRule.NonZero)


# ------------------------------------------------------------------ the logo
def mark():
    """Speech bubble with the sound wave and text lines cut through it."""
    def m(x, y):                                    # mark group: translate(48 34) scale(0.8)
        return P(48 + 0.8 * x, 34 + 0.8 * y)
    def sc(v):
        return v * 0.8 * MM
    (bx0, by1), (bx1, by0) = m(0, 0), m(240, 160)
    bubble = rrect(bx0, by0, bx1 - bx0, by1 - by0, sc(38))
    tail = CrossSection([[m(92, 150), m(92, 160), m(46, 200), m(56, 160), m(56, 150)]], FillRule.NonZero)
    bubble = bubble + tail
    w = sc(12)
    holes = [capsule(m(x, y0), m(x, y1), w) for x, y0, y1 in
             ((40, 68, 92), (62, 50, 110), (84, 34, 126), (106, 54, 106))]
    holes += [capsule(m(x0, y), m(x1, y), w) for x0, x1, y in
              ((134, 202, 54), (134, 190, 80), (134, 174, 106))]
    return bubble - CrossSection.batch_boolean(holes, __import__("manifold3d").OpType.Add)


def build():
    plate = rrect(*P(0, 240), 760 * MM, 240 * MM, 28 * MM)
    voice = text("Voice ", TITLE_FONT, 72, 270, 128, spacing=-1.5)
    # "Labels" starts where "Voice " ends
    font = TTFont(str(TITLE_FONT))
    k = 72 / font["head"].unitsPerEm
    adv = sum(font["hmtx"][font.getBestCmap()[ord(c)]][0] * k - 1.5 for c in "Voice ")
    labels = text("Labels", TITLE_FONT, 72, 270 + adv, 128, spacing=-1.5)
    tag = text("Speak it · Check it · Print it", TAG_FONT, 24, 274, 174)
    up = lambda cs: cs.extrude(RAISE).translate([0, 0, RAISE_Z])
    base = plate.extrude(BASE_T)
    parts = {
        "logo_1_base_dark": base,
        "logo_2_yellow": up(mark() + labels),
        "logo_3_white": up(voice),
        "logo_4_gray": up(tag),
    }
    parts["logo_plaque"] = Manifold.batch_boolean(list(parts.values()), __import__("manifold3d").OpType.Add)
    return parts


def save(m, path):
    import trimesh
    mesh = m.to_mesh()
    trimesh.Trimesh(np.asarray(mesh.vert_properties)[:, :3], np.asarray(mesh.tri_verts)).export(path)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for name, m in build().items():
        x0, y0, z0, x1, y1, z1 = m.bounding_box()
        print(f"{name:18s} {x1 - x0:6.1f} x {y1 - y0:5.1f} x {z1 - z0:4.1f} mm  pieces {len(m.decompose())}"
              f"  {m.status().name}")
        save(m, OUT / f"{name}.stl")
