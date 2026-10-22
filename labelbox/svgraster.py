"""A small SVG renderer for single-colour icons, using only Pillow and numpy.

    svg_to_image(svg_text, 256)  ->  PIL "L" image, black icon on white

Covers what icon sets use: path (every command, arcs included), rect, circle,
ellipse, line, polyline, polygon and g, with fill / stroke / stroke-width /
fill-rule / transform, set as attributes or in style="". Any colour other than
white or "none" paints black, so it suits a black-and-white label printer.
Not covered: gradients, masks, clip paths, text and images.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageDraw

SS = 3                       # supersampling for smooth edges
MAX_SVG_BYTES = 200_000

_NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_TOKEN = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_ARGS = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7, "Z": 0}
INHERITED = ("fill", "stroke", "stroke-width", "fill-rule", "stroke-linecap",
             "stroke-linejoin", "color")


# --- small helpers ---------------------------------------------------------

def _tag(el) -> str:
    return el.tag.rsplit("}", 1)[-1]


def _f(v, default=0.0) -> float:
    if v is None:
        return default
    m = _NUM.search(str(v))
    return float(m.group()) if m else default


def _style(el) -> dict:
    d = {k: v for k, v in el.attrib.items()}
    for part in el.attrib.get("style", "").split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            d[k.strip()] = v.strip()
    return d


def _paint(value) -> int | None:
    """None = don't paint; 0 = black; 255 = white."""
    if value is None:
        return None
    v = value.strip().lower()
    if v in ("none", "transparent") or v.startswith("url("):
        return None
    if v in ("white", "#fff", "#ffffff") or re.fullmatch(r"rgb\(\s*255\s*,\s*255\s*,\s*255\s*\)", v):
        return 255
    return 0


def _mul(a, b):
    """Affine matrices as (a, b, c, d, e, f): x' = a x + c y + e, y' = b x + d y + f."""
    return (a[0] * b[0] + a[2] * b[1], a[1] * b[0] + a[3] * b[1],
            a[0] * b[2] + a[2] * b[3], a[1] * b[2] + a[3] * b[3],
            a[0] * b[4] + a[2] * b[5] + a[4], a[1] * b[4] + a[3] * b[5] + a[5])


def _transform(text: str):
    m = (1, 0, 0, 1, 0, 0)
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", text or ""):
        v = [float(x) for x in _NUM.findall(args)]
        if name == "matrix" and len(v) == 6:
            t = tuple(v)
        elif name == "translate" and v:
            t = (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0)
        elif name == "scale" and v:
            t = (v[0], 0, 0, v[1] if len(v) > 1 else v[0], 0, 0)
        elif name == "rotate" and v:
            a = math.radians(v[0])
            t = (math.cos(a), math.sin(a), -math.sin(a), math.cos(a), 0, 0)
            if len(v) == 3:
                t = _mul(_mul((1, 0, 0, 1, v[1], v[2]), t), (1, 0, 0, 1, -v[1], -v[2]))
        elif name == "skewX" and v:
            t = (1, 0, math.tan(math.radians(v[0])), 1, 0, 0)
        elif name == "skewY" and v:
            t = (1, math.tan(math.radians(v[0])), 0, 1, 0, 0)
        else:
            continue
        m = _mul(m, t)
    return m


def _apply(m, pts):
    return [(m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]) for x, y in pts]


# --- geometry: everything becomes lists of polylines ------------------------

def _bezier(p0, p1, p2, p3, n=16):
    out = []
    for i in range(1, n + 1):
        t = i / n
        u = 1 - t
        out.append((u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
                    u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1]))
    return out


