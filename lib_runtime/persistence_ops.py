"""lib_runtime.persistence_ops — host-side workspace serialization helpers.

These live in lib_runtime because they touch engine domain objects
(Workspace, Cube, Dimension, etc.) and persistence internals.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from lib_openm.api import Engine
    from lib_command.core.session import CommandSession


def prepare_workspace_for_snapshot(engine: "Engine") -> Any:
    """Sync engine state to workspace and ensure canonical graph structures.

    Returns the workspace object ready for serialization.
    """
    from lib_openm.lib_meta.bootstrap import ensure_system_cubes
    from lib_openm.outline_graph_bridge import migrate_workspace_outline_to_graph

    ws = engine.workspace
    ensure_system_cubes(ws)
    migrate_workspace_outline_to_graph(ws)
    return ws


def generate_snapshot_payload(
    engine: "Engine",
    persist_calculated: bool = False,
) -> dict[str, Any]:
    """Serialize workspace state into a snapshot payload dict.

    This is the host-side equivalent of save_workspace for timeline snapshots.
    """
    from dataclasses import asdict
    from lib_openm.persistence import _serialize_value

    ws = prepare_workspace_for_snapshot(engine)
    payload: dict[str, Any] = {"workspace": asdict(ws)}

    # Serialize cube data with tagged values.
    for cube_id, cube in payload["workspace"]["cubes"].items():
        data = cube.get("data", {})
        override_addrs = cube.get("user_override_addrs", set())
        if isinstance(override_addrs, set):
            override_addrs_list = [
                ("|".join(addr)).replace(".", "__dot__") for addr in override_addrs
            ]
            cube["user_override_addrs"] = override_addrs_list
        else:
            override_addrs_list = override_addrs if isinstance(override_addrs, list) else []

        if not persist_calculated:
            filtered_data: dict[str, Any] = {}
            for k, v in data.items():
                addr_key = ("|".join(k)).replace(".", "__dot__")
                if addr_key in override_addrs_list:
                    filtered_data[addr_key] = _serialize_value(v)
            cube["data"] = filtered_data
        else:
            cube["data"] = {
                ("|".join(k)).replace(".", "__dot__"): _serialize_value(v)
                for k, v in data.items()
            }

    # Recursively sanitize any remaining tuple keys (e.g. _item_ref_index)
    _sanitize_tuple_keys(payload)

    return payload


def _sanitize_tuple_keys(obj: Any) -> None:
    """In-place conversion of dict tuple keys to pipe-delimited strings.

    Walks nested dicts and lists.  Tuples that are dict keys are joined
    with '|' (mirroring the cube address convention).  Other tuple values
    are left unchanged.
    """
    if isinstance(obj, dict):
        keys_to_fix = [k for k in obj.keys() if isinstance(k, tuple)]
        for k in keys_to_fix:
            new_key = "|".join(str(part) for part in k)
            obj[new_key] = obj.pop(k)
        for v in obj.values():
            _sanitize_tuple_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            _sanitize_tuple_keys(item)


def restore_workspace_from_dict(ws_dict: dict[str, Any]) -> Any:
    """Deserialize a workspace dict into engine domain objects.

    Returns a Workspace instance with all dimensions, cubes, views, and rules.
    """
    from lib_openm.model import (
        CellFormat,
        Cube,
        Dimension,
        DimensionItem,
        OutlineNode,
        TableViewSpec,
        Workspace,
    )
    from lib_openm.persistence import _deserialize_value
    from lib_openm.rule_eval import Rule
    from lib_openm.lib_meta.bootstrap import ensure_system_cubes
    from lib_openm.outline_graph_bridge import migrate_workspace_outline_to_graph

    ws = Workspace(
        id=ws_dict.get("id", "ws_unknown"),
        name=ws_dict.get("name", "Restored"),
    )

    def _restore_outline(outline_list: list[dict]) -> list[OutlineNode]:
        result: list[OutlineNode] = []
        for node_dict in outline_list:
            node = OutlineNode(
                label=node_dict.get("label", ""),
                item_id=node_dict.get("item_id"),
                children=_restore_outline(node_dict.get("children", [])),
            )
            result.append(node)
        return result

    # Dimensions
    for dim_id, dim_dict in ws_dict.get("dimensions", {}).items():
        dim = Dimension(
            id=dim_dict["id"],
            name=dim_dict["name"],
            items=[],
            dim_type=dim_dict.get("dim_type", "set"),
            is_technical=dim_dict.get("is_technical", False),
            outline=_restore_outline(dim_dict.get("outline", [])),
        )
        for it in dim_dict.get("items", []):
            dim.items.append(DimensionItem(id=it["id"], name=it["name"]))
        outline_cache_raw = dim_dict.get("_outline_cache")
        if outline_cache_raw is not None:
            object.__setattr__(dim, "_outline_cache", _restore_outline(outline_cache_raw))
        else:
            object.__setattr__(dim, "_outline_cache", dim.outline)
        ws.dimensions[dim_id] = dim

    # Cubes
    for cube_id, cube_dict in ws_dict.get("cubes", {}).items():
        cube = Cube(
            id=cube_dict["id"],
            name=cube_dict["name"],
            dimension_ids=list(cube_dict.get("dimension_ids", [])),
            data={},
        )
        for k, v in cube_dict.get("data", {}).items():
            addr_str = k.replace("__dot__", ".") if isinstance(k, str) else k
            addr = tuple(addr_str.split("|")) if isinstance(addr_str, str) else addr_str
            deserialized, is_hardcoded = _deserialize_value(v)
            cube.data[addr] = deserialized
            if is_hardcoded:
                cube.user_override_addrs.add(addr)
        if not cube.user_override_addrs and cube_dict.get("user_override_addrs"):
            for addr_str in cube_dict.get("user_override_addrs", []):
                if isinstance(addr_str, str):
                    addr_raw = addr_str.replace("__dot__", ".")
                    cube.user_override_addrs.add(tuple(addr_raw.split("|")))
        ws.cubes[cube_id] = cube

    # Views
    for view_id, view_dict in ws_dict.get("views", {}).items():
        if "row_dim_ids" in view_dict and "col_dim_ids" in view_dict:
            row_dim_ids = list(view_dict.get("row_dim_ids") or [])
            col_dim_ids = list(view_dict.get("col_dim_ids") or [])
            page_dim_ids = list(view_dict.get("page_dim_ids") or [])
        else:
            row_dim_ids = [view_dict.get("row_dimension_id", "")]
            col_dim_ids = [view_dict.get("col_dimension_id", "")]
            page_dim_ids = []

        def _restore_cell_formats(fmt_dict: dict) -> dict[str, CellFormat]:
            result: dict[str, CellFormat] = {}
            for key, fmt in fmt_dict.items():
                if isinstance(fmt, dict):
                    result[key] = CellFormat(
                        bg_color=fmt.get("bg_color"),
                        font_color=fmt.get("font_color"),
                    )
                elif isinstance(fmt, CellFormat):
                    result[key] = fmt
            return result

        view = TableViewSpec(
            id=view_dict["id"],
            name=view_dict["name"],
            cube_id=view_dict["cube_id"],
            row_dim_ids=row_dim_ids,
            col_dim_ids=col_dim_ids,
            page_dim_ids=page_dim_ids,
            row_outline=_restore_outline(view_dict.get("row_outline", [])),
            col_outline=_restore_outline(view_dict.get("col_outline", [])),
            col_widths={int(k): v for k, v in view_dict.get("col_widths", {}).items()},
            row_header_widths={int(k): v for k, v in view_dict.get("row_header_widths", {}).items()},
            cell_formats=_restore_cell_formats(view_dict.get("cell_formats", {})),
            group_formats=_restore_cell_formats(view_dict.get("group_formats", {})),
            item_formats=_restore_cell_formats(view_dict.get("item_formats", {})),
        )
        ws.views[view_id] = view

    ws.views_order = ws_dict.get("views_order", list(ws.views.keys()))

    # Rules
    for rid, rdict in ws_dict.get("rules", {}).items():
        rule = Rule(
            id=rid,
            cube_id=rdict.get("cube_id", ""),
            expression=rdict.get("expression", ""),
            addr_mask=tuple(rdict.get("addr_mask", [])) if rdict.get("addr_mask") else None,
            targets=rdict.get("targets"),
            is_anchored=rdict.get("is_anchored", False),
        )
        ws.rules[rid] = rule

    # Rule order
    order_raw = ws_dict.get("rule_order")
    if isinstance(order_raw, list):
        ws.rule_order = [x for x in order_raw if isinstance(x, str)]
    else:
        ws.rule_order = list(ws.rules.keys())

    # Ensure system cubes and rebuild canonical graph
    ensure_system_cubes(ws)
    migrate_workspace_outline_to_graph(ws)

    return ws
