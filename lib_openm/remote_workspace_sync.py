"""Workspace serialization for the remote engine.

Moved to lib_openm so that RemoteEngine does not depend on lib_runtime.
"""

from __future__ import annotations

from typing import Any


def workspace_to_msgpack_dict(ws: Any) -> dict[str, Any]:
    """Return a dict suitable for ``msgpack.packb`` and ``load_workspace_msgpack``."""
    from lib_openm.persistence import (
        _cube_to_dict,
        _dimension_to_dict,
        _rule_rule_to_dict,
        _serialize_value,
        _view_to_dict,
    )
    from lib_openm.lib_meta.bootstrap import ensure_system_cubes
    from lib_openm.outline_graph_bridge import migrate_workspace_outline_to_graph, extract_graph_for_remote
    from lib_openm.udf_registry import get_default_registry
    from lib_openm.technical_ids import normalize_addr, CHANNEL_TO_AT_ID

    ensure_system_cubes(ws)
    migrate_workspace_outline_to_graph(ws)

    udf_reg = get_default_registry()
    udf_list = udf_reg.serialize() if udf_reg else []

    dimensions_dict: dict[str, Any] = {
        k: _dimension_to_dict(v) for k, v in ws.dimensions.items()
    }

    # The "@" (channel) dimension is virtual in Python — it's never stored in
    # ws.dimensions but appears in cube.dimension_ids.  The remote server requires
    # every dimension ID referenced by a cube to exist in the dimensions map,
    # so we inject a synthetic entry with all technical channel items so the
    # remote engine can resolve channel names (e.g. "fill") to their canonical
    # item IDs (e.g. "at_fill") when building rule masks.
    if "@" not in dimensions_dict:
        dimensions_dict["@"] = {
            "id": "@",
            "name": "@",
            "dim_type": "set",
            "is_technical": True,
            "items": [
                {"id": at_id, "name": ch}
                for ch, at_id in CHANNEL_TO_AT_ID.items()
            ],
        }

    ws_dict: dict[str, Any] = {
        "id": ws.id,
        "name": ws.name,
        "dimensions": dimensions_dict,
        "cubes": {k: _cube_to_dict(v) for k, v in ws.cubes.items()},
        "rules": {k: _rule_rule_to_dict(v) for k, v in ws.rules.items()},
        "rule_order": list(ws.rule_order),
        "views": {k: _view_to_dict(v) for k, v in ws.views.items()},
        "views_order": list(ws.views_order),
        "udfs": udf_list,
    }
    if ws.saved_default_view_id is not None:
        ws_dict["saved_default_view_id"] = ws.saved_default_view_id

    graph_data = extract_graph_for_remote(ws)
    if graph_data is not None:
        ws_dict["graph"] = graph_data

    for cube_id, cube in ws_dict["cubes"].items():
        actual_cube = ws.cubes.get(cube_id)
        override_addrs_set = actual_cube.user_override_addrs if actual_cube else set()
        override_keys = {
            "|".join(normalize_addr(addr)) for addr in override_addrs_set
        }
        data = cube.get("data", {})
        serialized: dict[str, Any] = {}
        for k, v in data.items():
            key = "|".join(k)
            serialized[key] = _serialize_value(v, hardcoded=key in override_keys)
        cube["data"] = serialized

    return _stringify_dict_keys({"schema_version": 17, "workspace": ws_dict})


def _stringify_dict_keys(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _stringify_dict_keys(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_stringify_dict_keys(v) for v in obj]
    return obj
