"""lib_contracts.events — client-facing event topic constants.

GUI and other clients subscribe to these topics through the approved
client-facing event interface.
"""

# Domain / application events that other clients may observe
EVENT_WORKSPACE_DIRTY_CHANGED = "event.workspace.dirty_changed"
EVENT_DIMENSION_RENAMED = "event.dimension.renamed"
EVENT_DIMENSION_ITEM_RENAMED = "event.dimension_item.renamed"
EVENT_VIEW_CREATED = "event.view.created"
EVENT_VIEW_ACTIVATED = "event.view.activated"
EVENT_VIEW_DELETED = "event.view.deleted"
EVENT_CUBE_DELETED = "event.cube.deleted"
EVENT_ENGINE_SWITCHED = "event.engine.switched"

# UI-only topics (coordinator events, not meant for cross-client observation)
# These should use GUI-local signals/channels rather than the bus.
UI_STATUS_UPDATE = "ui.status_update"
UI_REFRESH = "ui.refresh"
UI_GRID_REFRESH = "ui.grid_refresh"

__all__ = [
    "EVENT_WORKSPACE_DIRTY_CHANGED",
    "EVENT_DIMENSION_RENAMED",
    "EVENT_DIMENSION_ITEM_RENAMED",
    "EVENT_VIEW_CREATED",
    "EVENT_VIEW_ACTIVATED",
    "EVENT_VIEW_DELETED",
    "EVENT_CUBE_DELETED",
    "EVENT_ENGINE_SWITCHED",
    "UI_STATUS_UPDATE",
    "UI_REFRESH",
    "UI_GRID_REFRESH",
]
