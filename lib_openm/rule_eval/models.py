"""Data models for rule evaluation."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    """A rule applied to some subset of a cube's address space.

    Rules are defined by an ``addr_mask`` that records constraints across all
    dimensions. The mask is aligned to ``Cube.dimension_ids`` for the owning cube:

    - ``None``   → wildcard on that dimension (rule applies to all items)
    - ``item_id`` → rule only applies when that dimension's item matches
    """

    id: str
    cube_id: str
    expression: str
    addr_mask: tuple[str | None, ...] | None = None
    # Original parsed targets preserving sequential keywords like [THIS], [PREV]
    targets: tuple[tuple[str, str], ...] | None = None
    # True if this is an anchored rule - uses default items for new dimensions
    is_anchored: bool = False


