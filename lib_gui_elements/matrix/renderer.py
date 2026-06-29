"""Rendering helpers for the matrix grid."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6 import QtCore, QtGui, QtWidgets


class GridRenderer:
    """Rendering helper methods (main paintEvent stays in MatrixGrid)."""

    def __init__(self, grid: "MatrixGrid") -> None:
        self._grid = grid

    def row_leaf_header_rect(self, row_idx: int) -> "QtCore.QRect":
        """Calculate rect for row leaf header at given index."""
        from PySide6 import QtCore

        off = self._grid._scroll_offset()
        header_h = self._grid._m.col_header_h * max(1, getattr(self._grid, '_col_header_levels', 1))
        y = header_h + row_idx * self._grid._m.row_h - off.y()
        row_header_w = self._grid._row_header_width()
        # Get the actual leaf level width (last level in row headers)
        row_header_levels = getattr(self._grid, '_row_header_levels', 1)
        leaf_level = max(0, row_header_levels - 1)
        leaf_w = self._grid._geometry.row_header_level_width(leaf_level)
        # Position at the right edge of row header area
        x_offset = max(0, row_header_w - leaf_w)
        return QtCore.QRect(int(x_offset), int(y), int(leaf_w), self._grid._m.row_h)

    def col_leaf_header_rect(self, col_idx: int) -> "QtCore.QRect":
        """Calculate rect for column leaf header at given index."""
        from PySide6 import QtCore

        off = self._grid._scroll_offset()
        row_header_w = self._grid._row_header_width()
        x = row_header_w
        for i in range(col_idx):
            x += self._grid._col_width(i)
        x -= off.x()
        col_header_levels = getattr(self._grid, '_col_header_levels', 1)
        # Leaf level is at (levels - 1) since levels are 0-indexed
        leaf_level = max(0, col_header_levels - 1)
        y_leaf = leaf_level * self._grid._m.col_header_h
        return QtCore.QRect(int(x), int(y_leaf), self._grid._col_width(col_idx), self._grid._m.col_header_h)

    def draw_diagonal_shading(
        self, p: "QtGui.QPainter", rect: "QtCore.QRect", color: str = "#e8e8e8"
    ) -> None:
        """Draw diagonal line shading pattern in a cell."""
        from PySide6 import QtCore, QtGui

        pen = QtGui.QPen(QtGui.QColor(color))
        pen.setWidth(1)
        p.setPen(pen)

        # Draw diagonal lines
        x1, y1 = rect.left(), rect.top()
        x2, y2 = rect.right(), rect.bottom()

        # Top-left to bottom-right diagonals
        step = 8
        for offset in range(-rect.height(), rect.width(), step):
            start_x = max(x1, x1 + offset)
            start_y = max(y1, y1 - offset)
            end_x = min(x2, x2 + offset)
            end_y = min(y2, y2 - offset)

            if start_x < end_x and start_y < end_y:
                p.drawLine(QtCore.QPoint(start_x, start_y), QtCore.QPoint(end_x, end_y))

    def draw_cell_borders(
        self,
        p: "QtGui.QPainter",
        rect: "QtCore.QRect",
        fmt: "CellFormat",
    ) -> None:
        """Draw cell borders based on format settings."""
        from PySide6 import QtCore, QtGui
        from lib_contracts.types import CellFormat

        if not isinstance(fmt, CellFormat):
            return

        def create_border_pen(thickness: str) -> QtGui.QPen:
            width = 2 if thickness == "thick" else 1
            pen = QtGui.QPen(QtGui.QColor(fmt.border_color), width)
            pen.setCapStyle(QtCore.Qt.PenCapStyle.FlatCap)

            # Set pen style based on border_style
            if fmt.border_style == "dashed":
                pen.setStyle(QtCore.Qt.PenStyle.DashLine)
            elif fmt.border_style == "dotted":
                pen.setStyle(QtCore.Qt.PenStyle.DotLine)
            else:  # solid
                pen.setStyle(QtCore.Qt.PenStyle.SolidLine)

            return pen

        def border_width(thickness: str) -> int:
            return 2 if thickness == "thick" else 1

        def draw_corner(x: float, y: float, thickness_a: str, thickness_b: str) -> None:
            width = max(border_width(thickness_a), border_width(thickness_b))
            size = float(width)
            half = size / 2.0
            p.save()
            p.setPen(QtCore.Qt.PenStyle.NoPen)
            p.setBrush(QtGui.QBrush(QtGui.QColor(fmt.border_color)))
            p.drawRect(QtCore.QRectF(x - half, y - half, size, size))
            p.restore()

        left = float(rect.left())
        right = float(rect.right())
        top = float(rect.top())
        bottom = float(rect.bottom())
        inner_left = left + 1.0
        inner_right = right - 1.0
        inner_top = top + 1.0
        inner_bottom = bottom - 1.0

        # Draw borders based on format settings
        # (Implementation continues in the main file)
    def draw_cell_borders(self, p: QtGui.QPainter, rect: QtCore.QRect, fmt: CellFormat) -> None:
        """Draw custom borders on a cell based on its format."""
        # Helper to create pen with style
        def create_border_pen(thickness: str) -> QtGui.QPen:
            width = 2 if thickness == "thick" else 1
            pen = QtGui.QPen(QtGui.QColor(fmt.border_color), width)
            pen.setCapStyle(QtCore.Qt.PenCapStyle.FlatCap)
            
            # Set pen style based on border_style
            if fmt.border_style == "dashed":
                pen.setStyle(QtCore.Qt.PenStyle.DashLine)
            elif fmt.border_style == "dotted":
                pen.setStyle(QtCore.Qt.PenStyle.DotLine)
            else:  # solid
                pen.setStyle(QtCore.Qt.PenStyle.SolidLine)
            
            return pen

        def border_width(thickness: str) -> int:
            return 2 if thickness == "thick" else 1

        def draw_corner(x: float, y: float, thickness_a: str, thickness_b: str) -> None:
            width = max(border_width(thickness_a), border_width(thickness_b))
            size = float(width)
            half = size / 2.0
            p.save()
            p.setPen(QtCore.Qt.PenStyle.NoPen)
            p.setBrush(QtGui.QBrush(QtGui.QColor(fmt.border_color)))
            p.drawRect(QtCore.QRectF(x - half, y - half, size, size))
            p.restore()

        left = float(rect.left())
        right = float(rect.right())
        top = float(rect.top())
        bottom = float(rect.bottom())
        inner_left = left + 1.0
        inner_right = right - 1.0
        inner_top = top + 1.0
        inner_bottom = bottom - 1.0
        corner_right = right - 0.5
        corner_bottom = bottom - 0.5
        corner_left = left + 0.5
        corner_top = top + 0.5
        edge_right = right
        edge_bottom = bottom
        
        # Draw top border
        if fmt.border_top != "none":
            pen = create_border_pen(fmt.border_top)
            p.setPen(pen)
            p.drawLine(
                QtCore.QPointF(corner_left, inner_top),
                QtCore.QPointF(corner_right, inner_top),
            )
        
        # Draw bottom border
        if fmt.border_bottom != "none":
            pen = create_border_pen(fmt.border_bottom)
            p.setPen(pen)
            p.drawLine(
                QtCore.QPointF(corner_left, edge_bottom),
                QtCore.QPointF(right, edge_bottom),
            )
        
        # Draw left border
        if fmt.border_left != "none":
            pen = create_border_pen(fmt.border_left)
            p.setPen(pen)
            p.drawLine(
                QtCore.QPointF(inner_left, corner_top),
                QtCore.QPointF(inner_left, corner_bottom),
            )
        
        # Draw right border
        if fmt.border_right != "none":
            pen = create_border_pen(fmt.border_right)
            p.setPen(pen)
            p.drawLine(
                QtCore.QPointF(edge_right, corner_top),
                QtCore.QPointF(edge_right, bottom),
            )

        if fmt.border_top != "none" and fmt.border_left != "none":
            draw_corner(inner_left, inner_top, fmt.border_top, fmt.border_left)
        if fmt.border_top != "none" and fmt.border_right != "none":
            draw_corner(edge_right, inner_top, fmt.border_top, fmt.border_right)
        if fmt.border_bottom != "none" and fmt.border_left != "none":
            draw_corner(inner_left, edge_bottom, fmt.border_bottom, fmt.border_left)
        if fmt.border_bottom != "none" and fmt.border_right != "none":
            draw_corner(edge_right, edge_bottom, fmt.border_bottom, fmt.border_right)


