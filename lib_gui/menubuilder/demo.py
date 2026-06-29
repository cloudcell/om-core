"""
Menu Builder Demo - A comprehensive toolbar editor for OpenM

Run with:
    cd <project root folder>
    source ./venv/bin/activate
    python -m lib_gui.menubuilder.demo

Features:
- Drag and drop button tiles to build custom toolbars
- Save/load toolbar configurations as JSON
- Professional UI following design from demo_format_composer.py
- Support for multiple button categories (formatting, navigation, data, etc.)
- Standardized command system
"""

from __future__ import annotations

import sys
from pathlib import Path

from lib_utils.paths import OM_TOOLBARS_DIR

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PySide6 import QtCore, QtGui, QtWidgets

from lib_gui.menubuilder.models import (
    ButtonDef, ToolbarConfig, CategoryDef,
    DEFAULT_CATEGORIES, BUTTON_LIBRARY
)
from lib_gui.menubuilder.persistence import (
    save_toolbar, load_toolbar, list_saved_toolbars, delete_toolbar
)
from lib_gui.menubuilder.widgets import (
    DraggableTile, TileDropZone, load_svg_icon
)


class ToolbarBuilderWidget(QtWidgets.QWidget):
    """Main builder widget with palette and drop zone."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_config = ToolbarConfig("New Toolbar")
        self.categories = DEFAULT_CATEGORIES.copy()
        self._unsaved_changes = False

        self._setup_ui()
        self._populate_saved_toolbars()

    def _setup_ui(self):
        """Set up the builder UI."""
        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # === LEFT SIDEBAR: Button Palette ===
        sidebar = self._create_sidebar()
        main_layout.addWidget(sidebar)

        # === DIVIDER ===
        divider = QtWidgets.QFrame()
        divider.setFixedWidth(1)
        divider.setStyleSheet("background: #E5E7EB;")
        main_layout.addWidget(divider)

        # === RIGHT AREA: Builder Canvas ===
        builder = self._create_builder_area()
        main_layout.addWidget(builder, stretch=1)

    def _create_sidebar(self) -> QtWidgets.QFrame:
        """Create the left sidebar with button palette."""
        sidebar = QtWidgets.QFrame()
        sidebar.setFixedWidth(260)
        sidebar.setStyleSheet("background: #FAFAFA;")

        layout = QtWidgets.QVBoxLayout(sidebar)
        layout.setSpacing(0)
        layout.setContentsMargins(16, 16, 16, 16)

        # Header
        title = QtWidgets.QLabel("Button Palette")
        title.setStyleSheet("font-size: 14px; font-weight: 600; color: #1F2937; margin-bottom: 4px;")
        layout.addWidget(title)

        subtitle = QtWidgets.QLabel("Drag buttons to the toolbar")
        subtitle.setStyleSheet("font-size: 11px; color: #6B7280; margin-bottom: 16px;")
        layout.addWidget(subtitle)

        # Search box
        self.search_box = QtWidgets.QLineEdit()
        self.search_box.setPlaceholderText("Search buttons...")
        self.search_box.setStyleSheet("""
            QLineEdit {
                background: white;
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12px;
                margin-bottom: 12px;
            }
            QLineEdit:focus {
                border-color: #3B82F6;
            }
        """)
        self.search_box.textChanged.connect(self._filter_buttons)
        layout.addWidget(self.search_box)

        # Scrollable palette
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.palette_content = QtWidgets.QWidget()
        self.palette_layout = QtWidgets.QVBoxLayout(self.palette_content)
        self.palette_layout.setSpacing(12)
        self.palette_layout.setContentsMargins(0, 0, 4, 0)
        self.palette_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        self._build_palette()

        scroll.setWidget(self.palette_content)
        layout.addWidget(scroll)

        return sidebar

    def _build_palette(self):
        """Build the button palette from categories."""
        # Clear existing
        while self.palette_layout.count():
            item = self.palette_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for category in self.categories:
            # Category header
            header = QtWidgets.QLabel(category.name)
            header.setStyleSheet(f"""
                font-size: 11px;
                font-weight: 600;
                color: #6B7280;
                text-transform: uppercase;
                padding: 8px 0 4px 0;
                border-bottom: 1px solid #E5E7EB;
                margin-bottom: 8px;
                background: {category.color}20;
            """)
            self.palette_layout.addWidget(header)

            # Button grid
            grid = QtWidgets.QWidget()
            grid_layout = QtWidgets.QVBoxLayout(grid)
            grid_layout.setSpacing(6)
            grid_layout.setContentsMargins(0, 0, 0, 8)

            for btn in category.buttons:
                tile = DraggableTile(btn, compact=False)
                tile.tile_clicked.connect(self._on_palette_click)
                tile.setObjectName(f"tile_{btn.id}")
                grid_layout.addWidget(tile)

            self.palette_layout.addWidget(grid)

        self.palette_layout.addStretch()

    def _filter_buttons(self, text: str):
        """Filter buttons by search text."""
        text = text.lower()

        for i in range(self.palette_layout.count()):
            widget = self.palette_layout.itemAt(i).widget()
            if widget and widget.objectName().startswith("tile_"):
                btn_id = widget.objectName().replace("tile_", "")
                btn = BUTTON_LIBRARY.get(btn_id)
                if btn:
                    matches = (text in btn.label.lower() or
                              text in btn.tooltip.lower() or
                              text in btn.category.lower())
                    widget.setVisible(matches)

    def _create_builder_area(self) -> QtWidgets.QFrame:
        """Create the main builder canvas."""
        builder = QtWidgets.QFrame()
        builder.setStyleSheet("background: white;")

        layout = QtWidgets.QVBoxLayout(builder)
        layout.setSpacing(20)
        layout.setContentsMargins(32, 32, 32, 32)

        # === Toolbar Name Section ===
        name_row = QtWidgets.QHBoxLayout()

        name_label = QtWidgets.QLabel("Toolbar Name:")
        name_label.setStyleSheet("font-size: 12px; font-weight: 600; color: #374151;")
        name_row.addWidget(name_label)

        self.name_input = QtWidgets.QLineEdit(self.current_config.name)
        self.name_input.setStyleSheet("""
            QLineEdit {
                background: white;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 13px;
                max-width: 300px;
            }
            QLineEdit:focus {
                border-color: #3B82F6;
            }
        """)
        self.name_input.textChanged.connect(self._on_name_changed)
        name_row.addWidget(self.name_input)

        name_row.addStretch()
        layout.addLayout(name_row)

        # === Saved Toolbars Dropdown ===
        saved_row = QtWidgets.QHBoxLayout()

        saved_label = QtWidgets.QLabel("Saved Toolbars:")
        saved_label.setStyleSheet("font-size: 12px; color: #6B7280;")
        saved_row.addWidget(saved_label)

        self.saved_combo = QtWidgets.QComboBox()
        self.saved_combo.setStyleSheet("""
            QComboBox {
                background: white;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 12px;
                min-width: 200px;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 4px solid #6B7280;
            }
        """)
        self.saved_combo.currentIndexChanged.connect(self._on_saved_selected)
        saved_row.addWidget(self.saved_combo)

        load_btn = QtWidgets.QPushButton("Load")
        load_btn.setStyleSheet("""
            QPushButton {
                background: white;
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 12px;
                color: #4B5563;
            }
            QPushButton:hover {
                background: #F3F4F6;
            }
        """)
        load_btn.clicked.connect(self._load_selected_toolbar)
        saved_row.addWidget(load_btn)

        delete_btn = QtWidgets.QPushButton("Delete")
        delete_btn.setStyleSheet("""
            QPushButton {
                background: white;
                border: 1px solid #EF4444;
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 12px;
                color: #EF4444;
            }
            QPushButton:hover {
                background: #FEF2F2;
            }
        """)
        delete_btn.clicked.connect(self._delete_selected_toolbar)
        saved_row.addWidget(delete_btn)

        saved_row.addStretch()
        layout.addLayout(saved_row)

        # === Divider ===
        divider = QtWidgets.QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background: #E5E7EB;")
        layout.addWidget(divider)

        # === Drop Zone Section ===
        dz_label = QtWidgets.QLabel("Your Toolbar")
        dz_label.setStyleSheet("font-size: 12px; font-weight: 600; color: #6B7280; text-transform: uppercase;")
        layout.addWidget(dz_label)

        # Drop zone
        self.drop_zone = TileDropZone()
        self.drop_zone.buttons_changed.connect(self._on_buttons_changed)
        self.drop_zone.setMinimumHeight(80)
        layout.addWidget(self.drop_zone)

        # Hint text
        hint = QtWidgets.QLabel("Tip: Drag buttons from the left, or click palette buttons to add. Right-click tiles to remove or reorder.")
        hint.setStyleSheet("font-size: 11px; color: #9CA3AF; margin-top: 4px;")
        layout.addWidget(hint)

        # === Quick Add Buttons ===
        quick_label = QtWidgets.QLabel("Quick Add (Click to add):")
        quick_label.setStyleSheet("font-size: 12px; font-weight: 600; color: #6B7280; text-transform: uppercase; margin-top: 16px;")
        layout.addWidget(quick_label)

        quick_row = QtWidgets.QHBoxLayout()
        quick_row.setSpacing(6)

        # Add some commonly used buttons as quick-add
        quick_buttons = [
            BUTTON_LIBRARY.get("copy"),
            BUTTON_LIBRARY.get("paste"),
            BUTTON_LIBRARY.get("bold"),
            BUTTON_LIBRARY.get("recalc"),
        ]
        for btn in quick_buttons:
            if btn:
                tile = DraggableTile(btn, compact=True)
                tile.setFixedSize(28, 28)
                tile.tile_clicked.connect(self._on_palette_click)
                quick_row.addWidget(tile)

        quick_row.addStretch()
        layout.addLayout(quick_row)

        # === Action Buttons ===
        actions = QtWidgets.QHBoxLayout()
        actions.setSpacing(8)

        self.new_btn = QtWidgets.QPushButton("New")
        self.new_btn.setStyleSheet("""
            QPushButton {
                background: white;
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 12px;
                color: #4B5563;
            }
            QPushButton:hover {
                background: #F3F4F6;
            }
        """)
        self.new_btn.clicked.connect(self._new_toolbar)
        actions.addWidget(self.new_btn)

        self.clear_btn = QtWidgets.QPushButton("Clear All")
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background: white;
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 12px;
                color: #4B5563;
            }
            QPushButton:hover {
                background: #F3F4F6;
                border-color: #9CA3AF;
            }
        """)
        self.clear_btn.clicked.connect(self._clear_all)
        actions.addWidget(self.clear_btn)

        actions.addStretch()

        self.save_btn = QtWidgets.QPushButton("Save Toolbar")
        self.save_btn.setStyleSheet("""
            QPushButton {
                background: #3B82F6;
                border: none;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 12px;
                color: white;
                font-weight: 500;
            }
            QPushButton:hover {
                background: #2563EB;
            }
        """)
        self.save_btn.clicked.connect(self._save_toolbar)
        actions.addWidget(self.save_btn)

        self.export_btn = QtWidgets.QPushButton("Export...")
        self.export_btn.setStyleSheet("""
            QPushButton {
                background: white;
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 12px;
                color: #4B5563;
            }
            QPushButton:hover {
                background: #F3F4F6;
            }
        """)
        self.export_btn.clicked.connect(self._export_toolbar)
        actions.addWidget(self.export_btn)

        layout.addLayout(actions)

        # === Status Bar ===
        self.status_label = QtWidgets.QLabel("Ready")
        self.status_label.setStyleSheet("font-size: 11px; color: #9CA3AF; margin-top: 8px;")
        layout.addWidget(self.status_label)

        layout.addStretch()

        return builder

    def _on_palette_click(self, button_def: ButtonDef):
        """Handle click on palette button - add to toolbar."""
        self.drop_zone.add_button(button_def)
        self._mark_unsaved()

    def _on_buttons_changed(self, buttons: list[ButtonDef]):
        """Update current config when buttons change."""
        self.current_config.buttons = buttons
        self._mark_unsaved()

    def _on_name_changed(self, name: str):
        """Update toolbar name."""
        self.current_config.name = name or "New Toolbar"
        self._mark_unsaved()

    def _mark_unsaved(self):
        """Mark the current config as having unsaved changes."""
        self._unsaved_changes = True
        self._update_status()

    def _update_status(self):
        """Update the status label."""
        count = len(self.current_config.buttons)
        name = self.current_config.name
        modified = " *" if self._unsaved_changes else ""
        self.status_label.setText(f"{name}{modified} - {count} button(s)")

    def _new_toolbar(self):
        """Create a new empty toolbar."""
        if self._unsaved_changes:
            reply = QtWidgets.QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Discard them?",
                QtWidgets.QMessageBox.StandardButton.Yes |
                QtWidgets.QMessageBox.StandardButton.No
            )
            if reply != QtWidgets.QMessageBox.StandardButton.Yes:
                return

        self.current_config = ToolbarConfig("New Toolbar")
        self.name_input.setText(self.current_config.name)
        self.drop_zone.clear()
        self._unsaved_changes = False
        self._update_status()

    def _clear_all(self):
        """Clear all buttons from the toolbar."""
        self.drop_zone.clear()
        self._mark_unsaved()

    def _save_toolbar(self):
        """Save the current toolbar configuration."""
        if not self.current_config.buttons:
            QtWidgets.QMessageBox.warning(self, "Empty Toolbar", "Cannot save an empty toolbar.")
            return

        try:
            filepath = save_toolbar(self.current_config)
            self._unsaved_changes = False
            self._update_status()
            self._populate_saved_toolbars()
            QtWidgets.QMessageBox.information(self, "Saved", f"Toolbar saved to:\n{filepath}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to save: {e}")

    def _export_toolbar(self):
        """Export toolbar to a custom location."""
        from .persistence import export_to_application_format

        if not self.current_config.buttons:
            QtWidgets.QMessageBox.warning(self, "Empty Toolbar", "Cannot export an empty toolbar.")
            return

        filepath, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export Toolbar",
            str(Path.home() / f"{self.current_config.name}.json"),
            "JSON Files (*.json)"
        )

        if filepath:
            try:
                export_to_application_format(self.current_config, Path(filepath))
                QtWidgets.QMessageBox.information(self, "Exported", f"Toolbar exported to:\n{filepath}")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", f"Failed to export: {e}")

    def _populate_saved_toolbars(self):
        """Populate the saved toolbars dropdown."""
        self.saved_combo.clear()
        self.saved_combo.addItem("-- Select Saved Toolbar --")

        toolbars = list_saved_toolbars()
        for name, filepath in toolbars:
            self.saved_combo.addItem(name, filepath)

    def _on_saved_selected(self, index: int):
        """Handle selection from saved toolbars dropdown."""
        # Just placeholder - actual loading happens on Load button click
        pass

    def _load_selected_toolbar(self):
        """Load the selected toolbar."""
        index = self.saved_combo.currentIndex()
        if index <= 0:  # First item is placeholder
            QtWidgets.QMessageBox.information(self, "Select Toolbar", "Please select a toolbar to load.")
            return

        filepath = self.saved_combo.currentData()

        if self._unsaved_changes:
            reply = QtWidgets.QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Discard them?",
                QtWidgets.QMessageBox.StandardButton.Yes |
                QtWidgets.QMessageBox.StandardButton.No
            )
            if reply != QtWidgets.QMessageBox.StandardButton.Yes:
                return

        try:
            config = load_toolbar(filepath)
            self.current_config = config
            self.name_input.setText(config.name)
            self.drop_zone.set_buttons(config.buttons)
            self._unsaved_changes = False
            self._update_status()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to load: {e}")

    def _delete_selected_toolbar(self):
        """Delete the selected toolbar."""
        index = self.saved_combo.currentIndex()
        if index <= 0:
            QtWidgets.QMessageBox.information(self, "Select Toolbar", "Please select a toolbar to delete.")
            return

        name = self.saved_combo.currentText()
        filepath = self.saved_combo.currentData()

        reply = QtWidgets.QMessageBox.question(
            self, "Confirm Delete",
            f"Delete toolbar '{name}'?\n\nThis cannot be undone.",
            QtWidgets.QMessageBox.StandardButton.Yes |
            QtWidgets.QMessageBox.StandardButton.No
        )

        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            try:
                delete_toolbar(filepath)
                self._populate_saved_toolbars()
                QtWidgets.QMessageBox.information(self, "Deleted", f"Toolbar '{name}' deleted.")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", f"Failed to delete: {e}")