def _arc(p0, rx, ry, phi, large, sweep, p1):
    """Endpoint arc to points (SVG spec, appendix B.2.4)."""
    if p0 == p1:
        return []
    rx, ry = abs(rx), abs(ry)
    if rx == 0 or ry == 0:
        return [p1]
    cp, sp = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    dx, dy = (p0[0] - p1[0]) / 2, (p0[1] - p1[1]) / 2
    x1, y1 = cp * dx + sp * dy, -sp * dx + cp * dy
    lam = (x1 * x1) / (rx * rx) + (y1 * y1) / (ry * ry)
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
    den = rx * rx * y1 * y1 + ry * ry * x1 * x1
    k = math.sqrt(max(0.0, num / den)) if den else 0.0
    if large == sweep:
        k = -k
    cx1, cy1 = k * rx * y1 / ry, -k * ry * x1 / rx
    cx = cp * cx1 - sp * cy1 + (p0[0] + p1[0]) / 2
    cy = sp * cx1 + cp * cy1 + (p0[1] + p1[1]) / 2

    def ang(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a
    t1 = ang(1, 0, (x1 - cx1) / rx, (y1 - cy1) / ry)
    dt = ang((x1 - cx1) / rx, (y1 - cy1) / ry, (-x1 - cx1) / rx, (-y1 - cy1) / ry)
    if not sweep and dt > 0:
        dt -= 2 * math.pi
    elif sweep and dt < 0:
        dt += 2 * math.pi
    n = max(4, int(abs(dt) / (math.pi / 16)))
    out = []
    for i in range(1, n + 1):
        t = t1 + dt * i / n
        x, y = rx * math.cos(t), ry * math.sin(t)
        out.append((cp * x - sp * y + cx, sp * x + cp * y + cy))
    out[-1] = p1
    return out


def parse_path(d: str):
    """Return [(points, closed), ...] for an SVG path's d attribute."""
    toks = _TOKEN.findall(d or "")
    subs, cur, closed = [], [], False
    x = y = sx = sy = 0.0
    last_c = last_q = None           # reflected control points for S / T
    cmd = None
    i = 0

    def flush():
        nonlocal cur, closed
        if len(cur) > 1:
            subs.append((cur, closed))
        cur, closed = [], False

    while i < len(toks):
        t = toks[i]
        if t.isalpha():
            cmd = t
            i += 1
            if cmd in "Zz":
                closed = True
                x, y = sx, sy
                flush()
                cur = [(x, y)]
                last_c = last_q = None
                continue
        if cmd is None:
            break
        n = _ARGS[cmd.upper()]
        if i + n > len(toks) or any(tok.isalpha() for tok in toks[i:i + n]):
            break
        a = [float(v) for v in toks[i:i + n]]
        i += n
        rel = cmd.islower()
        C = cmd.upper()
        ox, oy = (x, y) if rel else (0.0, 0.0)
        if C == "M":
            flush()
            x, y = a[0] + ox, a[1] + oy
            sx, sy = x, y
            cur = [(x, y)]
            cmd = "l" if rel else "L"          # further pairs are line-tos
            last_c = last_q = None
            continue
        if not cur:
            cur = [(x, y)]
        if C == "L":
            x, y = a[0] + ox, a[1] + oy
            cur.append((x, y))
            last_c = last_q = None
        elif C == "H":
            x = a[0] + (x if rel else 0)
            cur.append((x, y))
            last_c = last_q = None
        elif C == "V":
            y = a[0] + (y if rel else 0)
            cur.append((x, y))
            last_c = last_q = None
        elif C in "CS":
            if C == "C":
                c1 = (a[0] + ox, a[1] + oy)
                c2, e = (a[2] + ox, a[3] + oy), (a[4] + ox, a[5] + oy)
            else:
                c1 = (2 * x - last_c[0], 2 * y - last_c[1]) if last_c else (x, y)
                c2, e = (a[0] + ox, a[1] + oy), (a[2] + ox, a[3] + oy)
            cur += _bezier((x, y), c1, c2, e)
            last_c, last_q = c2, None
            x, y = e
        elif C in "QT":
            if C == "Q":
                q, e = (a[0] + ox, a[1] + oy), (a[2] + ox, a[3] + oy)
            else:
                q = (2 * x - last_q[0], 2 * y - last_q[1]) if last_q else (x, y)
                e = (a[0] + ox, a[1] + oy)
            c1 = (x + 2 / 3 * (q[0] - x), y + 2 / 3 * (q[1] - y))
            c2 = (e[0] + 2 / 3 * (q[0] - e[0]), e[1] + 2 / 3 * (q[1] - e[1]))
            cur += _bezier((x, y), c1, c2, e)
            last_q, last_c = q, None
            x, y = e
        elif C == "A":
            e = (a[5] + ox, a[6] + oy)
            cur += _arc((x, y), a[0], a[1], a[2], bool(a[3]), bool(a[4]), e)
            x, y = e
            last_c = last_q = None
    flush()
    return subs


def _ellipse(cx, cy, rx, ry, n=48):
    return [(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n))
            for i in range(n)]


