"""Graph mutation primitives for %RECNOD / %RECEDG.

Phase 2 deliverable: low-level primitives that speak node_id and enforce invariants.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Literal

from lib_openm.technical_ids import CHANNEL_TO_AT_ID
from lib_utils.ids import new_id

if TYPE_CHECKING:
    from lib_openm.model import Dimension, Workspace


# ── helpers (mirrored from outline_graph_bridge for self-containment) ──


def _dim_by_name(ws: "Workspace", name: str) -> "Dimension" | None:
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


# ── GraphIssue ──


@dataclass
class GraphIssue:
    code: str
    message: str
    severity: Literal["warning", "error"]
    node_id: str | None = None
    edge_id: str | None = None


# ── low-level record access helpers ──


def _get_system_cubes(ws: "Workspace"):
    recnodadr = _dim_by_name(ws, "%RECNODADR")
    recnodfld = _dim_by_name(ws, "%RECNODFLD")
    recnod = _cube_by_name(ws, "%RECNOD")
    recedgadr = _dim_by_name(ws, "%RECEDGADR")
    recedgfld = _dim_by_name(ws, "%RECEDGFLD")
    recedg = _cube_by_name(ws, "%RECEDG")
    if any(x is None for x in (recnodadr, recnodfld, recnod, recedgadr, recedgfld, recedg)):
        raise RuntimeError("System cubes not bootstrapped. Call ensure_system_cubes() first.")
    return recnodadr, recnodfld, recnod, recedgadr, recedgfld, recedg


def _read_node_meta(node_id: str, ws: "Workspace") -> dict | None:
    """Read metadata for a single node from %RECNOD."""
    recnodadr, recnodfld, recnod, *_ = _get_system_cubes(ws)
    adr_id = _item_id(recnodadr, node_id)
    if adr_id is None:
        return None
    knd_id = _item_id(recnodfld, "KND")
    dim_fld_id = _item_id(recnodfld, "DIM")
    lbl_id = _item_id(recnodfld, "LBL")
    ref_id = _item_id(recnodfld, "REF")
    ord_id = _item_id(recnodfld, "ORD")
    return {
        "node_id": node_id,
        "kind": recnod.get((CHANNEL_TO_AT_ID["value"], adr_id, knd_id)) if knd_id else None,
        "dim_id": recnod.get((CHANNEL_TO_AT_ID["value"], adr_id, dim_fld_id)) if dim_fld_id else None,
        "label": recnod.get((CHANNEL_TO_AT_ID["value"], adr_id, lbl_id)) if lbl_id else None,
        "ref": recnod.get((CHANNEL_TO_AT_ID["value"], adr_id, ref_id)) if ref_id else None,
        "root_ord": recnod.get((CHANNEL_TO_AT_ID["value"], adr_id, ord_id)) if ord_id else None,
    }


def _all_nodes_for_dim(dim_id: str, ws: "Workspace") -> list[dict]:
    """Return all %RECNOD metadata dicts for a given dimension."""
    recnodadr, recnodfld, recnod, *_ = _get_system_cubes(ws)
    dim_fld_id = _item_id(recnodfld, "DIM")
    if dim_fld_id is None:
        return []
    result = []
    for adr_item in recnodadr.items:
        if adr_item.name == "NUL":
            continue
        node_dim = recnod.get((CHANNEL_TO_AT_ID["value"], adr_item.id, dim_fld_id))
        if node_dim != dim_id:
            continue
        meta = _read_node_meta(adr_item.name, ws)
        if meta:
            result.append(meta)
    return result


def _all_edges_for_dim(dim_id: str, ws: "Workspace") -> list[dict]:
    """Return all %RECEDG metadata dicts for a given dimension."""
    _, _, _, recedgadr, recedgfld, recedg = _get_system_cubes(ws)
    dim_fld_id = _item_id(recedgfld, "DIM")
    if dim_fld_id is None:
        return []
    knd_id = _item_id(recedgfld, "KND")
    src_id = _item_id(recedgfld, "SRC")
    tgt_id = _item_id(recedgfld, "TGT")
    ord_id = _item_id(recedgfld, "ORD")
    result = []
    for adr_item in recedgadr.items:
        if adr_item.name == "NUL":
            continue
        edge_dim = recedg.get((CHANNEL_TO_AT_ID["value"], adr_item.id, dim_fld_id))
        if edge_dim != dim_id:
            continue
        edge = {
            "edge_id": adr_item.name,
            "kind": recedg.get((CHANNEL_TO_AT_ID["value"], adr_item.id, knd_id)) if knd_id else None,
            "src": recedg.get((CHANNEL_TO_AT_ID["value"], adr_item.id, src_id)) if src_id else None,
            "tgt": recedg.get((CHANNEL_TO_AT_ID["value"], adr_item.id, tgt_id)) if tgt_id else None,
            "ord": recedg.get((CHANNEL_TO_AT_ID["value"], adr_item.id, ord_id)) if ord_id else None,
        }
        result.append(edge)
    return result


def _display_parent_edge(node_id: str, dim_id: str, ws: "Workspace") -> dict | None:
    """Return the single display parent edge (MEMBER_OF or AGGREG_OF) for a node, or None."""
    for edge in _all_edges_for_dim(dim_id, ws):
        if edge["src"] == node_id and edge["kind"] in ("MEMBER_OF", "AGGREG_OF"):
            return edge
    return None


def _delete_edge_raw(edge_id: str, ws: "Workspace") -> None:
    """Physically delete an edge from %RECEDG."""
    _, _, _, recedgadr, recedgfld, recedg = _get_system_cubes(ws)
    edge_adr_id = _item_id(recedgadr, edge_id)
    if edge_adr_id is None:
        return
    # Clear every field
    for fld_item in recedgfld.items:
        if fld_item.name == "NUL":
            continue
        fld_id = fld_item.id
        addr = (edge_adr_id, fld_id)
        full_addr = (CHANNEL_TO_AT_ID["value"],) + addr
        recedg.set(addr, None)
        recedg.user_override_addrs.discard(full_addr)
        recedg.user_override_addrs.discard(addr)
    # Remove the edge from the address dimension so the row disappears
    for i, it in enumerate(recedgadr.items):
        if it.name == edge_id:
            recedgadr.items.pop(i)
            break


def _create_edge_raw(
    edge_id: str,
    kind: str,
    src: str,
    tgt: str,
    dim_id: str,
    order: int,
    ws: "Workspace",
) -> str:
    """Create an edge in %RECEDG. Returns edge_id.

    If edge_id already exists, updates fields in place (idempotent).
    """
    _, _, _, recedgadr, recedgfld, recedg = _get_system_cubes(ws)
    edge_adr_id = _item_id(recedgadr, edge_id)
    if edge_adr_id is None:
        recedgadr.add_item(edge_id)
        edge_adr_id = _item_id(recedgadr, edge_id)
    knd_id = _item_id(recedgfld, "KND")
    src_id = _item_id(recedgfld, "SRC")
    tgt_id = _item_id(recedgfld, "TGT")
    dim_fld_id = _item_id(recedgfld, "DIM")
    ord_id = _item_id(recedgfld, "ORD")
    for addr in [
        (edge_adr_id, knd_id, kind),
        (edge_adr_id, src_id, src),
        (edge_adr_id, tgt_id, tgt),
        (edge_adr_id, dim_fld_id, dim_id),
        (edge_adr_id, ord_id, order),
    ]:
        edge_adr, fld_id, value = addr
        if fld_id is None:
            continue
        recedg.set((edge_adr, fld_id), value)
        recedg.user_override_addrs.add((CHANNEL_TO_AT_ID["value"], edge_adr, fld_id))
    return edge_id


def _create_group_node_raw(dim_id: str, label: str, ws: "Workspace") -> str:
    """Create a GROUP node and return stable node_id."""
    from lib_openm.outline_graph_bridge import create_group_node as _legacy_create_group_node

    return _legacy_create_group_node(dim_id, label, ws)


def _ensure_item_ref_node_raw(dim_id: str, item_id: str, ws: "Workspace", label: str | None = None) -> str:
    """Ensure an ITEM_REF node exists and return node_id."""
    from lib_openm.outline_graph_bridge import ensure_item_node as _legacy_ensure_item_node

    return _legacy_ensure_item_node(dim_id, item_id, ws, label=label)

# TODO: move to constants somewhere in the config:
SPARSE_ORD_GAP = 1000  # gap between sparse order keys for insertion without renumbering


def _set_node_root_ord(node_id: str, order: int | None, ws: "Workspace") -> None:
    """Set or clear %RECNOD.ORD for a node."""
    recnodadr, recnodfld, recnod, *_ = _get_system_cubes(ws)
    node_adr_id = _item_id(recnodadr, node_id)
    if node_adr_id is None:
        return
    ord_id = _item_id(recnodfld, "ORD")
    if ord_id is None:
        return
    recnod.set((node_adr_id, ord_id), order)
    recnod.user_override_addrs.add((CHANNEL_TO_AT_ID["value"], node_adr_id, ord_id))


def _remove_node_raw(node_id: str, ws: "Workspace") -> None:
    """Physically remove a node from %RECNOD."""
    recnodadr, recnodfld, recnod, *_ = _get_system_cubes(ws)
    node_adr_id = _item_id(recnodadr, node_id)
    if node_adr_id is None:
        return

    # If this is an ITEM_REF node, remove it from the fast lookup index
    knd_id = _item_id(recnodfld, "KND")
    dim_fld_id = _item_id(recnodfld, "DIM")
    ref_id = _item_id(recnodfld, "REF")
    if knd_id and dim_fld_id and ref_id:
        node_knd = recnod.get((CHANNEL_TO_AT_ID["value"], node_adr_id, knd_id))
        if node_knd == "ITEM_REF":
            dim_val = recnod.get((CHANNEL_TO_AT_ID["value"], node_adr_id, dim_fld_id))
            ref_val = recnod.get((CHANNEL_TO_AT_ID["value"], node_adr_id, ref_id))
            if dim_val and ref_val and (dim_val, ref_val) in ws._item_ref_index:
                del ws._item_ref_index[(dim_val, ref_val)]

    # Clear every field
    for fld_item in recnodfld.items:
        if fld_item.name == "NUL":
            continue
        fld_id = fld_item.id
        addr = (node_adr_id, fld_id)
        full_addr = (CHANNEL_TO_AT_ID["value"],) + addr
        recnod.set(addr, None)
        recnod.user_override_addrs.discard(full_addr)
        recnod.user_override_addrs.discard(addr)
    # Remove the node from the address dimension so the row disappears
    recnodadr.items = [it for it in recnodadr.items if it.name != node_id]


# ── cache invalidation ──


def _invalidate_dim_outline(dim: "Dimension", ws: "Workspace") -> None:
    """Mark dim outline cache stale after mutation. Rebuilds lazily on next read."""
    dim.invalidate_outline_cache()


# ── decorator / context manager ──


def _dim_id_to_dim(dim_id: str, ws: "Workspace") -> "Dimension":
    for dim in ws.dimensions.values():
        if dim.id == dim_id:
            return dim
    raise ValueError(f"Dimension not found: {dim_id}")


@contextmanager
def graph_mutation(dim_id: str, ws: "Workspace"):
    """Context manager for compound graph mutations.

    Invalidates outline cache and optionally validates exactly once at exit.
    """
    dim = _dim_id_to_dim(dim_id, ws)
    try:
        yield
    finally:
        _invalidate_dim_outline(dim, ws)


def mutates_dimension_graph(fn: Callable):
    """Decorator for simple one-step primitives.

    Invalidates outline cache after the primitive runs.
    """

    def wrapper(dim_id: str, *args, **kwargs):
        ws = kwargs.pop("ws", None)
        if ws is None and args:
            # ws is the last positional arg for all decorated functions
            ws = args[-1]
            args = args[:-1]
        if ws is None:
            raise TypeError("ws argument is required")
        dim = _dim_id_to_dim(dim_id, ws)
        result = fn(dim_id, *args, ws=ws, **kwargs)
        _invalidate_dim_outline(dim, ws)
        return result

    return wrapper


# ── validation helpers ──


def _validate_label_not_blank(label: str, what: str) -> None:
    if not label or not str(label).strip():
        raise ValueError(f"{what} label must be non-empty")


def _validate_unique_group_label(dim_id: str, label: str, ws: "Workspace", exclude_node_id: str | None = None) -> None:
    _validate_label_not_blank(label, "Group")
    clean = str(label).strip().casefold()
    for node in _all_nodes_for_dim(dim_id, ws):
        if node["kind"] != "GROUP":
            continue
        if exclude_node_id and node["node_id"] == exclude_node_id:
            continue
        if str(node.get("label", "")).strip().casefold() == clean:
            raise ValueError(f"Duplicate group label in dimension: {label}")
    # Also prevent group labels matching item names
    dim = _dim_id_to_dim(dim_id, ws)
    for item in dim.items:
        if item.name.strip().casefold() == clean:
            raise ValueError(f"Duplicate group label in dimension: {label}")


def _validate_unique_item_label(
    dim: "Dimension", label: str, ws: "Workspace", exclude_item_id: str | None = None
) -> None:
    _validate_label_not_blank(label, "Item")
    clean = str(label).strip().casefold()
    for item in dim.items:
        if exclude_item_id and item.id == exclude_item_id:
            continue
        if item.name.strip().casefold() == clean:
            raise ValueError(f"Duplicate item label in dimension: {label}")
    # Also prevent item names matching group labels
    for node in _all_nodes_for_dim(dim.id, ws):
        if node["kind"] == "GROUP":
            if str(node.get("label", "")).strip().casefold() == clean:
                raise ValueError(f"Duplicate item label in dimension: {label}")


def _validate_edge_combination(edge_kind: str, src_meta: dict, tgt_meta: dict) -> None:
    if edge_kind == "MEMBER_OF":
        if tgt_meta["kind"] != "GROUP":
            raise ValueError("MEMBER_OF target must be a GROUP node")
    elif edge_kind == "AGGREG_OF":
        if src_meta["kind"] != "ITEM_REF":
            raise ValueError("AGGREG_OF source must be an ITEM_REF node")
        if tgt_meta["kind"] != "GROUP":
            raise ValueError("AGGREG_OF target must be a GROUP node")
    else:
        raise ValueError(f"Unknown edge kind: {edge_kind}")


def _detect_cycle(dim_id: str, child_node_id: str, parent_node_id: str, ws: "Workspace") -> bool:
    """Detect if adding MEMBER_OF(child->parent) would create a cycle."""
    # Traverse upward from parent; if we reach child, it's a cycle
    visited = set()
    current = parent_node_id
    while current:
        if current in visited:
            break
        visited.add(current)
        edge = _display_parent_edge(current, dim_id, ws)
        if edge and edge["kind"] == "MEMBER_OF":
            current = edge["tgt"]
        else:
            break
        if current == child_node_id:
            return True
    return False


# ── public primitives ──


def ensure_item_ref_node(dim_id: str, item_id: str, ws: "Workspace", label: str | None = None) -> str:
    """Find or create an ITEM_REF node for a dimension item.

    Returns node_id. Raises ValueError if multiple matching nodes exist.
    """
    recnodadr, recnodfld, recnod, *_ = _get_system_cubes(ws)
    knd_id = _item_id(recnodfld, "KND")
    dim_fld_id = _item_id(recnodfld, "DIM")
    ref_id = _item_id(recnodfld, "REF")

    matches: list[str] = []
    for adr_item in recnodadr.items:
        if adr_item.name == "NUL":
            continue
        if knd_id and recnod.get((CHANNEL_TO_AT_ID["value"], adr_item.id, knd_id)) != "ITEM_REF":
            continue
        if dim_fld_id and recnod.get((CHANNEL_TO_AT_ID["value"], adr_item.id, dim_fld_id)) != dim_id:
            continue
        if ref_id and recnod.get((CHANNEL_TO_AT_ID["value"], adr_item.id, ref_id)) == item_id:
            matches.append(adr_item.name)

    if len(matches) > 1:
        raise ValueError(f"Multiple ITEM_REF nodes found for ({dim_id}, {item_id})")
    if len(matches) == 1:
        return matches[0]

    return _ensure_item_ref_node_raw(dim_id, item_id, ws, label=label)


def _find_item_ref_node_id(dim_id: str, item_id: str, ws: "Workspace") -> str | None:
    """Find an existing ITEM_REF node_id for a dimension item.

    Returns None if not found (does NOT create).
    """
    # Fast path: in-memory index
    idx = ws._item_ref_index.get((dim_id, item_id))
    if idx is not None:
        return idx

    recnodadr, recnodfld, recnod, *_ = _get_system_cubes(ws)
    knd_id = _item_id(recnodfld, "KND")
    dim_fld_id = _item_id(recnodfld, "DIM")
    ref_id = _item_id(recnodfld, "REF")

    for adr_item in recnodadr.items:
        if adr_item.name == "NUL":
            continue
        if knd_id and recnod.get((CHANNEL_TO_AT_ID["value"], adr_item.id, knd_id)) != "ITEM_REF":
            continue
        if dim_fld_id and recnod.get((CHANNEL_TO_AT_ID["value"], adr_item.id, dim_fld_id)) != dim_id:
            continue
        if ref_id and recnod.get((CHANNEL_TO_AT_ID["value"], adr_item.id, ref_id)) == item_id:
            # Populate the index for future fast lookups
            ws._item_ref_index[(dim_id, item_id)] = adr_item.name
            return adr_item.name
    return None


@mutates_dimension_graph
def create_group_node(dim_id: str, label: str, ws: "Workspace") -> str:
    """Create a GROUP node with the given label.

    Raises ValueError if label is blank or duplicates another group label.
    """
    _validate_unique_group_label(dim_id, label, ws)
    return _create_group_node_raw(dim_id, label, ws)


@mutates_dimension_graph
def attach_edge(
    dim_id: str,
    child_node_id: str,
    parent_node_id: str,
    edge_kind: str,
    order: int,
    ws: "Workspace",
) -> str:
    """Attach a display parent edge from child to parent.

    - edge_kind must be MEMBER_OF or AGGREG_OF.
    - Validates source/target node kinds match the edge kind.
    - Rejects child that already has another display parent edge.
    - Idempotent: if the exact same edge exists, updates ORD and returns edge_id.
    - Raises ValueError on validation failure.
    """
    if edge_kind not in ("MEMBER_OF", "AGGREG_OF"):
        raise ValueError(f"Invalid edge kind: {edge_kind}")

    child_meta = _read_node_meta(child_node_id, ws)
    parent_meta = _read_node_meta(parent_node_id, ws)
    if child_meta is None:
        raise ValueError(f"Child node not found: {child_node_id}")
    if parent_meta is None:
        raise ValueError(f"Parent node not found: {parent_node_id}")

    _validate_edge_combination(edge_kind, child_meta, parent_meta)

    existing = _display_parent_edge(child_node_id, dim_id, ws)
    if existing:
        if existing["tgt"] == parent_node_id and existing["kind"] == edge_kind:
            # Idempotent: update ORD
            _delete_edge_raw(existing["edge_id"], ws)
            return _create_edge_raw(existing["edge_id"], edge_kind, child_node_id, parent_node_id, dim_id, order, ws)
        else:
            raise ValueError(
                f"Child {child_node_id} already has display parent edge to {existing['tgt']} ({existing['kind']})"
            )

    if edge_kind == "MEMBER_OF" and child_meta["kind"] == "GROUP":
        if _detect_cycle(dim_id, child_node_id, parent_node_id, ws):
            raise ValueError("Adding MEMBER_OF edge would create a cycle")

    edge_id = new_id("edg")
    return _create_edge_raw(edge_id, edge_kind, child_node_id, parent_node_id, dim_id, order, ws)


@mutates_dimension_graph
def detach_edge(
    dim_id: str,
    child_node_id: str,
    parent_node_id: str,
    edge_kind: str,
    ws: "Workspace",
) -> bool:
    """Detach a display parent edge.

    Idempotent: returns False if the edge does not exist, True if removed.
    After removal, the child node becomes unplaced/staging.
    """
    for edge in _all_edges_for_dim(dim_id, ws):
        if edge["src"] == child_node_id and edge["tgt"] == parent_node_id and edge["kind"] == edge_kind:
            _delete_edge_raw(edge["edge_id"], ws)
            return True
    return False


@mutates_dimension_graph
def move_edge(
    dim_id: str,
    child_node_id: str,
    old_parent_node_id: str,
    new_parent_node_id: str,
    edge_kind: str,
    new_order: int,
    ws: "Workspace",
) -> str:
    """Move a child from one parent to another.

    Atomic: validates the new edge first. If validation fails, the old edge is left untouched.
    Returns new edge_id on success. Raises on validation failure.
    """
    # Verify old edge exists
    old_edge = None
    for edge in _all_edges_for_dim(dim_id, ws):
        if edge["src"] == child_node_id and edge["tgt"] == old_parent_node_id and edge["kind"] == edge_kind:
            old_edge = edge
            break
    if old_edge is None:
        raise ValueError(f"Old edge not found: {child_node_id} -> {old_parent_node_id} ({edge_kind})")

    child_meta = _read_node_meta(child_node_id, ws)
    new_parent_meta = _read_node_meta(new_parent_node_id, ws)
    if child_meta is None:
        raise ValueError(f"Child node not found: {child_node_id}")
    if new_parent_meta is None:
        raise ValueError(f"New parent node not found: {new_parent_node_id}")

    _validate_edge_combination(edge_kind, child_meta, new_parent_meta)

    if edge_kind == "MEMBER_OF" and child_meta["kind"] == "GROUP":
        if _detect_cycle(dim_id, child_node_id, new_parent_node_id, ws):
            raise ValueError("Moving edge would create a cycle")

    with graph_mutation(dim_id, ws):
        _delete_edge_raw(old_edge["edge_id"], ws)
        edge_id = new_id("edg")
        _create_edge_raw(edge_id, edge_kind, child_node_id, new_parent_node_id, dim_id, new_order, ws)
        _renumber_children(dim_id, new_parent_node_id, edge_kind, ws)
    return edge_id


def rename_group_node(group_node_id: str, new_label: str, ws: "Workspace") -> None:
    """Update the label of a GROUP node.

    Raises ValueError if blank or duplicates another group label in the same DIM.
    """
    meta = _read_node_meta(group_node_id, ws)
    if meta is None:
        raise ValueError(f"Node not found: {group_node_id}")
    if meta["kind"] != "GROUP":
        raise ValueError(f"Node {group_node_id} is not a GROUP")
    dim_id = meta["dim_id"]
    _validate_unique_group_label(dim_id, new_label, ws, exclude_node_id=group_node_id)

    recnodadr, recnodfld, recnod, *_ = _get_system_cubes(ws)
    node_adr_id = _item_id(recnodadr, group_node_id)
    lbl_id = _item_id(recnodfld, "LBL")
    if node_adr_id and lbl_id:
        recnod.set((node_adr_id, lbl_id), new_label)
        recnod.user_override_addrs.add((CHANNEL_TO_AT_ID["value"], node_adr_id, lbl_id))

    dim = _dim_id_to_dim(dim_id, ws)
    _invalidate_dim_outline(dim, ws)


@mutates_dimension_graph
def rename_dimension_item(dim_id: str, item_id: str, new_label: str, ws: "Workspace") -> None:
    """Update the name of a dimension item.

    Also updates the label of the corresponding ITEM_REF node in %RECNOD.
    Raises ValueError if blank or duplicates another item label in the same DIM.
    """
    dim = _dim_id_to_dim(dim_id, ws)
    _validate_unique_item_label(dim, new_label, ws, exclude_item_id=item_id)

    # Replace frozen DimensionItem
    from lib_openm.model import DimensionItem

    for i, item in enumerate(dim.items):
        if item.id == item_id:
            dim.items[i] = DimensionItem(id=item_id, name=new_label)
            break

    # Update any matching ITEM_REF node label
    recnodadr, recnodfld, recnod, *_ = _get_system_cubes(ws)
    ref_id = _item_id(recnodfld, "REF")
    lbl_id = _item_id(recnodfld, "LBL")
    dim_fld_id = _item_id(recnodfld, "DIM")
    knd_id = _item_id(recnodfld, "KND")
    for adr_item in recnodadr.items:
        if adr_item.name == "NUL":
            continue
        if knd_id and recnod.get((CHANNEL_TO_AT_ID["value"], adr_item.id, knd_id)) != "ITEM_REF":
            continue
        if dim_fld_id and recnod.get((CHANNEL_TO_AT_ID["value"], adr_item.id, dim_fld_id)) != dim_id:
            continue
        if ref_id and recnod.get((CHANNEL_TO_AT_ID["value"], adr_item.id, ref_id)) == item_id:
            if lbl_id:
                recnod.set((adr_item.id, lbl_id), new_label)
                recnod.user_override_addrs.add((CHANNEL_TO_AT_ID["value"], adr_item.id, lbl_id))
            break


@mutates_dimension_graph
def reorder_group_children(
    dim_id: str,
    parent_node_id: str,
    edge_kind: str,
    ordered_node_ids: list[str],
    ws: "Workspace",
) -> None:
    """Rewrite ORD values densely from 0 for children of a parent.

    ordered_node_ids must exactly match the current set of child node_ids.
    Raises ValueError on mismatch.
    """
    current_children = [
        edge["src"]
        for edge in _all_edges_for_dim(dim_id, ws)
        if edge["tgt"] == parent_node_id and edge["kind"] == edge_kind
    ]
    current_set = set(current_children)
    ordered_set = set(ordered_node_ids)
    if current_set != ordered_set:
        raise ValueError("ordered_node_ids does not match current children")

    _, _, _, recedgadr, recedgfld, recedg = _get_system_cubes(ws)
    knd_id = _item_id(recedgfld, "KND")
    src_id = _item_id(recedgfld, "SRC")
    tgt_id = _item_id(recedgfld, "TGT")
    dim_fld_id = _item_id(recedgfld, "DIM")
    ord_id = _item_id(recedgfld, "ORD")

    for new_ord, child_id in enumerate(ordered_node_ids):
        for adr_item in recedgadr.items:
            if adr_item.name == "NUL":
                continue
            if dim_fld_id and recedg.get((CHANNEL_TO_AT_ID["value"], adr_item.id, dim_fld_id)) != dim_id:
                continue
            if knd_id and recedg.get((CHANNEL_TO_AT_ID["value"], adr_item.id, knd_id)) != edge_kind:
                continue
            if src_id and recedg.get((CHANNEL_TO_AT_ID["value"], adr_item.id, src_id)) != child_id:
                continue
            if tgt_id and recedg.get((CHANNEL_TO_AT_ID["value"], adr_item.id, tgt_id)) != parent_node_id:
                continue
            if ord_id:
                recedg.set((adr_item.id, ord_id), new_ord)
                recedg.user_override_addrs.add((CHANNEL_TO_AT_ID["value"], adr_item.id, ord_id))
            break


@mutates_dimension_graph
def move_node_to_root(dim_id: str, node_id: str, order: int, ws: "Workspace") -> None:
    """Remove any display parent edge and make a node root-level.

    Deletes any existing MEMBER_OF or AGGREG_OF edge for the node,
    sets root ORD, and renumbers all root-level nodes densely from 0.
    """
    # Delete any display parent edge
    for edge in _all_edges_for_dim(dim_id, ws):
        if edge["src"] == node_id and edge["kind"] in ("MEMBER_OF", "AGGREG_OF"):
            _delete_edge_raw(edge["edge_id"], ws)

    # Set root ORD and renumber densely
    root_nodes = _root_level_nodes(dim_id, ws)
    # Remove node from list if present, then insert at requested position
    root_ids = [n["node_id"] for n in root_nodes if n["node_id"] != node_id]
    order = max(0, min(order, len(root_ids)))
    root_ids.insert(order, node_id)
    for i, rid in enumerate(root_ids):
        _set_node_root_ord(rid, i, ws)


@mutates_dimension_graph
def set_root_order(dim_id: str, node_id: str, order: int, ws: "Workspace") -> None:
    """Set a root-level node's ORD and renumber all root-level nodes densely."""
    root_nodes = _root_level_nodes(dim_id, ws)
    root_ids = [n["node_id"] for n in root_nodes]
    if node_id not in root_ids:
        raise ValueError(f"Node {node_id} is not root-level")
    root_ids.remove(node_id)
    order = max(0, min(order, len(root_ids)))
    root_ids.insert(order, node_id)
    for i, rid in enumerate(root_ids):
        _set_node_root_ord(rid, i, ws)


