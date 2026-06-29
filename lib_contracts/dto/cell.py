"""Cell DTO module — domain-agnostic data transfer objects for cell-level queries.

These TypedDict schemas define the boundary contract for cell data between engine
and GUI. No engine domain objects cross this boundary.

Usage:
    from lib_openm.dto.cell import CellDTO, CellRangeDTO, CellAddressDTO
"""

from __future__ import annotations

from typing import Literal, TypedDict
from typing_extensions import TypeAlias

# ---------------------------------------------------------------------------
# Primitive types
# ---------------------------------------------------------------------------

# CellPrimitive: only primitive Python values allowed in DTOs.
# Never engine objects, never nested complex types.
# NOTE: NaN, Infinity, Decimal, dates, and other non-primitive values must be
# coerced deliberately before crossing the boundary.
#   - NaN/Infinity → kind="error" or display-only text
#   - Decimal → float or str with explicit conversion
#   - Dates → ISO 8601 string
CellPrimitive: TypeAlias = str | int | float | bool | None

# CellKind: literal type for cell value classification
CellKind: TypeAlias = Literal["empty", "number", "text", "bool", "error"]

# CellExplainSource: literal type for explain source classification
CellExplainSource: TypeAlias = Literal["override", "rule", "error", "empty"]


# ---------------------------------------------------------------------------
# DTO schemas
# ---------------------------------------------------------------------------

class CellExplainDTO(TypedDict):
    """Explain data for a single cell. Never contains engine objects."""

    source: CellExplainSource
    rule_body: str | None  # Rule body expression if source is "rule" or "error"
    error: str | None  # Error message if source is "error"
    # depends is a list of full addresses (dimension.item tuples)
    # Can be None if dependency tracking is disabled
    depends: list[tuple[str, ...]] | None


class CellDTO(TypedDict):
    """Snapshot of a single cell's state. Never contains engine objects.

    This is the primary DTO that crosses the engine/GUI boundary for cell data.
    All fields are primitives or nested TypedDicts with primitive fields.
    """

    view_id: str
    cube_id: str
    row_key: tuple[str, ...]  # Row axis keys (dimension items)
    col_key: tuple[str, ...]  # Column axis keys (dimension items)
    addr: tuple[str, ...]  # Full address (all dimension IDs → items)
    value: CellPrimitive  # Raw cell value (primitive only)
    display_value: str  # Display-ready string (e.g., "N/A", "#DIV/0!")
    kind: CellKind  # Cell value kind
    explain: CellExplainDTO


class CellRangeDTO(TypedDict):
    """Snapshot of a rectangular range of cells for grid rendering."""

    view_id: str
    cube_id: str
    row_start: int
    col_start: int
    row_end: int
    col_end: int
    cells: list[CellDTO]  # Flattened list in row-major order
    row_keys: list[tuple[str, ...]]  # Visible row keys
    col_keys: list[tuple[str, ...]]  # Visible column keys


class CellAddressDTO(TypedDict):
    """Result of addr_resolve query: full address resolution for a cell position."""

    view_id: str
    row_key: tuple[str, ...]
    col_key: tuple[str, ...]
    addr: tuple[str, ...]