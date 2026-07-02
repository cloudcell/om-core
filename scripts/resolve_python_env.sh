#!/usr/bin/env bash
# Resolve the project Python environment for shell entry points.
# OM Core uses uv exclusively.
#
# Exports:
#   UV      - path to the uv executable
#   PYTHON  - command prefix for running Python through uv
#   PYRUN   - command prefix for running commands through uv

resolve_python_env() {
    # Prefer a project-local uv, then common installer locations, then PATH.
    if [ -x "${PWD}/venv/bin/uv" ]; then
        UV="${PWD}/venv/bin/uv"
    elif [ -x "$HOME/.local/bin/uv" ]; then
        UV="$HOME/.local/bin/uv"
        export PATH="$HOME/.local/bin:$PATH"
    elif [ -x "$HOME/.cargo/bin/uv" ]; then
        UV="$HOME/.cargo/bin/uv"
        export PATH="$HOME/.cargo/bin:$PATH"
    elif command -v uv >/dev/null 2>&1; then
        UV=$(command -v uv)
    else
        cat >&2 <<'EOF'
OM Core uses uv to manage its Python environment.

uv is not installed or not on your PATH. uv is needed because it will:
  - create the project's virtual environment (./.venv)
  - install the exact dependency versions recorded in uv.lock
  - run commands inside that environment

EOF

        if [ -t 0 ]; then
            read -r -p "Install uv automatically now? [Y/n]: " answer
            answer=${answer:-Y}
            case "$answer" in
                [Yy]*)
                    echo "Installing uv..."
                    if curl -LsSf https://astral.sh/uv/install.sh | sh; then
                        if [ -x "$HOME/.local/bin/uv" ]; then
                            UV="$HOME/.local/bin/uv"
                            export PATH="$HOME/.local/bin:$PATH"
                        elif [ -x "$HOME/.cargo/bin/uv" ]; then
                            UV="$HOME/.cargo/bin/uv"
                            export PATH="$HOME/.cargo/bin:$PATH"
                        elif command -v uv >/dev/null 2>&1; then
                            UV=$(command -v uv)
                        else
                            echo "Installation finished, but uv was not found in the expected location." >&2
                            echo "Please open a new terminal or add ~/.local/bin or ~/.cargo/bin to your PATH, then retry." >&2
                            exit 1
                        fi
                    else
                        echo "Automatic uv installation failed." >&2
                        echo "Please install uv manually: https://docs.astral.sh/uv" >&2
                        exit 1
                    fi
                    ;;
                *)
                    echo "uv is required to run this project." >&2
                    echo "Please install uv manually: https://docs.astral.sh/uv" >&2
                    exit 1
                    ;;
            esac
        else
            echo "This is a non-interactive shell; cannot prompt to install uv." >&2
            echo "Please install uv manually: https://docs.astral.sh/uv" >&2
            exit 1
        fi
    fi

    PYRUN="$UV run"
    PYTHON="$UV run python"
    export UV PYTHON PYRUN

    ensure_python
}

# Ensure a project-compatible Python interpreter is installed.
# uv can download and manage Python versions automatically without admin rights.
ensure_python() {
    if [ -z "${UV:-}" ]; then
        echo "ensure_python: UV is not set. Call resolve_python_env first." >&2
        exit 1
    fi

    local py_spec="3.12"
    if [ -f "${PWD}/pyproject.toml" ]; then
        local parsed
        parsed=$(grep -E '^requires-python' pyproject.toml | head -n1 | sed -E 's/.*([0-9]+\.[0-9]+).*/\1/')
        if [ -n "$parsed" ]; then
            py_spec="$parsed"
        fi
    fi

    if ! "$UV" python find "$py_spec" >/dev/null 2>&1; then
        echo "Python $py_spec not found; installing via uv..." >&2
        if ! "$UV" python install "$py_spec"; then
            echo "Failed to install Python $py_spec via uv." >&2
            echo "Please install Python $py_spec manually: https://www.python.org/downloads/" >&2
            exit 1
        fi
    fi
}
