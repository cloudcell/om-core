"""Context-aware format panel with visual controls."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QSpinBox, QComboBox, QSlider, QGridLayout,
    QColorDialog, QFontComboBox, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QFont, QFontMetrics

from .format_pill_bar import FormatSection

if TYPE_CHECKING:
    from typing import List, Optional, Tuple


# Preset colors (modern palette)
PRESET_COLORS: List[str] = [
    "#FFFFFF", "#F3F4F6", "#E5E7EB", "#D1D5DB",  # Grays
    "#FECACA", "#FED7AA", "#FEF08A", "#BBF7D0", "#BFDBFE", "#E9D5FF",  # Pastels
    "#EF4444", "#F97316", "#EAB308", "#22C55E", "#3B82F6", "#A855F7",  # Vibrant
    "#7F1D1D", "#9A3412", "#854D0E", "#14532D", "#1E3A8A", "#581C87",  # Dark
]


class ColorSwatchGrid(QWidget):
    """Grid of color swatches with picker."""
    
    color_selected = Signal(str)
    
    SWATCH_SIZE = 24
    SWATCH_SPACING = 4
    COLS = 6
    
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.selected_color: Optional[str] = None
        self._swatch_buttons: List[QPushButton] = []
        
        self._setup_ui()
        
    def _setup_ui(self) -> None:
        """Create color swatch grid."""
        layout = QGridLayout(self)
        layout.setSpacing(self.SWATCH_SPACING)
        layout.setContentsMargins(0, 0, 0, 0)
        
        for i, color in enumerate(PRESET_COLORS):
            row = i // self.COLS
            col = i % self.COLS
            
            btn = QPushButton()
            btn.setFixedSize(self.SWATCH_SIZE, self.SWATCH_SIZE)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    border: 1px solid #D1D5DB;
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    border: 2px solid #3B82F6;
                }}
                QPushButton:checked {{
                    border: 2px solid #3B82F6;
                    background-color: {color};
                }}
            """)
            btn.setCheckable(True)
            btn.clicked.connect(lambda c, clr=color: self._on_swatch_clicked(clr))
            layout.addWidget(btn, row, col)
            self._swatch_buttons.append(btn)
            
        # Add custom picker button
        picker_btn = QPushButton("+")
        picker_btn.setFixedSize(self.SWATCH_SIZE, self.SWATCH_SIZE)
        picker_btn.setStyleSheet("""
            QPushButton {
                background-color: #F3F4F6;
                border: 1px dashed #9CA3AF;
                border-radius: 4px;
                color: #6B7280;
                font-weight: bold;
            }
            QPushButton:hover {
                border: 2px solid #3B82F6;
                color: #3B82F6;
            }
        """)
        picker_btn.setToolTip("Custom color...")
        picker_btn.clicked.connect(self._on_custom_color)
        layout.addWidget(picker_btn, len(PRESET_COLORS) // self.COLS, 0)
        
    def _on_swatch_clicked(self, color: str) -> None:
        """Handle color swatch selection."""
        self.selected_color = color
        
        # Uncheck others
        for btn, clr in zip(self._swatch_buttons, PRESET_COLORS):
            btn.setChecked(clr == color)
            
        self.color_selected.emit(color)
        
    def _on_custom_color(self) -> None:
        """Open color picker dialog."""
        color = QColorDialog.getColor(QColor(self.selected_color or "#FFFFFF"), self, "Select Color")
        if color.isValid():
            self._on_swatch_clicked(color.name())
            
    def set_color(self, color: Optional[str]) -> None:
        """Set selected color programmatically."""
        self.selected_color = color
        for btn, clr in zip(self._swatch_buttons, PRESET_COLORS):
            btn.setChecked(clr == color)


class AlignmentGrid(QWidget):
    """3x3 grid for horizontal/vertical alignment selection."""
    
    alignment_changed = Signal(str, str)  # h_align, v_align
    
    H_ALIGNMENTS = ["left", "center", "right"]
    V_ALIGNMENTS = ["top", "middle", "bottom"]
    
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.current_h = "left"
        self.current_v = "middle"
        self._buttons: List[List[QPushButton]] = []
        
        self._setup_ui()
        
    def _setup_ui(self) -> None:
        """Create alignment grid."""
        layout = QGridLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(0, 0, 0, 0)
        
        for v_idx, v_align in enumerate(self.V_ALIGNMENTS):
            row = []
            for h_idx, h_align in enumerate(self.H_ALIGNMENTS):
                btn = QPushButton()
                btn.setFixedSize(32, 32)
                btn.setCheckable(True)
                btn.setProperty("h_align", h_align)
                btn.setProperty("v_align", v_align)
                
                # Style based on position
                icon_text = self._get_alignment_icon(h_align, v_align)
                btn.setText(icon_text)
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #F9FAFB;
                        border: 1px solid #E5E7EB;
                        border-radius: 4px;
                        font-size: 10px;
                        color: #6B7280;
                    }
                    QPushButton:hover {
                        background-color: #F3F4F6;
                        border-color: #D1D5DB;
                    }
                    QPushButton:checked {
                        background-color: #DBEAFE;
                        border-color: #3B82F6;
                        color: #1E40AF;
                    }
                """)
                
                btn.clicked.connect(lambda c, h=h_align, v=v_align: self._on_alignment_clicked(h, v))
                layout.addWidget(btn, v_idx, h_idx)
                row.append(btn)
                
                if h_align == self.current_h and v_align == self.current_v:
                    btn.setChecked(True)
                    
            self._buttons.append(row)
            
    def _get_alignment_icon(self, h: str, v: str) -> str:
        """Get icon/emoji representation for alignment."""
        icons = {
            ("left", "top"): "↖",
            ("center", "top"): "↑",
            ("right", "top"): "↗",
            ("left", "middle"): "←",
            ("center", "middle"): "⊕",
            ("right", "middle"): "→",
            ("left", "bottom"): "↙",
            ("center", "bottom"): "↓",
            ("right", "bottom"): "↘",
        }
        return icons.get((h, v), "○")
        
    def _on_alignment_clicked(self, h_align: str, v_align: str) -> None:
        """Handle alignment selection."""
        self.current_h = h_align
        self.current_v = v_align
        
        # Update button states
        for v_idx, v in enumerate(self.V_ALIGNMENTS):
            for h_idx, h in enumerate(self.H_ALIGNMENTS):
                self._buttons[v_idx][h_idx].setChecked(
                    h == h_align and v == v_align
                )
                
        self.alignment_changed.emit(h_align, v_align)
        
    def get_alignment(self) -> Tuple[str, str]:
        """Get current alignment."""
        return self.current_h, self.current_v


class BorderDiagramWidget(QWidget):
    """Interactive border diagram widget like LibreOffice Calc."""
    
    border_clicked = Signal(str)  # side: top, bottom, left, right
    
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(120, 90)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.borders = {"top": False, "bottom": False, "left": False, "right": False}
        self.hover_side: Optional[str] = None
        
    def set_borders(self, borders: dict) -> None:
        """Update border state."""
        self.borders = {
            "top": borders.get("top", "none") != "none",
            "bottom": borders.get("bottom", "none") != "none",
            "left": borders.get("left", "none") != "none",
            "right": borders.get("right", "none") != "none",
        }
        self.update()
        
    def paintEvent(self, event) -> None:
        """Draw the border diagram."""
        from PySide6.QtGui import QPainter, QPen, QColor, QBrush
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Background (cell interior)
        painter.fillRect(self.rect(), QBrush(QColor("#FFFFFF")))
        
        # Outer frame (thin gray)
        painter.setPen(QPen(QColor("#E5E7EB"), 1))
        painter.drawRect(10, 10, 100, 70)
        
        # Border lines
        for side, active in self.borders.items():
            is_hover = self.hover_side == side
            
            if active:
                # Active border: thick blue
                pen = QPen(QColor("#3B82F6"), 3)
            elif is_hover:
                # Hover: medium gray
                pen = QPen(QColor("#9CA3AF"), 2)
            else:
                # Inactive: thin light gray
                pen = QPen(QColor("#D1D5DB"), 1)
            
            painter.setPen(pen)
            
            if side == "top":
                painter.drawLine(10, 10, 110, 10)
            elif side == "bottom":
                painter.drawLine(10, 80, 110, 80)
            elif side == "left":
                painter.drawLine(10, 10, 10, 80)
            elif side == "right":
                painter.drawLine(110, 10, 110, 80)
                
        # Corner handles (small squares at corners)
        painter.setBrush(QBrush(QColor("#FFFFFF")))
        painter.setPen(QPen(QColor("#9CA3AF"), 1))
        for x, y in [(8, 8), (108, 8), (8, 78), (108, 78)]:
            painter.drawRect(x, y, 4, 4)
            
    def mouseMoveEvent(self, event) -> None:
        """Track hover over border areas."""
        x, y = event.position().x(), event.position().y()
        
        # Define border hit zones (generous 12px width)
        if 10 <= x <= 110 and 4 <= y <= 16:
            self.hover_side = "top"
        elif 10 <= x <= 110 and 74 <= y <= 86:
            self.hover_side = "bottom"
        elif 4 <= x <= 16 and 10 <= y <= 80:
            self.hover_side = "left"
        elif 104 <= x <= 116 and 10 <= y <= 80:
            self.hover_side = "right"
        else:
            self.hover_side = None
            
        self.update()
        
    def mousePressEvent(self, event) -> None:
        """Handle click on borders."""
        if self.hover_side:
            self.border_clicked.emit(self.hover_side)
            
    def leaveEvent(self, event) -> None:
        """Clear hover on leave."""
        self.hover_side = None
        self.update()


class BorderPresetButton(QPushButton):
    """Preset button with border icon."""
    
    def __init__(self, preset_type: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.preset_type = preset_type
        self.setFixedSize(36, 32)
        self.setCheckable(True)
        self.setToolTip(self._get_tooltip())
        
    def _get_tooltip(self) -> str:
        tooltips = {
            "none": "No borders",
            "outer": "Outer border only",
            "all": "All borders",
            "top": "Top border",
            "bottom": "Bottom border",
        }
        return tooltips.get(self.preset_type, "")
        
    def paintEvent(self, event) -> None:
        """Draw preset icon."""
        from PySide6.QtGui import QPainter, QPen, QColor
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Background
        if self.isChecked():
            painter.fillRect(self.rect(), QColor("#DBEAFE"))
            pen = QPen(QColor("#3B82F6"), 2)
        else:
            painter.fillRect(self.rect(), QColor("#F9FAFB"))
            pen = QPen(QColor("#6B7280"), 2)
            
        # Draw cell outline
        painter.setPen(pen)
        painter.drawRect(6, 6, 24, 20)
        
        # Draw borders based on preset
        if self.preset_type == "outer":
            pass  # Just the outline
        elif self.preset_type == "all":
            # Inner cross
            painter.drawLine(18, 6, 18, 26)
            painter.drawLine(6, 16, 30, 16)
        elif self.preset_type == "top":
            # Just top
            painter.drawLine(6, 6, 30, 6)
        elif self.preset_type == "bottom":
            # Just bottom
            painter.drawLine(6, 26, 30, 26)


class BorderEditor(QWidget):
    """Professional border editor like LibreOffice Calc."""
    
    border_changed = Signal(dict)  # border config dict
    
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.current_border = {"top": "none", "bottom": "none", "left": "none", "right": "none"}
        self._setup_ui()
        
    def _setup_ui(self) -> None:
        """Create professional border editor UI."""
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Left side: Presets
        presets_layout = QVBoxLayout()
        presets_layout.setSpacing(8)
        
        preset_label = QLabel("Presets")
        preset_label.setStyleSheet("font-weight: 600; color: #374151;")
        presets_layout.addWidget(preset_label)
        
        # Preset buttons grid
        preset_grid = QHBoxLayout()
        preset_grid.setSpacing(4)
        
        self.preset_buttons = {}
        presets = ["none", "outer", "all", "top", "bottom"]
        for preset in presets:
            btn = BorderPresetButton(preset)
            btn.clicked.connect(lambda c, p=preset: self._apply_preset(p))
            preset_grid.addWidget(btn)
            self.preset_buttons[preset] = btn
            
        preset_grid.addStretch()
        presets_layout.addLayout(preset_grid)
        presets_layout.addStretch()
        
        main_layout.addLayout(presets_layout)
        
        # Center: Interactive diagram
        diagram_layout = QVBoxLayout()
        diagram_layout.setSpacing(8)
        
        user_label = QLabel("User-defined")
        user_label.setStyleSheet("font-weight: 600; color: #374151;")
        diagram_layout.addWidget(user_label)
        
        self.diagram = BorderDiagramWidget()
        self.diagram.border_clicked.connect(self._toggle_side)
        diagram_layout.addWidget(self.diagram, alignment=Qt.AlignmentFlag.AlignCenter)
        
        hint_label = QLabel("Click lines to toggle")
        hint_label.setStyleSheet("color: #9CA3AF; font-size: 10px;")
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        diagram_layout.addWidget(hint_label)
        
        main_layout.addLayout(diagram_layout)
        
        # Right side: Style options
        style_layout = QVBoxLayout()
        style_layout.setSpacing(8)
        
        line_label = QLabel("Line")
        line_label.setStyleSheet("font-weight: 600; color: #374151;")
        style_layout.addWidget(line_label)
        
        # Style dropdown
        self.style_combo = QComboBox()
        self.style_combo.addItem("Solid", "solid")
        self.style_combo.addItem("Dashed", "dashed")
        self.style_combo.addItem("Dotted", "dotted")
        self.style_combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                padding: 4px 8px;
                min-width: 100px;
            }
        """)
        style_layout.addWidget(self.style_combo)
        
        # Color button
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("Color:"))
        self.color_btn = QPushButton()
        self.color_btn.setFixedSize(24, 24)
        self.color_btn.setStyleSheet("""
            QPushButton {
                background-color: #000000;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
            }
        """)
        self.color_btn.clicked.connect(self._pick_color)
        color_layout.addWidget(self.color_btn)
        color_layout.addStretch()
        style_layout.addLayout(color_layout)
        
        style_layout.addStretch()
        main_layout.addLayout(style_layout)
        
        self._update_ui()
        
    def _apply_preset(self, preset: str) -> None:
        """Apply preset border configuration."""
        presets = {
            "none": {"top": "none", "bottom": "none", "left": "none", "right": "none"},
            "outer": {"top": "thin", "bottom": "thin", "left": "thin", "right": "thin"},
            "all": {"top": "thin", "bottom": "thin", "left": "thin", "right": "thin"},
            "top": {"top": "thin", "bottom": "none", "left": "none", "right": "none"},
            "bottom": {"top": "none", "bottom": "thin", "left": "none", "right": "none"},
        }
        
        self.current_border = presets.get(preset, {}).copy()
        
        # Uncheck other presets
        for key, btn in self.preset_buttons.items():
            btn.setChecked(key == preset)
            
        self._update_ui()
        self.border_changed.emit(self.current_border)
        
    def _toggle_side(self, side: str) -> None:
        """Toggle individual border side."""
        current = self.current_border.get(side, "none")
        self.current_border[side] = "thin" if current == "none" else "none"
        
        # Uncheck presets (now in custom state)
        for btn in self.preset_buttons.values():
            btn.setChecked(False)
            
        self._update_ui()
        self.border_changed.emit(self.current_border)
        
    def _pick_color(self) -> None:
        """Open color picker for border color."""
        color = QColorDialog.getColor(QColor("#000000"), self, "Border Color")
        if color.isValid():
            self.color_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color.name()};
                    border: 1px solid #E5E7EB;
                    border-radius: 4px;
                }}
            """)
            self.current_border["color"] = color.name()
            self._update_ui()
            self.border_changed.emit(self.current_border)
        
    def _update_ui(self) -> None:
        """Update diagram to match current state."""
        self.diagram.set_borders(self.current_border)
        
        # Update preset states
        for preset, btn in self.preset_buttons.items():
            config = {
                "none": {"top": "none", "bottom": "none", "left": "none", "right": "none"},
                "outer": {"top": "thin", "bottom": "thin", "left": "thin", "right": "thin"},
                "all": {"top": "thin", "bottom": "thin", "left": "thin", "right": "thin"},
                "top": {"top": "thin", "bottom": "none", "left": "none", "right": "none"},
                "bottom": {"top": "none", "bottom": "thin", "left": "none", "right": "none"},
            }.get(preset, {})
            
            matches = all(self.current_border.get(k) == v for k, v in config.items())
            btn.setChecked(matches)


class NumberFormatPanel(QWidget):
    """Number format templates and options."""
    
    format_changed = Signal(str, int)  # format_type, decimal_places
    
    FORMATS = [
        ("General", "general", "1234.56"),
        ("Number", "number", "1,234.56"),
        ("Currency", "currency", "$1,234.56"),
        ("Percentage", "percentage", "123.46%"),
        ("Scientific", "scientific", "1.23E+03"),
    ]
    
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._setup_ui()
        
    def _setup_ui(self) -> None:
        """Create number format panel."""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Format buttons
        for name, fmt, preview in self.FORMATS:
            btn = QPushButton(f"{name}\n{preview}")
            btn.setFixedHeight(44)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #F9FAFB;
                    border: 1px solid #E5E7EB;
                    border-radius: 6px;
                    text-align: left;
                    padding: 4px 10px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #F3F4F6;
                    border-color: #3B82F6;
                }
            """)
            btn.clicked.connect(lambda c, f=fmt: self.format_changed.emit(f, 2))
            layout.addWidget(btn)
            
        # Decimal places
        dp_layout = QHBoxLayout()
        dp_layout.addWidget(QLabel("Decimal places:"))
        self.dp_spin = QSpinBox()
        self.dp_spin.setRange(0, 10)
        self.dp_spin.setValue(2)
        self.dp_spin.setStyleSheet("""
            QSpinBox {
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                padding: 4px;
            }
        """)
        dp_layout.addWidget(self.dp_spin)
        dp_layout.addStretch()
        layout.addLayout(dp_layout)
        

