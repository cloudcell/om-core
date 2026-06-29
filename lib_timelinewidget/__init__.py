"""Timeline Widget Library - Clean, modular timeline visualization.

A lightweight Qt-based timeline widget for visualizing snapshot trees
with branch support. Minimal dependencies, essential features only.

Example:
    from lib_timelinewidget import TimelineWidget, SnapshotInfo
    
    widget = TimelineWidget()
    widget.set_snapshots(snapshots)
    widget.node_selected.connect(on_node_selected)
"""

__version__ = "0.1.0"

from .models import SnapshotInfo, SnapshotType
from .engine import TimelineEngine
from .timeline_widget import TimelineWidget

__all__ = [
    "SnapshotInfo",
    "SnapshotType",
    "TimelineEngine",
    "TimelineWidget",
]