def _shape(el, st):
    t = _tag(el)
    g = lambda k: _f(st.get(k))       # noqa: E731
    if t == "path":
        return parse_path(st.get("d", ""))
    if t == "rect":
        x, y, w, h = g("x"), g("y"), g("width"), g("height")
        if w <= 0 or h <= 0:
            return []
        rx, ry = st.get("rx"), st.get("ry")
        rx = _f(rx if rx is not None else ry)
        ry = _f(ry if ry is not None else st.get("rx"))
        rx, ry = min(rx, w / 2), min(ry, h / 2)
        if rx <= 0 or ry <= 0:
            return [([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], True)]
        d = (f"M{x + rx} {y}H{x + w - rx}A{rx} {ry} 0 0 1 {x + w} {y + ry}V{y + h - ry}"
             f"A{rx} {ry} 0 0 1 {x + w - rx} {y + h}H{x + rx}A{rx} {ry} 0 0 1 {x} {y + h - ry}"
             f"V{y + ry}A{rx} {ry} 0 0 1 {x + rx} {y}Z")
        return parse_path(d)
    if t == "circle":
        r = g("r")
        return [(_ellipse(g("cx"), g("cy"), r, r), True)] if r > 0 else []
    if t == "ellipse":
        return [(_ellipse(g("cx"), g("cy"), g("rx"), g("ry")), True)] if g("rx") > 0 and g("ry") > 0 else []
    if t == "line":
        return [([(g("x1"), g("y1")), (g("x2"), g("y2"))], False)]
    if t in ("polyline", "polygon"):
        v = [float(n) for n in _NUM.findall(st.get("points", ""))]
        pts = list(zip(v[0::2], v[1::2]))
        return [(pts, t == "polygon")] if len(pts) > 1 else []
    return []


# --- raster ----------------------------------------------------------------

