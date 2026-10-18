"""Turn a 1-bit label image into ZPL that a Zebra printer understands."""

from __future__ import annotations

from PIL import Image, ImageOps

import config


def image_to_zpl(img: Image.Image, copies: int = 1) -> bytes:
    """Encode the whole label as one ^GF graphic field.

    In ZPL a 1 bit is a black dot. PIL's 1-bit images use 1 for white, so the
    image is inverted first. PIL pads each row to a whole byte, which is the
    same row layout ^GF expects.
    """
    bw = ImageOps.invert(img.convert("L")).convert("1", dither=Image.Dither.NONE)
    width, height = bw.size
    bytes_per_row = (width + 7) // 8
    data = bw.tobytes()
    assert len(data) == bytes_per_row * height
    total = len(data)

    zpl = (
        "^XA"
        "^MNY"                                # gap/notch sensing for die-cut labels
        f"^PW{width}"                         # print width in dots
        f"^LL{height}"                        # label length in dots
        "^LH0,0"
        f"^PR{config.PRINT_SPEED_IPS}"
        f"~SD{config.PRINT_DARKNESS:02d}"
        f"^FO0,0^GFA,{total},{total},{bytes_per_row},{data.hex().upper()}^FS"
        f"^PQ{max(1, int(copies))}"
        "^XZ"
    )
    return zpl.encode("ascii")


def zpl_to_image(zpl: bytes) -> Image.Image:
    """Decode a ^GFA field back into an image (used for testing)."""
    s = zpl.decode("ascii")
    gf = s.split("^GFA,", 1)[1].split("^FS", 1)[0]
    total, _, bpr, hexdata = gf.split(",", 3)
    raw = bytes.fromhex(hexdata)
    height = int(total) // int(bpr)
    img = Image.frombytes("1", (int(bpr) * 8, height), raw)
    return ImageOps.invert(img.convert("L"))
