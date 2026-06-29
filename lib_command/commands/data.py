"""
Data commands - Cell data operations.

Properties: data.value, data.rule_body
"""

from __future__ import annotations

from typing import Any, Optional


def cmd_set_data(
    ctx,
    target_type: str,
    target_id: Optional[str],
    property: str,
    value: Any
) -> dict:
    """Set a data property (value, rule_body)."""
    data_prop = property.replace("data.", "")

    if data_prop == "value":
        return cmd_set_value(ctx, target_type, target_id, value)
    elif data_prop == "rule_body":
        return cmd_set_rule_body(ctx, target_type, target_id, value)
    else:
        ctx.status(f"Unknown data property: {data_prop}")
        return {"affected": 0, "error": f"Unknown property: {data_prop}"}


def cmd_set_value(
    ctx,
    target_type: str,
    target_id: Optional[str],
    value: Any
) -> dict:
    """Set a cell value."""
    from .utils import resolve_target
    cells = resolve_target(ctx, target_type, target_id)

    results = []
    affected = 0
    engine = ctx.engine

    for cell in cells:
        if isinstance(cell, dict) and cell.get("type") == "semantic_cell":
            address = cell.get("address", "")
            if _set_value_at_address(engine, address, value):
                affected += 1
                results.append({"cell": address, "value": value})

    ctx.status(f"Set value on {affected} cell(s)")
    if affected > 0:
        ctx.refresh()

    return {"affected": affected, "property": "value", "value": value}


def cmd_set_rule_body(
    ctx,
    target_type: str,
    target_id: Optional[str],
    rule_body: str
) -> dict:
    """Set a cell rule body."""
    from .utils import resolve_target
    cells = resolve_target(ctx, target_type, target_id)

    results = []
    affected = 0
    engine = ctx.engine

    for cell in cells:
        if isinstance(cell, dict) and cell.get("type") == "semantic_cell":
            address = cell.get("address", "")
            if _set_rule_body_at_address(engine, address, rule_body):
                affected += 1
                results.append({"cell": address, "rule_body": rule_body})

    ctx.status(f"Set rule body on {affected} cell(s)")
    if affected > 0:
        ctx.refresh()

    return {"affected": affected, "property": "rule_body", "value": rule_body}


def _set_value_at_address(engine: Any, address: str, value: Any) -> bool:
    """Set value at semantic address."""
    try:
        if "::" not in address or not engine:
            return False

        cube_part, dims_part = address.split("::", 1)
        dims = dims_part.split(":")

        # Find cube by ID or name
        cube = engine.require_cube_by_id(cube_part)
        if cube is None:
            cube = engine.find_cube_by_name(cube_part)
        if cube is None:
            return False
        cube_id = cube.id

        addr_tuple = ("@.value",) + tuple(dims)
        engine.set_cell_value_by_addr(cube_id, addr_tuple, value)
        return True
    except Exception:
        return False


def _set_rule_body_at_address(engine: Any, address: str, rule_body: str) -> bool:
    """Set rule body at semantic address."""
    try:
        if "::" not in address or not engine:
            return False

        cube_part, dims_part = address.split("::", 1)
        dims = dims_part.split(":")

        # Find cube by ID or name
        cube = engine.require_cube_by_id(cube_part)
        if cube is None:
            cube = engine.find_cube_by_name(cube_part)
        if cube is None:
            return False
        cube_id = cube.id

        addr_tuple = ("@.value",) + tuple(dims)
        engine.set_cell_rule_by_addr(cube_id, addr_tuple, rule_body)
        return True
    except Exception:
        return False
