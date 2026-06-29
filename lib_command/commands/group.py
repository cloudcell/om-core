"""Group commands — CRUD for outline groups via %RECNOD / %RECEDG."""

from __future__ import annotations

from typing import Any

from lib_openm.outline_graph_bridge import (
    _cube_by_name,
    _dim_by_name,
    _item_id,
)
from lib_openm.dto.outline import OutlinePatch


def _get_ws(ctx):
    ws = getattr(ctx, "workspace", None)
    if ws is None:
        raise ValueError("No workspace available in context")
    return ws


def cmd_group_create(
    ctx,
    dim_id: str,
    label: str,
    parent_group_node_id: str | None = None,
    order: int = 0,
) -> dict[str, Any]:
    """Create a new group node in the outline graph.

    Args:
        dim_id: Dimension ID where the group lives.
        label: Display label for the group.
        parent_group_node_id: Optional parent group node ID (creates MEMBER_OF edge).
        order: Position among siblings.
    """
    from lib_openm.outline_graph_bridge import create_group_node, _add_member_edge

    ws = _get_ws(ctx)
    group_id = create_group_node(dim_id, label, ws)

    if parent_group_node_id:
        _add_member_edge(group_id, parent_group_node_id, dim_id, order, ws)

    ctx.status(f"Created group '{label}' ({group_id[:8]}...)")
    patch = OutlinePatch(
        patch_type="group_created",
        dim_id=dim_id,
        payload={
            "group_node_id": group_id,
            "label": label,
            "parent_group_node_id": parent_group_node_id,
            "order": order,
        },
    )
    return {
        "group_node_id": group_id,
        "label": label,
        "dim_id": dim_id,
        "parent_group_node_id": parent_group_node_id,
        "patches": [patch],
    }


def cmd_group_add_items(
    ctx,
    dim_id: str,
    item_ids: list[str],
    group_node_id: str,
    order: int = 0,
) -> dict[str, Any]:
    """Add dimension items to a group.

    Args:
        dim_id: Dimension ID.
        item_ids: List of dimension item IDs to add.
        group_node_id: Target group node ID.
        order: Starting position for new members.
    """
    from lib_openm.outline_graph_bridge import ensure_item_node, _add_member_edge

    ws = _get_ws(ctx)
    edge_ids: list[str] = []
    for i, item_id in enumerate(item_ids):
        item_node_id = ensure_item_node(dim_id, item_id, ws)
        edge_id = _add_member_edge(item_node_id, group_node_id, dim_id, order + i, ws)
        edge_ids.append(edge_id)

    ctx.status(f"Added {len(item_ids)} item(s) to group {group_node_id[:8]}...)")
    patch = OutlinePatch(
        patch_type="items_added_to_group",
        dim_id=dim_id,
        payload={
            "group_node_id": group_node_id,
            "item_ids": item_ids,
            "edge_ids": edge_ids,
            "order": order,
        },
    )
    return {
        "dim_id": dim_id,
        "group_node_id": group_node_id,
        "item_ids": item_ids,
        "edge_ids": edge_ids,
        "patches": [patch],
    }


def cmd_group_remove_items(
    ctx,
    dim_id: str,
    item_ids: list[str],
    group_node_id: str,
) -> dict[str, Any]:
    """Remove dimension items from a group.

    Args:
        dim_id: Dimension ID.
        item_ids: List of dimension item IDs to remove.
        group_node_id: Target group node ID.
    """
    from lib_openm.outline_graph_bridge import _remove_edge

    ws = _get_ws(ctx)
    recedgadr = _dim_by_name(ws, "%RECEDGADR")
    recedgfld = _dim_by_name(ws, "%RECEDGFLD")
    recedg = _cube_by_name(ws, "%RECEDG")

    if any(x is None for x in (recedgadr, recedgfld, recedg)):
        raise RuntimeError("System cubes not bootstrapped")

    edge_knd_id = _item_id(recedgfld, "KND")
    edge_src_id = _item_id(recedgfld, "SRC")
    edge_tgt_id = _item_id(recedgfld, "TGT")
    edge_dim_id = _item_id(recedgfld, "DIM")

    # Build item_node_id -> item_id map
    from lib_openm.outline_graph_bridge import ensure_item_node
    item_node_map: dict[str, str] = {}
    for item_id in item_ids:
        node_id = ensure_item_node(dim_id, item_id, ws)
        item_node_map[node_id] = item_id

    removed: list[str] = []
    for edge_adr in list(recedgadr.items):
        if edge_adr.name == "NUL":
            continue
        if recedg.get(("@.value", edge_adr.id, edge_dim_id)) != dim_id:
            continue
        if recedg.get(("@.value", edge_adr.id, edge_knd_id)) != "MEMBER_OF":
            continue
        if recedg.get(("@.value", edge_adr.id, edge_tgt_id)) != group_node_id:
            continue
        src = recedg.get(("@.value", edge_adr.id, edge_src_id))
        if src in item_node_map:
            _remove_edge(edge_adr.name, ws)
            removed.append(item_node_map[src])

    ctx.status(f"Removed {len(removed)} item(s) from group {group_node_id[:8]}...")
    patch = OutlinePatch(
        patch_type="items_removed_from_group",
        dim_id=dim_id,
        payload={
            "group_node_id": group_node_id,
            "item_ids": removed,
        },
    )
    return {
        "dim_id": dim_id,
        "group_node_id": group_node_id,
        "removed_item_ids": removed,
        "patches": [patch],
    }


