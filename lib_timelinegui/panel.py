"""Timeline Panel - Dock widget wrapper for TimelineWidget.

Provides TimelineDockManager for MainWindow integration.
Uses lib_timelinewidget for the actual timeline visualization.

The panel is a pure client: all timeline reads go through the query spine and
all writes go through the command spine. It does not open the timeline SQLite
file directly.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional, List, Callable
from datetime import datetime, timezone

from PySide6 import QtCore, QtGui, QtWidgets

from lib_timelinewidget import TimelineWidget, SnapshotInfo, SnapshotType
from lib_timelinewidget.engine import TimelineEngine
from lib_command.dto.timeline import TimelineSnapshotDTO
import logging

logger = logging.getLogger(__name__)



class TimelinePanel(QtWidgets.QDockWidget):
    """Dockable timeline panel for MainWindow.

    Wraps TimelineWidget and provides session management interface.
    Initially uses mock data; connects to real datastore when available.

    Signals:
        restore_requested: Emitted when user requests restore (snapshot_id, callback)
        checkpoint_requested: Emitted when user requests checkpoint (description, callback)
        new_session_requested: Emitted when user requests new session (callback)
    """

    # Permission-based signals - handlers must call callback(True/False) to approve
    restore_permission_requested = QtCore.Signal(str, object)  # snapshot_id, callback
    checkpoint_permission_requested = QtCore.Signal(str, object)  # description, callback
    new_session_permission_requested = QtCore.Signal(object)  # callback

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__("Timeline", parent)

        logger.info("__init__() starting...")

        # Required for QMainWindow.saveState() to save/restore dock position
        self.setObjectName("TimelineDock")

        self.setAllowedAreas(
            QtCore.Qt.DockWidgetArea.LeftDockWidgetArea |
            QtCore.Qt.DockWidgetArea.RightDockWidgetArea |
            QtCore.Qt.DockWidgetArea.BottomDockWidgetArea
        )

        # Enable dock features for proper resize handling
        self.setFeatures(
            QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        # Initialize session state FIRST (before creating widget)
        self._snapshots: List[SnapshotInfo] = []
        self._current_branch: str = "main"
        self._last_snapshot_id: Optional[str] = None
        self._restore_in_progress: bool = False  # Prevent concurrent restores
        self._session: Any = None  # CommandSession for bus-based checkpoint/restore

        # Polling timer: in multi-window / multi-process setups the local bus
        # may not see checkpoints created by another process. Poll the canonical
        # datastore so the panel eventually converges.
        self._poll_interval_ms: int = 2000
        self._refresh_timer = QtCore.QTimer(self)
        self._refresh_timer.timeout.connect(self._poll_datastore)

        # Debounce timer: coalesce rapid reload requests (e.g. event bus
        # redelivering workspace.loaded during remote startup) into a single
        # timeline_snapshots query.
        self._reload_debounce_timer = QtCore.QTimer(self)
        self._reload_debounce_timer.setSingleShot(True)
        self._reload_debounce_timer.timeout.connect(self._reload_snapshots)

        # Central widget containing the timeline
        self._container = QtWidgets.QWidget()
        self._layout = QtWidgets.QVBoxLayout(self._container)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(4)

        # Toolbar
        self._toolbar = self._create_toolbar()
        self._layout.addLayout(self._toolbar)

        # Timeline widget - pass initial snapshots so it has data immediately
        self._timeline = TimelineWidget()
        self._timeline.set_snapshots(self._snapshots)  # Set data BEFORE adding to layout

        # Scroll area for timeline with standard Qt scrollbars
        self._scroll = QtWidgets.QScrollArea()
        self._scroll.setWidget(self._timeline)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._layout.addWidget(self._scroll, stretch=1)

        # Info panel - displays selected snapshot details
        self._info_panel = self._create_info_panel()
        self._layout.addWidget(self._info_panel)

        # Connect signals
        self._timeline.node_selected.connect(self._on_node_selected)
        self._timeline.node_double_clicked.connect(self._on_node_double_clicked)
        self._timeline.restore_requested.connect(self._on_restore_requested)
        self._timeline.rename_requested.connect(self._on_rename_requested)
        self._timeline.create_snapshot_requested.connect(self._on_create_snapshot)

        self.setWidget(self._container)
        
        # Set initial size for proper dock state save/restore
        self.setMinimumSize(250, 200)
        self.resize(350, 400)  # Default size
        
        logger.info("__init__() complete")

    def _create_info_panel(self) -> QtWidgets.QFrame:
        """Create info panel showing selected snapshot details."""
        panel = QtWidgets.QFrame()
        panel.setFrameStyle(QtWidgets.QFrame.Shape.StyledPanel | QtWidgets.QFrame.Shadow.Sunken)
        panel.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border-top: 1px solid #dee2e6;
            }
            QLabel {
                background: transparent;
                border: none;
            }
        """)

        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Title label
        self._info_title = QtWidgets.QLabel("No snapshot selected")
        self._info_title.setStyleSheet("font-weight: bold; color: #495057;")
        layout.addWidget(self._info_title)

        # Details grid
        details_layout = QtWidgets.QGridLayout()
        details_layout.setColumnStretch(1, 1)
        details_layout.setHorizontalSpacing(12)
        details_layout.setVerticalSpacing(4)

        # ID
        details_layout.addWidget(QtWidgets.QLabel("ID:"), 0, 0)
        self._info_id = QtWidgets.QLabel("-")
        self._info_id.setStyleSheet("color: #6c757d; font-family: monospace; font-size: 11px;")
        self._info_id.setWordWrap(True)
        details_layout.addWidget(self._info_id, 0, 1)

        # Branch
        details_layout.addWidget(QtWidgets.QLabel("Branch:"), 1, 0)
        self._info_branch = QtWidgets.QLabel("-")
        self._info_branch.setStyleSheet("color: #6c757d;")
        details_layout.addWidget(self._info_branch, 1, 1)

        # Parent
        details_layout.addWidget(QtWidgets.QLabel("Parent:"), 2, 0)
        self._info_parent = QtWidgets.QLabel("-")
        self._info_parent.setStyleSheet("color: #6c757d; font-family: monospace; font-size: 11px;")
        self._info_parent.setWordWrap(True)
        details_layout.addWidget(self._info_parent, 2, 1)

        # Created at
        details_layout.addWidget(QtWidgets.QLabel("Created:"), 3, 0)
        self._info_created = QtWidgets.QLabel("-")
        self._info_created.setStyleSheet("color: #6c757d;")
        details_layout.addWidget(self._info_created, 3, 1)

        layout.addLayout(details_layout)
        layout.addStretch()

        return panel

    def _create_toolbar(self) -> QtWidgets.QHBoxLayout:
        """Create toolbar buttons."""
        layout = QtWidgets.QHBoxLayout()

        # New Session button (hidden - auto-triggered on new file / open file)
        self._btn_new_session = QtWidgets.QPushButton("New Session")
        self._btn_new_session.setToolTip("Start a new session (clears timeline)")
        self._btn_new_session.clicked.connect(self._on_new_session_requested)
        self._btn_new_session.setVisible(False)  # Hidden, auto-triggered instead
        # layout.addWidget(self._btn_new_session)  # Not added to UI
        
        # Checkpoint button
        self._btn_checkpoint = QtWidgets.QPushButton("Checkpoint")
        self._btn_checkpoint.setToolTip("Create manual checkpoint")
        self._btn_checkpoint.clicked.connect(self._on_create_snapshot)
        layout.addWidget(self._btn_checkpoint)

        # Dump State button
        self._btn_dump = QtWidgets.QPushButton("Dump State")
        self._btn_dump.setToolTip("Print timeline workspace state to terminal")
        self._btn_dump.clicked.connect(self._on_dump_state)
        layout.addWidget(self._btn_dump)

        # Spacer pushes buttons to left
        layout.addStretch()

        return layout
    
    def _init_session_start(self):
        """Initialize session - load existing snapshots via the query spine.

        The panel only *displays* snapshots; it does not create them.
        Snapshot creation is the composition root's responsibility
        (lib_runtime.app_host / runtime_factory), which respects the
        persistence mode config.
        """
        logger.debug("_init_session_start() called")
        self._current_branch = "main"
        self._reload_snapshots()

    def _on_new_session_requested(self):
        """Handle new session request - asks for permission via signal."""
        callback_invoked = [False]
        
        def on_permission_granted(approved: bool):
            callback_invoked[0] = True
            if approved:
                self._do_start_new_session()
            else:
                pass  # Session denied
        
        # Emit the signal - handlers will call the callback
        self.new_session_permission_requested.emit(on_permission_granted)
        
        # Check if callback was invoked (synchronously)
        if not callback_invoked[0]:
            pass  # No permission handler, denied

    def _do_start_new_session(self):
        """Actually start new session (internal use only - requires permission first)."""
        self._snapshots = []
        self._current_branch = "main"
        self._last_snapshot_id = None

        self._timeline.set_snapshots(self._snapshots)
        self._timeline.update()

    def start_new_session(self):
        """Start a new session (legacy - use _do_start_new_session with permission)."""
        self._do_start_new_session()

    def reload(self) -> None:
        """Reload snapshots from the query spine.

        This is a public API for callers such as MainWindow to request a
        refresh after a workspace switch or checkpoint event. Calls are
        debounced so a burst of events results in one timeline query.
        """
        self._debounced_reload()

    def _debounced_reload(self) -> None:
        """Schedule a single reload, coalescing rapid repeated calls."""
        if not self._reload_debounce_timer.isActive():
            self._reload_debounce_timer.start(100)


    def _get_main_branch_leaf(self) -> Optional[str]:
        """Find the leaf snapshot of the main branch (the one with no children on main)."""
        # Build a map of which snapshots are children (have parents)
        children_on_main = set()
        for snap in self._snapshots:
            if snap.parent_id and snap.branch_name == "main":
                children_on_main.add(snap.parent_id)

        # Find main branch snapshots that are NOT parents of any other main snapshot
        # (i.e., the leaf nodes on main branch)
        main_leaf_candidates = []
        for snap in self._snapshots:
            if snap.branch_name == "main" and snap.snapshot_id not in children_on_main:
                main_leaf_candidates.append(snap)

        # If no candidates, return the session start (first snapshot with no parent)
        if not main_leaf_candidates:
            for snap in self._snapshots:
                if snap.parent_id is None:
                    return snap.snapshot_id
            return None

        # Return the most recently created leaf (should be only one in normal case)
        # Sort by creation time, take the latest
        main_leaf_candidates.sort(key=lambda s: s.created_at)
        return main_leaf_candidates[-1].snapshot_id

    def _generate_id(self) -> str:
        """Generate unique snapshot ID (full UUID)."""
        from uuid import uuid4

        return str(uuid4())

    def _init_mock_data(self):
        """Initialize with mock snapshot data for UI testing. (Deprecated - use start_new_session)"""
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        self._snapshots = [
            SnapshotInfo(
                snapshot_id="snap-001",
                description="Session Start",
                branch_name="main",
                created_at=now - timedelta(hours=2),
                type=SnapshotType.MANUAL
            ),
            SnapshotInfo(
                snapshot_id="snap-002",
                description="Auto-save",
                branch_name="main",
                parent_id="snap-001",
                created_at=now - timedelta(minutes=45),
                type=SnapshotType.AUTO
            ),
            SnapshotInfo(
                snapshot_id="snap-003",
                description="Before restructure",
                branch_name="main",
                parent_id="snap-002",
                created_at=now - timedelta(minutes=20),
                type=SnapshotType.MANUAL
            ),
        ]
        self._last_snapshot_id = "snap-003"
        self._timeline.set_snapshots(self._snapshots)
    
    # Signal handlers
    def _on_node_selected(self, snapshot_id: str):
        """Handle node selection - update info panel with snapshot details."""

        # Find the snapshot in our list
        selected_snap = None
        for snap in self._snapshots:
            if snap.snapshot_id == snapshot_id:
                selected_snap = snap
                break

        if selected_snap:
            # Update info panel (truncate title if > 50 chars)
            desc = selected_snap.description or "Untitled"
            if len(desc) > 50:
                desc = desc[:50] + "..."
            self._info_title.setText(desc)
            self._info_id.setText(selected_snap.snapshot_id)
            self._info_branch.setText(selected_snap.branch_name)
            self._info_parent.setText(selected_snap.parent_id or "(root)")
            self._info_created.setText(selected_snap.created_at.strftime("%Y-%m-%d %H:%M:%S"))
        else:
            # Snapshot not in our list - reload from query spine and try again
            self._reload_snapshots()
            for snap in self._snapshots:
                if snap.snapshot_id == snapshot_id:
                    desc = snap.description or "Untitled"
                    if len(desc) > 50:
                        desc = desc[:50] + "..."
                    self._info_title.setText(desc)
                    self._info_id.setText(snap.snapshot_id)
                    self._info_branch.setText(snap.branch_name)
                    self._info_parent.setText(snap.parent_id or "(root)")
                    self._info_created.setText(snap.created_at.strftime("%Y-%m-%d %H:%M:%S"))
                    # Refresh timeline to show new snapshot
                    self._timeline.set_snapshots(self._snapshots)
                    self._timeline.update()
                    return
            # Still not found - clear info panel
            self._info_title.setText("No snapshot selected")
            self._info_id.setText("-")
            self._info_branch.setText("-")
            self._info_parent.setText("-")
            self._info_created.setText("-")
    
    def _on_node_double_clicked(self, snapshot_id: str):
        """Handle node double-click (restore)."""
        self._on_restore_requested(snapshot_id)

    def _on_rename_requested(self, snapshot_id: str, current_description: str):
        """Handle rename request - show dialog to edit description."""
        new_desc, ok = QtWidgets.QInputDialog.getText(
            self,
            "Rename Snapshot",
            "New description:",
            text=current_description
        )

        if not ok or not new_desc or new_desc == current_description:
            return

        if not self._session:
            logger.error("Cannot rename checkpoint: no CommandSession available")
            return

        result = self._session.execute(
            "rename_checkpoint",
            checkpoint_id=snapshot_id,
            description=new_desc,
        )
        if result.success:
            self._reload_snapshots()
        else:
            logger.error(f"rename_checkpoint failed: {getattr(result, 'error', 'unknown error')}")

    def _on_restore_requested(self, snapshot_id: str):
        """Handle restore request - asks for permission via signal.

        The connected handler must call callback(True) to approve or callback(False) to deny.
        If no handler is connected, defaults to denial (safe default).
        """
        if self._restore_in_progress:
            return

        if not self._session:
            logger.error("Cannot restore checkpoint: no CommandSession available")
            return

        callback_invoked = [False]

        def on_permission_granted(approved: bool):
            callback_invoked[0] = True
            if approved:
                self._do_restore(snapshot_id)

        # Emit the signal - handlers will call the callback
        self.restore_permission_requested.emit(snapshot_id, on_permission_granted)

        # Check if callback was invoked (synchronously)
        if not callback_invoked[0]:
            # No permission handler connected — restore directly
            self._do_restore(snapshot_id)

    def _do_restore(self, snapshot_id: str):
        """Actually perform the restore (internal use only)."""
        self._restore_in_progress = True

        try:
            result = self._session.execute(
                "restore_checkpoint",
                snapshot_id=snapshot_id,
            )
            if result.success and result.data:
                new_snapshot_id = result.data.get("new_snapshot_id")
                logger.debug(f"restore_checkpoint succeeded: {new_snapshot_id}")
            else:
                logger.error(f"restore_checkpoint failed: {getattr(result, 'error', 'unknown error')}")
                return

            # The command service restructured the datastore. Reload via query
            # spine so the widget reflects the canonical state.
            self._reload_snapshots()
            self._last_snapshot_id = new_snapshot_id
            self._timeline.set_snapshots(self._snapshots)
            self._timeline.update()
            self._on_node_selected(new_snapshot_id)
        finally:
            self._restore_in_progress = False
    
    def _on_create_snapshot(self):
        """Handle create checkpoint request - asks for permission via signal."""
        text, ok = QtWidgets.QInputDialog.getText(
            self,
            "Create Checkpoint",
            "Description:"
        )
        if not ok or not text:
            return

        # Use callback with timeout to detect if any handler responded
        callback_invoked = [False]  # Use list for mutable closure
        
        def on_permission_granted(approved: bool):
            callback_invoked[0] = True
            if approved:
                self._do_create_checkpoint(text)
            else:
                pass  # Checkpoint denied
        
        # Emit the signal - handlers will call the callback
        self.checkpoint_permission_requested.emit(text, on_permission_granted)

        # Check if callback was invoked (synchronously)
        if not callback_invoked[0]:
            # No permission handler connected — create checkpoint directly
            self._do_create_checkpoint(text)

    def _on_dump_state(self):
        """Dump timeline workspace state to terminal."""
        logger.info("[DUMP] Timeline Workspace State")
        logger.info(f"Total snapshots: {len(self._snapshots)}")
        logger.info(f"Current branch: {self._current_branch}")
        logger.info(f"Last snapshot ID: {self._last_snapshot_id}")
        logger.info(f"Has command session: {self._session is not None}")
        logger.info("Snapshots:")
        for i, snap in enumerate(self._snapshots):
            parent = snap.parent_id or "(root)"
            logger.info(f"  {i}: {snap.snapshot_id} | {snap.description!r}")
            logger.info(f"      branch={snap.branch_name}, parent={parent}")
            logger.info(f"      created={snap.created_at}")

    def _do_create_checkpoint(self, description: str, branch: Optional[str] = None) -> str:
        """Actually create checkpoint (internal use only - requires permission first)."""
        logger.info(f"_do_create_checkpoint() called: description={description!r}, branch={branch}")
        branch = branch or self._current_branch

        if not self._session:
            logger.error("Cannot create checkpoint: no CommandSession available")
            return ""

        # Reload to get the latest main-branch leaf.
        self._reload_snapshots()
        parent_id = self._get_main_branch_leaf()
        logger.debug(f"parent_id={parent_id}")

        result = self._session.execute(
            "create_checkpoint",
            description=description,
            parent_id=parent_id,
            branch=branch,
        )
        if not result.success or not result.data:
            logger.error(f"create_checkpoint failed: {getattr(result, 'error', 'unknown error')}")
            return ""

        snapshot_id = result.data.get("snapshot_id")
        logger.debug(f"create_checkpoint succeeded: {snapshot_id}")

        # Reload so the new snapshot (including is_delta metadata) appears.
        self._reload_snapshots()
        if self._snapshots:
            self._last_snapshot_id = self._snapshots[-1].snapshot_id

        self._timeline.set_snapshots(self._snapshots)
        self._timeline.update()
        logger.info(f"_do_create_checkpoint() COMPLETE: snapshot_id={snapshot_id}")

        return snapshot_id or ""

    # Public API for MainWindow integration
    def get_timeline_widget(self) -> TimelineWidget:
        """Get the underlying timeline widget."""
        return self._timeline

    def set_engine(self, engine: Optional[TimelineEngine]):
        """Set the timeline engine (for real data)."""
        if engine:
            self._timeline._engine = engine
            self._timeline.set_snapshots(engine.get_snapshots())

    def set_session(self, session: Any) -> None:
        """Set the command session for bus-based checkpoint/restore.

        The panel calls session.execute(...) and session.query(...) on the bus.
        """
        self._session = session
        self._subscribe_to_events()
        self._reload_snapshots()
        self._start_polling()

    def _subscribe_to_events(self) -> None:
        """Subscribe to checkpoint lifecycle events so the panel refreshes."""
        if not self._session:
            return
        for topic in (
            "event.workspace.checkpoint_created",
            "event.workspace.checkpoint_restored",
            "event.workspace.checkpoint_renamed",
            "event.workspace.checkpoint_deleted",
        ):
            try:
                self._session.subscribe(topic, self._on_checkpoint_event)
            except Exception as e:
                logger.warning(f"Could not subscribe to {topic}: {e}")

    def _on_checkpoint_event(self, event: Any) -> None:
        """Refresh snapshots when checkpoint events arrive on the bus.

        The event may be delivered from the transport client's polling thread, so
        the actual UI refresh is scheduled on the Qt event loop to avoid unsafe
        cross-thread widget updates.
        """
        QtCore.QTimer.singleShot(0, self._reload_snapshots)

    def _start_polling(self) -> None:
        """Start periodic refresh when the panel has a session and is visible."""
        if self._session and self.isVisible() and not self._refresh_timer.isActive():
            self._refresh_timer.start(self._poll_interval_ms)

    def _stop_polling(self) -> None:
        """Stop periodic refresh."""
        if self._refresh_timer.isActive():
            self._refresh_timer.stop()

    def _poll_datastore(self) -> None:
        """Periodic poll: refresh if the canonical datastore changed."""
        if not self._session or not self.isVisible():
            self._stop_polling()
            return
        self._reload_snapshots()

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        """Refresh and start polling when the dock becomes visible."""
        super().showEvent(event)
        self._debounced_reload()
        self._start_polling()

    def hideEvent(self, event: QtGui.QHideEvent) -> None:
        """Stop polling when the dock is hidden to save resources."""
        super().hideEvent(event)
        self._stop_polling()

    def _snapshot_lists_equal(
        self, a: List[SnapshotInfo], b: List[SnapshotInfo]
    ) -> bool:
        """Return True if two snapshot lists have the same IDs in the same order."""
        if len(a) != len(b):
            return False
        return all(s1.snapshot_id == s2.snapshot_id for s1, s2 in zip(a, b))

    def _reload_snapshots(self) -> None:
        """Load snapshots via the query spine and convert to widget model."""
        if not self._session:
            logger.debug("No command session; snapshots remain empty")
            self._snapshots = []
            self._last_snapshot_id = None
            self._timeline.set_snapshots(self._snapshots)
            self._timeline.update()
            return

        try:
            dtos = self._session.query("timeline_snapshots") or []
        except Exception as e:
            logger.error(f"timeline_snapshots query failed: {e}")
            dtos = []

        new_snapshots = [self._dto_to_snapshot_info(dto) for dto in dtos]
        if self._snapshot_lists_equal(self._snapshots, new_snapshots):
            return

        self._snapshots = new_snapshots
        if self._snapshots:
            self._last_snapshot_id = self._snapshots[-1].snapshot_id
        else:
            self._last_snapshot_id = None

        self._timeline.set_snapshots(self._snapshots)
        self._timeline.update()

    @staticmethod
    def _dto_to_snapshot_info(dto: TimelineSnapshotDTO) -> SnapshotInfo:
        """Convert a neutral timeline DTO into a widget SnapshotInfo."""
        try:
            snap_type = SnapshotType(dto["snapshot_type"])
        except ValueError:
            snap_type = SnapshotType.MANUAL

        created_at: datetime
        try:
            created_at = datetime.fromisoformat(dto["created_at"])
        except ValueError:
            created_at = datetime.now(timezone.utc)

        return SnapshotInfo(
            snapshot_id=dto["snapshot_id"],
            parent_id=dto["parent_id"],
            description=dto["description"],
            branch_name=dto["branch_name"] or "main",
            created_at=created_at,
            type=snap_type,
            is_delta=dto.get("is_delta", False),
        )

    # Public API for MainWindow integration


