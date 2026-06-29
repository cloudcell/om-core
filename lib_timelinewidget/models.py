"""Core data models for timeline visualization.

Minimal dataclasses required for rendering the timeline.
No business logic, just data structure.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List


class SnapshotType(Enum):
    """Type of snapshot in the timeline."""
    MANUAL = "manual"      # User-created checkpoint
    AUTO = "auto"          # Auto-saved state
    BRANCH = "branch"      # Branch point marker


@dataclass
class SnapshotInfo:
    """Minimal snapshot metadata for timeline rendering.
    
    Attributes:
        snapshot_id: Unique identifier
        parent_id: Parent snapshot in tree (None for root)
        description: User-facing label
        branch_name: Branch identifier (e.g., "main", "experiment-1")
        created_at: Timestamp for display
        type: Classification affecting visual style
        is_alt_indicator: True if this is a branch indicator node (not real snapshot)
    """
    snapshot_id: str
    parent_id: Optional[str] = None
    description: str = ""
    branch_name: str = "main"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    type: SnapshotType = SnapshotType.MANUAL
    
    # Visual/internal flags
    is_alt_indicator: bool = False  # Branch indicator pseudo-node
    child_ids: List[str] = field(default_factory=list)  # For fork detection
    is_delta: bool = False  # True if stored as delta, False if full snapshot
    
    def __hash__(self) -> int:
        """Make SnapshotInfo hashable for use in sets/dicts."""
        return hash(self.snapshot_id)
    
    def __eq__(self, other) -> bool:
        """Equality based on snapshot_id."""
        if not isinstance(other, SnapshotInfo):
            return False
        return self.snapshot_id == other.snapshot_id