class MenuBuilderDemo(QtWidgets.QMainWindow):
    """Main demo window for the menu builder."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Menu Builder - OpenM Toolbar Editor")
        self.setMinimumSize(1000, 700)

        # Set professional font
        font = QtGui.QFont("Inter", 11)
        if not QtGui.QFontDatabase.hasFamily("Inter"):
            font = QtGui.QFont("Segoe UI", 11) if sys.platform == "win32" else QtGui.QFont("SF Pro", 11)
        QtWidgets.QApplication.setFont(font)

        # Menu bar
        self._setup_menubar()

        # Central widget
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)

        layout = QtWidgets.QVBoxLayout(central)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # Top bar
        top_bar = self._create_top_bar()
        layout.addWidget(top_bar)

        # Main builder
        self.builder = ToolbarBuilderWidget()
        layout.addWidget(self.builder, stretch=1)

    def _setup_menubar(self):
        """Set up the menu bar."""
        menubar = self.menuBar()
        menubar.setStyleSheet("""
            QMenuBar {
                background: white;
                border-bottom: 1px solid #E5E7EB;
            }
            QMenuBar::item {
                padding: 6px 12px;
                background: transparent;
            }
            QMenuBar::item:selected {
                background: #F3F4F6;
                border-radius: 4px;
            }
        """)

        # File menu
        file_menu = menubar.addMenu("File")

        new_action = QtGui.QAction("New Toolbar", self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self._on_new)
        file_menu.addAction(new_action)

        open_action = QtGui.QAction("Open...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._on_open)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        save_action = QtGui.QAction("Save", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._on_save)
        file_menu.addAction(save_action)

        save_as_action = QtGui.QAction("Save As...", self)
        save_as_action.triggered.connect(self._on_save_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        exit_action = QtGui.QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Help menu
        help_menu = menubar.addMenu("Help")

        about_action = QtGui.QAction("About", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    def _create_top_bar(self) -> QtWidgets.QFrame:
        """Create the top title bar."""
        top_bar = QtWidgets.QFrame()
        top_bar.setFixedHeight(50)
        top_bar.setStyleSheet("background: white; border-bottom: 1px solid #E5E7EB;")

        layout = QtWidgets.QHBoxLayout(top_bar)
        layout.setContentsMargins(20, 0, 20, 0)

        # Logo/Title
        logo = QtWidgets.QLabel("Menu Builder")
        logo.setStyleSheet("font-size: 18px; font-weight: 700; color: #1F2937;")
        layout.addWidget(logo)

        subtitle = QtWidgets.QLabel("— Build custom toolbars for OpenM")
        subtitle.setStyleSheet("font-size: 13px; color: #6B7280; margin-left: 8px;")
        layout.addWidget(subtitle)

        layout.addStretch()

        return top_bar

    def _on_new(self):
        """File > New Toolbar"""
        self.builder._new_toolbar()

    def _on_open(self):
        """File > Open"""
        filepath, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open Toolbar",
            str(OM_TOOLBARS_DIR),
            "JSON Files (*.json)"
        )
        if filepath:
            try:
                config = load_toolbar(filepath)
                self.builder.current_config = config
                self.builder.name_input.setText(config.name)
                self.builder.drop_zone.set_buttons(config.buttons)
                self.builder._unsaved_changes = False
                self.builder._update_status()
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", f"Failed to load: {e}")

    def _on_save(self):
        """File > Save"""
        self.builder._save_toolbar()

    def _on_save_as(self):
        """File > Save As"""
        filepath, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Toolbar As",
            str(OM_TOOLBARS_DIR / f"{self.builder.current_config.name}.json"),
            "JSON Files (*.json)"
        )
        if filepath:
            try:
                import json
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(self.builder.current_config.to_dict(), f, indent=2)
                self.builder._unsaved_changes = False
                self.builder._update_status()
                QtWidgets.QMessageBox.information(self, "Saved", f"Toolbar saved to:\n{filepath}")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", f"Failed to save: {e}")

    def _on_about(self):
        """Help > About"""
        QtWidgets.QMessageBox.about(
            self, "About Menu Builder",
            "<h2>Menu Builder</h2>"
            "<p>Version 1.0</p>"
            "<p>A toolbar editor for OpenM with drag-and-drop interface, "
            "JSON persistence, and standardized commands.</p>"
            "<p>Drag buttons from the left palette to the toolbar drop zone. "
            "Right-click tiles to remove or reorder them.</p>"
        )


def main():
    """Run the menu builder demo."""
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")

    # Set application-wide stylesheet
    app.setStyleSheet("""
        QToolTip {
            background: #1F2937;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 4px 8px;
            font-size: 12px;
        }
    """)

    demo = MenuBuilderDemo()
    demo.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
