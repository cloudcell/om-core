"""Cell read model — read-only query facade for cell data.

This is NOT a cache. This is NOT a synchronized projection.
It delegates to query handlers which read engine state.

Usage:
    cell_read_model = CellReadModel(executor)
    cell_dto = cell_read_model.get_cell(view_id, row_key, col_key)
    range_dto = cell_read_model.get_cell_range(view_id, row_keys, col_keys)

Boundary:
    Only CellDTO dicts cross this boundary — never engine objects.
"""

from __future__ import annotations

from lib_contracts.dto import CellPrimitive


# ---------------------------------------------------------------------------
# Migration compatibility helper
# ---------------------------------------------------------------------------

def _result_ok(result) -> bool:
    """Check if an ExecutionResult indicates success.

    Handles the canonical ExecutionResult.success property.
    """
    return getattr(result, "success", False)


# ---------------------------------------------------------------------------
# CellReadModel
# ---------------------------------------------------------------------------

class CellReadModel:
    """Read-only query facade for cell data.

    This is NOT a cache. This is NOT a synchronized projection.
    It delegates to query handlers which read engine state.

    Usage:
        - Single cell reads (rule bar, selected cell details) -> get_cell()
        - Grid rendering -> get_cell_range() (batch)
        - Address resolution -> addr_for_view_keys()

    Caching is NOT included in Phase D. It will be added later when
    invalidation events are designed.
    """

    def __init__(self, session) -> None:
        self.session = session

    def get_cell(
        self,
        view_id: str,
        row_key: tuple[str, ...],
        col_key: tuple[str, ...],
    ) -> dict:
        """Get a single cell as CellDTO (returned as dict)."""
        data = self.session.query(
            "cell_detail",
            view_id=view_id,
            row_key=row_key,
            col_key=col_key,
        )
        if data:
            return data  # type: ignore

        return {
            "view_id": view_id,
            "cube_id": "",
            "row_key": row_key,
            "col_key": col_key,
            "addr": (),
            "value": None,
            "display_value": "",
            "kind": "empty",
            "explain": {
                "source": "empty",
                "rule": None,
                "error": None,
                "depends": None,
            },
        }

    def get_cell_range(
        self,
        view_id: str,
        row_keys: list[tuple[str, ...]],
        col_keys: list[tuple[str, ...]],
    ) -> dict:
        """Get rectangular range of cells as CellRangeDTO (returned as dict).

        Use this for grid/table rendering — NOT individual get_cell() calls.

        Row-major shape invariant: len(cells) == len(row_keys) * len(col_keys)
        always holds, even on failure (full error cells returned).
        """
        data = self.session.query(
            "cell_range",
            view_id=view_id,
            row_keys=row_keys,
            col_keys=col_keys,
        )
        if data:
            return data  # type: ignore

        # Full error cells so shape invariant always holds
        cells = [
            {
                "view_id": view_id,
                "cube_id": "",
                "row_key": rk,
                "col_key": ck,
                "addr": (),
                "value": None,
                "display_value": "",
                "kind": "empty",
                "explain": {
                    "source": "empty",
                    "rule": None,
                    "error": None,
                    "depends": None,
                },
            }
            for rk in row_keys
            for ck in col_keys
        ]
        # Empty ranges use row_end=-1, col_end=-1 by mathematical convention.
        # (UI table models should handle negative end indices as "no data".)
        return {
            "view_id": view_id,
            "cube_id": "",
            "row_start": 0,
            "col_start": 0,
            "row_end": len(row_keys) - 1 if row_keys else -1,
            "col_end": len(col_keys) - 1 if col_keys else -1,
            "cells": cells,
            "row_keys": row_keys,
            "col_keys": col_keys,
        }

    def addr_for_view_keys(
        self,
        view_id: str,
        row_key: tuple[str, ...],
        col_key: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Resolve view keys to full address tuple."""
        data = self.session.query(
            "addr_resolve",
            view_id=view_id,
            row_key=row_key,
            col_key=col_key,
        )
        if data:
            addr = data.get("addr", ())
            return tuple(addr) if isinstance(addr, list) else addr
        return ()

    def cell_value(
        self,
        view_id: str,
        row_key: tuple[str, ...],
        col_key: tuple[str, ...],
    ) -> CellPrimitive:
        """Convenience method for single-cell value reads.

        NOTE: This is NOT a fast path — it still executes a full cell_detail query.
        A real fast path would require a dedicated query.cell_value optimized handler.
        """
        return self.get_cell(view_id, row_key, col_key).get("value")

    def cell_rule(
        self,
        cube_id: str,
        addr: tuple[str, ...],
    ) -> str | None:
        """Get exact-cell rule expression for a cube address, or None."""
        data = self.session.query("cell_rule", cube_id=cube_id, addr=addr)
        if data:
            return data.get("expression")
        return None

    def rule_detail(
        self,
        cube_id: str,
        addr: tuple[str, ...],
    ) -> str | None:
        """Get best matching rule expression for a cube address, or None."""
        data = self.session.query("rule_detail", cube_id=cube_id, addr=addr)
        if data:
            return data.get("expression")
        return None

    def cube_rule_counts(
        self,
        cube_id: str,
    ) -> dict[str, int]:
        """Get rule counts for a cube.

        Returns {"cell_rules": int, "rules": int}.
        """
        data = self.session.query("cube_rule_counts", cube_id=cube_id)
        if data:
            return {
                "cell_rules": data.get("cell_rules", 0),
                "rules": data.get("rules", 0),
            }
        return {"cell_rules": 0, "rules": 0}