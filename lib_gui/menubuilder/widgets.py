"""
UI widgets for the menu builder.
Provides draggable tiles, drop zones, and category panels.
"""

from __future__ import annotations

from typing import Callable

from PySide6 import QtCore, QtGui, QtWidgets

from lib_gui.icons import load_icon_colorized

from .models import ButtonDef, CategoryDef


def load_svg_icon(icon_name: str, size: int = 16, color: str = "#4B5563") -> QtGui.QIcon:
    """Load and colorize an SVG icon from the zipped icon bundle."""
    return load_icon_colorized(icon_name, size=size, color=color)


class DraggableTile(QtWidgets.QPushButton):
    """
    A draggable tile representing a button definition.
    Can be dragged from the palette to the toolbar builder.
    """

    # Signals
    tile_dragged = QtCore.Signal(ButtonDef)  # Emitted when drag starts
    tile_clicked = QtCore.Signal(ButtonDef)  # Emitted on click (for non-drag selection)

    def __init__(self, button_def: ButtonDef, parent=None, compact: bool = False):
        super().__init__(parent)
        self.button_def = button_def
        self.compact = compact
        self._drag_start_pos = None

        self._setup_ui()

    def _setup_ui(self):
        """Configure the tile appearance."""
        if self.compact:
            # Compact mode: icon only, small button
            self.setFixedSize(28, 28)
            self.setIcon(load_svg_icon(self.button_def.icon, 16, "#4B5563"))
            self.setIconSize(QtCore.QSize(16, 16))
            self.setToolTip(f"{self.button_def.label}\n{self.button_def.tooltip or ''}")
        else:
            # Full mode: icon + text
            self.setText(f"  {self.button_def.label}")
            self.setIcon(load_svg_icon(self.button_def.icon, 14, "#4B5563"))
            self.setIconSize(QtCore.QSize(14, 14))
            self.setFixedHeight(32)

        self.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))

        # Styling based on category color
        self._apply_style()

        self.clicked.connect(self._on_clicked)

    def _apply_style(self):
        """Apply visual style to the tile."""
        color = self.button_def.color or "#F3F4F6"

        if self.compact:
            # Compact: subtle border, colored background
            self.setStyleSheet(f"""
                QPushButton {{
                    background: {color};
                    border: 1px solid rgba(0,0,0,0.08);
                    border-radius: 4px;
                    padding: 0;
                }}
                QPushButton:hover {{
                    background: {self._darken(color, 0.95)};
                    border-color: rgba(0,0,0,0.15);
                }}
                QPushButton:pressed {{
                    background: {self._darken(color, 0.9)};
                }}
            """)
        else:
            # Full: white background with subtle border
            self.setStyleSheet("""
                QPushButton {
                    background: white;
                    border: 1px solid #E5E7EB;
                    border-radius: 6px;
                    padding: 0 12px;
                    font-size: 12px;
                    color: #374151;
                    text-align: left;
                }
                QPushButton:hover {
                    background: #F3F4F6;
                    border-color: #D1D5DB;
                }
                QPushButton:pressed {
                    background: #E5E7EB;
                }
            """)

    def _darken(self, hex_color: str, factor: float) -> str:
        """Darken a hex color by a factor."""
        c = QtGui.QColor(hex_color)
        h, s, l, a = c.getHsl()
        return QtGui.QColor.fromHsl(h, s, int(l * factor), a).name()

    def _on_clicked(self):
        """Handle click - emit the tile_clicked signal."""
        self.tile_clicked.emit(self.button_def)

    # === Drag and Drop Support ===

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        if not (event.buttons() & QtCore.Qt.MouseButton.LeftButton):
            return

        if self._drag_start_pos is None:
            return

        # Check if we've moved enough to start a drag
        distance = (event.pos() - self._drag_start_pos).manhattanLength()
        if distance < QtWidgets.QApplication.startDragDistance():
            return

        # Start drag operation
        self._start_drag()

    def _start_drag(self):
        """Initiate a drag operation with the button definition."""
        drag = QtGui.QDrag(self)
        mime_data = QtCore.QMimeData()

        # Serialize button def to JSON for mime data
        import json
        mime_data.setText(json.dumps(self.button_def.to_dict()))
        mime_data.setData("application/x-menubuilder-tile", json.dumps(self.button_def.to_dict()).encode())

        drag.setMimeData(mime_data)

        # Create drag pixmap (visual feedback)
        pixmap = self.grab()
        drag.setPixmap(pixmap)
        drag.setHotSpot(QtCore.QPoint(pixmap.width() // 2, pixmap.height() // 2))

        self.tile_dragged.emit(self.button_def)

        # Execute drag
        drag.exec(QtCore.Qt.DropAction.CopyAction)


class TileDropZone(QtWidgets.QFrame):
    """
    A drop zone where tiles can be dropped to build a toolbar.
    Shows the current toolbar configuration with draggable reordering.
    """

    # Signals
    button_added = QtCore.Signal(ButtonDef)      # Button added via drop
    button_removed = QtCore.Signal(ButtonDef)    # Button removed
    button_reordered = QtCore.Signal(list)       # Buttons reordered [ButtonDef, ...]
    buttons_changed = QtCore.Signal(list)        # Any change to buttons

    def __init__(self, parent=None):
        super().__init__(parent)
        self.buttons: list[ButtonDef] = []
        self.tiles: list[DraggableTile] = []
        self._drag_insert_index = -1

        self._setup_ui()
        self.setAcceptDrops(True)

    def _setup_ui(self):
        """Configure the drop zone appearance."""
        self.setMinimumHeight(60)
        self.setStyleSheet("""
            QFrame {
                background: #F3F4F6;
                border-radius: 8px;
                border: 2px dashed #D1D5DB;
            }
            QFrame[active="true"] {
                border-color: #3B82F6;
                background: #EFF6FF;
            }
        """)

        # Horizontal layout for tiles
        self.layout = QtWidgets.QHBoxLayout(self)
        self.layout.setSpacing(6)
        self.layout.setContentsMargins(12, 12, 12, 12)
        self.layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)

        # Empty state label
        self.empty_label = QtWidgets.QLabel("Drag tiles here to build your toolbar...")
        self.empty_label.setStyleSheet("font-size: 12px; color: #9CA3AF; font-style: italic;")
        self.layout.addWidget(self.empty_label)
        self.layout.addStretch()

    def add_button(self, button_def: ButtonDef) -> None:
        """Add a button to the toolbar."""
        # Hide empty label
        if self.empty_label.isVisible():
            self.empty_label.hide()

        # Create compact tile
        tile = self._create_toolbar_tile(button_def)

        # Insert before stretch
        index = self.layout.count() - 1  # Before stretch
        self.layout.insertWidget(index, tile)

        self.buttons.append(button_def)
        self.tiles.append(tile)

        self.buttons_changed.emit(self.buttons.copy())

    def _create_toolbar_tile(self, button_def: ButtonDef) -> QtWidgets.QWidget:
        """Create a tile widget for the toolbar with remove capability."""
        # Container for tile + remove button
        container = QtWidgets.QFrame()
        container.setStyleSheet("background: transparent; border: none;")
        container.setFixedSize(32, 32)  # Compact container

        layout = QtWidgets.QHBoxLayout(container)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # The tile button
        tile = DraggableTile(button_def, container, compact=True)
        tile.setFixedSize(28, 28)
        tile.tile_clicked.connect(lambda: self._remove_button(button_def, container))

        # Add context menu for removal
        tile.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        tile.customContextMenuRequested.connect(lambda pos: self._show_tile_menu(pos, button_def, container))

        layout.addWidget(tile)

        return container

    def _show_tile_menu(self, pos, button_def: ButtonDef, container: QtWidgets.QWidget):
        """Show context menu for a tile."""
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

        remove_action = menu.addAction(f"Remove '{button_def.label}'")
        remove_action.triggered.connect(lambda: self._remove_button(button_def, container))

        menu.addSeparator()

        move_left = menu.addAction("Move Left")
        move_left.triggered.connect(lambda: self._move_button(button_def, -1))
        move_left.setEnabled(self.buttons.index(button_def) > 0)

        move_right = menu.addAction("Move Right")
        move_right.triggered.connect(lambda: self._move_button(button_def, 1))
        move_right.setEnabled(self.buttons.index(button_def) < len(self.buttons) - 1)

        menu.exec(QtGui.QCursor.pos())

    def _remove_button(self, button_def: ButtonDef, container: QtWidgets.QWidget):
        """Remove a button from the toolbar."""
        # Remove from layout
        self.layout.removeWidget(container)
        container.deleteLater()

        # Remove from lists
        if button_def in self.buttons:
            idx = self.buttons.index(button_def)
            self.buttons.pop(idx)
            if idx < len(self.tiles):
                self.tiles.pop(idx)

        # Show empty label if no buttons
        if not self.buttons:
            self.empty_label.show()

        self.button_removed.emit(button_def)
        self.buttons_changed.emit(self.buttons.copy())

    def _move_button(self, button_def: ButtonDef, direction: int):
        """Move a button left or right."""
        idx = self.buttons.index(button_def)
        new_idx = idx + direction

        if 0 <= new_idx < len(self.buttons):
            # Reorder lists
            self.buttons.insert(new_idx, self.buttons.pop(idx))

            # Rebuild layout
            self._rebuild_layout()

            self.button_reordered.emit(self.buttons.copy())
            self.buttons_changed.emit(self.buttons.copy())

    def _rebuild_layout(self):
        """Rebuild the layout from the buttons list."""
        # Clear layout
        while self.layout.count() > 1:  # Keep stretch
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Rebuild tiles
        self.tiles = []
        for button_def in self.buttons:
            tile = self._create_toolbar_tile(button_def)
            index = self.layout.count() - 1
            self.layout.insertWidget(index, tile)

        # Show/hide empty label
        if self.buttons:
            self.empty_label.hide()
        else:
            self.empty_label.show()

    def clear(self):
        """Remove all buttons."""
        self.buttons.clear()
        self._rebuild_layout()
        self.buttons_changed.emit([])

    def set_buttons(self, buttons: list[ButtonDef]):
        """Set the complete button list."""
        self.buttons = list(buttons)
        self._rebuild_layout()
        self.buttons_changed.emit(self.buttons.copy())

    # === Drag and Drop Support ===

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent):
        """Accept drag if it contains tile data."""
        if event.mimeData().hasFormat("application/x-menubuilder-tile") or event.mimeData().hasText():
            event.acceptProposedAction()
            self.setProperty("active", "true")
            self.style().unpolish(self)
            self.style().polish(self)
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QtGui.QDragLeaveEvent):
        """Reset appearance when drag leaves."""
        self.setProperty("active", "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, event: QtGui.QDropEvent):
        """Handle drop - add the button to the toolbar."""
        import json

        self.setProperty("active", "false")
        self.style().unpolish(self)
        self.style().polish(self)

        # Get button data from mime
        data = None
        if event.mimeData().hasFormat("application/x-menubuilder-tile"):
            data = json.loads(bytes(event.mimeData().data("application/x-menubuilder-tile")).decode())
        elif event.mimeData().hasText():
            data = json.loads(event.mimeData().text())

        if data:
            button_def = ButtonDef.from_dict(data)
            self.add_button(button_def)
            self.button_added.emit(button_def)
            event.acceptProposedAction()


class CategoryPanel(QtWidgets.QFrame):
    """
    A panel showing buttons from a category.
    Contains draggable tiles for each button.
    """

    button_selected = QtCore.Signal(ButtonDef)  # Button clicked/selected

    def __init__(self, category: CategoryDef, parent=None):
        super().__init__(parent)
        self.category = category
        self._setup_ui()

    def _setup_ui(self):
        """Set up the panel UI."""
        self.setStyleSheet("background: transparent;")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(0, 0, 0, 16)

        # Category header
        header = QtWidgets.QLabel(self.category.name)
        header.setStyleSheet(f"""
            font-size: 11px;
            font-weight: 600;
            color: #6B7280;
            text-transform: uppercase;
            padding: 8px 0 4px 0;
            border-bottom: 1px solid #E5E7EB;
            margin-bottom: 8px;
        """)
        layout.addWidget(header)

        # Button tiles
        flow_widget = QtWidgets.QWidget()
        flow_layout = QtWidgets.QFlowLayout(flow_widget) if hasattr(QtWidgets, 'QFlowLayout') else QtWidgets.QVBoxLayout(flow_widget)
        flow_layout.setSpacing(6)
        flow_layout.setContentsMargins(0, 0, 0, 0)

        for btn_def in self.category.buttons:
            tile = DraggableTile(btn_def, compact=False)
            tile.tile_clicked.connect(self.button_selected.emit)
            flow_layout.addWidget(tile)

        layout.addWidget(flow_widget)


class ButtonPalette(QtWidgets.QScrollArea):
    """
    Scrollable palette of available buttons organized by category.
    """

    button_selected = QtCore.Signal(ButtonDef)

    def __init__(self, categories: list[CategoryDef], parent=None):
        super().__init__(parent)
        self.categories = categories
        self._setup_ui()

    def _setup_ui(self):
        """Set up the palette UI."""
        self.setWidgetResizable(True)
        self.setStyleSheet("background: transparent; border: none;")
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Container
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.setSpacing(4)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        # Add category panels
        for category in self.categories:
            panel = CategoryPanel(category)
            panel.button_selected.connect(self.button_selected.emit)
            layout.addWidget(panel)

        layout.addStretch()
        self.setWidget(container)
