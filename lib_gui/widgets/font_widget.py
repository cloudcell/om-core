"""
Font Name Dropdown Widget.
Uses QListView with virtual items for fast rendering.
"""

from PySide6 import QtWidgets, QtCore, QtGui
from typing import Optional

SAMPLE_TEXT = "ABCxyz Illusion10O"


class FontNameDropdown(QtWidgets.QPushButton):
    """
    Fast font dropdown using QListView with virtual items.
    Only renders visible fonts for smooth performance.
    """
    
    font_selected = QtCore.Signal(str)
    _cached_fonts: list[str] = []
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._current_font: str = "Arial"
        self._popup: Optional[FontPickerPopup] = None
        
        # Fixed width with triangle indicator - smaller to prevent layout shifts
        self.setFixedSize(160, 26)
        
        # Prevent expanding and ignore extra space in toolbar
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        
        # Clear any button text to prevent overlap with label
        super().setText("")
        
        # Use layout with font label and triangle
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 4, 0)
        layout.setSpacing(2)
        
        # Font name label
        self._font_label = QtWidgets.QLabel(self._current_font)
        self._font_label.setStyleSheet("color: #374151; background: transparent;")
        self._font_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._font_label, 1)
        
        # Triangle indicator
        self._triangle = QtWidgets.QLabel("▼")
        self._triangle.setStyleSheet("color: #6B7280; font-size: 8px; background: transparent;")
        self._triangle.setFixedWidth(10)
        layout.addWidget(self._triangle)
        
        self.setStyleSheet("""
            QPushButton {
                background: white;
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 0px;
            }
            QPushButton:hover {
                border-color: #9CA3AF;
                background: #F9FAFB;
            }
            QPushButton:pressed {
                background: #F3F4F6;
            }
        """)
        
        self.clicked.connect(self._show_font_popup)
        self._update_display()
        
    @classmethod
    def _get_fonts(cls) -> tuple[list[str], list[str]]:
        """Load fonts once and cache, separating monospace from proportional."""
        if not cls._cached_fonts:
            font_db = QtGui.QFontDatabase()
            all_fonts = sorted(font_db.families())
            
            # Known monospace font name patterns
            MONO_PATTERNS = ['mono', 'courier', 'consolas', 'inconsolata', 'source code',
                           'fira code', 'jetbrains', 'cascadia', 'ubuntu mono', 'noto mono',
                           'liberation mono', 'dejavu sans mono', 'roboto mono',
                           ' SF Mono', 'Menlo', 'Hack', 'Droid Sans Mono', 'Lucida Console',
                           'monaco', 'andale mono', 'ocr a', 'code new roman']
            
            # Separate monospace fonts using multiple detection methods
            monospace = []
            proportional = []
            for name in all_fonts:
                is_mono = False
                lower_name = name.lower()
                
                # Method 1: Qt's built-in fixed pitch detection
                font = QtGui.QFont(name)
                if font.fixedPitch() or font_db.isFixedPitch(name):
                    is_mono = True
                
                # Method 2: Check font name patterns
                if not is_mono:
                    for pattern in MONO_PATTERNS:
                        if pattern in lower_name:
                            is_mono = True
                            break
                
                # Method 3: Measure character widths (slow but accurate)
                if not is_mono:
                    metrics = QtGui.QFontMetrics(font)
                    w_i = metrics.horizontalAdvance('i')
                    w_m = metrics.horizontalAdvance('M')
                    w_space = metrics.horizontalAdvance(' ')
                    # In monospace, common chars should have same width
                    if abs(w_i - w_m) < 2 and abs(w_i - w_space) < 2 and w_i > 0:
                        is_mono = True
                
                if is_mono:
                    monospace.append(name)
                else:
                    proportional.append(name)
            
            cls._cached_fonts = (monospace, proportional)
        return cls._cached_fonts
        
    def _update_display(self):
        """Update label to show current font."""
        self._font_label.setText(self._current_font)
        font = QtGui.QFont(self._current_font)
        font.setPointSize(10)
        self._font_label.setFont(font)
        
    def _show_font_popup(self):
        """Show the fast font picker popup."""
        monospace_fonts, proportional_fonts = self._get_fonts()
        
        self._popup = FontPickerPopup(monospace_fonts, proportional_fonts, self._current_font, self)
        self._popup.font_selected.connect(self._on_font_selected)
        
        pos = self.mapToGlobal(QtCore.QPoint(0, self.height()))
        self._popup.move(pos)
        self._popup.show()
        
    def _on_font_selected(self, font_name: str):
        """Handle font selection."""
        if font_name != self._current_font:
            self._current_font = font_name
            self._update_display()
            print(f"[FontNameDropdown] Selected: {font_name}")
            self.font_selected.emit(font_name)
            
    def get_current_font(self) -> str:
        return self._current_font
        
    def set_current_font(self, font_name: str):
        """Set the current font."""
        monospace, proportional = self._get_fonts()
        if font_name in monospace or font_name in proportional:
            self._current_font = font_name
            self._update_display()
            
    def refresh_fonts(self):
        FontNameDropdown._cached_fonts = []
        self._get_fonts()


