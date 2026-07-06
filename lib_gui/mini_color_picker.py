"""
Miniature color picker popup widget.
Inspired by Google Sheets color picker design.
"""
from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtSvg import QSvgRenderer
from typing import Callable, Optional

from lib_gui.icons import load_svg_renderer


class MiniColorPicker(QtWidgets.QFrame):
    """
    Compact color picker popup with preset palette and recent colors.
    
    Features:
    - No Fill checkbox
    - Standard/Custom dropdown selector
    - Large preset color grid (organized by hue/lightness)
    - Recent colors row (8 slots)
    - Custom color dialog option
    """
    
    color_selected = QtCore.Signal(str)  # Emits selected color hex
    no_fill_selected = QtCore.Signal()  # Emits when No Fill is checked
    
    def __init__(self, parent=None, initial_color: Optional[str] = None):
        super().__init__(parent, QtCore.Qt.WindowType.Popup)
        self._initial_color = initial_color
        self._current_palette = "standard"
        self._recent_colors: list[str] = []
        
        self._setup_ui()
        self._setup_styles()
        
    def _setup_styles(self):
        """Apply base styles."""
        self.setStyleSheet("""
            MiniColorPicker {
                background: #ffffff;
                border: 1px solid #dadce0;
                border-radius: 4px;
            }
            QCheckBox {
                font-size: 13px;
                color: #3c4043;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 2px solid #5f6368;
                border-radius: 2px;
            }
            QCheckBox::indicator:checked {
                background: #1a73e8;
                border-color: #1a73e8;
            }
            QComboBox {
                font-size: 13px;
                color: #3c4043;
                border: 1px solid #dadce0;
                border-radius: 4px;
                padding: 4px 8px;
                min-width: 100px;
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QComboBox QAbstractItemView {
                background: #ffffff;
                border: 1px solid #dadce0;
                selection-background-color: #e8f0fe;
            }
            QLabel {
                font-size: 12px;
                color: #5f6368;
            }
        """)
        
    def _setup_ui(self):
        """Build the color picker UI."""
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(12, 12, 12, 12)
        
        # === NO FILL CHECKBOX ===
        self._no_fill_checkbox = QtWidgets.QCheckBox("No Fill")
        self._no_fill_checkbox.stateChanged.connect(self._on_no_fill_changed)
        main_layout.addWidget(self._no_fill_checkbox)
        
        # === PALETTE SELECTOR ===
        self._palette_selector = QtWidgets.QComboBox()
        self._palette_selector.addItem("Standard", "standard")
        self._palette_selector.addItem("Material", "material")
        self._palette_selector.addItem("HTML Named", "html")
        self._palette_selector.addItem("Pastel", "pastel")
        self._palette_selector.addItem("Neon", "neon")
        self._palette_selector.addItem("Viridis", "viridis")
        self._palette_selector.addItem("Plasma", "plasma")
        self._palette_selector.addItem("Custom", "custom")
        self._palette_selector.currentIndexChanged.connect(self._on_palette_changed)
        main_layout.addWidget(self._palette_selector)
        
        # === COLOR GRID ===
        self._color_grid = QtWidgets.QGridLayout()
        self._color_grid.setSpacing(2)
        self._color_grid.setContentsMargins(0, 4, 0, 4)
        
        self._build_standard_palette()
        main_layout.addLayout(self._color_grid)
        
        # === SEPARATOR ===
        separator = QtWidgets.QFrame()
        separator.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        separator.setStyleSheet("background: #dadce0; max-height: 1px;")
        main_layout.addWidget(separator)
        
        # === RECENT COLORS ===
        recent_label = QtWidgets.QLabel("Recent")
        main_layout.addWidget(recent_label)
        
        self._recent_layout = QtWidgets.QHBoxLayout()
        self._recent_layout.setSpacing(3)
        self._recent_layout.setContentsMargins(0, 0, 0, 0)
        self._update_recent_display()
        main_layout.addLayout(self._recent_layout)
        
        # === CUSTOM COLOR BUTTON ===
        custom_btn = QtWidgets.QPushButton("Custom Color...")
        custom_btn.setStyleSheet("""
            QPushButton {
                font-size: 13px;
                color: #1a73e8;
                background: transparent;
                border: none;
                padding: 6px 0px;
                text-align: left;
            }
            QPushButton:hover {
                background: #e8f0fe;
                border-radius: 4px;
            }
        """)
        custom_btn.clicked.connect(self._on_custom_color)
        main_layout.addWidget(custom_btn)
        
    def _clear_color_grid(self):
        """Clear all widgets from the color grid."""
        while self._color_grid.count():
            item = self._color_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _build_standard_palette(self):
        """Build the standard 8x10 color palette (Google Sheets style layout)."""
        self._clear_color_grid()

        # Standard palette: 8 columns, 10 rows
        # Grays at top, then colors organized by hue
        colors = [
            # Row 0: Black & Grays (8 shades)
            "#000000", "#212121", "#424242", "#616161", "#757575", "#9e9e9e", "#bdbdbd", "#e0e0e0",
            # Row 1: More grays & white
            "#000000", "#434343", "#666666", "#999999", "#b7b7b7", "#cccccc", "#d9d9d9", "#efefef",
            # Row 2: Yellows (light to dark)
            "#fff8e7", "#fff2cc", "#ffe599", "#ffd966", "#f7c245", "#daa638", "#b3892b", "#8c6b1f",
            # Row 3: Oranges
            "#fff0e1", "#ffdeb5", "#ffc685", "#ffad56", "#e8934c", "#c47842", "#a16238", "#7f4e2e",
            # Row 4: Reds
            "#fce8e6", "#f7c5c2", "#f4a19c", "#e67c73", "#c55a54", "#9e4b47", "#7b3b38", "#5c2b29",
            # Row 5: Pinks
            "#fce8f0", "#f5c5d3", "#f09bb5", "#e87196", "#d9467c", "#b33767", "#8f2a52", "#6b1c3e",
            # Row 6: Purples
            "#f3e8fd", "#dfb7fd", "#c58af9", "#af6ff5", "#a142f4", "#683db8", "#522e8a", "#3c1e7b",
            # Row 7: Blues
            "#e8f0fe", "#b7d1fc", "#8ab4f8", "#5e97f6", "#4285f4", "#2c72d0", "#235ba8", "#1a4480",
            # Row 8: Teals/Cyans
            "#e0f7fa", "#b2ebf2", "#80deea", "#4dd0e1", "#3db9c7", "#3399a3", "#28797e", "#1e5a5e",
            # Row 9: Greens
            "#e8f5e9", "#c8e6c9", "#a5d6a7", "#81c784", "#61b265", "#4f9652", "#3d7a40", "#2d5f2f",
        ]

        for i, color in enumerate(colors):
            row = i // 8
            col = i % 8
            swatch = self._create_swatch(color)
            self._color_grid.addWidget(swatch, row, col)

    def _build_material_palette(self):
        """Build Material Design color palette."""
        self._clear_color_grid()

        # Material Design colors (8 hues x 10 shades)
        colors = [
            # Row 0: Red
            "#ffebee", "#ffcdd2", "#ef9a9a", "#e57373", "#ef5350", "#f44336", "#e53935", "#c62828",
            # Row 1: Pink
            "#fce4ec", "#f8bbd0", "#f48fb1", "#f06292", "#ec407a", "#e91e63", "#d81b60", "#ad1457",
            # Row 2: Purple
            "#f3e5f5", "#e1bee7", "#ce93d8", "#ba68c8", "#ab47bc", "#9c27b0", "#8e24aa", "#6a1b9a",
            # Row 3: Deep Purple
            "#ede7f6", "#d1c4e9", "#b39ddb", "#9575cd", "#7e57c2", "#673ab7", "#5e35b1", "#4527a0",
            # Row 4: Indigo
            "#e8eaf6", "#c5cae9", "#9fa8da", "#7986cb", "#5c6bc0", "#3f51b5", "#3949ab", "#283593",
            # Row 5: Blue
            "#e3f2fd", "#bbdefb", "#90caf9", "#64b5f6", "#42a5f5", "#2196f3", "#1e88e5", "#1565c0",
            # Row 6: Light Blue
            "#e1f5fe", "#b3e5fc", "#81d4fa", "#4fc3f7", "#29b6f6", "#03a9f4", "#039be5", "#0277bd",
            # Row 7: Cyan
            "#e0f7fa", "#b2ebf2", "#80deea", "#4dd0e1", "#26c6da", "#00bcd4", "#00acc1", "#00838f",
            # Row 8: Teal
            "#e0f2f1", "#b2dfdb", "#80cbc4", "#4db6ac", "#26a69a", "#009688", "#00897b", "#00695c",
            # Row 9: Green
            "#e8f5e9", "#c8e6c9", "#a5d6a7", "#81c784", "#66bb6a", "#4caf50", "#43a047", "#2e7d32",
        ]

        for i, color in enumerate(colors):
            row = i // 8
            col = i % 8
            swatch = self._create_swatch(color)
            self._color_grid.addWidget(swatch, row, col)

    def _build_html_palette(self):
        """Build HTML named color palette with tooltips."""
        self._clear_color_grid()

        # 80 most useful HTML named colors with names for tooltips
        colors = [
            # Grays & B&W
            ("#000000", "black"), ("#080808", "gray 3%"), ("#101010", "gray 6%"), ("#181818", "gray 9%"),
            ("#202020", "gray 13%"), ("#282828", "gray 16%"), ("#303030", "gray 19%"), ("#383838", "gray 22%"),
            ("#404040", "gray 25%"), ("#484848", "gray 28%"), ("#505050", "gray 31%"), ("#585858", "gray 35%"),
            ("#606060", "gray 38%"), ("#686868", "gray 41%"), ("#707070", "gray 44%"), ("#787878", "gray 47%"),
            # Reds & Pinks
            ("#ff0000", "red"), ("#dc143c", "crimson"), ("#b22222", "firebrick"), ("#8b0000", "dark red"),
            ("#ff1493", "deep pink"), ("#c71585", "medium violet red"), ("#db7093", "pale violet red"), ("#ffb6c1", "light pink"),
            ("#ffc0cb", "pink"), ("#ff69b4", "hot pink"), ("#ff6347", "tomato"), ("#fa8072", "salmon"),
            ("#e9967a", "dark salmon"), ("#f08080", "light coral"), ("#cd5c5c", "indian red"), ("#bc8f8f", "rosy brown"),
            # Oranges & Browns
            ("#ffa500", "orange"), ("#ff8c00", "dark orange"), ("#ff7f50", "coral"), ("#ff4500", "orange red"),
            ("#d2691e", "chocolate"), ("#f4a460", "sandy brown"), ("#daa520", "golden rod"), ("#b8860b", "dark golden rod"),
            ("#8b4513", "saddle brown"), ("#a0522d", "sienna"), ("#cd853f", "peru"), ("#deb887", "burlywood"),
            ("#d2b48c", "tan"), ("#f5deb3", "wheat"), ("#fff8dc", "corn silk"), ("#ffe4b5", "moccasin"),
            # Yellows & Greens
            ("#ffff00", "yellow"), ("#ffd700", "gold"), ("#f0e68c", "khaki"), ("#fffacd", "lemon chiffon"),
            ("#adff2f", "green yellow"), ("#7fff00", "chartreuse"), ("#7cfc00", "lawn green"), ("#00ff00", "lime"),
            ("#32cd32", "lime green"), ("#228b22", "forest green"), ("#006400", "dark green"), ("#008000", "green"),
            ("#9acd32", "yellow green"), ("#6b8e23", "olive drab"), ("#556b2f", "dark olive green"), ("#808000", "olive"),
            # Cyans & Blues
            ("#00ffff", "cyan/aqua"), ("#00ced1", "dark turquoise"), ("#40e0d0", "turquoise"), ("#48d1cc", "medium turquoise"),
            ("#20b2aa", "light sea green"), ("#008b8b", "dark cyan"), ("#008080", "teal"), ("#5f9ea0", "cadet blue"),
            ("#0000ff", "blue"), ("#0000cd", "medium blue"), ("#00008b", "dark blue"), ("#4169e1", "royal blue"),
            ("#6495ed", "cornflower blue"), ("#87ceeb", "sky blue"), ("#87cefa", "light sky blue"), ("#add8e6", "light blue"),
            # Purples & Misc
            ("#800080", "purple"), ("#8b008b", "dark magenta"), ("#9400d3", "dark violet"), ("#9932cc", "dark orchid"),
            ("#ba55d3", "medium orchid"), ("#da70d6", "orchid"), ("#ee82ee", "violet"), ("#dda0dd", "plum"),
            ("#d8bfd8", "thistle"), ("#e6e6fa", "lavender"), ("#f8f8ff", "ghost white"), ("#fffafa", "snow"),
            ("#fffaf0", "floral white"), ("#fffff0", "ivory"), ("#f5f5dc", "beige"), ("#ffffff", "white"),
        ]

        for i, (color, name) in enumerate(colors):
            row = i // 8
            col = i % 8
            swatch = self._create_swatch(color, tooltip=name)
            self._color_grid.addWidget(swatch, row, col)

    def _build_pastel_palette(self):
        """Build pastel color palette."""
        self._clear_color_grid()

        colors = [
            # Soft pastels - 10 rows x 8 columns
            "#ffb3ba", "#ffdfba", "#ffffba", "#baffc9", "#bae1ff", "#eecbff", "#ffcbf2", "#ffd9e8",
            "#ff9aa2", "#ffb7b2", "#ffdac1", "#fff4b2", "#c7f9cc", "#b5eadd", "#c9c9ff", "#eecbff",
            "#f4a3a8", "#f8b4a8", "#f9d5bb", "#fcf6bd", "#d0f4de", "#a9def9", "#e4c1f9", "#f6c6ff",
            "#e5989b", "#ffb5a7", "#fec5bb", "#fcd5ce", "#f8edeb", "#fae1dd", "#f9dedc", "#fce4ec",
            "#ffcad4", "#ffdac1", "#ffe5d9", "#ffeedd", "#fff0e5", "#f8edeb", "#f5ebe0", "#e6e2dd",
            "#f8ad9d", "#fbc4ab", "#ffdac1", "#ffeedd", "#f3e5f5", "#e1f5fe", "#e8f5e9", "#fff3e0",
            "#f4978e", "#f8ad9d", "#fbc4ab", "#ffdac1", "#e0f7fa", "#f3e5f5", "#fce4ec", "#f9fbe7",
            "#f08080", "#f4a3a8", "#f7b2ad", "#fad0c4", "#e0f2f1", "#e8eaf6", "#f3e5f5", "#fff9c4",
            "#e63946", "#f4a261", "#e9c46a", "#2a9d8f", "#264653", "#e76f51", "#f4a261", "#e9c46a",
            "#f1faee", "#a8dadc", "#457b9d", "#1d3557", "#e63946", "#f1faee", "#a8dadc", "#457b9d",
        ]

        for i, color in enumerate(colors):
            row = i // 8
            col = i % 8
            swatch = self._create_swatch(color)
            self._color_grid.addWidget(swatch, row, col)

    def _build_neon_palette(self):
        """Build neon/bright color palette."""
        self._clear_color_grid()

        colors = [
            # Neon colors - bright and saturated
            "#ff0000", "#ff4500", "#ff8c00", "#ffd700", "#7fff00", "#00ff00", "#00fa9a", "#00ffff",
            "#ff1493", "#ff0066", "#ff00ff", "#bf00ff", "#8b00ff", "#0000ff", "#0080ff", "#00bfff",
            "#ff3333", "#ff6347", "#ff8c69", "#ffdb58", "#9acd32", "#32cd32", "#3cb371", "#40e0d0",
            "#ff69b4", "#ff1493", "#ee82ee", "#da70d6", "#ba55d3", "#9370db", "#7b68ee", "#6495ed",
            "#ff6666", "#ff7f50", "#ffa07a", "#f0e68c", "#adff2f", "#7cfc00", "#00ff7f", "#66cdaa",
            "#ff6eb4", "#ff69b4", "#dda0dd", "#d8bfd8", "#e6e6fa", "#b0c4de", "#add8e6", "#87cefa",
            "#ff8080", "#ff9999", "#ffb6c1", "#ffc0cb", "#ffd700", "#ffff00", "#ffff99", "#ffffcc",
            "#ff00cc", "#ff00aa", "#ff0080", "#ff0060", "#ff0040", "#ff0020", "#ff0010", "#ff0008",
            "#00ff00", "#20ff20", "#40ff40", "#60ff60", "#80ff80", "#a0ffa0", "#c0ffc0", "#e0ffe0",
            "#0000ff", "#2020ff", "#4040ff", "#6060ff", "#8080ff", "#a0a0ff", "#c0c0ff", "#e0e0ff",
        ]

        for i, color in enumerate(colors):
            row = i // 8
            col = i % 8
            swatch = self._create_swatch(color)
            self._color_grid.addWidget(swatch, row, col)

    def _build_viridis_palette(self):
        """Build Viridis colormap palette."""
        self._clear_color_grid()

        # Viridis colormap colors (perceptually uniform)
        colors = [
            "#440154", "#471669", "#481b6d", "#482070", "#46307e", "#443983", "#3f4889", "#3e4a89",
            "#3d538b", "#3a5c8d", "#3a548c", "#36638c", "#34608d", "#31688e", "#2f6c8e", "#2e6f8e",
            "#2c728e", "#2a768e", "#287c8e", "#26818e", "#25848e", "#238a8d", "#228d8d", "#21918c",
            "#20928c", "#1f958b", "#1e998a", "#1f9a8a", "#1d9e89", "#1da088", "#20a386", "#22a785",
            "#24aa83", "#29af7f", "#2cb17e", "#31b57b", "#35b779", "#3bbc74", "#3ebe70", "#42be71",
            "#46c06f", "#4ac16d", "#4ec36b", "#52c569", "#56c667", "#5ac864", "#5ec962", "#62cb5f",
            "#65cb5e", "#69cd5b", "#6ece58", "#73d056", "#77d153", "#7ad150", "#7fd34e", "#81d34d",
            "#85d449", "#88d547", "#8cd646", "#8fd744", "#93d741", "#96d840", "#9ad93c", "#9dd93b",
            "#a0da39", "#a3db37", "#aadc32", "#addc30", "#b0dd2e", "#b3de2f", "#b6de2e", "#b9e02c",
            "#bce028", "#bfe128", "#c3e126", "#c6e224", "#c9e223", "#cce324", "#d0e226", "#d3e229",
        ]

        for i, color in enumerate(colors):
            row = i // 8
            col = i % 8
            swatch = self._create_swatch(color)
            self._color_grid.addWidget(swatch, row, col)

    def _build_plasma_palette(self):
        """Build Plasma colormap palette."""
        self._clear_color_grid()

        # Plasma colormap colors
        colors = [
            "#0d0887", "#140da3", "#1a0dab", "#2510b5", "#3013bb", "#3b16bf", "#4519c2", "#4f1cc5",
            "#581ec8", "#6221ca", "#6c24cc", "#7627ce", "#8029d0", "#892cd1", "#932fd3", "#9c31d4",
            "#a633d5", "#b036d6", "#b938d7", "#c33bd8", "#cc3dd8", "#d540d9", "#dd42d9", "#e645d9",
            "#ee48d9", "#f44bd9", "#f74fd9", "#f952d8", "#fb56d7", "#fc5ad6", "#fd5ed5", "#fe62d3",
            "#fe67d2", "#fe6bd0", "#fe70ce", "#fe75cc", "#fe79c9", "#fe7ec7", "#fe82c4", "#fe87c2",
            "#fe8cbf", "#fe90bc", "#fe95b9", "#fe9ab6", "#fe9fb3", "#fea3b0", "#fea8ad", "#feadaa",
            "#feb1a7", "#feb6a4", "#febba1", "#febf9e", "#fec49b", "#fec998", "#fece95", "#fed392",
            "#fed78f", "#ffdc8c", "#ffe189", "#ffe685", "#ffeb82", "#fff07f", "#fff57c", "#fffa79",
            "#ffff77", "#fffa7a", "#fff67d", "#fff17f", "#ffed82", "#ffe885", "#ffe488", "#ffdf8a",
            "#ffdb8d", "#ffd68f", "#ffd292", "#ffcd95", "#ffc997", "#ffc49a", "#ffc09d", "#ffbb9f",
        ]

        for i, color in enumerate(colors):
            row = i // 8
            col = i % 8
            swatch = self._create_swatch(color)
            self._color_grid.addWidget(swatch, row, col)
                
    def _create_swatch(self, color: str, tooltip: Optional[str] = None) -> QtWidgets.QPushButton:
        """Create a color swatch button with optional tooltip."""
        swatch = QtWidgets.QPushButton()
        swatch.setFixedSize(18, 18)
        swatch.setStyleSheet(f"""
            QPushButton {{
                background: {color};
                border: 1px solid #dadce0;
                border-radius: 2px;
            }}
            QPushButton:hover {{
                border: 2px solid #1a73e8;
            }}
        """)
        if tooltip:
            swatch.setToolTip(f"{tooltip} ({color})")
        swatch.clicked.connect(lambda checked, c=color: self._select_color(c))
        return swatch
        
    def _on_no_fill_changed(self, state):
        """Handle No Fill checkbox toggle."""
        if state == QtCore.Qt.CheckState.Checked.value:
            self.no_fill_selected.emit()
            self.close()
            
    def _on_palette_changed(self, index):
        """Handle palette type change."""
        palette_type = self._palette_selector.currentData()
        if palette_type == "standard":
            self._build_standard_palette()
        elif palette_type == "material":
            self._build_material_palette()
        elif palette_type == "html":
            self._build_html_palette()
        elif palette_type == "pastel":
            self._build_pastel_palette()
        elif palette_type == "neon":
            self._build_neon_palette()
        elif palette_type == "viridis":
            self._build_viridis_palette()
        elif palette_type == "plasma":
            self._build_plasma_palette()
        
    def _select_color(self, color_hex: str):
        """Select a color and emit signal."""
        self._save_recent_color(color_hex)
        self.color_selected.emit(color_hex)
        self.close()
        
    def _on_custom_color(self):
        """Open custom color dialog."""
        color = QtWidgets.QColorDialog.getColor(
            QtGui.QColor(self._initial_color or "#FFFFFF"),
            self,
            "Custom Color"
        )
        if color.isValid():
            self._select_color(color.name())
            
    def _save_recent_color(self, color_hex: str):
        """Add color to recent list."""
        if color_hex in self._recent_colors:
            self._recent_colors.remove(color_hex)
        self._recent_colors.insert(0, color_hex)
        self._recent_colors = self._recent_colors[:8]
        self._update_recent_display()
        
    def _update_recent_display(self):
        """Update the recent colors display."""
        # Clear existing
        while self._recent_layout.count():
            item = self._recent_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        # Add swatches for recent colors
        for color in self._recent_colors:
            swatch = self._create_swatch(color)
            self._recent_layout.addWidget(swatch)
            
        # Add empty placeholders
        for _ in range(8 - len(self._recent_colors)):
            placeholder = QtWidgets.QFrame()
            placeholder.setFixedSize(18, 18)
            placeholder.setStyleSheet("background: transparent; border: none;")
            self._recent_layout.addWidget(placeholder)
            
        self._recent_layout.addStretch()
        
    def set_recent_colors(self, colors: list[str]):
        """Set the recent colors list externally."""
        self._recent_colors = colors[:8]
        self._update_recent_display()
        
    def get_recent_colors(self) -> list[str]:
        """Get the current recent colors list."""
        return self._recent_colors[:8]


