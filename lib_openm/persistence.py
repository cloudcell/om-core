from __future__ import annotations

from dataclasses import asdict
import time
from types import SimpleNamespace
from typing import Any

from lib_openm.rule_eval import Rule
from lib_openm.rule_eval.utils import CellError
from lib_openm.model import CellFormat, Cube, Dimension, DimensionItem, OutlineNode, TableViewSpec, Workspace
from lib_openm.technical_ids import AT_PREFIX, CHANNEL_TO_AT_ID, normalize_addr, normalize_technical_item_id
from lib_openm.udf_registry import get_default_registry
from lib_utils.jsonutil import dump_file, load_file

def _serialize_value(v: Any, hardcoded: bool = False) -> Any:
    """Serialize a value to JSON-compatible tagged format.
    
    All values are wrapped with explicit type tags per the tagged value model:
    - Numbers: {"_type": "number", "value": 42.5} (includes booleans as 1.0/0.0)
    - Text: {"_type": "text", "value": "hello"}
    - Null: {"_type": "null"}
    - Error: {"_type": "error", "code": "#DIV/0!"}
    
    Hardcoded values (user overrides) include a "hardcoded": true flag:
    - Hardcoded number: {"_type": "number", "value": 42.5, "hardcoded": true}
    
    Note: Booleans are stored as numbers (1.0/0.0) like Excel, not as a separate type.
    """
    result: dict[str, Any]
    if isinstance(v, CellError):
        result = {"_type": "error", "code": v.code}
    elif v is None:
        result = {"_type": "null"}
    elif isinstance(v, bool):
        # Booleans are numeric (1.0/0.0) - no separate type, matching Excel behavior
        result = {"_type": "number", "value": 1.0 if v else 0.0}
    elif isinstance(v, (int, float)):
        result = {"_type": "number", "value": v}
    elif isinstance(v, str):
        result = {"_type": "text", "value": v}
    else:
        return v
    
    if hardcoded:
        result["hardcoded"] = True
    return result


def _deserialize_value(v: Any) -> tuple[Any, bool]:
    """Deserialize a tagged value back to runtime representation.
    
    Handles the tagged value format and legacy plain values.
    Returns tuple of (value, is_hardcoded) where is_hardcoded indicates
    if this value was user-entered (True) or computed (False).
    """
    if not isinstance(v, dict):
        # Legacy format: plain values - treat as hardcoded by default
        return (v, True)
    
    vtype = v.get("_type")
    is_hardcoded = v.get("hardcoded", False)  # New format includes hardcoded flag
    
    if vtype == "error":
        code = v.get("code", "#EXPRESSION!")
        value = CellError(code) if code in CellError._VALID_CODES else None
    elif vtype == "null":
        value = None
    elif vtype == "number":
        value = v.get("value", 0)
    elif vtype == "text":
        value = v.get("value", "")
    else:
        # Unknown type - return raw dict for debugging
        value = v
    
    return (value, is_hardcoded)


def _dimension_item_to_dict(item: DimensionItem) -> dict[str, Any]:
    """Convert DimensionItem to dict with ordered fields."""
    return {"id": item.id, "name": item.name}


def _outline_node_to_dict(node: OutlineNode) -> dict[str, Any]:
    """Convert OutlineNode to dict with ordered fields."""
    return {
        "label": node.label,
        "item_id": node.item_id,
        "children": [_outline_node_to_dict(c) for c in node.children],
    }


def _dimension_to_dict(dim: Dimension) -> dict[str, Any]:
    """Convert Dimension to dict with ordered fields.

    NOTE: outline is NOT persisted. %RECNOD / %RECEDG is the canonical
    source of truth for hierarchical structure. dim.outline is rebuilt
    from the graph on every load.
    """
    result: dict[str, Any] = {
        "id": dim.id,
        "name": dim.name,
        "items": [_dimension_item_to_dict(it) for it in dim.items],
        "dim_type": dim.dim_type,
        "is_technical": dim.is_technical,
    }
    override = getattr(dim, "_root_order_override", None)
    if override:
        result["root_order_override"] = dict(override)
    return result


def _cube_to_dict(cube: Cube) -> dict[str, Any]:
    """Convert Cube to dict with ordered fields."""
    return {
        "id": cube.id,
        "name": cube.name,
        "dimension_ids": list(cube.dimension_ids),
        "data": cube.data,
        # NOTE: user_override_addrs is NOT persisted separately anymore
        # Hardcoded status is embedded in value objects via _serialize_value
    }


