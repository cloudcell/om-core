"""Format section navigation pill bar."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QIcon, QPixmap, QColor, QPainter, QFont
from PySide6.QtSvg import QSvgRenderer

if TYPE_CHECKING:
    from typing import List, Optional


class FormatSection(Enum):
    """Format section types."""
    BACKGROUND = "background"
    FONT = "font"
    ALIGNMENT = "alignment"
    BORDERS = "borders"
    NUMBER = "number"


@dataclass
class FormatPillData:
    """Data for a format section pill."""
    section: FormatSection
    label: str
    icon_name: str
    shortcut: str


# Section configurations
SECTION_CONFIGS: List[FormatPillData] = [
    FormatPillData(FormatSection.BACKGROUND, "Fill", "palette", "Ctrl+1"),
    FormatPillData(FormatSection.FONT, "Font", "type", "Ctrl+2"),
    FormatPillData(FormatSection.ALIGNMENT, "Align", "align-start-horizontal", "Ctrl+3"),
    FormatPillData(FormatSection.BORDERS, "Border", "square", "Ctrl+4"),
    FormatPillData(FormatSection.NUMBER, "Number", "hash", "Ctrl+5"),
]


class FormatPill(QPushButton):
    """Single format section pill."""
    
    PILL_HEIGHT = 28
    ICON_SIZE = 14
    
    def __init__(self, data: FormatPillData, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.data = data
        self.is_active = False
        self._icon_pixmap: Optional[QPixmap] = None
        
        self._setup_ui()
        self._load_icon()
        
    def _setup_ui(self) -> None:
        """Configure pill appearance."""
        self.setFixedHeight(self.PILL_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        self.setText(f"  {self.data.label}")
        
        font = QFont("Inter", 10)
        font.setWeight(QFont.Weight.Medium)
        self.setFont(font)
        
        self._update_style()
        self._update_size()
        
    def _load_icon(self) -> None:
        """Load and render the lucide SVG icon from the zipped icon bundle."""
        try:
            from lib_gui.icons import load_svg_renderer
            renderer = load_svg_renderer(f"lucide/icons/{self.data.icon_name}")
            self._icon_pixmap = QPixmap(self.ICON_SIZE, self.ICON_SIZE)
            self._icon_pixmap.fill(Qt.GlobalColor.transparent)

            painter = QPainter(self._icon_pixmap)
            renderer.render(painter)
            painter.end()
        except Exception as e:
            print(f"Failed to load icon {self.data.icon_name}: {e}")
            
    def _update_size(self) -> None:
        """Calculate pill width based on content."""
        from PySide6.QtGui import QFontMetrics
        
        fm = QFontMetrics(self.font())
        text_width = fm.horizontalAdvance(self.text())
        width = 12 + self.ICON_SIZE + 4 + text_width + 12
        self.setFixedWidth(max(width, 70))
        
    def _update_style(self) -> None:
        """Update stylesheet based on state."""
        if self.is_active:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #DBEAFE;
                    border: 1px solid #3B82F6;
                    border-radius: 14px;
                    padding: 4px 10px;
                    color: #1E40AF;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background-color: #BFDBFE;
                    border-color: #2563EB;
                }
                QPushButton:pressed {
                    background-color: #93C5FD;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #F3F4F6;
                    border: 1px solid #E5E7EB;
                    border-radius: 14px;
                    padding: 4px 10px;
                    color: #374151;
                }
                QPushButton:hover {
                    background-color: #FFFFFF;
                    border-color: #D1D5DB;
                }
                QPushButton:pressed {
                    background-color: #E5E7EB;
                }
            """)
            
    def paintEvent(self, event) -> None:
        """Custom paint with icon."""
        super().paintEvent(event)
        
        if self._icon_pixmap:
            painter = QPainter(self)
            y = (self.height() - self.ICON_SIZE) // 2
            painter.drawPixmap(10, y, self._icon_pixmap)
            painter.end()
            
    def set_active(self, active: bool) -> None:
        """Set active state."""
        self.is_active = active
        self.setChecked(active)
        self._update_style()
        
        if active:
            # Bouncy animation
            anim = QPropertyAnimation(self, b"geometry", self)
            anim.setDuration(150)
            anim.setEasingCurve(QEasingCurve.Type.OutBack)
            geo = self.geometry()
            anim.setStartValue(geo.adjusted(0, 2, 0, -2))
            anim.setEndValue(geo)
            anim.start()


class FormatPillBar(QWidget):
    """
    Horizontal pill bar for format section navigation.
    Inspired by channel_filter_bar.py but optimized for format sections.
    """
    
    section_changed = Signal(FormatSection)  # Emitted when section changes
    
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.pills: List[FormatPill] = []
        self.active_section: Optional[FormatSection] = None
        
        self._setup_ui()
        self._create_pills()
        
    def _setup_ui(self) -> None:
        """Set up the pill bar layout."""
        layout = QHBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.setLayout(layout)
        self.setStyleSheet("background-color: #FAFAFA; border-bottom: 1px solid #E5E7EB;")
        
    def _create_pills(self) -> None:
        """Create pill widgets for each section."""
        layout = self.layout()
        
        for config in SECTION_CONFIGS:
            pill = FormatPill(config)
            pill.clicked.connect(lambda checked, s=config.section: self._on_pill_clicked(s))
            layout.addWidget(pill)
            self.pills.append(pill)
            
        layout.addStretch()
        
    def _on_pill_clicked(self, section: FormatSection) -> None:
        """Handle pill click - toggle section."""
        if self.active_section == section:
            # Clicking active pill deselects it
            self.active_section = None
            self._update_pill_states()
            self.section_changed.emit(None)  # type: ignore
        else:
            self.active_section = section
            self._update_pill_states()
            self.section_changed.emit(section)
            
    def _update_pill_states(self) -> None:
        """Update all pills to match current selection."""
        for pill in self.pills:
            pill.set_active(pill.data.section == self.active_section)
            
    def set_section(self, section: Optional[FormatSection]) -> None:
        """Programmatically set active section."""
        self.active_section = section
        self._update_pill_states()
        if section:
            self.section_changed.emit(section)
        else:
            self.section_changed.emit(None)  # type: ignore
            
    def clear_selection(self) -> None:
        """Clear all selections."""
        self.set_section(None)
