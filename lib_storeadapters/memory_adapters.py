"""In-memory workspace persistence adapters for tests and isolation.

These adapters do not touch the filesystem. ``InMemoryAdapter`` deep-copies the
workspace object graph. ``InMemoryJsonAdapter`` round-trips through the same
JSON payload used by ``JsonFileAdapter``.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from lib_openm.model import Workspace
from lib_storeadapters.json_file_adapter import (
    workspace_from_json_string,
    workspace_to_json_string,
)
from lib_storeadapters.ports import WorkspacePersistenceAdapter


class InMemoryAdapter(WorkspacePersistenceAdapter):
    """Stateless in-memory adapter that deep-copies workspaces on save/load."""

    def __init__(self) -> None:
        self._storage: dict[str, Workspace] = {}

    def save_workspace(self, path: str | Path, workspace: Workspace) -> None:
        """Persist a deep copy of the workspace in memory."""
        self._storage[str(path)] = deepcopy(workspace)

    def load_workspace(self, path: str | Path) -> Workspace:
        """Return a deep copy of the previously saved workspace."""
        return deepcopy(self._storage[str(path)])

    def load_workspace_profiled(
        self, path: str | Path
    ) -> tuple[Workspace, dict[str, Any]]:
        """Load and return a synthetic diagnostic profile."""
        ws = self.load_workspace(path)
        profile = {
            "path": str(path),
            "timings_ms": {},
            "counts": {
                "dimensions": len(ws.dimensions),
                "cubes": len(ws.cubes),
                "views": len(ws.views),
                "rules": len(ws.rules),
            },
            "legacy_ui_state": {},
        }
        return ws, profile


class InMemoryJsonAdapter(WorkspacePersistenceAdapter):
    """In-memory adapter that round-trips workspaces through the JSON payload."""

    def __init__(self) -> None:
        self._storage: dict[str, str] = {}

    def save_workspace(self, path: str | Path, workspace: Workspace) -> None:
        """Persist the workspace as a JSON string in memory."""
        self._storage[str(path)] = workspace_to_json_string(workspace)

    def load_workspace(self, path: str | Path) -> Workspace:
        """Load a workspace from the stored JSON string."""
        return workspace_from_json_string(self._storage[str(path)])

    def load_workspace_profiled(
        self, path: str | Path
    ) -> tuple[Workspace, dict[str, Any]]:
        """Load and return a synthetic diagnostic profile.

        The profile is intentionally minimal because the JSON round-trip is
        not file-based. The returned shape matches ``JsonFileAdapter`` for
        command-layer compatibility.
        """
        ws = self.load_workspace(path)
        profile = {
            "path": str(path),
            "timings_ms": {},
            "counts": {
                "dimensions": len(ws.dimensions),
                "cubes": len(ws.cubes),
                "views": len(ws.views),
                "rules": len(ws.rules),
            },
            "legacy_ui_state": {},
        }
        return ws, profile
