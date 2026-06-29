"""Timeline-aware workspace persistence adapter.

Wraps a plain WorkspacePersistenceAdapter for the runtime command save/load path.
Timeline snapshots are created only via the explicit checkpoint command, not by
file save.
"""

from __future__ import annotations

import logging
from pathlib import Path

from lib_storeadapters.ports import WorkspaceLike, WorkspacePersistenceAdapter

logger = logging.getLogger(__name__)


class TimelineAwareWorkspaceAdapter(WorkspacePersistenceAdapter):
    """Wraps a file adapter for the runtime command save/load path.

    This adapter does not create timeline snapshots on save; snapshots are only
    created via the checkpoint command. It should not be used by low-level
    serialization tests, import/export tools, or other code that requires pure
    file persistence.
    """

    def __init__(self, workspace_adapter: WorkspacePersistenceAdapter) -> None:
        self._workspace = workspace_adapter

    def save_workspace(self, path: str | Path, workspace: WorkspaceLike) -> None:
        """Save the workspace file.

        Timeline snapshots are intentionally not created here. Use the explicit
        checkpoint command to create a timeline snapshot.
        """
        self._workspace.save_workspace(path, workspace)

    def load_workspace(self, path: str | Path) -> WorkspaceLike:
        """Load a workspace from the underlying adapter without touching the datastore."""
        return self._workspace.load_workspace(path)

    def load_workspace_profiled(self, path: str | Path) -> tuple[WorkspaceLike, dict]:
        """Load a workspace and profile from the underlying adapter without touching the datastore."""
        return self._workspace.load_workspace_profiled(path)
