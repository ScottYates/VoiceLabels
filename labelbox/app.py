"""Voice label printer: hold the button, speak, edit, see the label, print.

    python3 app.py              # normal (fullscreen, prints to the Zebra)
    python3 app.py --dry-run    # saves labels to ./out instead of printing
    python3 app.py --windowed   # not fullscreen (handy when testing)

Keys: F1 talk (press to start, press again to stop)   F2 date on/off
      F3 QR on/off   F4 landscape/portrait   F5 left/center/right
      Ctrl+P or Ctrl+Enter print
      Esc clear text   Ctrl+Shift+Q quit
Touch: tap TALK then press and hold it again = clear and start over;
       press and hold the text box or preview = screen off
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
from pathlib import Path
import queue
import subprocess
import time
import threading
import tkinter as tk

from PIL import Image, ImageTk

import config
import icons
import printer
from hardware import Button
from render import LabelSpec, for_printer, render
from stt import PushToTalk
from zpl import image_to_zpl

BG = "#1e1f22"
PANEL = "#2b2d31"
FG = "#f2f3f5"
MUTED = "#a4a7ad"
ACCENT = "#f0b232"
REC = "#e5484d"
OK = "#3fb950"
INPUT_BG = "#14161a"      # text box: darker than the panel, unlike the white label
INPUT_EDGE = "#4a4f57"
LINER = "#c9b98f"         # label backing paper in the preview
LABEL_GHOST = "#d9d6cc"   # neighbouring labels on the roll


def today() -> str:
    return dt.date.today().strftime(config.DATE_FORMAT)


class PowerTile(tk.Canvas):
    """A large square-ish tile: drawn icon, label and a short note, all inside.
    Tapping calls on_tap; the owner switches it between normal and armed."""

    def __init__(self, master, kind, label, note, font_big, font_note, on_tap, accent,
                 icon=None, icon_armed=None):
        super().__init__(master, bg=BG, highlightthickness=0, bd=0, cursor="hand2")
        self.kind, self.label, self.note = kind, label, note
        self.icon, self.icon_armed = icon, icon_armed
        self.font_big, self.font_note, self.accent = font_big, font_note, accent
        self.armed_text = None
        self.bind("<Configure>", lambda e: self.draw())
        self.bind("<ButtonRelease-1>", lambda e: on_tap())

    def set_armed(self, text):
        self.armed_text = text
        self.draw()

    @staticmethod
    def _rrect(c, x0, y0, x1, y1, r, **kw):
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
               x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        return c.create_polygon(pts, smooth=True, **kw)

    def draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 20 or h < 20:
            return
        armed = self.armed_text is not None
        bg = REC if armed else PANEL
        self._rrect(self, 2, 2, w - 2, h - 2, 18, fill=bg, outline="")
        fg = "#ffffff" if armed else FG
        icon_col = "#ffffff" if armed else self.accent
        cx, cy, r = w / 2, h * 0.34, min(w, h) * 0.16
        lw = max(4, int(r / 5))
        if self.icon is not None:
            self.create_image(cx, cy, image=self.icon_armed if armed else self.icon)
        elif self.kind == "shutdown":                      # power symbol
            self.create_arc(cx - r, cy - r, cx + r, cy + r, start=120, extent=300,
                            style="arc", outline=icon_col, width=lw)
            self.create_line(cx, cy - r * 1.15, cx, cy - r * 0.15, fill=icon_col, width=lw,
                             capstyle="round")
        elif self.kind == "restart":                     # circular arrow
            self.create_arc(cx - r, cy - r, cx + r, cy + r, start=110, extent=290,
                            style="arc", outline=icon_col, width=lw)
            import math as _m
            a = _m.radians(110)
            ex, ey = cx + r * _m.cos(a), cy - r * _m.sin(a)
            s_ = r * 0.55
            self.create_polygon(ex - s_ * 0.2, ey - s_ * 0.55, ex + s_ * 0.85, ey - s_ * 0.05,
                                ex - s_ * 0.2, ey + s_ * 0.6, fill=icon_col, outline="")
        else:                                            # monitor (desktop)
            self.create_rectangle(cx - r * 1.25, cy - r * 0.9, cx + r * 1.25, cy + r * 0.6,
                                  outline=icon_col, width=lw)
            self.create_line(cx, cy + r * 0.6, cx, cy + r * 1.05, fill=icon_col, width=lw)
            self.create_line(cx - r * 0.6, cy + r * 1.1, cx + r * 0.6, cy + r * 1.1,
                             fill=icon_col, width=lw, capstyle="round")
        main = self.armed_text if armed else self.label
        self.create_text(cx, h * 0.66, text=main, fill=fg, font=self.font_big, justify="center",
                         width=w - 24)
        if not armed:
            self.create_text(cx, h * 0.87, text=self.note, fill=MUTED, font=self.font_note,
                             justify="center", width=w - 24)


class HoldButton(tk.Canvas):
    """A button that must be held for `seconds` before it fires.

    While held, a green bar sweeps across it and the label counts down.
    Letting go early cancels. begin()/end() can also be driven by a
    physical button.
    """

    def __init__(self, master, text, font, seconds, on_fire, on_start=None,
                 on_cancel=None, bg=ACCENT, fill=OK, fg="#000000", icon=None):
        super().__init__(master, highlightthickness=0, bd=0, bg=bg, height=1, cursor="hand2")
        self.text, self.font, self.seconds = text, font, seconds
        self.icon = icon                                  # a PhotoImage drawn left of the label
        import tkinter.font as tkfont
        self._measure = tkfont.Font(font=font).measure
        self.on_fire, self.on_start, self.on_cancel = on_fire, on_start, on_cancel
        self.bg, self.fill, self.fg = bg, fill, fg
        self._t0 = None
        self._job = None
        self.bind("<Configure>", lambda e: self._draw(0.0))
        self.bind("<ButtonPress-1>", lambda e: self.begin())
        self.bind("<ButtonRelease-1>", lambda e: self.end())

    def _draw(self, p, label=None):
        w, h = self.winfo_width(), self.winfo_height()
        self.delete("all")
        self.create_rectangle(0, 0, w, h, fill=self.bg, width=0)
        if p > 0:
            self.create_rectangle(0, 0, int(w * min(p, 1.0)), h, fill=self.fill, width=0)
        text = label or self.text
        if self.icon is None:
            self.create_text(w // 2, h // 2, text=text, font=self.font, fill=self.fg)
            return
        iw, gap = self.icon.width(), max(8, self.icon.width() // 3)
        total = iw + gap + self._measure(text)
        x0 = (w - total) // 2
        self.create_image(x0 + iw // 2, h // 2, image=self.icon)
        self.create_text(x0 + iw + gap, h // 2, text=text, font=self.font, fill=self.fg, anchor="w")

    def begin(self):
        if self._t0 is not None:
            return
        if self.on_start and self.on_start() is False:
            return                                      # nothing to print, etc.
        if self.seconds <= 0:                           # no hold required
            self._draw(1.0, "PRINTING")
            self.after(700, lambda: self._draw(0.0))
            self.on_fire()
            return
        self._t0 = time.monotonic()
        self._tick()

    def _tick(self):
        p = (time.monotonic() - self._t0) / self.seconds
        if p >= 1.0:
            self._t0 = None
            self._draw(1.0, "PRINTING")
            self.after(700, lambda: self._draw(0.0))
            self.on_fire()
            return
        left = max(1, int(self.seconds - (time.monotonic() - self._t0)) + 1)
        self._draw(p, f"HOLD {left}")
        self._job = self.after(30, self._tick)

    def end(self):
        if self._t0 is None:
            return
        self._t0 = None
        if self._job:
            self.after_cancel(self._job)
            self._job = None
        self._draw(0.0)
        if self.on_cancel:
            self.on_cancel()


class App:
    def __init__(self, root: tk.Tk, dry_run: bool, screen: tuple[int, int]):
        self.root = root
        self.screen = screen
        self.dry_run = dry_run
        self.events: queue.Queue = queue.Queue()
        self.recording = False
        self.busy = False
        self._preview_job = None
        self._preview_photo = None
        self._auto_date = today()

        self.show_date = tk.BooleanVar(value=config.DATE_DEFAULT_ON)
        self.show_qr = tk.BooleanVar(value=config.QR_DEFAULT_ON)
        self.date_text = tk.StringVar(value=self._auto_date)
        self.qr_text = tk.StringVar(value="")
        self.orientation = tk.StringVar(value=config.ORIENTATION)
        self.align = tk.StringVar(value=config.TEXT_ALIGN)
        self.copies = tk.IntVar(value=1)

        self._build_ui()
        self._bind_keys()
        saved = self._load_settings()
        self.brightness = int(saved.get("brightness", 100))
        self.print_btn.seconds = float(saved.get("print_hold", config.PRINT_HOLD_SECONDS))
        if saved.get("align") in self.ALIGNS:
            self.align.set(saved["align"])
        self._refresh_align_buttons()
        self._display_power(True)     # in case an earlier run left it blanked
        self._apply_brightness()

        self.stt = PushToTalk(
            on_partial=lambda t: self.events.put(("partial", t)),
            on_final=lambda t: self.events.put(("final", t)),
            on_error=lambda m: self.events.put(("error", m)),
            on_progress=lambda f, _file: self.events.put(("progress", f)),
        )
        self.button = Button(
            config.TALK_BUTTON_PIN, config.TALK_LED_PIN,
            on_press=lambda: self.events.put(("hw_press", None)),
            on_release=lambda held: self.events.put(("hw_release", held)),
        )
        self.print_hw = Button(
            config.PRINT_BUTTON_PIN, config.PRINT_LED_PIN,
            on_press=lambda: self.events.put(("print_press", None)),
            on_release=lambda held: self.events.put(("print_release", held)),
        )

        self.set_status("Initializing…", MUTED)
        threading.Thread(target=self._load_model, daemon=True).start()

        for var in (self.show_date, self.show_qr, self.date_text, self.qr_text, self.orientation,
                    self.align):
            var.trace_add("write", lambda *_: self.schedule_preview())
        self.root.after(50, self._poll)
        self.schedule_preview()

        # Screen blanking: any touch, click or key counts as activity.
        self._last_activity = time.monotonic()
        self._blank_overlay = None
        self._talk_down_at = 0.0
        self._last_talk_tap = -10.0
        self._lp_jobs = []
        self._lp_origin = None
        self._lp_status = None
        self.root.bind_all("<ButtonPress>", lambda e: self._note_activity(), add="+")
        self.root.bind_all("<KeyPress>", lambda e: self._wake(), add="+")
        if config.SCREEN_BLANK_SECONDS:
            self.root.after(5000, self._check_idle)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        """Main screen: Hold to talk (top left) and PRINT (top right) side by
        side at the same size; below them the label preview and status on the
        left, the text box and Rotate / Clear / Setup on the right. Date, QR,
        copies and brightness live on a separate Setup screen with big buttons.
        Sizes scale with the screen (800x480 on the 7" panel)."""
        r = self.root
        sw, sh = self.screen
        s = min(sw, sh) / 720          # 0.67 on 800x480
        self._s = s

        def font(pt, bold=False):
            size = max(9, round(pt * s))
            return ("DejaVu Sans", size, "bold") if bold else ("DejaVu Sans", size)
        self._font = font
        self._icon_cache = {}

        pad = max(6, round(14 * s))
        gap = max(4, round(9 * s))
        self._gap = gap
        r.configure(bg=BG)

        body = tk.Frame(r, bg=BG)
        body.pack(fill="both", expand=True, padx=pad, pady=pad)
        body.columnconfigure(0, weight=11, uniform="c")
        body.columnconfigure(1, weight=9, uniform="c")

        # Top row: the two main actions, same height and font.
        big = dict(font=font(30, True), relief="flat", bd=0, highlightthickness=0,
                   pady=round(30 * s), cursor="hand2")
        self.talk_btn = tk.Button(body, text=" Hold to talk", bg=PANEL, fg=FG,
                                  image=self.icon("mic", FG, 30), compound="left",
                                  activebackground=PANEL, activeforeground=FG, **big)
        self.talk_btn.grid(row=0, column=0, sticky="nsew", padx=(0, pad), pady=(0, gap))
        self.talk_btn.bind("<ButtonPress-1>", lambda e: self.talk_press())
        self.talk_btn.bind("<ButtonRelease-1>", lambda e: self.talk_release())
        self.print_btn = HoldButton(body, "PRINT", font(30, True), config.PRINT_HOLD_SECONDS,
                                    on_fire=self.print_label, on_start=self._print_hold_start,
                                    on_cancel=self._print_hold_cancel,
                                    icon=self.icon("printer", "#000000", 30))
        self.print_btn.grid(row=0, column=1, sticky="nsew", pady=(0, gap))

        # Rows below the top buttons: captions, the two boxes (same height),
        # then the status message beside Rotate / Clear / Setup.
        body.rowconfigure(1, weight=0)
        body.rowconfigure(2, weight=1)
        cap_font, cap_bold = font(15), font(15, True)

        cap = tk.Frame(body, bg=BG)
        cap.grid(row=1, column=1, sticky="ew")
        tk.Label(cap, text="LABEL PREVIEW", bg=BG, fg=MUTED, font=cap_bold,
                 anchor="w").pack(side="left")
        self.size_caption = tk.Label(cap, text="", bg=BG, fg=MUTED, font=cap_font, anchor="e")
        self.size_caption.pack(side="right")
        tcap = tk.Frame(body, bg=BG)
        tcap.grid(row=1, column=0, sticky="ew", padx=(0, pad))
        tk.Label(tcap, text="TEXT", bg=BG, fg=MUTED, font=cap_bold,
                 anchor="w").pack(side="left")
        tk.Label(tcap, text="type here to edit", bg=BG, fg=MUTED, font=cap_font,
                 anchor="e").pack(side="right")

        # Right box: the label drawn on its backing paper.
        self.canvas = tk.Canvas(body, bg=LINER, width=1, height=1, highlightthickness=2,
                                highlightbackground=INPUT_EDGE)
        self.canvas.grid(row=2, column=1, sticky="nsew")
        self.canvas.bind("<Configure>", lambda e: self.schedule_preview())

        # Left box: a dark input, so it can't be mistaken for the white label.
        self.text = tk.Text(body, width=1, height=1, wrap="word", font=font(22),
                            bg=INPUT_BG, fg=FG, insertbackground=FG, insertwidth=3,
                            undo=True, relief="flat", padx=10, pady=8,
                            highlightthickness=2, highlightbackground=INPUT_EDGE,
                            highlightcolor=ACCENT, selectbackground=ACCENT,
                            selectforeground="#000000")
        self.text.grid(row=2, column=0, sticky="nsew", padx=(0, pad))
        self.text.bind("<<Modified>>", self._text_changed)
        self.placeholder = tk.Label(self.text, text="Hold to talk, or type the label text",
                                    bg=INPUT_BG, fg=MUTED, font=font(19), anchor="nw",
                                    justify="left", wraplength=1)
        self.placeholder.bind("<Button-1>", lambda e: self.text.focus_set())
        # Press and hold on either box turns the screen off.
        for w in (self.text, self.placeholder, self.canvas):
            w.bind("<ButtonPress-1>", self._long_press_start, add="+")
            w.bind("<B1-Motion>", self._long_press_move, add="+")
            w.bind("<ButtonRelease-1>", self._long_press_cancel, add="+")
        self.text.bind("<Configure>", lambda e: (
            self.placeholder.configure(wraplength=max(50, e.width - 30)),
            self.status.configure(wraplength=max(100, e.width - 4))))

        # Bottom row: status message (left), Rotate / Clear / Setup (right).
        self.status = tk.Label(body, text="", bg=BG, fg=FG, font=font(22, True),
                               anchor="w", justify="left")
        self.status.grid(row=3, column=0, sticky="ew", padx=(0, pad), pady=(gap, 0))
        row = tk.Frame(body, bg=BG)
        row.grid(row=3, column=1, sticky="ew", pady=(gap, 0))
        btn = dict(font=font(20, True), relief="flat", bd=0, highlightthickness=0,
                   pady=round(18 * s), bg=PANEL, fg=FG, activebackground=PANEL,
                   activeforeground=FG, cursor="hand2")
        for col, (label, ic, cmd) in enumerate([(" Rotate", "rotate", self.toggle_orientation),
                                                (" Clear", "clear", self.clear),
                                                (" Setup", "gear", self.open_setup)]):
            row.columnconfigure(col, weight=1, uniform="b")
            tk.Button(row, text=label, command=cmd, image=self.icon(ic, FG, 20), compound="left",
                      **btn).grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else gap, 0))

        self._build_setup()
        self.text.focus_set()

    # --------------------------------------------------------------- setup
    def _build_setup(self):
        """A full-window panel, hidden until Setup is tapped."""
        s, font, gap = self._s, self._font, self._gap
        pad = max(8, round(18 * s))
        p = tk.Frame(self.root, bg=BG)
        self.setup_panel = p
        p.columnconfigure(1, weight=1)
        for r_ in (1, 2, 4, 5, 6):              # button rows share the spare height
            p.rowconfigure(r_, weight=1, uniform="rows")

        big = dict(font=font(24, True), relief="flat", bd=0, highlightthickness=0,
                   pady=round(20 * s), cursor="hand2", bg=PANEL, fg=FG,
                   activebackground=PANEL, activeforeground=FG)
        label = dict(bg=BG, fg=MUTED, font=font(20, True), anchor="w")
        entry = dict(font=font(24), relief="flat")

        head = tk.Frame(p, bg=BG)
        head.grid(row=0, column=0, columnspan=2, sticky="w", padx=pad, pady=(pad, gap))
        tk.Label(head, text="Setup", bg=BG, fg=FG, font=font(30, True), anchor="w").pack(anchor="w")
        self.net_label = tk.Label(head, text="", bg=BG, fg=MUTED, font=font(15, True), anchor="w")
        self.net_label.pack(anchor="w")
        top = tk.Frame(p, bg=BG)
        top.grid(row=0, column=1, sticky="e", padx=pad, pady=(pad, gap))
        self.protect_label = tk.Label(top, text="", bg=BG, font=font(15, True), justify="right")
        self.protect_label.pack(side="left", padx=(0, pad))
        tk.Button(top, text=" Power", command=self.open_power, image=self.icon("power", FG, 24),
                  compound="left", **dict(big, padx=round(26 * s))).pack(side="left", padx=(0, gap))
        tk.Button(top, text=" Done", command=self.close_setup, image=self.icon("check", "#000000", 24),
                  compound="left",
                  **dict(big, bg=ACCENT, fg="#000000", activebackground="#ffd36b",
                         activeforeground="#000000", padx=round(30 * s))).pack(side="left")

        # Date and QR: a big on/off button plus the text to print.
        self._toggles = {}
        for r_, (name, var, text_var) in enumerate(
                [("Date", self.show_date, self.date_text), ("QR", self.show_qr, self.qr_text)],
                start=1):
            t = tk.Checkbutton(p, text=name, variable=var, indicatoron=False,
                               offrelief="flat", selectcolor=OK, **big)
            t.grid(row=r_, column=0, sticky="nsew", padx=(pad, gap), pady=(0, gap))
            tk.Entry(p, textvariable=text_var, **entry).grid(
                row=r_, column=1, sticky="nsew", padx=(0, pad), pady=(0, gap))
            self._toggles[name] = (t, var)
            var.trace_add("write", lambda *_: self._refresh_toggles())
        tk.Label(p, text="QR text: leave blank to use the label text", bg=BG, fg=MUTED,
                 font=font(15), anchor="w").grid(row=3, column=1, sticky="w",
                                                 padx=(0, pad), pady=(0, gap))

        # Text alignment: Left / Center / Right, the current one highlighted.
        tk.Label(p, text=" Align", image=self.icon("align-left", MUTED, 20), compound="left",
                 **label).grid(row=4, column=0, sticky="w", padx=(pad, gap), pady=(0, gap))
        al = tk.Frame(p, bg=BG)
        al.grid(row=4, column=1, sticky="nsew", padx=(0, pad), pady=(0, gap))
        al.rowconfigure(0, weight=1)
        self._align_btns = {}
        for i, a in enumerate(self.ALIGNS):
            al.columnconfigure(i, weight=1, uniform="al")
            b = tk.Button(al, text=" " + a.capitalize(), compound="left",
                          command=lambda a=a: self.set_align(a), **big)
            b.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else gap, 0))
            self._align_btns[a] = b

        # Copies: − n +
        tk.Label(p, text=" Copies", image=self.icon("copies", MUTED, 20), compound="left",
                 **label).grid(row=5, column=0, sticky="w",
                                                padx=(pad, gap), pady=(0, gap))
        cp = tk.Frame(p, bg=BG)
        cp.grid(row=5, column=1, sticky="nsw", padx=(0, pad), pady=(0, gap))
        step = dict(big, padx=round(34 * s))
        tk.Button(cp, text="−", command=lambda: self._bump_copies(-1), **step).pack(side="left", fill="y")
        tk.Label(cp, textvariable=self.copies, bg=BG, fg=FG, width=3,
                 font=font(30, True)).pack(side="left")
        tk.Button(cp, text="+", command=lambda: self._bump_copies(1), **step).pack(side="left", fill="y")

        # Brightness: one button per level, the current one highlighted.
        tk.Label(p, text=" Brightness", image=self.icon("sun", MUTED, 20), compound="left",
                 **label).grid(row=6, column=0, sticky="w",
                                                    padx=(pad, gap), pady=(0, gap))
        br = tk.Frame(p, bg=BG)
        br.grid(row=6, column=1, sticky="nsew", padx=(0, pad), pady=(0, gap))
        br.rowconfigure(0, weight=1)
        self._bright_btns = {}
        for i, lv in enumerate(sorted(config.BRIGHTNESS_LEVELS) or [100]):
            br.columnconfigure(i, weight=1, uniform="br")
            b = tk.Button(br, text=f"{lv}%", command=lambda lv=lv: self.set_brightness(lv), **big)
            b.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else gap, 0))
            self._bright_btns[lv] = b
        # Print hold: how long PRINT must be held.
        p.rowconfigure(7, weight=1, uniform="rows")
        tk.Label(p, text=" Print hold", image=self.icon("timer", MUTED, 20), compound="left",
                 **label).grid(row=7, column=0, sticky="w",
                                                    padx=(pad, gap), pady=(0, pad))
        ph = tk.Frame(p, bg=BG)
        ph.grid(row=7, column=1, sticky="nsew", padx=(0, pad), pady=(0, pad))
        ph.rowconfigure(0, weight=1)
        self._hold_btns = {}
        for i, sec in enumerate(config.PRINT_HOLD_CHOICES):
            ph.columnconfigure(i, weight=1, uniform="ph")
            b = tk.Button(ph, text="Off" if sec == 0 else f"{sec:g} s",
                          command=lambda sec=sec: self.set_print_hold(sec), **big)
            b.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else gap, 0))
            self._hold_btns[sec] = b
        self._refresh_toggles()
        self._build_power(big, pad, gap, font)

    # ------------------------------------------------------------ power panel
    POWER_ACTIONS = {   # key: (label, armed label, note)
        "restart": ("Restart", "Tap again\nto restart", "Back in about a minute"),
        "shutdown": ("Shut down", "Tap again\nto shut down", "Switch back on to start"),
        "desktop": ("Desktop", "Tap again\nto exit", "The app icon brings it back"),
    }

    def _build_power(self, big, pad, gap, font):
        """Restart / Shut down / Exit to desktop, each needing a second tap."""
        p = tk.Frame(self.root, bg=BG)
        self.power_panel = p
        p.columnconfigure((0, 1, 2), weight=1, uniform="pw")
        p.rowconfigure(2, weight=1)
        tk.Label(p, text="Power", bg=BG, fg=FG, font=font(30, True), anchor="w").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=pad, pady=(pad, gap))
        tk.Button(p, text=" Back", command=self.close_power, image=self.icon("back", "#000000", 24),
                  compound="left",
                  **dict(big, bg=ACCENT, fg="#000000", activebackground="#ffd36b",
                         activeforeground="#000000", padx=round(30 * self._s))).grid(
            row=0, column=2, sticky="e", padx=pad, pady=(pad, gap))
        self.power_note = tk.Label(p, text="", bg=BG, fg=MUTED, font=font(16, True), anchor="w",
                                   justify="left")
        self.power_note.grid(row=1, column=0, columnspan=3, sticky="w", padx=pad, pady=(0, gap))
        self._power_btns = {}
        accents = {"restart": ACCENT, "shutdown": REC, "desktop": MUTED}
        row = tk.Frame(p, bg=BG)                     # equal spacing, so all tiles match
        row.grid(row=2, column=0, columnspan=3, sticky="nsew", padx=pad - gap // 2, pady=(0, pad))
        row.rowconfigure(0, weight=1)
        for i, (key, (lab, _, note)) in enumerate(self.POWER_ACTIONS.items()):
            row.columnconfigure(i, weight=1, uniform="tile")
            ic = {"restart": "rotate", "shutdown": "power", "desktop": "monitor"}[key]
            t = PowerTile(row, key, lab, note, font(24, True), font(14),
                          lambda k=key: self._power_tap(k), accents[key],
                          icon=self.icon(ic, accents[key], 84),
                          icon_armed=self.icon(ic, "#ffffff", 84))
            t.grid(row=0, column=i, sticky="nsew", padx=gap // 2)
            self._power_btns[key] = t
        self._power_armed = None

    def open_power(self):
        self._power_armed = None
        self._refresh_power_buttons()
        state = self.protection_state()
        self.power_note.configure(text={
            "on": "Safe to unplug at any time.",
            "pending": "Unplug protection starts after a restart.",
            "ending": "Unplug protection ends at the next restart.",
            "off": "Shut down before unplugging.",
        }[state], fg=OK if state == "on" else MUTED)
        self.power_panel.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.power_panel.lift()

    def close_power(self):
        self._power_armed = None
        self.power_panel.place_forget()

    def _refresh_power_buttons(self):
        for key, t in self._power_btns.items():
            t.set_armed(self.POWER_ACTIONS[key][1] if key == self._power_armed else None)

    def _power_tap(self, key):
        """First tap arms the button for 4 s; a second tap does it."""
        if self._power_armed != key:
            self._power_armed = key
            self._refresh_power_buttons()
            token = object()
            self._power_token = token
            self.root.after(4000, lambda: (self._power_token is token and self._power_armed == key
                                           and (setattr(self, "_power_armed", None),
                                                self._refresh_power_buttons())))
            return
        self._power_armed = None
        self._refresh_power_buttons()
        if key == "desktop":
            self._exit_armed = True
            self.exit_to_desktop()
            return
        verb, msg = (("reboot", "Restarting…") if key == "restart"
                     else ("poweroff", "Shutting down… wait for the screen to go dark"))
        self.button.led_off()
        self.print_hw.led_off()
        try:
            subprocess.run(["sync"], timeout=20)
            r = subprocess.run(["systemctl", verb], capture_output=True, text=True, timeout=20)
            ok = r.returncode == 0
            err = r.stderr.strip()
        except Exception as e:  # noqa: BLE001
            ok, err = False, str(e)
        if ok:
            self.power_note.configure(text=msg, fg=ACCENT)
        else:
            if "authentication" in (err or "").lower():
                err = "not allowed yet. Run once: sudo bash ~/labelbox/kiosk/allow-power.sh"
            self.power_note.configure(text="Couldn't do that: " + (err or "systemctl failed")[:120], fg=REC)

    ALIGNS = ("left", "center", "right")

    def set_align(self, align: str):
        if align not in self.ALIGNS:
            return
        self.align.set(align)
        self._save_settings(align=align)
        self._refresh_align_buttons()

    def cycle_align(self):
        i = self.ALIGNS.index(self.align.get()) if self.align.get() in self.ALIGNS else 0
        self.set_align(self.ALIGNS[(i + 1) % len(self.ALIGNS)])

    def _refresh_align_buttons(self):
        cur = self.align.get()
        for a, b in getattr(self, "_align_btns", {}).items():
            on = a == cur
            col = "#000000" if on else FG
            b.configure(image=self.icon("align-" + a, col, 24),
                        bg=OK if on else PANEL, activebackground=OK if on else PANEL,
                        fg=col, activeforeground=col)

    def set_print_hold(self, seconds):
        self.print_btn.seconds = float(seconds)
        self._save_settings(print_hold=float(seconds))
        self._refresh_hold_buttons()

    def _refresh_hold_buttons(self):
        cur = self.print_btn.seconds
        for sec, b in getattr(self, "_hold_btns", {}).items():
            on = abs(sec - cur) < 1e-6
            b.configure(bg=OK if on else PANEL, activebackground=OK if on else PANEL,
                        fg="#000000" if on else FG, activeforeground="#000000" if on else FG)

    def open_setup(self):
        self.setup_panel.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.setup_panel.lift()
        self._refresh_brightness_buttons()
        self._refresh_hold_buttons()
        text, color = {
            "on": ("Safe to unplug", OK),
            "pending": ("Safe to unplug\nafter a restart", MUTED),
            "ending": ("Unplug protection\nends at restart", ACCENT),
            "off": ("Shut down before\nunplugging", MUTED),
        }[self.protection_state()]
        self.protect_label.configure(text=text, fg=color)
        self.net_label.configure(text=self.network_text())

    def exit_to_desktop(self):
        """First tap arms the button; a second tap within 4 s leaves the app."""
        if not getattr(self, "_exit_armed", False):
            self.open_setup()
            self.open_power()
            return
        self._exit_armed = False
        if os.environ.get("LABELBOX_KIOSK"):
            # Starting the desktop stops the kiosk service (they conflict).
            r = subprocess.run(["systemctl", "--no-block", "start", "lightdm.service"],
                               capture_output=True, text=True)
            if r.returncode != 0:
                self.close_power()
                self.close_setup()
                self.set_status("Couldn't start the desktop: "
                                + (r.stderr.strip() or "systemctl failed"), REC)
        else:
            self.root.destroy()                         # running on the desktop already

    def _quit_now(self):
        """Ctrl+Shift+Q: go straight to the desktop (or quit if already there)."""
        self._exit_armed = True
        self.exit_to_desktop()

    def close_setup(self):
        if hasattr(self, "power_panel"):
            self.close_power()
        self.setup_panel.place_forget()
        self.text.focus_set()
        self.schedule_preview()

    def icon(self, name, color=FG, pt=24):
        """A PhotoImage icon sized to sit beside text of `pt` points."""
        px = max(18, round(pt * 2.0 * self._s))
        key = (name, color, px)
        if key not in self._icon_cache:
            self._icon_cache[key] = ImageTk.PhotoImage(icons.icon_image(name, px, color))
        return self._icon_cache[key]

    def _refresh_toggles(self):
        for name, (t, var) in self._toggles.items():
            on = var.get()
            ic = {"Date": "calendar", "QR": "qr"}.get(name, "check")
            t.configure(text=" " + name, image=self.icon(ic, "#000000" if on else FG, 24),
                        compound="left",
                        fg="#000000" if on else FG,
                        activeforeground="#000000" if on else FG,
                        activebackground=OK if on else PANEL)

    def _refresh_brightness_buttons(self):
        for lv, b in getattr(self, "_bright_btns", {}).items():
            on = lv == self.brightness
            b.configure(bg=OK if on else PANEL, activebackground=OK if on else PANEL,
                        fg="#000000" if on else FG, activeforeground="#000000" if on else FG)

    def _bump_copies(self, delta: int):
        try:
            n = int(self.copies.get())
        except (tk.TclError, ValueError):
            n = 1
        self.copies.set(max(1, min(50, n + delta)))

    def _bind_keys(self):
        keys = {
            "<F1>": lambda e: self.toggle_recording(),
            "<F2>": lambda e: self.show_date.set(not self.show_date.get()),
            "<F3>": lambda e: self.show_qr.set(not self.show_qr.get()),
            "<F4>": lambda e: self.toggle_orientation(),
            "<F5>": lambda e: self.cycle_align(),
            "<Control-p>": lambda e: self.print_label(),
            "<Control-Return>": lambda e: self.print_label(),
            "<Escape>": lambda e: (self.close_setup() if self.setup_panel.winfo_ismapped()
                                   else self.clear()),
            "<Control-Q>": lambda e: self._quit_now(),     # Ctrl+Shift+Q
        }
        for seq, fn in keys.items():
            # Bind on the text box too, and stop Tk's built-in text bindings.
            for w in (self.root, self.text):
                w.bind(seq, lambda e, fn=fn: (fn(e), "break")[1])

    def set_status(self, msg: str, color: str = FG):
        self.status.configure(text=msg, fg=color)

    # ------------------------------------------------------------- preview
    def _text_changed(self, _e=None):
        if self.text.edit_modified():
            self.text.edit_modified(False)
            self.schedule_preview()

    def current_spec(self) -> LabelSpec:
        return LabelSpec(
            text=self.text.get("1.0", "end-1c"),
            show_date=self.show_date.get(),
            date_text=self.date_text.get().strip(),
            show_qr=self.show_qr.get(),
            qr_data=self.qr_text.get().strip(),
            orientation=self.orientation.get(),
            align=self.align.get(),
        )

    def schedule_preview(self):
        if self._preview_job:
            self.root.after_cancel(self._preview_job)
        self._preview_job = self.root.after(120, self.update_preview)

    def update_preview(self):
        self._preview_job = None
        try:
            img = render(self.current_spec())
        except Exception as e:  # noqa: BLE001
            self.set_status(f"Preview error: {e}", REC)
            return
        cw, ch = max(self.canvas.winfo_width(), 50), max(self.canvas.winfo_height(), 50)
        pad, gap = 14, 10
        scale = min((cw - 2 * pad - 2 * gap) / img.width, (ch - 2 * pad) / img.height)
        w, h = max(1, int(img.width * scale)), max(1, int(img.height * scale))
        shown = img.convert("L").resize((w, h), Image.LANCZOS)
        self._preview_photo = ImageTk.PhotoImage(shown)
        c = self.canvas
        c.delete("all")
        x0, y0 = (cw - w) // 2, (ch - h) // 2
        # Draw it as a label on a roll: the box is the backing paper, with the
        # neighbouring labels peeking in at the sides.
        for nx in (x0 - gap - w, x0 + w + gap):
            c.create_rectangle(nx, y0, nx + w, y0 + h, fill=LABEL_GHOST, outline="")
        c.create_image(x0, y0, image=self._preview_photo, anchor="nw")
        self.size_caption.configure(
            text='3 × 2 in' if self.orientation.get() == "landscape" else '2 × 3 in')
        # Placeholder in the text box when it's empty.
        if self.text.get("1.0", "end-1c").strip():
            self.placeholder.place_forget()
        else:
            self.placeholder.place(x=12, y=10)

    # ----------------------------------------------------------- recording
    def talk_press(self):
        """TALK went down (screen or physical button). A tap followed quickly by
        a press and hold clears the text and starts over."""
        now = time.monotonic()
        fresh = now - self._last_talk_tap <= getattr(config, "DOUBLE_TAP_SECONDS", 0.6)
        self._talk_down_at = now
        self._last_talk_tap = -10.0
        self.start_recording(fresh=fresh)

    def talk_release(self):
        held = time.monotonic() - self._talk_down_at
        if held < config.MIN_TALK_SECONDS:
            self.stop_recording(cancel=True)        # a tap: too short to be speech
            self._last_talk_tap = time.monotonic()
        else:
            self.stop_recording()

    def toggle_recording(self):
        self.stop_recording() if self.recording else self.start_recording()

    def start_recording(self, fresh: bool = False):
        if self.recording or self.busy:
            return
        if not self.stt.ready:
            self.set_status("Speech model is still loading…", MUTED)
            return
        # Keep the date current unless someone typed their own.
        if self.date_text.get() == self._auto_date:
            self._auto_date = today()
            self.date_text.set(self._auto_date)
        if fresh:
            self._set_text("")                     # start over: nothing to go back to
        self._status_before = (self.status.cget("text"), self.status.cget("fg"))
        self.recording = True
        self._before_recording = self.text.get("1.0", "end-1c")
        self.stt.begin()
        self.button.led_on()
        self.talk_btn.configure(bg=REC, activebackground=REC, text=" Listening…")
        self.set_status("Cleared. Listening… release to finish" if fresh
                        else "Listening… release to finish", REC)

    def stop_recording(self, cancel: bool = False):
        if not self.recording:
            return
        self.recording = False
        self.talk_btn.configure(bg=PANEL, activebackground=PANEL, text=" Hold to talk")
        if cancel:
            self.stt.cancel()
            self.button.led_off()
            self._set_text(self._before_recording)
            # Put back the message from before the tap, not "Listening…".
            text, color = getattr(self, "_status_before", ("", FG))
            if not text or text.startswith(("Listening", "Cleared")):
                text, color = self._idle_hint(), FG
            self.set_status(text, color)
            return
        self.busy = True
        self.button.led_on()                       # stays on until the words are in
        self.set_status("Transcribing…", MUTED)
        self.stt.end()

    def _set_text(self, value: str):
        self.text.delete("1.0", "end")
        self.text.insert("1.0", value)
        self.text.mark_set("insert", "end-1c")
        self.schedule_preview()

    @staticmethod
    def _tidy(spoken: str) -> str:
        """Speech recognition ends sentences with a period; labels don't want one."""
        spoken = spoken.strip()
        while spoken.endswith(".") and not spoken.endswith("..."):
            spoken = spoken[:-1].rstrip()
        return spoken

    def _merge(self, spoken: str) -> str:
        spoken = self._tidy(spoken)
        if config.RECORD_MODE == "append" and self._before_recording.strip():
            return f"{self._before_recording.rstrip()} {spoken}"
        return spoken

    # ------------------------------------------------------------ printing
    def _print_hold_start(self):
        """Called when PRINT is pressed. Return False to refuse the hold."""
        self._note_activity()
        if self.recording or self.busy:
            return False
        spec = self.current_spec()
        if not (spec.text.strip() or spec.show_qr or spec.show_date):
            self.set_status("Nothing to print yet", MUTED)
            return False
        self.print_hw.led_blink(fast=True)
        self.set_status("Keep holding to print…", ACCENT)
        return True

    def _print_hold_cancel(self):
        self.print_hw.led_off()
        self.set_status(f"Hold PRINT for {self.print_btn.seconds:g} seconds to print", MUTED)

    def print_label(self):
        if self.recording or self.busy:
            return
        spec = self.current_spec()
        if not (spec.text.strip() or spec.show_qr or spec.show_date):
            self.set_status("Nothing to print yet", MUTED)
            return
        try:
            copies = max(1, min(50, int(self.copies.get())))
        except (tk.TclError, ValueError):
            copies = 1
        self.busy = True
        self.print_hw.led_on()                     # stays on until the label is sent
        self.set_status("Printing…", MUTED)

        def work():
            try:
                img = render(spec)
                zpl = image_to_zpl(for_printer(img, spec.orientation), copies=copies)
                msg = printer.send(zpl, dry_run=self.dry_run, preview_png=img)
                self.events.put(("printed", f"{msg} ({copies} cop{'y' if copies == 1 else 'ies'})"))
            except Exception as e:  # noqa: BLE001
                self.events.put(("print_error", str(e)))

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------- screen blanking
    def _note_activity(self):
        self._last_activity = time.monotonic()

    def _display_power(self, on: bool):
        try:
            subprocess.run(["wlopm", "--on" if on else "--off", "*"],
                           timeout=5, capture_output=True)
        except Exception:  # noqa: BLE001 - not on a Wayland desktop
            pass

    # ------------------------------------------------------------ brightness
    SETTINGS_FILE = Path(__file__).with_name("settings.json")

    @staticmethod
    def _backlights() -> list:
        return sorted(glob.glob("/sys/class/backlight/*"))

    # With power-off protection on (kiosk/protect.sh), the main storage is
    # read-only and anything written to it is lost at restart, so settings are
    # also kept on the boot partition through a small root helper.
    BOOT_SETTINGS = Path("/boot/firmware/voicelabels-settings.json")
    SAVE_HELPER = "/usr/local/sbin/voicelabels-save-settings"

    def _load_settings(self) -> dict:
        for f in (self.BOOT_SETTINGS, self.SETTINGS_FILE):
            try:
                data = json.loads(f.read_text())
                if isinstance(data, dict):
                    return data
            except (OSError, ValueError):
                continue
        return {}

    def _save_settings(self, **changes):
        data = self._load_settings()
        data.update(changes)
        text = json.dumps(data, indent=2)
        tmp = self.SETTINGS_FILE.with_suffix(".tmp")
        try:                                   # write, flush to disk, then swap in
            with open(tmp, "w") as fh:
                fh.write(text)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.SETTINGS_FILE)
        except OSError:
            pass
        if os.path.exists(self.SAVE_HELPER):
            try:
                subprocess.run(["sudo", "-n", self.SAVE_HELPER], input=text.encode(),
                               timeout=10, capture_output=True)
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    def network_text() -> str:
        """'labelbox · 192.168.1.20', or a note when there's no network."""
        import socket
        host = socket.gethostname()
        ip = None
        try:                       # the address used to reach the network (sends nothing)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sk:
                sk.connect(("192.0.2.1", 9))
                ip = sk.getsockname()[0]
        except OSError:
            pass
        if not ip or ip.startswith("127."):
            try:
                ips = subprocess.run(["hostname", "-I"], capture_output=True, text=True,
                                     timeout=3).stdout.split()
                ip = next((a for a in ips if "." in a and not a.startswith("127.")), None)
            except Exception:  # noqa: BLE001
                ip = None
        return f"{host} · {ip}" if ip else f"{host} · no network"

    @staticmethod
    def protection_state() -> str:
        """'on' (safe to unplug), 'pending' (on after a restart), or 'off'."""
        try:
            now = "overlayroot=tmpfs" in Path("/proc/cmdline").read_text()
            conf = "overlayroot=tmpfs" in Path("/boot/firmware/cmdline.txt").read_text()
        except OSError:
            return "off"
        if now:
            return "on" if conf else "ending"
        return "pending" if conf else "off"

    def _apply_brightness(self):
        pct = max(1, min(100, int(self.brightness)))
        for dev in self._backlights():
            try:
                top = int(Path(dev, "max_brightness").read_text())
                Path(dev, "brightness").write_text(str(max(1, round(top * pct / 100))))
            except (OSError, ValueError):
                pass
        self._refresh_brightness_buttons()

    def set_brightness(self, level: int):
        self.brightness = int(level)
        self._apply_brightness()
        self._save_settings(brightness=self.brightness)

    def _check_idle(self):
        idle = time.monotonic() - self._last_activity
        if (self._blank_overlay is None and not self.recording and not self.busy
                and idle >= config.SCREEN_BLANK_SECONDS):
            self._blank()
        self.root.after(5000, self._check_idle)

    def _blank(self):
        # A black cover over the whole window catches the waking touch, so it
        # can't also press whatever button is underneath.
        cover = tk.Frame(self.root, bg="#000000", cursor="none")
        cover.place(relx=0, rely=0, relwidth=1, relheight=1)
        cover.lift()
        cover.bind("<ButtonPress>", lambda e: (self._wake(), "break")[1])
        self._blank_overlay = cover
        self._display_power(False)

    def _long_press_start(self, e):
        self._long_press_cancel()
        secs = getattr(config, "LONG_PRESS_BLANK_SECONDS", 0)
        if not secs or self.recording or self.busy:
            return
        self._lp_origin = (e.x_root, e.y_root)
        self._lp_status = (self.status.cget("text"), self.status.cget("fg"))
        self._lp_jobs = [
            self.root.after(int(min(0.6, secs / 2) * 1000),
                            lambda: self.set_status("Keep holding to turn the screen off", MUTED)),
            self.root.after(int(secs * 1000), self._long_press_fire),
        ]

    def _long_press_move(self, e):
        # Dragging (e.g. selecting text) is not a long press.
        if self._lp_origin and (abs(e.x_root - self._lp_origin[0]) > 15
                                or abs(e.y_root - self._lp_origin[1]) > 15):
            self._long_press_cancel()

    def _long_press_cancel(self, _e=None):
        jobs, self._lp_jobs = self._lp_jobs, []
        for job in jobs:
            self.root.after_cancel(job)
        if jobs and self._lp_status:
            self.set_status(*self._lp_status)       # put back the message it replaced
        self._lp_origin = self._lp_status = None

    def _long_press_fire(self):
        self._lp_jobs = []
        if self._lp_status:
            self.set_status(*self._lp_status)
        self._lp_origin = self._lp_status = None
        if self._blank_overlay is None and not self.recording and not self.busy:
            self._blank()

    def _wake(self):
        self._note_activity()
        if self._blank_overlay is not None:
            self._display_power(True)
            # The panel can come back at full brightness; put back the level
            # it had, now and again shortly after in case the driver resets it.
            self._apply_brightness()
            self.root.after(400, self._apply_brightness)
            self.root.after(1500, self._apply_brightness)
            self._blank_overlay.destroy()
            self._blank_overlay = None

    # --------------------------------------------------------------- misc
    def toggle_orientation(self):
        self.orientation.set("portrait" if self.orientation.get() == "landscape" else "landscape")

    def clear(self):
        if self.recording:
            self.stop_recording(cancel=True)
        self._set_text("")
        self.set_status("Hold the button and speak", FG)

    def _load_model(self):
        self.stt.load()
        if self.stt.ready:
            self.events.put(("ready", None))

    def _poll(self):
        try:
            while True:
                kind, val = self.events.get_nowait()
                self._handle(kind, val)
        except queue.Empty:
            pass
        self.root.after(50, self._poll)

    def _idle_hint(self) -> str:
        return ("Hold the button and speak" if self.button.available
                else "Hold the Talk button (or press F1) and speak")

    def _handle(self, kind, val):
        if kind == "ready":
            self.button.led_flash(2)                   # ready
            hint = "Hold the button and speak" if self.button.available else "Hold the Talk button (or press F1) and speak"
            if not self.stt.mic_name:
                self.set_status("Microphone not found. Plug in the USB mic.", REC)
                return
            self.set_status(hint, FG)
        elif kind == "progress":
            self.set_status(f"Initializing… {val:.0%}", MUTED)
        elif kind == "partial" and self.recording:
            self._set_text(self._merge(val))
        elif kind == "final":
            self.busy = False
            if val:
                self.button.led_flash(2)               # done
                self._set_text(self._merge(val))
                self.set_status("Edit if needed, then print", OK)
            else:
                self.button.led_off()
                self._set_text(self._before_recording)
                self.set_status("Didn't catch that. Try again", ACCENT)
        elif kind == "hw_press":
            self._wake()
            self.talk_press()
        elif kind == "hw_release":
            self._note_activity()
            self.talk_release()
        elif kind == "print_press":
            self._wake()
            self.print_btn.begin()
        elif kind == "print_release":
            self._note_activity()
            self.print_btn.end()
        elif kind == "printed":
            self.busy = False
            self.print_hw.led_flash(2)                 # done
            self.set_status(val, OK)
        elif kind == "print_error":
            self.busy = False
            self.button.led_off()
            self.print_hw.led_off()
            self.set_status(val, REC)
        elif kind == "error":
            self.busy = False
            self.recording = False
            self.button.led_off()
            self.set_status(val, REC)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="save labels to ./out instead of printing")
    ap.add_argument("--windowed", action="store_true", help="don't go fullscreen")
    ap.add_argument("--size", default="800x480",
                    help="window size with --windowed, e.g. 800x480 or 720x1280")
    args = ap.parse_args()

    root = tk.Tk()
    root.title("Voice Labels")
    if config.FULLSCREEN and not args.windowed:
        screen = (root.winfo_screenwidth(), root.winfo_screenheight())
        root.geometry(f"{screen[0]}x{screen[1]}+0+0")
        root.attributes("-fullscreen", True)
        root.configure(cursor="none")

        # Started from the desktop, the window manager sometimes ignores the
        # first fullscreen request (e.g. while a launch dialog has focus).
        # Check once the window is up and ask again if it isn't full size.
        def ensure_fullscreen(tries):
            if not root.winfo_ismapped():
                root.after(300, ensure_fullscreen, tries)
                return
            if root.winfo_width() < screen[0] - 2 or root.winfo_height() < screen[1] - 2:
                root.attributes("-fullscreen", False)
                root.after(50, lambda: (root.attributes("-fullscreen", True),
                                        root.lift(), root.focus_force()))
            if tries > 1:
                root.after(1500, ensure_fullscreen, tries - 1)
        root.after(500, ensure_fullscreen, 4)
    else:
        w, h = (int(v) for v in args.size.lower().split("x"))
        screen = (w, h)
        root.geometry(f"{w}x{h}")
    app = App(root, dry_run=args.dry_run, screen=screen)
    if os.environ.get("LABELBOX_SHOW_SETUP"):      # for screenshots while testing
        root.after(300, app.open_setup)
    if os.environ.get("LABELBOX_SHOW_POWER"):
        root.after(400, lambda: (app.open_setup(), app.open_power()))
    if os.environ.get("LABELBOX_TEXT"):            # pre-filled label, for screenshots
        root.after(300, lambda: app._set_text(os.environ["LABELBOX_TEXT"]))
    try:
        root.mainloop()
    finally:
        app.stt.close()


if __name__ == "__main__":
    main()
