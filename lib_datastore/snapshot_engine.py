"""Snapshot engine - create, restore, and compare snapshots.

NO GUI DEPENDENCIES.
This is the core business logic for snapshot management.
Works with DataStore implementations to persist state.
"""

from typing import Optional, List, Dict, Any, Callable
from datetime import datetime
import uuid
import logging

from .models import Snapshot, Session, SnapshotType
from .datastore import DataStore, SQLiteDataStore

logger = logging.getLogger(__name__)


class SnapshotEngine:
    """Core engine for snapshot operations.
    
    This class provides high-level operations for creating, restoring,
    and managing snapshots. It works with a DataStore implementation
    for persistence.
    
    Usage:
        store = SQLiteDataStore(Path("session.openm"))
        engine = SnapshotEngine(store)
        
        # Create snapshot
        snapshot_id = engine.create_snapshot("Checkpoint 1")
        
        # Restore to snapshot
        engine.restore_snapshot(snapshot_id)
        
        # Get timeline data
        snapshots = engine.get_all_snapshots()
    """
    
    def __init__(self, store: DataStore, payload_generator: Optional[Callable[[], Dict[str, Any]]] = None, payload_restorer: Optional[Callable[[Dict[str, Any]], bool]] = None):
        """Initialize with a datastore and optional payload callbacks.
        
        Args:
            store: DataStore implementation for persistence
            payload_generator: Callable that generates workspace state payload
            payload_restorer: Callable that restores workspace from payload
        """
        self._store = store
        self._payload_generator = payload_generator
        self._payload_restorer = payload_restorer
        
        # Current session state
        self._current_snapshot_id: Optional[str] = None
        self._current_branch: str = "main"
    
    def create_snapshot(
        self,
        description: str,
        parent_id: Optional[str] = None,
        branch_name: Optional[str] = None,
        snapshot_type: SnapshotType = SnapshotType.MANUAL
    ) -> Optional[str]:
        """Create a new snapshot.
        
        Args:
            description: User-provided label for the snapshot
            parent_id: Parent snapshot ID (None for root)
            branch_name: Branch name (defaults to current branch)
            snapshot_type: Snapshot type (MANUAL, AUTO, RESTORED, BRANCH)
        
        Returns:
            New snapshot ID or None if creation failed
        """
        logger.info(f"create_snapshot() called: description={description!r}, parent_id={parent_id}, branch_name={branch_name}, type={snapshot_type}")
        logger.debug(f"_payload_generator set: {self._payload_generator is not None}")
        try:
            # Determine parent and branch
            if parent_id is None and self._current_snapshot_id:
                parent_id = self._current_snapshot_id
            
            if branch_name is None:
                branch_name = self._current_branch
            
            # Generate payload if callback provided
            payload: Dict[str, Any] = {}
            if self._payload_generator:
                logger.debug("calling _payload_generator()")
                payload = self._payload_generator()
                logger.debug(f"_payload_generator returned: {type(payload)}, keys={list(payload.keys()) if isinstance(payload, dict) else 'N/A'}")
            else:
                logger.debug("no _payload_generator, using empty payload")
            
            # Create snapshot object
            snapshot = Snapshot.create(
                description=description,
                parent_id=parent_id,
                branch_name=branch_name,
                snapshot_type=snapshot_type,
                cell_count=payload.get("cell_count", 0)
            )
            
            # Persist to datastore
            logger.debug("calling store.save_snapshot()...")
            save_result = self._store.save_snapshot(snapshot, payload)
            logger.debug(f"store.save_snapshot() returned {save_result}")
            if not save_result:
                return None
            
            # Update current state
            self._current_snapshot_id = snapshot.snapshot_id
            self._current_branch = branch_name
            logger.info(f"create_snapshot() SUCCESS: snapshot_id={snapshot.snapshot_id}")
            return snapshot.snapshot_id
        
        except Exception as e:
            logger.error(f"Error creating snapshot: {e}")
            return None
    
    def restore_snapshot(self, snapshot_id: str, new_description: Optional[str] = None) -> Optional[str]:
        """Restore workspace to a snapshot state.
        
        This creates a new "restored" snapshot on the main branch
        and optionally restores the payload. The restored snapshot
        is stored as a delta from the target snapshot (possibly zero delta).
        
        Args:
            snapshot_id: Snapshot to restore to
            new_description: Optional custom description (defaults to "Restored from ...")
        
        Returns:
            New snapshot ID (the "restored from" snapshot) or None if failed
        """
        try:
            # Load the target snapshot
            target = self._store.get_snapshot_metadata(snapshot_id)
            if not target:
                logger.warning(f"Snapshot not found: {snapshot_id}")
                return None
            
            # Load payload
            payload = self._store.load_snapshot(snapshot_id)
            if payload is None:
                logger.error(f"Could not load payload for: {snapshot_id}")
                return None
            
            # Restore the payload if restorer provided
            if self._payload_restorer:
                ws_dict = payload.get("workspace") if isinstance(payload, dict) else None
                if not ws_dict:
                    logger.error(f"Payload for {snapshot_id} is empty or missing 'workspace' key — snapshot was likely created before payload callbacks were wired or serialization failed")
                if not self._payload_restorer(payload):
                    logger.error(f"Failed to restore payload for: {snapshot_id}")
                    return None

            # Reset the in-memory delta chain so the next delta is computed
            # from the restored state, not from the stale pre-restore state.
            if hasattr(self._store, 'reset_delta_state'):
                self._store.reset_delta_state(base_snapshot_id=snapshot_id)

            # Create "Restored from ..." snapshot as a proper delta
            # This ensures consistent delta chains and allows checkpoints from restored states
            desc = new_description or f"Restored from {target.description or target.snapshot_id[:8]}"
            new_id = self.create_snapshot(
                description=desc,
                parent_id=snapshot_id,  # Parent is the snapshot being restored TO
                branch_name="main",
                snapshot_type=SnapshotType.RESTORED
            )
            
            return new_id
        
        except Exception as e:
            logger.error(f"Error restoring snapshot: {e}")
            return None
    
    def create_branch(self, from_snapshot_id: str, branch_name: str) -> bool:
        """Create a new branch from a snapshot.
        
        Args:
            from_snapshot_id: Snapshot where branch starts
            branch_name: Name for the new branch
        
        Returns:
            True if successful
        """
        try:
            # Verify snapshot exists
            snapshot = self._store.get_snapshot_metadata(from_snapshot_id)
            if not snapshot:
                return False
            
            # Create branch point snapshot
            self._current_snapshot_id = from_snapshot_id
            self._current_branch = branch_name
            
            return True
        
        except Exception as e:
            logger.error(f"Error creating branch: {e}")
            return False
    
    def get_snapshot(self, snapshot_id: str) -> Optional[Snapshot]:
        """Get snapshot metadata by ID."""
        return self._store.get_snapshot_metadata(snapshot_id)
    
    def get_all_snapshots(self) -> List[Snapshot]:
        """Get all snapshots in chronological order."""
        return self._store.list_snapshots()
    
    def get_branch_snapshots(self, branch_name: str) -> List[Snapshot]:
        """Get all snapshots on a specific branch."""
        return self._store.list_snapshots(branch_name)
    
    def get_snapshot_lineage(self, snapshot_id: str) -> List[Snapshot]:
        """Get lineage from root to snapshot."""
        lineage = []
        current_id = snapshot_id
        
        while current_id:
            snap = self._store.get_snapshot_metadata(current_id)
            if not snap:
                break
            lineage.append(snap)
            current_id = snap.parent_id
        
        return list(reversed(lineage))
    
    def get_children(self, snapshot_id: str) -> List[Snapshot]:
        """Get all direct children of a snapshot."""
        all_snapshots = self._store.list_snapshots()
        return [s for s in all_snapshots if s.parent_id == snapshot_id]
    
    def compare_snapshots(self, snapshot_a: str, snapshot_b: str) -> Dict[str, Any]:
        """Compare two snapshots and return differences.
        
        Returns:
            Dict with keys: added, removed, modified
        """
        try:
            payload_a = self._store.load_snapshot(snapshot_a) or {}
            payload_b = self._store.load_snapshot(snapshot_b) or {}
            
            # Get cells from payloads (structure depends on payload generator)
            cells_a = payload_a.get("cells", {})
            cells_b = payload_b.get("cells", {})
            
            result = {
                "added": [],
                "removed": [],
                "modified": [],
            }
            
            # Find added and modified
            for addr, value_b in cells_b.items():
                if addr not in cells_a:
                    result["added"].append({"address": addr, "value": value_b})
                elif cells_a[addr] != value_b:
                    result["modified"].append({
                        "address": addr,
                        "old_value": cells_a[addr],
                        "new_value": value_b,
                    })
            
            # Find removed
            for addr in cells_a:
                if addr not in cells_b:
                    result["removed"].append({"address": addr})
            
            return result
        
        except Exception as e:
            logger.error(f"Error comparing snapshots: {e}")
            return {"added": [], "removed": [], "modified": []}
    
    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a snapshot."""
        return self._store.delete_snapshot(snapshot_id)
    
    def rename_snapshot(self, snapshot_id: str, new_description: str) -> bool:
        """Rename a snapshot.
        
        Note: This requires re-saving the snapshot with new metadata.
        The payload is preserved.
        """
        try:
            # Get existing snapshot
            snapshot = self._store.get_snapshot_metadata(snapshot_id)
            if not snapshot:
                return False
            
            # Load payload
            payload = self._store.load_snapshot(snapshot_id) or {}
            
            # Update description
            snapshot.description = new_description
            
            # Re-save
            return self._store.save_snapshot(snapshot, payload)
        
        except Exception as e:
            logger.error(f"Error renaming snapshot: {e}")
            return False
    
    def update_snapshot_branch(self, snapshot_id: str, branch_name: str) -> bool:
        """Update a snapshot's branch assignment.
        
        This is used after restructure operations to persist branch changes.
        Uses update_branch_only to preserve delta payload integrity.
        """
        try:
            # Use update_branch_only to avoid corrupting delta payload
            return self._store.update_branch_only(snapshot_id, branch_name)
        
        except Exception as e:
            logger.error(f"Error updating snapshot branch: {e}")
            return False
    
    def update_snapshot_parent(self, snapshot_id: str, new_parent_id: Optional[str]) -> bool:
        """Update a snapshot's parent_id and base_snapshot_id.
        
        This is used during restructure operations to rewire delta chains
        when snapshots are moved to alt branches.
        """
        try:
            return self._store.update_snapshot_parent(snapshot_id, new_parent_id)
        
        except Exception as e:
            logger.error(f"Error updating snapshot parent: {e}")
            return False
    
    def update_snapshot_payload(self, snapshot_id: str, payload: Dict[str, Any]) -> bool:
        """Update a snapshot's payload.
        
        This is used to update Session Start with the actual initial workspace state.
        """
        try:
            # Get existing snapshot
            snapshot = self._store.get_snapshot_metadata(snapshot_id)
            if not snapshot:
                return False
            
            # Re-save with new payload — force full save so delta logic never
            # corrupts an explicitly-supplied payload update.
            return self._store.save_snapshot(snapshot, payload, force_full=True)
        
        except Exception as e:
            logger.error(f"Error updating snapshot payload: {e}")
            return False
    
    def get_current_snapshot_id(self) -> Optional[str]:
        """Get the current (most recent) snapshot ID."""
        return self._current_snapshot_id
    
    def get_current_branch(self) -> str:
        """Get the current branch name."""
        return self._current_branch
    
    def set_current_state(self, snapshot_id: Optional[str], branch: str = "main"):
        """Set current snapshot and branch (for initialization)."""
        self._current_snapshot_id = snapshot_id
        self._current_branch = branch
    
    def get_tree_structure(self) -> Dict[str, List[str]]:
        """Get tree structure as parent -> children mapping."""
        all_snapshots = self._store.list_snapshots()
        tree: Dict[str, List[str]] = {}
        
        for snap in all_snapshots:
            parent = snap.parent_id or "root"
            if parent not in tree:
                tree[parent] = []
            tree[parent].append(snap.snapshot_id)
        
        return tree
