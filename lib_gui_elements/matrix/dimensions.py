"""Dimension and outline axis helpers for the matrix grid."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PySide6 import QtCore, QtGui, QtWidgets
    from lib_contracts.types import OutlineNode


class DimensionHelper:
    """Helper methods for dimension and outline axis operations."""

    def __init__(self, grid: "MatrixGrid") -> None:
        self._grid = grid

    def axis_dim_id(self, axis: str) -> str | None:
        """Get dimension ID for the given axis."""
        view = self._grid._workspace_read_model.get_view(self._grid._view_id)
        dim_ids = list(
            view.get(f"{axis}_dim_ids", []) or [] if view else []
        )
        if not dim_ids:
            return None
        # For stacked dimensions, return the last dimension ID
        # as it represents the leaf level
        return dim_ids[-1] if dim_ids else None

    def normalized_outline(
        self, did: str, outline: list["OutlineNode"]
    ) -> list["OutlineNode"]:
        """Normalize outline structure - ensure all nodes are OutlineNode instances."""
        from lib_contracts.types import OutlineNode

        def _walk(nodes: list["OutlineNode"]) -> list["OutlineNode"]:
            result: list["OutlineNode"] = []
            for node in nodes:
                if isinstance(node, dict):
                    children = _walk(list(node.get("children", [])))
                    result.append(
                        OutlineNode(
                            label=node.get("label", ""),
                            item_id=node.get("item_id"),
                            children=children,
                            node_id=node.get("node_id"),
                            is_aggregate=node.get("is_aggregate", False),
                        )
                    )
                elif isinstance(node, OutlineNode):
                    if node.children:
                        new_children = _walk(list(node.children))
                        if new_children != list(node.children):
                            result.append(
                                OutlineNode(
                                    label=node.label,
                                    item_id=node.item_id,
                                    children=new_children,
                                    node_id=node.node_id,
                                    is_aggregate=node.is_aggregate,
                                )
                            )
                        else:
                            result.append(node)
                    else:
                        result.append(node)
                else:
                    # Unknown type, skip
                    pass
            return result

        return _walk(outline)

    def axis_outline(self, axis: str) -> list["OutlineNode"]:
        """Get the outline for a given axis."""
        did = self.axis_dim_id(axis)
        if did is None:
            return []
        dim = self._grid._workspace_read_model.get_dimension(did)
        outline = dim.get("outline", []) if dim else []
        fixed = self.normalized_outline(did, outline)
        return fixed

    def ensure_outline_axis(self, axis: str) -> bool:
        """Ensure outline exists for the given axis."""
        did = self.axis_dim_id(axis)
        if did is None:
            return False
        dim = self._grid._workspace_read_model.get_dimension(did)
        cur = dim.get("outline", []) if dim else []
        if cur:
            return True
        self._grid.execute_command("set_dimension_outline", dim_id=did, outline=None)
        return True

    def outline_root(self, axis: str) -> list["OutlineNode"]:
        """Get root outline for axis (same as axis_outline but with normalization)."""
        did = self.axis_dim_id(axis)
        if did is None:
            return []
        dim = self._grid._workspace_read_model.get_dimension(did)
        outline = dim.get("outline", []) if dim else []
        fixed = self.normalized_outline(did, outline)
        return fixed

    def set_outline_root(self, axis: str, root: list["OutlineNode"]) -> None:
        """Set root outline for axis via command spine."""
        did = self.axis_dim_id(axis)
        if did is None:
            return
        self._grid.execute_command("set_dimension_outline", dim_id=did, outline=root)

    def prune_empty_groups(self, nodes: list["OutlineNode"]) -> list["OutlineNode"]:
        """Remove empty group nodes from outline."""
        from lib_contracts.types import OutlineNode

        def _walk(node_list: list["OutlineNode"]) -> list["OutlineNode"]:
            result: list["OutlineNode"] = []
            for node in node_list:
                if node.item_id is None:
                    # It's a group - check if it has children after pruning
                    if node.children:
                        new_children = _walk(list(node.children))
                        if new_children:
                            result.append(
                                OutlineNode(
                                    label=node.label,
                                    item_id=None,
                                    children=new_children,
                                    node_id=node.node_id,
                                    display_edge_kind=node.display_edge_kind,
                                    is_aggregate=node.is_aggregate,
                                )
                            )
                    # Empty groups are dropped
                else:
                    # It's a leaf - keep it
                    if node.children:
                        new_children = _walk(list(node.children))
                        result.append(
                            OutlineNode(
                                label=node.label,
                                item_id=node.item_id,
                                children=new_children,
                                node_id=node.node_id,
                                display_edge_kind=node.display_edge_kind,
                                is_aggregate=node.is_aggregate,
                            )
                        )
                    else:
                        result.append(node)
            return result

        return _walk(nodes)

    def collect_empty_group_labels(self, nodes: list["OutlineNode"]) -> set[str]:
        """Collect labels of all empty groups that would be pruned.

        Returns a set of group labels that are empty (no children) and would be removed by prune_empty_groups.
        """
        from lib_contracts.types import OutlineNode
        empty_labels: set[str] = set()

        def _walk(node_list: list["OutlineNode"]) -> None:
            for node in node_list:
                if node.item_id is None and node.label:
                    # It's a group with a label
                    if node.children:
                        _walk(list(node.children))
                    else:
                        # Empty group - would be pruned
                        empty_labels.add(node.label)
                elif node.children:
                    _walk(list(node.children))

        _walk(nodes)
        return empty_labels
