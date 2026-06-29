"""
lib_gui.menubuilder - A flexible menu/toolbar builder system for OpenM

Provides draggable tile-based UI for building custom toolbars and menus,
with JSON persistence and standardized command execution.
"""

from .models import ButtonDef, ToolbarConfig, CommandSpec, CategoryDef
from .persistence import save_toolbar, load_toolbar, list_saved_toolbars
from .widgets import DraggableTile, TileDropZone, CategoryPanel

__all__ = [
    "ButtonDef",
    "ToolbarConfig",
    "CommandSpec",
    "CategoryDef",
    "save_toolbar",
    "load_toolbar",
    "list_saved_toolbars",
    "DraggableTile",
    "TileDropZone",
    "CategoryPanel",
]