def _view_to_dict(view: TableViewSpec) -> dict[str, Any]:
    """Convert TableViewSpec to dict with ordered fields.

    Note: Deprecated fields excluded:
    - cell_formats, group_formats, item_formats - formatting via @ dimension rules
    - row_outline, col_outline - stacking is flat/derived from dimension order
    """
    result: dict[str, Any] = {
        "id": view.id,
        "name": view.name,
        "cube_id": view.cube_id,
        "row_dim_ids": list(view.row_dim_ids),
        "col_dim_ids": list(view.col_dim_ids),
        "page_dim_ids": list(view.page_dim_ids),
        # NOTE: row_outline/col_outline not persisted - stacking is derived
        # from dimension order. Custom cross-dimensional groupings not supported.
        "col_widths": view.col_widths,
        "row_header_widths": view.row_header_widths,
    }
    # Save page selections (dim_id -> item_id)
    if view.page_selections:
        result["page_selections"] = dict(view.page_selections)
    # NOTE: Per-view UI state (active_cell, selection_mode, selected_indices,
    # anchor_cell, scroll_pos) is not persisted. It belongs to session state.
    return result


def _rule_rule_to_dict(r: Rule) -> dict[str, Any]:
    """Convert Rule to dict with ordered fields."""
    addr_mask = None
    if r.addr_mask is not None:
        addr_mask = [
            normalize_technical_item_id(x) if isinstance(x, str) else None
            for x in r.addr_mask
        ]
    return {
        "id": r.id,
        "cube_id": r.cube_id,
        "expression": r.expression,
        "addr_mask": addr_mask,
        "targets": [list(t) for t in r.targets] if r.targets is not None else None,
        "is_anchored": r.is_anchored,
    }


def _convert_cell_rule_to_anchored_rule(f: Any, ws: Workspace) -> Rule:
    """Convert a cell rule to an anchored rule.
    
    Cell rules target a single specific cell address. When converted to anchored rules,
    they use default items for any dimensions not explicitly specified.
    """
    cube = ws.cubes.get(f.cube_id)

    # Build addr_mask from cell address
    if f.addr and cube:
        mask_list: list[str | None] = []
        targets: list[tuple[str, str]] = []
        
        # Check if f.addr already includes @ dimension (full address)
        # or if it's a short address (without @ dimension)
        addr_includes_at = len(f.addr) == len(cube.dimension_ids) and (
            f.addr[0].startswith("@.") or f.addr[0].startswith(AT_PREFIX)
        )
        
        if addr_includes_at:
            # Full address - use it directly, matching each position
            for i, dim_id in enumerate(cube.dimension_ids):
                if i < len(f.addr):
                    item_id = f.addr[i]
                    mask_list.append(item_id)
                    # Get dimension name for target (skip @ dimension)
                    if dim_id != "@":
                        dim = ws.dimensions.get(dim_id)
                        if dim:
                            item_name = next((it.name for it in dim.items if it.id == item_id), item_id)
                            targets.append((dim.name, item_name))
                else:
                    mask_list.append(None)
        else:
            # Short address - map to non-@ dimensions
            addr_idx = 0
            for i, dim_id in enumerate(cube.dimension_ids):
                if dim_id == "@":
                    # @ dimension uses default value, not from rule address
                    mask_list.append(None)
                elif addr_idx < len(f.addr):
                    item_id = f.addr[addr_idx]
                    mask_list.append(item_id)
                    # Get dimension name for target
                    dim = ws.dimensions.get(dim_id)
                    if dim:
                        item_name = next((it.name for it in dim.items if it.id == item_id), item_id)
                        targets.append((dim.name, item_name))
                    addr_idx += 1
                else:
                    mask_list.append(None)
        addr_mask = tuple(mask_list)
        targets_tuple = tuple(targets)
    else:
        addr_mask = None
        targets_tuple = None

    return Rule(
        id=f.id,  # Preserve original ID
        cube_id=f.cube_id,
        expression=f.expression,
        addr_mask=addr_mask,
        targets=targets_tuple,
        is_anchored=True,  # Cell rules become anchored rules
    )


