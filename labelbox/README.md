# Voice Labels

A stand-alone voice-to-label printer. Hold the button, say what the label should say, fix any words on the keyboard, check the preview, and print a 2×3" label. Speech recognition runs entirely on the Pi, so there are no fees and no internet needed after setup.

```
 hold button → speak → release → text appears → edit → preview updates → PRINT
```

## What's on a label

Each label has three parts, and the screen preview is the exact image that gets printed:

- **Text**: the spoken words, sized automatically to the largest font that fits.
- **Date** (optional): today's date by default; you can type any date or note in its place.
- **QR code** (optional): encodes the label text, or anything you type in the QR field (a URL, part number, etc.).

Labels can be **landscape** (3" wide, the default) or **portrait** (2" wide). Tap **Rotate** or press F4 to switch.

## Parts

| Part | Notes |
|---|---|
| Raspberry Pi 5, 4GB | 2GB may work but leaves little headroom for the speech model |
| Official 27W USB-C power supply, Active Cooler | |
| 32GB microSD card | |
| Hosyond 7" DSI touchscreen, 800×480 | Ribbon cable to the DSI port, power from the GPIO header (see Display setup). The app also works on the official 5" Touch Display 2 |
| Compact USB or Bluetooth keyboard | Function keys F1–F4 are handy but optional |
| C G CHANGEEK CGS-M1 gooseneck USB microphone | Works with no driver. Bend the gooseneck toward the speaker (see Microphone setup) |
| Two 30 mm arcade buttons with LEDs (TALK and PRINT) | EG Starts 5V type. The case deck has 30.4 mm holes |
| 3D-printed case | See `case/README.md` |
| Zebra GK420d or GC420d, USB | Used; must be the "d" (direct thermal) model or set up for direct thermal |
| 2"×3" direct-thermal die-cut labels | 1" core fits these printers |

## Wiring the buttons

Use the Pi's 40-pin header (physical pin numbers). TALK is the left button on the case deck, PRINT the right.

| Wire | Pi pin |
|---|---|
| TALK switch, one leg | Pin 11 (GPIO17) |
| TALK switch, other leg | Pin 9 (GND) |
| TALK light + | Pin 13 (GPIO27) |
| TALK light − | Pin 14 (GND) |
| PRINT switch, one leg | Pin 15 (GPIO22) |
| PRINT switch, other leg | Pin 20 (GND) |
| PRINT light + | Pin 16 (GPIO23) |
| PRINT light − | Pin 25 (GND) |

No resistor is needed on the switches; the Pi's internal pull-ups are used. The EG Starts buttons have a resistor built into the light, which glows a little dimmer from the Pi's 3.3 V pins than at 5 V. If a light doesn't come on at all, set its `_LED_PIN` to `None` in `config.py`. The display's power leads also go on the header (5V and GND); the pins above stay free.

## Display setup (Hosyond 7" DSI)

1. With the Pi off, connect the ribbon cable to the display and to one of the Pi 5's two small camera/display connectors. The Pi 5 needs the narrow 22-pin end; check that the box includes a 22-pin-to-15-pin cable.
2. Connect the display's power leads to a 5V pin (pin 2 or 4) and a GND pin (pin 6). This leaves the button pins (9, 11, 13, 14) free.
3. Boot. On a fresh Raspberry Pi OS the screen should come up by itself. If it stays black with the backlight on, add this line to the end of `/boot/firmware/config.txt` and reboot:
   ```
   dtoverlay=vc4-kms-dsi-7inch
   ```
   If you used the second connector, add `,dsi0` to the end of that line.

The screen is landscape (800×480). The app detects this and puts the text box on the left and the label preview on the right. On a tall screen it stacks them instead.

## Microphone setup (gooseneck USB mic)

The mic works out of the box on the Pi. Distance matters more than anything else for accuracy: quiet or distant audio is the main cause of wrong words.