class TimelineDockManager:
    """Manages timeline dock widget in MainWindow.
    
    Usage in MainWindow:
        self._timeline_manager = TimelineDockManager(self)
        # ... later ...
        self._timeline_manager.show_timeline()
    """
    
    def __init__(self, main_window: QtWidgets.QMainWindow):
        self._main_window = main_window
        
        # Create panel immediately (not lazily) so Qt can save/restore dock state
        self._panel = TimelinePanel(main_window)
        main_window.addDockWidget(
            QtCore.Qt.DockWidgetArea.RightDockWidgetArea,
            self._panel
        )
        self._panel.hide()  # Start hidden
        
        # Connect visibility change to sync toggle action
        self._panel.visibilityChanged.connect(self._sync_toggle_action)
        
        # Create toggle action for menu (similar to QDockWidget.toggleViewAction)
        self._toggle_action = QtGui.QAction("Timeline", main_window)
        self._toggle_action.setCheckable(True)
        self._toggle_action.triggered.connect(self._on_toggle_triggered)
    
    def _on_toggle_triggered(self, checked: bool):
        """Handle menu toggle action."""
        if checked:
            self.show_timeline()
        else:
            self.hide_timeline()
    
    def _sync_toggle_action(self):
        """Sync toggle action state with panel visibility."""
        is_visible = self._panel is not None and self._panel.isVisible()
        self._toggle_action.setChecked(is_visible)
    
    def show_timeline(self):
        """Show the timeline dock panel."""
        self._panel.show()
        self._panel.raise_()
        self._toggle_action.setChecked(True)
    
    def hide_timeline(self):
        """Hide the timeline dock panel."""
        self._panel.hide()
        self._toggle_action.setChecked(False)
    
    def toggle_timeline(self):
        """Toggle timeline visibility."""
        if self._panel and self._panel.isVisible():
            self.hide_timeline()
        else:
            self.show_timeline()
    
    def toggleViewAction(self) -> QtGui.QAction:
        """Return the toggle action for menu integration (QDockWidget-compatible API)."""
        return self._toggle_action
    
    def get_panel(self) -> Optional[TimelinePanel]:
        """Get the timeline panel (if created)."""
        return self._panel


# For testing standalone
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)

    window = QtWidgets.QMainWindow()
    window.setWindowTitle("Timeline Panel Test")
    window.resize(1000, 700)

    # Add a dummy central widget
    central = QtWidgets.QWidget()
    central_layout = QtWidgets.QVBoxLayout(central)
    central_layout.addWidget(QtWidgets.QLabel("Main workspace area"))
    window.setCentralWidget(central)

    # Add timeline. In a real integration the panel receives a CommandSession
    # through set_session(); here it displays mock data.
    manager = TimelineDockManager(window)
    panel = manager.get_panel()
    if panel is not None:
        panel._init_mock_data()
    manager.show_timeline()

    window.show()
    sys.exit(app.exec())
