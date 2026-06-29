"""Storage backends for snapshot persistence.

NO GUI DEPENDENCIES.
Provides abstract interface and SQLite implementation.
"""

from abc import ABC, abstractmethod
from pathlib import Path
import sqlite3
import json
import hashlib
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from copy import deepcopy

from .models import Snapshot, Session, Branch, SnapshotType

logger = logging.getLogger(__name__)
from .datastoreconf import (
    DATASTORE_SAVEDELTAS,
    DATASTORE_MAX_DELTA_CHAIN,
    DATASTORE_FULL_SNAPSHOT_EVERY,
    DATASTORE_VERIFY_CHECKSUMS,
)
from .delta_engine import compute_delta, apply_delta, _compute_checksum, DeltaChain, DeltaChecksumError, PayloadChecksumError


class DataStore(ABC):
    """Abstract interface for snapshot storage.
    
    Implementations must provide CRUD operations for snapshots
    and session metadata.
    """
    
    @abstractmethod
    def save_snapshot(self, snapshot: Snapshot, payload: Dict[str, Any]) -> bool:
        """Store snapshot with its payload.
        
        Args:
            snapshot: Snapshot metadata
            payload: Workspace state data (will be JSON serialized)
        
        Returns:
            True if successful
        """
        pass
    
    @abstractmethod
    def load_snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """Load snapshot payload by ID.
        
        Returns:
            Payload dict or None if not found
        """
        pass
    
    @abstractmethod
    def get_snapshot_metadata(self, snapshot_id: str) -> Optional[Snapshot]:
        """Get snapshot metadata without loading payload."""
        pass
    
    @abstractmethod
    def list_snapshots(self, branch_name: Optional[str] = None) -> List[Snapshot]:
        """List all snapshots, optionally filtered by branch."""
        pass
    
    @abstractmethod
    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a snapshot and its payload."""
        pass
    
    @abstractmethod
    def save_session_metadata(self, session: Session) -> bool:
        """Save session-level metadata."""
        pass
    
    @abstractmethod
    def load_session_metadata(self) -> Optional[Session]:
        """Load session metadata."""
        pass


class SQLiteDataStore(DataStore):
    """SQLite-backed storage for snapshots.
    
    Schema:
        snapshots:
            - id (TEXT PRIMARY KEY)
            - parent_id (TEXT, nullable)
            - branch_name (TEXT, default 'main')
            - description (TEXT)
            - created_at (TEXT ISO8601)
            - type (TEXT)
            - cell_count (INTEGER)
            - tags (TEXT - JSON array)
            - payload_json (TEXT)
            - checksum (TEXT)
            - content_hash (TEXT, nullable)
        
        session_metadata:
            - key (TEXT PRIMARY KEY)
            - value (TEXT)
    
    File extension: .openm (OM session file)
    """
    
    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._init_schema()

        # Delta chain management (only used when DATASTORE_SAVEDELTAS=True)
        self._delta_chain: Optional[DeltaChain] = None
        self._last_full_snapshot_id: Optional[str] = None
        self._auto_save_count = 0

        # Recover delta-chain state from existing snapshots so restarts
        # continue the delta chain instead of resetting to full snapshots.
        self._recover_delta_state()
    
    def _init_schema(self):
        """Initialize database tables."""
        with sqlite3.connect(self._db_path) as conn:
            # Snapshots table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    id TEXT PRIMARY KEY,
                    parent_id TEXT,
                    branch_name TEXT DEFAULT 'main',
                    description TEXT,
                    created_at TEXT,
                    type TEXT DEFAULT 'manual',
                    cell_count INTEGER DEFAULT 0,
                    tags TEXT,
                    payload_json TEXT,
                    checksum TEXT,
                    is_delta BOOLEAN DEFAULT 0,
                    base_snapshot_id TEXT,
                    payload_checksum TEXT,
                    delta_chain_index INTEGER DEFAULT 0,
                    content_hash TEXT,
                    FOREIGN KEY (parent_id) REFERENCES snapshots(id),
                    FOREIGN KEY (base_snapshot_id) REFERENCES snapshots(id)
                )
            """)
            
            # Migration: add payload_checksum column if it doesn't exist
            try:
                conn.execute("ALTER TABLE snapshots ADD COLUMN payload_checksum TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists
            
            # Migration: add delta_chain_index column if it doesn't exist
            try:
                conn.execute("ALTER TABLE snapshots ADD COLUMN delta_chain_index INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass  # Column already exists

            # Migration: add content_hash column if it doesn't exist
            try:
                conn.execute("ALTER TABLE snapshots ADD COLUMN content_hash TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists
            
            # Session metadata table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS session_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            
            # Indexes for performance
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_branch 
                ON snapshots(branch_name)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_parent 
                ON snapshots(parent_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_created 
                ON snapshots(created_at)
            """)
    
    def _compute_checksum(self, data: str) -> str:
        """Compute MD5 checksum for data integrity."""
        return hashlib.md5(data.encode()).hexdigest()
    
    def reset_delta_state(self, base_snapshot_id: Optional[str] = None) -> None:
        """Invalidate the in-memory delta chain.

        Call this after a restore operation or any branch restructure that
        changes the logical sequence of snapshots.  The next save_snapshot will
        re-initialise the chain from the given base (or from the DB state if
        none is provided).
        """
        self._delta_chain = None
        if base_snapshot_id:
            self._last_full_snapshot_id = base_snapshot_id
            self._auto_save_count = 0
        else:
            # Fall back to the most recent full snapshot in the DB
            self._recover_delta_state()
        logger.info(f"Delta state reset: base={self._last_full_snapshot_id}, chain cleared")

    def _recover_delta_state(self) -> None:
        """Recover delta-chain state from existing snapshots in the DB.

        On restart the DataStore instance is recreated, so in-memory
        counters (_last_full_snapshot_id, _auto_save_count) are lost.
        Scan the DB to reconstruct them so new snapshots continue the
        delta chain instead of resetting to full snapshots.
        """
        try:
            with sqlite3.connect(self._db_path) as conn:
                # Find the most recent snapshot with delta_chain_index == 0 (full base)
                cursor = conn.execute(
                    """SELECT id FROM snapshots
                       WHERE delta_chain_index = 0
                       ORDER BY created_at DESC LIMIT 1"""
                )
                row = cursor.fetchone()
                if row and row[0]:
                    self._last_full_snapshot_id = row[0]

                # Count how many snapshots have been created since that base
                if self._last_full_snapshot_id:
                    cursor = conn.execute(
                        """SELECT COUNT(*) FROM snapshots
                           WHERE created_at > (
                               SELECT created_at FROM snapshots WHERE id = ?
                           )""",
                        (self._last_full_snapshot_id,)
                    )
                    row = cursor.fetchone()
                    self._auto_save_count = row[0] if row else 0
        except sqlite3.Error:
            # Leave defaults (fresh session)
            pass

    def _should_save_full(self, snapshot: Snapshot, force_full: bool = False) -> bool:
        """Determine if we should save a full snapshot or delta."""
        if not DATASTORE_SAVEDELTAS:
            return True
        if force_full:
            return True
        # Always save full for session start or milestones
        if snapshot.type in (SnapshotType.SESSION_START, SnapshotType.MILESTONE):
            return True
        # Force full every N auto-saves (0 = disabled)
        if DATASTORE_FULL_SNAPSHOT_EVERY > 0 and self._auto_save_count >= DATASTORE_FULL_SNAPSHOT_EVERY:
            return True
        return False
    
    def save_snapshot(self, snapshot: Snapshot, payload: Dict[str, Any], 
                      force_full: bool = False) -> bool:
        """Store snapshot with payload.
        
        Args:
            snapshot: The snapshot metadata
            payload: Full workspace payload
            force_full: If True, always save full payload regardless of delta setting
        """
        logger.info(f"save_snapshot() called: snapshot_id={snapshot.snapshot_id}, db_path={self._db_path}")
        
        is_full = self._should_save_full(snapshot, force_full)
        is_delta = False
        base_snapshot_id = None
        stored_payload = payload
        
        checksum = None
        payload_checksum = None
        
        # Check persisted delta chain index BEFORE computing delta
        # This ensures we don't compute a delta just to throw it away
        if not is_full and DATASTORE_MAX_DELTA_CHAIN > 0 and snapshot.parent_id:
            parent_meta = self.get_snapshot_metadata(snapshot.parent_id)
            if parent_meta:
                would_be_index = parent_meta.delta_chain_index + 1
                if would_be_index >= DATASTORE_MAX_DELTA_CHAIN:
                    logger.info(f"Chain limit reached ({would_be_index} >= {DATASTORE_MAX_DELTA_CHAIN}), forcing full snapshot")
                    is_full = True
        
        if DATASTORE_SAVEDELTAS and not is_full and self._last_full_snapshot_id:
            # Compute delta from last known state
            if self._delta_chain is None:
                self._delta_chain = DeltaChain(max_chain_length=DATASTORE_MAX_DELTA_CHAIN)
                # Try to load base payload
                base_payload = self._load_raw_payload(self._last_full_snapshot_id)
                if base_payload is not None:
                    self._delta_chain.set_base(self._last_full_snapshot_id, base_payload)
            
            if self._delta_chain and self._delta_chain.base_payload is not None:
                # Check if chain is full BEFORE adding this delta
                if self._delta_chain.needs_new_base():
                    # Force full snapshot to start new chain
                    is_full = True
                    self._last_full_snapshot_id = None
                    self._delta_chain = None
                    self._auto_save_count = 0
                else:
                    delta = self._delta_chain.add_delta(snapshot.snapshot_id, payload)

                    # Get checksums from DeltaChain (computed during add_delta)
                    delta_checksum, payload_checksum = self._delta_chain.get_last_checksums()

                    # Set base snapshot ID for delta reconstruction (needed for ALL deltas)
                    base_snapshot_id = snapshot.parent_id if snapshot.parent_id else self._last_full_snapshot_id

                    if delta.get("unchanged"):
                        # No changes - delta already has correct structure from compute_delta
                        logger.info("No changes detected, saving zero-delta")
                        # Store the delta (not the full payload) for zero-delta
                        stored_payload = delta
                        is_delta = True
                        is_full = False
                    else:
                        # Store delta directly (raw diff, no wrapper)
                        stored_payload = delta
                        is_delta = True
                        is_full = False

                    # Prevent delta from pointing to itself as base (would cause infinite recursion)
                    if base_snapshot_id == snapshot.snapshot_id:
                        logger.info("Delta base would be same as snapshot, forcing full")
                        is_full = True
                        is_delta = False
                        base_snapshot_id = None
                        stored_payload = payload
            else:
                # Can't compute delta, fall back to full
                is_full = True
        elif not is_full and self._last_full_snapshot_id is None:
            # No base for delta, must save full
            is_full = True
        
        # Track delta chain index (0 = full base, 1+ = delta position)
        if is_full:
            delta_chain_index = 0
            self._last_full_snapshot_id = snapshot.snapshot_id
            self._delta_chain = None
            self._auto_save_count = 0
        else:
            # Continue delta chain from parent snapshot
            parent_index = 0
            if snapshot.parent_id:
                parent_meta = self.get_snapshot_metadata(snapshot.parent_id)
                if parent_meta:
                    parent_index = parent_meta.delta_chain_index
            # For RESTORED type, continue chain from restored snapshot
            # For regular snapshots, continue from parent's index
            delta_chain_index = parent_index + 1
            self._auto_save_count += 1
        
        # Check if we've exceeded the max delta chain limit
        if (DATASTORE_MAX_DELTA_CHAIN > 0 and 
            delta_chain_index >= DATASTORE_MAX_DELTA_CHAIN and 
            not is_full):
            # Force full snapshot to reset chain
            is_full = True
            delta_chain_index = 0
            self._last_full_snapshot_id = snapshot.snapshot_id
            self._delta_chain = None
            self._auto_save_count = 0
            stored_payload = payload  # Use full payload
        
        # Update snapshot object
        snapshot.delta_chain_index = delta_chain_index
        snapshot.is_delta = is_delta
        
        try:
            # Use canonical JSON format (sorted keys, compact separators) for consistency
            payload_json = json.dumps(stored_payload, default=str, sort_keys=True, separators=(',', ':'))
            
            # For deltas, use the pre-computed checksum from DeltaChain
            # For full snapshots, compute checksum on the stored JSON
            if is_delta and delta_checksum:
                checksum = delta_checksum
            else:
                checksum = self._compute_checksum(payload_json)
            
            logger.info(f"payload size={len(payload_json)} bytes (delta={is_delta})")
            
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO snapshots 
                    (id, parent_id, branch_name, description, created_at,
                     type, cell_count, tags, payload_json, checksum, is_delta,
                     base_snapshot_id, payload_checksum, delta_chain_index, content_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot.snapshot_id,
                        snapshot.parent_id,
                        snapshot.branch_name,
                        snapshot.description,
                        snapshot.created_at.isoformat(),
                        snapshot.type.value,
                        snapshot.cell_count,
                        json.dumps(snapshot.tags),
                        payload_json,
                        checksum,
                        is_delta,
                        base_snapshot_id,
                        payload_checksum,
                        delta_chain_index,
                        snapshot.content_hash,
                    )
                )
                conn.commit()
            
            # Update payload checksum in snapshot (for deltas: expected reconstructed payload checksum)
            snapshot.payload_checksum = payload_checksum if is_delta else checksum
            logger.info(f"save_snapshot() SUCCESS: snapshot_id={snapshot.snapshot_id} (delta={is_delta})")
            return True
        
        except sqlite3.Error as e:
            logger.error(f"Error saving snapshot: {e}")
            return False
    
    def _load_raw_payload(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """Load raw payload without delta reconstruction."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.execute(
                    "SELECT payload_json, is_delta FROM snapshots WHERE id = ?",
                    (snapshot_id,)
                )
                row = cursor.fetchone()
                if row:
                    # Content is stored raw - parse and return directly
                    return json.loads(row[0])
                return None
        except (sqlite3.Error, json.JSONDecodeError):
            return None
    
    def _get_last_delta_chain_index(self) -> int:
        """Get the delta chain index of the most recent snapshot.
        
        Returns:
            The delta_chain_index value from the last snapshot, or 0 if no snapshots exist.
        """
        try:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.execute(
                    """SELECT delta_chain_index FROM snapshots 
                       ORDER BY created_at DESC LIMIT 1"""
                )
                row = cursor.fetchone()
                if row and row[0] is not None:
                    return row[0]
                return 0
        except sqlite3.Error:
            return 0
    
    def load_snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """Load snapshot payload by ID.
        
        Automatically reconstructs full payload from delta if needed.
        """
        try:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.execute(
                    """SELECT payload_json, checksum, is_delta, base_snapshot_id 
                       FROM snapshots WHERE id = ?""",
                    (snapshot_id,)
                )
                row = cursor.fetchone()
                
                if not row:
                    return None
                
                payload_json, stored_checksum, is_delta, base_snapshot_id = row
                
                # Verify checksum
                computed_checksum = self._compute_checksum(payload_json)
                if computed_checksum != stored_checksum:
                    logger.warning(f"Checksum mismatch for {snapshot_id}")
                    return None
                
                stored_payload = json.loads(payload_json)
                
                # Handle reference snapshots (e.g., "Restored from X")
                if stored_payload.get("_ref"):
                    # This is a reference - load the target snapshot's payload
                    target_id = stored_payload["_ref"]
                    return self.load_snapshot(target_id)
                
                # If this is a delta, reconstruct full payload
                if is_delta and base_snapshot_id and DATASTORE_SAVEDELTAS:
                    result = self._reconstruct_from_delta(stored_payload, base_snapshot_id, snapshot_id)
                else:
                    # Full snapshot: stored_payload IS the raw payload already
                    result = stored_payload
                
                # JSON round-trip to ensure consistent structure regardless of source
                if result is not None:
                    result_json = json.dumps(result, default=str, sort_keys=True, separators=(',', ':'))
                    result = json.loads(result_json)
                return result
        
        except (sqlite3.Error, json.JSONDecodeError) as e:
            logger.error(f"Error loading snapshot: {e}")
            return None
    
    def _reconstruct_from_delta(self, stored_payload: Dict, base_snapshot_id: str, 
                                 target_snapshot_id: str) -> Optional[Dict[str, Any]]:
        """Reconstruct full payload by applying delta chain from base."""
        # stored_payload IS the delta directly (raw diff, no wrapper)
        delta = stored_payload
        
        if delta.get("_full"):
            # This is actually a full snapshot disguised as delta
            return delta.get("payload")
        
        # Load base payload
        base_payload = self._load_raw_payload(base_snapshot_id)
        if base_payload is None:
            logger.error(f"Cannot load base snapshot {base_snapshot_id}")
            return None
        
        # If base is also a delta, recursively reconstruct
        try:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.execute(
                    "SELECT is_delta, base_snapshot_id FROM snapshots WHERE id = ?",
                    (base_snapshot_id,)
                )
                row = cursor.fetchone()
                if row and row[0]:  # is_delta
                    base_payload = self._reconstruct_from_delta(base_payload, row[1], base_snapshot_id)
                    if base_payload is None:
                        return None
        except sqlite3.Error:
            pass
        
        # JSON round-trip base payload to ensure consistent structure for delta application
        # This ensures the base matches the state when the delta was originally computed
        base_json = json.dumps(base_payload, default=str, sort_keys=True, separators=(',', ':'))
        base_payload = json.loads(base_json)

        # Get checksums from DB for verification
        delta_checksum = None
        payload_checksum = None
        try:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.execute(
                    "SELECT checksum, payload_checksum FROM snapshots WHERE id = ?",
                    (target_snapshot_id,)
                )
                row = cursor.fetchone()
                if row:
                    delta_checksum = row[0]  # Checksum of delta content
                    payload_checksum = row[1]  # Expected payload checksum
        except sqlite3.Error:
            pass

        # Add _target_checksum to delta for verification
        if payload_checksum:
            delta = dict(delta)  # Copy to avoid modifying stored
            delta["_target_checksum"] = payload_checksum

        # Debug: print what we're working with
        import hashlib
        import json as json_mod
        base_checksum = hashlib.md5(json_mod.dumps(base_payload, default=str, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        logger.debug(f"target={target_snapshot_id[:8]}, base={base_snapshot_id[:8]}, base_checksum={base_checksum[:16]}")
        logger.debug(f"delta keys={list(delta.keys())}, expected_payload_checksum={payload_checksum[:16] if payload_checksum else 'none'}")
        
        # Apply delta to base with checksum verification
        try:
            reconstructed = apply_delta(base_payload, delta, verify=True, delta_checksum=delta_checksum)
            reconstructed_json = json_mod.dumps(reconstructed, default=str, sort_keys=True, separators=(',', ':'))
            reconstructed_checksum = hashlib.md5(reconstructed_json.encode()).hexdigest()
            logger.debug(f"reconstructed checksum={reconstructed_checksum[:16]}, expected={payload_checksum[:16] if payload_checksum else 'none'}")
            return reconstructed
        except (DeltaChecksumError, PayloadChecksumError) as e:
            logger.error(f"Checksum verification failed for delta {target_snapshot_id}: {e}")
            raise
    
    def create_full_snapshot(self, snapshot_id: str) -> bool:
        """Force creation of a full snapshot from an existing delta.
        
        Useful for periodic consolidation or when user explicitly requests it.
        """
        try:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.execute(
                    """SELECT payload_json, checksum, is_delta, base_snapshot_id, parent_id,
                          branch_name, description, created_at, type, cell_count, tags
                       FROM snapshots WHERE id = ?""",
                    (snapshot_id,)
                )
                row = cursor.fetchone()
                if not row:
                    return False
                
                (payload_json, stored_checksum, is_delta, base_snapshot_id, 
                 parent_id, branch_name, description, created_at, type_val,
                 cell_count, tags) = row
                
                if not is_delta:
                    # Already a full snapshot
                    return True
                
                # Reconstruct full payload
                stored_delta = json.loads(payload_json)
                full_payload = self._reconstruct_from_delta(stored_delta, base_snapshot_id, snapshot_id)
                
                if full_payload is None:
                    return False
                
                # Store raw payload directly (no wrapper)
                # Checksum is computed on the raw JSON for corruption detection
                stored_json = json.dumps(full_payload, default=str, sort_keys=True, separators=(',', ':'))
                checksum = self._compute_checksum(stored_json)

                conn.execute(
                    """UPDATE snapshots
                       SET payload_json = ?, checksum = ?, is_delta = 0, base_snapshot_id = NULL,
                           payload_checksum = NULL
                       WHERE id = ?""",
                    (stored_json, checksum, snapshot_id)
                )
                conn.commit()
                
                logger.info(f"Consolidated delta {snapshot_id} to full snapshot")
                return True
                
        except (sqlite3.Error, json.JSONDecodeError) as e:
            logger.error(f"Error creating full snapshot: {e}")
            return False
    
    def get_snapshot_metadata(self, snapshot_id: str) -> Optional[Snapshot]:
        """Get snapshot metadata without loading payload."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT id, parent_id, branch_name, description, created_at,
                           type, cell_count, tags, checksum, is_delta, delta_chain_index,
                           content_hash
                    FROM snapshots WHERE id = ?
                    """,
                    (snapshot_id,)
                )
                row = cursor.fetchone()
                
                if not row:
                    return None
                
                return Snapshot(
                    snapshot_id=row[0],
                    parent_id=row[1],
                    branch_name=row[2],
                    description=row[3] or "",
                    created_at=datetime.fromisoformat(row[4]),
                    type=self._parse_type(row[5]),
                    cell_count=row[6] or 0,
                    tags=json.loads(row[7]) if row[7] else [],
                    payload_checksum=row[8],
                    is_delta=bool(row[9]) if row[9] is not None else False,
                    delta_chain_index=row[10] if row[10] is not None else 0,
                    content_hash=row[11],
                )
        
        except Exception as e:
            logger.error(f"Error getting metadata: {e}")
            return None
    
    def update_branch_only(self, snapshot_id: str, branch_name: str) -> bool:
        """Update only the branch name without touching the payload.
        
        This is used during restructure operations to preserve delta integrity.
        """
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    "UPDATE snapshots SET branch_name = ? WHERE id = ?",
                    (branch_name, snapshot_id)
                )
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"Error updating branch: {e}")
            return False
    
    def update_snapshot_parent(self, snapshot_id: str, new_parent_id: Optional[str]) -> bool:
        """Update the parent_id of a snapshot.

        This is used during restructure operations to rewire delta chains.
        Also updates base_snapshot_id to match parent_id for delta snapshots.
        """
        try:
            with sqlite3.connect(self._db_path) as conn:
                # Get current delta status from the actual schema columns
                cursor = conn.execute(
                    "SELECT is_delta, base_snapshot_id FROM snapshots WHERE id = ?",
                    (snapshot_id,)
                )
                row = cursor.fetchone()
                is_delta = bool(row[0]) if row else False

                # Update parent_id
                conn.execute(
                    "UPDATE snapshots SET parent_id = ? WHERE id = ?",
                    (new_parent_id, snapshot_id)
                )

                # For delta snapshots, also update base_snapshot_id column
                if is_delta:
                    conn.execute(
                        "UPDATE snapshots SET base_snapshot_id = ? WHERE id = ?",
                        (new_parent_id, snapshot_id)
                    )

                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"Error updating parent: {e}")
            return False
    
    def save_snapshot_reference(self, snapshot: Snapshot, target_snapshot_id: str) -> bool:
        """Save a snapshot as a reference to another snapshot.
        
        This is used for RESTORED snapshots to avoid storing redundant deltas.
        The snapshot's payload is stored as a reference: {"_ref": target_snapshot_id}
        
        Args:
            snapshot: The snapshot to save (a new "Restored from X" snapshot)
            target_snapshot_id: The snapshot ID this references
            
        Returns:
            True if successful
        """
        try:
            import hashlib
            
            # Store reference payload instead of actual payload
            ref_payload = {"_ref": target_snapshot_id}
            payload_json = json.dumps(ref_payload, default=str, sort_keys=True, separators=(',', ':'))
            payload_checksum = hashlib.md5(payload_json.encode('utf-8')).hexdigest()
            
            # Metadata for reference snapshot
            metadata = {
                "is_delta": False,
                "is_full": False,
                "is_reference": True,
                "target_snapshot_id": target_snapshot_id,
                "payload_checksum": payload_checksum,
            }
            
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO snapshots (
                        id, parent_id, branch_name, description, created_at,
                        type, cell_count, tags,
                        payload_json, checksum, is_delta, base_snapshot_id, payload_checksum, delta_chain_index
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot.snapshot_id,
                        snapshot.parent_id,
                        snapshot.branch_name,
                        snapshot.description,
                        snapshot.created_at.isoformat(),
                        snapshot.type.value,
                        0,  # cell_count - not meaningful for references
                        json.dumps({"is_reference": True, "target_snapshot_id": target_snapshot_id}),
                        payload_json,
                        payload_checksum,  # checksum
                        0,  # is_delta = False
                        None,  # base_snapshot_id
                        payload_checksum,
                        0,  # delta_chain_index = 0 for reference (resets chain)
                    )
                )
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"Error saving snapshot reference: {e}")
            return False
    
    def list_snapshots(self, branch_name: Optional[str] = None) -> List[Snapshot]:
        """List all snapshots, optionally filtered by branch."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                if branch_name:
                    cursor = conn.execute(
                        """
                        SELECT id, parent_id, branch_name, description, created_at,
                               type, cell_count, tags, checksum, is_delta, delta_chain_index,
                               content_hash
                        FROM snapshots WHERE branch_name = ?
                        ORDER BY created_at
                        """,
                        (branch_name,)
                    )
                else:
                    cursor = conn.execute(
                        """
                        SELECT id, parent_id, branch_name, description, created_at,
                               type, cell_count, tags, checksum, is_delta, delta_chain_index,
                               content_hash
                        FROM snapshots
                        ORDER BY created_at
                        """
                    )
                
                snapshots = []
                for row in cursor.fetchall():
                    snapshots.append(Snapshot(
                        snapshot_id=row[0],
                        parent_id=row[1],
                        branch_name=row[2],
                        description=row[3] or "",
                        created_at=datetime.fromisoformat(row[4]),
                        type=self._parse_type(row[5]),
                        cell_count=row[6] or 0,
                        tags=json.loads(row[7]) if row[7] else [],
                        payload_checksum=row[8],
                        is_delta=bool(row[9]) if row[9] is not None else False,
                        delta_chain_index=row[10] if row[10] is not None else 0,
                        content_hash=row[11],
                    ))
                
                return snapshots
        
        except sqlite3.Error as e:
            logger.error(f"Error listing snapshots: {e}")
            return []
    
    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a snapshot and its payload."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("DELETE FROM snapshots WHERE id = ?", (snapshot_id,))
                conn.commit()
                return True
        
        except sqlite3.Error as e:
            logger.error(f"Error deleting snapshot: {e}")
            return False
    
    def save_session_metadata(self, session: Session) -> bool:
        """Save session-level metadata."""
        logger.info(f"save_session_metadata() called: session_id={session.session_id}, db_path={self._db_path}")
        try:
            data = session.to_dict()
            logger.info(f"session has {len(session.snapshots)} snapshots")
            
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO session_metadata (key, value) VALUES (?, ?)",
                    ("session", json.dumps(data, default=str))
                )
                conn.commit()
            logger.info("save_session_metadata() SUCCESS")
            return True
        
        except (sqlite3.Error, json.JSONDecodeError) as e:
            logger.error(f"Error saving session metadata: {e}")
            return False
    
    def load_session_metadata(self) -> Optional[Session]:
        """Load session metadata."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.execute(
                    "SELECT value FROM session_metadata WHERE key = ?",
                    ("session",)
                )
                row = cursor.fetchone()
                
                if not row:
                    return None
                
                data = json.loads(row[0])
                return Session.from_dict(data)
        
        except (sqlite3.Error, json.JSONDecodeError, KeyError) as e:
            print(f"[DataStore] Error loading session metadata: {e}")
            return None
    
    def _parse_type(self, type_str: Optional[str]) -> Any:
        """Parse snapshot type from string."""
        from .models import SnapshotType
        try:
            return SnapshotType(type_str or "manual")
        except ValueError:
            return SnapshotType.MANUAL
