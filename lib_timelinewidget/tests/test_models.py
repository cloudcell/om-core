"""Tests for models module."""

import pytest
from datetime import datetime

from lib_timelinewidget.models import SnapshotInfo, SnapshotType


class TestSnapshotInfo:
    """Tests for SnapshotInfo dataclass."""
    
    def test_basic_creation(self):
        """Test creating a basic SnapshotInfo."""
        snap = SnapshotInfo(
            snapshot_id="snap_001",
            parent_id=None,
            description="Test snapshot",
            branch_name="main",
            type=SnapshotType.MANUAL,
        )
        
        assert snap.snapshot_id == "snap_001"
        assert snap.parent_id is None
        assert snap.description == "Test snapshot"
        assert snap.branch_name == "main"
        assert snap.type == SnapshotType.MANUAL
        assert snap.is_alt_indicator is False
    
    def test_default_values(self):
        """Test default field values."""
        snap = SnapshotInfo(snapshot_id="snap_002")
        
        assert snap.parent_id is None
        assert snap.description == ""
        assert snap.branch_name == "main"
        assert snap.type == SnapshotType.MANUAL
        assert isinstance(snap.created_at, datetime)
        assert snap.child_ids == []
    
    def test_hashable(self):
        """Test SnapshotInfo is hashable (for use in sets/dicts)."""
        snap1 = SnapshotInfo(snapshot_id="snap_001")
        snap2 = SnapshotInfo(snapshot_id="snap_002")
        
        snap_set = {snap1, snap2}
        assert len(snap_set) == 2
        
        snap_dict = {snap1: "first", snap2: "second"}
        assert snap_dict[snap1] == "first"
    
    def test_equality_by_id(self):
        """Test equality is based on snapshot_id."""
        snap1 = SnapshotInfo(snapshot_id="same_id", description="First")
        snap2 = SnapshotInfo(snapshot_id="same_id", description="Second")
        snap3 = SnapshotInfo(snapshot_id="different_id", description="First")
        
        assert snap1 == snap2  # Same ID
        assert snap1 != snap3  # Different ID
    
    def test_alt_indicator(self):
        """Test creating an alt indicator."""
        indicator = SnapshotInfo(
            snapshot_id="__indicator_123",
            parent_id="parent_123",
            description="Branch: experiment",
            branch_name="experiment",
            type=SnapshotType.BRANCH,
            is_alt_indicator=True,
        )
        
        assert indicator.is_alt_indicator is True
        assert indicator.parent_id == "parent_123"


class TestSnapshotType:
    """Tests for SnapshotType enum."""
    
    def test_enum_values(self):
        """Test enum has expected values."""
        assert SnapshotType.MANUAL.value == "manual"
        assert SnapshotType.AUTO.value == "auto"
        assert SnapshotType.BRANCH.value == "branch"