@mutates_dimension_graph
def move_root_to_group(dim_id: str, node_id: str, parent_node_id: str, edge_kind: str, order: int, ws: "Workspace") -> str:
    """Move a root-level node into a group.

    Clears root ORD, attaches a display edge, and renumbers remaining root nodes densely.
    Rejects if the node already has a display parent (use move_edge instead).
    """
    all_nodes = _all_nodes_for_dim(dim_id, ws)
    node_map = {n["node_id"]: n for n in all_nodes}

    if node_id not in node_map:
        raise ValueError(f"Node not found: {node_id}")
    parent = node_map.get(parent_node_id)
    if parent is None:
        raise ValueError(f"Parent node not found: {parent_node_id}")
    if parent.get("kind") != "GROUP":
        raise ValueError(f"Parent node must be a GROUP: {parent_node_id}")
    if edge_kind not in ("MEMBER_OF", "AGGREG_OF"):
        raise ValueError(f"Invalid edge kind: {edge_kind}")

    # Node must not already have a display parent
    for edge in _all_edges_for_dim(dim_id, ws):
        if edge["src"] == node_id and edge["kind"] in ("MEMBER_OF", "AGGREG_OF"):
            raise ValueError(f"Node {node_id} already has a display parent; use move_edge instead")

    # Clear root ORD, create edge, renumber roots and children
    _set_node_root_ord(node_id, None, ws)
    edge_id = _create_edge_raw(
        new_id("edg"), edge_kind, node_id, parent_node_id, dim_id, order, ws
    )
    _renumber_children(dim_id, parent_node_id, edge_kind, ws)
    _renumber_root(dim_id, ws)
    return edge_id


