from __future__ import annotations

import os
from datetime import datetime
from typing import Callable

from PySide6 import QtCore, QtWidgets

from lib_gui.cell_read_model import CellReadModel
from lib_gui.view_workspace import ViewWorkspacePane
from lib_gui.view_workspace_controller import ViewWorkspaceController
from lib_gui.workspace_read_model import WorkspaceReadModel
from lib_command.core.session import CommandSession


class ViewWorkspaceWindow(QtWidgets.QMainWindow):
    """Auxiliary window hosting an independent view workspace pane."""

    def __init__(
        self,
        on_workspace_changed: Callable[[], None],
        parent: QtWidgets.QWidget | None = None,
        session: CommandSession | None = None,
    ) -> None:
        super().__init__(parent)
        # File tracking attributes (mirroring MainWindow)
        self._filepath: str | None = None
        self._dirty = False
        self._workspace_number = 0  # Set by MainWindow when creating
        self._update_window_title()

        if session is None:
            raise RuntimeError(
                "ViewWorkspaceWindow requires session from the GUI composition root"
            )

        self._pane = ViewWorkspacePane(
            session=session,
            parent=self,
        )
        cell_rm = CellReadModel(session)
        ws_rm = WorkspaceReadModel(session)
        self._controller = ViewWorkspaceController(
            session=session,
            pane=self._pane,
            cell_read_model=cell_rm,
            workspace_read_model=ws_rm,
            parent=self,
        )
        self._controller.workspace_changed.connect(on_workspace_changed)
        self._controller.initialize()

        # Phase E: Engine publishes event.workspace.dirty_changed; subscribe via session
        if session is not None:
            session.subscribe("event.workspace.dirty_changed", self._on_workspace_dirty_changed)

        self.setCentralWidget(self._pane)
        self.resize(900, 500)

    @property
    def controller(self) -> ViewWorkspaceController:
        return self._controller

    def reload_workspace(self) -> None:
        self._controller.reload_workspace()

    def _update_window_title(self) -> None:
        """Update window title based on filepath, dirty state, and workspace number."""
        if self._filepath:
            filename = os.path.basename(self._filepath)
        else:
            # Generate timestamped default name
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"New_Model_{timestamp}.json"
        
        dirty_marker = "*" if self._dirty else ""
        
        if self._workspace_number > 0:
            title = f"OM: {dirty_marker}{filename} (Workspace {self._workspace_number})"
        else:
            title = f"OM: {dirty_marker}{filename}"
        
        self.setWindowTitle(title)

    def _on_workspace_dirty_changed(self, event) -> None:
        """Handle event.workspace.dirty_changed events from the bus."""
        is_dirty = event.payload.get("is_dirty", True) if hasattr(event, "payload") else True
        self._mark_dirty(is_dirty)

    def _mark_dirty(self, dirty: bool = True) -> None:
        """Mark workspace as having unsaved changes."""
        if self._dirty != dirty:
            self._dirty = dirty
            self._update_window_title()
