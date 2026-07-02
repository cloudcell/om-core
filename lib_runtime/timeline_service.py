"""lib_runtime.timeline_service — runtime timeline service.

Owns checkpoint history, snapshot cadence policy, and checkpoint storage.
Operates on Engine/Workspace supplied by the runtime context.
Does NOT own the live Engine or Workspace.

This service delegates all snapshot storage to a SnapshotStoreAdapter so that
persistence details stay outside the runtime layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from lib_storeadapters.ports import (
    BranchId,
    SnapshotId,
    SnapshotStoreAdapter,
    SnapshotType,
    WorkspaceId,
    WorkspaceLike,
)
from lib_timelinewidget.engine import TimelineEngine
from lib_timelinewidget.models import SnapshotInfo as WidgetSnapshotInfo


@dataclass
class RestoredTimelineState:
    """Result of a timeline restore operation."""

    workspace: WorkspaceLike
    diagnostics: dict


class TimelineService:
    """Runtime-owned timeline service.

    Delegates snapshot creation, restore, and branch operations to the
    supplied SnapshotStoreAdapter. Command handlers access this via
    ctx.services.timeline.
    """

    def __init__(
        self,
        snapshot_adapter: SnapshotStoreAdapter,
        workspace_provider: Callable[[], WorkspaceLike] | None = None,
        workspace_consumer: Callable[[WorkspaceLike], None] | None = None,
    ) -> None:
        self._snapshot_adapter = snapshot_adapter
        self._workspace_provider = workspace_provider
        self._workspace_consumer = workspace_consumer
        self._workspace_id: WorkspaceId | None = None

    def set_workspace_id(self, workspace_id: str | WorkspaceId | None) -> None:
        """Set the workspace ID used for snapshot storage.

        Call this when the active workspace changes so that subsequent
        checkpoints are saved to the correct datastore.
        """
        self._workspace_id = WorkspaceId(str(workspace_id)) if workspace_id else None

    def _get_workspace(self) -> WorkspaceLike:
        if self._workspace_provider is None:
            raise ValueError("TimelineService has no workspace provider")
        workspace = self._workspace_provider()
        if workspace is None:
            raise ValueError("TimelineService workspace provider returned None")
        return workspace

    def _get_workspace_id(self) -> WorkspaceId:
        if self._workspace_id is not None:
            return self._workspace_id
        workspace = self._get_workspace()
        return WorkspaceId(str(workspace.id))

    def create_snapshot(
        self,
        description: str,
        snapshot_type: SnapshotType = SnapshotType.MANUAL,
        parent_id: Optional[str] = None,
    ) -> SnapshotId:
        """Create a snapshot of the current workspace."""
        workspace_id = self._get_workspace_id()
        workspace = self._get_workspace()
        branch_id = self._snapshot_adapter.get_current_branch(workspace_id)
        return self._snapshot_adapter.create_snapshot(
            workspace_id=workspace_id,
            workspace=workspace,
            description=description,
            snapshot_type=snapshot_type,
            branch_id=branch_id,
            parent_id=SnapshotId(parent_id) if parent_id else None,
        )

    def create_checkpoint(
        self,
        description: str,
        parent_id: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> dict:
        """Create a checkpoint snapshot."""
        workspace_id = self._get_workspace_id()
        workspace = self._get_workspace()
        branch_id = BranchId(branch) if branch else self._snapshot_adapter.get_current_branch(workspace_id)
        snapshot_id = self._snapshot_adapter.create_snapshot(
            workspace_id=workspace_id,
            workspace=workspace,
            description=description,
            snapshot_type=SnapshotType.MANUAL,
            branch_id=branch_id,
            parent_id=SnapshotId(parent_id) if parent_id else None,
        )
        return {
            "snapshot_id": snapshot_id,
            "description": description,
            "parent_id": parent_id,
            "branch": branch or str(branch_id),
        }

    def _get_source_description(self, workspace_id: WorkspaceId, checkpoint_id: str) -> str | None:
        """Return the description of the source snapshot, if known."""
        for snap in self._snapshot_adapter.list_snapshots(workspace_id):
            if snap.snapshot_id == checkpoint_id:
                return snap.description
        return None

    def restore_checkpoint(
        self,
        checkpoint_id: str,
        new_description: Optional[str] = None,
    ) -> RestoredTimelineState:
        """Restore workspace to a timeline snapshot.

        Returns the restored workspace and diagnostics. The restored workspace
        is also passed to the configured workspace_consumer so the live engine
        can be updated.
        """
        workspace_id = self._get_workspace_id()
        workspace = self._snapshot_adapter.restore_snapshot(
            workspace_id, SnapshotId(checkpoint_id)
        )

        if self._workspace_consumer is not None:
            self._workspace_consumer(workspace)

        source_desc = self._get_source_description(workspace_id, checkpoint_id)
        desc = new_description or f"Restored from {source_desc or checkpoint_id[:8]}"
        # Restored snapshots always continue on the main branch so that the
        # datastore's current branch is reset to main.
        restored_id = self._snapshot_adapter.create_snapshot(
            workspace_id=workspace_id,
            workspace=workspace,
            description=desc,
            snapshot_type=SnapshotType.RESTORED,
            branch_id=BranchId("main"),
            parent_id=SnapshotId(checkpoint_id),
        )

        # Restructure the timeline so future snapshots move to a single alt
        # branch and the restored snapshot sits on the main spine.
        self._restructure_after_restore(workspace_id, checkpoint_id, restored_id)

        # The restored snapshot is the new head of the main branch; ensure the
        # datastore current branch reflects that so subsequent checkpoints and
        # visual rendering are consistent.
        self._snapshot_adapter.switch_branch(workspace_id, BranchId("main"))

        return RestoredTimelineState(
            workspace=workspace,
            diagnostics={
                "new_snapshot_id": restored_id,
                "restored_checkpoint_id": checkpoint_id,
            },
        )

    def _restructure_after_restore(
        self,
        workspace_id: WorkspaceId,
        checkpoint_id: str,
        restored_id: SnapshotId,
    ) -> None:
        """Move future snapshots to alt branch and keep restored snapshot on main."""
        snapshots = self._snapshot_adapter.list_snapshots(workspace_id)
        if not snapshots:
            return

        original_state = {
            str(s.snapshot_id): {
                "branch_id": s.branch_id,
                "parent_id": s.parent_id,
            }
            for s in snapshots
        }

        def _to_widget(s) -> WidgetSnapshotInfo:
            return WidgetSnapshotInfo(
                snapshot_id=str(s.snapshot_id),
                parent_id=str(s.parent_id) if s.parent_id is not None else None,
                description=s.description,
                branch_name=str(s.branch_id) if s.branch_id is not None else "main",
                created_at=s.created_at,
                type=SnapshotType(s.snapshot_type.value),
            )

        engine = TimelineEngine()
        engine.load_snapshots([_to_widget(s) for s in snapshots])
        engine.restructure_for_restore(checkpoint_id, str(restored_id))

        for s in engine.get_snapshots():
            sid = s.snapshot_id
            state = original_state.get(sid, {})
            new_branch = BranchId(s.branch_name)
            old_branch = state.get("branch_id")
            if old_branch is None or str(old_branch) != str(new_branch):
                self._snapshot_adapter.update_snapshot_branch(
                    workspace_id, SnapshotId(sid), new_branch
                )
            new_parent = SnapshotId(s.parent_id) if s.parent_id is not None else None
            old_parent = state.get("parent_id")
            if old_parent != new_parent:
                self._snapshot_adapter.update_snapshot_parent(
                    workspace_id, SnapshotId(sid), new_parent
                )

    def load_snapshots(self) -> list[Any]:
        """Load all snapshots for display."""
        return self._snapshot_adapter.list_snapshots(self._get_workspace_id())

    def rename_checkpoint(
        self, checkpoint_id: str, description: str
    ) -> dict[str, str]:
        """Rename a checkpoint snapshot."""
        workspace_id = self._get_workspace_id()
        self._snapshot_adapter.rename_snapshot(
            workspace_id, SnapshotId(checkpoint_id), description
        )
        return {"checkpoint_id": checkpoint_id, "description": description}

    def delete_checkpoint(self, checkpoint_id: str) -> dict[str, str]:
        """Delete a checkpoint snapshot."""
        workspace_id = self._get_workspace_id()
        self._snapshot_adapter.delete_snapshot(
            workspace_id, SnapshotId(checkpoint_id)
        )
        return {"checkpoint_id": checkpoint_id}

    def create_branch(self, branch_name: str) -> BranchId:
        """Create a new branch for the current workspace."""
        return self._snapshot_adapter.create_branch(
            self._get_workspace_id(), branch_name
        )

    def switch_branch(self, branch_id: BranchId) -> bool:
        """Switch the current branch."""
        return self._snapshot_adapter.switch_branch(self._get_workspace_id(), branch_id)

    def get_current_branch(self) -> BranchId | None:
        """Return the current branch for the current workspace."""
        return self._snapshot_adapter.get_current_branch(self._get_workspace_id())
