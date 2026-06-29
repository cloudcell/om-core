"""Clipboard operations for the matrix grid."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PySide6 import QtCore, QtGui, QtWidgets


class ClipboardHelper:
    """Handles clipboard copy/paste and clear operations for the grid."""

    def __init__(self, grid: "MatrixGrid") -> None:
        self._grid = grid

    def copy_selection(self) -> None:
        """Copy selected cells to clipboard as tab-separated values."""
        from PySide6 import QtWidgets

        cells = self._grid._iter_selected_cells()
        if not cells:
            return

        values: dict[tuple[int, int], str] = {}
        min_r = min_c = None
        max_r = max_c = None

        view = self._grid._workspace_read_model.get_view(self._grid._view_id)
        view_id = view["id"] if view else self._grid._view_id

        for r, c in cells:
            if not (0 <= r < len(self._grid._rows) and 0 <= c < len(self._grid._cols)):
                continue
            if not self._grid._rows[r].get("is_leaf", False):
                continue
            try:
                row_key = self._grid._row_keys[self._grid._leaf_row_index(r)]
                col_key = self._grid._col_keys[c]
                cell_value = self._grid._cell_read_model.cell_value(view_id, row_key, col_key)
                val = "" if cell_value is None else str(cell_value)
            except Exception:
                val = ""
            values[(r, c)] = val
            min_r = r if min_r is None else min(min_r, r)
            max_r = r if max_r is None else max(max_r, r)
            min_c = c if min_c is None else min(min_c, c)
            max_c = c if max_c is None else max(max_c, c)

        if min_r is None or min_c is None or max_r is None or max_c is None:
            return

        lines: list[str] = []
        for r in range(min_r, max_r + 1):
            row_vals: list[str] = []
            for c in range(min_c, max_c + 1):
                row_vals.append(values.get((r, c), ""))
            lines.append("\t".join(row_vals))

        QtWidgets.QApplication.clipboard().setText("\n".join(lines))

    def paste_clipboard(self) -> None:
        """Paste clipboard content into grid starting at current selection."""
        from PySide6 import QtWidgets

        cb = QtWidgets.QApplication.clipboard()
        text = cb.text()
        if not text:
            return

        rows = [line for line in text.splitlines()]
        grid = [r.split("\t") for r in rows]
        if not grid:
            return

        start_r, start_c = self._grid._sel_row, self._grid._sel_col
        view = self._grid._workspace_read_model.get_view(self._grid._view_id)
        view_id = view["id"] if view else self._grid._view_id

        for dr, row_vals in enumerate(grid):
            for dc, val in enumerate(row_vals):
                r = start_r + dr
                c = start_c + dc
                if not (0 <= r < len(self._grid._rows) and 0 <= c < len(self._grid._cols)):
                    continue
                if not self._grid._rows[r].get("is_leaf", False):
                    continue
                row_key = self._grid._row_keys[self._grid._leaf_row_index(r)]
                col_key = self._grid._col_keys[c]
                self._grid.execute_command(
                    "set_cell_by_keys",
                    view_id=view_id,
                    row_key=row_key,
                    col_key=col_key,
                    value=val,
                )

        self._grid.reload(invalidate_tiles="data")
        self._grid._edit_orig_value = None

    def clear_selection(self) -> None:
        """Clear values in all selected cells."""
        cells = self._grid._iter_selected_cells()
        print(f"[DEBUG DELETE] clear_selection called, cells={cells}")
        # Fallback: if selection list is empty, clear the current cell
        if not cells and 0 <= self._grid._sel_row < len(self._grid._rows) and 0 <= self._grid._sel_col < len(self._grid._cols):
            cells = [(self._grid._sel_row, self._grid._sel_col)]
            print(f"[DEBUG DELETE] using fallback current cell: row={self._grid._sel_row}, col={self._grid._sel_col}")

        view = self._grid._workspace_read_model.get_view(self._grid._view_id)
        view_id = view["id"] if view else self._grid._view_id
        print(f"[DEBUG DELETE] clearing {len(cells)} cells")

        for r, c in cells:
            if not self._grid._rows[r].get("is_leaf", False):
                print(f"[DEBUG DELETE] skipping row {r} - not a leaf")
                continue
            leaf_idx = self._grid._leaf_row_index(r)
            if not (0 <= leaf_idx < len(self._grid._row_keys)):
                print(f"[DEBUG DELETE] skipping row {r} - leaf_idx {leaf_idx} out of range")
                continue
            if not (0 <= c < len(self._grid._col_keys)):
                print(f"[DEBUG DELETE] skipping col {c} - out of range")
                continue
            row_key = self._grid._row_keys[leaf_idx]
            col_key = self._grid._col_keys[c]
            print(f"[DEBUG DELETE] clearing cell at row={r}, col={c}, row_key={row_key[:20] if row_key else None}, col_key={col_key[:20] if col_key else None}")
            self._grid.execute_command(
                "clear_cell_by_keys",
                view_id=view_id,
                row_key=row_key,
                col_key=col_key,
            )

        print(f"[DEBUG DELETE] emitting content_changed to trigger recalc and refresh")
        # Emit content_changed to trigger recalc and UI refresh via _on_matrix_content_changed
        self._grid.content_changed.emit()
