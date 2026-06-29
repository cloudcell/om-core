"""lib_datastore - Core storage and snapshot infrastructure.

This module provides storage backends for session persistence and snapshot management.
It operates INDEPENDENTLY of GUI code and can be used headlessly.

Architecture:
    models.py           - Core dataclasses (Snapshot, Session, Branch)
    datastore.py        - Abstract storage interface + SQLite implementation
    session_store.py    - Session file I/O (.openm format)
    snapshot_engine.py  - Create/restore/compare snapshots
    payload_generator.py - Workspace serialization adapter

Usage:
    from lib_datastore import SnapshotEngine, SQLiteDataStore
    
    store = SQLiteDataStore(Path("session.openm"))
    engine = SnapshotEngine(store)
    snapshot_id = engine.create_snapshot("Checkpoint 1")
"""

from .models import Snapshot, Session, Branch, SnapshotInfo, SnapshotType
from .datastore import DataStore, SQLiteDataStore
from .session_store import SessionStore, SessionFileInfo
from .snapshot_engine import SnapshotEngine
from .payload_generator import (
    PayloadGenerator,
    PayloadRestorer,
    PayloadContext,
    create_payload_callbacks,
)

__all__ = [
    "Snapshot",
    "Session", 
    "Branch",
    "SnapshotInfo",
    "SnapshotType",
    "DataStore",
    "SQLiteDataStore",
    "SessionStore",
    "SessionFileInfo",
    "SnapshotEngine",
    "PayloadGenerator",
    "PayloadRestorer",
    "PayloadContext",
    "create_payload_callbacks",
]
