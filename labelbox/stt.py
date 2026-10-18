"""Push-to-talk speech recognition with Moonshine (runs fully offline).

Usage:
    stt = PushToTalk(on_partial=..., on_final=..., on_error=...)
    stt.load()      # first run downloads the model (~needs internet once)
    stt.begin()     # button pressed
    stt.end()       # button released -> on_final(text) is called

Callbacks run on background threads; the UI hands them to its own thread.

Run `python3 stt.py` on the Pi to test the microphone by itself.
"""

from __future__ import annotations

import re
import threading
import time

import config


class PushToTalk:
    def __init__(self, on_partial=None, on_final=None, on_error=None, on_progress=None):
        self.on_partial = on_partial or (lambda text: None)
        self.on_final = on_final or (lambda text: None)
        self.on_error = on_error or (lambda msg: None)
        self.on_progress = on_progress
        self._mic = None
        self._lock = threading.Lock()
        self._lines: list[str] = []
        self._partial = ""
        self._listening = False
        self.ready = False
        self.mic_name = None

    # -- model -------------------------------------------------------------
    def load(self):
        try:
            from moonshine_voice import MicTranscriber
        except ImportError:
            self.on_error("moonshine-voice is not installed (see README step 4)")
            return
        try:
            mic = MicTranscriber().language(config.LANGUAGE)
            if self.on_progress:
                mic = mic.on_progress(self.on_progress)
            mic = mic.on_text(self._handle_text).on_line(self._handle_line)
            mic.load()   # downloads the English medium-streaming model on first run
            terms = [t for t in getattr(config, "KEYTERMS", []) if t and "," not in t]
            if terms:
                mic.set_keyterms(terms)
            self._mic = mic
            self.ready = True
            self.mic_name = self._pick_mic()
        except Exception as e:  # noqa: BLE001 - show any failure on screen
            self.on_error(f"Speech model failed to load: {e}")

    # -- microphone --------------------------------------------------------
    def _pick_mic(self, rescan: bool = False):
        """Point the transcriber at the input whose name contains MIC_NAME.

        Matching by name (not number) means it keeps working if the mic is
        moved to another USB port. Returns the device name, or None.
        """
        import sounddevice as sd
        if rescan:
            try:
                sd._terminate()
                sd._initialize()
            except Exception:  # noqa: BLE001
                pass
        want = getattr(config, "MIC_NAME", "USB").lower()
        for dev in sd.query_devices():
            if dev["max_input_channels"] > 0 and want in dev["name"].lower():
                name = dev["name"].split(" (hw:")[0]   # drop the card number
                m = re.search(r"\(hw:(\d+),", dev["name"])
                self._card = int(m.group(1)) if m else None
                self._mic.device(name)
                return name
        self._card = None
        self._mic.device(None)                         # fall back to the default input
        return None

    def _mic_still_there(self) -> bool:
        """True if the sound card we opened is still present (cheap check)."""
        if getattr(self, "_card", None) is None:
            return False
        try:
            with open("/proc/asound/cards") as f:
                cards = f.read()
        except OSError:
            return True                                # can't tell; assume fine
        for line in cards.splitlines():
            m = re.match(r"\s*(\d+)\s", line)
            if m and int(m.group(1)) == self._card:
                return True
        return False

    def _reopen_mic(self):
        """Forget the old audio stream and find the mic again (moved or replugged)."""
        stream = getattr(self._mic, "_sd_stream", None)
        if stream is not None:
            try:
                stream.close()
            except Exception:  # noqa: BLE001
                pass
            self._mic._sd_stream = None
        self.mic_name = self._pick_mic(rescan=True)

    # -- callbacks from Moonshine -----------------------------------------
    def _handle_text(self, text):
        with self._lock:
            if not self._listening:
                return
            self._partial = text or ""
            preview = " ".join(self._lines + [self._partial]).strip()
        self.on_partial(preview)

    def _handle_line(self, line):
        text = getattr(line, "text", line) or ""
        with self._lock:
            if text.strip():
                self._lines.append(text.strip())
            self._partial = ""

    # -- push to talk ------------------------------------------------------
    def begin(self):
        if not self.ready or self._listening:
            return
        with self._lock:
            self._lines, self._partial = [], ""
            self._listening = True
        if not self._mic_still_there():
            self._reopen_mic()
            if self.mic_name is None:
                self._listening = False
                self.on_error("Microphone not found. Is it plugged in?")
                return
        try:
            self._mic.start()
        except Exception:  # noqa: BLE001 - mic moved or unplugged: look again
            try:
                self._reopen_mic()
                if self.mic_name is None:
                    raise RuntimeError("Microphone not found. Is it plugged in?")
                self._mic.start()
            except Exception as e:  # noqa: BLE001
                self._listening = False
                self.on_error(str(e) if "not found" in str(e) else f"Microphone error: {e}")

    def end(self):
        if not self._listening:
            return
        threading.Thread(target=self._finish, daemon=True).start()

    def cancel(self):
        """Stop listening and throw the audio away (used for a quick tap)."""
        if not self._listening:
            return
        with self._lock:
            self._listening = False
        threading.Thread(target=self._stop_quietly, daemon=True).start()

    def _stop_quietly(self):
        try:
            self._mic.stop()
        except Exception:  # noqa: BLE001
            pass

    def _finish(self):
        time.sleep(config.TAIL_SECONDS)       # catch the end of the last word
        try:
            self._mic.stop()                  # completes any line still open
        except Exception as e:  # noqa: BLE001
            self.on_error(f"Microphone error: {e}")
        time.sleep(0.15)                      # let the final line callback land
        with self._lock:
            self._listening = False
            parts = self._lines + ([self._partial] if self._partial.strip() else [])
        self.on_final(_tidy(" ".join(parts)))

    def close(self):
        if self._mic is not None:
            try:
                self._mic.close()
            except Exception:  # noqa: BLE001
                pass


_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fourteen": 14,
    "sixteen": 16, "eighteen": 18, "twenty": 20, "twenty-four": 24, "thirty": 30,
}
# "M three" / "M-3" / "m 3" -> "M3" (metric screw sizes)
_METRIC = re.compile(r"\b[Mm][\s-]+(\d{1,2}|" + "|".join(
    sorted(_NUMBER_WORDS, key=len, reverse=True)) + r")\b", re.IGNORECASE)


def _tidy(text: str) -> str:
    text = " ".join(text.split())
    text = _METRIC.sub(
        lambda m: "M" + str(_NUMBER_WORDS.get(m.group(1).lower(), m.group(1))), text)
    return text[:1].upper() + text[1:] if text else text


if __name__ == "__main__":
    import sys
    if "--list" in sys.argv:
        import sounddevice as sd
        for i, dev in enumerate(sd.query_devices()):
            if dev["max_input_channels"] > 0:
                print(f"{i}: {dev['name']}")
        raise SystemExit
    done = threading.Event()
    stt = PushToTalk(
        on_partial=lambda t: print(f"\r… {t}", end="", flush=True),
        on_final=lambda t: (print(f"\nFINAL: {t!r}"), done.set()),
        on_error=lambda m: print(f"\nERROR: {m}"),
    )
    print("Loading model…")
    stt.load()
    while stt.ready:
        input("\nPress Enter, speak, then press Enter again (Ctrl+C quits). ")
        done.clear()
        stt.begin()
        input()
        stt.end()
        done.wait(10)
