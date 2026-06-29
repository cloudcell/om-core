"""Timeline controllers - adapters for data providers.

Implements the dual provider pattern:
- TimelineController: Interface for any data provider
- MockProvider: Wraps the existing TimelineEngine (for backward compatibility)
- DataStoreProvider: Wraps lib_datastore (real persistence)

This allows TimelinePanel to work with either mock or real data without changes.
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Callable, Dict, Any
from pathlib import Path
import logging

from lib_timelinewidget import SnapshotInfo
from lib_timelinewidget.engine import TimelineEngine

logger = logging.getLogger(__name__)

# Import lib_datastore (may not be available if not yet created)
try:
    from lib_datastore import SnapshotEngine, SQLiteDataStore, SessionStore
    from lib_datastore.models import SnapshotType
    HAS_DATASTORE = True
except ImportError:
    HAS_DATASTORE = False
    SnapshotEngine = None
    SQLiteDataStore = None
    SessionStore = None
    SnapshotType = None


class TimelineController(ABC):
    """Abstract interface for timeline data providers.
    
    TimelinePanel uses this interface, not caring whether the
    implementation is mock or real datastore.
    """
    
    @abstractmethod
    def load_snapshots(self) -> List[SnapshotInfo]:
        """Load all snapshots for display."""
        pass
    
    @abstractmethod
    def create_snapshot(self, description: str, parent_id: Optional[str] = None) -> Optional[str]:
        """Create a new snapshot/checkpoint."""
        pass
    
    @abstractmethod
    def restore_snapshot(self, snapshot_id: str, new_description: Optional[str] = None) -> Optional[str]:
        """Restore to a snapshot, returns new snapshot ID."""
        pass
    
    @abstractmethod
    def rename_snapshot(self, snapshot_id: str, new_description: str) -> bool:
        """Rename a snapshot."""
        pass
    
    @abstractmethod
    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a snapshot."""
        pass
    
    @abstractmethod
    def get_snapshot(self, snapshot_id: str) -> Optional[SnapshotInfo]:
        """Get a single snapshot by ID."""
        pass
    
    @abstractmethod
    def set_payload_callbacks(self, generator: Callable, restorer: Callable):
        """Set callbacks for payload generation/restoration."""
        pass