def save_workspace(path: str, ws: Workspace) -> None:
    # Build workspace dict with human-readable field order
    # Order: id, name, dimensions, cubes, rule_rules, views, views_order
    # NOTE: cell_rules are now migrated to anchored rules and excluded from saved files

    # Ensure system cubes exist and migrate any outline data to canonical graph store
    from lib_openm.lib_meta.bootstrap import ensure_system_cubes
    from lib_openm.outline_graph_bridge import migrate_workspace_outline_to_graph
    ensure_system_cubes(ws)
    migrate_workspace_outline_to_graph(ws)

    # All rules are now rules; no migration needed on save
    all_rules = dict(ws.rules)
    rule_order = list(ws.rule_order)

    # Serialize UDFs if any are registered
    udf_reg = get_default_registry()
    udf_list = udf_reg.serialize() if udf_reg else []

    ws_dict: dict[str, Any] = {
        "id": ws.id,
        "name": ws.name,
        "dimensions": {k: _dimension_to_dict(v) for k, v in ws.dimensions.items()},
        "cubes": {k: _cube_to_dict(v) for k, v in ws.cubes.items()},
        "rules": {k: _rule_rule_to_dict(v) for k, v in all_rules.items()},
        "rule_order": rule_order,
        # cell_rules section removed - all rules are now rules
        "views": {k: _view_to_dict(v) for k, v in ws.views.items()},
        "views_order": list(ws.views_order),
        # UDF definitions (schema v12+)
        "udfs": udf_list,
    }
    # Only views are physically active and visible
    if ws.active_view_id is not None:
        ws_dict["active_view_id"] = ws.active_view_id
    payload: dict[str, Any] = {
        "schema_version": 16,  # Schema 16: remove per-view UI selection state from workspace
        "workspace": ws_dict,
    }

    # Check if we should persist calculated values
    try:
        from lib_utils.config import engine as engine_config
        persist_calculated = engine_config("persistence", "persist_calculated_values", False)
    except Exception:
        persist_calculated = False  # Default to false (don't persist computed values)

    # tuple keys in cube.data need stringification
    # CellError values are serialized as tagged objects
    for cube_id, cube in payload["workspace"]["cubes"].items():
        data = cube.get("data", {})
        # Get user_override_addrs from the actual Cube object (not the dict)
        # This is needed to determine which values are hardcoded vs computed
        actual_cube = ws.cubes.get(cube_id)
        if actual_cube:
            override_addrs_set = actual_cube.user_override_addrs
            override_addrs_list = sorted(
                "|".join(normalize_addr(addr)) for addr in override_addrs_set
            )
        else:
            override_addrs_set = set()
            override_addrs_list = []

        if not persist_calculated:
            # Only persist data that is in user_override_addrs (hardcoded values)
            # Computed values from rules/rules are not persisted
            filtered_data = {}
            for k, v in data.items():
                addr_key = "|".join(k)
                # Only include hardcoded values (user overrides)
                is_hardcoded = addr_key in override_addrs_list
                if is_hardcoded:
                    filtered_data[addr_key] = _serialize_value(v, hardcoded=True)
            cube["data"] = filtered_data
        else:
            # Persist all values (legacy behavior)
            # Still embed hardcoded flag for user overrides
            cube["data"] = {
                "|".join(k): _serialize_value(v, hardcoded=("|".join(k) in override_addrs_list)) for k, v in data.items()
            }

    # Note: Deprecated cell_rules section removed - all rules are now rules.
    # Note: Deprecated cell_formats, group_formats, item_formats are already excluded
    # from views via _view_to_dict(). Formatting is handled via @ dimension rule rules.

    dump_file(path, payload)


def load_workspace(path: str) -> Workspace:
    ws, _ = load_workspace_profiled(path)
    return ws


