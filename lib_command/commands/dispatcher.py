"""
Main command dispatcher - Routes 'set' commands to appropriate handlers.
Supports batch operations for comma-separated targets.
"""

from __future__ import annotations

from typing import Any, Optional

# Sentinel object for when no value is provided
_MISSING = object()


def cmd_set(
    ctx,
    target: str,
    property: str,
    value: Any = _MISSING
) -> dict:
    """Generic property-set dispatcher.

    This handler serves the transitional ``set_property`` scoped command
    (registered in ``bootstrap.py``) as well as legacy bare-``set`` callers.
    It routes to domain-specific handlers (format, data, view, model,
    session, workspace) based on the ``target`` and ``property`` patterns.

    Args:
        ctx: Execution context.
        target: What to modify (e.g., ``"selection"``, ``"cell:A1"``,
            ``"cell:A1,cell:B2"`` for batch).
        property: Property path (e.g., ``"format.bold"``, ``"data.value"``).
        value: New value to set.  If omitted, defaults to ``True``.

    Returns:
        Dict with operation result.  For batch operations, includes a
        ``results`` list.

    Migration note:
        This is a transitional polyfill.  New code should prefer
        domain-scoped commands (``set_cell_value``, ``set_format``, etc.)
        once they cover all needed property paths.
    """
    from .utils import _parse_target
    from .format import cmd_set_format
    from .data import cmd_set_data
    from .model import cmd_create, _parse_target as _parse_model_target

    # If value is missing, treat target as "value" for property-less set
    # e.g., "set selection bold" → set selection format.bold true
    if value is _MISSING:
        value = True

    # Check if target contains comma-separated sub-targets
    if "," in str(target):
        return _set_batch(ctx, target, property, value)

    # Single-target path (original behavior)
    target_type, target_id = _parse_target(target)

    # Route session: targets to session handler
    if target_type == "session":
        return _set_session_property(ctx, target_id, property, value)

    # Route workspace targets
    if target_type == "workspace":
        return _set_workspace_property(ctx, target_id, property, value)

    # Route to appropriate handler based on property category
    if property.startswith("format."):
        return cmd_set_format(ctx, target_type, target_id, property, value)
    elif property.startswith("data."):
        return cmd_set_data(ctx, target_type, target_id, property, value)
    elif property.startswith("view."):
        return _set_view_property(ctx, target_type, target_id, property, value)
    elif property.startswith("model."):
        return _set_model_property(ctx, target_type, target_id, property, value)
    else:
        raise ValueError(f"Unknown property category: {property}")


def _set_batch(
    ctx,
    target: str,
    property: str,
    value: Any
) -> dict:
    """
    Set a property on multiple comma-separated targets.

    Splits the target string on commas and applies the property to each
    sub-target individually. Returns aggregated results.

    Example:
        set cell:A1,cell:B2,cell:C3 format.bold true
        → applies format.bold=true to all three cells
    """
    sub_targets = [t.strip() for t in target.split(",") if t.strip()]
    if not sub_targets:
        return {"affected": 0, "errors": ["No targets specified"]}

    results = []
    errors = []
    affected = 0

    for sub_target in sub_targets:
        try:
            result = cmd_set(ctx, sub_target, property, value)
            results.append(result)
            affected += 1
        except Exception as e:
            errors.append(f"{sub_target}: {e}")
            results.append({"error": str(e)})

    return {
        "affected": affected,
        "total": len(sub_targets),
        "results": results,
        "errors": errors if errors else None,
    }


