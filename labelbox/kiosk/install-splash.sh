#!/usr/bin/env bash
# Show the Voice Labels logo from power-on instead of the Raspberry Pi splash,
# and hide boot text, the Pi logos and the blinking cursor.
#   sudo bash kiosk/install-splash.sh
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Run this with sudo: sudo bash $0"; exit 1; }
DIR="$(cd "$(dirname "$0")/.." && pwd)"
THEME=/usr/share/plymouth/themes/voicelabels
CONFIG=/boot/firmware/config.txt
CMDLINE=/boot/firmware/cmdline.txt

echo "== Boot splash theme"
install -d "$THEME"
install -m 644 "$DIR/kiosk/plymouth/voicelabels.plymouth" "$DIR/kiosk/plymouth/voicelabels.script" "$THEME/"
install -m 644 "$DIR/assets/splash.png" "$THEME/splash.png"

echo "== Firmware: no rainbow screen"
grep -q '^disable_splash=1' "$CONFIG" || printf '\n[all]\ndisable_splash=1\n' >> "$CONFIG"

echo "== Kernel: quiet, splash, no Pi logos, no cursor"
cp -n "$CMDLINE" "$CMDLINE.before-voicelabels" || true
line="$(tr -d '\n' < "$CMDLINE")"
for opt in quiet splash logo.nologo vt.global_cursor_default=0 loglevel=3; do
    case " $line " in *" $opt "*) ;; *) line="$line $opt" ;; esac
done
printf '%s\n' "$line" > "$CMDLINE"

echo "== Rebuilding the boot image with the new splash (takes a minute)"
plymouth-set-default-theme -R voicelabels

echo
echo "Done. Reboot to see it: sudo reboot"
echo "To go back to the Raspberry Pi splash: sudo plymouth-set-default-theme -R pix"
