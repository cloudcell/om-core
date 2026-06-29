"""Bus monitor overlay for the REPL TUI.

Provides a transient two-pane overlay (topic checklist + message log)
that replaces the output pane while active.
"""

from .overlay import BusMonitorOverlay

__all__ = ["BusMonitorOverlay"]
