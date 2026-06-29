"""Timeline Panel - Dock widget wrapper for TimelineWidget.

Provides TimelineDockManager for MainWindow integration.
Uses lib_timelinewidget for the actual timeline visualization.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, List, Callable

# Add parent directory to path so lib_timelinewidget can be found without installation
_file_path = Path(__file__).resolve()
_project_root = _file_path.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from PySide6 import QtCore, QtGui, QtWidgets

from lib_timelinewidget import TimelineWidget, SnapshotInfo, SnapshotType
from lib_timelinewidget.engine import TimelineEngine
from lib_timeline.controllers import TimelineController, create_controller, MockProvider
from datetime import datetime, timezone
import uuid
import logging

logger = logging.getLogger(__name__)

# Feature flag: Set to True to use real datastore persistence
# When False, uses mock provider (backward compatible, no persistence)
USE_REAL_DATASTORE = True

from lib_utils.paths import OM_SESSIONS_DIR

# Session storage directory (used when USE_REAL_DATASTORE=True)
SESSIONS_DIR = OM_SESSIONS_DIR

def _generate_session_file() -> Path:
    """Generate a unique session file path with UUID to prevent collisions."""
    session_id = str(uuid.uuid4())
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    return SESSIONS_DIR / f"timeline_session_{session_id}.sqlite"


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
        logger.info(f"USE_REAL_DATASTORE={USE_REAL_DATASTORE}")
        logger.info(f"SESSIONS_DIR={SESSIONS_DIR}")
        
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
        self._session_file: Optional[Path] = None  # Current session file path
        self._payload_generator: Optional[Callable] = None  # Stored for controller recreation
        self._payload_restorer: Optional[Callable] = None  # Stored for controller recreation
        self._session: Any = None  # CommandSession for bus-based checkpoint/restore
        
        # Initialize controller (mock or real datastore based on feature flag)
        logger.info("creating controller...")
        if USE_REAL_DATASTORE:
            self._session_file = _generate_session_file()
            logger.info(f"New session file: {self._session_file}")
        self._controller: TimelineController = create_controller(
            use_real_datastore=USE_REAL_DATASTORE,
            session_file=self._session_file
        )
        logger.info(f"controller created: type={type(self._controller).__name__}")
        
        self._init_session_start()  # Create initial snapshot

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
        if USE_REAL_DATASTORE and self._session is None:
            logger.info(
                "Timeline panel has no command session yet; direct controller "
                "fallback snapshots need payload callbacks to capture workspace state."
            )
    
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
        """Initialize session - load existing snapshots from datastore.

        The panel only *displays* snapshots; it does not create them.
        Snapshot creation is the composition root's responsibility
        (lib_runtime.app_host / runtime_factory), which respects the
        persistence mode config.
        """
        logger.debug("_init_session_start() called")
        self._current_branch = "main"

        existing_snapshots = self._controller.load_snapshots()
        if existing_snapshots:
            logger.info(f"Loaded {len(existing_snapshots)} existing snapshots from datastore")
            self._snapshots = existing_snapshots
            self._last_snapshot_id = existing_snapshots[-1].snapshot_id
        else:
            logger.info("No existing snapshots — timeline starts empty")
            self._snapshots = []
            self._last_snapshot_id = None

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
        # Capture callbacks from the old controller before discarding it.
        # The panel's own _payload_generator may be None because
        # set_payload_callbacks() is owned by TimelineService, not the panel.
        old_controller = getattr(self, '_controller', None)
        old_engine = getattr(old_controller, '_engine', None)
        old_generator = getattr(old_engine, '_payload_generator', None) if old_engine else None
        old_restorer = getattr(old_engine, '_payload_restorer', None) if old_engine else None

        # Generate a new unique session file to avoid collisions
        if USE_REAL_DATASTORE:
            self._session_file = _generate_session_file()
            logger.info(f"New session file for new session: {self._session_file}")
            # Recreate controller with new session file
            self._controller = create_controller(
                use_real_datastore=USE_REAL_DATASTORE,
                session_file=self._session_file
            )
            logger.info("Controller recreated for new session")

            # Reapply stored payload callbacks if available
            if old_generator and old_restorer:
                logger.info("Reapplying stored payload callbacks...")
                self._controller.set_payload_callbacks(old_generator, old_restorer)
                # Also mirror onto panel storage so future recreations can find them
                self._payload_generator = old_generator
                self._payload_restorer = old_restorer
            elif self._payload_generator and self._payload_restorer:
                logger.info("Reapplying panel-stored payload callbacks...")
                self._controller.set_payload_callbacks(
                    self._payload_generator,
                    self._payload_restorer,
                )

        self._init_session_start()

        # In manual mode the timeline starts empty; in auto mode the composition
        # root (app_host / runtime_factory) creates the Session Start on startup.
        # Either way, _init_session_start() only loads existing snapshots.
        # The user must explicitly create a checkpoint to add the first snapshot.

        self._timeline.set_snapshots(self._snapshots)
        self._timeline.update()

    def start_new_session(self):
        """Start a new session (legacy - use _do_start_new_session with permission)."""
        self._do_start_new_session()

    def switch_to_workspace_session(
        self,
        workspace_path: str | None = None,
        *,
        session_file: Path | None = None,
    ) -> None:
        """Switch to a workspace-specific session file so timeline persists across restarts.

        Args:
            workspace_path: Path to the workspace JSON file. Session file is derived
                as ``<SESSIONS_DIR>/<workspace_stem>.timeline.openm``.
            session_file: Optional explicit session file path (overrides derivation
                from workspace_path). Used in remote mode where workspace file path
                is not known, but a deterministic session file is still needed.
        """
        if not USE_REAL_DATASTORE:
            return

        if session_file is None and workspace_path is not None:
            workspace_file = Path(workspace_path)
            # Keep timeline sessions in the canonical sessions directory, not
            # scattered next to workspace files in the project root.
            SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
            session_file = SESSIONS_DIR / f"{workspace_file.stem}.timeline.sqlite"

        if session_file is None:
            return

        if self._session_file == session_file:
            # Already using this session file — just reload snapshots
            self._init_session_start()
            self._timeline.set_snapshots(self._snapshots)
            self._timeline.update()
            return

        self._session_file = session_file
        logger.info(f"Switching to workspace session file: {self._session_file}")

        # Capture callbacks from the old controller before discarding it
        old_controller = getattr(self, '_controller', None)
        old_engine = getattr(old_controller, '_engine', None)
        old_generator = getattr(old_engine, '_payload_generator', None) if old_engine else None
        old_restorer = getattr(old_engine, '_payload_restorer', None) if old_engine else None

        # Recreate controller with the workspace-specific session file
        self._controller = create_controller(
            use_real_datastore=USE_REAL_DATASTORE,
            session_file=self._session_file
        )
        logger.info(f"Controller recreated for workspace session: {type(self._controller).__name__}")

        # Reapply stored payload callbacks if available
        if old_generator and old_restorer:
            self._controller.set_payload_callbacks(old_generator, old_restorer)
            self._payload_generator = old_generator
            self._payload_restorer = old_restorer
        elif self._payload_generator and self._payload_restorer:
            self._controller.set_payload_callbacks(
                self._payload_generator,
                self._payload_restorer,
            )

        self._init_session_start()

        # Backfill Session Start with actual workspace state if callbacks are wired
        self._update_session_start_payload()

        self._timeline.set_snapshots(self._snapshots)
        self._timeline.update()

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

    def _do_create_checkpoint(self, description: str, branch: Optional[str] = None) -> str:
        """Actually create checkpoint (internal use only - requires permission first)."""
        branch = branch or self._current_branch

        # Always extend from the main branch leaf, not the restored point
        parent_id = self._get_main_branch_leaf()

        snapshot = SnapshotInfo(
            snapshot_id=self._generate_id(),
            description=description,
            branch_name=branch,
            parent_id=parent_id,
            created_at=datetime.now(timezone.utc),
            type=SnapshotType.MANUAL
        )

        self._snapshots.append(snapshot)
        self._last_snapshot_id = snapshot.snapshot_id

        # Update timeline display
        self._timeline.set_snapshots(self._snapshots)
        self._timeline.update()

        return snapshot.snapshot_id

    def create_checkpoint(self, description: str, branch: Optional[str] = None) -> str:
        """Create a new checkpoint/snapshot (legacy - use _do_create_checkpoint with permission).

        Args:
            description: User description for this checkpoint
            branch: Branch name (defaults to current branch)

        Returns:
            The new snapshot ID
        """
        return self._do_create_checkpoint(description, branch)
    
    def _generate_id(self) -> str:
        """Generate unique snapshot ID (full UUID)."""
        return str(uuid.uuid4())
    
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
            # Snapshot not in our list - sync from controller and try again
            # (This can happen if controller created snapshots internally)
            self._snapshots = self._controller.load_snapshots()
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

        if ok and new_desc and new_desc != current_description:
            # CRITICAL: Sync from controller first to get complete snapshot list
            # (controller may have created "Restored from..." snapshots we don't know about)
            self._snapshots = self._controller.load_snapshots()

            # Use controller for persistence (renames in datastore if enabled)
            self._controller.rename_snapshot(snapshot_id, new_desc)

            # Find and update the snapshot
            for snap in self._snapshots:
                if snap.snapshot_id == snapshot_id:
                    # Update description
                    snap.description = new_desc
                    # Refresh timeline
                    self._timeline.set_snapshots(self._snapshots)
                    self._timeline.update()
                    break

    def _on_restore_requested(self, snapshot_id: str):
        """Handle restore request - asks for permission via signal.

        The connected handler must call callback(True) to approve or callback(False) to deny.
        If no handler is connected, defaults to denial (safe default).
        """
        if self._restore_in_progress:
            return

        callback_invoked = [False]
        
        def on_permission_granted(approved: bool):
            callback_invoked[0] = True
            if approved:
                self._do_restore(snapshot_id)
            else:
                pass  # Restore denied
        
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
            new_snapshot_id: Optional[str] = None

            # Bus-based path: execute through command session so lifecycle events
            # are published on the message bus.
            if self._session:
                logger.debug("executing restore via command session...")
                result = self._session.execute(
                    "restore_checkpoint",
                    snapshot_id=snapshot_id,
                )
                if result.success and result.data:
                    new_snapshot_id = result.data.get("new_snapshot_id")
                    logger.debug(f"restore command succeeded: {new_snapshot_id}")
                else:
                    logger.error(f"restore command failed: {getattr(result, 'error', 'unknown error')}")
            else:
                # Fallback: direct controller call (standalone / tests)
                logger.debug("calling controller.restore_snapshot() directly...")
                new_snapshot_id = self._controller.restore_snapshot(snapshot_id)
                logger.debug(f"controller.restore_snapshot() returned: {new_snapshot_id}")
            
            if new_snapshot_id:
                # Controller succeeded - sync snapshots and then do branch restructuring
                # via timeline widget (which handles the visual branch folding WITHOUT creating duplicate)
                logger.info(f"Controller restore succeeded: {new_snapshot_id}")
                self._snapshots = self._controller.load_snapshots()
                # Debug: show what we loaded
                logger.info(f"Loaded {len(self._snapshots)} snapshots:")
                for s in self._snapshots:
                    logger.info(f"  {s.snapshot_id[:8]}: branch={s.branch_name}, desc={s.description[:30]}")

                # Capture original state before restructure mutates the snapshots in place
                original_state = {
                    s.snapshot_id: {"branch_name": s.branch_name, "parent_id": s.parent_id}
                    for s in self._snapshots
                }

                self._timeline.set_snapshots(self._snapshots)
                # Call restructure_for_restore to move future snapshots to alt branch
                # This does NOT create a new "Restored from" snapshot (controller already did that)
                # Pass new_snapshot_id so it knows which snapshot to keep on main
                self._timeline.restructure_for_restore(snapshot_id, new_snapshot_id)
                # Update datastore with new branch and parent assignments so they're persisted
                logger.info("Updating datastore with new branch and parent assignments...")
                for snap in self._timeline.get_snapshots():
                    state = original_state.get(snap.snapshot_id, {})
                    if snap.branch_name != state.get("branch_name"):
                        self._controller.update_snapshot_branch(snap.snapshot_id, snap.branch_name)
                    if snap.parent_id != state.get("parent_id"):
                        self._controller.update_snapshot_parent(snap.snapshot_id, snap.parent_id)
            else:
                # Controller failed - surface error to user if possible, then fall back to widget
                if self._session and hasattr(self._session, 'context') and self._session.context:
                    try:
                        self._session.context.status("Checkpoint restore failed — check console for details")
                    except Exception:
                        pass
                logger.warning("Controller restore failed, using widget fallback")
                new_snapshot_id = self._timeline.restore_to_snapshot(snapshot_id)

            if new_snapshot_id:
                self._last_snapshot_id = new_snapshot_id
                # Refresh display with updated snapshots (including branch restructuring)
                self._snapshots = self._timeline.get_snapshots()
                self._timeline.set_snapshots(self._snapshots)
                self._timeline.update()
                # Select the newly created snapshot so info panel shows its details
                self._on_node_selected(new_snapshot_id)
            else:
                pass  # Restore failed
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
        logger.info(f"Controller type: {type(self._controller).__name__}")
        logger.info(f"Session file: {getattr(self._controller, 'get_session_file', lambda: 'N/A')()}")
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

        # CRITICAL: Sync from controller first to get complete snapshot list
        # (timeline widget may have stale data)
        self._snapshots = self._controller.load_snapshots()
        logger.info(f"synced {len(self._snapshots)} snapshots from controller")

        # Always extend from the main branch leaf, not the restored point
        parent_id = self._get_main_branch_leaf()
        logger.debug(f"parent_id={parent_id}")

        snapshot_id: Optional[str] = None

        # Bus-based path: execute through command session so lifecycle events
        # are published on the message bus.
        if self._session:
            logger.debug("executing checkpoint via command session...")
            result = self._session.execute(
                "create_checkpoint",
                description=description,
                parent_id=parent_id,
                branch=branch,
            )
            if result.success and result.data:
                snapshot_id = result.data.get("snapshot_id")
                logger.debug(f"checkpoint command succeeded: {snapshot_id}")
            else:
                logger.error(f"checkpoint command failed: {getattr(result, 'error', 'unknown error')}")
        else:
            # Fallback: direct controller call (standalone / tests)
            logger.debug("calling controller.create_snapshot() directly...")
            snapshot_id = self._controller.create_snapshot(
                description=description,
                parent_id=parent_id
            )
            logger.debug(f"controller.create_snapshot() returned: {snapshot_id}")
        
        if not snapshot_id:
            # Fallback to local creation if controller failed
            logger.warning("controller failed, using fallback local generation")
            snapshot_id = self._generate_id()
        
        # Get the full snapshot from controller to include is_delta and other metadata
        created_snapshot = self._controller.get_snapshot(snapshot_id)
        if created_snapshot:
            snapshot = created_snapshot
        else:
            # Fallback: create local SnapshotInfo (won't have is_delta)
            snapshot = SnapshotInfo(
                snapshot_id=snapshot_id,
                description=description,
                branch_name=branch,
                parent_id=parent_id,
                created_at=datetime.now(timezone.utc),
                type=SnapshotType.MANUAL
            )

        self._snapshots.append(snapshot)
        self._last_snapshot_id = snapshot.snapshot_id

        # Update timeline display
        self._timeline.set_snapshots(self._snapshots)
        self._timeline.update()
        logger.info(f"_do_create_checkpoint() COMPLETE: snapshot_id={snapshot_id}")

        return snapshot.snapshot_id

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

        The panel calls session.execute(...) instead of executor.execute(...).
        """
        self._session = session

    def get_controller(self) -> TimelineController:
        """Get the timeline controller."""
        return self._controller

    def set_payload_callbacks(self, generator: Callable, restorer: Callable):
        """Set callbacks for workspace serialization/restoration.
        
        Required when USE_REAL_DATASTORE=True to enable actual
        workspace state capture and restoration.
        
        Args:
            generator: Callable that returns workspace state dict
            restorer: Callable that restores workspace from dict
        """
        logger.info("set_payload_callbacks() called")
        logger.debug(f"generator={generator}, restorer={restorer}")
        
        # Store callbacks for reapplication when controller is recreated
        self._payload_generator = generator
        self._payload_restorer = restorer
        
        self._controller.set_payload_callbacks(generator, restorer)
        
        # Update Session Start snapshot with actual workspace state if it exists
        # and was created with an empty payload
        self._update_session_start_payload()
        
        logger.info("set_payload_callbacks() complete - workspace WILL be saved to snapshots")
    
    def _update_session_start_payload(self):
        """Update Session Start snapshot with current workspace state."""
        if not self._snapshots:
            return

        # Find Session Start snapshot
        session_start = None
        for snap in self._snapshots:
            if snap.description == "Session Start":
                session_start = snap
                break

        if not session_start:
            return

        # Check if the controller has a payload generator wired
        engine = getattr(self._controller, '_engine', None)
        payload_generator = getattr(engine, '_payload_generator', None) if engine else None
        if payload_generator is None:
            logger.debug("No payload generator available; skipping Session Start backfill")
            return

        logger.info("Updating Session Start payload with current workspace state...")
        try:
            payload = payload_generator()
            if payload:
                self._controller.update_snapshot_payload(session_start.snapshot_id, payload)
                logger.info("Session Start payload updated")
            else:
                logger.debug("Payload generator returned empty dict; skipping update")
        except Exception as e:
            logger.error(f"Could not update Session Start: {e}")


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
    import sys

    app = QtWidgets.QApplication(sys.argv)

    window = QtWidgets.QMainWindow()
    window.setWindowTitle("Timeline Panel Test")
    window.resize(1000, 700)

    # Add a dummy central widget
    central = QtWidgets.QWidget()
    central_layout = QtWidgets.QVBoxLayout(central)
    central_layout.addWidget(QtWidgets.QLabel("Main workspace area"))
    window.setCentralWidget(central)

    # Add timeline
    manager = TimelineDockManager(window)
    manager.show_timeline()

    # Install permission handlers with DEBUG mode
    # Set DEBUG_ANYTHING_GOES = True to auto-approve all operations
    from lib_timeline.config import install_debug_handlers, TimelineConfig
    TimelineConfig.DEBUG_ANYTHING_GOES = True  # Enable debug mode
    install_debug_handlers(manager.get_panel(), window)

    window.show()
    sys.exit(app.exec())