class FontPickerPopup(QtWidgets.QFrame):
    """Fast font picker using QListView with virtual items."""
    
    font_selected = QtCore.Signal(str)
    
    def __init__(self, monospace_fonts: list[str], proportional_fonts: list[str], 
                 current_font: str, parent=None):
        super().__init__(parent, QtCore.Qt.WindowType.Popup)
        
        self._monospace_fonts = monospace_fonts
        self._proportional_fonts = proportional_fonts
        self._current_font = current_font
        
        self.setFixedSize(420, 400)
        self.setStyleSheet("""
            QFrame {
                background: white;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
            }
        """)
        
        self._setup_ui()
        
    def _setup_ui(self):
        """Set up the popup UI with QListView."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header = QtWidgets.QFrame()
        header.setStyleSheet("""
            QFrame {
                background: #E8F4FD;
                border-bottom: 1px solid #BFDBFE;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }
        """)
        header_layout = QtWidgets.QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 12, 8)
        
        header_label = QtWidgets.QLabel(f"Current: {self._current_font}")
        header_label.setStyleSheet("color: #1E40AF; font-weight: bold;")
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        
        layout.addWidget(header)
        
        # Separator line
        sep = QtWidgets.QFrame()
        sep.setFixedHeight(2)
        sep.setStyleSheet("background: #E5E7EB;")
        layout.addWidget(sep)
        
        # ListView for fonts - virtual items for speed
        self._list_view = QtWidgets.QListView()
        self._list_view.setFixedHeight(340)
        self._list_view.setSpacing(0)
        self._list_view.setAlternatingRowColors(False)  # We handle alternation manually
        
        # Model with both font lists
        self._model = FontListModel(self._monospace_fonts, self._proportional_fonts, 
                                     self._current_font, self)
        self._list_view.setModel(self._model)
        
        # Delegate for custom rendering
        delegate = FontItemDelegate(self._list_view)
        self._list_view.setItemDelegate(delegate)
        
        # Selection - enable hover tracking
        self._list_view.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self._list_view.setMouseTracking(True)
        self._list_view.entered.connect(self._on_item_hovered)
        self._list_view.clicked.connect(self._on_item_clicked)
        
        # Track last hovered font to avoid duplicate signals
        self._last_hovered_font: Optional[str] = None
        
        # Scroll to current font
        idx = self._model.index_for_font(self._current_font)
        if idx >= 0:
            model_idx = self._model.index(idx, 0)
            self._list_view.scrollTo(model_idx, QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter)
            self._list_view.setCurrentIndex(model_idx)
        
        layout.addWidget(self._list_view)
        
        # Style the list - hover handled by delegate
        self._list_view.setStyleSheet("""
            QListView {
                border: none;
                background: white;
                outline: none;
            }
            QListView::item {
                min-height: 26px;
                padding: 0px;
                border: none;
            }
            QListView::item:selected {
                background: transparent;
                border: none;
            }
        """)
        
    def _on_item_hovered(self, index: QtCore.QModelIndex):
        """Highlight font on hover (visual only, no selection)."""
        if not index.isValid():
            return
            
        # Set current index for visual highlighting only
        self._list_view.setCurrentIndex(index)
        
    def _on_item_clicked(self, index: QtCore.QModelIndex):
        """Close popup on click."""
        if not index.isValid():
            return
            
        font_name = self._model.font_at(index.row())
        if font_name:
            self.font_selected.emit(font_name)
            self.close()


class FontListModel(QtCore.QAbstractListModel):
    """Virtual list model with monospace and proportional sections."""
    
    # Row types
    TYPE_HEADER = 0
    TYPE_FONT = 1
    
    # Sections
    SECTION_MONO = 0
    SECTION_PROP = 1
    
    def __init__(self, monospace_fonts: list[str], proportional_fonts: list[str], 
                 current_font: str, parent=None):
        super().__init__(parent)
        self._current_font = current_font
        
        # Build row mapping: list of (type, section, data) tuples
        # where data is header text for headers, font name for fonts
        self._rows = []
        
        # Monospace section
        if monospace_fonts:
            self._rows.append((self.TYPE_HEADER, self.SECTION_MONO, "Monospace Fonts"))
            for font in monospace_fonts:
                self._rows.append((self.TYPE_FONT, self.SECTION_MONO, font))
        
        # Proportional section
        if proportional_fonts:
            self._rows.append((self.TYPE_HEADER, self.SECTION_PROP, "Proportional Fonts"))
            for font in proportional_fonts:
                self._rows.append((self.TYPE_FONT, self.SECTION_PROP, font))
        
    def rowCount(self, parent=QtCore.QModelIndex()) -> int:
        return len(self._rows)
        
    def data(self, index: QtCore.QModelIndex, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
            
        row = index.row()
        if row < 0 or row >= len(self._rows):
            return None
            
        row_type, section, row_data = self._rows[row]
        
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return row_data
        elif role == QtCore.Qt.ItemDataRole.UserRole + 1:  # Type role
            return row_type
        elif role == QtCore.Qt.ItemDataRole.UserRole + 2:  # Section role
            return section
        elif role == QtCore.Qt.ItemDataRole.FontRole:
            if row_type == self.TYPE_FONT:
                font = QtGui.QFont(row_data)
                font.setPointSize(11)
                return font
        elif role == QtCore.Qt.ItemDataRole.UserRole:  # Is current font
            if row_type == self.TYPE_FONT:
                return row_data == self._current_font
            
        return None
        
    def font_at(self, row: int) -> Optional[str]:
        if 0 <= row < len(self._rows):
            row_type, section, row_data = self._rows[row]
            if row_type == self.TYPE_FONT:
                return row_data
        return None
        
    def index_for_font(self, font_name: str) -> int:
        """Find the row index for a given font name."""
        for i, (row_type, section, row_data) in enumerate(self._rows):
            if row_type == self.TYPE_FONT and row_data == font_name:
                return i
        return -1


class FontItemDelegate(QtWidgets.QStyledItemDelegate):
    """Custom delegate with dark headers and section-based zebra shading."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
    
    def _is_zebra_alt(self, model, index, section):
        """Count how many font items come before this one in the same section."""
        row = index.row()
        count = 0
        for i in range(row):
            idx = model.index(i, 0)
            row_type = idx.data(QtCore.Qt.ItemDataRole.UserRole + 1)
            row_section = idx.data(QtCore.Qt.ItemDataRole.UserRole + 2)
            if row_type == FontListModel.TYPE_FONT and row_section == section:
                count += 1
        return count % 2 == 1
    
    def paint(self, painter: QtGui.QPainter, option, index):
        """Paint item with section-based zebra shading and hover."""
        model = index.model()
        text = index.data(QtCore.Qt.ItemDataRole.DisplayRole)
        row_type = index.data(QtCore.Qt.ItemDataRole.UserRole + 1)
        section = index.data(QtCore.Qt.ItemDataRole.UserRole + 2)
        is_current = index.data(QtCore.Qt.ItemDataRole.UserRole) or False
        
        # Check if this item is hovered
        is_hovered = option.state & QtWidgets.QStyle.StateFlag.State_MouseOver
        
        if row_type == FontListModel.TYPE_HEADER:
            # Dark gray header with white text
            painter.fillRect(option.rect, QtGui.QColor("#374151"))
            painter.setPen(QtGui.QColor("white"))
            painter.setFont(QtGui.QFont("Arial", 9, QtGui.QFont.Weight.Bold))
            painter.drawText(option.rect.adjusted(12, 0, -12, 0), 
                           QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter,
                           text)
            return
        
        # Font row - compute zebra based on position within section (not paint order)
        is_alt = self._is_zebra_alt(model, index, section)
        
        # Determine base background color (zebra)
        base_color = None
        if section == FontListModel.SECTION_MONO:
            # Monospace: darker zebra (gray tones)
            if is_alt:
                base_color = QtGui.QColor("#E5E7EB")  # Darker gray
            else:
                base_color = QtGui.QColor("#F3F4F6")  # Medium gray
        else:
            # Proportional: lighter zebra (white tones)
            if is_alt:
                base_color = QtGui.QColor("#FAFAFA")  # Very light gray
            else:
                base_color = QtGui.QColor("white")
        
        # Always paint zebra background first
        painter.fillRect(option.rect, base_color)
        
        # Overlay hover highlight on top of zebra (preserving zebra underneath)
        if is_hovered:
            # Semi-transparent dark blue overlay
            painter.fillRect(option.rect, QtGui.QColor(30, 64, 175, 40))
            
        # Left border highlight for hover/current
        if is_hovered:
            # Dark blue border for hover
            painter.setPen(QtGui.QPen(QtGui.QColor("#1E40AF"), 3))
            painter.drawLine(option.rect.left(), option.rect.top() + 2,
                           option.rect.left(), option.rect.bottom() - 2)
        elif is_current:
            painter.setPen(QtGui.QPen(QtGui.QColor("#93C5FD"), 3))
            painter.drawLine(option.rect.left(), option.rect.top() + 2,
                           option.rect.left(), option.rect.bottom() - 2)
        
        # Font name (default Qt font - Arial)
        painter.setPen(QtGui.QColor("#374151"))
        painter.setFont(QtGui.QFont("Arial", 10))
        name_rect = option.rect.adjusted(12, 0, -200, 0)
        painter.drawText(name_rect, QtCore.Qt.AlignmentFlag.AlignLeft | 
                        QtCore.Qt.AlignmentFlag.AlignVCenter, text)
        
        # Sample text (in the actual font)
        sample_font = index.data(QtCore.Qt.ItemDataRole.FontRole)
        if sample_font:
            painter.setFont(sample_font)
        painter.setPen(QtGui.QColor("#6B7280"))
        sample_rect = option.rect.adjusted(200, 0, -12, 0)
        painter.drawText(sample_rect, QtCore.Qt.AlignmentFlag.AlignRight | 
                        QtCore.Qt.AlignmentFlag.AlignVCenter, SAMPLE_TEXT)
        
    def sizeHint(self, option, index) -> QtCore.QSize:
        row_type = index.data(QtCore.Qt.ItemDataRole.UserRole + 1)
        if row_type == FontListModel.TYPE_HEADER:
            return QtCore.QSize(400, 24)
        return QtCore.QSize(400, 26)


# Font Size Dropdown
FONT_SIZES = [6, 7, 8, 9, 10, 10.5, 11, 12, 14, 16, 18, 20, 22, 24, 26, 28, 32, 36, 48, 72]


class FontSizeDropdown(QtWidgets.QPushButton):
    """Font size dropdown with preset sizes."""
    
    size_selected = QtCore.Signal(float)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._current_size: float = 11.0
        self._popup: Optional[FontSizePopup] = None
        
        self.setFixedSize(60, 26)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        super().setText("")
        
        # Layout with label and triangle
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 4, 0)
        layout.setSpacing(2)
        
        self._size_label = QtWidgets.QLabel(str(self._current_size))
        self._size_label.setStyleSheet("color: #374151; background: transparent;")
        self._size_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._size_label, 1)
        
        self._triangle = QtWidgets.QLabel("▼")
        self._triangle.setStyleSheet("color: #6B7280; font-size: 8px; background: transparent;")
        self._triangle.setFixedWidth(10)
        layout.addWidget(self._triangle)
        
        self.setStyleSheet("""
            QPushButton {
                background: white;
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 0px;
            }
            QPushButton:hover {
                border-color: #9CA3AF;
                background: #F9FAFB;
            }
            QPushButton:pressed {
                background: #F3F4F6;
            }
        """)
        
        self.clicked.connect(self._show_popup)
        self._update_display()
        
    def _update_display(self):
        """Update label to show current size."""
        self._size_label.setText(str(int(self._current_size)) if self._current_size == int(self._current_size) else str(self._current_size))
        
    def _show_popup(self):
        """Show the size picker popup."""
        self._popup = FontSizePopup(FONT_SIZES, self._current_size, self)
        self._popup.size_selected.connect(self._on_size_selected)
        
        pos = self.mapToGlobal(QtCore.QPoint(0, self.height()))
        self._popup.move(pos)
        self._popup.show()
        
    def _on_size_selected(self, size: float):
        """Handle size selection."""
        if size != self._current_size:
            self._current_size = size
            self._update_display()
            print(f"[FontSizeDropdown] Selected size: {size}")
            self.size_selected.emit(size)
            
    def get_current_size(self) -> float:
        return self._current_size
        
    def set_current_size(self, size: float):
        if size in FONT_SIZES:
            self._current_size = size
            self._update_display()


