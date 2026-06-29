"""Visual metrics and colors for the matrix grid."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6 import QtGui


@dataclass
class GridMetrics:
    """Visual metrics and colors for the grid."""

    row_header_w: int = 90
    col_header_h: int = 24
    row_h: int = 22
    col_w: int = 90
    gridline: "QtGui.QColor" = field(default_factory=lambda: None)  # Initialized below
    header_bg: "QtGui.QColor" = field(default_factory=lambda: None)
    header_fg: "QtGui.QColor" = field(default_factory=lambda: None)
    sel_bg: "QtGui.QColor" = field(default_factory=lambda: None)
    sel_fg: "QtGui.QColor" = field(default_factory=lambda: None)
    related_bg: "QtGui.QColor" = field(default_factory=lambda: None)

    def __post_init__(self):
        # Import here to avoid issues during module load
        from PySide6 import QtGui

        if self.gridline is None:
            self.gridline = QtGui.QColor("#d0d0d0")
        if self.header_bg is None:
            self.header_bg = QtGui.QColor("#f2f4f8")
        if self.header_fg is None:
            self.header_fg = QtGui.QColor("#202020")
        if self.sel_bg is None:
            # Import here to avoid circular imports
            from lib_utils.config import gui as gui_config
            alpha = gui_config("appearance", "selection_alpha", 120)
            try:
                alpha = int(alpha)
            except (ValueError, TypeError):
                alpha = 120
            self.sel_bg = QtGui.QColor(42, 118, 210, max(0, min(255, alpha)))
        if self.sel_fg is None:
            self.sel_fg = QtGui.QColor("#ffffff")
        if self.related_bg is None:
            self.related_bg = QtGui.QColor("#d8deeb")
