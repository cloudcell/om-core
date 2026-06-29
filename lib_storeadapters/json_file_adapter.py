"""JSON file persistence adapter for workspace state.

This adapter wraps the existing free functions in lib_openm.persistence.
It does not refactor the serialization, migration, or tagged-value helpers.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from lib_openm.model import Workspace
from lib_openm.persistence import load_workspace_profiled, save_workspace
from lib_storeadapters.ports import WorkspacePersistenceAdapter


def workspace_to_json_string(workspace: Workspace) -> str:
    """Serialize a workspace to the same JSON string used by ``JsonFileAdapter``.

    This is a thin wrapper around the canonical file-based serialization path
    in ``lib_openm.persistence``. It writes to a temporary file so that the
    existing save logic, migration, and system-cube bootstrap are reused
    exactly.
    """
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".openm", encoding="utf-8", delete=False
    ) as f:
        tmp_path = f.name
    try:
        save_workspace(tmp_path, workspace)
        with open(tmp_path, "r", encoding="utf-8") as f:
            return f.read()
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def workspace_from_json_string(json_str: str) -> Workspace:
    """Deserialize a workspace from the JSON string used by ``JsonFileAdapter``.

    This is a thin wrapper around the canonical file-based load path. It
    writes to a temporary file so that migration, system-cube bootstrap, and
    load profiling are reused exactly.
    """
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".openm", encoding="utf-8", delete=False
    ) as f:
        tmp_path = f.name
        f.write(json_str)
    try:
        ws, _ = load_workspace_profiled(tmp_path)
        return ws
    finally:
        Path(tmp_path).unlink(missing_ok=True)


class JsonFileAdapter(WorkspacePersistenceAdapter):
    """Adapter that saves/loads workspace state as JSON .openm files."""

    def save_workspace(self, path: str | Path, workspace: Workspace) -> None:
        """Persist the workspace to a JSON file."""
        save_workspace(str(path), workspace)

    def load_workspace(self, path: str | Path) -> Workspace:
        """Load a workspace from a JSON file."""
        ws, _ = load_workspace_profiled(str(path))
        return ws

    def load_workspace_profiled(
        self, path: str | Path
    ) -> tuple[Workspace, dict[str, Any]]:
        """Load a workspace and return the diagnostic profile.

        This method is specific to the JSON adapter and is not part of the
        generic WorkspacePersistenceAdapter interface. It preserves the
        existing load profiling behavior used by the command layer.
        """
        return load_workspace_profiled(str(path))