class FontSizePopup(QtWidgets.QFrame):
    """Popup for selecting font sizes."""
    
    size_selected = QtCore.Signal(float)
    
    def __init__(self, sizes: list[float], current_size: float, parent=None):
        super().__init__(parent, QtCore.Qt.WindowType.Popup)
        
        self._sizes = sizes
        self._current_size = current_size
        
        self.setFixedSize(80, 300)
        self.setStyleSheet("""
            QFrame {
                background: white;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
            }
        """)
        
        self._setup_ui()
        
    def _setup_ui(self):
        """Set up the popup UI."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # ListView for sizes
        self._list_view = QtWidgets.QListView()
        self._list_view.setSpacing(0)
        
        # Model
        self._model = SizeListModel(self._sizes, self._current_size, self)
        self._list_view.setModel(self._model)
        
        # Delegate
        delegate = SizeItemDelegate(self._list_view)
        self._list_view.setItemDelegate(delegate)
        
        # Selection
        self._list_view.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self._list_view.setMouseTracking(True)
        self._list_view.entered.connect(self._on_item_hovered)
        self._list_view.clicked.connect(self._on_item_clicked)
        
        # Scroll to current
        try:
            idx = self._sizes.index(self._current_size)
            model_idx = self._model.index(idx, 0)
            self._list_view.scrollTo(model_idx, QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter)
            self._list_view.setCurrentIndex(model_idx)
        except ValueError:
            pass
        
        layout.addWidget(self._list_view)
        
        # Style
        self._list_view.setStyleSheet("""
            QListView {
                border: none;
                background: white;
                outline: none;
            }
            QListView::item {
                min-height: 26px;
                padding: 0px;
                border: none;
            }
            QListView::item:selected {
                background: transparent;
                border: none;
            }
        """)
        
    def _on_item_hovered(self, index: QtCore.QModelIndex):
        """Highlight size on hover."""
        if index.isValid():
            self._list_view.setCurrentIndex(index)
        
    def _on_item_clicked(self, index: QtCore.QModelIndex):
        """Select size and close."""
        if not index.isValid():
            return
            
        size = self._model.size_at(index.row())
        if size:
            self.size_selected.emit(size)
            self.close()


class SizeListModel(QtCore.QAbstractListModel):
    """Model for font sizes."""
    
    def __init__(self, sizes: list[float], current_size: float, parent=None):
        super().__init__(parent)
        self._sizes = sizes
        self._current_size = current_size
        
    def rowCount(self, parent=QtCore.QModelIndex()) -> int:
        return len(self._sizes)
        
    def data(self, index: QtCore.QModelIndex, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
            
        row = index.row()
        if row < 0 or row >= len(self._sizes):
            return None
            
        size = self._sizes[row]
        
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return str(int(size)) if size == int(size) else str(size)
        elif role == QtCore.Qt.ItemDataRole.UserRole:
            return size == self._current_size
        elif role == QtCore.Qt.ItemDataRole.FontRole:
            font = QtGui.QFont("Arial", int(max(8, min(size, 16))))
            return font
            
        return None
        
    def size_at(self, row: int) -> Optional[float]:
        if 0 <= row < len(self._sizes):
            return self._sizes[row]
        return None


class SizeItemDelegate(QtWidgets.QStyledItemDelegate):
    """Delegate for rendering size items with hover."""
    
    def paint(self, painter: QtGui.QPainter, option, index):
        """Paint size item with zebra and hover."""
        text = index.data(QtCore.Qt.ItemDataRole.DisplayRole)
        is_current = index.data(QtCore.Qt.ItemDataRole.UserRole) or False
        is_hovered = option.state & QtWidgets.QStyle.StateFlag.State_MouseOver
        
        # Zebra background
        is_alt = index.row() % 2 == 1
        if is_alt:
            painter.fillRect(option.rect, QtGui.QColor("#F9FAFB"))
        else:
            painter.fillRect(option.rect, QtGui.QColor("white"))
        
        # Hover overlay
        if is_hovered:
            painter.fillRect(option.rect, QtGui.QColor(30, 64, 175, 40))
            
        # Left border
        if is_hovered:
            painter.setPen(QtGui.QPen(QtGui.QColor("#1E40AF"), 3))
            painter.drawLine(option.rect.left(), option.rect.top() + 2,
                           option.rect.left(), option.rect.bottom() - 2)
        elif is_current:
            painter.setPen(QtGui.QPen(QtGui.QColor("#3B82F6"), 3))
            painter.drawLine(option.rect.left(), option.rect.top() + 2,
                           option.rect.left(), option.rect.bottom() - 2)
        
        # Draw size number in actual font size
        sample_font = index.data(QtCore.Qt.ItemDataRole.FontRole)
        if sample_font:
            painter.setFont(sample_font)
        painter.setPen(QtGui.QColor("#374151"))
        painter.drawText(option.rect.adjusted(12, 0, -12, 0),
                        QtCore.Qt.AlignmentFlag.AlignCenter | QtCore.Qt.AlignmentFlag.AlignVCenter,
                        text)
        
    def sizeHint(self, option, index) -> QtCore.QSize:
        return QtCore.QSize(80, 26)