class FormatContextPanel(QWidget):
    """
    Context-aware format panel that shows controls based on selected section.
    """
    
    format_applied = Signal(str, object)  # format_type, value
    
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.current_section: Optional[FormatSection] = None
        
        self._setup_ui()
        self._hide_all_controls()
        
    def _setup_ui(self) -> None:
        """Set up panel with all possible controls (shown/hidden dynamically)."""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setSpacing(12)
        self.main_layout.setContentsMargins(16, 16, 16, 16)
        
        # Background controls
        self.bg_label = QLabel("Background Color")
        self.bg_label.setStyleSheet("font-weight: 600; color: #374151;")
        self.main_layout.addWidget(self.bg_label)
        
        self.color_grid = ColorSwatchGrid()
        self.color_grid.color_selected.connect(self._on_bg_color_selected)
        self.main_layout.addWidget(self.color_grid)
        
        # Font controls
        self.font_label = QLabel("Typography")
        self.font_label.setStyleSheet("font-weight: 600; color: #374151;")
        self.main_layout.addWidget(self.font_label)
        
        # Font family row
        self.font_family_row = QWidget()
        font_family_layout = QHBoxLayout(self.font_family_row)
        font_family_layout.setContentsMargins(0, 0, 0, 0)
        font_family_layout.setSpacing(8)
        family_label = QLabel("Family:")
        family_label.setStyleSheet("color: #6B7280;")
        font_family_layout.addWidget(family_label)
        self.font_combo = QFontComboBox()
        self.font_combo.setMinimumWidth(160)
        self.font_combo.setStyleSheet("""
            QFontComboBox {
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                padding: 4px;
            }
            QFontComboBox::drop-down {
                border: none;
            }
        """)
        self.font_combo.currentFontChanged.connect(self._on_font_changed)
        font_family_layout.addWidget(self.font_combo, stretch=1)
        self.main_layout.addWidget(self.font_family_row)
        
        # Font size row
        self.font_size_row = QWidget()
        font_size_layout = QHBoxLayout(self.font_size_row)
        font_size_layout.setContentsMargins(0, 0, 0, 0)
        font_size_layout.setSpacing(8)
        size_label = QLabel("Size:")
        size_label.setStyleSheet("color: #6B7280;")
        font_size_layout.addWidget(size_label)
        
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(6, 72)
        self.size_slider.setValue(10)
        self.size_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 4px;
                background: #E5E7EB;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                width: 16px;
                height: 16px;
                background: #3B82F6;
                border-radius: 8px;
            }
        """)
        
        self.size_spin = QSpinBox()
        self.size_spin.setRange(6, 72)
        self.size_spin.setValue(10)
        self.size_spin.setFixedWidth(50)
        self.size_spin.setStyleSheet("""
            QSpinBox {
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                padding: 4px;
            }
        """)
        
        self.size_slider.valueChanged.connect(self.size_spin.setValue)
        self.size_spin.valueChanged.connect(self.size_slider.setValue)
        self.size_spin.valueChanged.connect(self._on_font_size_changed)
        
        font_size_layout.addWidget(self.size_slider, stretch=1)
        font_size_layout.addWidget(self.size_spin)
        self.main_layout.addWidget(self.font_size_row)
        
        # Alignment controls
        self.align_label = QLabel("Cell Alignment")
        self.align_label.setStyleSheet("font-weight: 600; color: #374151;")
        self.main_layout.addWidget(self.align_label)
        
        self.alignment_grid = AlignmentGrid()
        self.alignment_grid.alignment_changed.connect(self._on_alignment_changed)
        self.main_layout.addWidget(self.alignment_grid)
        
        # Border controls
        self.border_label = QLabel("Cell Borders")
        self.border_label.setStyleSheet("font-weight: 600; color: #374151;")
        self.main_layout.addWidget(self.border_label)
        
        self.border_editor = BorderEditor()
        self.border_editor.border_changed.connect(self._on_border_changed)
        self.main_layout.addWidget(self.border_editor)
        
        # Number controls
        self.number_label = QLabel("Number Format")
        self.number_label.setStyleSheet("font-weight: 600; color: #374151;")
        self.main_layout.addWidget(self.number_label)
        
        self.number_panel = NumberFormatPanel()
        self.number_panel.format_changed.connect(self._on_number_format_changed)
        self.main_layout.addWidget(self.number_panel)
        
        self.main_layout.addStretch()
        
        # Apply button
        self.apply_btn = QPushButton("✓ Apply Format")
        self.apply_btn.setFixedHeight(36)
        self.apply_btn.setStyleSheet("""
            QPushButton {
                background-color: #3B82F6;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #2563EB;
            }
        """)
        self.apply_btn.clicked.connect(self._on_apply_clicked)
        self.main_layout.addWidget(self.apply_btn)
        
    def _hide_all_controls(self) -> None:
        """Hide all section-specific controls."""
        for widget in [
            self.bg_label, self.color_grid,
            self.font_label, self.font_family_row, self.font_size_row,
            self.align_label, self.alignment_grid,
            self.border_label, self.border_editor,
            self.number_label, self.number_panel,
            self.apply_btn,
        ]:
            widget.hide()
            
    def show_section(self, section: Optional[FormatSection]) -> None:
        """Show controls for the selected section."""
        self.current_section = section
        self._hide_all_controls()
        
        if section is None:
            self._animate_collapse()
            return
            
        self._animate_expand()
        
        if section == FormatSection.BACKGROUND:
            self.bg_label.show()
            self.color_grid.show()
            self.apply_btn.show()
            
        elif section == FormatSection.FONT:
            self.font_label.show()
            self.font_family_row.show()
            self.font_size_row.show()
            self.apply_btn.show()
            
        elif section == FormatSection.ALIGNMENT:
            self.align_label.show()
            self.alignment_grid.show()
            self.apply_btn.show()
            
        elif section == FormatSection.BORDERS:
            self.border_label.show()
            self.border_editor.show()
            self.apply_btn.show()
            
        elif section == FormatSection.NUMBER:
            self.number_label.show()
            self.number_panel.show()
            self.apply_btn.show()
            
    def _animate_expand(self) -> None:
        """Animate panel expansion."""
        self.show()
        anim = QPropertyAnimation(self, b"maximumHeight", self)
        anim.setDuration(200)
        anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        anim.setStartValue(0)
        anim.setEndValue(400)
        anim.start()
        
    def _animate_collapse(self) -> None:
        """Animate panel collapse."""
        anim = QPropertyAnimation(self, b"maximumHeight", self)
        anim.setDuration(200)
        anim.setEasingCurve(QEasingCurve.Type.InQuad)
        anim.setStartValue(self.height())
        anim.setEndValue(0)
        anim.start()
        
    def _on_bg_color_selected(self, color: str) -> None:
        """Handle background color selection."""
        self._pending_format = ("bg_color", color)
        
    def _on_font_changed(self, font: QFont) -> None:
        """Handle font family change."""
        self._pending_format = ("font_family", font.family())
        
    def _on_font_size_changed(self, size: int) -> None:
        """Handle font size change."""
        self._pending_format = ("font_size", size)
        
    def _on_alignment_changed(self, h: str, v: str) -> None:
        """Handle alignment change."""
        self._pending_format = ("alignment", {"h": h, "v": v})
        
    def _on_border_changed(self, border: dict) -> None:
        """Handle border change."""
        self._pending_format = ("border", border)
        
    def _on_number_format_changed(self, fmt: str, dp: int) -> None:
        """Handle number format change."""
        self._pending_format = ("number_format", {"format": fmt, "decimals": dp})
        
    def _on_apply_clicked(self) -> None:
        """Apply the pending format."""
        if hasattr(self, '_pending_format'):
            fmt_type, value = self._pending_format
            self.format_applied.emit(fmt_type, value)
