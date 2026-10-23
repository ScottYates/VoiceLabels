"""Send ZPL to the Zebra printer, either straight to the USB device or via a
CUPS raw queue. With --dry-run, labels are saved to ./out instead.

The USB connection is two-way, so the printer can also be asked for its
status (~HS): paused, out of labels, head open, labels waiting in its buffer.
send() checks that first: a paused printer is resumed, and a printer that
can't print says why instead of silently keeping the label.
"""

from __future__ import annotations

import datetime as dt
import os
import subprocess
import threading
import time
from pathlib import Path

import config

_LOCK = threading.Lock()          # one conversation with the printer at a time
LOG = Path(__file__).with_name("printer.log")


class PrintError(Exception):
    pass


def log(msg: str):
    line = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print("printer:", msg, flush=True)
    try:
        lines = LOG.read_text().splitlines(True)[-400:] if LOG.exists() else []
        lines.append(line + "\n")
        LOG.write_text("".join(lines))
    except OSError:
        pass


def _talk(data: bytes, wait: float = 0.0) -> bytes:
    """Write to the USB printer and collect whatever it answers within `wait` s."""
    dev = config.PRINTER_DEVICE
    try:
        fd = os.open(dev, os.O_RDWR | os.O_NONBLOCK)
    except FileNotFoundError as e:
        raise PrintError(f"Printer not found at {dev}. Is it plugged in and on?") from e
    except PermissionError as e:
        raise PrintError(f"No permission for {dev} (add your user to the 'lp' group)") from e
    except OSError as e:
        raise PrintError(f"Printer error: {e}") from e
    try:
        # drain anything left over from earlier, so answers line up
        try:
            while os.read(fd, 4096):
                pass
        except (BlockingIOError, OSError):
            pass
        view, deadline = memoryview(data), time.monotonic() + 30
        while view:
            try:
                n = os.write(fd, view)
                view = view[n:]
            except BlockingIOError:
                if time.monotonic() > deadline:
                    raise PrintError("The printer stopped taking data")
                time.sleep(0.02)
        out, end = b"", time.monotonic() + wait
        while time.monotonic() < end:
            try:
                chunk = os.read(fd, 1024)
                if chunk:
                    out += chunk
                    if out.count(b"\x03") >= 3:        # ~HS answers with three lines
                        break
            except (BlockingIOError, OSError):
                pass
            time.sleep(0.05)
        return out
    except OSError as e:
        raise PrintError(f"Printer error: {e}") from e
    finally:
        os.close(fd)


def status() -> dict | None:
    """The printer's host status (~HS), or None if it didn't answer."""
    if config.CUPS_QUEUE:
        return None
    with _LOCK:
        raw = _talk(b"~HS", wait=2.0)
    lines = [l.strip(b"\x02\x03\r\n ").decode("ascii", "replace")
             for l in raw.split(b"\x03") if l.strip(b"\x02\x03\r\n ")]
    if len(lines) < 2:
        return None
    a, b = lines[0].split(","), lines[1].split(",")
    try:
        return {
            "paper_out": a[1] == "1", "paused": a[2] == "1", "label_length": int(a[3]),
            "formats_waiting": int(a[4]), "buffer_full": a[5] == "1",
            "under_temp": a[10] == "1", "over_temp": a[11] == "1",
            "head_up": b[2] == "1", "ribbon_out": b[3] == "1",
            "labels_remaining": int(b[8]) if b[8].isdigit() else 0,
            "raw": " | ".join(lines),
        }
    except (IndexError, ValueError):
        return {"raw": " | ".join(lines)}


def describe(st: dict | None) -> str:
    if st is None:
        return "no answer"
    bits = [k.replace("_", " ") for k in ("paused", "paper_out", "head_up", "buffer_full",
                                          "under_temp", "over_temp") if st.get(k)]
    if st.get("formats_waiting"):
        bits.append(f"{st['formats_waiting']} label(s) waiting")
    return ", ".join(bits) or "ready"


def problem(st: dict | None) -> str | None:
    """A message for the screen if the printer can't print, else None."""
    if not st:
        return None
    if st.get("paper_out"):
        return "The printer is out of labels (or they aren't loaded through the sensor)"
    if st.get("head_up"):
        return "The printer's lid is open"
    if st.get("over_temp"):
        return "The printer's print head is too hot. Give it a minute"
    return None


def resume():
    """Take the printer out of pause (~PS)."""
    with _LOCK:
        _talk(b"~PS")


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

    note = ""
    st = status()
    if st is None:
        log("no status answer before printing; sending anyway")
    else:
        msg = problem(st)
        if msg:
            log(f"not printing: {describe(st)} [{st.get('raw')}]")
            raise PrintError(msg)
        if st.get("paused"):
            log(f"printer was paused [{st.get('raw')}]; resuming")
            resume()
            note = " (the printer was paused; resumed it)"
    with _LOCK:
        _talk(zpl)
    # A label still sitting in the buffer a few seconds later means it isn't printing.
    time.sleep(2.5)
    after = status()
    if after and after.get("formats_waiting") and not after.get("labels_remaining"):
        log(f"label sent but still waiting: {describe(after)} [{after.get('raw')}]")
        raise PrintError("The printer got the label but isn't printing it ("
                         f"{describe(after)}). Press its feed button once, or turn it off and on")
    return "Sent to printer" + note


def watch(every: float = 30.0, on_change=None):
    """Background check of the printer's status, logging every change (so an
    unexplained stop can be traced to the time it happened)."""
    def loop():
        last = None
        while True:
            st = None
            try:
                if Path(config.PRINTER_DEVICE).exists():
                    st = status()
                    d = describe(st)
                else:
                    d = "not connected"
            except PrintError as e:
                d = f"error: {e}"
            if d != last:
                log(f"status: {d}" + (f" [{st.get('raw')}]" if st else ""))
                if on_change:
                    on_change(st, d)
                last = d
            time.sleep(every)
    if not config.CUPS_QUEUE:
        threading.Thread(target=loop, daemon=True, name="printer-watch").start()
