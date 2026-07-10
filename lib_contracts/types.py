"""lib_contracts.types — dependency-light foundation module.

Contains shared data-class / enum definitions that both lib_openm and
lib_gui_elements can import without creating a cycle.

This module must not import any lib_* package (lib_openm, lib_command,
lib_gui, lib_runtime, lib_plugins, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, TypeAlias

# ── Type aliases for formatting ──

FormatKind: TypeAlias = Literal[
    "general",
    "number",
    "currency",
    "percent",
    "scientific",
    "boolean",
    "date",
    "time",
    "datetime",
]

FormatArgValue: TypeAlias = str | int | bool


# ── Exceptions ──

class CircularReferenceError(Exception):
    """Raised when a circular dependency is detected in formula evaluation."""
    pass


class RuleValidationError(ValueError):
    """Error raised when rule body validation fails."""
    pass


class CalculationCancelledError(Exception):
    """Raised when a long-running calculation is cancelled by user request."""
    pass


class SnapshotInvariantError(Exception):
    """Raised when the read-only snapshot path observes an invalid engine state."""
    pass


class FormatError(Exception):
    """Base class for all format-related errors."""


class InvalidFormatString(FormatError):
    """Malformed outer quoting or invalid format-string syntax."""


class UnknownFormatPreset(FormatError):
    """Unknown `preset:<kind>` value."""


class InvalidFormatArgument(FormatError):
    """Invalid, missing, or wrongly typed preset argument."""


class UnsupportedFormatPattern(FormatError):
    """`pattern:` family recognized but not implemented."""


class DeferredFormatRendering(FormatError):
    """Parsed preset is valid, but rendering is intentionally deferred."""


# ── Formatting data classes ──

@dataclass
class CellFormat:
    """Formatting for cells, group headers, or dimension items."""
    # Visual style
    bg_color: str | None = None  # hex color like "#ff0000"
    font_color: str | None = None  # hex color like "#000000"
    font_family: str | None = None
    font_size: int | None = None
    font_weight: int = 400  # 100-900: thin(100), light(300), normal(400), medium(500), semibold(600), bold(700), heavy(800), black(900)
    font_italic: bool = False
    font: str | None = None  # Combined font specification (deprecated)

    # Format patterns (one per value type)
    format_number: str = "general"  # Number, currency, percentage, date, time
    format_text: str = ""  # Case, truncate, etc.
    format_null: str = ""  # How to display empty (blank, "N/A", "-")
    format_error: str = ""  # Error display style

    # Legacy compatibility (deprecated)
    number_format: str = "general"  # Deprecated: use format_number
    decimal_places: int = 2  # Deprecated: embed in format_number

    # Layout
    text_h_align: str = "left"  # left, center, right
    text_v_align: str = "middle"  # top, middle, bottom
    text_indent: int = 0  # Number of indents
    text_wrap: bool = False  # Wrap long text
    text_rotation: int = 0  # Angle in degrees (not implemented yet)

    # Borders
    border_top: str = "none"  # none, thin, thick
    border_bottom: str = "none"  # none, thin, thick
    border_left: str = "none"  # none, thin, thick
    border_right: str = "none"  # none, thin, thick
    border_diag_up: str = "none"  # Diagonal up border
    border_diag_down: str = "none"  # Diagonal down border
    border_style: str = "solid"  # solid, dashed, dotted
    border_color: str = "#000000"  # hex color for borders


@dataclass(frozen=True)
class FormatPreset:
    """A parsed format preset with kind and argument mapping."""

    kind: FormatKind
    args: Mapping[str, FormatArgValue]


# ── Outline data class ──

@dataclass
class OutlineNode:
    label: str
    item_id: str | None = None
    children: list["OutlineNode"] = field(default_factory=list)
    node_id: str | None = None
    display_edge_kind: str | None = None  # "MEMBER_OF" / "AGGREG_OF" / None (root)
    is_aggregate: bool = False  # Deprecated: use display_edge_kind == "AGGREG_OF"


# ── Value classification ──

def get_value_type(value: Any) -> str:
    """Classify a Python value into one of: numeric, text, null, error.

    Used to determine which at_value_type channel value to set.
    """
    if value is None:
        return "null"
    # Duck-type CellError to avoid importing lib_openm
    if hasattr(value, "code") and hasattr(value, "_VALID_CODES"):
        return "error"
    if isinstance(value, (int, float)):
        return "numeric"
    # Everything else is text (including str, datetime objects, etc.)
    return "text"


# ── Technical dimension channels ──

TECHNICAL_CHANNELS = [
    # === SECTION 1: CORE DATA ===
    # The value itself and its semantic classification
    "value",        # Default - where cell values live
    # Type is derived from value via get_value_type() function

    # === SECTION 2: COMPACT STYLE ===
    "style",        # JSON string with compact style properties

    # === SECTION 3: FORMAT ===
    # numeric, text, null, error (only 4 types)
    # but multiple formats:
    # scalar | text | temporal | bool | null | error | (range)
    "format_number",
    "format_text",
    "format_null",
    "format_error",

    # === SECTION 4: VISUAL STYLE ===
    "fill",           # Background color
    "font_family",
    "font_size",
    "font_weight",    # 100-900 scale (normal=400, bold=700)
    "font_italic",
    "font_color",

    # === SECTION 5: ALIGNMENT & LAYOUT ===
    "text_h_align",      # Horizontal alignment: left, center, right
    "text_v_align",      # Vertical alignment: top, middle, bottom
    "text_indent",       # Number of indents (int)
    "text_wrap",         # bool: wrap long text
    "text_rotation",     # Angle in degrees (int) (not implemented yet)

    # === SECTION 6: BORDERS ===
    # Border styles for each side: none/type/weight/color
    "border_top",
    "border_bottom",
    "border_left",
    "border_right",
    "border_diag_up",
    "border_diag_down",

    # === SECTION 7: VALIDATION ===
    # Input constraints and data quality
    "validation_type",    # "none" | "list" | "range" | "regex" | "custom"
    "validation_rule",    # The constraint: "A,B,C" | "1..100" | "^"A-Z+"$" | rule
    "validation_message", # Custom error message
    "validation_allow_empty",        # bool: can cell be empty/null?

    # === SECTION 8: SUPPLEMENTARY ===
    "comment",      # Cell comment/annotation
]
