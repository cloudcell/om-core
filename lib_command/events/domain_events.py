"""Domain events for the canonical command path.

These are published to the MessageBus by command handlers.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DimensionStructureChangedEvent:
    dim_id: str
    reason: str
    affected_node_ids: list[str]