def _fill(canvas: np.ndarray, polys, evenodd: bool, value: int):
    """Scanline fill with the non-zero or even-odd rule, sampling pixel centres."""
    edges = []
    for pts in polys:
        n = len(pts)
        for i in range(n):
            (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
            if y0 != y1:
                edges.append((x0, y0, x1, y1))
    if not edges:
        return
    e = np.array(edges, dtype=np.float64)
    x0, y0, x1, y1 = e.T
    ymin, ymax = np.minimum(y0, y1), np.maximum(y0, y1)
    direction = np.where(y1 > y0, 1, -1)
    slope = (x1 - x0) / (y1 - y0)
    h, w = canvas.shape
    r0 = max(0, int(math.floor(ymin.min())))
    r1 = min(h, int(math.ceil(ymax.max())) + 1)
    for row in range(r0, r1):
        yc = row + 0.5
        act = (ymin <= yc) & (yc < ymax)
        if not act.any():
            continue
        xs = x0[act] + (yc - y0[act]) * slope[act]
        ds = direction[act]
        order = np.argsort(xs, kind="stable")
        xs, ds = xs[order], ds[order]
        if evenodd:
            inside = (np.arange(1, len(xs) + 1) % 2) == 1
        else:
            inside = np.cumsum(ds) != 0
        for k in np.nonzero(inside)[0]:
            if k + 1 >= len(xs):
                break
            a = max(0, int(math.ceil(xs[k] - 0.5)))
            b = min(w, int(math.ceil(xs[k + 1] - 0.5)))
            if b > a:
                canvas[row, a:b] = value


def _stroke(img: Image.Image, subs, width: float, value: int, round_caps: bool):
    d = ImageDraw.Draw(img)
    w = max(1, int(round(width)))
    r = width / 2
    for pts, closed in subs:
        line = list(pts) + ([pts[0]] if closed else [])
        d.line(line, fill=value, width=w)
        joints = line if (round_caps or closed) else line[1:-1]
        for x, y in joints:                       # round joins (and caps)
            d.ellipse((x - r, y - r, x + r, y + r), fill=value)


def svg_to_image(svg: str | bytes, size: int) -> Image.Image:
    """Render to a size x size "L" image: black icon, white background, centred."""
    if isinstance(svg, bytes):
        svg = svg.decode("utf-8", "replace")
    if len(svg) > MAX_SVG_BYTES or "<!ENTITY" in svg:
        raise ValueError("SVG too large or not allowed")
    root = ET.fromstring(svg)
    vb = [float(v) for v in _NUM.findall(root.attrib.get("viewBox", ""))]
    if len(vb) != 4 or vb[2] <= 0 or vb[3] <= 0:
        vb = [0, 0, _f(root.attrib.get("width"), 24) or 24, _f(root.attrib.get("height"), 24) or 24]
    px = size * SS
    scale = px / max(vb[2], vb[3])
    ox = (px - vb[2] * scale) / 2 - vb[0] * scale
    oy = (px - vb[3] * scale) / 2 - vb[1] * scale
    base = (scale, 0, 0, scale, ox, oy)

    img = Image.new("L", (px, px), 255)
    canvas = np.array(img)
    skip = {"defs", "clipPath", "mask", "title", "desc", "metadata", "style", "symbol",
            "linearGradient", "radialGradient", "pattern", "text"}

    def walk(el, inherited, m):
        nonlocal canvas, img
        st = _style(el)
        if st.get("display") == "none" or st.get("visibility") == "hidden":
            return
        if _f(st.get("opacity"), 1) < 0.35:
            return
        style = dict(inherited)
        for k in INHERITED:
            if k in st:
                style[k] = st[k]
        m = _mul(m, _transform(st.get("transform", "")))
        t = _tag(el)
        if t in skip:
            return
        if t in ("svg", "g", "a"):
            for ch in el:
                walk(ch, style, m)
            return
        subs = _shape(el, st)
        if not subs:
            return
        subs = [(_apply(m, pts), closed) for pts, closed in subs]
        fill = _paint(style.get("fill", "black"))
        if fill is not None and _f(st.get("fill-opacity"), 1) >= 0.35 and t not in ("line", "polyline"):
            _fill(canvas, [p for p, _ in subs], style.get("fill-rule") == "evenodd", fill)
        elif fill is not None and t == "polyline":
            _fill(canvas, [p for p, _ in subs], style.get("fill-rule") == "evenodd", fill)
        stroke = _paint(style.get("stroke"))
        if stroke is not None:
            sw = _f(style.get("stroke-width"), 1.0) * math.sqrt(abs(m[0] * m[3] - m[1] * m[2]))
            img = Image.fromarray(canvas)
            _stroke(img, subs, sw, stroke,
                    style.get("stroke-linecap", "butt") in ("round", "square"))
            canvas = np.array(img)

    walk(root, {"fill": "black"}, base)
    return Image.fromarray(canvas).resize((size, size), Image.LANCZOS)
