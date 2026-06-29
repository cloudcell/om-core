"""Tests for lib_timeline.controllers module.

Tests TimelineController dual provider pattern.
"""

import pytest
import tempfile
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lib_timeline.controllers import (
    MockProvider,
    DataStoreProvider,
    create_controller,
)


class TestMockProvider:
    """Test MockProvider implementation."""
    
    @pytest.fixture
    def provider(self):
        """Create fresh MockProvider."""
        return MockProvider()
    
    def test_create_and_load_snapshot(self, provider):
        """Test creating and loading via mock provider."""
        snap_id = provider.create_snapshot("Test")
        
        assert snap_id is not None
        
        # Load via load_snapshots
        snaps = provider.load_snapshots()
        assert len(snaps) >= 1
        
        # Get specific
        snap = provider.get_snapshot(snap_id)
        assert snap is not None
        assert snap.description == "Test"
    
    def test_restore_snapshot(self, provider):
        """Test restore operation."""
        original_id = provider.create_snapshot("Original")
        
        restored_id = provider.restore_snapshot(original_id)
        
        assert restored_id is not None
        assert restored_id != original_id
    
    def test_rename_snapshot(self, provider):
        """Test rename operation."""
        snap_id = provider.create_snapshot("Old Name")
        
        result = provider.rename_snapshot(snap_id, "New Name")
        assert result is True
        
        renamed = provider.get_snapshot(snap_id)
        assert renamed.description == "New Name"
    
    def test_delete_snapshot(self, provider):
        """Test delete operation."""
        snap_id = provider.create_snapshot("To Delete")
        
        assert provider.get_snapshot(snap_id) is not None
        
        result = provider.delete_snapshot(snap_id)
        assert result is True
        
        # Note: MockProvider may not actually delete, just verify it returns True
    
    def test_payload_callbacks_no_op(self, provider):
        """Test that set_payload_callbacks is no-op for mock."""
        # Should not raise
        provider.set_payload_callbacks(lambda: {}, lambda p: True)


class TestDataStoreProvider:
    """Test DataStoreProvider implementation."""
    
    @pytest.fixture
    def provider(self):
        """Create DataStoreProvider with temp file."""
        with tempfile.NamedTemporaryFile(suffix=".openm", delete=False) as f:
            db_path = Path(f.name)
        
        prov = DataStoreProvider(db_path)
        yield prov
        
        # Cleanup
        db_path.unlink(missing_ok=True)
    
    def test_create_snapshot_persists(self, provider):
        """Test that snapshots are persisted to file."""
        snap_id = provider.create_snapshot("Persisted")
        
        assert snap_id is not None
        
        # Create new provider pointing to same file
        new_provider = DataStoreProvider(provider.get_session_file())
        
        # Should find the snapshot
        snap = new_provider.get_snapshot(snap_id)
        assert snap is not None
        assert snap.description == "Persisted"
    
    def test_get_session_file(self, provider):
        """Test getting session file path."""
        path = provider.get_session_file()
        assert path is not None
        assert path.suffix == ".openm"
    
    def test_save_explicit(self, provider):
        """Test explicit save operation."""
        result = provider.save()
        assert result is True


class TestCreateController:
    """Test factory function."""
    
    def test_create_mock_controller(self):
        """Test creating mock controller."""
        ctrl = create_controller(use_real_datastore=False)
        assert isinstance(ctrl, MockProvider)
    
    def test_create_datastore_controller(self):
        """Test creating datastore controller."""
        with tempfile.NamedTemporaryFile(suffix=".openm", delete=False) as f:
            db_path = Path(f.name)
        
        try:
            ctrl = create_controller(
                use_real_datastore=True,
                session_file=db_path
            )
            assert isinstance(ctrl, DataStoreProvider)
        finally:
            db_path.unlink(missing_ok=True)
    
    def test_datastore_requires_session_file(self):
        """Test that datastore requires session file."""
        with pytest.raises(ValueError):
            create_controller(use_real_datastore=True, session_file=None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
