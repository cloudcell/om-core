#!/bin/bash

# OpenModeling launcher — runtime-first, then clients.
#
# Architecture:
#   1. Runtime (engine + bus + command service + transport) starts first.
#   2. Clients (GUI with splash, REPL, etc.) connect separately.
#   3. Default: GUI + REPL both start. GUI gets the splash screen.

# Check if virtual environment exists, ask before creating
if [ ! -d "./venv" ]; then
    read -r -p "Virtual environment not found. Create one? [Y/n]: " answer
    answer=${answer:-Y}
    case "$answer" in
        [Yy]*)
            echo "Creating virtual environment..."
            python3 -m venv ./venv
            ;;
        *)
            echo "Please create a virtual environment and retry."
            exit 1
            ;;
    esac
fi

# Activate virtual environment
source ./venv/bin/activate

# Check if packages from requirements.txt are installed
check_packages() {
    while IFS= read -r package || [[ -n "$package" ]]; do
        # Skip empty lines and comments
        [[ -z "$package" || "$package" =~ ^# ]] && continue

        # Extract package name (handle specs like pkg>=1.0, pkg==1.0, etc.)
        pkg_name=$(echo "$package" | sed -E 's/([a-zA-Z0-9_-]+).*/\1/')

        if ! python -c "import $pkg_name" 2>/dev/null; then
            # Try pip show as fallback for packages with different import names
            if ! pip show "$pkg_name" >/dev/null 2>&1; then
                echo "Missing package: $package"
                return 1
            fi
        fi
    done < requirements.txt
    return 0
}

if ! check_packages; then
    echo ""
    read -r -p "Some required packages are missing. Install them now? [Y/n]: " answer
    answer=${answer:-Y}
    case "$answer" in
        [Yy]*)
            echo "Installing missing packages..."
            pip install -r requirements.txt || {
                echo "Package installation failed. Please install manually and retry."
                exit 1
            }
            ;;
        *)
            echo "Please install missing packages by running: pip install -r requirements.txt"
            exit 1
            ;;
    esac
fi

# Resolve script directory for background/foreground coordination
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
    python -O main.py --runtime
    exit $?

elif [ "$1" = "--gui" ]; then
    # GUI client only (connects to existing --runtime)
    echo "Starting OM GUI client..."
    python -O main.py --gui
    exit $?

elif [ "$1" = "--gui-only" ]; then
    # Runtime + GUI only (no REPL client). Splash screen lives here.
    echo "Starting OM runtime + GUI..."
    python -O main.py --gui-only
    exit $?

elif [ "$1" = "--repl" ]; then
    # REPL client only (assumes runtime is already running)
    echo "Starting OM REPL client..."
    python -O main.py --repl
    REPL_EXIT=$?
    # Guard: restore terminal echo if the REPL died abnormally (SIGTERM, etc.)
    # Python finally blocks don't run on SIGTERM, so the shell must clean up.
    stty echo 2>/dev/null || true
    exit $REPL_EXIT

elif [ "$1" = "--tui" ]; then
    # TUI client only (connects to existing --runtime)
    echo "Starting OM TUI client..."
    python -O main.py --tui
    TUI_EXIT=$?
    stty echo 2>/dev/null || true
    exit $TUI_EXIT

elif [ "$1" = "--gui-with-repl" ]; then
    # Legacy single-process combined mode
    echo "Starting OM GUI + REPL (single process)..."
    python -O main.py --gui-with-repl
    exit $?

elif [ "$1" = "--batch" ] && [ -n "$2" ]; then
    # Headless batch execution (remote client, requires runtime)
    echo "Running OM in batch mode: $2"
    python -O main.py --batch "$2"
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
    python -O main.py --gui-only &
    GUI_PID=$!

    # Detach the GUI so it survives after this script exits.
    disown $GUI_PID 2>/dev/null || true
    GUI_PID=""

    # Brief pause to let transport server initialise
    sleep 1

    if [ "$OPEN_TUI" -eq 1 ]; then
        echo "Opening TUI in a separate terminal..."
        TUI_CMD="cd \"$SCRIPT_DIR\" && source ./venv/bin/activate && ./start.sh --tui"

        if command -v gnome-terminal >/dev/null 2>&1; then
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
