#!/usr/bin/env bash
# Make the Pi boot straight into Voice Labels (no desktop), restart it if it
# crashes, and allow switching to the desktop from the Setup screen.
#   sudo bash kiosk/install-kiosk.sh
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Run this with sudo: sudo bash $0"; exit 1; }
USER_NAME="${SUDO_USER:-pi}"
DIR="$(cd "$(dirname "$0")/.." && pwd)"
HOME_DIR="$(getent passwd "$USER_NAME" | cut -d: -f6)"

echo "== Kiosk service for $USER_NAME in $DIR"
sed -e "s#@USER@#$USER_NAME#g" -e "s#@DIR@#$DIR#g" "$DIR/kiosk/labelbox.service" \
    > /etc/systemd/system/labelbox.service
sed "s#@USER@#$USER_NAME#g" "$DIR/kiosk/labelbox.rules" > /etc/polkit-1/rules.d/50-labelbox.rules
chmod +x "$DIR/kiosk/session.sh" "$DIR/kiosk/launch.sh" "$DIR/run.sh"

echo "== Desktop: stop auto-starting the app there, add Voice Labels buttons"
rm -f "$HOME_DIR/.config/autostart/labelbox.desktop"
runuser -u "$USER_NAME" -- env HOME="$HOME_DIR" bash "$DIR/kiosk/launchers.sh"

bash "$DIR/kiosk/install-splash.sh"

echo "== Boot to the kiosk instead of the desktop"
systemctl daemon-reload
systemctl enable labelbox.service
systemctl set-default multi-user.target

echo
echo "Done. Reboot to start the kiosk: sudo reboot"
