"""
Format commands - Cell formatting operations.

Properties: format.bold, format.italic, format.color, format.bg_color, format.font_size
"""

from __future__ import annotations

from typing import Any, Optional
from dataclasses import dataclass


@dataclass
class PropertySpec:
    """Specification for a settable property."""
    path: str                    # Full path like "format.bold"
    name: str                    # Display name
    value_type: type             # Expected value type
    target_types: list[str]      # Valid target types: ["cell", "selection", "item"]
    description: str = ""


# Property registry for format properties
PROPERTY_REGISTRY: dict[str, PropertySpec] = {
    "format.bold": PropertySpec("format.bold", "Bold", bool, ["cell", "selection", "item"], "Make text bold"),
    "format.italic": PropertySpec("format.italic", "Italic", bool, ["cell", "selection", "item"]),
    "format.underline": PropertySpec("format.underline", "Underline", bool, ["cell", "selection", "item"]),
    "format.color": PropertySpec("format.color", "Text Color", str, ["cell", "selection", "item"]),
    "format.bg_color": PropertySpec("format.bg_color", "Background Color", str, ["cell", "selection", "item"]),
    "format.font_size": PropertySpec("format.font_size", "Font Size", int, ["cell", "selection", "item"]),
    "format.number_format": PropertySpec("format.number_format", "Number Format", str, ["cell", "selection", "item"]),
}


def list_properties(category: Optional[str] = None) -> list[PropertySpec]:
    """List available properties, optionally filtered by category."""
    specs = list(PROPERTY_REGISTRY.values())
    if category:
        specs = [s for s in specs if s.path.startswith(f"{category}.")]
    return specs


def cmd_set_format(
    ctx,
    target_type: str,
    target_id: Optional[str],
    property: str,
    value: Any
) -> dict:
    """Set a formatting property via @ dimension channels."""
    format_prop = property.replace("format.", "")

    # Map format property to @ dimension channel
    prop_to_channel = {
        "bold": ("font_weight", lambda v: 700 if v else 400),
        "italic": ("font_italic", lambda v: v),
        "bg_color": ("fill", lambda v: v),
        "color": ("font_color", lambda v: v),
        "font_color": ("font_color", lambda v: v),
        "font_size": ("font_size", lambda v: int(v) if isinstance(v, (int, float, str)) else v),
    }

    if format_prop not in prop_to_channel:
        ctx.status(f"Unknown format property: {format_prop}")
        return {"affected": 0, "error": f"Unknown property: {format_prop}"}

    channel_name, value_transform = prop_to_channel[format_prop]
    channel_value = value_transform(value)

    # Get target cells
    from .utils import resolve_target
    cells = resolve_target(ctx, target_type, target_id)

    # Apply format via @ dimension to each cell
    results = []
    affected = 0
    engine = ctx.engine

    for cell in cells:
        # Handle dict-based cell references (from semantic addresses)
        if isinstance(cell, dict) and cell.get("type") == "semantic_cell":
            address = cell.get("address", "")
            if _set_format_at_address(engine, address, channel_name, channel_value):
                affected += 1
                results.append({"cell": address, "channel": f"@.{channel_name}", "value": channel_value})
        elif target_type == "selection" and ctx.selection:
            # For selection, resolve to actual cells and apply
            for sel_cell in ctx.selection:
                if isinstance(sel_cell, dict) and "address" in sel_cell:
                    addr_str = sel_cell.get("address", "")
                    if _set_format_at_address(engine, addr_str, channel_name, channel_value):
                        affected += 1
                        results.append({"cell": addr_str, "channel": f"@.{channel_name}", "value": channel_value})

    if affected > 0:
        ctx.status(f"Applied {format_prop}={channel_value} to {affected} cell(s) via @.{channel_name}")
        ctx.refresh()

    return {"affected": affected, "property": format_prop, "value": channel_value, "channel": f"@.{channel_name}"}


def _set_format_at_address(engine: Any, address: str, channel: str, value: Any) -> bool:
    """Set format via @ dimension channel by semantic address.

    Address format: Cube::Dim.Item:Dim.Item
    """
    try:
        if "::" not in address or not engine:
            return False

        # Parse address: Cube::Dim.Item:Dim.Item
        cube_part, dims_part = address.split("::", 1)
        dims = dims_part.split(":")

        if len(dims) < 2:
            return False

        # Find cube by ID or name
        cube = engine.require_cube_by_id(cube_part)
        if cube is None:
            cube = engine.find_cube_by_name(cube_part)
        if cube is None:
            return False
        cube_id = cube.id

        # Build address tuple with @ channel
        addr_tuple = (f"@.{channel}",) + tuple(dims)

        # Set the value
        engine.set_cell_value_by_addr(cube_id, addr_tuple, value)
        return True

    except Exception:
        return False
