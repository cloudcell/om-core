"""Tests for TimelineWidget.

Uses pytest-qt for Qt testing. Install with: pip install pytest-qt
"""

import pytest
from datetime import datetime, timedelta

from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QApplication

from lib_timelinewidget import TimelineWidget, SnapshotInfo, SnapshotType


@pytest.fixture
def widget(qtbot):
    """Create a TimelineWidget for testing."""
    widget = TimelineWidget()
    qtbot.addWidget(widget)
    widget.resize(600, 400)
    return widget


class TestTimelineWidgetBasic:
    """Basic widget tests."""
    
    def test_creation(self, widget):
        """Test widget can be created."""
        assert widget is not None
        assert widget.selected_id() is None
    
    def test_set_snapshots_empty(self, widget):
        """Test setting empty snapshot list."""
        widget.set_snapshots([])
        assert widget.selected_id() is None
        # Should not crash
    
    def test_set_snapshots_single(self, widget):
        """Test setting single snapshot."""
        snapshots = [
            SnapshotInfo(
                snapshot_id="snap_001",
                description="Root",
                branch_name="main",
            )
        ]
        widget.set_snapshots(snapshots)
        assert widget.selected_id() is None
    
    def test_set_snapshots_linear_chain(self, widget):
        """Test setting linear chain of snapshots."""
        snapshots = [
            SnapshotInfo(
                snapshot_id="snap_001",
                description="Root",
                branch_name="main",
            ),
            SnapshotInfo(
                snapshot_id="snap_002",
                parent_id="snap_001",
                description="Child",
                branch_name="main",
            ),
            SnapshotInfo(
                snapshot_id="snap_003",
                parent_id="snap_002",
                description="Grandchild",
                branch_name="main",
            ),
        ]
        widget.set_snapshots(snapshots)
        # Should build main path successfully
        assert widget.selected_id() is None
    
    def test_selection(self, widget):
        """Test selection API."""
        snapshots = [
            SnapshotInfo(snapshot_id="snap_001", description="First"),
            SnapshotInfo(snapshot_id="snap_002", description="Second"),
        ]
        widget.set_snapshots(snapshots)
        
        # Select first
        widget.set_selected("snap_001")
        assert widget.selected_id() == "snap_001"
        
        # Select second
        widget.set_selected("snap_002")
        assert widget.selected_id() == "snap_002"
        
        # Clear selection
        widget.set_selected(None)
        assert widget.selected_id() is None


class TestTimelineWidgetBranches:
    """Tests for branch visualization."""
    
    def test_simple_branch(self, widget):
        """Test displaying a simple branch."""
        snapshots = [
            SnapshotInfo(
                snapshot_id="root",
                description="Root",
                branch_name="main",
            ),
            SnapshotInfo(
                snapshot_id="main_child",
                parent_id="root",
                description="Main branch",
                branch_name="main",
            ),
            SnapshotInfo(
                snapshot_id="alt_child",
                parent_id="root",
                description="Alt branch",
                branch_name="experiment",
            ),
        ]
        widget.set_snapshots(snapshots)
        # Should render main path + branch indicator + alt path
        assert widget.selected_id() is None
    
    def test_deep_branch(self, widget):
        """Test branch with multiple nodes."""
        snapshots = [
            SnapshotInfo(
                snapshot_id="root",
                description="Root",
                branch_name="main",
            ),
            SnapshotInfo(
                snapshot_id="main_1",
                parent_id="root",
                description="Main 1",
                branch_name="main",
            ),
            SnapshotInfo(
                snapshot_id="alt_1",
                parent_id="root",
                description="Alt 1",
                branch_name="alt",
            ),
            SnapshotInfo(
                snapshot_id="alt_2",
                parent_id="alt_1",
                description="Alt 2",
                branch_name="alt",
            ),
            SnapshotInfo(
                snapshot_id="alt_3",
                parent_id="alt_2",
                description="Alt 3",
                branch_name="alt",
            ),
        ]
        widget.set_snapshots(snapshots)
        # Should handle nested branch path
        assert widget.selected_id() is None
    
    def test_multiple_branches_from_same_node(self, widget):
        """Test multiple branches diverging from one node."""
        snapshots = [
            SnapshotInfo(
                snapshot_id="root",
                description="Root",
                branch_name="main",
            ),
            SnapshotInfo(
                snapshot_id="main_child",
                parent_id="root",
                description="Main",
                branch_name="main",
            ),
            SnapshotInfo(
                snapshot_id="exp_1",
                parent_id="root",
                description="Experiment 1",
                branch_name="exp-1",
            ),
            SnapshotInfo(
                snapshot_id="exp_2",
                parent_id="root",
                description="Experiment 2",
                branch_name="exp-2",
            ),
        ]
        widget.set_snapshots(snapshots)
        # Should show both branch indicators