@mutates_dimension_graph
def ungroup_group(dim_id: str, group_node_id: str, ws: "Workspace") -> None:
    """Dissolve a group: promote children to parent or root.

    Steps:
    1. Find the group's display parent edge, if any.
    2. Collect MEMBER_OF children in edge.ORD order.
    3. If the group had a parent: re-target each child's edge to that parent.
    4. If the group was root-level: detach each child (make root-level).
    5. Delete AGGREG_OF edges targeting the group.
    6. Aggregate ITEM_REF nodes become unplaced/staging (not deleted).
    7. Delete the group node.
    8. Renumber affected siblings.
    """
    meta = _read_node_meta(group_node_id, ws)
    if meta is None or meta["kind"] != "GROUP":
        raise ValueError(f"Not a GROUP node: {group_node_id}")

    parent_edge = _display_parent_edge(group_node_id, dim_id, ws)
    parent_id = parent_edge["tgt"] if parent_edge else None
    parent_ord = parent_edge["ord"] if parent_edge else None

    # Collect MEMBER_OF children ordered by ORD
    children = sorted(
        [
            edge
            for edge in _all_edges_for_dim(dim_id, ws)
            if edge["tgt"] == group_node_id and edge["kind"] == "MEMBER_OF"
        ],
        key=lambda e: e["ord"] if isinstance(e["ord"], int) else 0,
    )

    # Collect AGGREG_OF edges targeting the group
    aggreg_edges = [
        edge
        for edge in _all_edges_for_dim(dim_id, ws)
        if edge["tgt"] == group_node_id and edge["kind"] == "AGGREG_OF"
    ]

    with graph_mutation(dim_id, ws):
        # Re-target or detach children
        for child in children:
            _delete_edge_raw(child["edge_id"], ws)
            if parent_id is not None:
                edge_id = new_id("edg")
                _create_edge_raw(edge_id, "MEMBER_OF", child["src"], parent_id, dim_id, 0, ws)
            else:
                _set_node_root_ord(child["src"], 0, ws)

        # Delete aggregate edges
        for edge in aggreg_edges:
            _delete_edge_raw(edge["edge_id"], ws)

        # Delete group node
        _remove_node_raw(group_node_id, ws)
        if parent_id is not None:
            # Renumber siblings under parent
            _renumber_children(dim_id, parent_id, "MEMBER_OF", ws)
        else:
            # Renumber root nodes
            _renumber_root(dim_id, ws)

        # After renumbering, assign root_ord to orphaned aggregate items
        # so they maintain a deterministic position at the end of root level
        aggreg_src_ids = {edge["src"] for edge in aggreg_edges}

        # Find aggregates that still have display edges (attached to other groups)
        remaining_srcs = {
            e["src"] for e in _all_edges_for_dim(dim_id, ws)
            if e["kind"] in ("MEMBER_OF", "AGGREG_OF") and e["src"] in aggreg_src_ids
        }
        orphan_aggregates = aggreg_src_ids - remaining_srcs

        if orphan_aggregates:
            root_nodes = _root_level_nodes(dim_id, ws)
            meaningful_ords = [
                n["root_ord"] for n in root_nodes
                if n["node_id"] not in orphan_aggregates
                and isinstance(n["root_ord"], (int, float))
            ]
            next_ord = int(max(meaningful_ords)) + 1 if meaningful_ords else 0

            for agg_id in sorted(orphan_aggregates):
                _set_node_root_ord(agg_id, next_ord, ws)
                next_ord += 1

        # Clean up ordinary item nodes that are now orphaned, but preserve aggregates
        _cleanup_orphan_item_ref_nodes(dim_id, ws, exclude=aggreg_src_ids)


