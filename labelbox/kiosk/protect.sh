#!/usr/bin/env bash
# Power-off protection: make the Pi safe to unplug at any moment.
#
# Turns on Raspberry Pi OS's overlay file system: the SD card's main partition
# becomes read-only and every change goes to memory instead, so pulling the
# power can't corrupt anything. Voice Labels' settings (brightness, print hold)
# are saved to the boot partition so they survive restarts.
#
#   sudo bash kiosk/protect.sh on       then restart
#   sudo bash kiosk/protect.sh off      then restart (do this before updating
#                                       the app or running apt upgrades)
#   bash kiosk/protect.sh status
#
# While protection is on, anything else you change (installed packages, files
# in your home folder, app updates) is lost at the next restart.
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME="${SUDO_USER:-pi}"
HELPER=/usr/local/sbin/voicelabels-save-settings
SUDOERS=/etc/sudoers.d/voicelabels
BOOT_SETTINGS=/boot/firmware/voicelabels-settings.json

status() {
    local now=off conf=off
    grep -q "overlayroot=tmpfs" /proc/cmdline && now=on
    grep -q "overlayroot=tmpfs" /boot/firmware/cmdline.txt && conf=on
    case "$now/$conf" in
        on/on)   echo "Protection is ON: safe to unplug." ;;
        off/on)  echo "Protection turns ON at the next restart." ;;
        on/off)  echo "Protection is on now but turns OFF at the next restart." ;;
        *)       echo "Protection is OFF: shut down before unplugging." ;;
    esac
}

need_root() { [ "$(id -u)" = 0 ] || { echo "Run this with sudo: sudo bash $0 $1"; exit 1; }; }

case "${1:-status}" in
on)
    need_root on
    if grep -q "overlayroot=tmpfs" /proc/cmdline; then
        echo "The main partition is read-only right now; turn protection off, restart, then run this again."
        exit 1
    fi
    echo "== Settings helper (keeps settings on the boot partition)"
    cat > "$HELPER" <<'EOS'
#!/bin/sh
# Save Voice Labels settings (JSON on stdin) to the boot partition safely.
set -e
dest=/boot/firmware/voicelabels-settings.json
tmp=$(mktemp /boot/firmware/.vl-XXXXXX)
head -c 8192 > "$tmp"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert isinstance(d, dict)' "$tmp" || { rm -f "$tmp"; exit 1; }
sync "$tmp"
mv -f "$tmp" "$dest"
sync /boot/firmware
EOS
    chmod 755 "$HELPER"
    echo "$USER_NAME ALL=(root) NOPASSWD: $HELPER" > "$SUDOERS"
    chmod 440 "$SUDOERS"
    visudo -cf "$SUDOERS" >/dev/null
    if [ -f "$DIR/settings.json" ] && [ ! -f "$BOOT_SETTINGS" ]; then
        "$HELPER" < "$DIR/settings.json" || true
    fi

    echo "== Read-only main partition (overlay file system)"
    raspi-config nonint enable_overlayfs
    raspi-config nonint disable_bootro      # boot partition stays writable for settings
    echo
    status
    echo "Restart to start protection: sudo reboot"
    ;;
off)
    need_root off
    raspi-config nonint disable_overlayfs
    echo
    status
    echo "Restart, then make your updates. Turn it back on afterwards: sudo bash $0 on"
    ;;
status)
    status
    ;;
*)
    echo "Usage: sudo bash $0 on|off   or   bash $0 status"; exit 1 ;;
esac
