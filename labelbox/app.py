"""Voice label printer: hold the button, speak, edit, see the label, print.

    python3 app.py              # normal (fullscreen, prints to the Zebra)
    python3 app.py --dry-run    # saves labels to ./out instead of printing
    python3 app.py --windowed   # not fullscreen (handy when testing)

Keys: F1 talk (press to start, press again to stop)   F2 date on/off
      F3 QR on/off   F4 landscape/portrait   Ctrl+P or Ctrl+Enter print
      Esc clear text   Ctrl+Shift+Q quit
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


class HoldButton(tk.Canvas):
    """A button that must be held for `seconds` before it fires.

    While held, a green bar sweeps across it and the label counts down.
    Letting go early cancels. begin()/end() can also be driven by a
    physical button.
    """

    def __init__(self, master, text, font, seconds, on_fire, on_start=None,
                 on_cancel=None, bg=ACCENT, fill=OK, fg="#000000"):
        super().__init__(master, highlightthickness=0, bd=0, bg=bg, height=1, cursor="hand2")
        self.text, self.font, self.seconds = text, font, seconds
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
        self.create_text(w // 2, h // 2, text=label or self.text, font=self.font, fill=self.fg)

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
        self.copies = tk.IntVar(value=1)

        self._build_ui()
        self._bind_keys()
        saved = self._load_settings()
        self.brightness = int(saved.get("brightness", 100))
        self.print_btn.seconds = float(saved.get("print_hold", config.PRINT_HOLD_SECONDS))
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

        self.set_status("Loading speech model…", MUTED)
        self.button.led_blink()
        threading.Thread(target=self._load_model, daemon=True).start()

        for var in (self.show_date, self.show_qr, self.date_text, self.qr_text, self.orientation):
            var.trace_add("write", lambda *_: self.schedule_preview())
        self.root.after(50, self._poll)
        self.schedule_preview()

        # Screen blanking: any touch, click or key counts as activity.
        self._last_activity = time.monotonic()
        self._blank_overlay = None
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
        self.talk_btn = tk.Button(body, text="● Hold to talk", bg=PANEL, fg=FG,
                                  activebackground=PANEL, activeforeground=FG, **big)
        self.talk_btn.grid(row=0, column=0, sticky="nsew", padx=(0, pad), pady=(0, gap))
        self.talk_btn.bind("<ButtonPress-1>", lambda e: self.start_recording())
        self.talk_btn.bind("<ButtonRelease-1>", lambda e: self.stop_recording())
        self.print_btn = HoldButton(body, "PRINT", font(30, True), config.PRINT_HOLD_SECONDS,
                                    on_fire=self.print_label, on_start=self._print_hold_start,
                                    on_cancel=self._print_hold_cancel)
        self.print_btn.grid(row=0, column=1, sticky="nsew", pady=(0, gap))

        # Rows below the top buttons: captions, the two boxes (same height),
        # then the status message beside Rotate / Clear / Setup.
        body.rowconfigure(1, weight=0)
        body.rowconfigure(2, weight=1)
        cap_font, cap_bold = font(15), font(15, True)

        cap = tk.Frame(body, bg=BG)
        cap.grid(row=1, column=0, sticky="ew", padx=(0, pad))
        tk.Label(cap, text="LABEL PREVIEW", bg=BG, fg=MUTED, font=cap_bold,
                 anchor="w").pack(side="left")
        self.size_caption = tk.Label(cap, text="", bg=BG, fg=MUTED, font=cap_font, anchor="e")
        self.size_caption.pack(side="right")
        tcap = tk.Frame(body, bg=BG)
        tcap.grid(row=1, column=1, sticky="ew")
        tk.Label(tcap, text="TEXT", bg=BG, fg=MUTED, font=cap_bold,
                 anchor="w").pack(side="left")
        tk.Label(tcap, text="type here to edit", bg=BG, fg=MUTED, font=cap_font,
                 anchor="e").pack(side="right")

        # Left box: the label drawn on its backing paper.
        self.canvas = tk.Canvas(body, bg=LINER, width=1, height=1, highlightthickness=2,
                                highlightbackground=INPUT_EDGE)
        self.canvas.grid(row=2, column=0, sticky="nsew", padx=(0, pad))
        self.canvas.bind("<Configure>", lambda e: self.schedule_preview())

        # Right box: a dark input, so it can't be mistaken for the white label.
        self.text = tk.Text(body, width=1, height=1, wrap="word", font=font(22),
                            bg=INPUT_BG, fg=FG, insertbackground=FG, insertwidth=3,
                            undo=True, relief="flat", padx=10, pady=8,
                            highlightthickness=2, highlightbackground=INPUT_EDGE,
                            highlightcolor=ACCENT, selectbackground=ACCENT,
                            selectforeground="#000000")
        self.text.grid(row=2, column=1, sticky="nsew")
        self.text.bind("<<Modified>>", self._text_changed)
        self.placeholder = tk.Label(self.text, text="Hold to talk, or type the label text",
                                    bg=INPUT_BG, fg=MUTED, font=font(19), anchor="nw",
                                    justify="left", wraplength=1)
        self.placeholder.bind("<Button-1>", lambda e: self.text.focus_set())
        self.text.bind("<Configure>", lambda e: self.placeholder.configure(
            wraplength=max(50, e.width - 30)))

        # Bottom row: status message (left), Rotate / Clear / Setup (right).
        self.status = tk.Label(body, text="", bg=BG, fg=FG, font=font(22, True),
                               anchor="w", justify="left")
        self.status.grid(row=3, column=0, sticky="ew", padx=(0, pad), pady=(gap, 0))
        self.canvas.bind("<Configure>", lambda e: (
            self.status.configure(wraplength=max(100, e.width - 4)), self.schedule_preview()),
            add="")
        row = tk.Frame(body, bg=BG)
        row.grid(row=3, column=1, sticky="ew", pady=(gap, 0))
        btn = dict(font=font(20, True), relief="flat", bd=0, highlightthickness=0,
                   pady=round(18 * s), bg=PANEL, fg=FG, activebackground=PANEL,
                   activeforeground=FG, cursor="hand2")
        for col, (label, cmd) in enumerate([("⟳ Rotate", self.toggle_orientation),
                                            ("Clear", self.clear),
                                            ("⚙ Setup", self.open_setup)]):
            row.columnconfigure(col, weight=1, uniform="b")
            tk.Button(row, text=label, command=cmd, **btn).grid(
                row=0, column=col, sticky="nsew", padx=(0 if col == 0 else gap, 0))

        self._build_setup()
        self.text.focus_set()

    # --------------------------------------------------------------- setup
    def _build_setup(self):
        """A full-window panel, hidden until ⚙ Setup is tapped."""
        s, font, gap = self._s, self._font, self._gap
        pad = max(8, round(18 * s))
        p = tk.Frame(self.root, bg=BG)
        self.setup_panel = p
        p.columnconfigure(1, weight=1)
        for r_ in (1, 2, 4, 5):                 # button rows share the spare height
            p.rowconfigure(r_, weight=1, uniform="rows")

        big = dict(font=font(24, True), relief="flat", bd=0, highlightthickness=0,
                   pady=round(20 * s), cursor="hand2", bg=PANEL, fg=FG,
                   activebackground=PANEL, activeforeground=FG)
        label = dict(bg=BG, fg=MUTED, font=font(20, True), anchor="w")
        entry = dict(font=font(24), relief="flat")

        tk.Label(p, text="Setup", bg=BG, fg=FG, font=font(30, True), anchor="w").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=pad, pady=(pad, gap))
        top = tk.Frame(p, bg=BG)
        top.grid(row=0, column=1, sticky="e", padx=pad, pady=(pad, gap))
        self.exit_btn = tk.Button(top, text="Exit to desktop", command=self.exit_to_desktop,
                                  **dict(big, padx=round(24 * s)))
        self.exit_btn.pack(side="left", padx=(0, gap))
        tk.Button(top, text="Done", command=self.close_setup,
                  **dict(big, bg=ACCENT, fg="#000000", activebackground="#ffd36b",
                         activeforeground="#000000", padx=round(40 * s))).pack(side="left")

        # Date and QR: a big on/off button plus the text to print.
        self._toggles = {}
        for r_, (name, var, text_var) in enumerate(
                [("Date", self.show_date, self.date_text), ("QR", self.show_qr, self.qr_text)],
                start=1):
            t = tk.Checkbutton(p, text=name, variable=var, indicatoron=False,
                               offrelief="flat", selectcolor=OK, width=7, **big)
            t.grid(row=r_, column=0, sticky="nsew", padx=(pad, gap), pady=(0, gap))
            tk.Entry(p, textvariable=text_var, **entry).grid(
                row=r_, column=1, sticky="nsew", padx=(0, pad), pady=(0, gap))
            self._toggles[name] = (t, var)
            var.trace_add("write", lambda *_: self._refresh_toggles())
        tk.Label(p, text="QR text: leave blank to use the label text", bg=BG, fg=MUTED,
                 font=font(15), anchor="w").grid(row=3, column=1, sticky="w",
                                                 padx=(0, pad), pady=(0, gap))

        # Copies: − n +
        tk.Label(p, text="Copies", **label).grid(row=4, column=0, sticky="w",
                                                padx=(pad, gap), pady=(0, gap))
        cp = tk.Frame(p, bg=BG)
        cp.grid(row=4, column=1, sticky="nsw", padx=(0, pad), pady=(0, gap))
        step = dict(big, padx=round(34 * s))
        tk.Button(cp, text="−", command=lambda: self._bump_copies(-1), **step).pack(side="left", fill="y")
        tk.Label(cp, textvariable=self.copies, bg=BG, fg=FG, width=3,
                 font=font(30, True)).pack(side="left")
        tk.Button(cp, text="+", command=lambda: self._bump_copies(1), **step).pack(side="left", fill="y")

        # Brightness: one button per level, the current one highlighted.
        tk.Label(p, text="Brightness", **label).grid(row=5, column=0, sticky="w",
                                                    padx=(pad, gap), pady=(0, gap))
        br = tk.Frame(p, bg=BG)
        br.grid(row=5, column=1, sticky="nsew", padx=(0, pad), pady=(0, gap))
        br.rowconfigure(0, weight=1)
        self._bright_btns = {}
        for i, lv in enumerate(sorted(config.BRIGHTNESS_LEVELS) or [100]):
            br.columnconfigure(i, weight=1, uniform="br")
            b = tk.Button(br, text=f"{lv}%", command=lambda lv=lv: self.set_brightness(lv), **big)
            b.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else gap, 0))
            self._bright_btns[lv] = b
        # Print hold: how long PRINT must be held.
        p.rowconfigure(6, weight=1, uniform="rows")
        tk.Label(p, text="Print hold", **label).grid(row=6, column=0, sticky="w",
                                                    padx=(pad, gap), pady=(0, pad))
        ph = tk.Frame(p, bg=BG)
        ph.grid(row=6, column=1, sticky="nsew", padx=(0, pad), pady=(0, pad))
        ph.rowconfigure(0, weight=1)
        self._hold_btns = {}
        for i, sec in enumerate(config.PRINT_HOLD_CHOICES):
            ph.columnconfigure(i, weight=1, uniform="ph")
            b = tk.Button(ph, text="Off" if sec == 0 else f"{sec:g} s",
                          command=lambda sec=sec: self.set_print_hold(sec), **big)
            b.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else gap, 0))
            self._hold_btns[sec] = b
        self._refresh_toggles()

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

    def exit_to_desktop(self):
        """First tap arms the button; a second tap within 4 s leaves the app."""
        if not getattr(self, "_exit_armed", False):
            self._exit_armed = True
            self.exit_btn.configure(text="Tap again to exit", bg=REC, activebackground=REC,
                                    fg="#ffffff", activeforeground="#ffffff")
            self.root.after(4000, self._disarm_exit)
            return
        self._disarm_exit()
        if os.environ.get("LABELBOX_KIOSK"):
            # Starting the desktop stops the kiosk service (they conflict).
            r = subprocess.run(["systemctl", "--no-block", "start", "lightdm.service"],
                               capture_output=True, text=True)
            if r.returncode != 0:
                self.close_setup()
                self.set_status("Couldn't start the desktop: "
                                + (r.stderr.strip() or "systemctl failed"), REC)
        else:
            self.root.destroy()                         # running on the desktop already

    def _quit_now(self):
        """Ctrl+Shift+Q: go straight to the desktop (or quit if already there)."""
        self._exit_armed = True
        self.exit_to_desktop()

    def _disarm_exit(self):
        self._exit_armed = False
        self.exit_btn.configure(text="Exit to desktop", bg=PANEL, activebackground=PANEL,
                                fg=FG, activeforeground=FG)

    def close_setup(self):
        self.setup_panel.place_forget()
        self.text.focus_set()
        self.schedule_preview()

    def _refresh_toggles(self):
        for name, (t, var) in self._toggles.items():
            on = var.get()
            t.configure(text=("✓ " if on else "") + name,
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
    def toggle_recording(self):
        self.stop_recording() if self.recording else self.start_recording()

    def start_recording(self):
        if self.recording or self.busy:
            return
        if not self.stt.ready:
            self.set_status("Speech model is still loading…", MUTED)
            return
        # Keep the date current unless someone typed their own.
        if self.date_text.get() == self._auto_date:
            self._auto_date = today()
            self.date_text.set(self._auto_date)
        self.recording = True
        self._before_recording = self.text.get("1.0", "end-1c")
        self.stt.begin()
        self.button.led_on()
        self.talk_btn.configure(bg=REC, activebackground=REC, text="● Listening…")
        self.set_status("Listening… release to finish", REC)

    def stop_recording(self, cancel: bool = False):
        if not self.recording:
            return
        self.recording = False
        self.talk_btn.configure(bg=PANEL, activebackground=PANEL, text="● Hold to talk")
        if cancel:
            self.stt.cancel()
            self.button.led_off()
            self._set_text(self._before_recording)
            return
        self.busy = True
        self.button.led_blink()
        self.set_status("Transcribing…", MUTED)
        self.stt.end()

    def _set_text(self, value: str):
        self.text.delete("1.0", "end")
        self.text.insert("1.0", value)
        self.text.mark_set("insert", "end-1c")
        self.schedule_preview()

    def _merge(self, spoken: str) -> str:
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
        self.button.led_blink()
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

    def _load_settings(self) -> dict:
        try:
            return json.loads(self.SETTINGS_FILE.read_text())
        except (OSError, ValueError):
            return {}

    def _save_settings(self, **changes):
        data = self._load_settings()
        data.update(changes)
        try:
            self.SETTINGS_FILE.write_text(json.dumps(data, indent=2))
        except OSError:
            pass

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

    def _handle(self, kind, val):
        if kind == "ready":
            self.button.led_off()
            hint = "Hold the button and speak" if self.button.available else "Hold the Talk button (or press F1) and speak"
            if not self.stt.mic_name:
                self.set_status("Microphone not found. Plug in the USB mic.", REC)
                return
            self.set_status(hint, FG)
        elif kind == "progress":
            self.set_status(f"Downloading speech model… {val:.0%}", MUTED)
        elif kind == "partial" and self.recording:
            self._set_text(self._merge(val))
        elif kind == "final":
            self.busy = False
            self.button.led_off()
            if val:
                self._set_text(self._merge(val))
                self.set_status("Edit if needed, then print", OK)
            else:
                self._set_text(self._before_recording)
                self.set_status("Didn't catch that. Try again", ACCENT)
        elif kind == "hw_press":
            self._wake()
            self.start_recording()
        elif kind == "hw_release":
            self._note_activity()
            if val < config.MIN_TALK_SECONDS:
                self.stop_recording(cancel=True)        # too short to be speech
            else:
                self.stop_recording()
        elif kind == "print_press":
            self._wake()
            self.print_btn.begin()
        elif kind == "print_release":
            self._note_activity()
            self.print_btn.end()
        elif kind == "printed":
            self.busy = False
            self.button.led_off()
            self.print_hw.led_off()
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
        root.attributes("-fullscreen", True)
        root.configure(cursor="none")
    else:
        w, h = (int(v) for v in args.size.lower().split("x"))
        screen = (w, h)
        root.geometry(f"{w}x{h}")
    app = App(root, dry_run=args.dry_run, screen=screen)
    if os.environ.get("LABELBOX_SHOW_SETUP"):      # for screenshots while testing
        root.after(300, app.open_setup)
    if os.environ.get("LABELBOX_TEXT"):            # pre-filled label, for screenshots
        root.after(300, lambda: app._set_text(os.environ["LABELBOX_TEXT"]))
    try:
        root.mainloop()
    finally:
        app.stt.close()


if __name__ == "__main__":
    main()
