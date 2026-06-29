"""lib_contracts.dto — client-facing DTO re-exports.

Canonical location for domain-agnostic data transfer objects.
GUI and other clients import from here.
"""

from .cell import (
    CellAddressDTO,
    CellDTO,
    CellExplainDTO,
    CellKind,
    CellPrimitive,
    CellRangeDTO,
)
from .workspace import (
    CubeSnapshotDTO,
    ViewLayoutDTO,
    ViewSnapshotDTO,
    WorkspaceSnapshotDTO,
    WorkspaceSummaryDTO,
)
from .outline import OutlinePatch

__all__ = [
    "CellAddressDTO",
    "CellDTO",
    "CellExplainDTO",
    "CellKind",
    "CellPrimitive",
    "CellRangeDTO",
    "CubeSnapshotDTO",
    "OutlinePatch",
    "ViewLayoutDTO",
    "ViewSnapshotDTO",
    "WorkspaceSnapshotDTO",
    "WorkspaceSummaryDTO",
]
