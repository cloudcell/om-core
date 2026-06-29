#!/bin/bash
set -e

# Prevent Qt tests from opening visible windows during headless/CI runs
export QT_QPA_PLATFORM=offscreen
PYTHON="./venv/bin/python"

echo "=== Running tests sequentially ==="
"$PYTHON" -m pytest tests/
echo ""


# Generate version timestamp for this build only if all successful
if [ $? -eq 0 ]; then
    TS=$(date +%Y%m%d-%H%M%S)
    HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "nogit")
    echo "${TS}-${HASH}" > version.txt
    echo "Version: $(cat version.txt)"
fi

