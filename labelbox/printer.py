"""Send ZPL to the Zebra printer, either straight to the USB device or via a
CUPS raw queue. With --dry-run, labels are saved to ./out instead."""

from __future__ import annotations

import datetime as dt
import subprocess
from pathlib import Path

import config


class PrintError(Exception):
    pass


def send(zpl: bytes, dry_run: bool = False, preview_png=None) -> str:
    if dry_run:
        out = Path(__file__).parent / "out"
        out.mkdir(exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        (out / f"label-{stamp}.zpl").write_bytes(zpl)
        if preview_png is not None:
            preview_png.save(out / f"label-{stamp}.png")
        return f"Saved to out/label-{stamp}.zpl (dry run)"

    if config.CUPS_QUEUE:
        r = subprocess.run(["lp", "-d", config.CUPS_QUEUE, "-o", "raw"],
                           input=zpl, capture_output=True)
        if r.returncode != 0:
            raise PrintError(r.stderr.decode(errors="replace").strip() or "lp failed")
        return "Sent to printer"

    dev = Path(config.PRINTER_DEVICE)
    if not dev.exists():
        raise PrintError(f"Printer not found at {dev}. Is it plugged in and on?")
    try:
        with open(dev, "wb") as f:
            f.write(zpl)
    except PermissionError as e:
        raise PrintError(f"No permission for {dev} (add your user to the 'lp' group)") from e
    except OSError as e:
        raise PrintError(f"Printer error: {e}") from e
    return "Sent to printer"
