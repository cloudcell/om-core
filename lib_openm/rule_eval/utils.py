"""Utility functions and constants for the rule evaluation engine."""
from __future__ import annotations

import os
from typing import Any

from lib_contracts.types import RuleValidationError

# Debug flag for rule evaluation
_RULE_EVAL_DEBUG = bool(int(os.environ.get("OPENM_RULE_EVAL_DEBUG", "0")))


class CellError:
    """Represents an error value in a cell (e.g., #DIV/0!, #CIRC!, #REF!).

    Using a dedicated type instead of strings allows for:
    - Type-safe error detection (isinstance check vs string comparison)
    - Clear distinction between error values and text strings
    - Extensible error metadata (source, stack trace, etc.)
    """

    # Valid error codes
    _VALID_CODES = frozenset({
        "#SYNTAX!",      # family 0: pre-evaluation gate
        "#NAME!",        # family 1: name / reference
        "#REF!",         # family 1: name / reference
        "#SHAPE!",       # family 2: shape / dimensionality
        "#VALUE!",       # family 3: type / value-kind
        "#N/A",          # family 4: lookup / availability
        "#DIV/0!",       # family 5: arithmetic / numeric
        "#NUM!",         # family 5: arithmetic / numeric
        "#CIRC!",        # family 6: circular dependency
        "#EXPRESSION!",  # family 7: expression fallback
    })

    __slots__ = ("code",)

    def __init__(self, code: str) -> None:
        if code not in self._VALID_CODES:
            raise ValueError(f"Invalid error code: {code!r}")
        self.code: str = code

    def __str__(self) -> str:
        return self.code

    def __repr__(self) -> str:
        return f"CellError({self.code!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, CellError):
            return self.code == other.code
        if isinstance(other, str):
            return self.code == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.code)


def _normalize_negative_zero(value: Any) -> Any:
    """Convert -0.0 to 0.0 to avoid negative zero issues in floating point arithmetic."""
    if isinstance(value, float) and value == 0.0:
        return 0.0
    return value
