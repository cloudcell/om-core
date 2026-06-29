"""Session persistence layer.

NO GUI DEPENDENCIES.
Handles saving/loading complete sessions to/from .openm files.

File format: SQLite database with embedded metadata table.
Extension: .openm (OM session file)
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import json
import sqlite3
import logging

from .datastore import SQLiteDataStore
from .models import Session, Snapshot

logger = logging.getLogger(__name__)


@dataclass
class SessionFileInfo:
    """Metadata about a session file."""
    file_path: Path
    session_id: str
    name: str
    created_at: str
    modified_at: str
    snapshot_count: int
    version: str
    is_valid: bool


class SessionStore:
    """Manages session file I/O.
    
    This is the high-level interface for creating, opening, and managing
    OM session files (.openm extension).
    
    Usage:
        store = SessionStore(Path("workspace.openm"))
        datastore = store.create_new("My Project")
        # ... use datastore to save snapshots ...
        store.save()  # Flush to disk
    """
    
    def __init__(self, file_path: Path):
        self._file_path = Path(file_path)
        self._store: Optional[SQLiteDataStore] = None
        self._session: Optional[Session] = None
    
    def create_new(self, name: str = "Untitled Session") -> SQLiteDataStore:
        """Create new empty session file.
        
        Args:
            name: Human-readable session name
        
        Returns:
            SQLiteDataStore instance ready for use
        
        Raises:
            FileExistsError: If file already exists
        """
        if self._file_path.exists():
            raise FileExistsError(f"Session file already exists: {self._file_path}")
        
        # Ensure parent directory exists
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create the datastore (initializes schema)
        self._store = SQLiteDataStore(self._file_path)
        
        # Create initial session
        self._session = Session.create(name)
        
        # Save session metadata
        self._store.save_session_metadata(self._session)
        
        return self._store
    
    def open_existing(self) -> Optional[SQLiteDataStore]:
        """Open existing session file.
        
        Returns:
            SQLiteDataStore instance or None if file invalid
        """
        if not self._file_path.exists():
            return None
        
        try:
            # Validate it's a valid SQLite file
            self._store = SQLiteDataStore(self._file_path)
            
            # Load session metadata
            self._session = self._store.load_session_metadata()
            
            if self._session is None:
                logger.info(f"No session metadata found in {self._file_path}")
                return None
            
            return self._store
        
        except (sqlite3.Error, Exception) as e:
            logger.error(f"Error opening session file: {e}")
            return None
    
    def save(self) -> bool:
        """Flush session metadata to disk.
        
        Call this periodically or before closing to ensure
        session state is persisted.
        """
        logger.info(f"save() called, file_path={self._file_path}, has_store={self._store is not None}, has_session={self._session is not None}")
        if not self._store or not self._session:
            logger.warning(f"save() FAILED: store={self._store}, session={self._session}")
            return False
        
        try:
            # Update modified time
            from datetime import datetime
            self._session.modified_at = datetime.now()
            logger.debug(f"calling save_session_metadata for session_id={self._session.session_id}")
            result = self._store.save_session_metadata(self._session)
            logger.debug(f"save_session_metadata returned {result}")
            return result
        
        except Exception as e:
            logger.error(f"Error saving session: {e}")
            return False
    
    def get_session(self) -> Optional[Session]:
        """Get current session metadata."""
        return self._session
    
    def get_store(self) -> Optional[SQLiteDataStore]:
        """Get underlying datastore."""
        return self._store
    
    def get_file_path(self) -> Path:
        """Get session file path."""
        return self._file_path
    
    @classmethod
    def get_file_info(cls, file_path: Path) -> SessionFileInfo:
        """Get metadata about a session file without fully loading it.
        
        Useful for file browsers or session managers.
        """
        info = SessionFileInfo(
            file_path=file_path,
            session_id="",
            name="Unknown",
            created_at="",
            modified_at="",
            snapshot_count=0,
            version="1.0",
            is_valid=False,
        )
        
        if not file_path.exists():
            return info
        
        try:
            store = SQLiteDataStore(file_path)
            session = store.load_session_metadata()
            
            if session:
                info.session_id = session.session_id
                info.name = session.name
                info.created_at = session.created_at.isoformat()
                info.modified_at = session.modified_at.isoformat()
                info.snapshot_count = len(session.snapshots)
                info.version = session.version
                info.is_valid = True
        
        except Exception:
            pass
        
        return info
    
    def is_open(self) -> bool:
        """Check if a session is currently open."""
        return self._store is not None
    
    def close(self):
        """Close the session file.
        
        Note: SQLite connections are per-operation, so this mainly
        clears references. Call save() first if you need to persist.
        """
        logger.debug("close() called")
        if self._session:
            logger.debug("close() auto-saving session before close")
            self.save()
        
        self._store = None
        self._session = None
        logger.debug("close() complete, references cleared")
