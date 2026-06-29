"""Core dataclasses for snapshot management.

NO GUI DEPENDENCIES.
These models represent the domain entities for session/snapshot management.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
import uuid


class SnapshotType(Enum):
    """Type of snapshot creation."""
    AUTO = "auto"           # Automatic checkpoint
    MANUAL = "manual"       # User-initiated checkpoint
    RESTORED = "restored"   # Created by restoring to another snapshot
    BRANCH = "branch"       # Branch point
    SESSION_START = "session_start"  # Initial session snapshot (always full)
    MILESTONE = "milestone"          # Explicit full snapshot for consolidation


@dataclass
class Snapshot:
    """A point-in-time snapshot of workspace state.
    
    This is the core entity representing a saved state that can be
    restored to or branched from.
    """
    snapshot_id: str
    parent_id: Optional[str] = None
    description: str = ""
    branch_name: str = "main"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    type: SnapshotType = SnapshotType.MANUAL
    cell_count: int = 0
    tags: List[str] = field(default_factory=list)
    
    # Payload reference (actual data stored separately in DataStore)
    payload_checksum: Optional[str] = None
    
    # Stable hash of the workspace's canonical serialized form.
    content_hash: Optional[str] = None
    
    # Storage type
    is_delta: bool = False  # True if stored as delta, False if full snapshot
    
    # Delta chain position (0 = full snapshot base, 1+ = delta number in chain)
    delta_chain_index: int = 0
    
    @classmethod
    def create(
        cls,
        description: str,
        parent_id: Optional[str] = None,
        branch_name: str = "main",
        snapshot_type: SnapshotType = SnapshotType.MANUAL,
        cell_count: int = 0
    ) -> "Snapshot":
        """Factory method to create a new snapshot with generated ID."""
        return cls(
            snapshot_id=str(uuid.uuid4()),
            parent_id=parent_id,
            description=description,
            branch_name=branch_name,
            type=snapshot_type,
            cell_count=cell_count
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for storage."""
        return {
            "snapshot_id": self.snapshot_id,
            "parent_id": self.parent_id,
            "description": self.description,
            "branch_name": self.branch_name,
            "created_at": self.created_at.isoformat(),
            "type": self.type.value,
            "cell_count": self.cell_count,
            "tags": self.tags,
            "payload_checksum": self.payload_checksum,
            "content_hash": self.content_hash,
            "delta_chain_index": self.delta_chain_index,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Snapshot":
        """Deserialize from dictionary."""
        # Parse datetime and ensure it's timezone-aware (UTC)
        dt = datetime.fromisoformat(data["created_at"])
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        
        return cls(
            snapshot_id=data["snapshot_id"],
            parent_id=data.get("parent_id"),
            description=data.get("description", ""),
            branch_name=data.get("branch_name", "main"),
            created_at=dt,
            type=SnapshotType(data.get("type", "manual")),
            cell_count=data.get("cell_count", 0),
            tags=data.get("tags", []),
            payload_checksum=data.get("payload_checksum"),
            content_hash=data.get("content_hash"),
            delta_chain_index=data.get("delta_chain_index", 0),
        )


@dataclass
class Branch:
    """A branch in the snapshot tree.
    
    Branches allow parallel lines of development from a common ancestor.
    """
    name: str
    head_snapshot_id: Optional[str] = None  # Latest snapshot on this branch
    parent_branch: Optional[str] = None     # Branch this forked from
    fork_snapshot_id: Optional[str] = None  # Snapshot where fork occurred
    created_at: datetime = field(default_factory=datetime.now)
    is_active: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "head_snapshot_id": self.head_snapshot_id,
            "parent_branch": self.parent_branch,
            "fork_snapshot_id": self.fork_snapshot_id,
            "created_at": self.created_at.isoformat(),
            "is_active": self.is_active,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Branch":
        """Deserialize from dictionary."""
        return cls(
            name=data["name"],
            head_snapshot_id=data.get("head_snapshot_id"),
            parent_branch=data.get("parent_branch"),
            fork_snapshot_id=data.get("fork_snapshot_id"),
            created_at=datetime.fromisoformat(data["created_at"]),
            is_active=data.get("is_active", True),
        )


@dataclass
class Session:
    """A working session containing snapshots and branches.
    
    This represents the top-level container for all snapshot data
    associated with a workspace.
    """
    session_id: str
    name: str = "Untitled Session"
    created_at: datetime = field(default_factory=datetime.now)
    modified_at: datetime = field(default_factory=datetime.now)
    current_snapshot_id: Optional[str] = None
    
    # All snapshots in this session (flat list, tree structure via parent_id)
    snapshots: Dict[str, Snapshot] = field(default_factory=dict)
    
    # All branches in this session
    branches: Dict[str, Branch] = field(default_factory=dict)
    
    # Metadata
    version: str = "1.0"
    
    @classmethod
    def create(cls, name: str = "Untitled Session") -> "Session":
        """Factory method to create a new session."""
        session_id = str(uuid.uuid4())
        return cls(
            session_id=session_id,
            name=name,
        )
    
    def add_snapshot(self, snapshot: Snapshot) -> None:
        """Add a snapshot to this session."""
        self.snapshots[snapshot.snapshot_id] = snapshot
        self.modified_at = datetime.now()
        
        # Update branch head if on main branch
        if snapshot.branch_name == "main":
            if "main" not in self.branches:
                self.branches["main"] = Branch(name="main")
            self.branches["main"].head_snapshot_id = snapshot.snapshot_id
    
    def get_branch_snapshots(self, branch_name: str) -> List[Snapshot]:
        """Get all snapshots on a specific branch."""
        return [
            snap for snap in self.snapshots.values()
            if snap.branch_name == branch_name
        ]
    
    def get_snapshot_lineage(self, snapshot_id: str) -> List[Snapshot]:
        """Get lineage from root to this snapshot (inclusive)."""
        lineage = []
        current_id = snapshot_id
        
        while current_id:
            snap = self.snapshots.get(current_id)
            if not snap:
                break
            lineage.append(snap)
            current_id = snap.parent_id
        
        return list(reversed(lineage))
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "session_id": self.session_id,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "modified_at": self.modified_at.isoformat(),
            "current_snapshot_id": self.current_snapshot_id,
            "snapshots": {
                sid: snap.to_dict()
                for sid, snap in self.snapshots.items()
            },
            "branches": {
                name: branch.to_dict()
                for name, branch in self.branches.items()
            },
            "version": self.version,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Session":
        """Deserialize from dictionary."""
        session = cls(
            session_id=data["session_id"],
            name=data.get("name", "Untitled Session"),
            created_at=datetime.fromisoformat(data["created_at"]),
            modified_at=datetime.fromisoformat(data["modified_at"]),
            current_snapshot_id=data.get("current_snapshot_id"),
            snapshots={
                sid: Snapshot.from_dict(sdata)
                for sid, sdata in data.get("snapshots", {}).items()
            },
            branches={
                name: Branch.from_dict(bdata)
                for name, bdata in data.get("branches", {}).items()
            },
            version=data.get("version", "1.0"),
        )
        return session


# Backwards compatibility - alias for existing code
SnapshotInfo = Snapshot
