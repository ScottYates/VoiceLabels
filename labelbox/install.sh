#!/usr/bin/env bash
# One-time setup on Raspberry Pi OS (Bookworm or Trixie, desktop version).
# Run from the labelbox folder:  bash install.sh
set -euo pipefail
cd "$(dirname "$0")"
APP_DIR="$(pwd)"

echo "== System packages"
sudo apt update
sudo apt install -y python3-venv python3-tk python3-pil.imagetk python3-gpiozero \
    python3-lgpio libportaudio2 fonts-dejavu-core wlopm

echo "== Python environment"
python3 -m venv --system-site-packages .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo "== Printer and GPIO access"
sudo usermod -aG lp,gpio,video "$USER"

echo "== Download the speech model now, while online"
./run.sh - <<'PY'
from stt import PushToTalk
s = PushToTalk(on_error=print)
s.load()
print("Speech model ready" if s.ready else "Speech model did NOT load")
print("Microphone:", s.mic_name or "not found (plug in the USB mic)")
s.close()
PY

echo "== Start the app at boot (kiosk mode, no desktop)"
sudo bash kiosk/install-kiosk.sh

echo
echo "Done. Reboot (sudo reboot) to start Voice Labels."
