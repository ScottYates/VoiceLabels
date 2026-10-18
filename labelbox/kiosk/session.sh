#!/usr/bin/env bash
# Runs inside the kiosk window manager. Starts the app and restarts it if it
# crashes or closes. "Exit to desktop" in Setup stops this whole service.
cd "$(dirname "$0")/.."
export LABELBOX_KIOSK=1
while true; do
    ./run.sh
    echo "Voice Labels stopped (exit $?); restarting in 2 seconds" >&2
    sleep 2
done
