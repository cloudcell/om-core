"""Tests for lib_datastore.datastore module.

Tests SQLiteDataStore CRUD operations and checksum validation.
"""

import pytest
import tempfile
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lib_datastore import SQLiteDataStore, Snapshot, SnapshotType


class TestSQLiteDataStore:
    """Test SQLiteDataStore implementation."""
    
    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".openm", delete=False) as f:
            db_path = Path(f.name)
        
        store = SQLiteDataStore(db_path)
        yield store, db_path
        
        # Cleanup
        db_path.unlink(missing_ok=True)
    
    def test_init_creates_schema(self, temp_db):
        """Test that initialization creates required tables."""
        store, db_path = temp_db
        
        # Database file should exist
        assert db_path.exists()
        
        # Tables should be queryable
        import sqlite3
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row[0] for row in cursor.fetchall()}
            
            assert "snapshots" in tables
            assert "session_metadata" in tables
    
    def test_save_and_load_snapshot(self, temp_db):
        """Test saving and loading a snapshot."""
        store, _ = temp_db
        
        # Create and save snapshot
        snap = Snapshot.create("Test Snapshot")
        payload = {"cells": {"A1": 100, "B2": 200}, "cell_count": 2}
        
        result = store.save_snapshot(snap, payload)
        assert result is True
        
        # Load payload
        loaded = store.load_snapshot(snap.snapshot_id)
        assert loaded is not None
        assert loaded["cells"]["A1"] == 100
        assert loaded["cell_count"] == 2
    
    def test_get_snapshot_metadata(self, temp_db):
        """Test retrieving snapshot metadata."""
        store, _ = temp_db
        
        snap = Snapshot.create(
            "My Snapshot",
            parent_id="parent-123",
            branch_name="feature",
            snapshot_type=SnapshotType.MANUAL,
            cell_count=50
        )
        payload = {"test": "data"}
        
        store.save_snapshot(snap, payload)
        
        # Get metadata only
        metadata = store.get_snapshot_metadata(snap.snapshot_id)
        assert metadata is not None
        assert metadata.description == "My Snapshot"
        assert metadata.parent_id == "parent-123"
        assert metadata.branch_name == "feature"
        assert metadata.cell_count == 50
    
    def test_list_snapshots(self, temp_db):
        """Test listing all snapshots."""
        store, _ = temp_db
        
        # Create multiple snapshots
        snap1 = Snapshot.create("Snap 1", branch_name="main")
        snap2 = Snapshot.create("Snap 2", branch_name="feature")
        snap3 = Snapshot.create("Snap 3", branch_name="main")
        
        store.save_snapshot(snap1, {})
        store.save_snapshot(snap2, {})
        store.save_snapshot(snap3, {})
        
        # List all
        all_snaps = store.list_snapshots()
        assert len(all_snaps) == 3
        
        # List by branch
        main_snaps = store.list_snapshots("main")
        assert len(main_snaps) == 2
    
    def test_delete_snapshot(self, temp_db):
        """Test deleting a snapshot."""
        store, _ = temp_db
        
        snap = Snapshot.create("To Delete")
        store.save_snapshot(snap, {})
        
        # Verify exists
        assert store.get_snapshot_metadata(snap.snapshot_id) is not None
        
        # Delete
        result = store.delete_snapshot(snap.snapshot_id)
        assert result is True
        
        # Verify deleted
        assert store.get_snapshot_metadata(snap.snapshot_id) is None
    
    def test_checksum_validation(self, temp_db):
        """Test that checksums detect data corruption."""
        store, db_path = temp_db
        
        snap = Snapshot.create("Test")
        payload = {"data": "important"}
        store.save_snapshot(snap, payload)
        
        # Manually corrupt the data in database
        import sqlite3
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "UPDATE snapshots SET payload_json = ? WHERE id = ?",
                ('{"data": "corrupted"}', snap.snapshot_id)
            )
            conn.commit()
        
        # Try to load - should fail checksum
        loaded = store.load_snapshot(snap.snapshot_id)
        assert loaded is None  # Checksum mismatch
    
    def test_save_and_load_session_metadata(self, temp_db):
        """Test session metadata persistence."""
        store, _ = temp_db
        
        from lib_datastore import Session
        
        session = Session.create("Test Session")
        snap = Snapshot.create("Test Snap")
        session.add_snapshot(snap)
        
        # Save
        result = store.save_session_metadata(session)
        assert result is True
        
        # Load
        loaded = store.load_session_metadata()
        assert loaded is not None
        assert loaded.session_id == session.session_id
        assert loaded.name == "Test Session"
        assert len(loaded.snapshots) == 1
    
    def test_nonexistent_snapshot(self, temp_db):
        """Test handling of non-existent snapshot."""
        store, _ = temp_db
        
        assert store.load_snapshot("nonexistent") is None
        assert store.get_snapshot_metadata("nonexistent") is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