@mutates_dimension_graph
def delete_group_structure(dim_id: str, group_node_id: str, ws: "Workspace") -> None:
    """Delete a group and nested groups, preserving ordinary items.

    Steps:
    1. Find the group's parent display edge, if any.
    2. Traverse MEMBER_OF hierarchy, collecting GROUP nodes and ordinary ITEM_REF nodes.
    3. Delete all GROUP nodes in the hierarchy.
    4. Promote ordinary ITEM_REF nodes to the deleted group's parent or root.
    5. Delete MEMBER_OF edges involving deleted GROUP nodes.
    6. Delete AGGREG_OF edges targeting deleted groups.
    7. Aggregate ITEM_REF nodes become unplaced/staging (not deleted).
    8. Renumber affected root or sibling ORD densely.
    """
    meta = _read_node_meta(group_node_id, ws)
    if meta is None or meta["kind"] != "GROUP":
        raise ValueError(f"Not a GROUP node: {group_node_id}")

    parent_edge = _display_parent_edge(group_node_id, dim_id, ws)
    parent_id = parent_edge["tgt"] if parent_edge else None

    # Traverse MEMBER_OF hierarchy
    group_ids_to_delete = {group_node_id}
    ordinary_items_to_promote: list[tuple[str, int]] = []  # (node_id, order)

    def _traverse(node_id: str, depth: int = 0) -> None:
        child_edges = sorted(
            [
                edge
                for edge in _all_edges_for_dim(dim_id, ws)
                if edge["tgt"] == node_id and edge["kind"] == "MEMBER_OF"
            ],
            key=lambda e: e["ord"] if isinstance(e["ord"], int) else 0,
        )
        for edge in child_edges:
            child_meta = _read_node_meta(edge["src"], ws)
            if child_meta is None:
                continue
            if child_meta["kind"] == "GROUP":
                group_ids_to_delete.add(edge["src"])
                _traverse(edge["src"], depth + 1)
            elif child_meta["kind"] == "ITEM_REF":
                ordinary_items_to_promote.append((edge["src"], edge["ord"] if isinstance(edge["ord"], int) else 0))

    _traverse(group_node_id)

    # Collect aggregate items attached to the deleted group(s)
    aggreg_src_ids = {
        edge["src"]
        for edge in _all_edges_for_dim(dim_id, ws)
        if edge["tgt"] in group_ids_to_delete and edge["kind"] == "AGGREG_OF"
    }

    # Collect all edges involving deleted groups
    edges_to_delete = [
        edge
        for edge in _all_edges_for_dim(dim_id, ws)
        if edge["src"] in group_ids_to_delete or edge["tgt"] in group_ids_to_delete
    ]

    with graph_mutation(dim_id, ws):
        # Delete edges
        for edge in edges_to_delete:
            _delete_edge_raw(edge["edge_id"], ws)

        # Promote ordinary items
        for item_id, _ord in ordinary_items_to_promote:
            if parent_id is not None:
                edge_id = new_id("edg")
                _create_edge_raw(edge_id, "MEMBER_OF", item_id, parent_id, dim_id, 0, ws)
            else:
                _set_node_root_ord(item_id, 0, ws)

        # Delete group nodes
        for gid in group_ids_to_delete:
            _remove_node_raw(gid, ws)

        # Renumber
        if parent_id is not None:
            _renumber_children(dim_id, parent_id, "MEMBER_OF", ws)
        else:
            _renumber_root(dim_id, ws)

        # After renumbering, assign root_ord to orphaned aggregate items
        # so they maintain a deterministic position at the end of root level
        remaining_srcs = {
            e["src"] for e in _all_edges_for_dim(dim_id, ws)
            if e["kind"] in ("MEMBER_OF", "AGGREG_OF") and e["src"] in aggreg_src_ids
        }
        orphan_aggregates = aggreg_src_ids - remaining_srcs

        if orphan_aggregates:
            root_nodes = _root_level_nodes(dim_id, ws)
            meaningful_ords = [
                n["root_ord"] for n in root_nodes
                if n["node_id"] not in orphan_aggregates
                and isinstance(n["root_ord"], (int, float))
            ]
            next_ord = int(max(meaningful_ords)) + 1 if meaningful_ords else 0

            for agg_id in sorted(orphan_aggregates):
                _set_node_root_ord(agg_id, next_ord, ws)
                next_ord += 1

        # Clean up ordinary item nodes that are now orphaned, but preserve aggregates
        _cleanup_orphan_item_ref_nodes(dim_id, ws, exclude=aggreg_src_ids)


