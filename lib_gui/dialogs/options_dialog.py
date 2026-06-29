"""Options dialog for application settings."""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from lib_utils.config import gui as gui_config, set_gui as gui_config_set


class OptionsDialog(QtWidgets.QDialog):
    """Dialog for configuring application options."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Options")
        self.setMinimumWidth(400)
        self.setModal(True)

        layout = QtWidgets.QVBoxLayout(self)

        # Create tab widget
        self._tabs = QtWidgets.QTabWidget(self)
        layout.addWidget(self._tabs)

        # General settings tab
        self._general_tab = self._create_general_tab()
        self._tabs.addTab(self._general_tab, "General")

        # Button box
        self._button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self._button_box.accepted.connect(self._on_accept)
        self._button_box.rejected.connect(self.reject)
        layout.addWidget(self._button_box)

    def _create_general_tab(self) -> QtWidgets.QWidget:
        """Create the General settings tab."""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(tab)
        layout.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.DontWrapRows)
        layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # Selection alpha level (0-255)
        sel_alpha = gui_config("appearance", "selection_alpha", 120)
        self._sel_alpha_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self._sel_alpha_slider.setRange(0, 255)
        self._sel_alpha_slider.setValue(int(sel_alpha))
        self._sel_alpha_slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBelow)
        self._sel_alpha_slider.setTickInterval(64)

        self._sel_alpha_label = QtWidgets.QLabel(str(int(sel_alpha)))

        sel_alpha_layout = QtWidgets.QHBoxLayout()
        sel_alpha_layout.addWidget(self._sel_alpha_slider)
        sel_alpha_layout.addWidget(self._sel_alpha_label)

        layout.addRow("Selection Alpha Level:", sel_alpha_layout)
        self._sel_alpha_slider.valueChanged.connect(self._on_sel_alpha_changed)

        # Mouse scroll sensitivity
        sensitivity = gui_config("behavior", "mouse_scroll_sensitivity", 1.0)
        self._scroll_sensitivity_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self._scroll_sensitivity_slider.setRange(1, 100)  # 0.1 to 10.0
        self._scroll_sensitivity_slider.setValue(int(sensitivity * 10))
        self._scroll_sensitivity_slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBelow)
        self._scroll_sensitivity_slider.setTickInterval(10)

        self._scroll_sensitivity_label = QtWidgets.QLabel(f"{sensitivity:.1f}x")

        slider_layout = QtWidgets.QHBoxLayout()
        slider_layout.addWidget(self._scroll_sensitivity_slider)
        slider_layout.addWidget(self._scroll_sensitivity_label)

        layout.addRow("Mouse Scroll Sensitivity:", slider_layout)

        # Connect slider to update label
        self._scroll_sensitivity_slider.valueChanged.connect(self._on_sensitivity_changed)

        # Prefetch Max Tile Size (1 to 256)
        tile_size = gui_config("performance", "prefetch_max_tile_size", 5)
        self._tile_size_spin = QtWidgets.QSpinBox()
        self._tile_size_spin.setRange(1, 256)
        self._tile_size_spin.setValue(int(tile_size))
        layout.addRow("Prefetch Max Tile Size:", self._tile_size_spin)

        # Pre-Render Thread Pool Size (1 to half of CPU cores)
        import os
        max_threads = (os.cpu_count() or 4) // 2
        pool_size = gui_config("performance", "prerender_thread_pool_size", max(1, max_threads))
        self._pool_size_spin = QtWidgets.QSpinBox()
        self._pool_size_spin.setRange(1, max(1, max_threads))
        self._pool_size_spin.setValue(int(pool_size))
        layout.addRow("Pre-Render Thread Pool Size:", self._pool_size_spin)

        # Pre-render plain data (value-only fast fallback)
        plain_enabled = gui_config("performance", "prerender_plain_data", False)
        self._plain_data_check = QtWidgets.QCheckBox("Pre-render plain data (value-only fast fallback)")
        self._plain_data_check.setChecked(bool(plain_enabled))
        layout.addRow(self._plain_data_check)

        # Show system elements (names beginning with '%')
        show_system = gui_config("gui", "show_system_elements", False)
        self._show_system_elements_check = QtWidgets.QCheckBox("Show system elements (names beginning with '%')")
        self._show_system_elements_check.setChecked(bool(show_system))
        layout.addRow(self._show_system_elements_check)

        # Add stretch to push everything to the top
        layout.addItem(QtWidgets.QSpacerItem(
            20, 40,
            QtWidgets.QSizePolicy.Policy.Minimum,
            QtWidgets.QSizePolicy.Policy.Expanding
        ))

        return tab

    def _on_sel_alpha_changed(self, value: int) -> None:
        """Update the selection alpha label when slider moves."""
        self._sel_alpha_label.setText(str(value))

    def _on_sensitivity_changed(self, value: int) -> None:
        """Update the sensitivity label when slider moves."""
        sensitivity = value / 10.0
        self._scroll_sensitivity_label.setText(f"{sensitivity:.1f}x")

    def _on_accept(self) -> None:
        """Save settings and close dialog."""
        # Save selection alpha level
        gui_config_set("appearance", "selection_alpha", self._sel_alpha_slider.value())

        # Save mouse scroll sensitivity
        sensitivity = self._scroll_sensitivity_slider.value() / 10.0
        gui_config_set("behavior", "mouse_scroll_sensitivity", sensitivity)

        # Save tile prefetch and pre-render pool settings
        gui_config_set("performance", "prefetch_max_tile_size", self._tile_size_spin.value())
        gui_config_set("performance", "prerender_thread_pool_size", self._pool_size_spin.value())
        gui_config_set("performance", "prerender_plain_data", self._plain_data_check.isChecked())

        # Save system elements visibility
        gui_config_set("gui", "show_system_elements", self._show_system_elements_check.isChecked())

        self.accept()
