#!/usr/bin/env bash
# Undo install-kiosk.sh: boot to the desktop again and start the app there.
#   sudo bash kiosk/uninstall-kiosk.sh
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Run this with sudo: sudo bash $0"; exit 1; }
USER_NAME="${SUDO_USER:-pi}"
DIR="$(cd "$(dirname "$0")/.." && pwd)"
HOME_DIR="$(getent passwd "$USER_NAME" | cut -d: -f6)"
systemctl disable labelbox.service || true
rm -f /etc/systemd/system/labelbox.service /etc/polkit-1/rules.d/50-labelbox.rules
rm -f "$HOME_DIR/.local/share/applications/labelbox.desktop" "$HOME_DIR/Desktop/labelbox.desktop"
install -d -o "$USER_NAME" -g "$USER_NAME" "$HOME_DIR/.config/autostart"
printf '[Desktop Entry]\nType=Application\nName=Voice Labels\nExec=%s/run.sh\nPath=%s\n' "$DIR" "$DIR" \
    > "$HOME_DIR/.config/autostart/labelbox.desktop"
chown "$USER_NAME:$USER_NAME" "$HOME_DIR/.config/autostart/labelbox.desktop"
systemctl daemon-reload
systemctl set-default graphical.target
echo "Done. Reboot to start the desktop: sudo reboot"
