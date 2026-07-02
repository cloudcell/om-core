"""Persistence ports.

These abstract interfaces live outside the engine so the engine can be replaced
without changing the persistence contract.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, NewType

WorkspaceId = NewType("WorkspaceId", str)
SnapshotId = NewType("SnapshotId", str)
BranchId = NewType("BranchId", str)
WorkspaceLike = Any


class SnapshotType(str, Enum):
    """Type of snapshot stored in the timeline datastore."""

    AUTO = "auto"
    MANUAL = "manual"
    RESTORED = "restored"
    SESSION_START = "session_start"


@dataclass(frozen=True)
class SnapshotInfo:
    """Lightweight snapshot metadata returned by the snapshot store."""

    snapshot_id: SnapshotId
    workspace_id: WorkspaceId
    description: str
    snapshot_type: SnapshotType
    created_at: datetime  # UTC, timezone-aware
    content_hash: str | None = None
    branch_id: BranchId | None = None
    parent_id: SnapshotId | None = None
    is_delta: bool = False


@dataclass(frozen=True)
class BranchInfo:
    """Lightweight branch metadata returned by the snapshot store."""

    branch_id: BranchId
    workspace_id: WorkspaceId
    name: str
    head_snapshot_id: SnapshotId | None
    created_at: datetime  # UTC, timezone-aware


class WorkspacePersistenceAdapter(ABC):
    """Port for workspace file save/load.

    Lives outside the engine so the engine can be replaced without changing
    the persistence contract.
    """

    @abstractmethod
    def save_workspace(self, path: str | Path, workspace: WorkspaceLike) -> None:
        """Persist the workspace to the given path.

        This method must not mutate the workspace.
        """
        raise NotImplementedError

    @abstractmethod
    def load_workspace(self, path: str | Path) -> WorkspaceLike:
        """Load and return a new workspace instance from the given path."""
        raise NotImplementedError

    @abstractmethod
    def load_workspace_profiled(
        self, path: str | Path
    ) -> tuple[WorkspaceLike, dict]:
        """Load a workspace and return it with a diagnostic profile."""
        raise NotImplementedError


class SnapshotStoreAdapter(ABC):
    """Port for timeline snapshot storage.

    Lives outside the engine. Implementations are owned by the runtime
    command layer.
    """

    @abstractmethod
    def list_snapshots(self, workspace_id: WorkspaceId) -> list[SnapshotInfo]:
        """List all snapshots for a workspace."""
        raise NotImplementedError

    @abstractmethod
    def create_snapshot(
        self,
        workspace_id: WorkspaceId,
        workspace: WorkspaceLike,
        description: str,
        snapshot_type: SnapshotType = SnapshotType.MANUAL,
        branch_id: BranchId | None = None,
        parent_id: SnapshotId | None = None,
        content_hash: str | None = None,
    ) -> SnapshotId:
        """Create a new snapshot and return its stable ID."""
        raise NotImplementedError

    @abstractmethod
    def restore_snapshot(
        self, workspace_id: WorkspaceId, snapshot_id: SnapshotId
    ) -> WorkspaceLike:
        """Restore a snapshot and return the workspace it represents."""
        raise NotImplementedError

    @abstractmethod
    def delete_snapshot(
        self, workspace_id: WorkspaceId, snapshot_id: SnapshotId
    ) -> bool:
        """Delete a snapshot. Return True if it existed."""
        raise NotImplementedError

    @abstractmethod
    def rename_snapshot(
        self,
        workspace_id: WorkspaceId,
        snapshot_id: SnapshotId,
        new_description: str,
    ) -> bool:
        """Rename a snapshot. Return True if it existed."""
        raise NotImplementedError

    @abstractmethod
    def get_latest_snapshot(
        self,
        workspace_id: WorkspaceId,
        snapshot_type: SnapshotType | None = None,
    ) -> SnapshotInfo | None:
        """Return the most recent snapshot, optionally filtered by type."""
        raise NotImplementedError

    @abstractmethod
    def list_branches(self, workspace_id: WorkspaceId) -> list[BranchInfo]:
        """List all branches for a workspace."""
        raise NotImplementedError

    @abstractmethod
    def create_branch(
        self,
        workspace_id: WorkspaceId,
        branch_name: str,
        snapshot_id: SnapshotId | None = None,
    ) -> BranchId:
        """Create a new branch and return its stable ID."""
        raise NotImplementedError

    @abstractmethod
    def get_current_branch(self, workspace_id: WorkspaceId) -> BranchId | None:
        """Return the current branch ID for a workspace, if any."""
        raise NotImplementedError

    @abstractmethod
    def switch_branch(
        self, workspace_id: WorkspaceId, branch_id: BranchId
    ) -> bool:
        """Switch the current branch. Return True on success."""
        raise NotImplementedError

    @abstractmethod
    def update_snapshot_branch(
        self, workspace_id: WorkspaceId, snapshot_id: SnapshotId, branch_id: BranchId
    ) -> bool:
        """Update a snapshot's branch assignment without touching its payload."""
        raise NotImplementedError

    @abstractmethod
    def update_snapshot_parent(
        self, workspace_id: WorkspaceId, snapshot_id: SnapshotId, parent_id: SnapshotId | None
    ) -> bool:
        """Update a snapshot's parent_id and, for delta snapshots, its base."""
        raise NotImplementedError