- **Placement:** in the printed case, the mic plugs straight into the Pi through the opening in the right side wall. Bend the gooseneck toward where people stand, within about 30 cm (1 ft) of their mouth.
- **Mute button:** the mic has its own mute. If every recording comes back as "Didn't catch that," check that it isn't muted.
- **Noise:** the mic picks up sound from all sides, so keep it away from fans. The printer only runs after recording, so it won't interfere.
- **Gain:** open a terminal, run `alsamixer`, press F6 to choose the USB mic, press F4 for capture controls, and raise the Mic level to about 80–90%. Run `sudo alsactl store` to keep the setting after reboots.
- **Check it:** run `.venv/bin/python stt.py` and speak a few test labels at normal volume from where users will stand. If words are often wrong, move the mic closer before changing anything else.

## Setting up the printer

1. Load the 2×3" label roll and adjust the guides to the 2" width. For a 4" printer, center the roll.
2. **Calibrate**: with the printer on, hold the feed button until the status light flashes twice, then let go. The printer feeds a few labels and learns where the gaps are. Do this again whenever you change label sizes.
3. Plug the printer into the Pi by USB. It shows up as `/dev/usb/lp0`, and the app writes to it directly, with no driver needed.

If you would rather use CUPS (for example, to also print from other computers), create a raw queue and put its name in `CUPS_QUEUE` in `config.py`.

## Installing the software

1. Flash **Raspberry Pi OS (64-bit, with desktop)** with Raspberry Pi Imager. Set the Wi-Fi network, username and SSH in the Imager settings.
2. Connect the display as described in Display setup.
3. Copy the `labelbox` folder to the Pi, for example to `/home/<you>/labelbox`.
4. Run the installer while the Pi is online. It installs packages, downloads the speech model (one time), gives your user access to the printer and GPIO, and sets the Pi to boot straight into the app (kiosk mode, below):
   ```
   cd ~/labelbox
   bash install.sh
   sudo reboot
   ```

After the reboot, the app opens fullscreen.

### Kiosk mode

The Pi boots straight into Voice Labels with no desktop behind it. If the app crashes or closes, it restarts within a couple of seconds.

