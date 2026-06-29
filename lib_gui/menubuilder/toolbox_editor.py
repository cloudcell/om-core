"""
Live Menu/Toolbar Editor - Floating palette for editing the main GUI

When active:
- Main toolbar becomes a drop zone for widgets
- Toolbar items become selectable for macro assignment
- Changes apply in real-time
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6 import QtCore, QtGui, QtWidgets

from .models import (
    ToolboxConfig, MenuItemDef, WidgetType, MenuLocation,
    ButtonDef, CategoryDef, DEFAULT_CATEGORIES, COMMAND_LIBRARY, BUTTON_LIBRARY
)
from .persistence import save_toolbox_config, load_toolbox_config, DEFAULT_TOOLBOX_CONFIG_PATH
from .widgets import load_svg_icon

if TYPE_CHECKING:
    from lib_gui.app import MainWindow


class ToolboxEditorPalette(QtWidgets.QDockWidget):
    """
    Floating palette for editing menus and toolbars.
    When open, main window enters 'menu edit mode'.
    """
    
    # Signals to communicate with MainWindow
    widget_drag_started = QtCore.Signal(dict)  # widget data
    widget_dropped_on_toolbar = QtCore.Signal(str, dict)  # position, data
    close_requested = QtCore.Signal()
    
    def __init__(self, main_window: MainWindow, parent=None):
        super().__init__("Toolbox Editor", parent)
        self._main_window = main_window
        self._config = ToolboxConfig()
        self._is_editing = False
        self._selected_palette_tile = None  # Track selected tile for visual feedback
        
        self._setup_ui()
        self._load_config()
        
    def _setup_ui(self):
        """Set up the floating palette UI."""
        self.setFeatures(
            QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetFloatable |
            QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self.setAllowedAreas(QtCore.Qt.DockWidgetArea.LeftDockWidgetArea | 
                           QtCore.Qt.DockWidgetArea.RightDockWidgetArea)
        
        # Main container
        container = QtWidgets.QWidget()
        self.setWidget(container)
        
        layout = QtWidgets.QVBoxLayout(container)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)
        
        # === EDIT MODE INDICATOR ===
        self._edit_indicator = QtWidgets.QFrame()
        self._edit_indicator.setStyleSheet("""
            QFrame {
                background: #DBEAFE;
                border: 2px solid #3B82F6;
                border-radius: 6px;
                padding: 8px;
            }
        """)
        indicator_layout = QtWidgets.QHBoxLayout(self._edit_indicator)
        indicator_layout.setContentsMargins(8, 4, 8, 4)
        
        icon = QtWidgets.QLabel()
        icon.setPixmap(load_svg_icon("edit", 16, "#3B82F6").pixmap(16, 16))
        indicator_layout.addWidget(icon)
        
        text = QtWidgets.QLabel("EDIT MODE ACTIVE\nDrag to toolbar/menu")
        text.setStyleSheet("font-size: 11px; font-weight: 600; color: #1D4ED8;")
        indicator_layout.addWidget(text)
        indicator_layout.addStretch()
        
        layout.addWidget(self._edit_indicator)
        
        # === WIDGET PALETTE ===
        palette_header = QtWidgets.QLabel("Widget Palette")
        palette_header.setStyleSheet("font-size: 13px; font-weight: 600; color: #1F2937;")
        layout.addWidget(palette_header)
        
        # Scroll area for widgets
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: white; border: 1px solid #E5E7EB; border-radius: 6px;")
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self._scroll_content = QtWidgets.QWidget()
        self._scroll_layout = QtWidgets.QVBoxLayout(self._scroll_content)
        self._scroll_layout.setSpacing(8)
        self._scroll_layout.setContentsMargins(8, 8, 8, 8)
        self._scroll_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        
        self._build_widget_palette()
        
        scroll.setWidget(self._scroll_content)
        layout.addWidget(scroll)
        
        # === PROPERTIES PANEL (when item selected) ===
        self._props_header = QtWidgets.QLabel("Selected Item")
        self._props_header.setStyleSheet("font-size: 13px; font-weight: 600; color: #1F2937;")
        layout.addWidget(self._props_header)
        
        self._props_panel = PropertiesEditor(self)
        self._props_panel.item_updated.connect(self._on_item_updated)
        layout.addWidget(self._props_panel)
        
        # === ACTION BUTTONS ===
        btn_layout = QtWidgets.QHBoxLayout()
        
        self._save_btn = QtWidgets.QPushButton("Save")
        self._save_btn.setStyleSheet("""
            QPushButton {
                background: #3B82F6;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                color: white;
                font-weight: 500;
            }
            QPushButton:hover { background: #2563EB; }
        """)
        self._save_btn.clicked.connect(self._save_config)
        btn_layout.addWidget(self._save_btn)
        
        self._reset_btn = QtWidgets.QPushButton("Reset")
        self._reset_btn.setStyleSheet("""
            QPushButton {
                background: white;
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover { background: #F3F4F6; }
        """)
        self._reset_btn.clicked.connect(self._reset_config)
        btn_layout.addWidget(self._reset_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        # Status label
        self._status = QtWidgets.QLabel("Ready")
        self._status.setStyleSheet("font-size: 11px; color: #6B7280;")
        layout.addWidget(self._status)
        
    def _build_widget_palette(self):
        """Build the widget palette sections."""
        # Basic Widgets
        self._add_palette_section("Basic Widgets", [
            ("Button", "button", "cursor-pointer", WidgetType.BUTTON),
            ("Toggle", "toggle", "toggle-left", WidgetType.TOGGLE),
            ("Separator", "separator", "minus", WidgetType.SEPARATOR),
            ("Spacer", "spacer", "space", WidgetType.SPACER),
        ])
        
        # Input Widgets
        self._add_palette_section("Inputs", [
            ("Font Name", "font_name", "type", WidgetType.FONT_NAME),
            ("Font Size", "font_size", "type", WidgetType.FONT_SIZE),
            ("Font Color", "font_color", "type", WidgetType.FONT_COLOR),
            ("Cell Fill", "color", "paint-bucket", WidgetType.COLOR_PICKER),
        ])
        
        # Custom Buttons (with right-click duplicate/delete)
        self._add_custom_buttons_section()
        
        # Standard Buttons
        self._add_button_section()
        
        # Macros
        self._add_macro_section()
        
        self._scroll_layout.addStretch()
        
    def _add_palette_section(self, title: str, items: list[tuple]):
        """Add a section to the widget palette."""
        header = QtWidgets.QLabel(title)
        header.setStyleSheet("""
            font-size: 11px;
            font-weight: 600;
            color: #6B7280;
            padding: 8px 0 4px 0;
            border-bottom: 1px solid #E5E7EB;
        """)
        self._scroll_layout.addWidget(header)
        
        for label, widget_id, icon, widget_type in items:
            tile = DraggableWidgetTile(label, icon, widget_type)
            tile.drag_started.connect(self._on_widget_drag)
            tile.selected.connect(self._on_palette_tile_selected)
            self._scroll_layout.addWidget(tile)
            
    def _add_button_section(self):
        """Add standard buttons."""
        header = QtWidgets.QLabel("Standard Buttons")
        header.setStyleSheet("""
            font-size: 11px;
            font-weight: 600;
            color: #6B7280;
            padding: 8px 0 4px 0;
            border-bottom: 1px solid #E5E7EB;
        """)
        self._scroll_layout.addWidget(header)
        
        for btn_id, btn_def in list(BUTTON_LIBRARY.items())[:11]:
            tile = DraggableButtonTile(btn_def)
            tile.drag_started.connect(self._on_button_drag)
            tile.selected.connect(self._on_palette_tile_selected)
            self._scroll_layout.addWidget(tile)
            
    def _add_macro_section(self):
        """Add recorded macros."""
        self._macro_header = QtWidgets.QLabel("Recorded Macros")
        self._macro_header.setStyleSheet("""
            font-size: 11px;
            font-weight: 600;
            color: #6B7280;
            padding: 8px 0 4px 0;
            border-bottom: 1px solid #E5E7EB;
        """)
        self._scroll_layout.addWidget(self._macro_header)
        
        self._macro_container = QtWidgets.QWidget()
        self._macro_layout = QtWidgets.QVBoxLayout(self._macro_container)
        self._macro_layout.setSpacing(4)
        self._macro_layout.setContentsMargins(0, 0, 0, 0)
        
        self._refresh_macros()
        self._scroll_layout.addWidget(self._macro_container)
        
    def _refresh_macros(self):
        """Refresh the macro list from files in ~/.om/macros/"""
        while self._macro_layout.count():
            item = self._macro_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        from lib_utils.paths import OM_MACROS_DIR
        macros_dir = OM_MACROS_DIR
        if not macros_dir.exists():
            label = QtWidgets.QLabel("No macros recorded")
            label.setStyleSheet("color: #9CA3AF; font-size: 11px; font-style: italic;")
            self._macro_layout.addWidget(label)
            return

        macro_files = sorted(macros_dir.glob("*.openm"))
        for macro_file in macro_files:
            try:
                # Parse macro name from file header
                macro_name = macro_file.stem
                with open(macro_file) as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("# Macro:"):
                            macro_name = line.split(":", 1)[1].strip()
                            break
                        if not line.startswith("#") and line:
                            break
                
                macro_id = macro_file.stem
                tile = DraggableMacroTile(macro_id, macro_name)
                tile.drag_started.connect(self._on_macro_drag)
                tile.selected.connect(self._on_palette_tile_selected)
                self._macro_layout.addWidget(tile)
            except Exception:
                pass

        if self._macro_layout.count() == 0:
            label = QtWidgets.QLabel("No macros recorded")
            label.setStyleSheet("color: #9CA3AF; font-size: 11px; font-style: italic;")
            self._macro_layout.addWidget(label)

    def _add_custom_buttons_section(self):
        """Add Custom Buttons section with template and saved buttons."""
        header = QtWidgets.QLabel("Custom Buttons")
        header.setStyleSheet("""
            font-size: 11px;
            font-weight: 600;
            color: #6B7280;
            padding: 8px 0 4px 0;
            border-bottom: 1px solid #E5E7EB;
        """)
        self._scroll_layout.addWidget(header)

        # Container for custom button tiles
        self._custom_buttons_container = QtWidgets.QWidget()
        self._custom_buttons_layout = QtWidgets.QVBoxLayout(self._custom_buttons_container)
        self._custom_buttons_layout.setSpacing(4)
        self._custom_buttons_layout.setContentsMargins(0, 0, 0, 0)

        # Path for custom buttons config
        from lib_utils.paths import WIDGET_PALETTE_CUSTOM_PATH
        self._custom_buttons_path = WIDGET_PALETTE_CUSTOM_PATH

        # Load saved custom buttons
        self._load_custom_buttons()

        self._scroll_layout.addWidget(self._custom_buttons_container)

    def _load_custom_buttons(self):
        """Load custom buttons from config file."""
        # Add the template "Custom Button" (not deletable)
        template = MenuItemDef(
            id="custom_button_template",
            label="Custom Button",
            widget_type=WidgetType.BUTTON,
            location=MenuLocation.TOOLBAR,
            icon="box",
            command_id=None,
            macro_id=None,
            tooltip="Drag to toolbar, right-click to duplicate"
        )
        self._add_custom_button_tile(template, is_template=True)

        # Load saved custom buttons
        if self._custom_buttons_path.exists():
            try:
                with open(self._custom_buttons_path) as f:
                    data = json.load(f)
                    for item_data in data.get("custom_buttons", []):
                        item_def = MenuItemDef.from_dict(item_data)
                        self._add_custom_button_tile(item_def, is_template=False)
            except Exception:
                pass

    def _add_custom_button_tile(self, item_def: MenuItemDef, is_template: bool = False):
        """Add a custom button tile to the container."""
        tile = DraggableCustomButtonTile(item_def, is_template=is_template)
        tile.drag_started.connect(self._on_widget_drag)
        tile.selected.connect(self._on_palette_tile_selected)
        tile.duplicate_requested.connect(self._on_duplicate_custom_button)
        tile.delete_requested.connect(self._on_delete_custom_button)
        tile.rename_requested.connect(self._on_rename_custom_button)
        self._custom_buttons_layout.addWidget(tile)

    def _on_duplicate_custom_button(self, tile):
        """Duplicate a custom button."""
        original_def = tile.item_def

        # Create a new MenuItemDef with a new ID
        new_def = MenuItemDef(
            id=f"custom_{uuid.uuid4().hex[:8]}",
            label=f"{original_def.label} Copy",
            widget_type=original_def.widget_type,
            location=MenuLocation.TOOLBAR,
            icon=original_def.icon,
            command_id=original_def.command_id,
            macro_id=original_def.macro_id,
            tooltip=original_def.tooltip
        )

        # Add the new tile
        self._add_custom_button_tile(new_def, is_template=False)

        # Save the updated list
        self._save_custom_buttons()

        # Select the new tile
        new_tile = self._custom_buttons_layout.itemAt(self._custom_buttons_layout.count() - 1).widget()
        if new_tile:
            new_tile.set_selected()
            self._on_palette_tile_selected(new_def)

        self._status.setText(f"Duplicated: {new_def.label}")

    def _on_delete_custom_button(self, tile):
        """Delete a custom button."""
        if tile.is_template:
            return  # Should not happen due to UI check, but safety first

        # Remove from layout
        self._custom_buttons_layout.removeWidget(tile)
        tile.deleteLater()

        # Save the updated list
        self._save_custom_buttons()

        self._status.setText(f"Deleted: {tile.item_def.label}")

    def _on_rename_custom_button(self, tile):
        """Rename a custom button."""
        if tile.is_template:
            return

        print(f"[DEBUG-RENAME] Renaming tile: {tile}, label={tile.item_def.label}")
        print(f"[DEBUG-RENAME] item_def id: {id(tile.item_def)}")

        # Show input dialog for new name
        new_name, ok = QtWidgets.QInputDialog.getText(
            self,
            "Rename Custom Button",
            "Enter new name:",
            QtWidgets.QLineEdit.EchoMode.Normal,
            tile.item_def.label
        )

        if ok and new_name.strip():
            old_label = tile.item_def.label
            tile.item_def.label = new_name.strip()
            print(f"[DEBUG-RENAME] Changed label from '{old_label}' to '{new_name.strip()}'")
            # Update the tile UI
            layout = tile.layout()
            if layout:
                # Find and update the label widget (second widget in layout)
                for i in range(layout.count()):
                    widget = layout.itemAt(i).widget()
                    if isinstance(widget, QtWidgets.QLabel):
                        # Skip the icon label (has pixmap), update the text label
                        if widget.pixmap() is None or widget.pixmap().isNull():
                            widget.setText(new_name.strip())
                            print(f"[DEBUG-RENAME] Updated label widget text")
                            break
            # Select the renamed tile
            tile.set_selected()
            self._on_palette_tile_selected(tile.item_def)
            # Save the updated list
            self._save_custom_buttons()
            self._status.setText(f"Renamed to: {new_name.strip()}")

    def _save_custom_buttons(self):
        """Save custom buttons to config file."""
        try:
            # Ensure directory exists
            self._custom_buttons_path.parent.mkdir(parents=True, exist_ok=True)

            # Collect all non-template custom buttons
            custom_buttons = []
            for i in range(self._custom_buttons_layout.count()):
                widget = self._custom_buttons_layout.itemAt(i).widget()
                if isinstance(widget, DraggableCustomButtonTile) and not widget.is_template:
                    custom_buttons.append(widget.item_def.to_dict())

            # Save to file
            with open(self._custom_buttons_path, 'w') as f:
                json.dump({"custom_buttons": custom_buttons}, f, indent=2)

        except Exception:
            pass

    def _on_widget_drag(self, data: dict):
        """Handle widget drag start."""
        self.widget_drag_started.emit(data)
        
    def _on_button_drag(self, data: dict):
        """Handle button drag start."""
        self.widget_drag_started.emit(data)
        
    def _on_macro_drag(self, data: dict):
        """Handle macro drag start."""
        self.widget_drag_started.emit(data)
        
    def _on_palette_tile_selected(self, item: MenuItemDef):
        """Handle palette tile selection - update properties panel and visual state."""
        new_tile = self.sender()
        print(f"[DEBUG-PALETTE] Selected tile: {new_tile}, label={item.label}")

        # Clear previous selection styling
        if self._selected_palette_tile and self._selected_palette_tile != new_tile:
            try:
                if hasattr(self._selected_palette_tile, 'clear_selection'):
                    self._selected_palette_tile.clear_selection()
            except RuntimeError:
                # Widget was deleted, ignore
                pass

        # Track new selection (the tile widget)
        self._selected_palette_tile = new_tile

        # Update properties panel
        self._props_panel.set_item(item)
        self._status.setText(f"Selected: {item.label}")
        
    def _on_item_updated(self, item_id: str):
        """Handle item property update."""
        print(f"[DEBUG-SAVE] Item updated: {item_id}")
        item = self._config.items.get(item_id)
        if item:
            print(f"[DEBUG-SAVE] Config item at {id(item)}, macro_id: {item.macro_id}")
        else:
            print(f"[DEBUG-SAVE] WARNING: Item {item_id} not found in config!")
        self._status.setText(f"Updated: {item_id}")
        
        # Refresh the selected palette tile if it's a custom button (icon may have changed)
        if self._selected_palette_tile and isinstance(self._selected_palette_tile, DraggableCustomButtonTile):
            print(f"[DEBUG-SAVE] Refreshing custom button tile icon")
            self._selected_palette_tile.refresh_icon()
            # Also save custom buttons config since icon changed
            self._save_custom_buttons()
        
        # Auto-save config so changes (like macro_id) are persisted
        self._save_config()
        # Notify main window to refresh toolbar
        if hasattr(self._main_window, '_refresh_toolbar_from_config'):
            self._main_window._refresh_toolbar_from_config(self._config)
            
    def _load_config(self):
        """Load existing config."""
        try:
            if DEFAULT_TOOLBOX_CONFIG_PATH.exists():
                self._config = load_toolbox_config()
                self._status.setText(f"Loaded: {self._config.name}")
        except Exception as e:
            self._status.setText(f"Error: {e}")
            
    def _save_config(self):
        """Save configuration."""
        try:
            print(f"\n{'='*60}")
            print(f"[DEBUG-SAVE] SAVING CONFIG with {len(self._config.items)} items")
            print(f"{'='*60}")
            for item_id, item in self._config.items.items():
                has_macro = "***HAS MACRO***" if item.macro_id else ""
                print(f"[DEBUG-SAVE]   Item {item_id}: macro_id={item.macro_id} {has_macro}")
            save_toolbox_config(self._config)
            print(f"[DEBUG-SAVE] Saved to {DEFAULT_TOOLBOX_CONFIG_PATH}")
            print(f"{'='*60}\n")
            self._status.setText(f"Saved to {DEFAULT_TOOLBOX_CONFIG_PATH}")
        except Exception as e:
            print(f"[DEBUG-SAVE] Save failed: {e}")
            self._status.setText(f"Save failed: {e}")
            
    def _reset_config(self):
        """Reset to empty."""
        reply = QtWidgets.QMessageBox.question(
            self, "Reset",
            "Clear all custom menu items?",
            QtWidgets.QMessageBox.StandardButton.Yes | 
            QtWidgets.QMessageBox.StandardButton.No
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            self._config = ToolboxConfig()
            self._status.setText("Reset")
            
    def set_selected_item(self, item_id: str | None):
        """Set the currently selected toolbar item for editing."""
        print(f"\n{'='*60}")
        print(f"[DEBUG-SELECT] set_selected_item called with item_id={item_id}")
        print(f"{'='*60}")
        if item_id and item_id in self._config.items:
            item = self._config.items[item_id]
            print(f"[DEBUG-SELECT] Found config item {item_id}")
            print(f"[DEBUG-SELECT]   - label: {item.label}")
            print(f"[DEBUG-SELECT]   - command_id: {item.command_id}")
            print(f"[DEBUG-SELECT]   - macro_id: {item.macro_id}")
            print(f"[DEBUG-SELECT]   - object id: {id(item)}")
            self._props_panel.set_item(item)
            self._props_header.setText(f"Selected: {item.label}")
        else:
            print(f"[DEBUG-SELECT] Item {item_id} not found in config or None")
            self._props_panel.set_item(None)
            self._props_header.setText("Selected Item")
            
    def add_item_to_config(self, location: str, item: MenuItemDef, position: int = None):
        """Add an item to the configuration."""
        print(f"[DEBUG-ADD] Adding item {item.id} ({item.label}) to {location} at position {position}")
        self._config.items[item.id] = item
        if location == "toolbar":
            if item.id in self._config.toolbar_layout:
                current_index = self._config.toolbar_layout.index(item.id)
                if position is not None and 0 <= position <= len(self._config.toolbar_layout):
                    if current_index != position:
                        # Move existing item without duplicating it.
                        self._config.toolbar_layout.pop(current_index)
                        if position > current_index:
                            position -= 1
                        self._config.toolbar_layout.insert(position, item.id)
                        print(f"[DEBUG-ADD] Moved existing item to position {position}, now has {len(self._config.toolbar_layout)} items")
                    else:
                        print(f"[DEBUG-ADD] Item already present at position {position}, no duplicate added")
                else:
                    print(f"[DEBUG-ADD] Item already present in toolbar_layout, not appending duplicate")
            else:
                if position is not None and 0 <= position <= len(self._config.toolbar_layout):
                    self._config.toolbar_layout.insert(position, item.id)
                    print(f"[DEBUG-ADD] Inserted at position {position}, now has {len(self._config.toolbar_layout)} items")
                else:
                    self._config.toolbar_layout.append(item.id)
                    print(f"[DEBUG-ADD] Appended to toolbar_layout, now has {len(self._config.toolbar_layout)} items")
        self._status.setText(f"Added: {item.label}")

    def remove_item_from_config(self, location: str, item_id_or_label: str):
        """Remove an item from the configuration by id or label."""
        # First try direct id match
        item_id = item_id_or_label
        if item_id not in self._config.items:
            # Try to find by label
            for iid, item in self._config.items.items():
                if item.label == item_id_or_label:
                    item_id = iid
                    break
        if item_id in self._config.items:
            del self._config.items[item_id]
        if location == "toolbar" and item_id in self._config.toolbar_layout:
            self._config.toolbar_layout.remove(item_id)
        self._status.setText(f"Removed: {item_id_or_label}")

    def get_config(self) -> ToolboxConfig:
        """Get current toolbox configuration."""
        return self._config
        
    def closeEvent(self, event):
        """Emit signal when closed."""
        self.close_requested.emit()
        super().closeEvent(event)


# =============================================================================
# DRAGGABLE TILES
# =============================================================================

class FontColorIconWidget(QtWidgets.QWidget):
    """Custom icon widget showing 'A' with colored underline for palette."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(16, 16)
        
    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        
        rect = self.rect()
        
        # Draw "A"
        painter.setPen(QtGui.QPen(QtGui.QColor("#000000")))
        painter.setFont(QtGui.QFont("Arial", 10, QtGui.QFont.Weight.Bold))
        painter.drawText(rect, QtCore.Qt.AlignmentFlag.AlignCenter, "A")
        
        # Draw colored underline (black for automatic/default)
        painter.setPen(QtGui.QPen(QtGui.QColor("#000000"), 2))
        underline_y = rect.bottom() - 2
        painter.drawLine(2, underline_y, rect.width() - 2, underline_y)
        
        painter.end()


class CellFillIconWidget(QtWidgets.QWidget):
    """Custom icon widget showing paint bucket with colored bar for palette."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(16, 16)
        
    def paintEvent(self, event):
        from pathlib import Path
        from PySide6.QtSvg import QSvgRenderer
        
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        
        rect = self.rect()
        
        # Draw colored bar at bottom (light gray for default)
        painter.setPen(QtGui.QPen(QtGui.QColor("#e8f0fe"), 2))
        bar_y = rect.bottom() - 2
        painter.drawLine(2, bar_y, rect.width() - 2, bar_y)
        
        # Load and draw Lucide paint-bucket icon
        lucide_path = Path(__file__).parent.parent.parent / "assets" / "icons" / "lucide" / "icons"
        icon_file = lucide_path / "paint-bucket.svg"
        if icon_file.exists():
            renderer = QSvgRenderer(str(icon_file))
            icon_rect = QtCore.QRect(2, 1, rect.width() - 4, rect.height() // 2 + 1)
            renderer.render(painter, icon_rect)
        else:
            # Fallback: simple bucket outline
            painter.setPen(QtGui.QPen(QtGui.QColor("#5f6368"), 1))
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawRect(4, 3, rect.width() - 8, rect.height() // 2 - 1)
        
        painter.end()


class FontNameIconWidget(QtWidgets.QWidget):
    """Custom icon widget showing 'Aa' with underline for font name in palette."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(16, 16)
        
    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        
        rect = self.rect()
        
        # Draw "Aa" text
        painter.setPen(QtGui.QPen(QtGui.QColor("#000000")))
        painter.setFont(QtGui.QFont("Arial", 9, QtGui.QFont.Weight.Bold))
        painter.drawText(rect, QtCore.Qt.AlignmentFlag.AlignCenter, "Aa")
        
        # Draw underline
        painter.setPen(QtGui.QPen(QtGui.QColor("#000000"), 2))
        underline_y = rect.bottom() - 2
        painter.drawLine(2, underline_y, rect.width() - 2, underline_y)
        
        painter.end()


class FontSizeIconWidget(QtWidgets.QWidget):
    """Custom icon widget showing 'S' with size indicator for font size in palette."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(16, 16)
        
    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        
        rect = self.rect()
        
        # Draw "S" text (Size)
        painter.setPen(QtGui.QPen(QtGui.QColor("#000000")))
        painter.setFont(QtGui.QFont("Arial", 10, QtGui.QFont.Weight.Bold))
        painter.drawText(rect, QtCore.Qt.AlignmentFlag.AlignCenter, "S")
        
        # Draw small number "10" below
        painter.setFont(QtGui.QFont("Arial", 6))
        painter.setPen(QtGui.QPen(QtGui.QColor("#374151")))
        painter.drawText(rect.adjusted(0, 4, 0, 0), QtCore.Qt.AlignmentFlag.AlignCenter, "10")
        
        painter.end()


class DraggableWidgetTile(QtWidgets.QFrame):
    """Draggable tile for widget types."""
    drag_started = QtCore.Signal(dict)
    selected = QtCore.Signal(MenuItemDef)
    
    def __init__(self, label: str, icon: str, widget_type: WidgetType, parent=None):
        super().__init__(parent)
        self._label = label
        self._icon = icon
        self._widget_type = widget_type
        self._base_color = "#F3F4F6"
        self._macro_id = None  # Store assigned macro
        self._setup_ui()
        
    def set_macro_id(self, macro_id: str | None):
        """Set the macro ID assigned to this tile."""
        print(f"[DEBUG-TILE-SET] set_macro_id called on tile {id(self)}, label='{self._label}'")
        print(f"[DEBUG-TILE-SET]   current macro_id: {self._macro_id}")
        print(f"[DEBUG-TILE-SET]   new macro_id: {macro_id}")
        self._macro_id = macro_id
        print(f"[DEBUG-TILE-SET]   AFTER: macro_id={self._macro_id}")
        
    def _setup_ui(self):
        self.setFixedHeight(32)
        self.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        self.setStyleSheet("""
            QFrame {
                background: #F3F4F6;
                border: 1px solid #E5E7EB;
                border-radius: 6px;
            }
            QFrame:hover {
                background: #E5E7EB;
                border-color: #3B82F6;
            }
        """)
        
        layout = QtWidgets.QHBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(8, 0, 8, 0)
        
        # Custom icon widget for font name, font size, font color and cell fill
        if self._widget_type == WidgetType.FONT_NAME:
            icon_widget = FontNameIconWidget(self)
            layout.addWidget(icon_widget)
        elif self._widget_type == WidgetType.FONT_SIZE:
            icon_widget = FontSizeIconWidget(self)
            layout.addWidget(icon_widget)
        elif self._widget_type == WidgetType.FONT_COLOR:
            icon_widget = FontColorIconWidget(self)
            layout.addWidget(icon_widget)
        elif self._widget_type == WidgetType.COLOR_PICKER:
            icon_widget = CellFillIconWidget(self)
            layout.addWidget(icon_widget)
        else:
            icon_label = QtWidgets.QLabel()
            icon_label.setPixmap(load_svg_icon(self._icon, 14, "#4B5563").pixmap(14, 14))
            layout.addWidget(icon_label)
        
        text = QtWidgets.QLabel(self._label)
        text.setStyleSheet("font-size: 12px; color: #374151;")
        layout.addWidget(text)
        layout.addStretch()
        
    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            # Emit selected signal first
            item = MenuItemDef(
                id=f"palette_{self._icon}",
                label=self._label,
                widget_type=self._widget_type,
                location=MenuLocation.TOOLBAR,
                icon=self._icon,
                tooltip=f"Widget: {self._label}"
            )
            self.selected.emit(item)
            self._apply_selection_style()
            
            data = {
                "type": "widget",
                "widget_type": self._widget_type.value,
                "widget_id": self._icon,
                "widget_label": self._label,
                "macro_id": self._macro_id  # Include assigned macro
            }
            print(f"[DEBUG-TILE] Dragging tile '{self._label}' (id={id(self)}) with macro_id={self._macro_id}")
            drag = QtGui.QDrag(self)
            mime = QtCore.QMimeData()
            mime.setText(json.dumps(data))
            drag.setMimeData(mime)
            result = drag.exec(QtCore.Qt.DropAction.CopyAction)
            self.drag_started.emit(data)

    def _apply_selection_style(self):
        """Apply blue outline and shadow for selection - only on tile, not label."""
        self.setStyleSheet(f"""
            QFrame {{
                background: {self._base_color};
                border: 2px solid #3B82F6;
                border-radius: 6px;
            }}
            QFrame:hover {{
                background: #E5E7EB;
                border: 2px solid #2563EB;
            }}
            QLabel {{
                border: none;
            }}
        """)
        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(12)
        shadow.setColor(QtGui.QColor("#3B82F6"))
        shadow.setOffset(0, 2)
        self.setGraphicsEffect(shadow)

    def clear_selection(self):
        """Remove selection styling."""
        self.setStyleSheet("""
            QFrame {
                background: #F3F4F6;
                border: 1px solid #E5E7EB;
                border-radius: 6px;
            }
            QFrame:hover {
                background: #E5E7EB;
                border-color: #3B82F6;
            }
        """)
        self.setGraphicsEffect(None)


class DraggableButtonTile(QtWidgets.QFrame):
    """Draggable tile for standard buttons."""
    drag_started = QtCore.Signal(dict)
    selected = QtCore.Signal(MenuItemDef)
    
    def __init__(self, btn_def: ButtonDef, parent=None):
        super().__init__(parent)
        self._btn_def = btn_def
        self._base_color = btn_def.color or "#F3F4F6"
        self._setup_ui()
        
    def _setup_ui(self):
        self.setFixedHeight(32)
        self.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        color = self._btn_def.color or "#F3F4F6"
        self.setStyleSheet(f"""
            QFrame {{
                background: {color};
                border: 1px solid #E5E7EB;
                border-radius: 6px;
            }}
            QFrame:hover {{
                background: {color}80;
                border-color: #3B82F6;
            }}
        """)
        
        layout = QtWidgets.QHBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(8, 0, 8, 0)
        
        icon_label = QtWidgets.QLabel()
        icon_label.setPixmap(load_svg_icon(self._btn_def.icon, 14, "#4B5563").pixmap(14, 14))
        layout.addWidget(icon_label)
        
        text = QtWidgets.QLabel(self._btn_def.label)
        text.setStyleSheet("font-size: 12px; color: #374151;")
        layout.addWidget(text)
        layout.addStretch()
        
    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            item = MenuItemDef(
                id=self._btn_def.id,
                label=self._btn_def.label,
                widget_type=WidgetType.BUTTON,
                location=MenuLocation.TOOLBAR,
                icon=self._btn_def.icon,
                command_id=self._btn_def.command.id if self._btn_def.command else None,
                tooltip=self._btn_def.tooltip
            )
            self.selected.emit(item)
            self._apply_selection_style()
            
            data = {
                "type": "button",
                "button_id": self._btn_def.id
            }
            drag = QtGui.QDrag(self)
            mime = QtCore.QMimeData()
            mime.setText(json.dumps(data))
            drag.setMimeData(mime)
            result = drag.exec(QtCore.Qt.DropAction.CopyAction)
            self.drag_started.emit(data)

    def _apply_selection_style(self):
        """Apply blue outline and shadow for selection - only on tile, not label."""
        self.setStyleSheet(f"""
            QFrame {{
                background: {self._base_color};
                border: 2px solid #3B82F6;
                border-radius: 6px;
            }}
            QFrame:hover {{
                background: {self._base_color}80;
                border: 2px solid #2563EB;
            }}
            QLabel {{
                border: none;
            }}
        """)
        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(12)
        shadow.setColor(QtGui.QColor("#3B82F6"))
        shadow.setOffset(0, 2)
        self.setGraphicsEffect(shadow)

    def clear_selection(self):
        """Remove selection styling."""
        self.setStyleSheet(f"""
            QFrame {{
                background: {self._base_color};
                border: 1px solid #E5E7EB;
                border-radius: 6px;
            }}
            QFrame:hover {{
                background: {self._base_color}80;
                border-color: #3B82F6;
            }}
        """)
        self.setGraphicsEffect(None)


class DraggableMacroTile(QtWidgets.QFrame):
    """Draggable tile for recorded macros."""
    drag_started = QtCore.Signal(dict)
    selected = QtCore.Signal(MenuItemDef)
    
    def __init__(self, macro_id: str, macro_name: str, parent=None):
        super().__init__(parent)
        self._macro_id = macro_id
        self._macro_name = macro_name
        self._base_color = "#D1FAE5"
        self._setup_ui()
        
    def _setup_ui(self):
        self.setFixedHeight(32)
        self.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        self.setStyleSheet("""
            QFrame {
                background: #D1FAE5;
                border: 1px solid #E5E7EB;
                border-radius: 6px;
            }
            QFrame:hover {
                background: #A7F3D0;
                border-color: #3B82F6;
            }
        """)
        
        layout = QtWidgets.QHBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(8, 0, 8, 0)
        
        icon_label = QtWidgets.QLabel()
        icon_label.setPixmap(load_svg_icon("player-play", 14, "#059669").pixmap(14, 14))
        layout.addWidget(icon_label)
        
        text = QtWidgets.QLabel(self._macro_name)
        text.setStyleSheet("font-size: 12px; color: #374151;")
        layout.addWidget(text)
        layout.addStretch()
        
    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            item = MenuItemDef(
                id=f"macro_{self._macro_id}",
                label=self._macro_name,
                widget_type=WidgetType.BUTTON,
                location=MenuLocation.TOOLBAR,
                icon="player-play",
                macro_id=self._macro_id,
                tooltip=f"Run macro: {self._macro_name}"
            )
            self.selected.emit(item)
            self._apply_selection_style()
            
            data = {
                "type": "macro",
                "macro_id": self._macro_id,
                "macro_name": self._macro_name
            }
            drag = QtGui.QDrag(self)
            mime = QtCore.QMimeData()
            mime.setText(json.dumps(data))
            drag.setMimeData(mime)
            drag.exec(QtCore.Qt.DropAction.CopyAction)
            self.drag_started.emit(data)

    def _apply_selection_style(self):
        """Apply blue outline and shadow for selection - only on tile, not label."""
        self.setStyleSheet(f"""
            QFrame {{
                background: {self._base_color};
                border: 2px solid #3B82F6;
                border-radius: 6px;
            }}
            QFrame:hover {{
                background: #A7F3D0;
                border: 2px solid #2563EB;
            }}
            QLabel {{
                border: none;
            }}
        """)
        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(12)
        shadow.setColor(QtGui.QColor("#3B82F6"))
        shadow.setOffset(0, 2)
        self.setGraphicsEffect(shadow)

    def clear_selection(self):
        """Remove selection styling."""
        self.setStyleSheet("""
            QFrame {
                background: #D1FAE5;
                border: 1px solid #E5E7EB;
                border-radius: 6px;
            }
            QFrame:hover {
                background: #A7F3D0;
                border-color: #3B82F6;
            }
        """)
        self.setGraphicsEffect(None)


class DraggableCustomButtonTile(QtWidgets.QFrame):
    """
    A draggable tile for custom buttons in the widget palette.
    Supports right-click context menu for duplicate and delete operations.
    """

    # Signals
    drag_started = QtCore.Signal(dict)  # Emitted when drag starts
    selected = QtCore.Signal(MenuItemDef)  # Emitted on click
    duplicate_requested = QtCore.Signal(object)  # Emitted when duplicate is requested
    delete_requested = QtCore.Signal(object)  # Emitted when delete is requested
    rename_requested = QtCore.Signal(object)  # Emitted when rename is requested

    def __init__(self, item_def: MenuItemDef, is_template: bool = False, parent=None):
        super().__init__(parent)
        self.item_def = item_def
        self.is_template = is_template  # True for the original "Custom Button"
        self.setFixedHeight(32)
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setProperty("base_color", "#F3F4F6")

        self._setup_ui()
        self._apply_style()

    def _setup_ui(self):
        """Configure the tile UI."""
        layout = QtWidgets.QHBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 4, 8, 4)

        # Icon
        icon_label = QtWidgets.QLabel()
        icon_pixmap = load_svg_icon(self.item_def.icon or "box", 14, "#4B5563").pixmap(14, 14)
        icon_label.setPixmap(icon_pixmap)
        layout.addWidget(icon_label)

        # Label
        text_label = QtWidgets.QLabel(self.item_def.label)
        text_label.setStyleSheet("font-size: 12px; color: #374151;")
        layout.addWidget(text_label)

        layout.addStretch()

        # Context menu
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _apply_style(self):
        """Apply visual style."""
        base_color = self.property("base_color") or "#F3F4F6"
        self.setStyleSheet(f"""
            QFrame {{
                background: {base_color};
                border: 1px solid #E5E7EB;
                border-radius: 6px;
            }}
            QFrame:hover {{
                background: #A7F3D0;
                border-color: #3B82F6;
            }}
        """)

    def set_selected(self):
        """Apply visual selection styling."""
        base_color = self.property("base_color") or "#F3F4F6"
        self.setStyleSheet(f"""
            QFrame {{
                background: {base_color};
                border: 2px solid #3B82F6;
                border-radius: 6px;
            }}
            QFrame:hover {{
                background: #A7F3D0;
                border-color: #3B82F6;
            }}
            QLabel {{
                border: none;
            }}
        """)
        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(12)
        shadow.setColor(QtGui.QColor("#3B82F6"))
        shadow.setOffset(0, 2)
        self.setGraphicsEffect(shadow)

    def clear_selection(self):
        """Remove selection styling."""
        self._apply_style()
        self.setGraphicsEffect(None)

    def refresh_icon(self):
        """Refresh the tile's icon after item_def.icon changes."""
        layout = self.layout()
        if layout:
            # Find the icon label (first QLabel with pixmap)
            for i in range(layout.count()):
                widget = layout.itemAt(i).widget()
                if isinstance(widget, QtWidgets.QLabel) and widget.pixmap():
                    # Update the icon
                    icon_pixmap = load_svg_icon(self.item_def.icon or "box", 14, "#4B5563").pixmap(14, 14)
                    widget.setPixmap(icon_pixmap)
                    break

    def _show_context_menu(self, pos: QtCore.QPoint):
        """Show context menu with duplicate and delete options."""
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: white;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 12px;
                font-size: 12px;
                color: #374151;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background: #F3F4F6;
            }
        """)

        duplicate_action = menu.addAction("Duplicate")
        duplicate_action.triggered.connect(lambda: self.duplicate_requested.emit(self))

        # Only show rename and delete for non-template buttons
        if not self.is_template:
            rename_action = menu.addAction("Rename")
            rename_action.triggered.connect(lambda: self.rename_requested.emit(self))

            menu.addSeparator()
            delete_action = menu.addAction("Delete")
            delete_action.triggered.connect(lambda: self.delete_requested.emit(self))

        menu.exec(self.mapToGlobal(pos))

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        """Handle mouse press - start drag or select."""
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
            self.set_selected()
            self.selected.emit(self.item_def)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        """Handle mouse move - start drag if moved far enough."""
        if not (event.buttons() & QtCore.Qt.MouseButton.LeftButton):
            return
        if self._drag_start_pos is None:
            return
        if (event.pos() - self._drag_start_pos).manhattanLength() < QtWidgets.QApplication.startDragDistance():
            return
        self._start_drag()

    def _start_drag(self):
        """Start drag operation."""
        drag = QtGui.QDrag(self)
        mime_data = QtCore.QMimeData()
        drag_data = self.item_def.to_dict()
        mime_data.setText(json.dumps(drag_data))
        mime_data.setData("application/x-menubuilder-tile", json.dumps(drag_data).encode())
        drag.setMimeData(mime_data)
        
        # Create a small drag pixmap with just the icon (32x32 button-like)
        pixmap = self._create_drag_pixmap()
        drag.setPixmap(pixmap)
        drag.setHotSpot(QtCore.QPoint(pixmap.width() // 2, pixmap.height() // 2))
        
        self.drag_started.emit(drag_data)
        drag.exec(QtCore.Qt.DropAction.CopyAction)
    
    def _create_drag_pixmap(self) -> QtGui.QPixmap:
        """Create a small pixmap for dragging (32x32 icon button)."""
        size = 32
        pixmap = QtGui.QPixmap(size, size)
        pixmap.fill(QtGui.QColor("transparent"))
        
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        
        # Draw rounded background
        rect = QtCore.QRectF(2, 2, size - 4, size - 4)
        painter.setPen(QtGui.QPen(QtGui.QColor("#D1D5DB"), 1))
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#F3F4F6")))
        painter.drawRoundedRect(rect, 4, 4)
        
        # Draw icon
        icon_name = self.item_def.icon or "box"
        icon_pixmap = load_svg_icon(icon_name, 18, "#4B5563").pixmap(18, 18)
        x = (size - 18) // 2
        y = (size - 18) // 2
        painter.drawPixmap(x, y, icon_pixmap)
        
        painter.end()
        return pixmap


# =============================================================================
# PROPERTIES EDITOR
# =============================================================================

class PropertiesEditor(QtWidgets.QWidget):
    """Editor for item properties including macro assignment."""
    item_updated = QtCore.Signal(str)  # item_id
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_item: MenuItemDef | None = None
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QtWidgets.QFormLayout(self)
        layout.setSpacing(8)
        
        # Label
        self._label_input = QtWidgets.QLineEdit()
        self._label_input.textChanged.connect(self._update_item)
        layout.addRow("Label:", self._label_input)
        
        # Icon - searchable dropdown with all outline icons
        self._icon_combo = QtWidgets.QComboBox()
        self._icon_combo.setEditable(True)
        self._icon_combo.setPlaceholderText("Search icon name...")
        self._icon_combo.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
        self._icon_combo.setMaxVisibleItems(20)
        self._icon_combo.setStyleSheet("QComboBox { combobox-popup: 0; }")  # Force dropdown with scrollbar
        self._load_icons()
        self._icon_combo.currentTextChanged.connect(self._update_item)
        self._icon_combo.lineEdit().textChanged.connect(self._update_item)
        layout.addRow("Icon:", self._icon_combo)
        
        # Tooltip
        self._tooltip_input = QtWidgets.QLineEdit()
        self._tooltip_input.textChanged.connect(self._update_item)
        layout.addRow("Tooltip:", self._tooltip_input)
        
        # Command
        self._command_combo = QtWidgets.QComboBox()
        self._command_combo.addItem("(None)", None)
        for cmd_id, cmd_spec in COMMAND_LIBRARY.items():
            self._command_combo.addItem(cmd_spec.name, cmd_id)
        self._command_combo.currentIndexChanged.connect(self._update_item)
        layout.addRow("Command:", self._command_combo)
        
        # === MACRO ASSIGNMENT ===
        macro_label = QtWidgets.QLabel("Recorded Macro")
        macro_label.setStyleSheet("font-size: 11px; font-weight: 600; color: #6B7280; margin-top: 8px;")
        layout.addRow(macro_label)
        
        # Macro row with refresh button
        macro_row = QtWidgets.QHBoxLayout()
        macro_row.setSpacing(6)
        
        self._macro_combo = QtWidgets.QComboBox()
        self._macro_combo.addItem("(None)", None)
        self._refresh_macros()
        
        # Connect macro combo change with debug
        def on_macro_changed(idx):
            data = self._macro_combo.currentData()
            text = self._macro_combo.currentText()
            print(f"[DEBUG-COMBO] Macro combo changed: index={idx}, text='{text}', data={data}")
            self._update_item()
        
        self._macro_combo.currentIndexChanged.connect(on_macro_changed)
        macro_row.addWidget(self._macro_combo, 1)
        
        # Refresh button with circular arrows
        refresh_btn = QtWidgets.QPushButton()
        refresh_btn.setFixedSize(24, 24)
        refresh_btn.setToolTip("Refresh macro list")
        refresh_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                padding: 2px;
            }
            QPushButton:hover {
                background: #E5E7EB;
                border-radius: 4px;
            }
        """)
        refresh_btn.setIcon(load_svg_icon("refresh", 16, "#6B7280"))
        refresh_btn.clicked.connect(self._on_refresh_macros_clicked)
        macro_row.addWidget(refresh_btn)
        
        layout.addRow("Macro:", macro_row)
        
        # Macro info
        self._macro_info = QtWidgets.QLabel()
        self._macro_info.setStyleSheet("font-size: 11px; color: #6B7280;")
        self._macro_info.setWordWrap(True)
        layout.addRow(self._macro_info)
        
        # Disable all initially
        self._set_enabled(False)
        
    def _on_refresh_macros_clicked(self):
        """Refresh button clicked — refresh combo and notify parent palette."""
        self._refresh_macros()
        # Notify parent ToolboxEditor to refresh its macro palette too
        parent = self.parent()
        if parent and hasattr(parent, '_refresh_macros'):
            parent._refresh_macros()

    def _refresh_macros(self):
        """Refresh macro dropdown from files in ~/.om/macros/"""
        self._macro_combo.clear()
        self._macro_combo.addItem("(None)", None)

        from lib_utils.paths import OM_MACROS_DIR
        macros_dir = OM_MACROS_DIR
        if not macros_dir.exists():
            return

        macro_files = sorted(macros_dir.glob("*.openm"))
        for macro_file in macro_files:
            try:
                # Parse macro name from file header
                macro_name = macro_file.stem
                with open(macro_file) as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("# Macro:"):
                            macro_name = line.split(":", 1)[1].strip()
                            break
                        if not line.startswith("#") and line:
                            break
                
                macro_id = macro_file.stem
                self._macro_combo.addItem(macro_name, macro_id)
            except Exception:
                pass
                
    def set_item(self, item: MenuItemDef | None):
        """Set item to edit."""
        print(f"\n[DEBUG-SET] === set_item called ===")
        self._current_item = item
        if item:
            print(f"[DEBUG-SET]   item.id: {item.id}")
            print(f"[DEBUG-SET]   item.label: {item.label}")
            print(f"[DEBUG-SET]   item.macro_id: {item.macro_id}")
            print(f"[DEBUG-SET]   object id: {id(item)}")
        
        if item is None:
            self._set_enabled(False)
            self._label_input.clear()
            self._icon_combo.setCurrentIndex(0)
            self._tooltip_input.clear()
            self._command_combo.setCurrentIndex(0)
            self._macro_combo.setCurrentIndex(0)
            self._macro_info.clear()
            return
            
        self._set_enabled(True)
        self._label_input.setText(item.label)
        # Find and select the icon in the combo
        if item.icon:
            idx = self._icon_combo.findData(item.icon)
            self._icon_combo.setCurrentIndex(max(0, idx))
        else:
            self._icon_combo.setCurrentIndex(0)
        self._tooltip_input.setText(item.tooltip)
        
        if item.command_id:
            idx = self._command_combo.findData(item.command_id)
            self._command_combo.setCurrentIndex(max(0, idx))
        else:
            self._command_combo.setCurrentIndex(0)
            
        if item.macro_id:
            idx = self._macro_combo.findData(item.macro_id)
            self._macro_combo.setCurrentIndex(max(0, idx))
            self._macro_info.setText(f"Executes: {item.macro_id}")
        else:
            self._macro_combo.setCurrentIndex(0)
            self._macro_info.clear()
            
    def _set_enabled(self, enabled: bool):
        """Enable/disable all inputs."""
        self._label_input.setEnabled(enabled)
        self._icon_combo.setEnabled(enabled)
        self._tooltip_input.setEnabled(enabled)
        self._command_combo.setEnabled(enabled)
        self._macro_combo.setEnabled(enabled)
        
    def _load_icons(self):
        """Load all icon names from the outline folder."""
        from pathlib import Path
        icon_path = Path(__file__).parent.parent.parent / "assets" / "icons" / "tabler" / "icons" / "outline"
        if icon_path.exists():
            self._icon_combo.addItem("(None)", None)
            icon_files = sorted(icon_path.glob("*.svg"))
            for icon_file in icon_files:
                icon_name = icon_file.stem
                self._icon_combo.addItem(icon_name, icon_name)
        
    def _update_item(self):
        """Update current item from UI."""
        if not self._current_item:
            print("[DEBUG-UPDATE] No current item, returning")
            return
            
        # Find parent to check if item is in config
        parent = self.parent()
        if parent and hasattr(parent, '_config'):
            config_item = parent._config.items.get(self._current_item.id)
            same_object = config_item is self._current_item
            print(f"[DEBUG-UPDATE] current_item id()={id(self._current_item)}, config_item id()={id(config_item) if config_item else 'NONE'}, same={same_object}")
        
        print(f"[DEBUG-UPDATE] Updating item {self._current_item.id} at {id(self._current_item)}")
        print(f"[DEBUG-UPDATE] BEFORE: macro_id={self._current_item.macro_id}")
        
        self._current_item.label = self._label_input.text()
        self._current_item.icon = self._icon_combo.currentData() or None
        self._current_item.tooltip = self._tooltip_input.text()
        self._current_item.command_id = self._command_combo.currentData()
        
        # Get macro_id from combo
        new_macro_id = self._macro_combo.currentData()
        print(f"[DEBUG-ASSIGN] Macro combo currentData: {new_macro_id}")
        
        if new_macro_id:
            print(f"[DEBUG-ASSIGN] *** ASSIGNING MACRO '{new_macro_id}' to item '{self._current_item.id}' ***")
        else:
            print(f"[DEBUG-ASSIGN] Clearing macro from item '{self._current_item.id}'")
        
        self._current_item.macro_id = new_macro_id
        
        # Also update the selected palette tile so drag includes macro
        # Find ToolboxEditorPalette by traversing up parent hierarchy
        parent = self.parent()
        palette = None
        while parent:
            if hasattr(parent, '_selected_palette_tile'):
                palette = parent
                break
            parent = parent.parent()
        
        print(f"[DEBUG-ASSIGN] Found palette: {palette}")
        if palette and palette._selected_palette_tile:
            tile = palette._selected_palette_tile
            print(f"[DEBUG-ASSIGN] _selected_palette_tile={tile}, id={id(tile)}")
            if hasattr(tile, 'set_macro_id'):
                tile.set_macro_id(new_macro_id)
                print(f"[DEBUG-ASSIGN] Called set_macro_id on tile, now macro_id={tile._macro_id}")
        
        print(f"[DEBUG-ASSIGN] AFTER: item.macro_id={self._current_item.macro_id}")
        
        if self._current_item.macro_id:
            self._macro_info.setText(f"Executes: {self._current_item.macro_id}")
        else:
            self._macro_info.clear()
            
        self.item_updated.emit(self._current_item.id)
