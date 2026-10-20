#!/usr/bin/env bash
# Let the Voice Labels user restart and shut down the Pi (and switch between
# the app and the desktop) without a password, however the app was started.
#   sudo bash kiosk/allow-power.sh
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Run this with sudo: sudo bash $0"; exit 1; }
USER_NAME="${SUDO_USER:-pi}"
DIR="$(cd "$(dirname "$0")/.." && pwd)"
sed "s#@USER@#$USER_NAME#g" "$DIR/kiosk/labelbox.rules" > /etc/polkit-1/rules.d/50-labelbox.rules
chmod 644 /etc/polkit-1/rules.d/50-labelbox.rules
echo "Done: $USER_NAME can now restart and shut down from the app's Power panel."
