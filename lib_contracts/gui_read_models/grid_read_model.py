"""Grid read model — read-only query facade for grid/view shape data.

This is NOT a cache. This is NOT a synchronized projection.
It delegates to query handlers which read engine state.

Usage:
    grid_read_model = GridReadModel(session)
    row_keys = grid_read_model.row_keys(view_id)
    col_keys = grid_read_model.col_keys(view_id)
    header = grid_read_model.row_header(view_id, section)
    header = grid_read_model.col_header(view_id, section)

Boundary:
    Only plain lists and strings cross this boundary — never engine objects.
"""

from __future__ import annotations


class GridReadModel:
    """Read-only query facade for grid/view shape data.

    This is NOT a cache. This is NOT a synchronized projection.
    It delegates to query handlers which read engine state.

    Usage:
        - Table row/column counts -> row_keys() / col_keys()
        - Header labels -> row_header() / col_header()

    Caching is NOT included in Phase E. It will be added later when
    invalidation events are designed.
    """

    def __init__(self, session) -> None:
        self.session = session

    def row_keys(
        self,
        view_id: str,
    ) -> list[tuple[str, ...]]:
        """Get row keys for a view."""
        data = self.session.query("view_row_keys", view_id=view_id)
        if data:
            return data.get("keys", [])
        return []

    def col_keys(
        self,
        view_id: str,
    ) -> list[tuple[str, ...]]:
        """Get column keys for a view."""
        data = self.session.query("view_col_keys", view_id=view_id)
        if data:
            return data.get("keys", [])
        return []

    def row_header(
        self,
        view_id: str,
        section: int,
    ) -> str:
        """Get row header label for a given section."""
        data = self.session.query("view_row_header", view_id=view_id, section=section)
        if data:
            return data.get("header", "")
        return ""

    def addr_for_rc(
        self,
        view_id: str,
        row: int,
        col: int,
    ) -> tuple[str, ...]:
        """Resolve view row/col indices to full address tuple.

        Delegates to row_keys / col_keys queries, then addr_resolve.
        """
        row_keys = self.row_keys(view_id)
        col_keys = self.col_keys(view_id)
        if not row_keys or not col_keys:
            return ()
        if row < 0 or row >= len(row_keys) or col < 0 or col >= len(col_keys):
            return ()
        data = self.session.query(
            "addr_resolve",
            view_id=view_id,
            row_key=row_keys[row],
            col_key=col_keys[col],
        )
        if data:
            addr = data.get("addr", ())
            return tuple(addr) if isinstance(addr, list) else addr
        return ()

    def col_header(
        self,
        view_id: str,
        section: int,
    ) -> str:
        """Get column header label for a given section."""
        data = self.session.query("view_col_header", view_id=view_id, section=section)
        if data:
            return data.get("header", "")
        return ""
