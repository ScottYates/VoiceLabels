<p align="center"><img src="labelbox/assets/logo.png" alt="Voice Labels: speak it, check it, print it" width="480"></p>

# Voice Labels

A stand-alone voice-to-label printer built on a Raspberry Pi 5. Hold **TALK** and say what the label should read. Fix any words on the keyboard or touchscreen, check the preview, then hold **PRINT** to print a 2×3" label on a Zebra thermal printer.

Speech recognition runs entirely on the Pi with [Moonshine](https://github.com/moonshine-ai/moonshine), so there's no cloud service, no fee, and no internet needed after setup.

<p align="center">
  <img src="case/docs/case-front.png?v=7" alt="The case: a 7-inch screen reclined above a deck with a red TALK button and a green PRINT button, the Voice Labels logo on the front panel and a gooseneck mic at the side" width="520">
</p>

| Main screen | Setup screen |
|---|---|
| <img src="labelbox/docs/screen.png?v=5" alt="Main screen: Hold and speak and PRINT buttons across the top, the text box on the left, the label preview with a screw icon on the right, and Rotate, Left, Icon, Help and Setup buttons" width="400"> | <img src="labelbox/docs/setup.png?v=3" alt="Setup screen: Network, Power and Done buttons, Date and QR toggles with text fields, align, copies, brightness and print hold buttons, and the Labels button" width="400"> |

<p align="center">
  <img src="labelbox/docs/sample-label.png" alt="A sample 3 by 2 inch label with text, a QR code and the date" width="300"><br>
  <em>A label as the app draws and prints it (3 × 2 in, 203 dpi)</em>
</p>

## What's here

| Folder | Contents |
|---|---|
| [`labelbox/`](labelbox/) | The app: touchscreen editor with a live label preview, push-to-talk speech, date and QR code options, Zebra ZPL printing, screen blanking, and a Setup screen. [Setup and usage guide](labelbox/README.md) |
| [`case/`](case/) | A 3D-printable desk console: the reclined screen housing, a button deck for TALK and PRINT, an opening for the mic to plug straight into the Pi, snap-out cable tabs, and a closed power pod with a switched, fused mains socket for the USB power brick. Includes print-ready STLs, the parametric Python model and an [interactive 3D viewer](https://scottyates.github.io/VoiceLabels/). [Printing and assembly guide](case/README.md) |

## Hardware

- Raspberry Pi 5 (4 GB), 27 W USB-C supply, Active Cooler, 32 GB microSD
- Hosyond 7" DSI touchscreen, 800×480
- USB gooseneck microphone (C G CHANGEEK CGS-M1)
- Two 30 mm arcade buttons with 5 V LEDs
- Zebra GK420d or GC420d direct-thermal printer (USB), 2×3" labels
- Compact wireless keyboard

## Quick start

On Raspberry Pi OS (64-bit, desktop), copy the `labelbox` folder to the Pi and run:

```
cd labelbox
bash install.sh
sudo reboot
```

The Pi then boots straight into the app (kiosk mode); Setup has an Exit to desktop button. See [labelbox/README.md](labelbox/README.md) for wiring, printer setup and settings.
