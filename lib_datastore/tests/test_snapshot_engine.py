"""Tests for lib_datastore.snapshot_engine module.

Tests SnapshotEngine create/restore/compare operations.
"""

import pytest
import tempfile
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lib_datastore import SnapshotEngine, SQLiteDataStore, SnapshotType


class TestSnapshotEngine:
    """Test SnapshotEngine operations."""
    
    @pytest.fixture
    def engine(self):
        """Create SnapshotEngine with temp database."""
        with tempfile.NamedTemporaryFile(suffix=".openm", delete=False) as f:
            db_path = Path(f.name)
        
        store = SQLiteDataStore(db_path)
        eng = SnapshotEngine(store)
        
        yield eng
        
        # Cleanup
        db_path.unlink(missing_ok=True)
    
    def test_create_snapshot(self, engine):
        """Test creating a snapshot."""
        snap_id = engine.create_snapshot("Test Checkpoint")
        
        assert snap_id is not None
        assert len(snap_id) == 36  # UUID format
        
        # Verify stored
        snap = engine.get_snapshot(snap_id)
        assert snap is not None
        assert snap.description == "Test Checkpoint"
        assert snap.type == SnapshotType.MANUAL
    
    def test_create_snapshot_with_parent(self, engine):
        """Test creating snapshot with parent relationship."""
        parent_id = engine.create_snapshot("Parent")
        engine.set_current_state(parent_id, "main")
        
        child_id = engine.create_snapshot("Child")
        
        child = engine.get_snapshot(child_id)
        assert child.parent_id == parent_id
    
    def test_restore_snapshot(self, engine):
        """Test restoring to a snapshot."""
        # Create original
        original_id = engine.create_snapshot("Original")
        
        # Restore to it
        restored_id = engine.restore_snapshot(original_id)
        
        assert restored_id is not None
        assert restored_id != original_id  # Creates new snapshot
        
        # Verify restored snapshot
        restored = engine.get_snapshot(restored_id)
        assert restored.type == SnapshotType.RESTORED
        assert "Original" in restored.description
    
    def test_get_all_snapshots(self, engine):
        """Test getting all snapshots."""
        # Create multiple
        engine.create_snapshot("Snap 1")
        engine.create_snapshot("Snap 2")
        engine.create_snapshot("Snap 3")
        
        all_snaps = engine.get_all_snapshots()
        assert len(all_snaps) == 3
    
    def test_get_snapshot_lineage(self, engine):
        """Test getting snapshot ancestry."""
        # Create chain
        root_id = engine.create_snapshot("Root")
        engine.set_current_state(root_id, "main")
        
        child_id = engine.create_snapshot("Child")
        engine.set_current_state(child_id, "main")
        
        grandchild_id = engine.create_snapshot("Grandchild")
        
        # Get lineage
        lineage = engine.get_snapshot_lineage(grandchild_id)
        
        assert len(lineage) == 3
        assert lineage[0].description == "Root"
        assert lineage[1].description == "Child"
        assert lineage[2].description == "Grandchild"
    
    def test_get_children(self, engine):
        """Test finding child snapshots."""
        parent_id = engine.create_snapshot("Parent")
        
        # Create children with explicit parent_id
        child1_id = engine.create_snapshot("Child 1", parent_id=parent_id)
        child2_id = engine.create_snapshot("Child 2", parent_id=parent_id)
        
        children = engine.get_children(parent_id)
        
        assert len(children) == 2
        child_ids = {c.snapshot_id for c in children}
        assert child1_id in child_ids
        assert child2_id in child_ids
    
    def test_rename_snapshot(self, engine):
        """Test renaming a snapshot."""
        snap_id = engine.create_snapshot("Old Name")
        
        result = engine.rename_snapshot(snap_id, "New Name")
        assert result is True
        
        renamed = engine.get_snapshot(snap_id)
        assert renamed.description == "New Name"
    
    def test_delete_snapshot(self, engine):
        """Test deleting a snapshot."""
        snap_id = engine.create_snapshot("To Delete")
        
        assert engine.get_snapshot(snap_id) is not None
        
        result = engine.delete_snapshot(snap_id)
        assert result is True
        
        assert engine.get_snapshot(snap_id) is None
    
    def test_compare_snapshots(self, engine):
        """Test comparing two snapshots."""
        # Create snapshots with different payloads
        snap1_id = engine.create_snapshot("State A")
        snap2_id = engine.create_snapshot("State B")
        
        # Compare (payloads are empty, so no changes)
        diff = engine.compare_snapshots(snap1_id, snap2_id)
        
        assert "added" in diff
        assert "removed" in diff
        assert "modified" in diff
    
    def test_create_branch(self, engine):
        """Test creating a branch."""
        main_id = engine.create_snapshot("Main")
        
        result = engine.create_branch(main_id, "feature-x")
        assert result is True
        
        # Verify current branch changed
        assert engine.get_current_branch() == "feature-x"
    
    def test_get_tree_structure(self, engine):
        """Test getting tree structure."""
        root_id = engine.create_snapshot("Root")
        engine.set_current_state(root_id, "main")
        
        child_id = engine.create_snapshot("Child")
        
        tree = engine.get_tree_structure()
        
        assert "root" in tree
        assert root_id in tree["root"]
        assert child_id in tree.get(root_id, [])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
