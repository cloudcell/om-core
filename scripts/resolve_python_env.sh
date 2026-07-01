#!/usr/bin/env bash
# Resolve the project Python environment for shell entry points.
#
# Prefers uv when it is available and pyproject.toml is present.
# Falls back to the legacy ./venv pip virtual environment.
#
# Exports:
#   UV      - absolute path to the selected uv executable (empty if none)
#   PYTHON  - command prefix for running Python (e.g. "uv run python" or "python")
#   PYRUN   - command prefix for running commands through the env manager
#             (e.g. "uv run" or empty)

resolve_python_env() {
    # Prefer a project-local uv installed in the legacy venv, then any uv on PATH.
    if [ -x "${PWD}/venv/bin/uv" ]; then
        UV="${PWD}/venv/bin/uv"
    elif command -v uv >/dev/null 2>&1; then
        UV=$(command -v uv)
    else
        UV=""
    fi

    if [ -n "$UV" ] && [ -f "pyproject.toml" ]; then
        # Let uv use its own project environment (typically .venv). Do not set
        # VIRTUAL_ENV to a different path, because uv ignores it and warns.
        PYRUN="$UV run"
        PYTHON="$UV run python"
    elif [ -d "${PWD}/venv" ]; then
        # Legacy pip path.
        # shellcheck source=/dev/null
        source "${PWD}/venv/bin/activate"
        PYRUN=""
        PYTHON="python"
        UV=""
    else
        echo "ERROR: No Python environment found." >&2
        echo "Install uv (https://docs.astral.sh/uv) or create a virtual environment:" >&2
        echo "  python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt" >&2
        exit 1
    fi

    export UV PYTHON PYRUN
}