def _set_view_property(
    ctx,
    target_type: str,
    target_id: Optional[str],
    property: str,
    value: Any
) -> dict:
    """Set a view property (selection, cursor, active_cell, selection_mode, etc.)."""
    view_prop = property.replace("view.", "")

    if view_prop == "selection":
        ctx.selection = value
        ctx.status(f"Selection set to {value}")
        return {"selection": value}
    elif view_prop == "cursor":
        ctx.status(f"Cursor moved to {value}")
        return {"cursor": value}
    elif view_prop in ("active_cell", "selection_mode", "selected_indices", "anchor_cell", "scroll_pos"):
        # Schema v16: these are per-session UI state fields. They are stored in
        # SessionStore, not on the canonical view object.
        if target_type != "view" or not target_id:
            raise ValueError(f"view.{view_prop} requires a view target")
        session_id = getattr(ctx, "session_id", None)
        if not session_id:
            raise ValueError("No session_id available for view UI state")
        from lib_command.core.session_store import get_session_store
        store = get_session_store()
        if view_prop == "active_cell":
            store.set_active_cell(session_id, tuple(value) if value is not None else None)
        elif view_prop == "anchor_cell":
            store.set_anchor_cell(session_id, tuple(value) if value is not None else None)
        elif view_prop == "scroll_pos":
            store.set_scroll_pos(session_id, tuple(value) if value is not None else None)
        elif view_prop == "selected_indices":
            store.set_selected_indices(session_id, list(value) if value is not None else [])
        elif view_prop == "selection_mode":
            store.set_selection_mode(session_id, value)
        ctx.status(f"Set {view_prop} on view {target_id}")
        return {"view_id": target_id, "property": view_prop, "value": value}
    elif view_prop == "name":
        if target_type != "view" or not target_id:
            raise ValueError("view.name requires a view target")
        engine = ctx.engine
        if not engine:
            raise ValueError("No engine available")
        view = engine.require_view_by_id(target_id)
        if view is None:
            raise ValueError(f"View not found: {target_id}")
        view.name = value
        ctx.status(f"Renamed view {target_id} to {value}")
        return {"view_id": target_id, "name": value}
    else:
        raise ValueError(f"Unknown view property: {view_prop}")


def _set_model_property(
    ctx,
    target_type: str,
    target_id: Optional[str],
    property: str,
    value: Any
) -> dict:
    """Set a model property (dimension, cube attributes)."""
    model_prop = property.replace("model.", "")
    ctx.status(f"Set {model_prop}={value}")
    return {"property": model_prop, "value": value}


def _set_session_property(
    ctx,
    session_key: Optional[str],
    property: str,
    value: Any
) -> dict:
    """Set a session property (active_cube, active_view, etc.).

    Session keys:
        active_cube  → current cube context (stored in variables['_current_cube'])
        active_view  → current active view ID
    """
    if session_key is None:
        raise ValueError("Missing session key (e.g., 'active_cube', 'active_view')")

    # Map session keys to variable names
    key_map = {
        "active_cube": "_current_cube",
        "active_view": "_current_view",
    }

    var_name = key_map.get(session_key)
    if var_name is None:
        raise ValueError(f"Unknown session key: {session_key}. Valid keys: {', '.join(key_map.keys())}")

    # Store in context variables (the bus-style session store)
    if property in ("id", "value", ""):
        ctx.variables[var_name] = value
        # Runtime active view is session state. If a session store is available,
        # route the active_view session variable through it so queries like
        # active_view_current return the same value.
        if session_key == "active_view":
            session_id = getattr(ctx, "session_id", None)
            if session_id:
                from lib_command.core.session_store import get_session_store
                get_session_store().set_active_view(session_id, value)
        ctx.status(f"Session {session_key} set to {value}")
        return {session_key: value}
    else:
        # Allow arbitrary properties on session keys
        ctx.variables[f"_session.{session_key}.{property}"] = value
        ctx.status(f"Session {session_key}.{property} = {value}")
        return {f"{session_key}.{property}": value}


def _set_workspace_property(
    ctx,
    workspace_key: Optional[str],
    property: str,
    value: Any,
) -> dict:
    """Set a workspace-level property (views_order, etc.)."""
    if property == "views_order":
        ws = ctx.engine.workspace if ctx.engine else None
        if ws is None:
            raise ValueError("No engine/workspace available")
        ws.views_order = value
        ctx.status(f"Set workspace views_order")
        return {"property": "views_order", "value": value}
    else:
        raise ValueError(f"Unknown workspace property: {property}")
