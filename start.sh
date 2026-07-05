#!/bin/bash

# OpenModeling launcher — runtime-first, then clients.
#
# Architecture:
#   1. Runtime (engine + bus + command service + transport) starts first.
#   2. Clients (GUI with splash, REPL, etc.) connect separately.
#   3. Default: GUI + REPL both start. GUI gets the splash screen.
#
# Requires uv. Install from https://docs.astral.sh/uv.

# Resolve script directory for background/foreground coordination
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Resolve the Python environment
source "$SCRIPT_DIR/scripts/resolve_python_env.sh"
resolve_python_env

cleanup() {
    # Default-mode only: kill background GUI if REPL exited abnormally.
    # Client-only modes (--tui, --repl, etc.) have no background orphans.
    if [ -n "${GUI_PID:-}" ]; then
        kill "$GUI_PID" 2>/dev/null
        wait "$GUI_PID" 2>/dev/null
    fi
}
trap cleanup EXIT INT TERM

# ---------------------------------------------------------------------------
# Mode dispatch
# ---------------------------------------------------------------------------

if [ "$1" = "--runtime" ]; then
    # Standalone runtime host (no clients)
    echo "Starting OM runtime host..."
    $PYTHON -O main.py --runtime
    exit $?

elif [ "$1" = "--gui" ]; then
    # GUI client only (connects to existing --runtime)
    echo "Starting OM GUI client..."
    $PYTHON -O main.py --gui
    exit $?

elif [ "$1" = "--gui-only" ]; then
    # Runtime + GUI only (no REPL client). Splash screen lives here.
    echo "Starting OM runtime + GUI..."
    $PYTHON -O main.py --gui-only
    exit $?

elif [ "$1" = "--repl" ]; then
    # REPL client only (assumes runtime is already running)
    echo "Starting OM REPL client..."
    $PYTHON -O main.py --repl
    REPL_EXIT=$?
    # Guard: restore terminal echo if the REPL died abnormally (SIGTERM, etc.)
    # Python finally blocks don't run on SIGTERM, so the shell must clean up.
    stty echo 2>/dev/null || true
    exit $REPL_EXIT

elif [ "$1" = "--tui" ]; then
    # TUI client only (connects to existing --runtime)
    echo "Starting OM TUI client..."
    $PYTHON -O main.py --tui
    TUI_EXIT=$?
    stty echo 2>/dev/null || true
    exit $TUI_EXIT

elif [ "$1" = "--gui-with-repl" ]; then
    # Legacy single-process combined mode
    echo "Starting OM GUI + REPL (single process)..."
    $PYTHON -O main.py --gui-with-repl
    exit $?

elif [ "$1" = "--batch" ] && [ -n "$2" ]; then
    # Headless batch execution (remote client, requires runtime)
    echo "Running OM in batch mode: $2"
    $PYTHON -O main.py --batch "$2"
    exit $?

else
    # DEFAULT: runtime + GUI (detached), plus TUI in a separate terminal.
    # Ask before the GUI starts so the prompt is not lost in engine output.
    read -r -p "Open a TUI in a separate terminal? [Y/n]: " answer
    answer=${answer:-Y}
    OPEN_TUI=0
    case "$answer" in
        [Yy]*)
            OPEN_TUI=1
            ;;
    esac

    echo "Starting OM runtime + GUI..."
    $PYTHON -O main.py --gui-only &
    GUI_PID=$!

    # Detach the GUI so it survives after this script exits.
    disown $GUI_PID 2>/dev/null || true
    GUI_PID=""

    # Brief pause to let transport server initialise
    sleep 1

    if [ "$OPEN_TUI" -eq 1 ]; then
        echo "Opening TUI in a separate terminal..."
        TUI_CMD="cd \"$SCRIPT_DIR\" && ./start.sh --tui"

        if command -v osascript >/dev/null 2>&1 && [ "$(uname -s)" = "Darwin" ]; then
            # macOS: open a new Terminal.app window and run the TUI client there.
            # Escape backslashes and double quotes so the path is safe in AppleScript.
            SCRIPT_DIR_AE=$(printf '%s\n' "$SCRIPT_DIR" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr -d '\n')
            osascript <<EOF
tell application "Terminal"
    activate
    do script "cd " & quoted form of "$SCRIPT_DIR_AE" & " && ./start.sh --tui"
end tell
EOF
        elif command -v gnome-terminal >/dev/null 2>&1; then
            gnome-terminal -- bash -c "$TUI_CMD" &
        elif command -v konsole >/dev/null 2>&1; then
            konsole -e bash -c "$TUI_CMD" &
        elif command -v xfce4-terminal >/dev/null 2>&1; then
            xfce4-terminal -e "bash -c '$TUI_CMD'" &
        elif command -v alacritty >/dev/null 2>&1; then
            alacritty -e bash -c "$TUI_CMD" &
        elif command -v kitty >/dev/null 2>&1; then
            kitty bash -c "$TUI_CMD" &
        elif command -v xterm >/dev/null 2>&1; then
            xterm -e bash -c "$TUI_CMD" &
        else
            echo "No supported terminal emulator found."
            echo "Please run './start.sh --tui' manually in another terminal."
        fi
    else
        echo "TUI not opened. Run './start.sh --tui' later if you want a command line."
    fi

    # Release the original terminal; the GUI and TUI run independently.
    trap - EXIT INT TERM
    exit 0
fi
