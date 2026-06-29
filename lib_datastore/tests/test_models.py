"""Tests for lib_datastore.models module.

Tests Snapshot, Session, Branch dataclasses and their serialization.
"""

import pytest
from datetime import datetime
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lib_datastore.models import Snapshot, Session, Branch, SnapshotType


class TestSnapshot:
    """Test Snapshot dataclass."""
    
    def test_create_generates_id(self):
        """Test that create() generates a unique ID."""
        snap1 = Snapshot.create("Test 1")
        snap2 = Snapshot.create("Test 2")
        
        assert snap1.snapshot_id != snap2.snapshot_id
        assert len(snap1.snapshot_id) == 36  # UUID format
    
    def test_create_sets_defaults(self):
        """Test that create() sets default values correctly."""
        snap = Snapshot.create("My Snapshot")
        
        assert snap.description == "My Snapshot"
        assert snap.branch_name == "main"
        assert snap.parent_id is None
        assert snap.type == SnapshotType.MANUAL
        assert snap.cell_count == 0
        assert snap.tags == []
    
    def test_create_with_parent(self):
        """Test creating snapshot with parent."""
        parent = Snapshot.create("Parent")
        child = Snapshot.create("Child", parent_id=parent.snapshot_id)
        
        assert child.parent_id == parent.snapshot_id
    
    def test_to_dict_roundtrip(self):
        """Test that to_dict/from_dict preserves all data."""
        original = Snapshot.create(
            description="Test Snapshot",
            parent_id="parent-123",
            branch_name="feature-branch",
            snapshot_type=SnapshotType.AUTO,
            cell_count=100
        )
        original.tags = ["tag1", "tag2"]
        
        data = original.to_dict()
        restored = Snapshot.from_dict(data)
        
        assert restored.snapshot_id == original.snapshot_id
        assert restored.description == original.description
        assert restored.parent_id == original.parent_id
        assert restored.branch_name == original.branch_name
        assert restored.type == original.type
        assert restored.cell_count == original.cell_count
        assert restored.tags == original.tags
    
    def test_snapshot_type_enum(self):
        """Test SnapshotType enum values."""
        assert SnapshotType.AUTO.value == "auto"
        assert SnapshotType.MANUAL.value == "manual"
        assert SnapshotType.RESTORED.value == "restored"
        assert SnapshotType.BRANCH.value == "branch"


class TestBranch:
    """Test Branch dataclass."""
    
    def test_default_values(self):
        """Test Branch default values."""
        branch = Branch(name="main")
        
        assert branch.name == "main"
        assert branch.head_snapshot_id is None
        assert branch.parent_branch is None
        assert branch.is_active is True
    
    def test_to_dict_roundtrip(self):
        """Test Branch serialization roundtrip."""
        original = Branch(
            name="feature-x",
            head_snapshot_id="snap-123",
            parent_branch="main",
            fork_snapshot_id="snap-000",
            is_active=True
        )
        
        data = original.to_dict()
        restored = Branch.from_dict(data)
        
        assert restored.name == original.name
        assert restored.head_snapshot_id == original.head_snapshot_id
        assert restored.parent_branch == original.parent_branch
        assert restored.is_active == original.is_active


class TestSession:
    """Test Session dataclass."""
    
    def test_create_generates_ids(self):
        """Test that Session.create() generates unique ID."""
        session1 = Session.create("Session 1")
        session2 = Session.create("Session 2")
        
        assert session1.session_id != session2.session_id
        assert session1.name == "Session 1"
        assert session2.name == "Session 2"
    
    def test_add_snapshot(self):
        """Test adding snapshots to session."""
        session = Session.create("Test")
        snap = Snapshot.create("Snapshot 1")
        
        session.add_snapshot(snap)
        
        assert len(session.snapshots) == 1
        assert session.snapshots[snap.snapshot_id] == snap
        assert session.branches["main"].head_snapshot_id == snap.snapshot_id
    
    def test_get_branch_snapshots(self):
        """Test filtering snapshots by branch."""
        session = Session.create("Test")
        
        main_snap = Snapshot.create("Main", branch_name="main")
        feature_snap = Snapshot.create("Feature", branch_name="feature")
        
        session.add_snapshot(main_snap)
        session.add_snapshot(feature_snap)
        
        main_only = session.get_branch_snapshots("main")
        assert len(main_only) == 1
        assert main_only[0].snapshot_id == main_snap.snapshot_id
    
    def test_get_snapshot_lineage(self):
        """Test getting snapshot ancestry."""
        session = Session.create("Test")
        
        # Create chain: root -> child -> grandchild
        root = Snapshot.create("Root")
        child = Snapshot.create("Child", parent_id=root.snapshot_id)
        grandchild = Snapshot.create("Grandchild", parent_id=child.snapshot_id)
        
        session.add_snapshot(root)
        session.add_snapshot(child)
        session.add_snapshot(grandchild)
        
        lineage = session.get_snapshot_lineage(grandchild.snapshot_id)
        
        assert len(lineage) == 3
        assert lineage[0].snapshot_id == root.snapshot_id
        assert lineage[1].snapshot_id == child.snapshot_id
        assert lineage[2].snapshot_id == grandchild.snapshot_id
    
    def test_to_dict_roundtrip(self):
        """Test Session serialization roundtrip."""
        original = Session.create("Test Session")
        snap = Snapshot.create("Test Snap")
        original.add_snapshot(snap)
        
        data = original.to_dict()
        restored = Session.from_dict(data)
        
        assert restored.session_id == original.session_id
        assert restored.name == original.name
        assert len(restored.snapshots) == 1
        assert snap.snapshot_id in restored.snapshots


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
