"""DTO deserialization: MsgPack dicts → Python model objects.

These are the inverse of the serialization functions in lib_openm/persistence.py.
The server returns MsgPack dicts; these functions reconstruct Python model objects.
"""

from __future__ import annotations

from typing import Any

from lib_openm.model import (
    Cube,
    Dimension,
    DimensionItem,
    TableViewSpec,
    Workspace,
)
from lib_openm.rule_eval.models import Rule
from lib_openm.rule_eval.utils import CellError
from lib_openm._engine_core import CellValue, Explain
from lib_openm.persistence import _deserialize_value


def _dto_to_dimension_item(item_id: str, d: dict[str, Any]) -> DimensionItem:
    return DimensionItem(id=str(item_id), name=str(d.get("name", "")))


def _dto_to_dimension(dim_id: str = "", d: dict[str, Any] | None = None) -> Dimension:
    if d is None:
        d = {}
    items: list[DimensionItem] = []
    items_data = d.get("items", {})
    if isinstance(items_data, dict):
        for item_id, item_dict in items_data.items():
            items.append(_dto_to_dimension_item(str(item_id), item_dict))
    elif isinstance(items_data, list):
        for item_dict in items_data:
            if isinstance(item_dict, dict):
                items.append(_dto_to_dimension_item(str(item_dict.get("id", "")), item_dict))

    dim_type = d.get("dim_type", d.get("kind", "set"))
    actual_id = str(d.get("id", dim_id))
    dim = Dimension(
        id=actual_id,
        name=str(d.get("name", "")),
        items=items,
        dim_type=str(dim_type),
        is_technical=bool(d.get("is_technical", False)),
    )
    root_order = d.get("root_order_override")
    if root_order:
        dim._root_order_override = dict(root_order)
    return dim


def _dto_to_cube(d: dict[str, Any], cube_id: str | None = None) -> Cube:
    cid = str(d.get("id", cube_id or ""))
    cube = Cube(
        id=cid,
        name=str(d.get("name", "")),
        dimension_ids=list(d.get("dimension_ids", [])),
    )
    data = d.get("data", {})
    for key_str, val in data.items():
        parts = tuple(key_str.split("|"))
        value, is_hardcoded = _deserialize_value(val)
        cube.data[parts] = value
        if is_hardcoded:
            cube.user_override_addrs.add(parts)
    return cube


def _dto_to_rule(d: dict[str, Any], rule_id: str | None = None) -> Rule:
    rid = str(d.get("id", rule_id or ""))
    addr_mask_raw = d.get("addr_mask")
    addr_mask: tuple[str | None, ...] | None = None
    if addr_mask_raw is not None:
        addr_mask = tuple(
            str(x) if x is not None else None
            for x in addr_mask_raw
        )

    targets_raw = d.get("targets")
    targets: tuple[tuple[str, str], ...] | None = None
    if targets_raw is not None:
        targets = tuple(tuple(t) for t in targets_raw)

    return Rule(
        id=rid,
        cube_id=str(d["cube_id"]),
        expression=str(d["expression"]),
        addr_mask=addr_mask,
        targets=targets,
        is_anchored=bool(d.get("is_anchored", False)),
    )


def _dto_to_view(d: dict[str, Any]) -> TableViewSpec:
    view = TableViewSpec(
        id=str(d["id"]),
        name=str(d["name"]),
        cube_id=str(d["cube_id"]),
        row_dim_ids=list(d.get("row_dim_ids", [])),
        col_dim_ids=list(d.get("col_dim_ids", [])),
        page_dim_ids=list(d.get("page_dim_ids", [])),
    )
    col_widths = d.get("col_widths", {})
    if col_widths:
        view.col_widths = {int(k): int(v) for k, v in col_widths.items()}
    row_header_widths = d.get("row_header_widths", {})
    if row_header_widths:
        view.row_header_widths = {int(k): int(v) for k, v in row_header_widths.items()}
    page_selections = d.get("page_selections", {})
    if page_selections:
        view.page_selections = dict(page_selections)
    return view


def _dto_to_workspace(d: dict[str, Any]) -> Workspace:
    """Reconstruct a full Workspace from a MsgPack dict.

    Handles the server's DTO format where dimensions/cubes/rules are maps
    keyed by their ID, and the ID is not duplicated inside each entry.
    """
    ws = Workspace(
        id=str(d.get("id", "")),
        name=str(d.get("name", "Untitled")),
    )

    for dim_id, dim_dict in d.get("dimensions", {}).items():
        ws.dimensions[str(dim_id)] = _dto_to_dimension(str(dim_id), dim_dict)

    for cube_id, cube_dict in d.get("cubes", {}).items():
        ws.cubes[str(cube_id)] = _dto_to_cube(cube_dict, cube_id=str(cube_id))

    for rule_id, rule_dict in d.get("rules", {}).items():
        ws.rules[str(rule_id)] = _dto_to_rule(rule_dict, rule_id=str(rule_id))

    ws.rule_order = [str(r) for r in d.get("rule_order", [])]

    for view_id, view_dict in d.get("views", {}).items():
        ws.views[str(view_id)] = _dto_to_view(view_dict)

    ws.views_order = [str(v) for v in d.get("views_order", [])]

    saved_default = d.get("saved_default_view_id")
    if saved_default:
        ws.saved_default_view_id = str(saved_default)

    return ws


def _dto_to_cell_value(d: dict[str, Any]) -> CellValue:
    """Deserialize a tagged cell value dict into a CellValue object.

    The server returns tagged values like:
      {"_type": "number", "value": 42.5}
      {"_type": "error", "code": "#DIV/0!"}
      {"_type": "null"}
      {"_type": "text", "value": "hello"}
    """
    value, _ = _deserialize_value(d)

    if isinstance(value, CellError):
        explain = Explain(
            source="error",
            cube_id="",
            addr=(),
            error=value.code,
        )
    else:
        explain = Explain(
            source="input",
            cube_id="",
            addr=(),
        )

    return CellValue(value=value, explain=explain)