def show_color_picker(
    parent: QtWidgets.QWidget,
    target_button: QtWidgets.QPushButton,
    on_color_selected: Callable[[str], None],
    recent_colors: Optional[list[str]] = None,
    initial_color: Optional[str] = None
) -> MiniColorPicker:
    """
    Show a color picker popup below a target button.
    
    Args:
        parent: Parent widget
        target_button: Button to position popup below
        on_color_selected: Callback when color is selected
        recent_colors: Optional list of recent colors
        initial_color: Optional initially selected color
        
    Returns:
        The MiniColorPicker instance
    """
    picker = MiniColorPicker(parent, initial_color)
    
    if recent_colors:
        picker.set_recent_colors(recent_colors)
        
    picker.color_selected.connect(on_color_selected)
    picker.no_fill_selected.connect(lambda: on_color_selected(""))
    
    # Position below button
    btn_pos = target_button.mapToGlobal(QtCore.QPoint(0, target_button.height()))
    picker.move(btn_pos)
    picker.show()

    return picker


class MiniFontColorButton(QtWidgets.QPushButton):
    """
    Font color button with "A" icon, colored underline, and dropdown triangle.
    - Click main area: apply color (stub for macro)
    - Click triangle: open color picker
    """

    color_changed = QtCore.Signal(str)  # Emits when color changes
    color_applied = QtCore.Signal(str)  # Emits when color should be applied (macro)

    # Width of the dropdown triangle area on the right
    DROPDOWN_WIDTH = 10

    def __init__(self, parent=None, show_auto_checkbox: bool = True):
        super().__init__(parent)
        self._current_color: Optional[str] = None
        self._recent_colors: list[str] = []
        self._show_auto = show_auto_checkbox
        self._is_auto = True  # Default to automatic
        self._dropdown_hovered = False

        self.setFixedSize(32, 28)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._on_clicked)
        self._update_appearance()

    def _update_appearance(self):
        """Update button appearance based on current state."""
        self.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 1px solid transparent;
                border-radius: 3px;
                padding: 0px;
            }
            QPushButton:hover {
                background: #e8f0fe;
                border-color: #dadce0;
            }
        """)
        self.update()

    def mouseMoveEvent(self, event):
        """Track mouse position to show dropdown hover."""
        rect = self.rect()
        dropdown_rect = QtCore.QRect(rect.width() - self.DROPDOWN_WIDTH, 0, self.DROPDOWN_WIDTH, rect.height())
        was_hovered = self._dropdown_hovered
        self._dropdown_hovered = dropdown_rect.contains(event.pos())
        if was_hovered != self._dropdown_hovered:
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        """Clear dropdown hover when mouse leaves."""
        self._dropdown_hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        """Custom paint to draw "A", colored underline, and dropdown triangle."""
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        main_width = rect.width() - self.DROPDOWN_WIDTH

        # Draw "A" higher up
        painter.setPen(QtGui.QPen(QtGui.QColor("#000000")))
        painter.setFont(QtGui.QFont("Arial", 12, QtGui.QFont.Weight.Bold))
        a_rect = QtCore.QRect(0, 0, main_width, rect.height() - 6)
        painter.drawText(a_rect, QtCore.Qt.AlignmentFlag.AlignCenter | QtCore.Qt.AlignmentFlag.AlignBottom, "A")

        # Draw colored underline
        if self._is_auto:
            underline_color = QtGui.QColor("#000000")
        else:
            underline_color = QtGui.QColor(self._current_color or "#000000")

        painter.setPen(QtGui.QPen(underline_color, 3))
        underline_y = rect.bottom() - 4
        painter.drawLine(4, underline_y, main_width - 4, underline_y)

        # Draw vertical separator line
        # painter.setPen(QtGui.QPen(QtGui.QColor("#dadce0"), 1))
        # painter.drawLine(main_width, 4, main_width, rect.height() - 4)

        # Draw dropdown triangle
        if self._dropdown_hovered:
            painter.fillRect(QtCore.QRect(main_width, 0, self.DROPDOWN_WIDTH, rect.height()), QtGui.QColor("#e8f0fe"))

        triangle_color = QtGui.QColor("#5f6368")
        painter.setPen(QtGui.QPen(triangle_color, 1))
        painter.setBrush(triangle_color)

        # Small triangle pointing down
        triangle_x = main_width + 2
        triangle_y = rect.height() // 2 - 1
        triangle_size = 4
        path = QtGui.QPainterPath()
        path.moveTo(triangle_x, triangle_y)
        path.lineTo(triangle_x + triangle_size, triangle_y)
        path.lineTo(triangle_x + triangle_size / 2, triangle_y + triangle_size)
        path.closeSubpath()
        painter.drawPath(path)

        painter.end()

    def _on_clicked(self):
        """Handle click - determine if main area or dropdown."""
        click_pos = self.mapFromGlobal(QtGui.QCursor.pos())
        rect = self.rect()
        main_width = rect.width() - self.DROPDOWN_WIDTH

        if click_pos.x() > main_width:
            # Clicked on dropdown triangle - show picker
            self._show_picker()
        else:
            # Clicked on main area - apply color (stub)
            self._apply_color()

    def _apply_color(self):
        """Apply the current color via macro."""
        color = "" if self._is_auto else (self._current_color or "#000000")
        self.color_applied.emit(color)

    def _show_picker(self):
        """Show the color picker popup."""
        picker = MiniColorPicker(self, self._current_color)
        picker.set_recent_colors(self._recent_colors)

        # Update checkbox visibility
        if hasattr(picker, '_no_fill_checkbox'):
            picker._no_fill_checkbox.setVisible(self._show_auto)
            if self._show_auto:
                picker._no_fill_checkbox.setText("Automatic")
                picker._no_fill_checkbox.setChecked(self._is_auto)

        def on_color_selected(color_hex: str):
            self._is_auto = False
            self._current_color = color_hex
            self._save_recent_color(color_hex)
            self._update_appearance()
            self.color_changed.emit(color_hex)

        def on_no_fill():
            self._is_auto = True
            self._current_color = None
            self._update_appearance()
            self.color_changed.emit("")

        picker.color_selected.connect(on_color_selected)
        picker.no_fill_selected.connect(on_no_fill)

        # Position below button
        btn_pos = self.mapToGlobal(QtCore.QPoint(0, self.height()))
        picker.move(btn_pos)
        picker.show()

    def _save_recent_color(self, color_hex: str):
        """Save color to recent list."""
        if color_hex in self._recent_colors:
            self._recent_colors.remove(color_hex)
        self._recent_colors.insert(0, color_hex)
        self._recent_colors = self._recent_colors[:8]

    def get_color(self) -> Optional[str]:
        """Get current selected color."""
        return None if self._is_auto else self._current_color

    def set_color(self, color_hex: Optional[str]):
        """Set the current color."""
        if color_hex is None or color_hex == "":
            self._is_auto = True
            self._current_color = None
        else:
            self._is_auto = False
            self._current_color = color_hex
        self._update_appearance()

    def is_automatic(self) -> bool:
        """Check if using automatic color."""
        return self._is_auto


class MiniCellFillButton(QtWidgets.QPushButton):
    """
    Cell fill/background color button with paint bucket icon, colored bar, and dropdown triangle.
    - Click main area: apply color (stub for macro)
    - Click triangle: open color picker
    """

    color_changed = QtCore.Signal(str)  # Emits when color changes
    color_applied = QtCore.Signal(str)  # Emits when color should be applied (macro)

    # Width of the dropdown triangle area on the right
    DROPDOWN_WIDTH = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_color: Optional[str] = None
        self._recent_colors: list[str] = []
        self._dropdown_hovered = False

        self.setFixedSize(32, 28)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._on_clicked)
        self._update_appearance()

    def _update_appearance(self):
        """Update button appearance based on current state."""
        self.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 1px solid transparent;
                border-radius: 3px;
                padding: 0px;
            }
            QPushButton:hover {
                background: #e8f0fe;
                border-color: #dadce0;
            }
        """)
        self.update()

    def mouseMoveEvent(self, event):
        """Track mouse position to show dropdown hover."""
        rect = self.rect()
        dropdown_rect = QtCore.QRect(rect.width() - self.DROPDOWN_WIDTH, 0, self.DROPDOWN_WIDTH, rect.height())
        was_hovered = self._dropdown_hovered
        self._dropdown_hovered = dropdown_rect.contains(event.pos())
        if was_hovered != self._dropdown_hovered:
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        """Clear dropdown hover when mouse leaves."""
        self._dropdown_hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        """Custom paint to draw Lucide paint-bucket icon, colored bar, and dropdown triangle."""
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        main_width = rect.width() - self.DROPDOWN_WIDTH
        fill_color = QtGui.QColor(self._current_color or "#e8f0fe")

        # Draw colored bar at bottom (same style as font color button)
        bar_y = rect.bottom() - 4
        painter.setPen(QtGui.QPen(fill_color, 3))
        painter.drawLine(4, bar_y, main_width - 4, bar_y)

        # Draw vertical separator line
        # painter.setPen(QtGui.QPen(QtGui.QColor("#dadce0"), 1))
        # painter.drawLine(main_width, 4, main_width, rect.height() - 4)

        # Draw the paint-bucket icon from the zipped icon store, colorized to
        # match the Toolbox Editor palette icon. We render to a temporary
        # pixmap and use SourceIn to apply the dark gray color because the
        # SVG uses currentColor.
        try:
            renderer = load_svg_renderer("lucide/icons/paint-bucket")
            icon_size = 16
            pixmap = QtGui.QPixmap(icon_size, icon_size)
            pixmap.fill(QtCore.Qt.GlobalColor.transparent)
            icon_painter = QtGui.QPainter(pixmap)
            renderer.render(icon_painter)
            icon_painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceIn)
            icon_painter.fillRect(pixmap.rect(), QtGui.QColor("#5f6368"))
            icon_painter.end()
            icon_x = 4 + (main_width - 8 - icon_size) // 2
            icon_y = 3 + (rect.height() - 8 - icon_size) // 2
            painter.drawPixmap(icon_x, icon_y, pixmap)
        except Exception:
            # Fallback: draw a simple bucket outline
            painter.setPen(QtGui.QPen(QtGui.QColor("#5f6368"), 1.5))
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            bucket_top = 5
            bucket_bottom = rect.height() // 2 + 1
            bucket_left = 5
            bucket_right = main_width - 5
            path = QtGui.QPainterPath()
            path.moveTo(bucket_left + 2, bucket_top + 4)
            path.lineTo(bucket_right - 2, bucket_top + 4)
            path.lineTo(bucket_right - 4, bucket_bottom - 2)
            path.lineTo(bucket_left + 4, bucket_bottom - 2)
            path.closeSubpath()
            painter.drawPath(path)
            painter.drawArc(bucket_left + 3, bucket_top - 1, 10, 6, 0, 180 * 16)
            painter.setPen(QtGui.QPen(QtGui.QColor("#5f6368"), 1.2))
            handle_path = QtGui.QPainterPath()
            handle_path.moveTo(bucket_right - 3, bucket_top + 2)
            handle_path.quadTo(bucket_right + 2, bucket_top - 1, bucket_right + 1, bucket_top + 4)
            painter.drawPath(handle_path)

        # Draw dropdown triangle
        if self._dropdown_hovered:
            painter.fillRect(QtCore.QRect(main_width, 0, self.DROPDOWN_WIDTH, rect.height()), QtGui.QColor("#e8f0fe"))

        triangle_color = QtGui.QColor("#5f6368")
        painter.setPen(QtGui.QPen(triangle_color, 1))
        painter.setBrush(triangle_color)

        # Small triangle pointing down
        triangle_x = main_width + 2
        triangle_y = rect.height() // 2 - 1
        triangle_size = 4
        path = QtGui.QPainterPath()
        path.moveTo(triangle_x, triangle_y)
        path.lineTo(triangle_x + triangle_size, triangle_y)
        path.lineTo(triangle_x + triangle_size / 2, triangle_y + triangle_size)
        path.closeSubpath()
        painter.drawPath(path)

        painter.end()

    def _on_clicked(self):
        """Handle click - determine if main area or dropdown."""
        click_pos = self.mapFromGlobal(QtGui.QCursor.pos())
        rect = self.rect()
        main_width = rect.width() - self.DROPDOWN_WIDTH

        if click_pos.x() > main_width:
            # Clicked on dropdown triangle - show picker
            self._show_picker()
        else:
            # Clicked on main area - apply color (stub)
            self._apply_color()

    def _apply_color(self):
        """Apply the current color (stub for macro execution)."""
        color = self._current_color or ""
        print(f"[STUB] Apply cell fill color: {color if color else 'none'}")
        self.color_applied.emit(color)

    def _show_picker(self):
        """Show the color picker popup."""
        picker = MiniColorPicker(self, self._current_color)
        picker.set_recent_colors(self._recent_colors)

        def on_color_selected(color_hex: str):
            self._current_color = color_hex
            self._save_recent_color(color_hex)
            self._update_appearance()
            self.color_changed.emit(color_hex)

        def on_no_fill():
            self._current_color = None
            self._update_appearance()
            self.color_changed.emit("")

        picker.color_selected.connect(on_color_selected)
        picker.no_fill_selected.connect(on_no_fill)

        # Position below button
        btn_pos = self.mapToGlobal(QtCore.QPoint(0, self.height()))
        picker.move(btn_pos)
        picker.show()

    def _save_recent_color(self, color_hex: str):
        """Save color to recent list."""
        if color_hex in self._recent_colors:
            self._recent_colors.remove(color_hex)
        self._recent_colors.insert(0, color_hex)
        self._recent_colors = self._recent_colors[:8]

    def get_color(self) -> Optional[str]:
        """Get current selected color."""
        return self._current_color

    def set_color(self, color_hex: Optional[str]):
        """Set the current color."""
        self._current_color = color_hex if color_hex else None
        self._update_appearance()