- **To get to the desktop:** open **⚙ Setup**, tap **Power**, then tap **Desktop** twice, or press **Ctrl+Shift+Q**.
- **To go back to the app:** tap the **Voice Labels button in the taskbar**, or double-click the **Voice Labels** icon on the desktop (it's also in the menu), or reboot. These buttons work without kiosk mode too; to add them on their own, run `bash kiosk/launchers.sh` (no sudo).
- **To turn kiosk mode off** (boot to the desktop and start the app there instead): `sudo bash kiosk/uninstall-kiosk.sh`. To turn it back on: `sudo bash kiosk/install-kiosk.sh`.

Logs: `journalctl -u labelbox -f`.

### Boot logo

From power-on, the screen shows the Voice Labels logo instead of the Raspberry Pi splash, with no boot text, and the logo stays up until the app appears. `install-kiosk.sh` sets this up. To set it up on its own: `sudo bash kiosk/install-splash.sh`, then reboot. To get the Raspberry Pi splash back: `sudo plymouth-set-default-theme -R pix`.

`kiosk/launchers.sh` also makes the logo the desktop wallpaper.

### Power-off protection (safe to unplug)

Normally a Pi should be shut down before its power is cut, or the SD card can be damaged. Protection removes that risk: the SD card's main partition becomes read-only and every change is kept in memory instead, so you can unplug it at any moment. Your settings (brightness, print hold) are saved to the boot partition, so they still survive restarts.

```
sudo bash kiosk/protect.sh on       # then: sudo reboot
sudo bash kiosk/protect.sh off      # then: sudo reboot
bash kiosk/protect.sh status
```

The top of the Setup screen shows whether it's safe to unplug.

While protection is on, anything else you change is lost at the next restart: app updates, installed packages, files in your home folder. To update, turn protection off, restart, make the changes, then turn it back on. Set up everything else (kiosk mode, the boot logo) before turning protection on.

## Using it

| Main screen | Setup screen |
|---|---|
| <img src="docs/screen.png?v=3" alt="Main screen" width="400"> | <img src="docs/setup.png?v=2" alt="Setup screen" width="400"> |

The main screen has **Hold to talk** (top left) and **PRINT** (top right). Under them, the dark **text box** on the left is where you edit the words, and the **label preview** on the right shows the label exactly as it will print, drawn on its backing paper. The status message sits under the text box, and **Rotate**, **Clear** and **Setup** sit under the preview. Every button has an icon beside its label.

| Do this | To |
|---|---|
| **Hold** the TALK button (or **Hold to talk** on screen), speak, release | Record. The TALK light stays on while it listens and works out the words, then blinks twice when the text is in (it also blinks twice when the app is ready at startup). F1 starts and stops recording from the keyboard |
| **Tap** TALK, then straight away **press and hold** it again (screen or deck button), speak, release | Clear the text and start over. The status says "Cleared. Listening…" |
| Type in the text box | Fix any words. The preview updates as you type |
| **Hold** the PRINT button (on screen or on the deck) for 3 seconds | Print. A green bar sweeps across PRINT and counts down; let go early to cancel. The PRINT light blinks while you hold, stays on while printing, then blinks twice when done. Ctrl+P or Ctrl+Enter print straight away |
| Tap **⟳ Rotate**, or press F4 | Switch landscape / portrait |
| Tap **Clear**, or press Esc | Clear the text |
| Tap **⚙ Setup** | Open the Setup screen (below) |
| **Press and hold** on the text box or the label preview for 1.5 seconds | Turn the screen off now, like the screen saver. Tap to wake it |

**Setup screen.** Tap **Done** or press Esc to return.

| Setting | What it does |
|---|---|
| **Date** (green with ✓ when on) and its text field | Print the date, or any text you type there. F2 also toggles it |
| **QR** (green with ✓ when on) and its text field | Print a QR code of the field's text, or of the label text if the field is blank. F3 also toggles it |
| **Copies − / +** | How many labels each PRINT makes |
| **Brightness 25 / 50 / 75 / 100%** | Screen brightness. Remembered across restarts |
| **Print hold Off / 1 / 2 / 3 / 5 s** | How long PRINT must be held. Off prints on a tap. Remembered across restarts |
| **Power** | Opens three tiles: **Restart**, **Shut down**, and **Desktop** (leave the app for the Raspberry Pi desktop). Tap a tile once and it turns red; tap it again to go ahead. The top line says whether it's safe to just unplug. Kiosk mode sets up the permission for Restart and Shut down; without kiosk mode, run `sudo bash kiosk/allow-power.sh` once |
| Under the title | The Pi's name and current IP address, for connecting to it over the network |

The screen goes dark after 5 minutes with no touch, key or button press. Tap it to wake it; that first tap only wakes the screen and never presses a button. Pressing TALK while the screen is dark wakes it and starts recording; PRINT wakes it and starts the hold. The screen comes back at the brightness you chose.

Tips for accuracy:
- Hold the button a moment *before* you start talking, and release a beat after you finish.
- Keep the mic 15–30cm from your mouth, away from fans and the printer.
- Spell-outs and part numbers are where speech recognition most often slips. A quick look at the preview catches them.

## Configuration

Everything adjustable is in `config.py`, with comments. The most common changes:

| Setting | What it does |
|---|---|
| `ORIENTATION` | Default layout: `"landscape"` or `"portrait"` |
| `LABEL_WIDTH_IN`, `LABEL_LENGTH_IN` | How the labels sit in the printer: width across the print head, and length along the feed. 3 and 2 for a 3 × 2" roll loaded wide side across |
| `LANDSCAPE_ROTATE_DEG` | Change 90 to 270 if labels whose layout is turned to fit the roll (portrait on a wide roll) print upside down |
| `DATE_FORMAT` | `"%b %d, %Y"` = Oct 16, 2026; `"%m/%d/%Y"` = 10/16/2026 |
| `DATE_DEFAULT_ON`, `QR_DEFAULT_ON` | Whether date / QR are on when the app starts |
| `PRINT_DARKNESS` | 0–30. Raise if the print is faint |
| `RECORD_MODE` | `"replace"` the text with each recording, or `"append"` to it |
| `PRINT_HOLD_SECONDS`, `PRINT_HOLD_CHOICES` | Default PRINT hold time, and the choices on the Setup screen (0 = no hold) |
| `TALK_BUTTON_PIN`, `PRINT_BUTTON_PIN`, `*_LED_PIN` | GPIO pins for the two buttons and their lights |
| `MIC_NAME` | Text in the microphone's name. The app finds it on any USB port; `./run.sh stt.py --list` shows the names |
| `KEYTERMS` | Words the speech model should favor (part numbers, names, jargon), spelled as you want them printed |
| `SCREEN_BLANK_SECONDS` | Seconds of inactivity before the screen goes dark (0 = never) |
| `LONG_PRESS_BLANK_SECONDS` | How long to hold on the text box or preview to turn the screen off (0 = never) |
| `DOUBLE_TAP_SECONDS` | How soon after a tap on TALK a press and hold counts as "clear and start over" |
| `BRIGHTNESS_LEVELS` | The brightness choices on the Setup screen, in percent |

## Testing without the hardware

On any Linux or Mac computer with Python 3 and Tk:

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python app.py --windowed --dry-run
```

The window is 800×480 by default to match the Hosyond screen. Add `--size 720x1280` to see the tall layout.

`--dry-run` saves each label to `out/` as a `.zpl` file and a `.png` of the preview instead of printing. To test only the microphone and speech model, run `.venv/bin/python stt.py`.

## Troubleshooting

| Problem | Fix |
|---|---|
| "Printer not found at /dev/usb/lp0" | Check the USB cable and power. Run `ls /dev/usb/` to see the device name and update `PRINTER_DEVICE` |
| "No permission for /dev/usb/lp0" | The installer adds you to the `lp` group; reboot so it takes effect |
| Labels print across two labels, or skip one | Calibrate the printer again (see Setting up the printer) |
| Print is faint | Raise `PRINT_DARKNESS`, or check that the labels are direct-thermal (scratch one with a fingernail; it should leave a dark mark) |
| "Microphone not found" | Plug the mic into any USB port and press TALK again; the app looks for it each time. If you use a different mic, set `MIC_NAME` to part of its name (`./run.sh stt.py --list`) |
| App doesn't start at boot | Check the kiosk service: `systemctl status labelbox` and `journalctl -u labelbox -b`. Run `sudo bash kiosk/install-kiosk.sh` again if it's missing |
| A deck button does nothing | Check the wiring against the table above. The status line says "Hold the Talk button (or press F1)" when the app can't see the TALK button |

## Files

| File | Purpose |
|---|---|
| `app.py` | The screen: editor, preview, buttons |
| `render.py` | Draws the label (text fitting, date, QR) |
| `zpl.py` | Converts the label image to Zebra's ZPL language |
| `printer.py` | Sends the ZPL to the printer |
| `stt.py` | Push-to-talk speech recognition with Moonshine |
| `hardware.py` | The deck buttons and their lights |
| `config.py` | All settings |
| `icons.py` | The button icons, drawn with Pillow (run it to see them all on one sheet) |
| `install.sh` | One-time setup on the Pi |
| `run.sh` | Starts the app (or another script) with the right environment |
| `kiosk/` | Boot-to-app service, boot logo, desktop launchers, and install/uninstall scripts |
| `assets/` | Logo, app icon and boot splash (SVG sources and PNGs) |
