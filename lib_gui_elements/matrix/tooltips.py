"""Tooltip generation helpers for the matrix grid."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PySide6 import QtCore, QtGui, QtWidgets


class TooltipHelper:
    """Helper methods for generating debug tooltips."""

    def __init__(self, grid: "MatrixGrid") -> None:
        self._grid = grid

    def get_row_leaf_tooltip(self, payload: tuple) -> str:
        """Generate debug tooltip for a row leaf header."""
        item_id, row_idx = payload
        view = self._grid._workspace_read_model.get_view(self._grid._view_id)
        row_dim_ids = list(view.get("row_dim_ids", []) or []) if view else []
        is_stacked = len(row_dim_ids) > 1

        # Determine if this is a dimension leaf or the actual row leaf
        header_type = "ROW LEAF HEADER"
        leaf_type = "row_leaf"
        if is_stacked and 0 <= row_idx < len(self._grid._rows):
            row = self._grid._rows[row_idx]
            labels = row.get("labels", [])
            label_paths = row.get("label_paths", [])
            # In stacked mode, check if this is the final leaf level
            # The last label corresponds to the actual row leaf
            if len(labels) > 1 and len(label_paths) > 1:
                # Find which level this leaf corresponds to
                for i, path in enumerate(label_paths):
                    if isinstance(path, tuple) and len(path) == 1 and path[0] == row_idx:
                        # This is a leaf at level i
                        if i < len(labels) - 1:
                            header_type = "DIMENSION LEAF HEADER"
                            leaf_type = "dim_leaf"
                        break

        info = [
            f"=== {header_type} ===",
            f"Type: {leaf_type}",
            f"Mode: {'stacked' if is_stacked else 'single-dim'}",
            f"Dimensions: {len(row_dim_ids)}",
            f"Item ID: {item_id}",
            f"Row Index: {row_idx}",
        ]

        if 0 <= row_idx < len(self._grid._rows):
            row = self._grid._rows[row_idx]
            info.extend([
                f"Is Leaf: {row.get('is_leaf', False)}",
                f"Labels: {row.get('labels', [])}",
                f"Label Paths: {row.get('label_paths', [])}",
                f"Path: {row.get('path', 'N/A')}",
                f"Level: {row.get('level', 'N/A')}",
            ])
            if row_idx < len(self._grid._row_keys):
                info.append(f"Row Key: {self._grid._row_keys[row_idx]}")

        return "\n".join(info)

    def get_row_group_tooltip(self, payload: tuple) -> str:
        """Generate debug tooltip for a row group header."""
        path, r0, r1, clicked_r = payload
        view = self._grid._workspace_read_model.get_view(self._grid._view_id)
        row_dim_ids = list(view.get("row_dim_ids", []) or []) if view else []
        is_stacked = len(row_dim_ids) > 1

        # Find band info for this group
        band_info = None
        for band in self._grid._row_bands:
            band_r0 = band.get("r0")
            band_r1 = band.get("r1")
            if band_r0 is None or band_r1 is None:
                # Match if hit range overlaps with band's rows
                band_info = (
                    f"  Level: {band.get('level')}\n"
                    f"  Label: {band.get('label')!r}\n"
                    f"  Row Range: {band.get('r0')}-{band.get('r1')}\n"
                    f"  Shaded: {band.get('shaded', False)}"
                )
                break
            # Check if this band contains the clicked row
            if band_r0 <= clicked_r <= band_r1:
                band_info = (
                    f"  Level: {band.get('level')}\n"
                    f"  Label: {band.get('label')!r}\n"
                    f"  Row Range: {band.get('r0')}-{band.get('r1')}\n"
                    f"  Shaded: {band.get('shaded', False)}"
                )
                break

        is_leaf = len(path) == 1
        header_type = "ROW LEAF HEADER" if is_leaf else "ROW GROUP HEADER"

        info = [
            f"=== {header_type} ===",
            f"Type: row_group",
            f"Mode: {'stacked' if is_stacked else 'single-dim'}",
            f"Dimensions: {len(row_dim_ids)}",
            f"Path: {path}",
            f"Clicked Row: {clicked_r}",
            f"Row Range (from hit): {r0}-{r1}",
            "Band Info:",
            band_info if band_info else "  (band not found)",
        ]

        # Add dimension info for stacked mode
        if is_stacked:
            # In stacked mode, the band level directly corresponds to the dimension index
            # Level 0 = first dimension, Level 1 = second dimension, etc.
            band_level = band.get("level") if band else None
            if band_level is not None:
                # Map band level to dimension index (each dimension has groups + items)
                dim_idx = band_level // 2 if len(row_dim_ids) > 1 else band_level
            else:
                dim_idx = "N/A"
            info.append("")
            info.append("Stacked Mode Info:")
            info.append(f"  Band Level: {band_level if band else 'N/A'}")
            info.append(f"  Band Type: {'group' if band and band.get('shaded') else 'item/leaf'}")
            info.append(f"  Dimension Index: {dim_idx}")
        else:
            # Single-dim mode: outline info is meaningful
            root = self._grid._dimensions.outline_root("row")
            if root:
                node = self._get_node_at_path(root, path)
                if node:
                    info.append("")
                    info.append("Outline Info:")
                    info.extend([
                        f"  Node Label: {node.label!r}",
                        f"  Node Item ID: {node.item_id}",
                        f"  Children Count: {len(node.children) if node.children else 0}",
                    ])

        return "\n".join(info)

    def get_col_leaf_tooltip(self, payload: int) -> str:
        """Generate debug tooltip for a column leaf header."""
        col_idx = payload

        # Get view info for mode detection
        view = self._grid._workspace_read_model.get_view(self._grid._view_id)
        col_dim_ids = list(view.get("col_dim_ids", []) or []) if view else []
        is_stacked = len(col_dim_ids) > 1

        info = [
            "=== COLUMN LEAF HEADER ===",
            f"Type: col_leaf",
            f"Mode: {'stacked' if is_stacked else 'single-dim'}",
            f"Dimensions: {len(col_dim_ids)}",
            f"Column Index: {col_idx}",
        ]

        if 0 <= col_idx < len(self._grid._cols):
            col = self._grid._cols[col_idx]
            info.extend([
                f"Item ID: {col.get('item_id', 'N/A')}",
                f"Labels: {col.get('labels', [])}",
                f"Label Paths: {col.get('label_paths', [])}",
                f"Path: {col.get('path', 'N/A')}",
                f"Level: {col.get('level', 'N/A')}",
            ])
            if col_idx < len(self._grid._col_keys):
                info.append(f"Column Key: {self._grid._col_keys[col_idx]}")

        return "\n".join(info)

    def get_col_group_tooltip(self, payload: tuple) -> str:
        """Generate debug tooltip for a column group header."""
        path, r0, r1, clicked_r = payload
        view = self._grid._workspace_read_model.get_view(self._grid._view_id)
        col_dim_ids = list(view.get("col_dim_ids", []) or []) if view else []
        is_stacked = len(col_dim_ids) > 1

        # Find band info for this group
        band_info = None
        for band in self._grid._col_bands:
            band_r0 = band.get("r0")
            band_r1 = band.get("r1")
            if band_r0 is None or band_r1 is None:
                # Match if hit range overlaps with band's rows
                band_info = (
                    f"  Level: {band.get('level')}\n"
                    f"  Label: {band.get('label')!r}\n"
                    f"  Row Range: {band.get('r0')}-{band.get('r1')}\n"
                    f"  Shaded: {band.get('shaded', False)}"
                )
                break
            # Check if this band contains the clicked row
            if band_r0 <= clicked_r <= band_r1:
                band_info = (
                    f"  Level: {band.get('level')}\n"
                    f"  Label: {band.get('label')!r}\n"
                    f"  Row Range: {band.get('r0')}-{band.get('r1')}\n"
                    f"  Shaded: {band.get('shaded', False)}"
                )
                break

        is_leaf = len(path) == 1
        header_type = "COL LEAF HEADER" if is_leaf else "COL GROUP HEADER"

        info = [
            f"=== {header_type} ===",
            f"Type: col_group",
            f"Mode: {'stacked' if is_stacked else 'single-dim'}",
            f"Dimensions: {len(col_dim_ids)}",
            f"Path: {path}",
            f"Clicked Row: {clicked_r}",
            f"Row Range (from hit): {r0}-{r1}",
            "Band Info:",
            band_info if band_info else "  (band not found)",
        ]

        # Add dimension info for stacked mode
        if is_stacked:
            # In stacked mode, bands alternate: groups (dim1), items (dim1), groups (dim2), items (dim2)...
            # The path refers to the band structure, not the outline structure
            # Calculate dimension index from band level
            band_level = band.get("level") if band else None
            if band_level is not None:
                dim_idx = band_level // 2 if len(col_dim_ids) > 1 else band_level
            else:
                dim_idx = "N/A"
            info.append("")
            info.append("Stacked Mode Info:")
            info.append(f"  Band Level: {band_level if band else 'N/A'}")
            info.append(f"  Band Type: {'group' if band and band.get('shaded') else 'item/leaf'}")
            info.append(f"  Dimension Index: {dim_idx}")
        else:
            # Single-dim mode: outline info is meaningful
            root = self._grid._dimensions.outline_root("col")
            if root:
                node = self._get_node_at_path(root, path)
                if node:
                    info.append("")
                    info.append("Outline Info:")
                    info.extend([
                        f"  Node Label: {node.label!r}",
                        f"  Node Item ID: {node.item_id}",
                        f"  Children Count: {len(node.children) if node.children else 0}",
                    ])

        return "\n".join(info)

    def get_cell_debug_tooltip(self, pos: "QtCore.QPoint") -> str | None:
        """Generate debug tooltip for a cell at the given position."""
        off = self._grid._geometry.scroll_offset()
        x_view = pos.x()
        y_view = pos.y()
        x = x_view + off.x()
        y = y_view + off.y()

        header_h = self._grid._m.col_header_h * max(1, self._grid._col_header_levels)
        row_header_w = self._grid._geometry.row_header_width()

        if x < row_header_w or y < header_h:
            return None

        # Calculate row
        r = (y - header_h) // self._grid._m.row_h

        # Calculate column using actual widths
        col_x = row_header_w
        c = -1
        for i in range(len(self._grid._cols)):
            col_w = self._grid._geometry.col_width(i)
            if col_x <= x < col_x + col_w:
                c = i
                break
            col_x += col_w

        if r < 0 or r >= len(self._grid._rows) or c < 0 or c >= len(self._grid._cols):
            return None

        row = self._grid._rows[r]
        col = self._grid._cols[c]

        # Get view info for mode detection
        view = self._grid._workspace_read_model.get_view(self._grid._view_id)
        row_dim_ids = list(view.get("row_dim_ids", []) or []) if view else []
        col_dim_ids = list(view.get("col_dim_ids", []) or []) if view else []
        row_stacked = len(row_dim_ids) > 1
        col_stacked = len(col_dim_ids) > 1

        is_leaf_cell = row.get("is_leaf", False) and col.get("is_leaf", False)

        # Get cell value and info via read model (resolve visual indices to keys)
        cell_value = "N/A"
        cell_source = "N/A"
        cell_rule = "N/A"
        cell_error = "N/A"
        if is_leaf_cell:
            try:
                leaf_r = self._grid._leaf_row_index(r)
                if 0 <= leaf_r < len(self._grid._row_keys) and 0 <= c < len(self._grid._col_keys):
                    row_key = self._grid._row_keys[leaf_r]
                    col_key = self._grid._col_keys[c]
                    cell_dto = self._grid._cell_read_model.get_cell(self._grid._view_id, row_key, col_key)
                    cell_value = cell_dto.get("value", "N/A")
                    explain = cell_dto.get("explain", {})
                    cell_source = explain.get("source", "N/A")
                    cell_rule = explain.get("rule_body") or "N/A"
                    cell_error = explain.get("error") or "N/A"
            except Exception:
                pass

        info = [
            "=== CELL ===",
            f"Row Mode: {'stacked' if row_stacked else 'single-dim'} ({len(row_dim_ids)} dims)",
            f"Col Mode: {'stacked' if col_stacked else 'single-dim'} ({len(col_dim_ids)} dims)",
            f"Row Index: {r}",
            f"Column Index: {c}",
            f"Is Leaf Cell: {is_leaf_cell}",
            f"Row Item ID: {row.get('item_id', 'N/A')}",
            f"Col Item ID: {col.get('item_id', 'N/A')}",
            f"Row Key: {self._grid._row_keys[r] if r < len(self._grid._row_keys) else 'N/A'}",
            f"Col Key: {self._grid._col_keys[c] if c < len(self._grid._col_keys) else 'N/A'}",
            "",
            "Cell Value Info:",
            f"  Value: {cell_value}",
            f"  Source: {cell_source}",
            f"  Rule: {cell_rule}",
            f"  Error: {cell_error}",
        ]

        return "\n".join(info)

    def _get_node_at_path(self, nodes: list[Any], path: tuple[int, ...]) -> Any | None:
        """Get node at path in outline tree."""
        arr = nodes
        cur = None
        from lib_contracts.types import OutlineNode
        for i in path:
            if not (0 <= i < len(arr)):
                return None
            cur = arr[i]
            if not isinstance(cur, OutlineNode):
                return None
            arr = list(cur.children)
        return cur