class MockProvider(TimelineController):
    """Provider wrapping the existing TimelineEngine (mock data).
    
    This maintains backward compatibility - existing code continues
    to work exactly as before.
    """
    
    def __init__(self):
        self._engine = TimelineEngine()
    
    def load_snapshots(self) -> List[SnapshotInfo]:
        """Get all snapshots from mock engine."""
        return self._engine.get_snapshots()
    
    def create_snapshot(self, description: str, parent_id: Optional[str] = None) -> Optional[str]:
        """Create via mock engine."""
        return self._engine.create_snapshot(description, parent_id)
    
    def restore_snapshot(self, snapshot_id: str, new_description: Optional[str] = None) -> Optional[str]:
        """Restore via mock engine."""
        return self._engine.restore_to_snapshot(snapshot_id, new_description)
    
    def rename_snapshot(self, snapshot_id: str, new_description: str) -> bool:
        """Rename via mock engine."""
        return self._engine.rename_snapshot(snapshot_id, new_description)
    
    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete via mock engine."""
        return self._engine.delete_snapshot(snapshot_id)
    
    def get_snapshot(self, snapshot_id: str) -> Optional[SnapshotInfo]:
        """Get from mock engine."""
        return self._engine.get_snapshot(snapshot_id)
    
    def set_payload_callbacks(self, generator: Callable, restorer: Callable):
        """No-op for mock provider (doesn't use payloads)."""
        pass
    
    def get_engine(self) -> TimelineEngine:
        """Access underlying engine (for direct operations)."""
        return self._engine


class DataStoreProvider(TimelineController):
    """Provider using real lib_datastore persistence.
    
    This is the production-ready implementation that saves
    workspace state to .openm files.
    """
    
    def __init__(self, session_file: Path):
        """Initialize with session file path.
        
        Args:
            session_file: Path to .openm file (created if doesn't exist)
        """
        logger.info(f"__init__() called: session_file={session_file}")
        if not HAS_DATASTORE:
            logger.error("lib_datastore not available")
            raise RuntimeError("lib_datastore not available")
        
        self._session_file = session_file
        self._session_store = SessionStore(session_file)
        self._store: Optional[SQLiteDataStore] = None
        self._engine: Optional[SnapshotEngine] = None
        
        # Try to open existing, or create new
        logger.debug("attempting to open existing session...")
        self._store = self._session_store.open_existing()
        if self._store is None:
            logger.info("no existing session, creating new...")
            self._store = self._session_store.create_new("Timeline Session")
            logger.info("created new session")
        else:
            logger.info("opened existing session")
        logger.info(f"__init__() complete, store={self._store}")
    
    def _ensure_engine(self):
        """Lazy initialization of SnapshotEngine."""
        if self._engine is None and self._store is not None:
            logger.debug("_ensure_engine() creating SnapshotEngine")
            self._engine = SnapshotEngine(self._store)
            logger.debug("SnapshotEngine created")
    
    def load_snapshots(self) -> List[SnapshotInfo]:
        """Load all snapshots from datastore."""
        self._ensure_engine()
        if not self._engine:
            return []
        
        snapshots = self._engine.get_all_snapshots()
        logger.info(f"load_snapshots() loaded {len(snapshots)} snapshots:")
        for s in snapshots:
            logger.info(f"  - {s.snapshot_id[:8]}: desc={s.description!r}, type={s.type}")
        # Convert lib_datastore Snapshot to lib_timelinewidget SnapshotInfo.
        # Widget SnapshotType only knows MANUAL/AUTO/BRANCH; datastore-only types
        # (restored, session_start, milestone) are visualized as MANUAL.
        def _to_widget_type(ds_type):
            if ds_type is None:
                return SnapshotType.MANUAL
            try:
                return SnapshotType(ds_type.value)
            except ValueError:
                return SnapshotType.MANUAL

        return [
            SnapshotInfo(
                snapshot_id=s.snapshot_id,
                parent_id=s.parent_id,
                description=s.description,
                branch_name=s.branch_name,
                created_at=s.created_at,
                type=_to_widget_type(s.type),
                is_delta=getattr(s, 'is_delta', False),
            )
            for s in snapshots
        ]
    
    def create_snapshot(self, description: str, parent_id: Optional[str] = None) -> Optional[str]:
        """Create snapshot in datastore."""
        logger.info(f"create_snapshot() called: description={description!r}, parent_id={parent_id}")
        self._ensure_engine()
        if not self._engine:
            logger.error("create_snapshot() FAILED: engine is None")
            return None
        
        from lib_datastore.models import SnapshotType as DSType
        
        logger.debug("calling SnapshotEngine.create_snapshot()")
        snapshot_id = self._engine.create_snapshot(
            description=description,
            parent_id=parent_id,
            snapshot_type=DSType.MANUAL if DSType else None
        )
        logger.debug(f"SnapshotEngine.create_snapshot() returned {snapshot_id}")
        
        # Persist session metadata
        logger.debug("persisting session metadata via SessionStore.save()")
        save_result = self._session_store.save()
        logger.debug(f"SessionStore.save() returned {save_result}")
        
        return snapshot_id
    
    def restore_snapshot(self, snapshot_id: str, new_description: Optional[str] = None) -> Optional[str]:
        """Restore snapshot from datastore."""
        logger.info(f"restore_snapshot() called: snapshot_id={snapshot_id}, new_description={new_description}")
        self._ensure_engine()
        if not self._engine:
            logger.error("restore_snapshot() FAILED: engine is None")
            return None
        
        logger.debug("calling SnapshotEngine.restore_snapshot()")
        new_id = self._engine.restore_snapshot(snapshot_id, new_description)
        logger.debug(f"SnapshotEngine.restore_snapshot() returned {new_id}")
        
        # Persist session metadata
        logger.debug("persisting session metadata after restore")
        save_result = self._session_store.save()
        logger.debug(f"SessionStore.save() returned {save_result}")
        
        return new_id
    
    def rename_snapshot(self, snapshot_id: str, new_description: str) -> bool:
        """Rename snapshot in datastore."""
        self._ensure_engine()
        if not self._engine:
            return False
        
        return self._engine.rename_snapshot(snapshot_id, new_description)
    
    def update_snapshot_branch(self, snapshot_id: str, branch_name: str) -> bool:
        """Update snapshot branch in datastore."""
        self._ensure_engine()
        if not self._engine:
            return False
        
        return self._engine.update_snapshot_branch(snapshot_id, branch_name)
    
    def update_snapshot_parent(self, snapshot_id: str, new_parent_id: Optional[str]) -> bool:
        """Update snapshot parent_id and base_snapshot_id for delta snapshots.
        
        This is used during restructure operations to keep delta chains valid.
        """
        self._ensure_engine()
        if not self._engine:
            return False
        
        return self._engine.update_snapshot_parent(snapshot_id, new_parent_id)
    
    def update_snapshot_payload(self, snapshot_id: str, payload: Dict[str, Any]) -> bool:
        """Update snapshot payload in datastore."""
        self._ensure_engine()
        if not self._engine:
            return False
        
        return self._engine.update_snapshot_payload(snapshot_id, payload)
    
    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete snapshot from datastore."""
        self._ensure_engine()
        if not self._engine:
            return False
        
        return self._engine.delete_snapshot(snapshot_id)
    
    def get_snapshot(self, snapshot_id: str) -> Optional[SnapshotInfo]:
        """Get snapshot from datastore."""
        self._ensure_engine()
        if not self._engine:
            return None
        
        s = self._engine.get_snapshot(snapshot_id)
        if not s:
            return None
        
        return SnapshotInfo(
            snapshot_id=s.snapshot_id,
            parent_id=s.parent_id,
            description=s.description,
            branch_name=s.branch_name,
            created_at=s.created_at,
            type=SnapshotType(s.type.value) if SnapshotType else s.type,
            is_delta=getattr(s, 'is_delta', False),
        )
    
    def set_payload_callbacks(self, generator: Callable, restorer: Callable):
        """Set payload generation/restoration callbacks."""
        logger.info("set_payload_callbacks() called")
        logger.debug(f"generator={generator}, restorer={restorer}")
        self._ensure_engine()
        if self._engine:
            self._engine._payload_generator = generator
            self._engine._payload_restorer = restorer
            logger.debug("callbacks set on SnapshotEngine")
        else:
            logger.error("could not set callbacks, engine is None")
    
    def get_session_file(self) -> Path:
        """Get the session file path."""
        return self._session_file
    
    def save(self) -> bool:
        """Explicitly save session to disk."""
        logger.info(f"save() called for session_file={self._session_file}")
        result = self._session_store.save()
        logger.debug(f"save() result={result}")
        return result


def create_controller(
    use_real_datastore: bool = False,
    session_file: Optional[Path] = None
) -> TimelineController:
    """Factory function to create appropriate controller.
    
    Args:
        use_real_datastore: If True, use DataStoreProvider, else MockProvider
        session_file: Required if use_real_datastore=True
    
    Returns:
        TimelineController instance
    """
    if use_real_datastore:
        if not HAS_DATASTORE:
            logger.warning("lib_datastore not available, falling back to mock")
            return MockProvider()
        
        if session_file is None:
            raise ValueError("session_file required when use_real_datastore=True")
        
        return DataStoreProvider(session_file)
    
    return MockProvider()
