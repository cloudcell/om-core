"""lib_timelinegui — GUI-only timeline components.

Runtime-neutral: may import lib_timeline/contracts.py but must not
import lib_runtime/ or lib_command/ internals.
"""

from __future__ import annotations

from lib_timelinegui.panel import TimelinePanel, TimelineDockManager

__all__ = ["TimelinePanel", "TimelineDockManager"]
