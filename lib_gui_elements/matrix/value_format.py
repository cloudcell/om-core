"""Value formatting utilities for matrix grid cells.

Handles formatting of cell values based on value_type and format patterns.
"""

from __future__ import annotations

import functools
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from lib_contracts.types import CellFormat

from lib_contracts.gui_read_models import FormatRenderer
from lib_openm.formatting import (
    DeferredFormatRendering,
    FormatError,
    InvalidFormatArgument,
    PresetParser,
    normalize_format_string,
)

NumberFormatter = Callable[[Any], str]


def format_cell_value(value: Any, fmt: CellFormat, value_type: str = "numeric") -> str:
    """Format a cell value according to its type and format settings.

    Args:
        value: The raw cell value
        fmt: CellFormat with format_* fields
        value_type: One of: numeric, text, null, error

    Returns:
        Formatted string for display
    """
    if value is None:
        # Use null format or default
        null_fmt = fmt.format_null if fmt.format_null else ""
        if null_fmt == "na":
            return "N/A"
        elif null_fmt == "dash":
            return "—"
        return ""

    # Convert to string for display
    v = str(value)

    # Apply type-specific formatting
    if value_type == "numeric":
        v = _format_number(value, fmt.format_number)
    elif value_type == "text":
        v = _format_text(v, fmt.format_text)
    elif value_type == "error":
        # Errors displayed as-is or with custom format
        v = v if not fmt.format_error else f"[{v}]"

    return v


def _format_number(value: Any, format_pattern: str) -> str:
    """Format a numeric value according to format pattern.

    Tries the ADR-0004 preset parser first, then falls back to legacy
    hardcoded behavior for backward compatibility.

    Format patterns:
        "general" - as-is
        "number" or "#,##0.00" - standard number format
        "currency" or "$#,##0.00" - currency with symbol
        "percentage" or "0%" - percentage
        "scientific" or "0.00E+00" - scientific notation
        "date" or "YYYY-MM-DD" - date format
        "time" or "HH:MM:SS" - time format
    """
    pattern = str(format_pattern) if format_pattern is not None else "general"

    # Try new ADR-0004 preset renderer first
    try:
        normalized = normalize_format_string(pattern)
        preset = PresetParser.parse(normalized)
        return FormatRenderer.render(value, preset)
    except DeferredFormatRendering:
        # Valid preset but rendering deferred; fall back to general display
        return str(value)
    except Exception:
        # Fall back to legacy hardcoded behavior for backward compatibility
        pass

    return _legacy_format_number(value, pattern)


def _legacy_format_number(value: Any, pattern: str) -> str:
    """Legacy hardcoded formatting for patterns that fail ADR-0004 parsing."""
    try:
        num = float(value)
    except (ValueError, TypeError):
        return str(value)

    if pattern == "general":
        return str(value)
    elif pattern == "number":
        return f"{num:,.2f}"
    elif pattern == "currency":
        if num < 0:
            return f"(${abs(num):,.2f})"
        else:
            return f"${num:,.2f}"
    elif pattern == "percentage":
        return f"{num * 100:.2f}%"
    elif pattern == "scientific":
        return f"{num:.2e}"

    # TODO: Parse complex format patterns like "#,##0.00"
    # For now, return as-is
    return str(value)


_RENDERERS: dict[str, Any] = {
    "general": lambda value, _args: str(value),
    "number": FormatRenderer._render_number,
    "currency": FormatRenderer._render_currency,
    "percent": FormatRenderer._render_percent,
    "scientific": FormatRenderer._render_scientific,
    "boolean": FormatRenderer._render_boolean,
}


def _compile_number_formatter(raw: str) -> NumberFormatter:
    """Compile a formatter for a raw format_number string.

    Normalization and parsing happen once inside this factory. The returned
    callable formats values directly without re-parsing the pattern or
    dispatching through :meth:`FormatRenderer.render` on the hot path.
    """
    pattern = str(raw) if raw is not None else "general"

    try:
        normalized = normalize_format_string(pattern)
        preset = PresetParser.parse(normalized)
    except Exception:
        # Normalization or parsing failed; use the legacy fallback for every
        # future value, exactly as _format_number would do for this raw string.
        return functools.partial(_legacy_format_number, pattern=pattern)

    if preset.kind in ("date", "time", "datetime"):
        return lambda value: str(value)

    renderer = _RENDERERS.get(preset.kind)
    if renderer is None:
        return functools.partial(_legacy_format_number, pattern=pattern)

    args: Mapping[str, object] = preset.args

    def formatter(value: Any) -> str:
        try:
            return renderer(value, args)
        except Exception:
            # Match _format_number's per-value fallback behavior.
            return str(value)

    return formatter


def _format_text(value: str, format_pattern: str) -> str:
    """Format text according to pattern.

    Format patterns:
        "" - as-is
        "upper" - UPPERCASE
        "lower" - lowercase
        "title" - Title Case
        "truncate:N" - Truncate to N chars
    """
    if not format_pattern:
        return value

    if format_pattern == "upper":
        return value.upper()
    elif format_pattern == "lower":
        return value.lower()
    elif format_pattern == "title":
        return value.title()
    elif format_pattern.startswith("truncate:"):
        try:
            n = int(format_pattern.split(":")[1])
            if len(value) > n:
                return value[:n] + "…"
        except (IndexError, ValueError):
            pass

    return value


def get_alignment_for_value(h_align: str, value: Any, value_type: str) -> str:
    """Determine horizontal alignment based on value type.

    Returns adjusted h_align - "right" for numeric if default, otherwise as-specified.
    """
    if h_align != "left":
        # User specified explicit alignment, respect it
        return h_align

    # Default alignment: numeric = right, text = left
    if value_type == "numeric":
        return "right"

    return "left"
