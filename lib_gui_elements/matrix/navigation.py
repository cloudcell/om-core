"""Navigation and cell lookup helpers for the matrix grid."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

# Debug flag for GUI - set DEBUG_GUI=true to enable verbose logging
DEBUG_GUI = os.environ.get("DEBUG_GUI", "false").lower() in ("true", "1", "yes")

if TYPE_CHECKING:
    from PySide6 import QtCore, QtGui, QtWidgets


class NavigationHelper:
    """Helper methods for cell navigation and position lookup."""

    def __init__(self, grid: "MatrixGrid") -> None:
        self._grid = grid

    def cell_at(self, pos: QtCore.QPoint) -> tuple[int, int] | None:
        """Get cell coordinates at a given point position."""
        off = self._grid._geometry.scroll_offset()
        x = pos.x() + off.x()
        y = pos.y() + off.y()
        header_h = self._grid._m.col_header_h * max(1, self._grid._col_header_levels)
        row_header_w = self._grid._geometry.row_header_width()
        if x < row_header_w or y < header_h:
            return None
        # Find column using custom widths
        col_x = row_header_w
        c = -1
        for i in range(len(self._grid._cols)):
            col_w = self._grid._geometry.col_width(i)
            if col_x <= x < col_x + col_w:
                c = i
                break
            col_x += col_w
        r = (y - header_h) // self._grid._m.row_h
        if not (0 <= r < len(self._grid._rows)):
            return None
        if c < 0 or c >= len(self._grid._cols):
            return None
        return int(r), int(c)

    def cell_rect(self, r: int, c: int) -> "QtCore.QRect":
        """Get the rectangle for a cell at (r, c)."""
        from PySide6 import QtCore

        off = self._grid._geometry.scroll_offset()
        row_header_w = self._grid._geometry.row_header_width()
        # Calculate x position using custom column widths
        x = row_header_w
        for i in range(c):
            x += self._grid._geometry.col_width(i)
        x -= off.x()
        header_h = self._grid._m.col_header_h * max(1, self._grid._col_header_levels)
        y = header_h + r * self._grid._m.row_h - off.y()
        return QtCore.QRect(
            int(x), int(y), self._grid._geometry.col_width(c), self._grid._m.row_h
        )

    def row_header_rect(self, r: int) -> "QtCore.QRect":
        """Get the rectangle for a row header at row r."""
        from PySide6 import QtCore

        off = self._grid._geometry.scroll_offset()
        header_h = self._grid._m.col_header_h * max(1, self._grid._col_header_levels)
        y = header_h + r * self._grid._m.row_h - off.y()
        row_header_w = self._grid._geometry.row_header_width()
        return QtCore.QRect(0, int(y), row_header_w, self._grid._m.row_h)

    def ensure_visible(self, r: int, c: int) -> None:
        """Ensure cell at (r, c) is visible by scrolling if needed."""
        if not (0 <= r < len(self._grid._rows) and 0 <= c < len(self._grid._cols)):
            return

        # Get current scroll position before any changes
        old_h = self._grid.horizontalScrollBar().value()
        old_v = self._grid.verticalScrollBar().value()

        # Get cell rectangle
        rect = self.cell_rect(r, c)
        visible = self._grid.viewport().rect()

        row_header_w = self._grid._geometry.row_header_width()
        header_h = self._grid._m.col_header_h * max(1, self._grid._col_header_levels)

        # Horizontal scroll
        if rect.left() < row_header_w:
            new_h = old_h - (row_header_w - rect.left())
            self._grid.horizontalScrollBar().setValue(new_h)
            DEBUG_GUI and print(f"DEBUG SCROLL: horizontal changed {old_h} -> {new_h} (cell {r},{c} left={rect.left()} < content_left={row_header_w})")
        elif rect.right() > visible.right():
            new_h = old_h + (rect.right() - visible.right())
            self._grid.horizontalScrollBar().setValue(new_h)
            DEBUG_GUI and print(f"DEBUG SCROLL: horizontal changed {old_h} -> {new_h} (cell {r},{c} right={rect.right()} > visible_right={visible.right()})")

        # Vertical scroll
        if rect.top() < header_h:
            new_v = old_v - (header_h - rect.top())
            self._grid.verticalScrollBar().setValue(new_v)
            DEBUG_GUI and print(f"DEBUG SCROLL: vertical changed {old_v} -> {new_v} (cell {r},{c} top={rect.top()} < content_top={header_h})")
        elif rect.bottom() > visible.bottom():
            new_v = old_v + (rect.bottom() - visible.bottom())
            self._grid.verticalScrollBar().setValue(new_v)
            DEBUG_GUI and print(f"DEBUG SCROLL: vertical changed {old_v} -> {new_v} (cell {r},{c} bottom={rect.bottom()} > visible_bottom={visible.bottom()})")

        # Log if no scroll change occurred
        final_h = self._grid.horizontalScrollBar().value()
        final_v = self._grid.verticalScrollBar().value()
        if final_h == old_h and final_v == old_v:
            DEBUG_GUI and print(f"DEBUG SCROLL: no change (cell {r},{c} already visible at h={old_h}, v={old_v})")

    def next_header_leaf_index(self, axis: str, start: int) -> int | None:
        """Find next leaf header index after start."""
        entries = self._grid._rows if axis == "row" else self._grid._cols
        for i in range(start + 1, len(entries)):
            if entries[i].get("is_leaf", False):
                return i
        return None

    def prev_header_leaf_index(self, axis: str, start: int) -> int | None:
        """Find previous leaf header index before start."""
        entries = self._grid._rows if axis == "row" else self._grid._cols
        for i in range(start - 1, -1, -1):
            if entries[i].get("is_leaf", False):
                return i
        return None

    def header_leaf_item_id(self, axis: str, index: int) -> str | None:
        """Return leaf item ID for header at given axis and index."""
        if axis == "row":
            target = self._grid._geometry.resolve_row_leaf_target(index)
        else:
            target = self._grid._geometry.resolve_col_leaf_target(index)
        if target is None:
            return None
        return target[1]  # target is (dim_id, item_id, item_name)

    def find_next_leaf(self, entries: list[dict], start: int) -> int:
        """Find next leaf entry starting from position, with wrap-around."""
        for i in range(max(0, start), len(entries)):
            if entries[i].get("is_leaf", False):
                return i
        for i in range(0, max(0, start)):
            if entries[i].get("is_leaf", False):
                return i
        return max(0, min(start, len(entries) - 1))

    def clamp_selection_to_leaf(
        self, sel_row: int, sel_col: int, rows: list[dict], cols: list[dict]
    ) -> tuple[int, int]:
        """Ensure selection is on a leaf row/col if possible."""
        if rows and not rows[sel_row].get("is_leaf", False):
            sel_row = self.find_next_leaf(rows, sel_row)
        if cols and not cols[sel_col].get("is_leaf", False):
            sel_col = self.find_next_leaf(cols, sel_col)
        return sel_row, sel_col
