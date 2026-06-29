"""Outline patch DTOs — for group change events."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypedDict


class OutlineNodeDTO(TypedDict):
    """Plain snapshot of a single outline node. Never contains engine objects."""

    label: str
    item_id: str | None
    children: list["OutlineNodeDTO"]
    node_id: str | None


@dataclass(frozen=True)
class OutlinePatch:
    """Immutable patch describing a single outline mutation.

    Patches are emitted by group command handlers and consumed by
    GUI read-model updaters (and optionally the event bus).
    """

    patch_type: str
    dim_id: str
    payload: dict[str, Any]
    workspace_revision: int = 0  # reserved for future WorkspaceRuntime

    def to_dict(self) -> dict[str, Any]:
        return {
            "patch_type": self.patch_type,
            "dim_id": self.dim_id,
            "payload": self.payload,
            "workspace_revision": self.workspace_revision,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "OutlinePatch":
        return cls(
            patch_type=d["patch_type"],
            dim_id=d["dim_id"],
            payload=dict(d.get("payload", {})),
            workspace_revision=d.get("workspace_revision", 0),
        )
