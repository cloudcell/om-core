#!/bin/bash
# Test runner for lib_timelinewidget
# Runs unit tests and optional GUI demo
#
# Usage:
#   ./test_timelinewidget.sh          # Run tests + GUI demo
#   ./test_timelinewidget.sh --ci     # Run tests only (headless mode)

set -e  # Exit on error

# Parse arguments
CI_MODE=false
if [ "$1" = "--ci" ]; then
    CI_MODE=true
fi

# Use venv Python if available
if [ -f "venv/bin/python" ]; then
    PYTHON="venv/bin/python"
else
    PYTHON="python"
fi

# Set Qt platform for headless testing
if [ "$CI_MODE" = true ] || [ -z "$DISPLAY" ]; then
    export QT_QPA_PLATFORM=offscreen
    echo "[Running in headless mode]"
fi

echo "=========================================="
echo "lib_timelinewidget Test Suite"
echo "Python: $PYTHON"
echo "=========================================="
echo ""

# Check if we're in the right directory
if [ ! -f "lib_timelinewidget/__init__.py" ]; then
    echo "Error: Must run from project root"
    echo "Current directory: $(pwd)"
    exit 1
fi

echo "[1/4] Running model tests..."
$PYTHON -m pytest lib_timelinewidget/tests/test_models.py -v
echo ""

echo "[2/4] Running widget unit tests..."
$PYTHON -m pytest lib_timelinewidget/tests/test_timeline_widget.py -v
echo ""

echo "[3/4] Running import test..."
$PYTHON -c "
from lib_timelinewidget import TimelineWidget, SnapshotInfo, SnapshotType
print('  ✓ Imports successful')
print(f'  ✓ TimelineWidget: {TimelineWidget}')
print(f'  ✓ SnapshotInfo: {SnapshotInfo}')
print(f'  ✓ SnapshotType: {SnapshotType}')
"
echo ""

# GUI Demo
if [ "$CI_MODE" = false ]; then
    echo "[4/4] GUI Demo (close window when done)..."
    echo "  Launching demo with sample data..."
    echo "  "
    echo "  Test actions:"
    echo "    - Click nodes to select"
    echo "    - Double-click nodes"
    echo "    - Right-click nodes for context menu"
    echo "    - Try Linear/Branched/Complex buttons"
    echo "    - Check timestamps and colors"
    echo ""
    
    # Run demo - stays open until user closes window
    $PYTHON -m lib_timelinewidget.demo
    
    echo ""
    echo "=========================================="
    echo "All tests passed!"
    echo "=========================================="
else
    echo "[4/4] GUI Demo - SKIPPED (CI mode - no display)"
    echo ""
    echo "=========================================="
    echo "CI tests passed! (GUI demo skipped)"
    echo "=========================================="
fi
