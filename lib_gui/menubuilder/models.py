"""
Data models for the menu builder system.
Defines button definitions, command specifications, and toolbar configurations.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum, auto
from typing import Callable, Any
from PySide6 import QtCore


class CommandType(Enum):
    """Types of commands that can be executed."""
    FILE = auto()             # File operations (new, open, save, etc.)
    FORMAT = auto()           # Text/cell formatting
    NAVIGATION = auto()       # View navigation
    CALCULATION = auto()      # Recalc, formula operations
    DATA = auto()             # Import, export, copy, paste
    MODEL = auto()            # Create dimensions, cubes, etc.
    VIEW = auto()             # Toggle panels, zoom
    CUSTOM = auto()           # User-defined commands


@dataclass
class CommandSpec:
    """Specification for a command that can be bound to a button."""
    id: str                           # Unique command identifier
    name: str                         # Human-readable name
    command_type: CommandType         # Category of command
    shortcut: str | None = None       # Keyboard shortcut (e.g., "Ctrl+B")
    parameters: dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "command_type": self.command_type.name,
            "shortcut": self.shortcut,
            "parameters": self.parameters,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> CommandSpec:
        return cls(
            id=data["id"],
            name=data["name"],
            command_type=CommandType[data["command_type"]],
            shortcut=data.get("shortcut"),
            parameters=data.get("parameters", {}),
            description=data.get("description", ""),
        )


@dataclass
class ButtonDef:
    """Definition of a toolbar button."""
    id: str                           # Unique button ID
    label: str                        # Display text
    icon: str                         # Icon name (Tabler icon)
    command: CommandSpec              # Associated command
    category: str                     # Category for grouping
    tooltip: str = ""
    color: str = "#F3F4F6"           # Background color hint
    enabled: bool = True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "icon": self.icon,
            "command": self.command.to_dict(),
            "category": self.category,
            "tooltip": self.tooltip,
            "color": self.color,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ButtonDef:
        return cls(
            id=data["id"],
            label=data["label"],
            icon=data["icon"],
            command=CommandSpec.from_dict(data["command"]),
            category=data["category"],
            tooltip=data.get("tooltip", ""),
            color=data.get("color", "#F3F4F6"),
            enabled=data.get("enabled", True),
        )


@dataclass
class CategoryDef:
    """Definition of a button category/group."""
    id: str
    name: str                         # Display name
    color: str                        # Color theme for this category
    buttons: list[ButtonDef] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "color": self.color,
            "buttons": [b.to_dict() for b in self.buttons],
        }

    @classmethod
    def from_dict(cls, data: dict) -> CategoryDef:
        return cls(
            id=data["id"],
            name=data["name"],
            color=data["color"],
            buttons=[ButtonDef.from_dict(b) for b in data.get("buttons", [])],
        )


@dataclass
class ToolbarConfig:
    """Complete configuration for a custom toolbar."""
    name: str
    description: str = ""
    buttons: list[ButtonDef] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: QtCore.QDateTime.currentDateTime().toString("yyyy-MM-dd hh:mm:ss"))
    modified_at: str = field(default_factory=lambda: QtCore.QDateTime.currentDateTime().toString("yyyy-MM-dd hh:mm:ss"))

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "buttons": [b.to_dict() for b in self.buttons],
            "created_at": self.created_at,
            "modified_at": self.modified_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ToolbarConfig:
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            buttons=[ButtonDef.from_dict(b) for b in data.get("buttons", [])],
            created_at=data.get("created_at", ""),
            modified_at=data.get("modified_at", ""),
        )


# Predefined command library - standardized commands across the application
COMMAND_LIBRARY: dict[str, CommandSpec] = {
    # File commands
    "file_new": CommandSpec("file_new", "New", CommandType.FILE, "Ctrl+N", {}, "Create new file"),
    "file_open": CommandSpec("file_open", "Open…", CommandType.FILE, "Ctrl+O", {}, "Open existing file"),
    "file_save": CommandSpec("file_save", "Save…", CommandType.FILE, "Ctrl+S", {}, "Save current file"),

    # Formatting commands
    "format_bold": CommandSpec("format_bold", "Bold", CommandType.FORMAT, "Ctrl+B", {}, "Make text bold"),
    "format_italic": CommandSpec("format_italic", "Italic", CommandType.FORMAT, "Ctrl+I", {}, "Make text italic"),
    "format_underline": CommandSpec("format_underline", "Underline", CommandType.FORMAT, "Ctrl+U", {}, "Underline text"),
    "format_strike": CommandSpec("format_strike", "Strikethrough", CommandType.FORMAT, None, {}, "Strike through text"),
    "format_align_left": CommandSpec("format_align_left", "Align Left", CommandType.FORMAT, None, {"align": "left"}),
    "format_align_center": CommandSpec("format_align_center", "Align Center", CommandType.FORMAT, None, {"align": "center"}),
    "format_align_right": CommandSpec("format_align_right", "Align Right", CommandType.FORMAT, None, {"align": "right"}),

    # Navigation commands
    "nav_first": CommandSpec("nav_first", "First", CommandType.NAVIGATION, None, {}, "Go to first item"),
    "nav_prev": CommandSpec("nav_prev", "Previous", CommandType.NAVIGATION, None, {}, "Go to previous item"),
    "nav_next": CommandSpec("nav_next", "Next", CommandType.NAVIGATION, None, {}, "Go to next item"),
    "nav_last": CommandSpec("nav_last", "Last", CommandType.NAVIGATION, None, {}, "Go to last item"),

    # Calculation commands
    "calc_recalc": CommandSpec("calc_recalc", "Recalculate", CommandType.CALCULATION, "F9", {}, "Recalculate all"),
    "calc_recalc_visible": CommandSpec("calc_recalc_visible", "Recalculate Visible", CommandType.CALCULATION, "Shift+F9", {}, "Recalculate visible cells"),

    # Data commands
    "data_copy": CommandSpec("data_copy", "Copy", CommandType.DATA, "Ctrl+C", {}, "Copy selection"),
    "data_paste": CommandSpec("data_paste", "Paste", CommandType.DATA, "Ctrl+V", {}, "Paste"),
    "data_cut": CommandSpec("data_cut", "Cut", CommandType.DATA, "Ctrl+X", {}, "Cut selection"),

    # Model commands
    "model_new_dim": CommandSpec("model_new_dim", "New Dimension", CommandType.MODEL, None, {}, "Create new dimension"),
    "model_new_cube": CommandSpec("model_new_cube", "New Cube", CommandType.MODEL, None, {}, "Create new cube"),
    "model_add_item": CommandSpec("model_add_item", "Add Item", CommandType.MODEL, None, {}, "Add dimension item"),

    # View commands
    "view_zoom_in": CommandSpec("view_zoom_in", "Zoom In", CommandType.VIEW, "Ctrl++", {}),
    "view_zoom_out": CommandSpec("view_zoom_out", "Zoom Out", CommandType.VIEW, "Ctrl+-", {}),
    "view_zoom_reset": CommandSpec("view_zoom_reset", "Reset Zoom", CommandType.VIEW, "Ctrl+0", {}),
}


# Predefined button library - reusable button definitions
BUTTON_LIBRARY: dict[str, ButtonDef] = {
    # File
    "new": ButtonDef("new", "New", "file-plus", COMMAND_LIBRARY["file_new"], "file", "Create new file", "#E5E7EB"),
    "open": ButtonDef("open", "Open", "folder-open", COMMAND_LIBRARY["file_open"], "file", "Open existing file", "#E5E7EB"),
    "save": ButtonDef("save", "Save", "device-floppy", COMMAND_LIBRARY["file_save"], "file", "Save current file", "#E5E7EB"),

    # Formatting
    "bold": ButtonDef("bold", "Bold", "bold", COMMAND_LIBRARY["format_bold"], "formatting", "Make text bold", "#FEF3C7"),
    "italic": ButtonDef("italic", "Italic", "italic", COMMAND_LIBRARY["format_italic"], "formatting", "Make text italic", "#FEF3C7"),
    "underline": ButtonDef("underline", "Underline", "underline", COMMAND_LIBRARY["format_underline"], "formatting", "Underline text", "#FEF3C7"),
    "strike": ButtonDef("strike", "Strike", "strikethrough", COMMAND_LIBRARY["format_strike"], "formatting", "Strike through", "#FEF3C7"),
    "align_left": ButtonDef("align_left", "Left", "align-left", COMMAND_LIBRARY["format_align_left"], "formatting", "Align left", "#FEF3C7"),
    "align_center": ButtonDef("align_center", "Center", "align-center", COMMAND_LIBRARY["format_align_center"], "formatting", "Align center", "#FEF3C7"),
    "align_right": ButtonDef("align_right", "Right", "align-right", COMMAND_LIBRARY["format_align_right"], "formatting", "Align right", "#FEF3C7"),

    # Navigation
    "first": ButtonDef("first", "First", "chevrons-left", COMMAND_LIBRARY["nav_first"], "navigation", "Go to first", "#DBEAFE"),
    "prev": ButtonDef("prev", "Prev", "chevron-left", COMMAND_LIBRARY["nav_prev"], "navigation", "Go to previous", "#DBEAFE"),
    "next": ButtonDef("next", "Next", "chevron-right", COMMAND_LIBRARY["nav_next"], "navigation", "Go to next", "#DBEAFE"),
    "last": ButtonDef("last", "Last", "chevrons-right", COMMAND_LIBRARY["nav_last"], "navigation", "Go to last", "#DBEAFE"),

    # Calculation
    "recalc": ButtonDef("recalc", "Recalc", "calculator", COMMAND_LIBRARY["calc_recalc"], "calculation", "Recalculate all (F9)", "#D1FAE5"),
    "recalc_vis": ButtonDef("recalc_vis", "Recalc Vis", "calculator-off", COMMAND_LIBRARY["calc_recalc_visible"], "calculation", "Recalculate visible (Shift+F9)", "#D1FAE5"),

    # Data
    "copy": ButtonDef("copy", "Copy", "copy", COMMAND_LIBRARY["data_copy"], "data", "Copy (Ctrl+C)", "#FCE7F3"),
    "paste": ButtonDef("paste", "Paste", "clipboard", COMMAND_LIBRARY["data_paste"], "data", "Paste (Ctrl+V)", "#FCE7F3"),
    "cut": ButtonDef("cut", "Cut", "scissors", COMMAND_LIBRARY["data_cut"], "data", "Cut (Ctrl+X)", "#FCE7F3"),

    # Model
    "new_dim": ButtonDef("new_dim", "New Dim", "folder-plus", COMMAND_LIBRARY["model_new_dim"], "model", "New dimension", "#F5D0FE"),
    "new_cube": ButtonDef("new_cube", "New Cube", "cube-plus", COMMAND_LIBRARY["model_new_cube"], "model", "New cube", "#F5D0FE"),
    "add_item": ButtonDef("add_item", "Add Item", "list-plus", COMMAND_LIBRARY["model_add_item"], "model", "Add item", "#F5D0FE"),

    # View
    "zoom_in": ButtonDef("zoom_in", "Zoom In", "zoom-in", COMMAND_LIBRARY["view_zoom_in"], "view", "Zoom in", "#FED7AA"),
    "zoom_out": ButtonDef("zoom_out", "Zoom Out", "zoom-out", COMMAND_LIBRARY["view_zoom_out"], "view", "Zoom out", "#FED7AA"),
    "zoom_reset": ButtonDef("zoom_reset", "Reset", "zoom-reset", COMMAND_LIBRARY["view_zoom_reset"], "view", "Reset zoom", "#FED7AA"),
}


# Category definitions with their buttons
DEFAULT_CATEGORIES: list[CategoryDef] = [
    CategoryDef("file", "File", "#E5E7EB", [
        BUTTON_LIBRARY["new"],
        BUTTON_LIBRARY["open"],
        BUTTON_LIBRARY["save"],
    ]),
    CategoryDef("formatting", "Formatting", "#FEF3C7", [
        BUTTON_LIBRARY["bold"],
        BUTTON_LIBRARY["italic"],
        BUTTON_LIBRARY["underline"],
        BUTTON_LIBRARY["strike"],
        BUTTON_LIBRARY["align_left"],
        BUTTON_LIBRARY["align_center"],
        BUTTON_LIBRARY["align_right"],
    ]),
    CategoryDef("navigation", "Navigation", "#DBEAFE", [
        BUTTON_LIBRARY["first"],
        BUTTON_LIBRARY["prev"],
        BUTTON_LIBRARY["next"],
        BUTTON_LIBRARY["last"],
    ]),
    CategoryDef("calculation", "Calculation", "#D1FAE5", [
        BUTTON_LIBRARY["recalc"],
        BUTTON_LIBRARY["recalc_vis"],
    ]),
    CategoryDef("data", "Data", "#FCE7F3", [
        BUTTON_LIBRARY["copy"],
        BUTTON_LIBRARY["paste"],
        BUTTON_LIBRARY["cut"],
    ]),
    CategoryDef("model", "Model", "#F5D0FE", [
        BUTTON_LIBRARY["new_dim"],
        BUTTON_LIBRARY["new_cube"],
        BUTTON_LIBRARY["add_item"],
    ]),
    CategoryDef("view", "View", "#FED7AA", [
        BUTTON_LIBRARY["zoom_in"],
        BUTTON_LIBRARY["zoom_out"],
        BUTTON_LIBRARY["zoom_reset"],
    ]),
]


# =============================================================================
# TOOLBOX SYSTEM - New data models for GUI toolbox and menu builder
# =============================================================================

class WidgetType(Enum):
    """Types of widgets that can be placed in menus/toolbars."""
    BUTTON = "button"           # Simple clickable button
    DROPDOWN = "dropdown"       # Dropdown menu (generic items)
    FONT_NAME = "font_name"     # Font name dropdown with font preview
    FONT_SIZE = "font_size"     # Font size dropdown
    COLOR_PICKER = "color"      # Color palette dropdown (cell fill)
    FONT_COLOR = "font_color"   # Font color picker button
    SEPARATOR = "separator"     # Visual separator
    SPACER = "spacer"          # Flexible space
    TOGGLE = "toggle"          # On/off toggle button
    SPLIT_BUTTON = "split"     # Button with dropdown arrow


class MenuLocation(Enum):
    """Locations where menu items can appear."""
    TOOLBAR = "toolbar"         # Main toolbar
    MENU_BAR = "menubar"        # Top menu bar (File, Edit, etc.)
    CONTEXT_MENU = "context"    # Right-click context menu
    RIBBON_TAB = "ribbon"       # Ribbon-style tab panel
    FLOATING_PALETTE = "palette"  # Detachable floating panel


@dataclass
class MenuItemDef:
    """Definition of a menu/toolbar item."""
    id: str                     # Unique identifier
    label: str                  # Display text
    widget_type: WidgetType     # Type of widget
    location: MenuLocation      # Where this appears

    # Visual properties
    icon: str | None = None     # Icon name (Tabler icon)
    tooltip: str = ""
    shortcut: str | None = None   # Keyboard shortcut
    color: str = "#F3F4F6"      # Background/indicator color
    enabled: bool = True
    visible: bool = True

    # For dropdowns/color pickers
    options: list[str] = field(default_factory=list)  # Dropdown options
    default_value: str = ""

    # Command/Action binding
    command_id: str | None = None           # Built-in command
    script_path: str | None = None          # Path to recorded script
    macro_id: str | None = None             # Reference to macro recorder entry

    # For menu hierarchy
    parent_menu: str | None = None          # Parent menu ID (for submenus)
    sort_order: int = 0                     # Position in menu

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "label": self.label,
            "widget_type": self.widget_type.value,
            "location": self.location.value,
            "icon": self.icon,
            "tooltip": self.tooltip,
            "shortcut": self.shortcut,
            "color": self.color,
            "enabled": self.enabled,
            "visible": self.visible,
            "options": self.options,
            "default_value": self.default_value,
            "command_id": self.command_id,
            "script_path": self.script_path,
            "macro_id": self.macro_id,
            "parent_menu": self.parent_menu,
            "sort_order": self.sort_order,
        }

    @classmethod
    def from_dict(cls, data: dict) -> MenuItemDef:
        """Create from dictionary."""
        return cls(
            id=data["id"],
            label=data["label"],
            widget_type=WidgetType(data["widget_type"]),
            location=MenuLocation(data["location"]),
            icon=data.get("icon"),
            tooltip=data.get("tooltip", ""),
            shortcut=data.get("shortcut"),
            color=data.get("color", "#F3F4F6"),
            enabled=data.get("enabled", True),
            visible=data.get("visible", True),
            options=data.get("options", []),
            default_value=data.get("default_value", ""),
            command_id=data.get("command_id"),
            script_path=data.get("script_path"),
            macro_id=data.get("macro_id"),
            parent_menu=data.get("parent_menu"),
            sort_order=data.get("sort_order", 0),
        )


@dataclass
class ToolboxConfig:
    """Complete GUI toolbox configuration."""
    version: str = "1.0"
    name: str = "default"

    # All menu items by ID
    items: dict[str, MenuItemDef] = field(default_factory=dict)

    # Toolbar layout (ordered list of item IDs)
    toolbar_layout: list[str] = field(default_factory=list)

    # Menu bar structure: {menu_name: [item_ids]}
    menubar_structure: dict[str, list[str]] = field(default_factory=dict)

    # Context menu for specific contexts
    context_menus: dict[str, list[str]] = field(default_factory=dict)

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    modified_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "version": self.version,
            "name": self.name,
            "items": {k: v.to_dict() for k, v in self.items.items()},
            "toolbar_layout": self.toolbar_layout,
            "menubar_structure": self.menubar_structure,
            "context_menus": self.context_menus,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ToolboxConfig:
        """Create from dictionary."""
        return cls(
            version=data.get("version", "1.0"),
            name=data.get("name", "default"),
            items={k: MenuItemDef.from_dict(v) for k, v in data.get("items", {}).items()},
            toolbar_layout=data.get("toolbar_layout", []),
            menubar_structure=data.get("menubar_structure", {}),
            context_menus=data.get("context_menus", {}),
            created_at=data.get("created_at", ""),
            modified_at=data.get("modified_at", ""),
        )
