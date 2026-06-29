"""Viewport cell key helpers — pure functions for grid addressing.

Moved from lib_command/commands/grid_helpers.py to remove
command-layer dependency from GUI elements.
"""
from __future__ import annotations

import json


def make_viewport_cell_key(
    row_key: tuple[str, ...],
    col_key: tuple[str, ...],
) -> str:
    """Produce a canonical, reversible, collision-safe viewport-cell key.

    Uses JSON serialization of both key tuples with a delimiter that is
    guaranteed not to appear in valid JSON (private-use Unicode).
    """
    # U+F8FF is a private-use character; it cannot appear in JSON text.
    _DELIMITER = "\uf8ff"
    return json.dumps(row_key, separators=(",", ":")) + _DELIMITER + json.dumps(col_key, separators=(",", ":"))


def parse_viewport_cell_key(key: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Parse a viewport cell key back into row and column key tuples."""
    _DELIMITER = "\uf8ff"
    row_json, col_json = key.split(_DELIMITER, 1)
    row_key = tuple(json.loads(row_json))
    col_key = tuple(json.loads(col_json))
    return row_key, col_key
