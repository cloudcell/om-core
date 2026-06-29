"""Event handling helpers for the matrix grid."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PySide6 import QtCore, QtGui, QtWidgets


class EventHelper:
    """Helper methods for event handling (main event handlers stay in MatrixGrid)."""

    def __init__(self, grid: "MatrixGrid") -> None:
        self._grid = grid

    def send_editor_key_event(self, source_event: QtGui.QKeyEvent) -> None:
        """Forward a key event to the editor widget."""
        from PySide6 import QtCore, QtGui

        # Create a new key event with the same key, modifier and text.
        new_event = QtGui.QKeyEvent(
            QtCore.QEvent.Type.KeyPress,
            source_event.key(),
            source_event.modifiers(),
            source_event.text(),
            source_event.isAutoRepeat(),
            source_event.count(),
        )
        QtCore.QCoreApplication.postEvent(self._grid._editor, new_event)

    def post_grid_key_event(self, source_event: QtGui.QKeyEvent) -> None:
        """Post a key event to the grid itself (for navigation)."""
        from PySide6 import QtCore, QtGui

        new_event = QtGui.QKeyEvent(
            source_event.type(),
            source_event.key(),
            source_event.modifiers(),
            source_event.text(),
            source_event.isAutoRepeat(),
            source_event.count(),
        )
        QtCore.QCoreApplication.postEvent(self._grid, new_event)

    # DEAD CODE — runtime rename_header_hit and contextMenuEvent are on MatrixGrid.
    # These methods were never called; they duplicated MatrixGrid methods that
    # contained direct Engine reads and mutations. Removed 2026-06-06 in F6a.
    # If any test or import breakage occurs, quarantine instead of restoring.