def _cleanup_orphan_item_ref_nodes(
    dim_id: str, ws: "Workspace", exclude: set[str] | None = None
) -> None:
    """Remove ITEM_REF nodes that have no root_ord and no display edges.

    Aggregate items that are explicitly excluded (e.g. after ungrouping)
    are preserved as unplaced/staging nodes even when orphaned.
    """
    recnodadr, recnodfld, recnod, recedgadr, recedgfld, recedg = _get_system_cubes(ws)
    if any(x is None for x in (recnodadr, recnodfld, recnod, recedgadr, recedgfld, recedg)):
        return

    knd_id = _item_id(recnodfld, "KND")
    dim_fld_id = _item_id(recnodfld, "DIM")
    ord_id = _item_id(recnodfld, "ORD")
    edge_dim_id = _item_id(recedgfld, "DIM")
    edge_src_id = _item_id(recedgfld, "SRC")
    edge_tgt_id = _item_id(recedgfld, "TGT")

    # Collect all nodes connected to any display edge for this dimension
    connected: set[str] = set()
    for edge_adr in recedgadr.items:
        if edge_adr.name == "NUL":
            continue
        if recedg.get((CHANNEL_TO_AT_ID["value"], edge_adr.id, edge_dim_id)) != dim_id:
            continue
        src = recedg.get((CHANNEL_TO_AT_ID["value"], edge_adr.id, edge_src_id))
        tgt = recedg.get((CHANNEL_TO_AT_ID["value"], edge_adr.id, edge_tgt_id))
        if isinstance(src, str):
            connected.add(src)
        if isinstance(tgt, str):
            connected.add(tgt)

    exclude_set = exclude or set()
    to_remove: list[str] = []
    for adr_item in recnodadr.items:
        if adr_item.name == "NUL":
            continue
        if adr_item.name in exclude_set:
            continue
        if recnod.get((CHANNEL_TO_AT_ID["value"], adr_item.id, dim_fld_id)) != dim_id:
            continue
        if recnod.get((CHANNEL_TO_AT_ID["value"], adr_item.id, knd_id)) != "ITEM_REF":
            continue
        if adr_item.name in connected:
            continue
        root_ord = recnod.get((CHANNEL_TO_AT_ID["value"], adr_item.id, ord_id)) if ord_id else None
        if root_ord is None:
            to_remove.append(adr_item.name)

    for node_id in to_remove:
        _remove_node_raw(node_id, ws)


