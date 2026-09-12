#!/bin/bash
# Double-click this file in Finder to set up and start the app.
cd "$(dirname "$0")" || exit 1

echo "MWO Match Stats - Setup and Launch"
echo

# ------------------------------------------------------------------
# Find a working Python 3. Recent macOS doesn't ship one by default,
# so "not found" here is the normal, expected first-run case.
# ------------------------------------------------------------------
PYCMD=""
if command -v python3 >/dev/null 2>&1; then
    PYCMD="python3"
fi

if [ -z "$PYCMD" ]; then
    echo "============================================================"
    echo "  Python isn't installed yet - opening the download page..."
    echo "============================================================"
    echo
    echo "  1. Click the big yellow \"Download Python\" button."
    echo "  2. Open the downloaded .pkg file and click through the"
    echo "     installer with the default options."
    echo "  3. When it finishes, come back and double-click"
    echo "     start.command again."
    echo
    open "https://www.python.org/downloads/"
    echo "Press Enter to close this window."
    read -r _
    exit 1
fi

echo "Checking everything the app needs is installed - this can take"
echo "a minute the first time, and is instant after that..."
echo
"$PYCMD" -m pip install -q -r requirements.txt
if [ $? -ne 0 ]; then
    echo
    echo "============================================================"
    echo "  Something went wrong installing what the app needs."
    echo "  Scroll up to see the error, or check the README's"
    echo "  Troubleshooting section."
    echo "============================================================"
    echo
    echo "Press Enter to close this window."
    read -r _
    exit 1
fi

echo
echo "Starting the app - your browser will open automatically in a"
echo "few seconds. Leave THIS window open while you're using it;"
echo "closing it stops the app."
echo

( sleep 3; open "http://localhost:8000" ) &
"$PYCMD" -m uvicorn app.main:app --port 8000

echo
echo "The app has stopped. Press Enter to close this window."
read -r _
