"""UI event topics for GUI event bus integration.

StrEnum to prevent typo-driven bugs in GUI event handling.
Raw strings should not be used in GUI code except in this file.

B.1 scope: ui.refresh, ui.grid.refresh, ui.status.update
Deferred: ui.view.refresh, ui.view.patch, ui.dirty.changed
"""

from enum import StrEnum


class UITopic(StrEnum):
    REFRESH = "ui.refresh"
    GRID_REFRESH = "ui.grid.refresh"
    STATUS_UPDATE = "ui.status.update"
    # Deferred to later phases:
    # VIEW_REFRESH = "ui.view.refresh"
    # VIEW_PATCH = "ui.view.patch"
    # DIRTY_CHANGED = "ui.dirty.changed"