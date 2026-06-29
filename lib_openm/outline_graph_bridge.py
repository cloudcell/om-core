"""Bridge between Dimension.outline and %RECNOD / %RECEDG canonical graph store.

Canonical direction after migration: graph → outline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lib_openm.technical_ids import CHANNEL_TO_AT_ID
from lib_utils.ids import new_id

if TYPE_CHECKING:
    from lib_openm.model import Dimension, OutlineNode, Workspace


# ── helpers ──

def _dim_by_name(ws: "Workspace", name: str):
    for dim in ws.dimensions.values():
        if dim.name == name:
            return dim
    return None


def _cube_by_name(ws: "Workspace", name: str):
    for cube in ws.cubes.values():
        if cube.name == name:
            return cube
    return None


def _item_id(dim, name: str) -> str | None:
    for it in dim.items:
        if it.name == name:
            return it.id
    return None


def _has_graph_data(dim_id: str, ws: "Workspace") -> bool:
    """Return True if %RECNOD contains nodes AND %RECEDG contains edges for this dimension."""
    recnodadr = _dim_by_name(ws, "%RECNODADR")
    recnodfld = _dim_by_name(ws, "%RECNODFLD")
    recnod = _cube_by_name(ws, "%RECNOD")
    recedgadr = _dim_by_name(ws, "%RECEDGADR")
    recedgfld = _dim_by_name(ws, "%RECEDGFLD")
    recedg = _cube_by_name(ws, "%RECEDG")

    if any(x is None for x in (recnodadr, recnodfld, recnod, recedgadr, recedgfld, recedg)):
        return False

    dim_fld_id = _item_id(recnodfld, "DIM")
    if dim_fld_id is None:
        return False

    has_nodes = False
    for adr_item in recnodadr.items:
        if adr_item.name == "NUL":
            continue
        if recnod.get((CHANNEL_TO_AT_ID["value"], adr_item.id, dim_fld_id)) == dim_id:
            has_nodes = True
            break

    if not has_nodes:
        return False

    edge_dim_fld_id = _item_id(recedgfld, "DIM")
    if edge_dim_fld_id is None:
        return False

    for edge_adr in recedgadr.items:
        if edge_adr.name == "NUL":
            continue
        if recedg.get((CHANNEL_TO_AT_ID["value"], edge_adr.id, edge_dim_fld_id)) == dim_id:
            return True
    return False


# ── node operations ──

def create_group_node(dim_id: str, label: str, ws: "Workspace") -> str:
    """Create a GROUP node and return stable node_id.

    All record graph nodes use the unified ``nod_`` prefix.
    Group identity is determined by ``KND = GROUP``, not by the prefix.
    """
    node_id = new_id("nod")

    recnodadr = _dim_by_name(ws, "%RECNODADR")
    recnodfld = _dim_by_name(ws, "%RECNODFLD")
    recnod = _cube_by_name(ws, "%RECNOD")

    if recnodadr is None or recnodfld is None or recnod is None:
        raise RuntimeError("System cubes not bootstrapped. Call ensure_system_cubes() first.")

    recnodadr.add_item(node_id)
    node_adr_id = _item_id(recnodadr, node_id)

    knd_id = _item_id(recnodfld, "KND")
    dim_fld_id = _item_id(recnodfld, "DIM")
    lbl_id = _item_id(recnodfld, "LBL")

    addr_knd = (node_adr_id, knd_id)
    recnod.set(addr_knd, "GROUP")
    recnod.user_override_addrs.add((CHANNEL_TO_AT_ID["value"],) + addr_knd)

    addr_dim = (node_adr_id, dim_fld_id)
    recnod.set(addr_dim, dim_id)
    recnod.user_override_addrs.add((CHANNEL_TO_AT_ID["value"],) + addr_dim)

    addr_lbl = (node_adr_id, lbl_id)
    recnod.set(addr_lbl, label)
    recnod.user_override_addrs.add((CHANNEL_TO_AT_ID["value"],) + addr_lbl)

    return node_id


def ensure_item_node(dim_id: str, item_id: str, ws: "Workspace", label: str | None = None) -> str:
    """Ensure an ITEM_REF node exists for a dimension item and return node_id.

    If label is not provided, falls back to the dimension item's name.
    """
    # Fast path: in-memory index
    idx = ws._item_ref_index.get((dim_id, item_id))
    if idx is not None:
        return idx

    recnodadr = _dim_by_name(ws, "%RECNODADR")
    recnodfld = _dim_by_name(ws, "%RECNODFLD")
    recnod = _cube_by_name(ws, "%RECNOD")

    if recnodadr is None or recnodfld is None or recnod is None:
        raise RuntimeError("System cubes not bootstrapped. Call ensure_system_cubes() first.")

    knd_id = _item_id(recnodfld, "KND")
    dim_fld_id = _item_id(recnodfld, "DIM")
    ref_id = _item_id(recnodfld, "REF")

    # Slow fallback: linear scan
    for adr_item in recnodadr.items:
        if adr_item.name == "NUL":
            continue
        node_knd = recnod.get((CHANNEL_TO_AT_ID["value"], adr_item.id, knd_id))
        if node_knd != "ITEM_REF":
            continue
        node_dim = recnod.get((CHANNEL_TO_AT_ID["value"], adr_item.id, dim_fld_id))
        if node_dim != dim_id:
            continue
        node_ref = recnod.get((CHANNEL_TO_AT_ID["value"], adr_item.id, ref_id))
        if node_ref == item_id:
            # Populate the index for future fast lookups
            ws._item_ref_index[(dim_id, item_id)] = adr_item.name
            return adr_item.name

    # Resolve label: explicit > item name > item_id
    resolved_label = label
    if resolved_label is None:
        for dim in ws.dimensions.values():
            if dim.id == dim_id:
                for it in dim.items:
                    if it.id == item_id:
                        resolved_label = it.name
                        break
                break
    if resolved_label is None:
        resolved_label = item_id

    # Create new ITEM_REF node
    node_id = new_id("nod")
    recnodadr.add_item(node_id)
    node_adr_id = _item_id(recnodadr, node_id)

    lbl_id = _item_id(recnodfld, "LBL")

    addr_knd = (node_adr_id, knd_id)
    recnod.set(addr_knd, "ITEM_REF")
    recnod.user_override_addrs.add((CHANNEL_TO_AT_ID["value"],) + addr_knd)

    addr_dim = (node_adr_id, dim_fld_id)
    recnod.set(addr_dim, dim_id)
    recnod.user_override_addrs.add((CHANNEL_TO_AT_ID["value"],) + addr_dim)

    addr_ref = (node_adr_id, ref_id)
    recnod.set(addr_ref, item_id)
    recnod.user_override_addrs.add((CHANNEL_TO_AT_ID["value"],) + addr_ref)

    addr_lbl = (node_adr_id, lbl_id)
    recnod.set(addr_lbl, resolved_label)
    recnod.user_override_addrs.add((CHANNEL_TO_AT_ID["value"],) + addr_lbl)

    # Register in index for fast future lookups
    ws._item_ref_index[(dim_id, item_id)] = node_id

    return node_id


# ── edge operations ──

def _remove_edge(edge_id: str, ws: "Workspace") -> None:
    """Remove an edge from %RECEDG by edge ID."""
    recedgadr = _dim_by_name(ws, "%RECEDGADR")
    recedgfld = _dim_by_name(ws, "%RECEDGFLD")
    recedg = _cube_by_name(ws, "%RECEDG")

    if any(x is None for x in (recedgadr, recedgfld, recedg)):
        return

    edge_adr_id = _item_id(recedgadr, edge_id)
    if edge_adr_id is None:
        return

    for field_name in ("KND", "SRC", "TGT", "DIM", "ORD"):
        fld_id = _item_id(recedgfld, field_name)
        if fld_id is None:
            continue
        addr = (edge_adr_id, fld_id)
        full_addr = (CHANNEL_TO_AT_ID["value"],) + addr
        recedg.set(addr, None)
        recedg.user_override_addrs.discard(full_addr)
        recedg.user_override_addrs.discard(addr)


def _create_edge(
    edge_id: str,
    kind: str,
    src: str,
    tgt: str,
    dim_id: str,
    order: int,
    ws: "Workspace",
) -> str:
    """Create an edge in %RECEDG. Returns edge_id."""
    recedgadr = _dim_by_name(ws, "%RECEDGADR")
    recedgfld = _dim_by_name(ws, "%RECEDGFLD")
    recedg = _cube_by_name(ws, "%RECEDG")

    if recedgadr is None or recedgfld is None or recedg is None:
        raise RuntimeError("System cubes not bootstrapped. Call ensure_system_cubes() first.")

    recedgadr.add_item(edge_id)
    edge_adr_id = _item_id(recedgadr, edge_id)

    knd_id = _item_id(recedgfld, "KND")
    src_id = _item_id(recedgfld, "SRC")
    tgt_id = _item_id(recedgfld, "TGT")
    dim_fld_id = _item_id(recedgfld, "DIM")
    ord_id = _item_id(recedgfld, "ORD")

    addr_knd = (edge_adr_id, knd_id)
    recedg.set(addr_knd, kind)
    recedg.user_override_addrs.add((CHANNEL_TO_AT_ID["value"],) + addr_knd)

    addr_src = (edge_adr_id, src_id)
    recedg.set(addr_src, src)
    recedg.user_override_addrs.add((CHANNEL_TO_AT_ID["value"],) + addr_src)

    addr_tgt = (edge_adr_id, tgt_id)
    recedg.set(addr_tgt, tgt)
    recedg.user_override_addrs.add((CHANNEL_TO_AT_ID["value"],) + addr_tgt)

    addr_dim = (edge_adr_id, dim_fld_id)
    recedg.set(addr_dim, dim_id)
    recedg.user_override_addrs.add((CHANNEL_TO_AT_ID["value"],) + addr_dim)

    addr_ord = (edge_adr_id, ord_id)
    recedg.set(addr_ord, order)
    recedg.user_override_addrs.add((CHANNEL_TO_AT_ID["value"],) + addr_ord)

    return edge_id


def _add_member_edge(
    src_node_id: str, tgt_group_node_id: str, dim_id: str, order: int, ws: "Workspace"
) -> str:
    """Add MEMBER_OF edge from src_node to group_node. Returns edge_id.

    src_node may be either an ITEM_REF node or a GROUP node.
    The edge kind is always MEMBER_OF; node type is determined by %RECNOD.KND.
    """
    edge_id = new_id("edg")
    return _create_edge(edge_id, "MEMBER_OF", src_node_id, tgt_group_node_id, dim_id, order, ws)


def _add_aggregate_edge(
    item_node_id: str, group_node_id: str, dim_id: str, order: int, ws: "Workspace"
) -> str:
    """Add AGGREG_OF edge from item_node to group_node. Returns edge_id."""
    edge_id = new_id("edg")
    return _create_edge(edge_id, "AGGREG_OF", item_node_id, group_node_id, dim_id, order, ws)


# ── migration ──

def migrate_outline_to_graph(dim: "Dimension", ws: "Workspace") -> None:
    """Migration-only: traverse dim.outline and write group / item nodes plus edges."""
    dim_id = dim.id

    def _walk(node: "OutlineNode", parent_group_id: str | None, order: int) -> None:
        if node.item_id is not None:
            # Leaf item reference — always create a graph node (Phase 4: graph is canonical)
            item_node_id = ensure_item_node(dim_id, node.item_id, ws, label=node.label)
            node.node_id = item_node_id
            if parent_group_id is not None:
                _add_member_edge(item_node_id, parent_group_id, dim_id, order, ws)
        else:
            # Group node — reuse existing group if label matches
            group_id = find_group_node_id_by_label(dim_id, node.label, ws)
            if group_id is None:
                group_id = create_group_node(dim_id, node.label, ws)
            node.node_id = group_id
            if parent_group_id is not None:
                _add_member_edge(group_id, parent_group_id, dim_id, order, ws)
            for i, child in enumerate(node.children):
                _walk(child, group_id, i)

    for i, node in enumerate(dim.outline):
        _walk(node, None, i)


# ── rebuild ──

def rebuild_outline_from_graph(dim: "Dimension", ws: "Workspace") -> list["OutlineNode"]:
    """Read %RECNOD / %RECEDG and return a rebuilt outline tree.

    This is a read-only operation — it does NOT mutate dim.outline.
    To persist the rebuilt outline back to the dimension, call sync_graph_to_outline.
    """
    from lib_openm.model import OutlineNode

    dim_id = dim.id

    recnodadr = _dim_by_name(ws, "%RECNODADR")
    recnodfld = _dim_by_name(ws, "%RECNODFLD")
    recnod = _cube_by_name(ws, "%RECNOD")
    recedgadr = _dim_by_name(ws, "%RECEDGADR")
    recedgfld = _dim_by_name(ws, "%RECEDGFLD")
    recedg = _cube_by_name(ws, "%RECEDG")

    if any(x is None for x in (recnodadr, recnodfld, recnod, recedgadr, recedgfld, recedg)):
        return list(dim.outline)

    # ── Collect nodes for this dimension ──
    knd_id = _item_id(recnodfld, "KND")
    dim_fld_id = _item_id(recnodfld, "DIM")
    lbl_id = _item_id(recnodfld, "LBL")
    ref_id = _item_id(recnodfld, "REF")

    # node_id -> (kind, label, ref_value, root_order)
    node_meta: dict[str, tuple[str, str, str | None, int]] = {}

    ord_id = _item_id(recnodfld, "ORD")

    for adr_item in recnodadr.items:
        if adr_item.name == "NUL":
            continue
        node_dim = recnod.get((CHANNEL_TO_AT_ID["value"], adr_item.id, dim_fld_id))
        if node_dim != dim_id:
            continue
        kind = recnod.get((CHANNEL_TO_AT_ID["value"], adr_item.id, knd_id))
        label = recnod.get((CHANNEL_TO_AT_ID["value"], adr_item.id, lbl_id))
        ref = recnod.get((CHANNEL_TO_AT_ID["value"], adr_item.id, ref_id))
        ord_val = recnod.get((CHANNEL_TO_AT_ID["value"], adr_item.id, ord_id))
        order = ord_val if isinstance(ord_val, int) else 0
        node_meta[adr_item.name] = (kind, label or adr_item.name, ref, order)

    # ── Build parent relationships from edges ──
    edge_knd_id = _item_id(recedgfld, "KND")
    edge_src_id = _item_id(recedgfld, "SRC")
    edge_tgt_id = _item_id(recedgfld, "TGT")
    edge_dim_id = _item_id(recedgfld, "DIM")
    edge_ord_id = _item_id(recedgfld, "ORD")

    # parent_id -> [(order, child_id, edge_kind), ...]
    children: dict[str | None, list[tuple[int, str, str]]] = {}

    # First pass: mark all src nodes as placed
    placed: set[str] = set()
    for edge_adr in recedgadr.items:
        if edge_adr.name == "NUL":
            continue
        edge_dim = recedg.get((CHANNEL_TO_AT_ID["value"], edge_adr.id, edge_dim_id))
        if edge_dim != dim_id:
            continue

        src = recedg.get((CHANNEL_TO_AT_ID["value"], edge_adr.id, edge_src_id))
        tgt = recedg.get((CHANNEL_TO_AT_ID["value"], edge_adr.id, edge_tgt_id))

        if src not in node_meta:
            continue

        placed.add(src)

    # Second pass: build children map from edges pointing to nodes
    for edge_adr in recedgadr.items:
        if edge_adr.name == "NUL":
            continue
        edge_dim = recedg.get((CHANNEL_TO_AT_ID["value"], edge_adr.id, edge_dim_id))
        if edge_dim != dim_id:
            continue

        src = recedg.get((CHANNEL_TO_AT_ID["value"], edge_adr.id, edge_src_id))
        tgt = recedg.get((CHANNEL_TO_AT_ID["value"], edge_adr.id, edge_tgt_id))
        ord_val = recedg.get((CHANNEL_TO_AT_ID["value"], edge_adr.id, edge_ord_id))
        order = ord_val if isinstance(ord_val, int) else 0
        kind = recedg.get((CHANNEL_TO_AT_ID["value"], edge_adr.id, edge_knd_id))

        if src not in node_meta:
            continue
        if tgt not in node_meta:
            continue

        edge_kind = kind if kind == "AGGREG_OF" else "MEMBER_OF"
        children.setdefault(tgt, []).append((order, src, edge_kind))

    # ── Place root-level nodes with no parent edge ──
    for node_id, (_kind, _label, _ref, order) in node_meta.items():
        if node_id not in placed:
            children.setdefault(None, []).append((order, node_id, None))

    # ── Recursively build OutlineNode tree ──
    def _build_level(parent_id: str | None) -> list[OutlineNode]:
        child_list = sorted(children.get(parent_id, []), key=lambda x: x[0])

        # Separate MEMBER_OF and AGGREG_OF, preserving order within each kind
        member_list = [(o, nid, ek) for o, nid, ek in child_list if ek != "AGGREG_OF"]
        aggreg_list = [(o, nid, ek) for o, nid, ek in child_list if ek == "AGGREG_OF"]

        result: list[OutlineNode] = []
        for _order, node_id, edge_kind in member_list:
            kind, label, ref, _root_order = node_meta[node_id]
            if kind == "GROUP":
                result.append(
                    OutlineNode(
                        label=label,
                        node_id=node_id,
                        display_edge_kind=edge_kind,
                        children=_build_level(node_id),
                    )
                )
            else:
                result.append(
                    OutlineNode(
                        label=label,
                        node_id=node_id,
                        item_id=ref,
                        display_edge_kind=edge_kind,
                        children=[],
                    )
                )

        for _order, node_id, edge_kind in aggreg_list:
            _kind, label, ref, _root_order = node_meta[node_id]
            result.append(
                OutlineNode(
                    label=label,
                    node_id=node_id,
                    item_id=ref,
                    display_edge_kind=edge_kind,
                    is_aggregate=True,
                    children=[],
                )
            )

        return result

    tree = _build_level(None)

    # Only return graph-backed outlines.  Fallback synthetic nodes from
    # dim.items caused the GUI to believe an outline existed, which made
    # dropEvent take the outline-based reorder path.  That path returns
    # early when node_id is missing, so nothing happened.  By returning []
    # when there are no graph nodes, the GUI correctly falls back to
    # _reorder_flat_dimension (set_dimension_item_order).
    # dim.outline is still available via get_outline's dim.outline fallback.
    return tree


def _outline_equal(a: list["OutlineNode"], b: list["OutlineNode"]) -> bool:
    """Compare two outline trees for structural equality."""
    if len(a) != len(b):
        return False
    for na, nb in zip(a, b):
        if na.label != nb.label:
            return False
        if na.item_id != nb.item_id:
            return False
        if na.display_edge_kind != nb.display_edge_kind:
            return False
        if not _outline_equal(list(na.children), list(nb.children)):
            return False
    return True


def sync_graph_to_outline(dim: "Dimension", ws: "Workspace") -> None:
    """Rebuild dim.outline from %RECNOD / %RECEDG and persist it if different.

    This is the inverse of sync_outline_to_graph: graph is source of truth,
    and the dimension's outline list is updated to reflect the graph state.

    Only overwrites dim.outline when the graph actually differs, so unsynced
    GUI outline edits (e.g. drag reordering) are not clobbered by unrelated
    cube data changes.
    """
    rebuilt = rebuild_outline_from_graph(dim, ws)
    if not _outline_equal(dim.outline, rebuilt):
        object.__setattr__(dim, "outline", rebuilt)
    if rebuilt:
        object.__setattr__(dim, "_outline_cache", rebuilt)
    return not _outline_equal(dim.outline, rebuilt)


def sync_workspace_graph_to_outline(ws: "Workspace") -> None:
    """Rebuild outlines for all dimensions that have graph data."""
    for dim in ws.dimensions.values():
        if dim.name.startswith("%"):
            continue
        if _has_graph_data(dim.id, ws):
            sync_graph_to_outline(dim, ws)


# ── workspace-wide migration ──

def migrate_workspace_outline_to_graph(ws: "Workspace") -> None:
    """For existing workspaces, populate %RECNOD / %RECEDG from Dimension.outline if graph data is missing.

    Idempotent: dimensions that already have graph data are skipped.
    After migration, graph is source of truth and outline is derived cache.
    """
    for dim in ws.dimensions.values():
        if dim.name.startswith("%"):
            continue
        if not dim.outline:
            continue
        if _has_graph_data(dim.id, ws):
            continue
        migrate_outline_to_graph(dim, ws)



# ── query layer ──

def get_item_group_ids(dim_id: str, item_id: str, ws: "Workspace") -> list[str]:
    """Return stable group_node_ids containing this item."""
    # Find ITEM_REF node for (dim_id, item_id)
    recnodadr = _dim_by_name(ws, "%RECNODADR")
    recnodfld = _dim_by_name(ws, "%RECNODFLD")
    recnod = _cube_by_name(ws, "%RECNOD")
    recedgadr = _dim_by_name(ws, "%RECEDGADR")
    recedgfld = _dim_by_name(ws, "%RECEDGFLD")
    recedg = _cube_by_name(ws, "%RECEDG")

    if any(x is None for x in (recnodadr, recnodfld, recnod, recedgadr, recedgfld, recedg)):
        return []

    knd_id = _item_id(recnodfld, "KND")
    dim_fld_id = _item_id(recnodfld, "DIM")
    ref_id = _item_id(recnodfld, "REF")

    item_node_id: str | None = None
    for adr_item in recnodadr.items:
        if adr_item.name == "NUL":
            continue
        if recnod.get((CHANNEL_TO_AT_ID["value"], adr_item.id, knd_id)) != "ITEM_REF":
            continue
        if recnod.get((CHANNEL_TO_AT_ID["value"], adr_item.id, dim_fld_id)) != dim_id:
            continue
        if recnod.get((CHANNEL_TO_AT_ID["value"], adr_item.id, ref_id)) == item_id:
            item_node_id = adr_item.name
            break

    if item_node_id is None:
        return []

    # Traverse MEMBER_OF edges from this item node
    edge_knd_id = _item_id(recedgfld, "KND")
    edge_src_id = _item_id(recedgfld, "SRC")
    edge_tgt_id = _item_id(recedgfld, "TGT")
    edge_dim_id = _item_id(recedgfld, "DIM")

    group_ids: list[str] = []
    for edge_adr in recedgadr.items:
        if edge_adr.name == "NUL":
            continue
        if recedg.get((CHANNEL_TO_AT_ID["value"], edge_adr.id, edge_dim_id)) != dim_id:
            continue
        if recedg.get((CHANNEL_TO_AT_ID["value"], edge_adr.id, edge_knd_id)) != "MEMBER_OF":
            continue
        src = recedg.get((CHANNEL_TO_AT_ID["value"], edge_adr.id, edge_src_id))
        if src == item_node_id:
            tgt = recedg.get((CHANNEL_TO_AT_ID["value"], edge_adr.id, edge_tgt_id))
            group_ids.append(tgt)

    return group_ids


def get_group_items(dim_id: str, group_node_id: str, ws: "Workspace") -> list[str]:
    """Return item IDs in this group by traversing MEMBER_OF edges."""
    recedgadr = _dim_by_name(ws, "%RECEDGADR")
    recedgfld = _dim_by_name(ws, "%RECEDGFLD")
    recedg = _cube_by_name(ws, "%RECEDG")
    recnodadr = _dim_by_name(ws, "%RECNODADR")
    recnodfld = _dim_by_name(ws, "%RECNODFLD")
    recnod = _cube_by_name(ws, "%RECNOD")

    if any(x is None for x in (recedgadr, recedgfld, recedg, recnodadr, recnodfld, recnod)):
        return []

    edge_knd_id = _item_id(recedgfld, "KND")
    edge_tgt_id = _item_id(recedgfld, "TGT")
    edge_src_id = _item_id(recedgfld, "SRC")
    edge_dim_id = _item_id(recedgfld, "DIM")
    ref_id = _item_id(recnodfld, "REF")

    item_ids: list[str] = []
    for edge_adr in recedgadr.items:
        if edge_adr.name == "NUL":
            continue
        if recedg.get((CHANNEL_TO_AT_ID["value"], edge_adr.id, edge_dim_id)) != dim_id:
            continue
        if recedg.get((CHANNEL_TO_AT_ID["value"], edge_adr.id, edge_knd_id)) != "MEMBER_OF":
            continue
        tgt = recedg.get((CHANNEL_TO_AT_ID["value"], edge_adr.id, edge_tgt_id))
        if tgt != group_node_id:
            continue
        src = recedg.get((CHANNEL_TO_AT_ID["value"], edge_adr.id, edge_src_id))
        # src is a node_id; look up its item ref
        src_adr_id = _item_id(recnodadr, src)
        if src_adr_id is None:
            continue
        item_ref = recnod.get((CHANNEL_TO_AT_ID["value"], src_adr_id, ref_id))
        if item_ref is not None:
            item_ids.append(item_ref)

    return item_ids


def find_group_node_id_by_label(dim_id: str, label: str, ws: "Workspace") -> str | None:
    """Find a GROUP node ID by its label (case-insensitive)."""
    recnodadr = _dim_by_name(ws, "%RECNODADR")
    recnodfld = _dim_by_name(ws, "%RECNODFLD")
    recnod = _cube_by_name(ws, "%RECNOD")

    if any(x is None for x in (recnodadr, recnodfld, recnod)):
        return None

    knd_id = _item_id(recnodfld, "KND")
    dim_fld_id = _item_id(recnodfld, "DIM")
    lbl_id = _item_id(recnodfld, "LBL")

    label_lower = label.lower()
    for adr_item in recnodadr.items:
        if adr_item.name == "NUL":
            continue
        if recnod.get((CHANNEL_TO_AT_ID["value"], adr_item.id, knd_id)) != "GROUP":
            continue
        if recnod.get((CHANNEL_TO_AT_ID["value"], adr_item.id, dim_fld_id)) != dim_id:
            continue
        node_label = recnod.get((CHANNEL_TO_AT_ID["value"], adr_item.id, lbl_id))
        if isinstance(node_label, str) and node_label.lower() == label_lower:
            return adr_item.name
    return None


def get_group_all_leaf_items(dim_id: str, group_node_id: str, ws: "Workspace") -> list[str]:
    """Recursively collect all leaf item IDs under a group (including nested groups)."""
    recedgadr = _dim_by_name(ws, "%RECEDGADR")
    recedgfld = _dim_by_name(ws, "%RECEDGFLD")
    recedg = _cube_by_name(ws, "%RECEDG")
    recnodadr = _dim_by_name(ws, "%RECNODADR")
    recnodfld = _dim_by_name(ws, "%RECNODFLD")
    recnod = _cube_by_name(ws, "%RECNOD")

    if any(x is None for x in (recedgadr, recedgfld, recedg, recnodadr, recnodfld, recnod)):
        return []

    edge_knd_id = _item_id(recedgfld, "KND")
    edge_src_id = _item_id(recedgfld, "SRC")
    edge_tgt_id = _item_id(recedgfld, "TGT")
    edge_dim_id = _item_id(recedgfld, "DIM")
    ref_id = _item_id(recnodfld, "REF")
    knd_id = _item_id(recnodfld, "KND")

    leaf_items: list[str] = []
    child_groups: list[str] = []

    for edge_adr in recedgadr.items:
        if edge_adr.name == "NUL":
            continue
        if recedg.get((CHANNEL_TO_AT_ID["value"], edge_adr.id, edge_dim_id)) != dim_id:
            continue

        kind = recedg.get((CHANNEL_TO_AT_ID["value"], edge_adr.id, edge_knd_id))
        tgt = recedg.get((CHANNEL_TO_AT_ID["value"], edge_adr.id, edge_tgt_id))
        if tgt != group_node_id:
            continue

        src = recedg.get((CHANNEL_TO_AT_ID["value"], edge_adr.id, edge_src_id))
        if kind != "MEMBER_OF":
            continue
        # Determine src node kind to know if it's an item ref or a nested group
        src_adr_id = _item_id(recnodadr, src)
        if src_adr_id is None:
            continue
        src_knd = recnod.get((CHANNEL_TO_AT_ID["value"], src_adr_id, knd_id))
        if src_knd == "GROUP":
            child_groups.append(src)
        else:
            # ITEM_REF node; resolve to item_id
            item_ref = recnod.get((CHANNEL_TO_AT_ID["value"], src_adr_id, ref_id))
            if item_ref is not None:
                leaf_items.append(item_ref)

    # Recurse into child groups
    for child_group_id in child_groups:
        leaf_items.extend(get_group_all_leaf_items(dim_id, child_group_id, ws))

    return leaf_items


def get_group_tree(dim_id: str, ws: "Workspace") -> list["OutlineNode"]:
    """Return full outline tree reconstructed from %RECNOD / %RECEDG."""
    from lib_openm.model import Dimension

    # Find dimension by id
    dim: "Dimension" | None = None
    for d in ws.dimensions.values():
        if d.id == dim_id:
            dim = d
            break

    if dim is None:
        return []

    return rebuild_outline_from_graph(dim, ws)


def ensure_group_in_graph(
    dim_id: str,
    group_node: "OutlineNode" | str,
    ws: "Workspace",
    parent_group_id: str | None = None,
) -> str:
    """Ensure a group node exists in the graph and is properly attached.

    Transitional bridge method: moves GUI-only logic into bridge code.
    Idempotent. Returns the group node ID.

    ``group_node`` may be an :class:`OutlineNode` or a plain string label.
    """
    from lib_openm.graph_mutation import attach_edge, _delete_edge_raw, _set_node_root_ord
    from lib_openm.model import OutlineNode

    if isinstance(group_node, str):
        label = group_node
        group_node = OutlineNode(label=label, children=[])
    else:
        label = group_node.label
    group_id = find_group_node_id_by_label(dim_id, label, ws)

    if group_id is not None:
        # Already exists; attach under parent if not already attached
        if parent_group_id is not None:
            # Remove any existing parent edge if it points elsewhere
            existing_parent = _display_parent_edge(group_id, dim_id, ws)
            if existing_parent and existing_parent != parent_group_id:
                _delete_edge_raw(existing_parent, ws)
            # Create MEMBER_OF edge from parent to this group
            attach_edge(dim_id, parent_group_id, group_id, "MEMBER_OF", 0, ws=ws)
        return group_id

    # Create new GROUP node
    group_id = create_group_node(dim_id, label, ws)

    # Attach item nodes for each child that has an item_id
    for i, child in enumerate(group_node.children):
        if child.item_id is not None:
            child_id = ensure_item_node(dim_id, child.item_id, ws, label=child.label)
            attach_edge(dim_id, child_id, group_id, "MEMBER_OF", i, ws=ws)

    # Attach to parent group if specified
    if parent_group_id is not None:
        attach_edge(dim_id, parent_group_id, group_id, "MEMBER_OF", 0, ws=ws)
    else:
        # Set as root-level group
        _set_node_root_ord(group_id, 0, ws)

    # Invalidate cache so next read rebuilds with new group_node
    from lib_openm.model import Dimension
    dim: "Dimension" | None = None
    for d in ws.dimensions.values():
        if d.id == dim_id:
            dim = d
            break
    if dim is not None:
        dim.invalidate_outline_cache()

    return group_id
