"""
Utility functions for command implementations.
"""

from __future__ import annotations

from typing import Any, Optional


def _find_or_create_default_view(engine, cube_id: str) -> str:
    """Return a view for the cube, creating a default one if necessary.

    Uses the read-only ``resolve_default_view_id_by_cube`` first, then
    ``create_default_view_for_cube`` only when no view exists.
    """
    existing_id = engine.resolve_default_view_id_by_cube(cube_id)
    if existing_id is not None:
        return existing_id
    return engine.create_default_view_for_cube(cube_id)


def _semantic_addr_to_cell_ref(engine, cube_id: str, dims: list[str], channel: str = "value") -> tuple[str, dict]:
    """Convert a semantic address to a canonical (view_id, cell_ref)."""
    view_id = _find_or_create_default_view(engine, cube_id)
    view = engine.require_view_by_id(view_id)
    row_dim_count = len(view.row_dim_ids)
    row_key = tuple(dims[:row_dim_count])
    col_key = tuple(dims[row_dim_count:])
    return view_id, {"kind": "ids", "row_key": row_key, "col_key": col_key, "channel": channel}


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
