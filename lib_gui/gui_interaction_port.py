"""Minimal port for REPL -> GUI shell interactions.

This is an explicit boundary between the REPL client and the GUI shell.
The REPL must not access GUI private widgets directly; it uses this port
for GUI-local operations like navigation, recording, file confirmation,
and window lifecycle.

Architecture:
    REPL -> GuiInteractionPort -> GUI internals

The port is intentionally tiny and boring. It grows only when a new
GUI-shell interaction is needed, never to expose broad GUI internals.
"""

from __future__ import annotations

from typing import Any, Callable


class GuiInteractionPort:
    """Explicit boundary for REPL -> GUI shell operations.

    Constructor:
        gui_window: The MainWindow or equivalent GUI root widget.
    """

    def __init__(self, gui_window: Any) -> None:
        self._gui = gui_window

    # ------------------------------------------------------------------
    # Window lifecycle
    # ------------------------------------------------------------------

    def close_window(self) -> None:
        """Close the GUI window (thread-safe)."""
        if self._gui is None:
            return
        try:
            from PySide6 import QtCore
            QtCore.QMetaObject.invokeMethod(
                self._gui,
                "close",
                QtCore.Qt.ConnectionType.BlockingQueuedConnection,
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Navigation / selection
    # ------------------------------------------------------------------

    def current_selection(self) -> tuple[int, int] | None:
        """Return current grid selection as (row, col), or None."""
        grid = getattr(self._gui, '_table', None)
        if grid is None:
            return None
        return grid._sel_row, grid._sel_col

    def grid_dimensions(self) -> tuple[int, int] | None:
        """Return grid size as (rows, cols), or None."""
        grid = getattr(self._gui, '_table', None)
        if grid is None or not grid._rows or not grid._cols:
            return None
        return len(grid._rows), len(grid._cols)

    def set_selection(self, row: int, col: int) -> None:
        """Set grid selection to (row, col) and emit update on GUI thread."""
        grid = getattr(self._gui, '_table', None)
        if grid is None:
            return

        def _do_navigate():
            grid._sel_row = row
            grid._sel_col = col
            grid._sel_mode = "cell"
            grid._sel_indices.clear()
            grid._anchor_row = row
            grid._anchor_col = col
            grid.selection_changed.emit()
            grid.update()
            grid.viewport().update()
            grid._request_repaint(f"navigate_port")
            grid._ensure_visible(grid._sel_row, grid._sel_col)

        grid._pending_navigate = _do_navigate
        from PySide6 import QtCore
        QtCore.QMetaObject.invokeMethod(
            grid,
            "_do_navigate_slot",
            QtCore.Qt.ConnectionType.QueuedConnection,
        )

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def confirm_discard_unsaved_changes(self) -> bool:
        """Ask user whether to discard unsaved changes.

        Returns True if the operation should proceed (user confirmed or no
        unsaved changes), False if cancelled.
        """
        if self._gui is None:
            return True
        if hasattr(self._gui, '_check_unsaved_changes'):
            return self._gui._check_unsaved_changes()
        return True

    def open_file(self, path: str) -> bool:
        """Open a file in the GUI. Returns True on success."""
        if self._gui is None:
            return False
        if hasattr(self._gui, 'open_file'):
            return self._gui.open_file(path)
        return False

    def get_workspace(self):
        """Return the current workspace object from the GUI."""
        if self._gui is None:
            return None
        return getattr(self._gui, '_ws', None)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def connect_selection_recording(
        self,
        on_selection_changed: Callable,
        on_cell_value_changed: Callable | None = None,
    ) -> None:
        """Connect recording callbacks to grid signals."""
        grid = getattr(self._gui, '_table', None)
        if grid is None:
            return
        from PySide6 import QtCore
        grid.selection_changed.connect(
            on_selection_changed,
            QtCore.Qt.ConnectionType.QueuedConnection,
        )
        if on_cell_value_changed and hasattr(grid, 'cell_value_changed'):
            grid.cell_value_changed.connect(
                on_cell_value_changed,
                QtCore.Qt.ConnectionType.QueuedConnection,
            )

    def disconnect_selection_recording(
        self,
        on_selection_changed: Callable,
    ) -> None:
        """Disconnect recording callbacks from grid signals."""
        grid = getattr(self._gui, '_table', None)
        if grid is None:
            return
        try:
            grid.selection_changed.disconnect(on_selection_changed)
        except Exception:
            pass

    def selection_addresses(self) -> list[str]:
        """Return semantic address strings for the current GUI selection.

        Delegates to the active grid's ``selected_addresses()``.
        Returns an empty list when no grid is available.
        """
        grid = getattr(self._gui, '_table', None)
        if grid is None or not hasattr(grid, 'selected_addresses'):
            return []
        return grid.selected_addresses()

    def recording_selection(self) -> tuple[int, int] | None:
        """Return current selection for recording purposes."""
        return self.current_selection()
