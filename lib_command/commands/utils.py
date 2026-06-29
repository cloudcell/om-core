"""
Utility functions for command implementations.
"""

from __future__ import annotations

from typing import Any, Optional


def _parse_target(target: str) -> tuple[str, Optional[str]]:
    """Parse target string into (type, id).

    Examples:
        "selection" -> ("selection", None)
        "cell:A1" -> ("cell", "A1")
        "item:Q1.Jan" -> ("item", "Q1.Jan")
        "view" -> ("view", None)
        "Cube::Dim.Item:Dim.Item" -> ("address", "Cube::Dim.Item:Dim.Item")
    """
    # Check for semantic address pattern (contains ::)
    if "::" in target:
        return "address", target

    if ":" in target:
        parts = target.split(":", 1)
        return parts[0], parts[1]
    return target, None


def resolve_target(
    ctx,
    target_type: str,
    target_id: Optional[str]
) -> list[Any]:
    """Resolve a target reference to actual objects."""
    if target_type == "selection":
        return ctx.selection or []
    elif target_type == "address":
        return _resolve_semantic_address(ctx, target_id) if target_id else []
    elif target_type == "cell":
        return [target_id] if target_id else []
    elif target_type == "item":
        return [target_id] if target_id else []
    elif target_type == "view":
        return [ctx.active_view]
    else:
        return []


def _resolve_semantic_address(ctx, address: str) -> list[Any]:
    """Resolve a semantic address to cell references.

    Semantic address format: Cube::Dim.Item:Dim.Item
    """
    try:
        if "::" not in address:
            return []

        cube_part, dims_part = address.split("::", 1)
        dims = dims_part.split(":")

        # Build cell reference
        cell_ref = {
            "cube": cube_part,
            "address": address,
            "dimensions": dims,
            "type": "semantic_cell"
        }

        return [cell_ref]

    except Exception:
        return []