def load_workspace_profiled(path: str) -> tuple[Workspace, dict[str, Any]]:
    profile: dict[str, Any] = {
        "path": path,
        "timings_ms": {},
        "counts": {
            "dimensions": 0,
            "dimension_items": 0,
            "cubes": 0,
            "cube_cells_loaded": 0,
            "cube_cells_skipped_errors": 0,
            "views": 0,
            "rules": 0,
        },
    }
    t_total = time.perf_counter()

    t0 = time.perf_counter()
    payload = load_file(path)
    profile["timings_ms"]["read_json"] = int((time.perf_counter() - t0) * 1000.0)

    schema_version = int(payload.get("schema_version", 1))
    ws_dict = payload["workspace"]

    ws = Workspace(id=ws_dict["id"], name=ws_dict["name"])

    def _load_outline(nodes_raw: Any) -> list[OutlineNode]:
        if not isinstance(nodes_raw, list):
            return []
        out: list[OutlineNode] = []
        for n in nodes_raw:
            if not isinstance(n, dict):
                continue
            label = n.get("label")
            if not isinstance(label, str):
                continue
            item_id = n.get("item_id")
            if not isinstance(item_id, str):
                item_id = None
            children = _load_outline(n.get("children"))
            out.append(OutlineNode(label=label, item_id=item_id, children=children))
        return out

    t0 = time.perf_counter()
    dim_count = 0
    dim_item_count = 0
    for dim_id, dim_dict in ws_dict.get("dimensions", {}).items():
        dim_type = dim_dict.get("dim_type", "set")
        if dim_type not in ("set", "seq"):
            dim_type = "set"
        is_technical = dim_dict.get("is_technical", False)
        dim = Dimension(
            id=dim_dict["id"],
            name=dim_dict["name"],
            items=[],
            dim_type=dim_type,
            is_technical=is_technical,
        )
        for it in dim_dict.get("items", []):
            dim.items.append(DimensionItem(id=it["id"], name=it["name"]))
            dim_item_count += 1
        # Phase 4: outline is read-only; bypass guard for JSON backward-compat load
        loaded = _load_outline(dim_dict.get("outline"))
        object.__setattr__(dim, "outline", loaded)
        object.__setattr__(dim, "_outline_cache", loaded)
        # Restore sparse root-order override (schema v15+)
        override = dim_dict.get("root_order_override")
        if override:
            object.__setattr__(dim, "_root_order_override", dict(override))
        ws.dimensions[dim_id] = dim
        dim_count += 1
    profile["timings_ms"]["hydrate_dimensions"] = int((time.perf_counter() - t0) * 1000.0)
    profile["counts"]["dimensions"] = dim_count
    profile["counts"]["dimension_items"] = dim_item_count

    t0 = time.perf_counter()
    cube_count = 0
    cube_cells_loaded = 0
    cube_cells_skipped_errors = 0
    for cube_id, cube_dict in ws_dict.get("cubes", {}).items():
        cube = Cube(
            id=cube_dict["id"],
            name=cube_dict["name"],
            dimension_ids=list(cube_dict["dimension_ids"]),
            data={},
        )

        # Migrate legacy cubes: add @ dimension if missing
        if "@" not in cube.dimension_ids and "@" in ws.dimensions:
            print(f"[LOAD] Migrating cube '{cube.name}' to include @ dimension")
            # Add @ to dimension_ids at the front
            cube.dimension_ids = ["@"] + cube.dimension_ids

        for k, v in cube_dict.get("data", {}).items():
            addr = normalize_addr(tuple(k.split("|")))

            # Handle tagged value format (new) and legacy plain values
            deserialized, is_hardcoded = _deserialize_value(v)
            
            # Handle legacy string error format: "#DIV/0!"
            if isinstance(v, str) and v.endswith("!") and v.startswith("#"):
                cube_cells_skipped_errors += 1
                print(f"[LOAD] Skipping legacy error value {v!r} at {cube_dict['name']}.{k} - will recalculate on load")
                continue
            
            if deserialized is None and isinstance(v, dict) and v.get("_type") == "error":
                # Invalid error code was deserialized to None
                cube_cells_skipped_errors += 1
                print(f"[LOAD] Skipping invalid error code at {cube_dict['name']}.{k} - will recalculate on load")
                continue

            if isinstance(deserialized, CellError):
                # Error values are skipped and recalculated on load
                cube_cells_skipped_errors += 1
                print(f"[LOAD] Skipping error value {deserialized.code!r} at {cube_dict['name']}.{k} - will recalculate on load")
                continue

            cube.data[addr] = deserialized
            cube_cells_loaded += 1
            
            # Reconstruct user_override_addrs from hardcoded flag
            if is_hardcoded:
                cube.user_override_addrs.add(addr)
        
        # Legacy: Load user_override_addrs from persisted list (for backward compatibility)
        # This handles old files that don't have the hardcoded flag in value objects
        if not cube.user_override_addrs and cube_dict.get("user_override_addrs"):
            for addr_str in cube_dict.get("user_override_addrs", []):
                if isinstance(addr_str, str):
                    cube.user_override_addrs.add(normalize_addr(tuple(addr_str.split("|"))))
        
        # Migrate data when dimensions are added (2D -> 3D, @ dimension added, etc.)
        expected_dims = len(cube.dimension_ids)
        if cube.data and any(len(addr) < expected_dims for addr in list(cube.data.keys())):
            # Old data has fewer dimensions - migrate to new format
            migrated_data: dict[tuple[str, ...], Any] = {}
            for old_addr, value in list(cube.data.items()):
                if len(old_addr) < expected_dims:
                    # Check if @ dimension was added (special case)
                    if "@" in cube.dimension_ids and "@" not in cube_dict.get("dimension_ids", []):
                        # @ was added - insert @.value at the correct position
                        at_idx = cube.dimension_ids.index("@")
                        padded = old_addr[:at_idx] + (CHANNEL_TO_AT_ID["value"],) + old_addr[at_idx:]
                    else:
                        # Pad with first items of new dimensions at the end
                        padded = list(old_addr)
                        for i in range(len(old_addr), expected_dims):
                            dim_id = cube.dimension_ids[i]
                            dim = ws.dimensions.get(dim_id)
                            if dim and dim.items:
                                padded.append(dim.items[0].id)
                            else:
                                padded.append("")
                        padded = tuple(padded)
                    migrated_data[padded] = value
                else:
                    migrated_data[old_addr] = value
            cube.data = migrated_data
            cube_cells_loaded = len(migrated_data)

        # Also migrate user_override_addrs
        if cube.user_override_addrs and any(len(addr) < expected_dims for addr in list(cube.user_override_addrs)):
            migrated_overrides: set[tuple[str, ...]] = set()
            for old_addr in list(cube.user_override_addrs):
                if len(old_addr) < expected_dims:
                    # Check if @ dimension was added (special case)
                    if "@" in cube.dimension_ids and "@" not in cube_dict.get("dimension_ids", []):
                        # @ was added - insert @.value at the correct position
                        at_idx = cube.dimension_ids.index("@")
                        padded = old_addr[:at_idx] + (CHANNEL_TO_AT_ID["value"],) + old_addr[at_idx:]
                    else:
                        # Pad with first items of new dimensions at the end
                        padded = list(old_addr)
                        for i in range(len(old_addr), expected_dims):
                            dim_id = cube.dimension_ids[i]
                            dim = ws.dimensions.get(dim_id)
                            if dim and dim.items:
                                # Only use default (first) item for overrides
                                padded.append(dim.items[0].id)
                            else:
                                padded.append("")
                        padded = tuple(padded)
                    migrated_overrides.add(padded)
                else:
                    migrated_overrides.add(old_addr)
            cube.user_override_addrs = migrated_overrides
        
        ws.cubes[cube_id] = cube
        cube_count += 1
    profile["timings_ms"]["hydrate_cubes"] = int((time.perf_counter() - t0) * 1000.0)
    profile["counts"]["cubes"] = cube_count
    profile["counts"]["cube_cells_loaded"] = cube_cells_loaded
    profile["counts"]["cube_cells_skipped_errors"] = cube_cells_skipped_errors

    # Collect legacy per-view UI state for schema < 16 migration.
    # Session layer reads this from profile and copies it into SessionViewState.
    if schema_version < 16:
        profile["legacy_ui_state"] = {
            view_id: {
                key: view_dict[key]
                for key in ("active_cell", "selection_mode", "selected_indices", "anchor_cell", "scroll_pos")
                if key in view_dict
            }
            for view_id, view_dict in ws_dict.get("views", {}).items()
        }
    else:
        profile["legacy_ui_state"] = {}

    t0 = time.perf_counter()
    view_count = 0
    for view_id, view_dict in ws_dict.get("views", {}).items():
        # Back-compat:
        # - schema v1/v2 stored row_dimension_id/col_dimension_id
        # - schema v3 stores row_dim_ids/col_dim_ids/page_dim_ids
        if "row_dim_ids" in view_dict and "col_dim_ids" in view_dict:
            row_dim_ids = list(view_dict.get("row_dim_ids") or [])
            col_dim_ids = list(view_dict.get("col_dim_ids") or [])
            page_dim_ids = list(view_dict.get("page_dim_ids") or [])
        else:
            row_dim_ids = [view_dict["row_dimension_id"]]
            col_dim_ids = [view_dict["col_dimension_id"]]
            page_dim_ids = []

        # Load col_widths and row_header_widths, converting string keys to int
        col_widths_raw = view_dict.get("col_widths", {})
        col_widths = {int(k): v for k, v in col_widths_raw.items()} if isinstance(col_widths_raw, dict) else {}
        
        row_header_widths_raw = view_dict.get("row_header_widths", {})
        row_header_widths = {int(k): v for k, v in row_header_widths_raw.items()} if isinstance(row_header_widths_raw, dict) else {}
        
        # Load format dictionaries and convert to CellFormat objects
        def _load_cell_format(fmt_dict: dict[str, Any] | None) -> CellFormat:
            if not isinstance(fmt_dict, dict):
                return CellFormat()
            # Load format_number, fall back to number_format for backward compatibility
            format_number = fmt_dict.get("format_number")
            if format_number is None:
                format_number = fmt_dict.get("number_format", "general")

            # Load font_weight, fall back from deprecated font_bold
            font_weight = fmt_dict.get("font_weight")
            if font_weight is None:
                # Backward compat: font_bold=True → 700 (bold), otherwise 400 (normal)
                font_weight = 700 if fmt_dict.get("font_bold", False) else 400
            else:
                font_weight = int(font_weight)

            return CellFormat(
                bg_color=fmt_dict.get("bg_color"),
                font_color=fmt_dict.get("font_color"),
                font_family=fmt_dict.get("font_family"),
                font_size=fmt_dict.get("font_size"),
                font_weight=font_weight,
                font_italic=fmt_dict.get("font_italic", False),
                format_number=format_number,
                format_text=fmt_dict.get("format_text", ""),
                format_null=fmt_dict.get("format_null", ""),
                format_error=fmt_dict.get("format_error", ""),
                number_format=fmt_dict.get("number_format", "general"),  # Deprecated
                decimal_places=fmt_dict.get("decimal_places", 2),
                border_top=fmt_dict.get("border_top", "none"),
                border_bottom=fmt_dict.get("border_bottom", "none"),
                border_left=fmt_dict.get("border_left", "none"),
                border_right=fmt_dict.get("border_right", "none"),
                border_style=fmt_dict.get("border_style", "solid"),
                border_color=fmt_dict.get("border_color", "#000000"),
                text_h_align=fmt_dict.get("text_h_align") or fmt_dict.get("h_align", "left"),
                text_v_align=fmt_dict.get("text_v_align") or fmt_dict.get("v_align", "middle"),
                text_indent=fmt_dict.get("text_indent") if fmt_dict.get("text_indent") is not None else fmt_dict.get("indent", 0),
                text_wrap=fmt_dict.get("text_wrap") if fmt_dict.get("text_wrap") is not None else fmt_dict.get("wrap_text", False),
                text_rotation=fmt_dict.get("text_rotation") if fmt_dict.get("text_rotation") is not None else fmt_dict.get("rotation", 0),
            )
        
        cell_formats_raw = view_dict.get("cell_formats", {})
        cell_formats = {k: _load_cell_format(v) for k, v in cell_formats_raw.items()} if isinstance(cell_formats_raw, dict) else {}
        
        group_formats_raw = view_dict.get("group_formats", {})
        group_formats = {k: _load_cell_format(v) for k, v in group_formats_raw.items()} if isinstance(group_formats_raw, dict) else {}
        
        item_formats_raw = view_dict.get("item_formats", {})
        item_formats = {k: _load_cell_format(v) for k, v in item_formats_raw.items()} if isinstance(item_formats_raw, dict) else {}
        
        # Load page selections (dim_id -> item_id)
        page_selections_raw = view_dict.get("page_selections", {})
        page_selections = dict(page_selections_raw) if isinstance(page_selections_raw, dict) else {}

        # Schema v16 and later: per-view UI state is not loaded into the workspace.
        # Legacy schema <=15 UI state is captured in profile["legacy_ui_state"] for
        # migration by the session layer.
        ws.views[view_id] = TableViewSpec(
            id=view_dict["id"],
            name=view_dict["name"],
            cube_id=view_dict["cube_id"],
            row_dim_ids=row_dim_ids,
            col_dim_ids=col_dim_ids,
            page_dim_ids=page_dim_ids,
            row_outline=_load_outline(view_dict.get("row_outline")),
            col_outline=_load_outline(view_dict.get("col_outline")),
            col_widths=col_widths,
            row_header_widths=row_header_widths,
            cell_formats=cell_formats,
            group_formats=group_formats,
            item_formats=item_formats,
            page_selections=page_selections,
        )
        view_count += 1
    profile["timings_ms"]["hydrate_views"] = int((time.perf_counter() - t0) * 1000.0)
    profile["counts"]["views"] = view_count

    t0 = time.perf_counter()
    rule_count = 0
    rules_raw = ws_dict.get("rules", {})
    if schema_version >= 4 and rules_raw:
        for rid, r_dict in rules_raw.items():
            # addr_mask was introduced in schema v9; tolerate its absence for
            # older workspaces.
            raw_mask = r_dict.get("addr_mask")
            addr_mask = None
            if isinstance(raw_mask, list):
                addr_mask = tuple(
                    normalize_technical_item_id(x) if isinstance(x, str) else None
                    for x in raw_mask
                )
            raw_targets = r_dict.get("targets")
            targets = None
            if isinstance(raw_targets, list):
                normalized: list[tuple[str, str]] = []
                for pair in raw_targets:
                    if isinstance(pair, (list, tuple)) and len(pair) == 2:
                        dim_name, item_name = pair
                        if isinstance(dim_name, str) and isinstance(item_name, str):
                            normalized.append((dim_name, item_name))
                if normalized:
                    targets = tuple(normalized)
            # is_anchored was introduced in schema v12; tolerate its absence
            is_anchored = r_dict.get("is_anchored", False)
            ws.rules[rid] = Rule(
                id=r_dict["id"],
                cube_id=r_dict["cube_id"],
                expression=r_dict["expression"],
                addr_mask=addr_mask,
                targets=targets,
                is_anchored=is_anchored,
            )
            rule_count += 1
    profile["timings_ms"]["hydrate_rules"] = int((time.perf_counter() - t0) * 1000.0)
    profile["counts"]["rules"] = rule_count

    # Load UDF definitions if present in the workspace file
    t0 = time.perf_counter()
    udf_count = 0
    udf_dicts = ws_dict.get("udfs", [])
    if isinstance(udf_dicts, list) and udf_dicts:
        try:
            udf_reg = get_default_registry()
            udf_reg.deserialize(udf_dicts)
            udf_count = len(udf_dicts)
        except Exception as e:
            print(f"[UDF] Warning: failed to load UDFs: {e}")
    profile["timings_ms"]["hydrate_udfs"] = int((time.perf_counter() - t0) * 1000.0)
    profile["counts"]["udfs"] = udf_count

    order_raw = ws_dict.get("rule_order")
    if isinstance(order_raw, list):
        ws.rule_order = [x for x in order_raw if isinstance(x, str)]
    else:
        ws.rule_order = list(ws.rules.keys())

    views_order_raw = ws_dict.get("views_order")
    if isinstance(views_order_raw, list):
        ws.views_order = [x for x in views_order_raw if isinstance(x, str)]
    else:
        ws.views_order = list(ws.views.keys())

    # Load active view ID (only views are physically active and visible)
    active_view_id = ws_dict.get("active_view_id")
    if isinstance(active_view_id, str) and active_view_id in ws.views:
        ws.active_view_id = active_view_id

    # Ensure @ technical dimension exists with all standard items
    # This handles both new workspaces and loaded workspaces that may be missing
    # the @ dimension or have an incomplete set of technical items
    ws._ensure_at_dimension()

    # Ensure self-describing system cubes exist (%CFG, %SIG, %TYP, %RECNOD, %RECEDG)
    from lib_openm.lib_meta.bootstrap import ensure_system_cubes
    ensure_system_cubes(ws)

    # Auto-migrate any existing Dimension.outline data to canonical graph store
    from lib_openm.outline_graph_bridge import (
        migrate_workspace_outline_to_graph,
        sync_workspace_graph_to_outline,
    )
    migrate_workspace_outline_to_graph(ws)

    # After migration, rebuild outlines from graph so dim.outline reflects graph state
    sync_workspace_graph_to_outline(ws)

    profile["timings_ms"]["total"] = int((time.perf_counter() - t_total) * 1000.0)
    return ws, profile