class TestTimelineWidgetSignals:
    """Tests for widget signals."""
    
    def test_node_selected_signal(self, widget, qtbot):
        """Test node_selected signal is emitted."""
        snapshots = [
            SnapshotInfo(
                snapshot_id="snap_001",
                description="Root",
                branch_name="main",
            ),
            SnapshotInfo(
                snapshot_id="snap_002",
                parent_id="snap_001",
                description="Child",
                branch_name="main",
            ),
        ]
        widget.set_snapshots(snapshots)
        widget.show()  # Widget must be shown for proper geometry
        qtbot.waitExposed(widget)  # Wait for widget to be exposed
        
        # Click on first real node (spine at x=40)
        # If TIMELINE_DEBUG_ROOT_FORK is True, meta-fork is at row 0 (y=26) and root is at row 1 (y=60)
        # If TIMELINE_DEBUG_ROOT_FORK is False, root is at row 0 (y=26)
        from lib_timelinewidget.timelineconf import TIMELINE_DEBUG_ROOT_FORK
        click_y = 60 if TIMELINE_DEBUG_ROOT_FORK else 26
        with qtbot.waitSignal(widget.node_selected, timeout=500) as blocker:
            qtbot.mouseClick(widget, Qt.LeftButton, pos=QPoint(40, click_y))
        
        assert blocker.args[0] == "snap_001"
    
    def test_node_double_clicked_signal(self, widget):
        """Test node_double_clicked signal."""
        # Similar to above but for double click
        pass  # Placeholder


class TestTimelineWidgetEdgeCases:
    """Edge case tests."""
    
    def test_missing_parent(self, widget):
        """Test handling snapshot with non-existent parent."""
        snapshots = [
            SnapshotInfo(
                snapshot_id="orphan",
                parent_id="nonexistent",
                description="Orphan node",
                branch_name="main",
            ),
        ]
        widget.set_snapshots(snapshots)
        # Should not crash
        assert widget.selected_id() is None
    
    def test_circular_reference(self, widget):
        """Test handling circular parent references."""
        # This would require creating a loop, which should be prevented
        # by the visited set in _build_branch_path
        snapshots = [
            SnapshotInfo(
                snapshot_id="a",
                parent_id="b",
                description="A",
                branch_name="main",
            ),
            SnapshotInfo(
                snapshot_id="b",
                parent_id="a",
                description="B",
                branch_name="main",
            ),
        ]
        widget.set_snapshots(snapshots)
        # Should not infinite loop
        assert widget.selected_id() is None
    
    def test_all_branches_no_main(self, widget):
        """Test tree with no 'main' branch."""
        snapshots = [
            SnapshotInfo(
                snapshot_id="root",
                description="Root",
                branch_name="alpha",
            ),
            SnapshotInfo(
                snapshot_id="child",
                parent_id="root",
                description="Child",
                branch_name="alpha",
            ),
        ]
        widget.set_snapshots(snapshots)
        # Should pick first as main path
        assert widget.selected_id() is None
    
    def test_timestamp_formatting(self, widget):
        """Test time formatting helper."""
        dt = datetime(2024, 6, 15, 14, 30, 45)
        formatted = widget._format_time(dt)
        assert formatted == "2024-Jun-15 14:30:45"


class TestTimelineWidgetPerformance:
    """Performance tests."""
    
    def test_large_tree(self, widget):
        """Test with many snapshots."""
        snapshots = []
        prev_id = None
        
        for i in range(100):
            snap_id = f"snap_{i:04d}"
            snapshots.append(SnapshotInfo(
                snapshot_id=snap_id,
                parent_id=prev_id,
                description=f"Snapshot {i}",
                branch_name="main",
            ))
            prev_id = snap_id
        
        # Should handle 100 nodes without issues
        widget.set_snapshots(snapshots)
        assert widget.selected_id() is None
    
    def test_many_branches(self, widget):
        """Test with many branches from single node."""
        snapshots = [
            SnapshotInfo(
                snapshot_id="root",
                description="Root",
                branch_name="main",
            ),
            SnapshotInfo(
                snapshot_id="main_child",
                parent_id="root",
                description="Main",
                branch_name="main",
            ),
        ]
        
        # Add 20 alternate branches
        for i in range(20):
            snapshots.append(SnapshotInfo(
                snapshot_id=f"alt_{i}",
                parent_id="root",
                description=f"Alt branch {i}",
                branch_name=f"branch-{i}",
            ))
        
        widget.set_snapshots(snapshots)
        # Should render all branches
        assert widget.selected_id() is None
