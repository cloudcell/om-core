"""
Navigation commands — LEGACY module.

DEPRECATED: This module contains legacy navigation handlers that are
superseded by view_state.py commands:

  - cmd_navigate        -> use move_selection (view_state.py)
  - cmd_get_selection   -> use query("selection_current")
  - cmd_set_selection   -> use set_selection (view_state.py)

These handlers remain registered for backward compatibility but must not
mutate GUI directly and must not become sources of truth.  Removal
will happen in Phase 7B after all callers are confirmed migrated.
"""

from __future__ import annotations


def cmd_navigate(ctx, direction: str, amount: int = 1, row: int = 0, col: int = 0) -> dict:
    """DEPRECATED: Use move_selection (view_state.py) instead.

    Legacy engine-based navigation.  Does not write to SessionStore.
    Remains registered only for backward compatibility.
    """
    # Phase 5E/6A: command handlers no longer read GUI or engine.active_view_id.
    # Bounds validation uses SessionViewState.active_view_id if available.
    engine = getattr(ctx, 'engine', None)
    session_id = getattr(ctx, 'session_id', None)
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

            ctx.status(f"Navigated {direction} to ({row}, {col})")
            return {"direction": direction, "amount": amount, "position": (row, col)}
        except Exception:
            pass

    ctx.status(f"Navigate {direction} by {amount}")
    return {"direction": direction, "amount": amount, "position": (row, col)}


def cmd_get_selection(ctx) -> dict:
    """DEPRECATED: Use query("selection_current") instead.

    Legacy compatibility handler — returns a generic response.
    Does not access GUI or engine runtime state.
    Remains registered only for backward compatibility.
    """
    ctx.status("get_selection is deprecated; use query('selection_current')")
    return {
        "position": (0, 0),
        "addresses": [],
        "deprecated": True,
    }