def cmd_group_remove(
    ctx,
    dim_id: str,
    group_node_id: str,
    cascade: bool = True,
) -> dict[str, Any]:
    """Remove a group node and optionally cascade to children.

    Args:
        dim_id: Dimension ID.
        group_node_id: Group node ID to remove.
        cascade: If True, remove all edges involving this node.
    """
    from lib_openm.outline_graph_bridge import _remove_edge

    ws = _get_ws(ctx)
    recedgadr = _dim_by_name(ws, "%RECEDGADR")
    recedgfld = _dim_by_name(ws, "%RECEDGFLD")
    recedg = _cube_by_name(ws, "%RECEDG")
    recnodadr = _dim_by_name(ws, "%RECNODADR")
    recnodfld = _dim_by_name(ws, "%RECNODFLD")
    recnod = _cube_by_name(ws, "%RECNOD")

    if any(x is None for x in (recedgadr, recedgfld, recedg, recnodadr, recnodfld, recnod)):
        raise RuntimeError("System cubes not bootstrapped")

    edge_knd_id = _item_id(recedgfld, "KND")
    edge_src_id = _item_id(recedgfld, "SRC")
    edge_tgt_id = _item_id(recedgfld, "TGT")
    edge_dim_id = _item_id(recedgfld, "DIM")

    removed_edges: list[str] = []
    if cascade:
        for edge_adr in list(recedgadr.items):
            if edge_adr.name == "NUL":
                continue
            if recedg.get(("@.value", edge_adr.id, edge_dim_id)) != dim_id:
                continue
            src = recedg.get(("@.value", edge_adr.id, edge_src_id))
            tgt = recedg.get(("@.value", edge_adr.id, edge_tgt_id))
            if src == group_node_id or tgt == group_node_id:
                _remove_edge(edge_adr.name, ws)
                removed_edges.append(edge_adr.name)

    # Mark node as inactive in %RECNOD
    node_adr_id = _item_id(recnodadr, group_node_id)
    if node_adr_id is not None:
        act_id = _item_id(recnodfld, "ACT")
        if act_id is not None:
            recnod.set((node_adr_id, act_id), False)
            recnod.user_override_addrs.add(("@.value", node_adr_id, act_id))

    ctx.status(f"Removed group {group_node_id[:8]}... ({len(removed_edges)} edge(s))")
    patch = OutlinePatch(
        patch_type="group_deleted",
        dim_id=dim_id,
        payload={
            "group_node_id": group_node_id,
            "cascade": cascade,
            "affected_edge_ids": removed_edges,
        },
    )
    return {
        "dim_id": dim_id,
        "group_node_id": group_node_id,
        "removed_edges": removed_edges,
        "cascade": cascade,
        "patches": [patch],
    }


def _resolve_group_ref(group_ref: dict, dim_id: str, ws: Any) -> str | None:
    """Resolve a group_ref dict to a group_node_id, or None for root.

    Raises ValueError if a label lookup fails.
    """
    kind = group_ref.get("kind")
    value = group_ref.get("value")
    if kind == "root":
        return None
    elif kind == "id":
        return value
    elif kind == "label":
        from lib_openm.outline_graph_bridge import find_group_node_id_by_label
        group_node_id = find_group_node_id_by_label(dim_id, value, ws)
        if group_node_id is None:
            raise ValueError(f"Group not found: {value!r}")
        return group_node_id
    else:
        raise ValueError(f"Unknown group_ref kind: {kind}")


def cmd_create_group(
    ctx,
    dim_id: str,
    label: str,
    parent_group_node_id: str | None = None,
    order: int = 0,
) -> dict[str, Any]:
    """Create a new group — canonical command.

    Thin wrapper around :func:`cmd_group_create` for canonical naming.
    """
    return cmd_group_create(ctx, dim_id, label, parent_group_node_id, order)


def cmd_delete_group(
    ctx,
    dim_id: str,
    group_node_id: str,
    cascade: bool = True,
) -> dict[str, Any]:
    """Delete a group — canonical command.

    Thin wrapper around :func:`cmd_group_remove` for canonical naming.
    """
    return cmd_group_remove(ctx, dim_id, group_node_id, cascade)


def cmd_move_items_to_group(
    ctx,
    dim_id: str,
    item_ids: list[str],
    group_ref: dict | None = None,
    group_node_id: str | None = None,
) -> dict[str, Any]:
    """Move dimension items to a group using a ``group_ref``.

    Canonical command.  ``group_ref`` may be:

    * ``{"kind": "root", "value": null}`` — move items to root
    * ``{"kind": "id", "value": "grp_..."}`` — move to group by node ID
    * ``{"kind": "label", "value": "Revenue"}`` — resolve label to node ID

    For backward compatibility, ``group_node_id`` may be passed directly
    instead of ``group_ref``.
    """
    if not dim_id:
        raise ValueError("dim_id is required")
    if not item_ids:
        raise ValueError("item_ids is required")
    if group_ref is not None and group_node_id is not None:
        raise ValueError("Cannot specify both group_ref and group_node_id")

    if group_ref is not None:
        ws = _get_ws(ctx)
        resolved_id = _resolve_group_ref(group_ref, dim_id, ws)
    elif group_node_id is not None:
        resolved_id = group_node_id
    else:
        raise ValueError("Must provide either group_ref or group_node_id")

    if resolved_id is None:
        from lib_command.commands.handlers import handle_ungroup_items_adapter
        handle_ungroup_items_adapter(ctx, dim_id, item_ids)
        return {"affected": len(item_ids), "property": "items_moved", "dim_id": dim_id, "dest": "root"}

    from lib_command.commands.handlers import handle_move_items_to_group_adapter
    handle_move_items_to_group_adapter(ctx, dim_id, item_ids, resolved_id)
    return {"affected": len(item_ids), "property": "items_moved", "dim_id": dim_id, "group_node_id": resolved_id}
