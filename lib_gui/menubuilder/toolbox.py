"""
GUI Toolbox Builder - Visual editor for gui-toolbox.conf

Features:
- Three-panel layout: Widget Palette | Design Canvas | Properties Panel
- Drag-and-drop from palette to toolbar/menu areas
- Macro assignment on selection
- Real-time preview of menu/toolbar structure
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from PySide6 import QtCore, QtGui, QtWidgets

from .models import (
    ToolboxConfig, MenuItemDef, WidgetType, MenuLocation,
    ButtonDef, CategoryDef, DEFAULT_CATEGORIES, COMMAND_LIBRARY, BUTTON_LIBRARY
)
from .persistence import save_toolbox_config, load_toolbox_config, DEFAULT_TOOLBOX_CONFIG_PATH
from .widgets import load_svg_icon, DraggableTile


# =============================================================================
# CUSTOM ICON WIDGETS FOR PALETTE
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
            from PySide6.QtSvg import QSvgRenderer
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


# =============================================================================
# WIDGET PALETTE - Left Panel
# =============================================================================

class WidgetPalette(QtWidgets.QWidget):
    """Palette of draggable widgets for building menus/toolbars."""
    
    widget_selected = QtCore.Signal(MenuItemDef)  # For click-to-add
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_tile: QtWidgets.QWidget | None = None
        self._drag_candidate: QtWidgets.QWidget | None = None
        self._drag_start_pos: QtCore.QPoint | None = None
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # Header
        header = QtWidgets.QLabel("Widget Palette")
        header.setStyleSheet("font-size: 14px; font-weight: 600; color: #1F2937;")
        layout.addWidget(header)
        
        # Search box
        self.search_box = QtWidgets.QLineEdit()
        self.search_box.setPlaceholderText("Search widgets...")
        self.search_box.setStyleSheet("""
            QLineEdit {
                background: white;
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12px;
                margin: 8px 0;
            }
            QLineEdit:focus { border-color: #3B82F6; }
        """)
        self.search_box.textChanged.connect(self._filter_widgets)
        layout.addWidget(self.search_box)
        
        # Scroll area for categories
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.scroll_content = QtWidgets.QWidget()
        self.scroll_layout = QtWidgets.QVBoxLayout(self.scroll_content)
        self.scroll_layout.setSpacing(12)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        
        self._build_palette()
        
        scroll.setWidget(self.scroll_content)
        layout.addWidget(scroll)
        
    def _build_palette(self):
        """Build the widget palette with categories."""
        # Basic Widgets Category
        self._add_category("Basic", "#F3F4F6", [
            ("Button", "button", "cursor-pointer", WidgetType.BUTTON),
            ("Toggle", "toggle", "toggle-left", WidgetType.TOGGLE),
            ("Separator", "separator", "minus", WidgetType.SEPARATOR),
            ("Spacer", "spacer", "space", WidgetType.SPACER),
        ])
        
        # Input Widgets Category
        self._add_category("Inputs", "#DBEAFE", [
            ("Font Name", "font_name", "type", WidgetType.FONT_NAME),
            ("Font Size", "font_size", "type", WidgetType.FONT_SIZE),
            ("Font Color", "font_color", "type", WidgetType.FONT_COLOR),
            ("Cell Fill", "color", "paint-bucket", WidgetType.COLOR_PICKER),
        ])
        
        # Standard Buttons (from existing BUTTON_LIBRARY)
        self._add_button_category()
        
        # Macros Category (populated dynamically)
        self._add_macro_category()
        
        self.scroll_layout.addStretch()
        
    def _add_category(self, name: str, color: str, items: list[tuple]):
        """Add a category section to the palette."""
        header = QtWidgets.QLabel(name)
        header.setStyleSheet(f"""
            font-size: 11px;
            font-weight: 600;
            color: #6B7280;
            text-transform: uppercase;
            padding: 8px 0 4px 0;
            border-bottom: 1px solid #E5E7EB;
            margin-bottom: 8px;
            background: {color}40;
        """)
        self.scroll_layout.addWidget(header)
        
        grid = QtWidgets.QWidget()
        grid_layout = QtWidgets.QVBoxLayout(grid)
        grid_layout.setSpacing(4)
        grid_layout.setContentsMargins(0, 0, 0, 8)
        
        for label, widget_id, icon, widget_type in items:
            tile = self._create_widget_tile(label, widget_id, icon, widget_type, color)
            grid_layout.addWidget(tile)
            
        self.scroll_layout.addWidget(grid)
        
    def _add_button_category(self):
        """Add standard buttons from BUTTON_LIBRARY."""
        header = QtWidgets.QLabel("Standard Buttons")
        header.setStyleSheet("""
            font-size: 11px;
            font-weight: 600;
            color: #6B7280;
            text-transform: uppercase;
            padding: 8px 0 4px 0;
            border-bottom: 1px solid #E5E7EB;
            margin-bottom: 8px;
            background: #FEF3C740;
        """)
        self.scroll_layout.addWidget(header)
        
        grid = QtWidgets.QWidget()
        grid_layout = QtWidgets.QVBoxLayout(grid)
        grid_layout.setSpacing(4)
        grid_layout.setContentsMargins(0, 0, 0, 8)
        
        for btn_id, btn_def in list(BUTTON_LIBRARY.items())[:8]:  # Limit to 8 for now
            tile = self._create_button_tile(btn_def)
            grid_layout.addWidget(tile)
            
        self.scroll_layout.addWidget(grid)
        
    def _add_macro_category(self):
        """Add recorded macros from ~/.om/macros/."""
        self.macro_header = QtWidgets.QLabel("Recorded Macros")
        self.macro_header.setStyleSheet("""
            font-size: 11px;
            font-weight: 600;
            color: #6B7280;
            text-transform: uppercase;
            padding: 8px 0 4px 0;
            border-bottom: 1px solid #E5E7EB;
            margin-bottom: 8px;
            background: #D1FAE540;
        """)
        self.scroll_layout.addWidget(self.macro_header)
        
        self.macro_container = QtWidgets.QWidget()
        self.macro_layout = QtWidgets.QVBoxLayout(self.macro_container)
        self.macro_layout.setSpacing(4)
        self.macro_layout.setContentsMargins(0, 0, 0, 8)
        
        self._refresh_macro_list()
        self.scroll_layout.addWidget(self.macro_container)
        
    def _refresh_macro_list(self):
        """Refresh the list of available macros."""
        # Clear existing
        while self.macro_layout.count():
            item = self.macro_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        from lib_utils.paths import OM_MACROS_DIR
        macros_dir = OM_MACROS_DIR
        if not macros_dir.exists():
            label = QtWidgets.QLabel("No macros recorded yet")
            label.setStyleSheet("font-size: 11px; color: #9CA3AF; font-style: italic;")
            self.macro_layout.addWidget(label)
            return
            
        # Load macro_index.json if exists
        index_file = macros_dir / "macro_index.json"
        if index_file.exists():
            try:
                with open(index_file) as f:
                    index = json.load(f)
                for macro_id, info in index.get("macros", {}).items():
                    tile = self._create_macro_tile(macro_id, info)
                    self.macro_layout.addWidget(tile)
            except Exception:
                pass
        
        if self.macro_layout.count() == 0:
            label = QtWidgets.QLabel("No macros recorded yet")
            label.setStyleSheet("font-size: 11px; color: #9CA3AF; font-style: italic;")
            self.macro_layout.addWidget(label)
            
    def _create_widget_tile(self, label: str, widget_id: str, icon: str, 
                            widget_type: WidgetType, color: str) -> QtWidgets.QWidget:
        """Create a draggable tile for a widget type."""
        container = QtWidgets.QFrame()
        container.setFixedHeight(32)
        container.setStyleSheet(f"""
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
        
        layout = QtWidgets.QHBoxLayout(container)
        layout.setSpacing(6)
        layout.setContentsMargins(8, 0, 8, 0)
        
        # Custom icon widget for font name, font size, font color and cell fill
        if widget_type == WidgetType.FONT_NAME:
            icon_widget = FontNameIconWidget(container)
            layout.addWidget(icon_widget)
        elif widget_type == WidgetType.FONT_SIZE:
            icon_widget = FontSizeIconWidget(container)
            layout.addWidget(icon_widget)
        elif widget_type == WidgetType.FONT_COLOR:
            icon_widget = FontColorIconWidget(container)
            layout.addWidget(icon_widget)
        elif widget_type == WidgetType.COLOR_PICKER:
            icon_widget = CellFillIconWidget(container)
            layout.addWidget(icon_widget)
        else:
            icon_label = QtWidgets.QLabel()
            icon_label.setPixmap(load_svg_icon(icon, 14, "#4B5563").pixmap(14, 14))
            layout.addWidget(icon_label)
        
        text = QtWidgets.QLabel(label)
        text.setStyleSheet("font-size: 12px; color: #374151;")
        layout.addWidget(text)
        layout.addStretch()
        
        # Store data for drag and selection
        container.setProperty("widget_type", widget_type.value)
        container.setProperty("widget_id", widget_id)
        container.setProperty("widget_label", label)
        container.setProperty("base_color", color)
        
        # Enable click selection and drag
        container.mousePressEvent = lambda e, c=container: self._on_tile_clicked(e, c)
        
        return container
        
    def _create_button_tile(self, btn_def: ButtonDef) -> QtWidgets.QWidget:
        """Create a tile for a standard button."""
        container = QtWidgets.QFrame()
        container.setFixedHeight(32)
        color = btn_def.color or "#F3F4F6"
        container.setStyleSheet(f"""
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
        
        layout = QtWidgets.QHBoxLayout(container)
        layout.setSpacing(6)
        layout.setContentsMargins(8, 0, 8, 0)
        
        icon_label = QtWidgets.QLabel()
        icon_label.setPixmap(load_svg_icon(btn_def.icon, 14, "#4B5563").pixmap(14, 14))
        layout.addWidget(icon_label)
        
        text = QtWidgets.QLabel(btn_def.label)
        text.setStyleSheet("font-size: 12px; color: #374151;")
        layout.addWidget(text)
        layout.addStretch()
        
        # Store data
        container.setProperty("button_id", btn_def.id)
        container.setProperty("is_button", True)
        container.setProperty("base_color", color)
        container.setProperty("btn_def", btn_def)
        
        container.mousePressEvent = lambda e, c=container: self._on_tile_clicked(e, c)
        
        return container
        
    def _create_macro_tile(self, macro_id: str, info: dict) -> QtWidgets.QWidget:
        """Create a tile for a recorded macro."""
        container = QtWidgets.QFrame()
        container.setFixedHeight(32)
        container.setStyleSheet("""
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
        
        layout = QtWidgets.QHBoxLayout(container)
        layout.setSpacing(6)
        layout.setContentsMargins(8, 0, 8, 0)
        
        icon_label = QtWidgets.QLabel()
        icon_label.setPixmap(load_svg_icon("player-play", 14, "#059669").pixmap(14, 14))
        layout.addWidget(icon_label)
        
        text = QtWidgets.QLabel(info.get("name", macro_id))
        text.setStyleSheet("font-size: 12px; color: #374151;")
        layout.addWidget(text)
        layout.addStretch()
        
        # Store data
        container.setProperty("macro_id", macro_id)
        container.setProperty("is_macro", True)
        container.setProperty("macro_name", info.get("name", macro_id))
        container.setProperty("base_color", "#D1FAE5")
        container.setProperty("macro_info", info)
        
        container.mousePressEvent = lambda e, c=container: self._on_tile_clicked(e, c)
        
        return container
        
    def _start_drag(self, container: QtWidgets.QWidget):
        """Start drag operation."""
        drag = QtGui.QDrag(container)
        mime = QtCore.QMimeData()
        
        # Encode widget data
        data = {}
        if container.property("is_button"):
            data = {"type": "button", "button_id": container.property("button_id")}
        elif container.property("is_macro"):
            data = {"type": "macro", "macro_id": container.property("macro_id"), 
                   "macro_name": container.property("macro_name")}
        else:
            data = {"type": "widget", "widget_type": container.property("widget_type"),
                   "widget_id": container.property("widget_id"),
                   "widget_label": container.property("widget_label")}
                   
        mime.setText(json.dumps(data))
        drag.setMimeData(mime)
        drag.exec(QtCore.Qt.DropAction.CopyAction)
        
    def _filter_widgets(self, text: str):
        """Filter widgets by search text."""
        text = text.lower()
        # Implementation for filtering
        pass

    def _on_tile_clicked(self, event: QtGui.QMouseEvent, container: QtWidgets.QWidget):
        """Handle tile click - select and show in properties panel."""
        import traceback
        traceback.print_stack(limit=5)
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._select_tile(container)
            # Create and emit MenuItemDef
            item_def = self._create_item_def_from_tile(container)
            if item_def:
                self.widget_selected.emit(item_def)
            # Store for potential drag
            self._drag_candidate = container
            self._drag_start_pos = event.pos()
            # Install mouse move/release handlers on the container for this drag session
            container._original_mouse_move = container.mouseMoveEvent
            container._original_mouse_release = container.mouseReleaseEvent
            container.mouseMoveEvent = lambda e, c=container: self._on_tile_mouse_move(e, c)
            container.mouseReleaseEvent = lambda e, c=container: self._on_tile_mouse_release(e, c)

    def _select_tile(self, container: QtWidgets.QWidget):
        """Apply visual selection styling to a tile."""
        # Deselect previous
        if self._selected_tile and self._selected_tile != container:
            self._clear_selection(self._selected_tile)
        
        # Apply selection styling: blue border + shadow
        base_color = container.property("base_color") or "#F3F4F6"
        container.setStyleSheet(f"""
            QFrame {{
                background: {base_color};
                border: 2px solid #3B82F6;
                border-radius: 6px;
            }}
            QFrame:hover {{
                background: {base_color}80;
                border: 2px solid #2563EB;
            }}
        """)
        
        # Add blue glow shadow
        shadow = QtWidgets.QGraphicsDropShadowEffect(container)
        shadow.setBlurRadius(12)
        shadow.setColor(QtGui.QColor("#3B82F6"))
        shadow.setOffset(0, 2)
        container.setGraphicsEffect(shadow)
        
        self._selected_tile = container

    def _clear_selection(self, container: QtWidgets.QWidget):
        """Remove selection styling from a tile."""
        if not container:
            return
        base_color = container.property("base_color") or "#F3F4F6"
        container.setStyleSheet(f"""
            QFrame {{
                background: {base_color};
                border: 1px solid #E5E7EB;
                border-radius: 6px;
            }}
            QFrame:hover {{
                background: {base_color}80;
                border-color: #3B82F6;
            }}
        """)
        container.setGraphicsEffect(None)

    def _on_tile_mouse_move(self, event: QtGui.QMouseMoveEvent, container: QtWidgets.QWidget):
        """Start drag if mouse moves beyond threshold."""
        if self._drag_candidate == container and self._drag_start_pos:
            # Calculate distance from start
            distance = (event.pos() - self._drag_start_pos).manhattanLength()
            if distance > 10:  # 10px threshold to start drag
                # Restore original handlers first
                if hasattr(container, '_original_mouse_move'):
                    container.mouseMoveEvent = container._original_mouse_move
                    del container._original_mouse_move
                if hasattr(container, '_original_mouse_release'):
                    container.mouseReleaseEvent = container._original_mouse_release
                    del container._original_mouse_release
                self._drag_candidate = None
                self._drag_start_pos = None
                self._start_drag(container)

    def _on_tile_mouse_release(self, event: QtGui.QMouseEvent, container: QtWidgets.QWidget):
        """Clean up drag tracking on mouse release."""
        # Restore original handlers
        if hasattr(container, '_original_mouse_move'):
            container.mouseMoveEvent = container._original_mouse_move
            del container._original_mouse_move
        if hasattr(container, '_original_mouse_release'):
            container.mouseReleaseEvent = container._original_mouse_release
            del container._original_mouse_release
        self._drag_candidate = None
        self._drag_start_pos = None

    def _create_item_def_from_tile(self, container: QtWidgets.QWidget):
        """Create MenuItemDef from tile data."""
        from lib_gui.menubuilder.models import MenuItemDef, WidgetType
        
        if container.property("is_button"):
            btn_def = container.property("btn_def")
            if btn_def:
                return MenuItemDef(
                    id=btn_def.id,
                    label=btn_def.label,
                    icon=btn_def.icon,
                    widget_type=WidgetType.BUTTON,
                    command_id=btn_def.command.id if btn_def.command else None,
                    tooltip=btn_def.tooltip
                )
        elif container.property("is_macro"):
            macro_id = container.property("macro_id")
            macro_name = container.property("macro_name")
            return MenuItemDef(
                id=f"macro_{macro_id}",
                label=macro_name,
                icon="player-play",
                widget_type=WidgetType.BUTTON,
                macro_id=macro_id,
                tooltip=f"Run macro: {macro_name}"
            )
        else:
            widget_type_val = container.property("widget_type")
            widget_id = container.property("widget_id")
            label = container.property("widget_label")
            return MenuItemDef(
                id=f"palette_{widget_id}",
                label=label,
                widget_type=WidgetType(widget_type_val) if widget_type_val else WidgetType.BUTTON,
                tooltip=f"Widget: {label}"
            )
        return None


# =============================================================================
# DESIGN CANVAS - Center Panel
# =============================================================================

class DesignCanvas(QtWidgets.QWidget):
    """Canvas for designing toolbars and menu structures."""
    
    item_selected = QtCore.Signal(str)  # item_id selected
    item_dropped = QtCore.Signal(dict)  # item data dropped
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_config = ToolboxConfig()
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # === Toolbar Preview Section ===
        toolbar_header = QtWidgets.QLabel("Toolbar Preview")
        toolbar_header.setStyleSheet("font-size: 12px; font-weight: 600; color: #6B7280;")
        layout.addWidget(toolbar_header)
        
        self.toolbar_area = QtWidgets.QFrame()
        self.toolbar_area.setMinimumHeight(48)
        self.toolbar_area.setStyleSheet("""
            QFrame {
                background: #F3F4F6;
                border: 2px dashed #D1D5DB;
                border-radius: 8px;
            }
            QFrame[active="true"] {
                border-color: #3B82F6;
                background: #EFF6FF;
            }
        """)
        self.toolbar_area.setAcceptDrops(True)
        
        toolbar_layout = QtWidgets.QHBoxLayout(self.toolbar_area)
        toolbar_layout.setSpacing(4)
        toolbar_layout.setContentsMargins(8, 8, 8, 8)
        toolbar_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        
        self.empty_toolbar_label = QtWidgets.QLabel("Drop widgets here to build toolbar...")
        self.empty_toolbar_label.setStyleSheet("color: #9CA3AF; font-style: italic;")
        toolbar_layout.addWidget(self.empty_toolbar_label)
        toolbar_layout.addStretch()
        
        # Drag events
        self.toolbar_area.dragEnterEvent = self._on_toolbar_drag_enter
        self.toolbar_area.dragLeaveEvent = self._on_toolbar_drag_leave
        self.toolbar_area.dropEvent = self._on_toolbar_drop
        
        layout.addWidget(self.toolbar_area)
        
        # === Menu Bar Section ===
        menu_header = QtWidgets.QLabel("Menu Bar Structure")
        menu_header.setStyleSheet("font-size: 12px; font-weight: 600; color: #6B7280;")
        layout.addWidget(menu_header)
        
        self.menu_area = QtWidgets.QFrame()
        self.menu_area.setStyleSheet("""
            QFrame {
                background: white;
                border: 1px solid #E5E7EB;
                border-radius: 8px;
            }
        """)
        menu_layout = QtWidgets.QVBoxLayout(self.menu_area)
        menu_layout.setSpacing(8)
        menu_layout.setContentsMargins(12, 12, 12, 12)
        
        # Menu list
        self.menu_list = QtWidgets.QListWidget()
        self.menu_list.setStyleSheet("""
            QListWidget {
                border: none;
                background: transparent;
            }
            QListWidget::item {
                padding: 8px;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background: #DBEAFE;
            }
        """)
        self.menu_list.itemClicked.connect(self._on_menu_selected)
        menu_layout.addWidget(self.menu_list)
        
        # Add menu button
        add_menu_btn = QtWidgets.QPushButton("+ Add Menu")
        add_menu_btn.setStyleSheet("""
            QPushButton {
                background: white;
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #F3F4F6;
            }
        """)
        add_menu_btn.clicked.connect(self._add_new_menu)
        menu_layout.addWidget(add_menu_btn)
        
        layout.addWidget(self.menu_area)
        
        layout.addStretch()
        
    def _on_toolbar_drag_enter(self, event: QtGui.QDragEnterEvent):
        """Handle drag entering toolbar area."""
        if event.mimeData().hasText():
            event.acceptProposedAction()
            self.toolbar_area.setProperty("active", "true")
            self.toolbar_area.style().unpolish(self.toolbar_area)
            self.toolbar_area.style().polish(self.toolbar_area)
            
    def _on_toolbar_drag_leave(self, event: QtGui.QDragLeaveEvent):
        """Handle drag leaving toolbar area."""
        self.toolbar_area.setProperty("active", "false")
        self.toolbar_area.style().unpolish(self.toolbar_area)
        self.toolbar_area.style().polish(self.toolbar_area)
        
    def _on_toolbar_drop(self, event: QtGui.QDropEvent):
        """Handle drop on toolbar area."""
        self.toolbar_area.setProperty("active", "false")
        self.toolbar_area.style().unpolish(self.toolbar_area)
        self.toolbar_area.style().polish(self.toolbar_area)
        
        if event.mimeData().hasText():
            try:
                data = json.loads(event.mimeData().text())
                self.item_dropped.emit(data)
                event.acceptProposedAction()
            except json.JSONDecodeError:
                pass
                
    def _on_menu_selected(self, item: QtWidgets.QListWidgetItem):
        """Handle menu item selection."""
        menu_name = item.text().split(" ")[0]  # Remove item count
        # Show menu contents
        
    def _add_new_menu(self):
        """Add a new menu to the menu bar."""
        text, ok = QtWidgets.QInputDialog.getText(self, "New Menu", "Menu name:")
        if ok and text:
            if text not in self.current_config.menubar_structure:
                self.current_config.menubar_structure[text] = []
                self._refresh_menu_list()
                
    def _refresh_menu_list(self):
        """Refresh the menu list display."""
        self.menu_list.clear()
        for menu_name, items in self.current_config.menubar_structure.items():
            item_text = f"{menu_name} ({len(items)} items)"
            self.menu_list.addItem(item_text)
            
    def add_item_to_toolbar(self, item_def: MenuItemDef):
        """Add a menu item to the toolbar preview."""
        # Hide empty label if it exists
        layout = self.toolbar_area.layout()
        if self.empty_toolbar_label and self.empty_toolbar_label.parent():
            if self.empty_toolbar_label.isVisible():
                self.empty_toolbar_label.hide()
        
        # Create widget based on type
        widget = self._create_toolbar_widget(item_def)
        
        # Insert before stretch
        index = layout.count() - 1
        layout.insertWidget(index, widget)
        
        self.current_config.toolbar_layout.append(item_def.id)
        self.current_config.items[item_def.id] = item_def
        
    def _create_toolbar_widget(self, item_def: MenuItemDef) -> QtWidgets.QWidget:
        """Create a widget for the toolbar preview."""
        if item_def.widget_type == WidgetType.BUTTON:
            btn = QtWidgets.QPushButton()
            if item_def.icon:
                btn.setIcon(load_svg_icon(item_def.icon, 16, "#4B5563"))
            btn.setToolTip(item_def.label)
            btn.setFixedSize(32, 32)
            btn.setStyleSheet("""
                QPushButton {
                    background: white;
                    border: 1px solid #E5E7EB;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background: #F3F4F6;
                    border-color: #3B82F6;
                }
            """)
            btn.clicked.connect(lambda: self.item_selected.emit(item_def.id))
            return btn
        elif item_def.widget_type == WidgetType.SEPARATOR:
            line = QtWidgets.QFrame()
            line.setFrameShape(QtWidgets.QFrame.Shape.VLine)
            line.setStyleSheet("color: #E5E7EB;")
            return line
        else:
            # Default button for other types
            btn = QtWidgets.QPushButton(item_def.label[:8])
            btn.setFixedHeight(32)
            return btn
            
    def clear_toolbar(self):
        """Clear all items from toolbar."""
        layout = self.toolbar_area.layout()
        # Remove all widgets except stretch and empty_label
        widgets_to_remove = []
        for i in range(layout.count() - 1):  # -1 to keep stretch at end
            item = layout.itemAt(i)
            if item and item.widget() and item.widget() != self.empty_toolbar_label:
                widgets_to_remove.append(item.widget())
        
        for widget in widgets_to_remove:
            layout.removeWidget(widget)
            widget.deleteLater()
        
        # Ensure empty label exists and is visible
        if self.empty_toolbar_label and self.empty_toolbar_label.parent():
            self.empty_toolbar_label.show()
        else:
            # Recreate if deleted
            self.empty_toolbar_label = QtWidgets.QLabel("Drop widgets here to build toolbar...")
            self.empty_toolbar_label.setStyleSheet("color: #9CA3AF; font-style: italic;")
            layout.insertWidget(0, self.empty_toolbar_label)
        
        self.current_config.toolbar_layout.clear()
        
    def set_config(self, config: ToolboxConfig):
        """Set the current toolbox configuration."""
        self.current_config = config
        self.clear_toolbar()
        
        # Rebuild toolbar
        for item_id in config.toolbar_layout:
            if item_id in config.items:
                self.add_item_to_toolbar(config.items[item_id])
                
        # Refresh menu list
        self._refresh_menu_list()


# =============================================================================
# PROPERTIES PANEL - Right Panel
# =============================================================================

class PropertiesPanel(QtWidgets.QWidget):
    """Panel for editing properties of selected menu items."""
    
    item_updated = QtCore.Signal(str)  # item_id that was updated
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_item: MenuItemDef | None = None
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # Header
        header = QtWidgets.QLabel("Properties")
        header.setStyleSheet("font-size: 14px; font-weight: 600; color: #1F2937;")
        layout.addWidget(header)
        
        # No selection label
        self.no_selection_label = QtWidgets.QLabel("Select an item to edit its properties")
        self.no_selection_label.setStyleSheet("color: #9CA3AF; font-style: italic;")
        self.no_selection_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.no_selection_label.setWordWrap(True)
        layout.addWidget(self.no_selection_label)
        
        # Properties form
        self.form_widget = QtWidgets.QWidget()
        self.form_layout = QtWidgets.QFormLayout(self.form_widget)
        self.form_layout.setSpacing(8)
        
        # ID (read-only)
        self.id_label = QtWidgets.QLabel()
        self.form_layout.addRow("ID:", self.id_label)
        
        # Label
        self.label_input = QtWidgets.QLineEdit()
        self.label_input.textChanged.connect(self._on_property_changed)
        self.form_layout.addRow("Label:", self.label_input)
        
        # Icon
        self.icon_input = QtWidgets.QLineEdit()
        self.icon_input.setPlaceholderText("tabler-icon-name")
        self.icon_input.textChanged.connect(self._on_property_changed)
        self.form_layout.addRow("Icon:", self.icon_input)
        
        # Tooltip
        self.tooltip_input = QtWidgets.QLineEdit()
        self.tooltip_input.textChanged.connect(self._on_property_changed)
        self.form_layout.addRow("Tooltip:", self.tooltip_input)
        
        # Command ID
        self.command_combo = QtWidgets.QComboBox()
        self.command_combo.addItem("(None)", None)
        for cmd_id, cmd_spec in COMMAND_LIBRARY.items():
            self.command_combo.addItem(cmd_spec.name, cmd_id)
        self.command_combo.currentIndexChanged.connect(self._on_property_changed)
        self.form_layout.addRow("Command:", self.command_combo)
        
        # === Macro Assignment Section ===
        macro_header = QtWidgets.QLabel("Recorded Macro")
        macro_header.setStyleSheet("font-size: 12px; font-weight: 600; color: #6B7280; margin-top: 16px;")
        self.form_layout.addRow(macro_header)
        
        self.macro_combo = QtWidgets.QComboBox()
        self.macro_combo.addItem("(None)", None)
        self._refresh_macro_combo()
        self.macro_combo.currentIndexChanged.connect(self._on_macro_selected)
        self.form_layout.addRow("Macro:", self.macro_combo)
        
        # Macro info
        self.macro_info = QtWidgets.QLabel()
        self.macro_info.setStyleSheet("font-size: 11px; color: #6B7280;")
        self.macro_info.setWordWrap(True)
        self.form_layout.addRow(self.macro_info)
        
        self.form_widget.hide()
        layout.addWidget(self.form_widget)
        
        layout.addStretch()
        
    def _refresh_macro_combo(self):
        """Refresh the macro dropdown list."""
        self.macro_combo.clear()
        self.macro_combo.addItem("(None)", None)

        from lib_utils.paths import OM_MACROS_DIR
        macros_dir = OM_MACROS_DIR
        if not macros_dir.exists():
            return
            
        index_file = macros_dir / "macro_index.json"
        if index_file.exists():
            try:
                with open(index_file) as f:
                    index = json.load(f)
                for macro_id, info in index.get("macros", {}).items():
                    name = info.get("name", macro_id)
                    self.macro_combo.addItem(name, macro_id)
            except Exception:
                pass
                
    def _on_property_changed(self):
        """Handle property change."""
        if self.current_item:
            self.current_item.label = self.label_input.text()
            self.current_item.icon = self.icon_input.text() or None
            self.current_item.tooltip = self.tooltip_input.text()
            self.current_item.command_id = self.command_combo.currentData()
            self.item_updated.emit(self.current_item.id)
            
    def _on_macro_selected(self):
        """Handle macro selection."""
        if self.current_item:
            macro_id = self.macro_combo.currentData()
            self.current_item.macro_id = macro_id
            
            # Update info label
            if macro_id:
                self.macro_info.setText(f"Will execute: {macro_id}")
            else:
                self.macro_info.setText("")
                
            self.item_updated.emit(self.current_item.id)
            
    def set_item(self, item: MenuItemDef | None):
        """Set the current item to edit."""
        self.current_item = item
        
        if item is None:
            self.no_selection_label.show()
            self.form_widget.hide()
            return
            
        self.no_selection_label.hide()
        self.form_widget.show()
        
        # Populate fields
        self.id_label.setText(item.id)
        self.id_label.setStyleSheet("font-family: monospace; color: #6B7280;")
        self.label_input.setText(item.label)
        self.icon_input.setText(item.icon or "")
        self.tooltip_input.setText(item.tooltip)
        
        # Set command combo
        if item.command_id:
            index = self.command_combo.findData(item.command_id)
            if index >= 0:
                self.command_combo.setCurrentIndex(index)
        else:
            self.command_combo.setCurrentIndex(0)
            
        # Set macro combo
        if item.macro_id:
            index = self.macro_combo.findData(item.macro_id)
            if index >= 0:
                self.macro_combo.setCurrentIndex(index)
        else:
            self.macro_combo.setCurrentIndex(0)


# =============================================================================
# MAIN TOOLBOX BUILDER WIDGET
# =============================================================================

class ToolboxBuilderWidget(QtWidgets.QWidget):
    """
    Main toolbox builder widget with three-panel layout.
    Provides visual editing of gui-toolbox.conf.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_config = ToolboxConfig()
        self._pending_widget_macro: str | None = None
        self._pending_widget_type: str | None = None
        self._setup_ui()
        self._load_existing_config()
        
    def _setup_ui(self):
        """Set up the three-panel layout."""
        self.setWindowTitle("Toolbox Editor")
        self.setMinimumSize(900, 600)
        
        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # === LEFT: Widget Palette ===
        self.palette = WidgetPalette()
        self.palette.setFixedWidth(240)
        self.palette.widget_selected.connect(self._on_palette_item_selected)
        main_layout.addWidget(self.palette)
        
        # Divider
        divider1 = QtWidgets.QFrame()
        divider1.setFixedWidth(1)
        divider1.setStyleSheet("background: #E5E7EB;")
        main_layout.addWidget(divider1)
        
        # === CENTER: Design Canvas ===
        self.canvas = DesignCanvas()
        self.canvas.item_dropped.connect(self._on_item_dropped)
        self.canvas.item_selected.connect(self._on_canvas_item_selected)
        main_layout.addWidget(self.canvas, stretch=1)
        
        # Divider
        divider2 = QtWidgets.QFrame()
        divider2.setFixedWidth(1)
        divider2.setStyleSheet("background: #E5E7EB;")
        main_layout.addWidget(divider2)
        
        # === RIGHT: Properties Panel ===
        self.properties = PropertiesPanel()
        self.properties.setFixedWidth(280)
        self.properties.item_updated.connect(self._on_item_updated)
        main_layout.addWidget(self.properties)
        
        # === BOTTOM: Action Buttons ===
        # Add a widget overlay for save/load buttons
        self._create_action_bar()
        
    def _create_action_bar(self):
        """Create floating action bar for save/load."""
        self.action_bar = QtWidgets.QFrame(self)
        self.action_bar.setStyleSheet("""
            QFrame {
                background: white;
                border: 1px solid #E5E7EB;
                border-radius: 8px;
            }
        """)
        
        layout = QtWidgets.QHBoxLayout(self.action_bar)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 8, 12, 8)
        
        # Save button
        save_btn = QtWidgets.QPushButton("Save")
        save_btn.setStyleSheet("""
            QPushButton {
                background: #3B82F6;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                color: white;
                font-weight: 500;
            }
            QPushButton:hover { background: #2563EB; }
        """)
        save_btn.clicked.connect(self._save_config)
        layout.addWidget(save_btn)
        
        # Load button
        load_btn = QtWidgets.QPushButton("Load")
        load_btn.setStyleSheet("""
            QPushButton {
                background: white;
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 6px 16px;
            }
            QPushButton:hover { background: #F3F4F6; }
        """)
        load_btn.clicked.connect(self._load_config)
        layout.addWidget(load_btn)
        
        # Reset button
        reset_btn = QtWidgets.QPushButton("Reset")
        reset_btn.setStyleSheet("""
            QPushButton {
                background: white;
                border: 1px solid #EF4444;
                border-radius: 4px;
                padding: 6px 16px;
                color: #EF4444;
            }
            QPushButton:hover { background: #FEF2F2; }
        """)
        reset_btn.clicked.connect(self._reset_config)
        layout.addWidget(reset_btn)
        
        layout.addStretch()
        
        # Status label
        self.status_label = QtWidgets.QLabel("Ready")
        self.status_label.setStyleSheet("color: #6B7280; font-size: 12px;")
        layout.addWidget(self.status_label)
        
    def resizeEvent(self, event):
        """Position the action bar at bottom."""
        super().resizeEvent(event)
        margin = 16
        bar_height = 48
        self.action_bar.setGeometry(
            margin, 
            self.height() - bar_height - margin,
            self.width() - (margin * 2),
            bar_height
        )
        
    def _load_existing_config(self):
        """Load existing config if available."""
        try:
            if DEFAULT_TOOLBOX_CONFIG_PATH.exists():
                self.current_config = load_toolbox_config()
                self.canvas.set_config(self.current_config)
                self.status_label.setText(f"Loaded: {self.current_config.name}")
        except Exception as e:
            self.status_label.setText(f"Error loading: {e}")
            
    def _on_item_dropped(self, data: dict):
        """Handle item dropped on canvas."""
        import uuid
        
        item_id = f"item_{uuid.uuid4().hex[:8]}"
        
        if data.get("type") == "button":
            btn_id = data.get("button_id")
            if btn_id in BUTTON_LIBRARY:
                btn_def = BUTTON_LIBRARY[btn_id]
                item = MenuItemDef(
                    id=item_id,
                    label=btn_def.label,
                    widget_type=WidgetType.BUTTON,
                    location=MenuLocation.TOOLBAR,
                    icon=btn_def.icon,
                    tooltip=btn_def.tooltip,
                    command_id=btn_def.command.id
                )
                self.current_config.items[item_id] = item
                self.canvas.add_item_to_toolbar(item)
                self.properties.set_item(item)
                
        elif data.get("type") == "macro":
            macro_id = data.get("macro_id")
            macro_name = data.get("macro_name", macro_id)
            item = MenuItemDef(
                id=item_id,
                label=macro_name,
                widget_type=WidgetType.BUTTON,
                location=MenuLocation.TOOLBAR,
                icon="player-play",
                macro_id=macro_id
            )
            self.current_config.items[item_id] = item
            self.canvas.add_item_to_toolbar(item)
            self.properties.set_item(item)
            
        elif data.get("type") == "widget":
            widget_type = WidgetType(data.get("widget_type"))
            label = data.get("widget_label", "New Item")
            item = MenuItemDef(
                id=item_id,
                label=label,
                widget_type=widget_type,
                location=MenuLocation.TOOLBAR
            )
            dropped_widget_type = data.get("widget_type")
            if self._pending_widget_macro and self._pending_widget_type == dropped_widget_type:
                item.macro_id = self._pending_widget_macro
            self._pending_widget_macro = None
            self._pending_widget_type = None
            self.current_config.items[item_id] = item
            self.canvas.add_item_to_toolbar(item)
            self.properties.set_item(item)
            
        self.status_label.setText(f"Added: {item_id}")
        
    def _on_palette_item_selected(self, item_def):
        """Handle palette item selection - show in properties panel."""
        self._pending_widget_macro = item_def.macro_id
        self._pending_widget_type = item_def.widget_type.value
        self.properties.set_item(item_def)
        self.status_label.setText(f"Selected: {item_def.label}")
        
    def _on_canvas_item_selected(self, item_id: str):
        """Handle item selection on canvas."""
        self._pending_widget_macro = None
        self._pending_widget_type = None
        if item_id in self.current_config.items:
            self.properties.set_item(self.current_config.items[item_id])
        else:
            self.properties.set_item(None)
            
    def _on_item_updated(self, item_id: str):
        """Handle item property update."""
        # Capture macro changes for palette items not yet dropped
        if item_id not in self.current_config.items:
            if self.properties.current_item:
                self._pending_widget_macro = self.properties.current_item.macro_id
                self._pending_widget_type = self.properties.current_item.widget_type.value
        # Refresh canvas to show updated label
        self.canvas.set_config(self.current_config)
        self.status_label.setText(f"Updated: {item_id}")
        
    def _save_config(self):
        """Save configuration to gui-toolbox.conf."""
        try:
            self.current_config.name = "custom_toolbox"
            save_toolbox_config(self.current_config)
            self.status_label.setText(f"Saved to: {DEFAULT_TOOLBOX_CONFIG_PATH}")
        except Exception as e:
            self.status_label.setText(f"Save failed: {e}")
            
    def _load_config(self):
        """Load configuration from file."""
        filepath, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Load Toolbox Config",
            str(DEFAULT_TOOLBOX_CONFIG_PATH.parent),
            "Config Files (*.conf *.json)"
        )
        if filepath:
            try:
                self.current_config = load_toolbox_config(Path(filepath))
                self.canvas.set_config(self.current_config)
                self.status_label.setText(f"Loaded: {filepath}")
            except Exception as e:
                self.status_label.setText(f"Load failed: {e}")
                
    def _reset_config(self):
        """Reset to empty configuration."""
        reply = QtWidgets.QMessageBox.question(
            self, "Reset Configuration",
            "Clear all items and start over?",
            QtWidgets.QMessageBox.StandardButton.Yes | 
            QtWidgets.QMessageBox.StandardButton.No
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            self.current_config = ToolboxConfig()
            self.canvas.set_config(self.current_config)
            self.properties.set_item(None)
            self.status_label.setText("Reset to empty")


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def main():
    """Standalone entry point for testing."""
    import sys
    from PySide6 import QtWidgets
    
    app = QtWidgets.QApplication(sys.argv)
    
    # Set application style
    app.setStyle("Fusion")
    
    # Create and show toolbox builder
    builder = ToolboxBuilderWidget()
    builder.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