# ── internal renumbering helpers ──


def _root_level_nodes(dim_id: str, ws: "Workspace") -> list[dict]:
    """Return all root-level nodes for a dimension, sorted by ORD."""
    all_nodes = _all_nodes_for_dim(dim_id, ws)
    root_ids = {n["node_id"] for n in all_nodes}
    for edge in _all_edges_for_dim(dim_id, ws):
        if edge["kind"] in ("MEMBER_OF", "AGGREG_OF") and edge["src"] in root_ids:
            root_ids.discard(edge["src"])
    root_nodes = [n for n in all_nodes if n["node_id"] in root_ids]
    root_nodes.sort(key=lambda n: n["root_ord"] if isinstance(n["root_ord"], int) else 0)
    return root_nodes


def _renumber_root(dim_id: str, ws: "Workspace") -> None:
    """Assign sparse order keys to root-level nodes.

    Uses large gaps (SPARSE_ORD_GAP) so insertions between siblings
    do not require rewriting all neighbors.
    """
    root_nodes = _root_level_nodes(dim_id, ws)
    for i, node in enumerate(root_nodes):
        _set_node_root_ord(node["node_id"], i * SPARSE_ORD_GAP, ws)


def _renumber_children(dim_id: str, parent_node_id: str, edge_kind: str, ws: "Workspace") -> None:
    """Assign sparse order keys to child edges.

    Uses large gaps (SPARSE_ORD_GAP) so insertions between siblings
    do not require rewriting all neighbors.
    """
    children = sorted(
        [
            edge
            for edge in _all_edges_for_dim(dim_id, ws)
            if edge["tgt"] == parent_node_id and edge["kind"] == edge_kind
        ],
        key=lambda e: e["ord"] if isinstance(e["ord"], int) else 0,
    )
    _, _, _, recedgadr, recedgfld, recedg = _get_system_cubes(ws)
    ord_id = _item_id(recedgfld, "ORD")
    for i, edge in enumerate(children):
        edge_adr_id = _item_id(recedgadr, edge["edge_id"])
        if edge_adr_id and ord_id:
            recedg.set((edge_adr_id, ord_id), i * SPARSE_ORD_GAP)
            recedg.user_override_addrs.add((CHANNEL_TO_AT_ID["value"], edge_adr_id, ord_id))


