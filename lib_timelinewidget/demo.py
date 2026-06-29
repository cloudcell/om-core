"""Demo application for lib_timelinewidget.

Run with: python -m lib_timelinewidget.demo
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QLabel, QTextEdit, QScrollArea
)
from PySide6.QtCore import Qt

from lib_timelinewidget import TimelineWidget, SnapshotInfo, SnapshotType


def parse_session_file(file_path: str) -> list:
    """Parse session file to get snapshot data.
    
    Format: snapshot_id | parent_id | branch | type | timestamp | description | cells | tags
    """
    snapshots = []
    
    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            parts = line.split(' | ')
            if len(parts) < 6:
                continue
            
            snap_id, parent_id, branch, snap_type, timestamp, description = parts[:6]
            
            # Parse timestamp
            try:
                dt = datetime.strptime(timestamp, "%Y%m%d %H:%M:%S")
            except:
                dt = datetime.now(timezone.utc)
            
            snapshots.append(SnapshotInfo(
                snapshot_id=snap_id,
                parent_id=parent_id if parent_id else None,
                description=description,
                branch_name=branch,
                created_at=dt,
                type=SnapshotType.MANUAL,
            ))
    
    return snapshots


class DemoWindow(QMainWindow):
    """Demo window showing timeline widget capabilities."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Timeline Widget Demo")
        
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        
        # Info label
        self.info_label = QLabel("Select a node to see details")
        self.info_label.setStyleSheet("padding: 10px; background: #f0f0f0;")
        layout.addWidget(self.info_label)
        
        # Timeline widget - load real session data
        self.timeline = TimelineWidget()
        session_file = Path(__file__).parent / "demo" / "session_20260418_043345.txt"
        if session_file.exists():
            self.timeline.set_snapshots(parse_session_file(str(session_file)))
        else:
            self.timeline.set_snapshots(self._create_demo_data())
        self.timeline.node_selected.connect(self._on_node_selected)
        self.timeline.node_double_clicked.connect(self._on_node_double_clicked)
        
        # Context menu signals (API)
        self.timeline.restore_requested.connect(self._on_restore)
        self.timeline.rename_requested.connect(self._on_rename)
        self.timeline.create_snapshot_requested.connect(self._on_create_snapshot)
        
        # Scroll area for timeline with standard Qt scrollbars
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.timeline)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        layout.addWidget(self.scroll, stretch=1)
        
        # Session info
        self.session_info = QLabel("Session: session_20260418_043345.txt | 23 snapshots | 6 branches")
        self.session_info.setStyleSheet("padding: 5px; color: #666; font-size: 11px;")
        layout.addWidget(self.session_info)
    
    def _create_demo_data(self) -> list:
        """Create demo snapshot data."""
        now = datetime.now(timezone.utc)
        
        return [
            SnapshotInfo(
                snapshot_id="root",
                description="Session Start",
                branch_name="main",
                created_at=now,
            ),
            SnapshotInfo(
                snapshot_id="setup",
                parent_id="root",
                description="Initial Setup",
                branch_name="main",
                created_at=now + timedelta(minutes=5),
            ),
            SnapshotInfo(
                snapshot_id="experiment_1",
                parent_id="setup",
                description="Experiment 1",
                branch_name="experiment",
                created_at=now + timedelta(minutes=10),
            ),
            SnapshotInfo(
                snapshot_id="experiment_2",
                parent_id="experiment_1",
                description="Experiment 2",
                branch_name="experiment",
                created_at=now + timedelta(minutes=15),
            ),
            SnapshotInfo(
                snapshot_id="main_1",
                parent_id="setup",
                description="Continue Main",
                branch_name="main",
                created_at=now + timedelta(minutes=12),
            ),
            SnapshotInfo(
                snapshot_id="main_2",
                parent_id="main_1",
                description="Save Progress",
                branch_name="main",
                created_at=now + timedelta(minutes=20),
            ),
            SnapshotInfo(
                snapshot_id="hotfix",
                parent_id="main_1",
                description="Hotfix Branch",
                branch_name="hotfix",
                created_at=now + timedelta(minutes=18),
            ),
        ]
    
    def _create_linear_data(self) -> list:
        """Create simple linear chain."""
        snapshots = []
        prev = None
        now = datetime.now(timezone.utc)
        
        for i in range(10):
            snap_id = f"snap_{i}"
            snapshots.append(SnapshotInfo(
                snapshot_id=snap_id,
                parent_id=prev,
                description=f"Step {i + 1}",
                branch_name="main",
                created_at=now + timedelta(minutes=i * 5),
            ))
            prev = snap_id
        
        return snapshots
    
    def _create_branched_data(self) -> list:
        """Create data with multiple branches."""
        now = datetime.now(timezone.utc)
        
        return [
            SnapshotInfo("root", description="Root", created_at=now),
            SnapshotInfo("m1", parent_id="root", description="Main 1", branch_name="main", created_at=now + timedelta(minutes=5)),
            SnapshotInfo("m2", parent_id="m1", description="Main 2", branch_name="main", created_at=now + timedelta(minutes=10)),
            SnapshotInfo("a1", parent_id="root", description="Alt A", branch_name="alt-a", created_at=now + timedelta(minutes=7)),
            SnapshotInfo("a2", parent_id="a1", description="Alt A2", branch_name="alt-a", created_at=now + timedelta(minutes=12)),
            SnapshotInfo("b1", parent_id="root", description="Alt B", branch_name="alt-b", created_at=now + timedelta(minutes=8)),
            SnapshotInfo("b2", parent_id="b1", description="Alt B2", branch_name="alt-b", created_at=now + timedelta(minutes=14)),
        ]
    
    def _create_complex_data(self) -> list:
        """Create complex nested branch structure."""
        now = datetime.now(timezone.utc)
        
        snapshots = [
            # Main line
            SnapshotInfo("s1", description="Start", created_at=now),
            SnapshotInfo("s2", parent_id="s1", description="Checkpoint 1", branch_name="main", created_at=now + timedelta(minutes=5)),
            SnapshotInfo("s3", parent_id="s2", description="Checkpoint 2", branch_name="main", created_at=now + timedelta(minutes=10)),
            
            # First branch from s2
            SnapshotInfo("e1", parent_id="s2", description="Exp 1 Start", branch_name="experiment", created_at=now + timedelta(minutes=6)),
            SnapshotInfo("e2", parent_id="e1", description="Exp 1 Progress", branch_name="experiment", created_at=now + timedelta(minutes=9)),
            SnapshotInfo("e3", parent_id="e2", description="Exp 1 Result", branch_name="experiment", created_at=now + timedelta(minutes=14)),
            
            # Nested branch from experiment
            SnapshotInfo("n1", parent_id="e2", description="Nested Branch", branch_name="nested", created_at=now + timedelta(minutes=11)),
            SnapshotInfo("n2", parent_id="n1", description="Nested Result", branch_name="nested", created_at=now + timedelta(minutes=13)),
            
            # Second branch from s2
            SnapshotInfo("f1", parent_id="s2", description="Fix Start", branch_name="fix", created_at=now + timedelta(minutes=7)),
            SnapshotInfo("f2", parent_id="f1", description="Fix Complete", branch_name="fix", created_at=now + timedelta(minutes=12)),
        ]
        
        return snapshots
    
    def _on_node_selected(self, snapshot_id: str):
        """Handle node selection."""
        self.info_label.setText(f"Selected: {snapshot_id}")
    
    def _on_node_double_clicked(self, snapshot_id: str):
        """Handle node double click."""
        self.info_label.setText(f"Double-clicked: {snapshot_id}")
    
    def _on_restore(self, snapshot_id: str):
        """Handle restore request from context menu."""
        self.info_label.setText(f"RESTORE requested to: {snapshot_id}")
    
    def _on_rename(self, snapshot_id: str, current_description: str):
        """Handle rename request from context menu."""
        self.info_label.setText(f"RENAME requested for: {snapshot_id} (currently: {current_description})")
    
    def _on_create_snapshot(self):
        """Handle create snapshot request from context menu."""
        self.info_label.setText("CREATE SNAPSHOT requested (from current node)")
    
    def _show_linear(self):
        """Show linear chain demo."""
        self.timeline.set_snapshots(self._create_linear_data())
        self.info_label.setText("Linear chain: 10 nodes in sequence")
    
    def _show_branched(self):
        """Show branched demo."""
        self.timeline.set_snapshots(self._create_branched_data())
        self.info_label.setText("Multiple branches from single node")
    
    def _show_complex(self):
        """Show complex demo."""
        self.timeline.set_snapshots(self._create_complex_data())
        self.info_label.setText("Complex: nested branches")
    
    def _clear(self):
        """Clear timeline."""
        self.timeline.set_snapshots([])
        self.info_label.setText("Timeline cleared")


def main():
    """Run demo application."""
    app = QApplication(sys.argv)
    
    # Set application style
    app.setStyle("Fusion")
    
    window = DemoWindow()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
