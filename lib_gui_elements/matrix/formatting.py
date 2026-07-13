"""Cell formatting helpers for the matrix grid."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PySide6 import QtCore, QtGui, QtWidgets
    from lib_contracts.types import CellFormat


class FormattingHelper:
    """Helper methods for cell formatting operations."""

    def __init__(self, grid: "MatrixGrid") -> None:
        self._grid = grid
        self._number_formatter_cache: dict[str, Any] = {}

    def apply_format_to_selection(
        self, format_type: str, value: object
    ) -> None:
        """Apply a format change to the current selection - only to cells, not headers."""
        from lib_contracts.types import CellFormat

        view_meta = self._grid.current_view_meta()
        cell_formats = view_meta.get("cell_formats", {}) if view_meta else {}

        if self._grid._sel_mode == "cell":
            # Apply to selected cells (single or multi-selection)
            cells_to_format = set()

            # Check for multi-cell selection in _sel_indices
            if self._grid._sel_indices:
                for item in self._grid._sel_indices:
                    if isinstance(item, tuple) and len(item) == 2:
                        cells_to_format.add(item)

            # Add current selection if not already included
            if (self._grid._sel_row, self._grid._sel_col) not in cells_to_format:
                cells_to_format.add((self._grid._sel_row, self._grid._sel_col))

            # Apply format to all selected cells
            for r, c in cells_to_format:
                try:
                    if not (
                        0 <= r < len(self._grid._rows)
                        and 0 <= c < len(self._grid._cols)
                    ):
                        continue
                    if not self._grid._rows[r].get("is_leaf", False):
                        continue

                    row_key = self._grid._row_keys[
                        self._grid._geometry.leaf_row_index(r)
                    ]
                    col_key = self._grid._col_keys[c]
                    cell_key = f"{row_key}|{col_key}"

                    fmt = cell_formats.get(cell_key, CellFormat())
                    fmt = self.update_format(fmt, format_type, value)
                    cell_formats[cell_key] = fmt
                except Exception:
                    pass

        elif self._grid._sel_mode == "row":
            # Apply to all cells in selected rows
            for r in self._grid._sel_indices:
                if not (0 <= r < len(self._grid._rows)):
                    continue
                if not self._grid._rows[r].get("is_leaf", False):
                    continue
                for c in range(len(self._grid._cols)):
                    try:
                        row_key = self._grid._row_keys[
                            self._grid._geometry.leaf_row_index(r)
                        ]
                        col_key = self._grid._col_keys[c]
                        cell_key = f"{row_key}|{col_key}"

                        fmt = cell_formats.get(cell_key, CellFormat())
                        fmt = self.update_format(fmt, format_type, value)
                        cell_formats[cell_key] = fmt
                    except Exception:
                        pass

        elif self._grid._sel_mode == "col":
            # Apply to all cells in selected columns
            for c in self._grid._sel_indices:
                if not (0 <= c < len(self._grid._cols)):
                    continue
                for r in range(len(self._grid._rows)):
                    if not self._grid._rows[r].get("is_leaf", False):
                        continue
                    try:
                        row_key = self._grid._row_keys[
                            self._grid._geometry.leaf_row_index(r)
                        ]
                        col_key = self._grid._col_keys[c]
                        cell_key = f"{row_key}|{col_key}"

                        fmt = cell_formats.get(cell_key, CellFormat())
                        fmt = self.update_format(fmt, format_type, value)
                        cell_formats[cell_key] = fmt
                    except Exception:
                        pass

        self._grid.viewport().update()

    def update_format(
        self, fmt: "CellFormat", format_type: str, value: object
    ) -> "CellFormat":
        """Update a CellFormat with a new format value."""
        from lib_contracts.types import CellFormat

        kwargs: dict[str, Any] = {}

        if format_type == "bg_color":
            kwargs["bg_color"] = value
        elif format_type == "font_color":
            kwargs["font_color"] = value
        elif format_type == "font_family":
            kwargs["font_family"] = value
        elif format_type == "font_size":
            kwargs["font_size"] = value
        elif format_type == "font_weight":
            kwargs["font_weight"] = int(value) if isinstance(value, (int, float, str)) else 400
        elif format_type == "font_bold":
            kwargs["font_weight"] = 700 if value else 400  # Deprecated: use font_weight
        elif format_type == "font_italic":
            kwargs["font_italic"] = value
        elif format_type == "format_number":
            kwargs["format_number"] = value
        elif format_type == "format_text":
            kwargs["format_text"] = value
        elif format_type == "format_null":
            kwargs["format_null"] = value
        elif format_type == "format_error":
            kwargs["format_error"] = value
        elif format_type == "number_format":
            kwargs["format_number"] = value  # Deprecated: use format_number
        elif format_type == "decimal_places":
            kwargs["decimal_places"] = value  # Deprecated: embed in format_number
        elif format_type == "border":
            # Individual border side with thickness
            if isinstance(value, dict):
                side = value.get("side")
                thickness = value.get("thickness")
                style = value.get("style")
                color = value.get("color")
                if side == "top":
                    kwargs["border_top"] = thickness
                elif side == "bottom":
                    kwargs["border_bottom"] = thickness
                elif side == "left":
                    kwargs["border_left"] = thickness
                elif side == "right":
                    kwargs["border_right"] = thickness
                if style is not None:
                    kwargs["border_style"] = style
                if color is not None:
                    kwargs["border_color"] = color
        elif format_type == "border_preset":
            # Quick presets
            preset = value
            style = None
            color = None
            if isinstance(value, dict):
                preset = value.get("preset")
                style = value.get("style")
                color = value.get("color")
            if preset == "all":
                kwargs["border_top"] = "thin"
                kwargs["border_bottom"] = "thin"
                kwargs["border_left"] = "thin"
                kwargs["border_right"] = "thin"
            elif preset == "outer":
                kwargs["border_top"] = "thin"
                kwargs["border_bottom"] = "thin"
                kwargs["border_left"] = "thin"
                kwargs["border_right"] = "thin"
            elif preset == "none":
                kwargs["border_top"] = "none"
                kwargs["border_bottom"] = "none"
                kwargs["border_left"] = "none"
                kwargs["border_right"] = "none"
            if style is not None:
                kwargs["border_style"] = style
            if color is not None:
                kwargs["border_color"] = color
        elif format_type == "border_style":
            kwargs["border_style"] = value
        elif format_type == "border_color":
            kwargs["border_color"] = value
        elif format_type == "text_h_align":
            kwargs["text_h_align"] = value
        elif format_type == "h_align":  # Deprecated
            kwargs["text_h_align"] = value
        elif format_type == "text_v_align":
            kwargs["text_v_align"] = value
        elif format_type == "v_align":  # Deprecated
            kwargs["text_v_align"] = value

        return CellFormat(
            bg_color=kwargs.get("bg_color", fmt.bg_color),
            font_color=kwargs.get("font_color", fmt.font_color),
            font_family=kwargs.get("font_family", fmt.font_family),
            font_size=kwargs.get("font_size", fmt.font_size),
            font_weight=kwargs.get("font_weight", fmt.font_weight),
            font_italic=kwargs.get("font_italic", fmt.font_italic),
            format_number=kwargs.get("format_number", fmt.format_number),
            format_text=kwargs.get("format_text", fmt.format_text),
            format_null=kwargs.get("format_null", fmt.format_null),
            format_error=kwargs.get("format_error", fmt.format_error),
            number_format=kwargs.get("number_format", fmt.number_format),
            decimal_places=kwargs.get("decimal_places", fmt.decimal_places),
            border_top=kwargs.get("border_top", fmt.border_top),
            border_bottom=kwargs.get("border_bottom", fmt.border_bottom),
            border_left=kwargs.get("border_left", fmt.border_left),
            border_right=kwargs.get("border_right", fmt.border_right),
            border_style=kwargs.get("border_style", fmt.border_style),
            border_color=kwargs.get("border_color", fmt.border_color),
            text_h_align=kwargs.get("text_h_align", fmt.text_h_align),
            text_v_align=kwargs.get("text_v_align", fmt.text_v_align),
            text_indent=kwargs.get("text_indent", fmt.text_indent),
            text_wrap=kwargs.get("text_wrap", fmt.text_wrap),
        )

    def get_cell_format(self, r: int, c: int) -> "CellFormat":
        """Get the CellFormat for a cell at (r, c).

        F5c: uses cached view metadata and snapshot channels instead of
        direct engine reads for @ dimension format values.
        """
        from lib_contracts.types import CellFormat

        view_meta = self._grid._cached_view_meta or {}

        # Try cell-specific format first (from view.cell_formats - static formats)
        if 0 <= r < len(self._grid._rows) and 0 <= c < len(self._grid._cols):
            try:
                row_key = self._grid._row_keys[
                    self._grid._geometry.leaf_row_index(r)
                ]
                col_key = self._grid._col_keys[c]
                key = f"{row_key}|{col_key}"
                cell_formats = view_meta.get("cell_formats", {})
                if key in cell_formats:
                    static_fmt = cell_formats[key]
                    # Merge with @ dimension format values from snapshot
                    at_fmt = self._get_at_dimension_format(r, c)
                    return self._merge_formats(at_fmt, static_fmt)
            except Exception:
                pass

            # Try row item format
            row = self._grid._rows[r]
            item_id = row.get("item_id")
            row_dim_ids = view_meta.get("row_dim_ids", [])
            if item_id and row_dim_ids:
                dim_id = row_dim_ids[0]
                key = f"{dim_id}:{item_id}"
                item_formats = view_meta.get("item_formats", {})
                if key in item_formats:
                    static_fmt = item_formats[key]
                    at_fmt = self._get_at_dimension_format(r, c)
                    return self._merge_formats(at_fmt, static_fmt)

            # Try column item format
            col = self._grid._cols[c]
            item_id = col.get("item_id")
            col_dim_ids = view_meta.get("col_dim_ids", [])
            if item_id and col_dim_ids:
                dim_id = col_dim_ids[0]
                key = f"{dim_id}:{item_id}"
                item_formats = view_meta.get("item_formats", {})
                if key in item_formats:
                    static_fmt = item_formats[key]
                    at_fmt = self._get_at_dimension_format(r, c)
                    return self._merge_formats(at_fmt, static_fmt)

        # Default: just return @ dimension format values from snapshot
        return self._get_at_dimension_format(r, c)

    def _get_at_dimension_format(self, r: int, c: int) -> "CellFormat":
        """Get format values from @ dimension via snapshot channels (no engine reads)."""
        from lib_contracts.types import CellFormat

        fmt = CellFormat()

        if not (0 <= r < len(self._grid._rows) and 0 <= c < len(self._grid._cols)):
            return fmt

        try:
            row_key = self._grid._row_keys[self._grid._geometry.leaf_row_index(r)]
            col_key = self._grid._col_keys[c]
        except Exception:
            return fmt

        # F5c: read channel values from cached tiles via flat lookup
        from lib_utils.viewport_keys import make_viewport_cell_key
        cell_key = make_viewport_cell_key(row_key, col_key)

        # Build flat cell_key -> channels cache when tile_cache changes.
        # Index every channel dictionary, not just font_color/fill, so that
        # format_number and other format channels are found for cells that have
        # no visual-style channels. The cache key uses the grid's tile-cache
        # generation counter so in-place snapshot updates (which keep the same
        # dict id and length) still invalidate the cache.
        cache = getattr(self, "_channels_flat_cache", None)
        tile_cache_gen = getattr(self._grid, "_tile_cache_gen", 0)
        cache_key = (tile_cache_gen, id(self._grid._tile_cache))
        if cache is None or cache[0] != cache_key:
            flat: dict[str, dict[str, Any]] = {}
            for snapshot in self._grid._tile_cache.values():
                ch = snapshot.get("channels", {})
                for channel_data in ch.values():
                    if not isinstance(channel_data, dict):
                        continue
                    for key in channel_data:
                        flat.setdefault(key, ch)
            cache = (cache_key, flat)
            self._channels_flat_cache = cache
        channels = cache[1].get(cell_key, {})

        format_values: dict[str, Any] = {}
        channel_to_attr = {
            "fill": "bg_color",
            "font_color": "font_color",
            "format_number": "format_number",
            "format_text": "format_text",
            "format_null": "format_null",
            "format_error": "format_error",
            "font_family": "font_family",
            "font_size": "font_size",
            "font_weight": "font_weight",
            "font_italic": "font_italic",
            "text_h_align": "text_h_align",
            "text_v_align": "text_v_align",
            "text_indent": "text_indent",
            "text_wrap": "text_wrap",
        }
        for channel, attr in channel_to_attr.items():
            value = channels.get(channel, {}).get(cell_key)
            if value is not None:
                format_values[attr] = value

        if not format_values:
            return fmt

        # Convert font_weight to int if it's a string from @ dimension
        font_weight = format_values.get("font_weight", fmt.font_weight)
        if isinstance(font_weight, str):
            font_weight = int(font_weight)

        return CellFormat(
            bg_color=format_values.get("bg_color", fmt.bg_color),
            font_color=format_values.get("font_color", fmt.font_color),
            format_number=format_values.get("format_number", fmt.format_number),
            format_text=format_values.get("format_text", fmt.format_text),
            format_null=format_values.get("format_null", fmt.format_null),
            format_error=format_values.get("format_error", fmt.format_error),
            font_family=format_values.get("font_family", fmt.font_family),
            font_size=format_values.get("font_size", fmt.font_size),
            font_weight=font_weight,
            font_italic=format_values.get("font_italic", fmt.font_italic),
            text_h_align=format_values.get("text_h_align", fmt.text_h_align),
            text_v_align=format_values.get("text_v_align", fmt.text_v_align),
            text_indent=format_values.get("text_indent", fmt.text_indent),
            text_wrap=format_values.get("text_wrap", fmt.text_wrap),
        )

    def _merge_formats(self, base: "CellFormat", override: "CellFormat") -> "CellFormat":
        """Merge two CellFormat objects, with override taking precedence for non-None values."""
        from lib_contracts.types import CellFormat

        return CellFormat(
            bg_color=override.bg_color if override.bg_color is not None else base.bg_color,
            font_color=override.font_color if override.font_color is not None else base.font_color,
            font_family=override.font_family if override.font_family is not None else base.font_family,
            font_size=override.font_size if override.font_size is not None else base.font_size,
            font_weight=override.font_weight if override.font_weight != 400 else base.font_weight,
            font_italic=override.font_italic if override.font_italic is not None else base.font_italic,
            format_number=override.format_number if override.format_number != "general" else base.format_number,
            format_text=override.format_text if override.format_text else base.format_text,
            format_null=override.format_null if override.format_null else base.format_null,
            format_error=override.format_error if override.format_error else base.format_error,
            number_format=override.number_format if override.number_format != "general" else base.number_format,
            decimal_places=override.decimal_places if override.decimal_places != 2 else base.decimal_places,
            border_top=override.border_top if override.border_top != "none" else base.border_top,
            border_bottom=override.border_bottom if override.border_bottom != "none" else base.border_bottom,
            border_left=override.border_left if override.border_left != "none" else base.border_left,
            border_right=override.border_right if override.border_right != "none" else base.border_right,
            border_style=override.border_style if override.border_style != "solid" else base.border_style,
            border_color=override.border_color if override.border_color != "#000000" else base.border_color,
            text_h_align=override.text_h_align if override.text_h_align != "left" else base.text_h_align,
            text_v_align=override.text_v_align if override.text_v_align != "middle" else base.text_v_align,
            text_indent=override.text_indent if override.text_indent != 0 else base.text_indent,
            text_wrap=override.text_wrap if override.text_wrap else base.text_wrap,
        )

    def format_value(self, value: str, format_number: str) -> str:
        """Format a value according to the numeric format pattern.

        Args:
            value: String representation of the value
            format_number: Format pattern like "number", "currency", "general"
        """
        from .value_format import _compile_number_formatter

        try:
            num = float(value)
        except (ValueError, TypeError):
            return value

        formatter = self._number_formatter_cache.get(format_number)
        if formatter is None:
            formatter = _compile_number_formatter(format_number)
            self._number_formatter_cache[format_number] = formatter

        return formatter(num)

    def _clear_number_formatter_cache(self) -> None:
        """Clear cached number formatters (for future invalidation hooks)."""
        self._number_formatter_cache.clear()


def get_contrast_font_color(bg_color: str | None,
                            threshold: int = 180,
                            dark_text: str = "#202020",
                            light_text: str = "#ffffff") -> str:
    """Return appropriate font color based on background intensity for readability.

    - Dark backgrounds (max RGB <= threshold) → Light text
    - Bright backgrounds (max RGB > threshold) → Dark text

    Args:
        bg_color: Hex color string (e.g., "#ff0000") or None
        threshold: RGB intensity threshold (0-255). If max(R,G,B) > threshold, bg is "bright".
        dark_text: Dark text color for bright/light backgrounds
        light_text: Light text color for dark backgrounds

    Returns:
        Hex color string for font color
    """
    if not bg_color:
        return dark_text

    try:
        bg = bg_color.lstrip('#')
        if len(bg) == 6:
            r, g, b = int(bg[0:2], 16), int(bg[2:4], 16), int(bg[4:6], 16)
        elif len(bg) == 3:
            r, g, b = int(bg[0]*2, 16), int(bg[1]*2, 16), int(bg[2]*2, 16)
        else:
            return dark_text

        # Bright background (any channel > threshold) → use dark text
        if max(r, g, b) > threshold:
            return dark_text
        # Dark background → use light text
        return light_text
    except Exception:
        return dark_text
