from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets


class FormatToolboxDock(QtWidgets.QDockWidget):
    format_changed = QtCore.Signal(str, object)  # (format_type, value)
    
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__("Format Toolbox", parent)
        self._pending_border_style = "solid"
        self._pending_border_color = "#000000"

        self._sections = QtWidgets.QListWidget(self)
        self._sections.addItem("Background")
        self._sections.addItem("Font")
        self._sections.addItem("Alignment")
        self._sections.addItem("Borders")
        self._sections.addItem("Number")

        self._stack = QtWidgets.QStackedWidget(self)
        
        # Background page
        self._bg_page = self._create_background_page()
        self._stack.addWidget(self._bg_page)
        
        # Font page
        self._font_page = self._create_font_page()
        self._stack.addWidget(self._font_page)
        
        # Alignment page
        self._alignment_page = self._create_alignment_page()
        self._stack.addWidget(self._alignment_page)
        
        # Borders page
        self._borders_page = self._create_borders_page()
        self._stack.addWidget(self._borders_page)
        
        # Number page
        self._number_page = self._create_number_page()
        self._stack.addWidget(self._number_page)

        self._sections.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._sections.setCurrentRow(0)

        body = QtWidgets.QWidget(self)
        body_layout = QtWidgets.QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body_layout.addWidget(self._sections, 1)
        body_layout.addWidget(self._stack, 2)

        self.setWidget(body)

    def contains_widget(self, widget: QtWidgets.QWidget | None) -> bool:
        content = self.widget()
        if widget is None or content is None:
            return False
        return widget is content or content.isAncestorOf(widget)

    def focus_description(self, widget: QtWidgets.QWidget | None = None) -> str:
        section = self._sections.currentItem().text() if self._sections.currentItem() else "Format"
        label = section
        # If a button or control within the section has focus, append its label
        if widget is not None and self.contains_widget(widget):
            text = getattr(widget, "text", lambda: "")()
            if isinstance(text, str) and text.strip():
                label = f"{section}: {text.strip()}"
        return f"Format: {label}"
    
    def _create_background_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        layout.addWidget(QtWidgets.QLabel("Background Color:", page))
        
        # Color picker button
        self._bg_color_btn = QtWidgets.QPushButton("Choose Color", page)
        self._bg_color_btn.clicked.connect(self._on_bg_color_clicked)
        layout.addWidget(self._bg_color_btn)
        
        # Clear background button
        clear_btn = QtWidgets.QPushButton("Clear Background", page)
        clear_btn.clicked.connect(lambda: self.format_changed.emit("bg_color", None))
        layout.addWidget(clear_btn)
        
        layout.addStretch(1)
        return page
    
    def _create_font_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # Font family
        layout.addWidget(QtWidgets.QLabel("Font Family:", page))
        self._font_family = QtWidgets.QFontComboBox(page)
        self._font_family.currentFontChanged.connect(lambda f: self.format_changed.emit("font_family", f.family()))
        layout.addWidget(self._font_family)
        
        # Font size
        layout.addWidget(QtWidgets.QLabel("Font Size:", page))
        self._font_size = QtWidgets.QSpinBox(page)
        self._font_size.setRange(6, 72)
        self._font_size.setValue(10)
        self._font_size.valueChanged.connect(lambda v: self.format_changed.emit("font_size", v))
        layout.addWidget(self._font_size)
        
        # Font color
        layout.addWidget(QtWidgets.QLabel("Font Color:", page))
        self._font_color_btn = QtWidgets.QPushButton("Choose Color", page)
        self._font_color_btn.clicked.connect(self._on_font_color_clicked)
        layout.addWidget(self._font_color_btn)
        
        # Font style
        style_layout = QtWidgets.QHBoxLayout()
        self._font_bold = QtWidgets.QCheckBox("Bold", page)
        self._font_bold.stateChanged.connect(lambda s: self.format_changed.emit("font_weight", 700 if s == QtCore.Qt.CheckState.Checked.value else 400))
        style_layout.addWidget(self._font_bold)
        
        self._font_italic = QtWidgets.QCheckBox("Italic", page)
        self._font_italic.stateChanged.connect(lambda s: self.format_changed.emit("font_italic", s == QtCore.Qt.CheckState.Checked.value))
        style_layout.addWidget(self._font_italic)
        layout.addLayout(style_layout)
        
        layout.addStretch(1)
        return page
    
    def _create_alignment_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # Horizontal alignment
        layout.addWidget(QtWidgets.QLabel("Horizontal Alignment:", page))
        h_align_layout = QtWidgets.QHBoxLayout()

        self._align_left = QtWidgets.QPushButton("Left", page)
        self._align_left.clicked.connect(lambda: self.format_changed.emit("text_h_align", "left"))
        h_align_layout.addWidget(self._align_left)

        self._align_center = QtWidgets.QPushButton("Center", page)
        self._align_center.clicked.connect(lambda: self.format_changed.emit("text_h_align", "center"))
        h_align_layout.addWidget(self._align_center)

        self._align_right = QtWidgets.QPushButton("Right", page)
        self._align_right.clicked.connect(lambda: self.format_changed.emit("text_h_align", "right"))
        h_align_layout.addWidget(self._align_right)

        layout.addLayout(h_align_layout)
        
        # Vertical alignment
        layout.addWidget(QtWidgets.QLabel("Vertical Alignment:", page))
        v_align_layout = QtWidgets.QHBoxLayout()

        self._align_top = QtWidgets.QPushButton("Top", page)
        self._align_top.clicked.connect(lambda: self.format_changed.emit("text_v_align", "top"))
        v_align_layout.addWidget(self._align_top)

        self._align_middle = QtWidgets.QPushButton("Middle", page)
        self._align_middle.clicked.connect(lambda: self.format_changed.emit("text_v_align", "middle"))
        v_align_layout.addWidget(self._align_middle)

        self._align_bottom = QtWidgets.QPushButton("Bottom", page)
        self._align_bottom.clicked.connect(lambda: self.format_changed.emit("text_v_align", "bottom"))
        v_align_layout.addWidget(self._align_bottom)

        layout.addLayout(v_align_layout)
        
        layout.addStretch(1)
        return page
    
    def _create_borders_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # Presets section
        layout.addWidget(QtWidgets.QLabel("Presets:", page))
        preset_layout = QtWidgets.QHBoxLayout()
        preset_layout.setSpacing(4)
        
        # Create preset buttons with visual icons
        def create_preset_btn(tooltip: str, preset: str) -> QtWidgets.QPushButton:
            btn = QtWidgets.QPushButton(page)
            btn.setFixedSize(32, 32)
            btn.setToolTip(tooltip)
            btn.clicked.connect(lambda: self._apply_border_preset(preset))
            return btn
        
        # All borders preset
        all_btn = create_preset_btn("All borders", "all")
        all_btn.setText("▦")
        preset_layout.addWidget(all_btn)
        
        # Outer border preset
        outer_btn = create_preset_btn("Outer border", "outer")
        outer_btn.setText("□")
        preset_layout.addWidget(outer_btn)
        
        # No borders preset
        none_btn = create_preset_btn("No borders", "none")
        none_btn.setText("○")
        preset_layout.addWidget(none_btn)
        
        preset_layout.addStretch(1)
        layout.addLayout(preset_layout)
        
        # Line properties section
        layout.addWidget(QtWidgets.QLabel("Line Properties:", page))
        
        # Line style dropdown
        style_layout = QtWidgets.QHBoxLayout()
        style_layout.addWidget(QtWidgets.QLabel("Style:", page))
        self._border_style = QtWidgets.QComboBox(page)
        self._border_style.addItem("Solid", "solid")
        self._border_style.addItem("Dashed", "dashed")
        self._border_style.addItem("Dotted", "dotted")
        self._border_style.currentIndexChanged.connect(self._on_border_style_changed)
        style_layout.addWidget(self._border_style, 1)
        layout.addLayout(style_layout)
        
        # Line color picker
        color_layout = QtWidgets.QHBoxLayout()
        color_layout.addWidget(QtWidgets.QLabel("Color:", page))
        self._border_color_btn = QtWidgets.QPushButton("Black", page)
        self._border_color_btn.clicked.connect(self._pick_border_color)
        color_layout.addWidget(self._border_color_btn, 1)
        layout.addLayout(color_layout)
        
        # Individual border controls with Thin/Thick columns
        layout.addWidget(QtWidgets.QLabel("Border Style:", page))
        
        # Create header row
        header_layout = QtWidgets.QHBoxLayout()
        header_layout.addWidget(QtWidgets.QLabel("", page), 1)
        thin_label = QtWidgets.QLabel("Thin", page)
        thin_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(thin_label)
        thick_label = QtWidgets.QLabel("Thick", page)
        thick_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(thick_label)
        layout.addLayout(header_layout)
        
        # Helper to create border row
        def create_border_row(label: str, side: str, thin_icon: str, thick_icon: str) -> QtWidgets.QHBoxLayout:
            row = QtWidgets.QHBoxLayout()
            row.addWidget(QtWidgets.QLabel(label, page), 1)
            
            thin_btn = QtWidgets.QPushButton(thin_icon, page)
            thin_btn.setFixedSize(32, 28)
            thin_btn.clicked.connect(lambda: self._apply_border_side(side, "thin"))
            row.addWidget(thin_btn)
            
            thick_btn = QtWidgets.QPushButton(thick_icon, page)
            thick_btn.setFixedSize(32, 28)
            thick_btn.clicked.connect(lambda: self._apply_border_side(side, "thick"))
            row.addWidget(thick_btn)
            
            return row
        
        # Add border rows
        layout.addLayout(create_border_row("Top:", "top", "─", "━"))
        layout.addLayout(create_border_row("Bot:", "bottom", "─", "━"))
        layout.addLayout(create_border_row("Left:", "left", "│", "┃"))
        layout.addLayout(create_border_row("Right:", "right", "│", "┃"))
        
        layout.addStretch(1)
        return page
    
    def _pick_border_color(self) -> None:
        """Open color picker for border color."""
        color = QtWidgets.QColorDialog.getColor(QtGui.QColor(self._pending_border_color), self, "Select Border Color")
        if color.isValid():
            self._pending_border_color = color.name()
            self._border_color_btn.setText(color.name())
            self._border_color_btn.setStyleSheet(f"background-color: {color.name()};")

    def _on_border_style_changed(self) -> None:
        self._pending_border_style = str(self._border_style.currentData())

    def _apply_border_side(self, side: str, thickness: str) -> None:
        self.format_changed.emit(
            "border",
            {
                "side": side,
                "thickness": thickness,
                "style": self._pending_border_style,
                "color": self._pending_border_color,
            },
        )

    def _apply_border_preset(self, preset: str) -> None:
        self.format_changed.emit(
            "border_preset",
            {
                "preset": preset,
                "style": self._pending_border_style,
                "color": self._pending_border_color,
            },
        )
    
    def _create_number_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        layout.addWidget(QtWidgets.QLabel("Number Format:", page))
        
        # Number format dropdown
        self._number_format = QtWidgets.QComboBox(page)
        self._number_format.addItem("General", "general")
        self._number_format.addItem("Number (1,234.56)", "number")
        self._number_format.addItem("Currency ($1,234.56)", "currency")
        self._number_format.addItem("Percentage (12.34%)", "percentage")
        self._number_format.addItem("Scientific (1.23E+03)", "scientific")
        self._number_format.currentIndexChanged.connect(lambda: self.format_changed.emit("number_format", self._number_format.currentData()))
        layout.addWidget(self._number_format)
        
        # Decimal places
        layout.addWidget(QtWidgets.QLabel("Decimal Places:", page))
        self._decimal_places = QtWidgets.QSpinBox(page)
        self._decimal_places.setRange(0, 10)
        self._decimal_places.setValue(2)
        self._decimal_places.valueChanged.connect(lambda v: self.format_changed.emit("decimal_places", v))
        layout.addWidget(self._decimal_places)
        
        layout.addStretch(1)
        return page
    
    def _on_bg_color_clicked(self) -> None:
        color = QtWidgets.QColorDialog.getColor(QtCore.Qt.GlobalColor.white, self, "Choose Background Color")
        if color.isValid():
            self.format_changed.emit("bg_color", color.name())
    
    def _on_font_color_clicked(self) -> None:
        color = QtWidgets.QColorDialog.getColor(QtCore.Qt.GlobalColor.black, self, "Choose Font Color")
        if color.isValid():
            self.format_changed.emit("font_color", color.name())