# ── validator ──


def validate_dimension_graph(dim_id: str, ws: "Workspace") -> list[GraphIssue]:
    """Check all graph invariants and return a list of GraphIssue objects."""
    issues: list[GraphIssue] = []
    all_nodes = _all_nodes_for_dim(dim_id, ws)
    all_edges = _all_edges_for_dim(dim_id, ws)

    node_map = {n["node_id"]: n for n in all_nodes}

    # Build parent edges per node
    display_parents: dict[str, list[dict]] = {}
    for edge in all_edges:
        if edge["kind"] in ("MEMBER_OF", "AGGREG_OF"):
            display_parents.setdefault(edge["src"], []).append(edge)

    # Check each edge
    for edge in all_edges:
        edge_id = edge["edge_id"]
        src = edge["src"]
        tgt = edge["tgt"]
        kind = edge["kind"]
        src_meta = node_map.get(src)
        tgt_meta = node_map.get(tgt)

        if src_meta is None:
            issues.append(GraphIssue("MISSING_SRC_NODE", f"Edge {edge_id} references missing source {src}", "error", edge_id=edge_id))
        if tgt_meta is None:
            issues.append(GraphIssue("MISSING_TGT_NODE", f"Edge {edge_id} references missing target {tgt}", "error", edge_id=edge_id))
        if src_meta and tgt_meta:
            if kind == "MEMBER_OF":
                if tgt_meta["kind"] != "GROUP":
                    issues.append(GraphIssue("MEMBER_OF_TGT_NOT_GROUP", f"MEMBER_OF edge {edge_id} target is not GROUP", "error", edge_id=edge_id))
            elif kind == "AGGREG_OF":
                if src_meta["kind"] != "ITEM_REF":
                    issues.append(GraphIssue("AGGREG_OF_SRC_NOT_ITEM", f"AGGREG_OF edge {edge_id} source is not ITEM_REF", "error", edge_id=edge_id))
                if tgt_meta["kind"] != "GROUP":
                    issues.append(GraphIssue("AGGREG_OF_TGT_NOT_GROUP", f"AGGREG_OF edge {edge_id} target is not GROUP", "error", edge_id=edge_id))

    # Check zero-or-one display parent per node
    for node_id, edges in display_parents.items():
        if len(edges) > 1:
            issues.append(GraphIssue("MULTIPLE_DISPLAY_PARENTS", f"Node {node_id} has {len(edges)} display parent edges", "error", node_id=node_id))

    # Check ORD uniqueness among siblings
    sibling_groups: dict[tuple[str | None, str], list[int]] = {}
    for edge in all_edges:
        if edge["kind"] not in ("MEMBER_OF", "AGGREG_OF"):
            continue
        key = (edge["tgt"], edge["kind"])
        sibling_groups.setdefault(key, []).append(edge["ord"] if isinstance(edge["ord"], int) else 0)
    for (parent, kind), ords in sibling_groups.items():
        seen = set()
        for o in ords:
            if o in seen:
                issues.append(GraphIssue("ORD_COLLISION", f"Duplicate ORD {o} under parent {parent} kind={kind}", "error"))
            seen.add(o)

    # Check root ORD uniqueness
    root_nodes = _root_level_nodes(dim_id, ws)
    seen_root_ords = set()
    for node in root_nodes:
        ord_val = node["root_ord"] if isinstance(node["root_ord"], int) else 0
        if ord_val in seen_root_ords:
            issues.append(GraphIssue("ROOT_ORD_COLLISION", f"Duplicate root ORD {ord_val} for node {node['node_id']}", "error", node_id=node["node_id"]))
        seen_root_ords.add(ord_val)

    # Check at most one ITEM_REF per (DIM, REF)
    item_ref_nodes = [n for n in all_nodes if n["kind"] == "ITEM_REF"]
    seen_refs: dict[str, str] = {}
    for n in item_ref_nodes:
        ref = n.get("ref")
        if ref:
            if ref in seen_refs:
                issues.append(GraphIssue("DUPLICATE_ITEM_REF", f"Multiple ITEM_REF nodes for ref {ref}", "error", node_id=n["node_id"]))
            else:
                seen_refs[ref] = n["node_id"]

    # Check MEMBER_OF acyclicity
    for node in all_nodes:
        if node["kind"] == "GROUP":
            visited = set()
            current = node["node_id"]
            while current:
                if current in visited:
                    issues.append(GraphIssue("MEMBER_OF_CYCLE", f"Cycle detected involving node {current}", "error", node_id=current))
                    break
                visited.add(current)
                edge = _display_parent_edge(current, dim_id, ws)
                if edge and edge["kind"] == "MEMBER_OF":
                    current = edge["tgt"]
                else:
                    break

    return issues
