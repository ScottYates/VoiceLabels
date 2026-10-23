#!/usr/bin/env bash
# Add a Voice Labels button to the taskbar, the menu and the desktop.
# Run as your normal user (no sudo):  bash kiosk/launchers.sh
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
chmod +x "$DIR/kiosk/launch.sh" "$DIR/run.sh"

LAUNCHER="[Desktop Entry]
Type=Application
Name=Voice Labels
Comment=Open the label printer app
Exec=$DIR/kiosk/launch.sh
Icon=$DIR/assets/icon.png
Terminal=false
Categories=Utility;"

for f in "$HOME/.local/share/applications/labelbox.desktop" "$HOME/Desktop/labelbox.desktop"; do
    mkdir -p "$(dirname "$f")"
    printf '%s\n' "$LAUNCHER" > "$f"
    chmod +x "$f"
done

# Desktop icons run on double-click without asking "Execute / Open?"
mkdir -p "$HOME/.config/libfm"
CONF="$HOME/.config/libfm/libfm.conf"
if [ -f "$CONF" ] && grep -q '^quick_exec=' "$CONF"; then
    sed -i 's/^quick_exec=.*/quick_exec=1/' "$CONF"
elif [ -f "$CONF" ] && grep -q '^\[config\]' "$CONF"; then
    sed -i '/^\[config\]/a quick_exec=1' "$CONF"
else
    printf '[config]\nquick_exec=1\n' >> "$CONF"
fi

# Taskbar button (Raspberry Pi OS panel)
PANEL="$HOME/.config/wf-panel-pi/wf-panel-pi.ini"
mkdir -p "$(dirname "$PANEL")"
if ! grep -q '^launchers=' "$PANEL" 2>/dev/null; then
    if [ -f /etc/xdg/wf-panel-pi/wf-panel-pi.ini ]; then
        cat /etc/xdg/wf-panel-pi/wf-panel-pi.ini >> "$PANEL"
    else
        printf '[panel]\nlaunchers=x-www-browser pcmanfm x-terminal-emulator\n' >> "$PANEL"
    fi
fi
grep -q '^launchers=.*\blabelbox\b' "$PANEL" || sed -i 's/^launchers=.*/& labelbox/' "$PANEL"

# Desktop wallpaper: the Voice Labels logo (matches the boot splash).
WP="$HOME/.config/pcmanfm/default/desktop-items-0.conf"
mkdir -p "$(dirname "$WP")"
if [ ! -f "$WP" ]; then
    cp /etc/xdg/pcmanfm/default/desktop-items-0.conf "$WP" 2>/dev/null || printf '[*]\n' > "$WP"
fi
setkey() { if grep -q "^$1=" "$WP"; then sed -i "s|^$1=.*|$1=$2|" "$WP"; else sed -i "/^\[\*\]/a $1=$2" "$WP"; fi; }
setkey wallpaper "$DIR/assets/splash.png"
setkey wallpaper_mode center
setkey wallpaper_common 1
setkey desktop_bg "#1e1e1f1f2222"
setkey desktop_shadow "#1e1e1f1f2222"
pkill -f "[p]cmanfm --desktop" || true    # restarts itself with the new settings

echo "Voice Labels added to the taskbar, the menu and the desktop, and set as the wallpaper."
