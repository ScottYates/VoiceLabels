"""Draw the label as an image. The same image is shown on screen and printed,
so the preview is exactly what comes out of the printer."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

import config


@dataclass
class LabelSpec:
    text: str = ""
    show_date: bool = False
    date_text: str = ""
    show_qr: bool = False
    qr_data: str = ""          # blank = use the label text
    orientation: str = config.ORIENTATION


def canvas_size(orientation: str) -> tuple[int, int]:
    short = round(config.LABEL_WIDTH_IN * config.DPI)    # 406
    long = round(config.LABEL_LENGTH_IN * config.DPI)    # 609
    return (long, short) if orientation == "landscape" else (short, long)


@lru_cache(maxsize=64)
def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


# --- text fitting ---------------------------------------------------------

def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str] | None:
    """Word-wrap text to max_w. Returns None if a single word is too wide."""
    lines: list[str] = []
    for para in text.split("\n"):
        words = para.split()
        if not words:
            lines.append("")
            continue
        line = words[0]
        if draw.textlength(line, font=font) > max_w:
            return None
        for w in words[1:]:
            trial = f"{line} {w}"
            if draw.textlength(trial, font=font) <= max_w:
                line = trial
            else:
                if draw.textlength(w, font=font) > max_w:
                    return None
                lines.append(line)
                line = w
        lines.append(line)
    return lines


def _fit_text(draw, text: str, box_w: int, box_h: int):
    """Find the largest font size where the wrapped text fits the box."""
    lo, hi = config.TEXT_MIN_PX, config.TEXT_MAX_PX
    best = None
    while lo <= hi:
        size = (lo + hi) // 2
        font = _font(config.FONT_BOLD, size)
        lines = _wrap(draw, text, font, box_w)
        line_h = round(size * 1.15)
        if lines is not None and line_h * len(lines) <= box_h:
            best = (font, lines, line_h)
            lo = size + 1
        else:
            hi = size - 1
    if best:
        return best
    # Too much text even at the minimum size: wrap by character and cut off.
    font = _font(config.FONT_BOLD, config.TEXT_MIN_PX)
    line_h = round(config.TEXT_MIN_PX * 1.15)
    lines, cur = [], ""
    for ch in text.replace("\n", " "):
        if draw.textlength(cur + ch, font=font) > box_w:
            lines.append(cur)
            cur = ch.lstrip()
        else:
            cur += ch
    lines.append(cur)
    max_lines = max(1, box_h // line_h)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:-1] + "…"
    return font, lines, line_h


def _draw_text_block(draw, text: str, box: tuple[int, int, int, int], center: bool):
    x0, y0, x1, y1 = box
    if not text.strip() or x1 - x0 < 20 or y1 - y0 < 10:
        return
    font, lines, line_h = _fit_text(draw, text.strip(), x1 - x0, y1 - y0)
    total_h = line_h * len(lines)
    y = y0 + (y1 - y0 - total_h) // 2
    for line in lines:
        w = draw.textlength(line, font=font)
        x = x0 + (x1 - x0 - w) / 2 if center else x0
        draw.text((x, y), line, font=font, fill=0)
        y += line_h


# --- QR -------------------------------------------------------------------

def make_qr(data: str, size: int) -> Image.Image:
    """QR code scaled by a whole number of dots per module, so it stays sharp."""
    import qrcode

    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=0, box_size=1)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").get_image().convert("L")
    scale = max(1, size // img.width)
    return img.resize((img.width * scale, img.height * scale), Image.NEAREST)


# --- main entry -----------------------------------------------------------

def render(spec: LabelSpec) -> Image.Image:
    """Return the label as a 1-bit image, in reading orientation."""
    w, h = canvas_size(spec.orientation)
    m = config.MARGIN_DOTS
    img = Image.new("L", (w, h), 255)
    draw = ImageDraw.Draw(img)

    text_box = [m, m, w - m, h - m]
    qr_data = (spec.qr_data or spec.text).strip()
    show_qr = spec.show_qr and bool(qr_data)
    date_font = _font(config.FONT_REGULAR, config.DATE_PX)
    date_h = round(config.DATE_PX * 1.25)
    gap = 12

    if spec.orientation == "landscape":
        # [ text ............ ][ QR ]
        # [ date              ]
        if show_qr:
            qr = make_qr(qr_data, round(min(w, h) * config.QR_SIZE_FRACTION))
            qx = w - m - qr.width
            img.paste(qr, (qx, (h - qr.height) // 2))
            text_box[2] = qx - gap
        if spec.show_date and spec.date_text:
            draw.text((m, h - m - date_h), spec.date_text, font=date_font, fill=0)
            text_box[3] = h - m - date_h - gap
        _draw_text_block(draw, spec.text, tuple(text_box), center=False)
    else:
        # [ date ]
        # [ text ]
        # [  QR  ]
        if spec.show_date and spec.date_text:
            dw = draw.textlength(spec.date_text, font=date_font)
            draw.text(((w - dw) / 2, m), spec.date_text, font=date_font, fill=0)
            text_box[1] = m + date_h + gap
        if show_qr:
            qr = make_qr(qr_data, round(min(w, h) * config.QR_SIZE_FRACTION))
            qy = h - m - qr.height
            img.paste(qr, ((w - qr.width) // 2, qy))
            text_box[3] = qy - gap
        _draw_text_block(draw, spec.text, tuple(text_box), center=True)

    # Hard black/white threshold (no dithering) keeps text edges clean.
    return img.point(lambda p: 255 if p >= 128 else 0).convert("1", dither=Image.Dither.NONE)


def for_printer(img: Image.Image, orientation: str) -> Image.Image:
    """Rotate so the image is 2" wide across the print head."""
    if orientation == "landscape":
        return img.rotate(config.LANDSCAPE_ROTATE_DEG, expand=True)
    return img
