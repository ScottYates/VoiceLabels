#!/usr/bin/env bash
# Start Voice Labels from the desktop (taskbar, menu or desktop icon).
# With kiosk mode installed this leaves the desktop and goes back to the kiosk;
# without it, the app opens on the desktop. Does nothing if it's already open.
DIR="$(cd "$(dirname "$0")/.." && pwd)"
if pgrep -f "[.]venv/bin/python app" >/dev/null; then
    exit 0
fi
if [ -f /etc/systemd/system/labelbox.service ]; then
    exec systemctl --no-block start labelbox.service
fi
cd "$DIR" && exec ./run.sh
