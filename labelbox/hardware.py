"""A physical push button with an optional built-in light.

on_press() runs the instant the button goes down; on_release(seconds_held)
runs when it comes back up. If there is no GPIO (e.g. testing on a laptop)
this quietly does nothing and the on-screen controls still work.
"""

from __future__ import annotations

import time


class Button:
    def __init__(self, pin, led_pin, on_press, on_release):
        self.on_press = on_press
        self.on_release = on_release
        self.available = False
        self._down_at = None
        self._led = None
        if pin is None:
            return
        try:
            from gpiozero import Button as GpioButton, LED

            self._btn = GpioButton(pin, pull_up=True, bounce_time=0.03)
            self._btn.when_pressed = self._pressed
            self._btn.when_released = self._released
            if led_pin is not None:
                self._led = LED(led_pin)
            self.available = True
        except Exception:  # noqa: BLE001 - no GPIO on this machine
            pass

    def _pressed(self):
        self._down_at = time.monotonic()
        self.on_press()

    def _released(self):
        if self._down_at is None:
            return
        held = time.monotonic() - self._down_at
        self._down_at = None
        self.on_release(held)

    # Light states: on, off, blink (slow or fast)
    def led_on(self):
        if self._led:
            self._led.on()

    def led_off(self):
        if self._led:
            self._led.off()

    def led_blink(self, fast: bool = False):
        if self._led:
            t = 0.07 if fast else 0.15
            self._led.blink(on_time=t, off_time=t)
