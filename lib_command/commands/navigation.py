"""
Navigation commands — LEGACY compatibility module.

These handlers are stable macro-language aliases:

  - cmd_navigate        -> macro-language "navigate"
  - cmd_get_selection   -> macro-language "get_selection"
  - cmd_set_selection   -> registered as "set_selection" canonical handler

They are superseded by view_state.py commands for new callers but remain
registered for backward compatibility.  They must not mutate GUI directly
and must not read or write Engine runtime UI state; they read and write
SessionStore via ctx.session_id.
"""

from __future__ import annotations


def cmd_navigate(ctx, direction: str, amount: int = 1, row: int = 0, col: int = 0) -> dict:
    """Navigate the selection in a direction for this session.

    Reads the current cursor from SessionStore, validates bounds via the
    canonical Engine API, and writes the new cursor back to SessionStore.
    Kept as a macro-language compatibility command; canonical callers should
    use ``move_selection``.
    """
    engine = getattr(ctx, "engine", None)
    session_id = getattr(ctx, "session_id", None)

    # Read current cursor from SessionStore (source of truth).
    if session_id:
        from lib_command.core.session_store import get_session_store
        vs = get_session_store().get_view_state(session_id)
        if vs is not None:
            row, col = vs.cursor_row, vs.cursor_col

    # Validate bounds using the active view from SessionStore and the Engine API.
    max_row, max_col = 0, 0
    view_id_for_bounds = None
    if session_id:
        from lib_command.core.session_store import get_session_store
        vs = get_session_store().get_view_state(session_id)
        if vs is not None:
            view_id_for_bounds = vs.active_view_id
    if view_id_for_bounds and engine is not None:
        try:
            row_keys = engine.view_row_keys(view_id_for_bounds)
            col_keys = engine.view_col_keys(view_id_for_bounds)
            max_row = max(0, len(row_keys) - 1)
            max_col = max(0, len(col_keys) - 1)
        except Exception:
            pass

    if direction == "right":
        col = min(col + amount, max_col)
    elif direction == "left":
        col = max(col - amount, 0)
    elif direction == "down":
        row = min(row + amount, max_row)
    elif direction == "up":
        row = max(row - amount, 0)
    elif direction == "first":
        col = 0
    elif direction == "last":
        col = max_col

    # Write new cursor back to SessionStore.
    if session_id:
        from lib_command.core.session_store import get_session_store
        get_session_store().set_selection(
            session_id,
            cursor_row=row,
            cursor_col=col,
            anchor_row=row,
            anchor_col=col,
            selection_mode="cell",
        )

    ctx.status(f"Navigated {direction} to ({row}, {col})")
    return {"direction": direction, "amount": amount, "position": (row, col)}


def cmd_get_selection(ctx) -> dict:
    """Return the current selection for this session.

    Reads from SessionStore (the runtime source of truth).  Kept as a
    macro-language convenience command; callers may also use the
    ``selection_current`` query.
    """
    session_id = getattr(ctx, "session_id", None)
    if session_id:
        from lib_command.core.session_store import get_session_store
        vs = get_session_store().get_view_state(session_id)
        if vs is not None:
            return {
                "position": (vs.cursor_row, vs.cursor_col),
                "anchor": (vs.anchor_row, vs.anchor_col),
                "mode": vs.selection_mode,
                "ranges": [
                    (r.start_row, r.start_col, r.end_row, r.end_col)
                    for r in vs.selection_ranges
                ],
                "selected_indices": list(vs.selected_indices),
                "page_selections": dict(vs.page_selections),
            }

    return {
        "position": (0, 0),
        "anchor": (0, 0),
        "mode": "cell",
        "ranges": [],
        "selected_indices": [],
        "page_selections": {},
    }


