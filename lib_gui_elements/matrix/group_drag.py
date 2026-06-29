"""Group header drag helpers for the matrix grid.

Core logic for dragging a GROUP node and its attached subtree.
Descendants are highlighted but are not individually moved.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lib_contracts.types import OutlineNode

if TYPE_CHECKING:
    from PySide6 import QtCore


def node_at_path(nodes: list[OutlineNode], path: tuple[int, ...]) -> OutlineNode | None:
    """Return the OutlineNode at *path* in the outline tree, or None."""
    arr = nodes
    cur: OutlineNode | None = None
    for i in path:
        if not (0 <= i < len(arr)):
            return None
        cur = arr[i]
        arr = list(cur.children)
    return cur


def get_descendant_sets(
    nodes: list[OutlineNode], group_path: tuple[int, ...]
) -> tuple[set[str], set[str], set[str]]:
    """Return (subtree_set, descendant_set, leaf_item_ref_set) for the group at *group_path*.

    - subtree_set: group_node_id + all descendant node_ids
    - descendant_set: descendants only (excludes the anchor group itself)
    - leaf_item_ref_set: ITEM_REF node_ids only
    """
    group_node = node_at_path(nodes, group_path)
    if group_node is None:
        return set(), set(), set()

    subtree_set: set[str] = set()
    descendant_set: set[str] = set()
    leaf_item_ref_set: set[str] = set()

    def _walk(node: OutlineNode, is_root: bool) -> None:
        nid = getattr(node, "node_id", None)
        if nid:
            subtree_set.add(nid)
            if not is_root:
                descendant_set.add(nid)
            if node.item_id is not None:
                leaf_item_ref_set.add(nid)
        for child in node.children:
            _walk(child, is_root=False)

    _walk(group_node, is_root=True)
    return subtree_set, descendant_set, leaf_item_ref_set


def count_leaf_descendants(nodes: list[OutlineNode], group_path: tuple[int, ...]) -> int:
    """Count ITEM_REF leaf descendants of the group at *group_path*."""
    _, _, leaf_set = get_descendant_sets(nodes, group_path)
    return len(leaf_set)


def classify_drop_zone(relative_y: float, row_height: float, is_group_row: bool) -> str:
    """Classify drop zone from cursor position within a row.

    Returns ``'before'``, ``'into'``, or ``'after'``.
    """
    frac = relative_y / max(1.0, row_height)
    if is_group_row:
        if frac < 0.25:
            return "before"
        elif frac > 0.75:
            return "after"
        return "into"
    else:
        return "before" if frac < 0.5 else "after"


def resolve_group_node_id(
    nodes: list[OutlineNode], group_path: tuple[int, ...]
) -> str | None:
    """Return the graph node_id for the group at *group_path*, or None."""
    group_node = node_at_path(nodes, group_path)
    if group_node is None:
        return None
    return getattr(group_node, "node_id", None) or None


def _leaf_node_id_for_item_id(
    nodes: list[OutlineNode], item_id: str
) -> str | None:
    """Find the ITEM_REF node_id for *item_id* in the outline tree."""

    def _walk(ns: list[OutlineNode]) -> str | None:
        for n in ns:
            if n.item_id == item_id:
                return getattr(n, "node_id", None)
            if n.children:
                result = _walk(list(n.children))
                if result:
                    return result
        return None

    return _walk(nodes)


def _parent_path_of(path: tuple[int, ...]) -> tuple[int, ...] | None:
    """Return the parent path, or None if *path* is a root-level node."""
    if len(path) <= 1:
        return None
    return path[:-1]


def _find_node_by_id(nodes: list[OutlineNode], node_id: str) -> OutlineNode | None:
    """DFS: return the first OutlineNode whose runtime node_id matches, or None."""
    for n in nodes:
        if getattr(n, "node_id", None) == node_id:
            return n
        if n.children:
            result = _find_node_by_id(list(n.children), node_id)
            if result is not None:
                return result
    return None


def _parent_of_node(nodes: list[OutlineNode], node_id: str) -> OutlineNode | None:
    """Return the node whose children list contains the target node_id, or None."""
    for n in nodes:
        for child in n.children:
            if getattr(child, "node_id", None) == node_id:
                return n
        if n.children:
            result = _parent_of_node(list(n.children), node_id)
            if result is not None:
                return result
    return None


def _ordered_siblings(nodes: list[OutlineNode], node_id: str) -> list[OutlineNode] | None:
    """Return the ordered sibling list (including self) under the same parent.

    Returns the top-level list for root-level nodes.  Returns None if the
    node cannot be found anywhere in the tree.
    """
    # Check root-level first
    for n in nodes:
        if getattr(n, "node_id", None) == node_id:
            return list(nodes)
    # Search for parent containing the node
    for n in nodes:
        for child in n.children:
            if getattr(child, "node_id", None) == node_id:
                return list(n.children)
        if n.children:
            result = _ordered_siblings(list(n.children), node_id)
            if result is not None:
                return result
    return None


def is_noop_move(
    *,
    group_node_id: str,
    new_parent_node_id: str | None,
    anchor_node_id: str | None,
    position: str,
    outline_nodes: list[OutlineNode],
) -> bool:
    """Return True if the move would not change the group's position."""
    # Validate target node exists
    target_node = _find_node_by_id(outline_nodes, group_node_id)
    if target_node is None:
        return False

    current_parent_node = _parent_of_node(outline_nodes, group_node_id)
    current_parent_id = getattr(current_parent_node, "node_id", None) if current_parent_node else None

    if current_parent_id != new_parent_node_id:
        return False

    # Same parent – check order.
    siblings = _ordered_siblings(outline_nodes, group_node_id)
    if siblings is None:
        return False

    src_ids = [
        getattr(n, "node_id", None) for n in siblings
    ]

    if position in ("first", "last"):
        if not src_ids:
            return True
        if position == "first" and src_ids[0] == group_node_id:
            return True
        if position == "last" and src_ids[-1] == group_node_id:
            return True
        return False

    if position in ("before", "after") and anchor_node_id is not None:
        try:
            group_idx = src_ids.index(group_node_id)
            anchor_idx = src_ids.index(anchor_node_id)
        except ValueError:
            return False
        if position == "before" and group_idx == anchor_idx - 1:
            return True
        if position == "after" and group_idx == anchor_idx + 1:
            return True
        return False

    return False
