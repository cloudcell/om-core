"""SQLite snapshot store adapter.

Wraps lib_datastore's SQLiteDataStore so the rest of the application uses the
SnapshotStoreAdapter port instead of datastore internals.
"""

from __future__ import annotations

import fcntl
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, IO

from lib_datastore.datastore import SQLiteDataStore
from lib_datastore.models import Session as DataStoreSession
from lib_datastore.models import Snapshot as DataStoreSnapshot
from lib_datastore.models import SnapshotType as DataStoreSnapshotType
from lib_datastore.session_store import SessionStore
from lib_openm.model import Workspace
from lib_storeadapters.json_file_adapter import workspace_from_json_string, workspace_to_json_string
from lib_storeadapters.ports import (
    BranchId,
    BranchInfo,
    SnapshotId,
    SnapshotInfo,
    SnapshotStoreAdapter,
    SnapshotType,
    WorkspaceId,
    WorkspaceLike,
)
from lib_storeadapters.serialization import workspace_content_hash

logger = logging.getLogger(__name__)

_CURRENT_BRANCH_KEY = "current_branch"


class SQLiteSnapshotStoreAdapter(SnapshotStoreAdapter):
    """Snapshot store backed by one SQLite file per workspace."""

    def __init__(self, store_dir: str | Path) -> None:
        self._store_dir = Path(store_dir)
        self._store_dir.mkdir(parents=True, exist_ok=True)
        # Cache of opened SessionStore per workspace to avoid repeated opens.
        self._session_stores: dict[WorkspaceId, SessionStore] = {}
        # Cache of opened lock file descriptors per workspace for cross-process
        # serialization of snapshot creation.
        self._lock_fds: dict[WorkspaceId, IO[str]] = {}

    def _db_path(self, workspace_id: WorkspaceId) -> Path:
        return self._store_dir / f"ws_{workspace_id}.timeline.sqlite"

    def _session_store(self, workspace_id: WorkspaceId) -> SessionStore:
        """Return a cached SessionStore, creating it if necessary."""
        if workspace_id not in self._session_stores:
            store = SessionStore(self._db_path(workspace_id))
            store_path = store.get_file_path()
            if store_path.exists():
                store.open_existing()
            else:
                store.create_new(f"Timeline Session {workspace_id}")
            self._session_stores[workspace_id] = store
        return self._session_stores[workspace_id]

    def _store(self, workspace_id: WorkspaceId) -> SQLiteDataStore:
        return self._session_store(workspace_id).get_store()

    def _save_session(self, workspace_id: WorkspaceId, session: DataStoreSession) -> bool:
        """Save the given session directly via the datastore."""
        return self._store(workspace_id).save_session_metadata(session)

    def _lock_path(self, workspace_id: WorkspaceId) -> Path:
        return self._store_dir / f"ws_{workspace_id}.timeline.lock"

    def _acquire_create_lock(self, workspace_id: WorkspaceId) -> None:
        """Acquire an exclusive cross-process lock for snapshot creation.

        This serializes the read-parent / write-snapshot / update-head sequence
        so that two windows/processes creating a snapshot at the same time see a
        consistent main-branch head and form a linear chain instead of siblings.
        """
        fd = self._lock_fds.get(workspace_id)
        if fd is None:
            lock_path = self._lock_path(workspace_id)
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            fd = open(lock_path, "w")
            self._lock_fds[workspace_id] = fd
        fcntl.flock(fd, fcntl.LOCK_EX)

    def _release_create_lock(self, workspace_id: WorkspaceId) -> None:
        """Release the exclusive cross-process lock for snapshot creation."""
        fd = self._lock_fds.get(workspace_id)
        if fd is not None:
            fcntl.flock(fd, fcntl.LOCK_UN)

    @staticmethod
    def _to_port_type(ds_type: DataStoreSnapshotType) -> SnapshotType:
        return SnapshotType(ds_type.value)

    @staticmethod
    def _to_ds_type(port_type: SnapshotType) -> DataStoreSnapshotType:
        return DataStoreSnapshotType(port_type.value)

    def _to_snapshot_info(
        self, ds_snapshot: DataStoreSnapshot, workspace_id: WorkspaceId
    ) -> SnapshotInfo:
        return SnapshotInfo(
            snapshot_id=SnapshotId(ds_snapshot.snapshot_id),
            workspace_id=workspace_id,
            description=ds_snapshot.description,
            snapshot_type=self._to_port_type(ds_snapshot.type),
            created_at=ds_snapshot.created_at,
            content_hash=ds_snapshot.content_hash,
            branch_id=BranchId(ds_snapshot.branch_name) if ds_snapshot.branch_name else None,
            parent_id=SnapshotId(ds_snapshot.parent_id) if ds_snapshot.parent_id else None,
            is_delta=ds_snapshot.is_delta,
        )

    def _to_branch_info(self, branch: Any, workspace_id: WorkspaceId) -> BranchInfo:
        return BranchInfo(
            branch_id=BranchId(branch.name),
            workspace_id=workspace_id,
            name=branch.name,
            head_snapshot_id=branch.head_snapshot_id,
            created_at=branch.created_at if isinstance(branch.created_at, datetime) else datetime.now(timezone.utc),
        )

    def update_snapshot_branch(
        self, workspace_id: WorkspaceId, snapshot_id: SnapshotId, branch_id: BranchId
    ) -> bool:
        store = self._store(workspace_id)
        return store.update_branch_only(str(snapshot_id), str(branch_id))

    def update_snapshot_parent(
        self, workspace_id: WorkspaceId, snapshot_id: SnapshotId, parent_id: SnapshotId | None
    ) -> bool:
        store = self._store(workspace_id)
        return store.update_snapshot_parent(
            str(snapshot_id), str(parent_id) if parent_id else None
        )

    def _current_branch(self, workspace_id: WorkspaceId) -> str:
        store = self._store(workspace_id)
        db_path = str(store._db_path)  # type: ignore[attr-defined]
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.execute(
                    "SELECT value FROM session_metadata WHERE key = ?",
                    (_CURRENT_BRANCH_KEY,),
                )
                row = cursor.fetchone()
                if row:
                    return row[0] or "main"
        except Exception as e:
            logger.error(f"Error reading current branch: {e}")
        return "main"

    def _set_current_branch(self, workspace_id: WorkspaceId, branch_name: str) -> None:
        store = self._store(workspace_id)
        db_path = str(store._db_path)  # type: ignore[attr-defined]
        try:
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO session_metadata (key, value) VALUES (?, ?)",
                    (_CURRENT_BRANCH_KEY, branch_name),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Error setting current branch: {e}")

    def list_snapshots(self, workspace_id: WorkspaceId) -> list[SnapshotInfo]:
        # Do not create the SQLite file on a read-only list; the file should only
        # appear after the first explicit snapshot write.
        db_path = self._db_path(workspace_id)
        if not db_path.exists():
            return []
        store = self._store(workspace_id)
        ds_snapshots = store.list_snapshots()
        return [self._to_snapshot_info(s, workspace_id) for s in ds_snapshots]

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
        # Serialize across processes so two windows cannot read the same head,
        # write two sibling snapshots, and corrupt the main-branch chain.
        self._acquire_create_lock(workspace_id)
        try:
            return self._create_snapshot_locked(
                workspace_id,
                workspace,
                description,
                snapshot_type,
                branch_id,
                parent_id,
                content_hash,
            )
        finally:
            self._release_create_lock(workspace_id)

    def _create_snapshot_locked(
        self,
        workspace_id: WorkspaceId,
        workspace: WorkspaceLike,
        description: str,
        snapshot_type: SnapshotType = SnapshotType.MANUAL,
        branch_id: BranchId | None = None,
        parent_id: SnapshotId | None = None,
        content_hash: str | None = None,
    ) -> SnapshotId:
        store = self._store(workspace_id)

        if content_hash is None:
            content_hash = workspace_content_hash(workspace)

        payload = json.loads(workspace_to_json_string(workspace))
        ds_type = self._to_ds_type(snapshot_type)
        branch_name = str(branch_id) if branch_id else self._current_branch(workspace_id)

        ds_snapshot = DataStoreSnapshot.create(
            description=description,
            branch_name=branch_name,
            snapshot_type=ds_type,
        )
        ds_snapshot.content_hash = content_hash

        if parent_id is not None:
            ds_snapshot.parent_id = str(parent_id)
        else:
            # Determine parent based on the current branch head.
            session = store.load_session_metadata()
            if session is not None and branch_name in session.branches:
                head_id = session.branches[branch_name].head_snapshot_id
                if head_id:
                    ds_snapshot.parent_id = head_id

        store.save_snapshot(ds_snapshot, payload)

        # Update branch head in session metadata.
        session = store.load_session_metadata()
        if session is None:
            session = DataStoreSession.create(f"Timeline Session {workspace_id}")
        if branch_name not in session.branches:
            from lib_datastore.models import Branch as DataStoreBranch
            session.branches[branch_name] = DataStoreBranch(name=branch_name)
        session.branches[branch_name].head_snapshot_id = ds_snapshot.snapshot_id
        self._save_session(workspace_id, session)

        return SnapshotId(ds_snapshot.snapshot_id)

    def restore_snapshot(
        self, workspace_id: WorkspaceId, snapshot_id: SnapshotId
    ) -> WorkspaceLike:
        store = self._store(workspace_id)
        payload = store.load_snapshot(str(snapshot_id))
        if payload is None:
            raise ValueError(f"Snapshot {snapshot_id} not found")

        json_str = json.dumps(payload, default=str, sort_keys=True, separators=(",", ":"))
        workspace = workspace_from_json_string(json_str)

        # Switch current branch to the restored snapshot's branch.
        metadata = store.get_snapshot_metadata(str(snapshot_id))
        if metadata and metadata.branch_name:
            self._set_current_branch(workspace_id, metadata.branch_name)

        # Reset the in-memory delta chain so the next snapshot is computed from
        # the restored state, not from the stale pre-restore state.
        store.reset_delta_state(base_snapshot_id=str(snapshot_id))

        return workspace

    def delete_snapshot(
        self, workspace_id: WorkspaceId, snapshot_id: SnapshotId
    ) -> bool:
        return self._store(workspace_id).delete_snapshot(str(snapshot_id))

    def rename_snapshot(
        self,
        workspace_id: WorkspaceId,
        snapshot_id: SnapshotId,
        new_description: str,
    ) -> bool:
        # lib_datastore does not expose a rename method; update the description directly.
        store = self._store(workspace_id)
        try:
            with sqlite3.connect(store._db_path) as conn:  # type: ignore[attr-defined]
                conn.execute(
                    "UPDATE snapshots SET description = ? WHERE id = ?",
                    (new_description, str(snapshot_id)),
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error renaming snapshot: {e}")
            return False

    def get_latest_snapshot(
        self,
        workspace_id: WorkspaceId,
        snapshot_type: SnapshotType | None = None,
    ) -> SnapshotInfo | None:
        snapshots = self.list_snapshots(workspace_id)
        if snapshot_type is not None:
            snapshots = [s for s in snapshots if s.snapshot_type == snapshot_type]
        if not snapshots:
            return None
        return max(snapshots, key=lambda s: s.created_at)

    def list_branches(self, workspace_id: WorkspaceId) -> list[BranchInfo]:
        store = self._store(workspace_id)
        session = store.load_session_metadata()
        if session is None:
            return []
        return [
            self._to_branch_info(branch, workspace_id)
            for branch in session.branches.values()
        ]

    def create_branch(
        self,
        workspace_id: WorkspaceId,
        branch_name: str,
        snapshot_id: SnapshotId | None = None,
    ) -> BranchId:
        store = self._store(workspace_id)
        session = store.load_session_metadata()
        if session is None:
            session = DataStoreSession.create(f"Timeline Session {workspace_id}")
        from lib_datastore.models import Branch as DataStoreBranch
        if branch_name not in session.branches:
            session.branches[branch_name] = DataStoreBranch(
                name=branch_name, head_snapshot_id=str(snapshot_id) if snapshot_id else None
            )
        self._save_session(workspace_id, session)
        return BranchId(branch_name)

    def get_current_branch(self, workspace_id: WorkspaceId) -> BranchId | None:
        return BranchId(self._current_branch(workspace_id))

    def switch_branch(
        self, workspace_id: WorkspaceId, branch_id: BranchId
    ) -> bool:
        self._set_current_branch(workspace_id, str(branch_id))
        return True
