#!/usr/bin/env bash
# Start the label app (or another script) with the bundled PortAudio library.
cd "$(dirname "$0")"
export LD_LIBRARY_PATH="$PWD/vendor/pa/usr/lib/aarch64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec .venv/bin/python "${@:-app.py}"
