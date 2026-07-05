"""
System commands - Save, load, recalc, quit operations.
"""

from __future__ import annotations

from typing import Optional


def cmd_recalc(ctx, scope: str = "all") -> dict:
    """
    Recalculate the model.

    Args:
        scope: "all", "visible", "cube:<id>"
    """
    engine = ctx.engine
    if not engine:
        raise ValueError("No engine available")

    ctx.status(f"Recalculating ({scope})...")

    # NOTE: _invalidate_slice_dependent_rules() was removed from here.
    # It is now called internally by engine outline-mutation methods
    # (add_dimension_item, set_dimension_item_order, move_nodes,
    # delete_dimension_items) so that invalidation happens at the mutation
    # site, not during recalculation.

    if scope == "all":
        if hasattr(engine, 'recalculate_all'):
            engine.recalculate_all()
        elif hasattr(engine, 'calculate'):
            engine.calculate()
    elif scope == "visible":
        # Visible recalculation: invalidate stale visible cell nodes before recomputing.
        # The engine recomputes the full workspace; visible cells are refreshed
        # on the next grid read. Future: narrow to viewport-only cells.
        if hasattr(engine, 'recalculate_all'):
            engine.recalculate_all()
        elif hasattr(engine, 'calculate'):
            engine.calculate()
    elif scope.startswith("cube:"):
        cube_id = scope[5:]
        if hasattr(engine, 'recalculate_cube'):
            engine.recalculate_cube(cube_id)

    return {"scope": scope, "status": "completed"}


def cmd_save(ctx, path: Optional[str] = None) -> dict:
    """Save the current workspace."""
    ws = ctx.workspace
    if not ws:
        raise ValueError("No workspace available")

    # Phase 6D/v16: workspace file stores only workspace-level defaults.
    # Per-view UI state (cursor, selection, anchor, scroll) lives in SessionStore.
    session_id = getattr(ctx, 'session_id', None)
    if session_id:
        from lib_command.core.session_store import get_session_store
        vs = get_session_store().get_view_state(session_id)
        if vs is not None:
            # Validate: missing active view -> fallback to first view
            active_view_id = vs.active_view_id
            if not active_view_id or active_view_id not in ws.views:
                active_view_id = ws.views_order[0] if ws.views_order else (
                    next(iter(ws.views.keys())) if ws.views else None
                )
                vs.active_view_id = active_view_id

            # Update workspace-level saved default
            ws.set_saved_default_view_id(active_view_id)

    save_path = path or "auto"

    adapter = getattr(ctx, "persistence_adapter", None)
    if adapter is None:
        raise ValueError("No persistence adapter available in command context")

    try:
        adapter.save_workspace(save_path, ws)
        variables = getattr(ctx, "variables", None)
        if variables is not None:
            variables["current_file_path"] = save_path
            variables["current_file_dirty"] = False
        ctx.status(f"Saved to {save_path}")
        return {"path": save_path}
    except Exception as e:
        ctx.status(f"Error saving: {e}")
        raise


def cmd_load(ctx, path: str) -> dict:
    """Load a workspace."""
    adapter = getattr(ctx, "persistence_adapter", None)
    if adapter is None:
        raise ValueError("No persistence adapter available in command context")

    try:
        ws, profile = adapter.load_workspace_profiled(path)
        if ws:
            ctx.workspace = ws

            # Tell the timeline service the new workspace ID so subsequent
            # checkpoints are saved to the correct datastore.
            timeline = getattr(getattr(ctx, "services", None), "timeline", None)
            if timeline is not None:
                ws_id = getattr(ws, "id", None)
                if ws_id is not None:
                    timeline.set_workspace_id(ws_id)

            # Phase 6D/v16: initialise SessionViewState from workspace-level saved
            # default and legacy per-view UI state (schema <=15).
            # SessionStore owns live runtime state; workspace owns canonical defaults.
            session_id = getattr(ctx, 'session_id', None)
            if session_id:
                from lib_command.core.session_store import get_session_store
                from lib_command.core.session_view_state import SessionViewState
                store = get_session_store()
                vs = store.get_view_state(session_id)
                if vs is None:
                    vs = SessionViewState(session_id=session_id)
                    store.set_view_state(session_id, vs)
                if vs is not None:
                    # Workspace-level active view default is the initial session default
                    if ws.saved_default_view_id:
                        vs.active_view_id = ws.saved_default_view_id

                    # Migrate legacy per-view UI state from schema <=15 files
                    legacy_ui_state = profile.get("legacy_ui_state", {})
                    active_view_id = vs.active_view_id
                    if active_view_id and active_view_id in legacy_ui_state:
                        active_state = legacy_ui_state[active_view_id]
                    elif ws.saved_default_view_id and ws.saved_default_view_id in ws.views:
                        active_state = legacy_ui_state.get(ws.saved_default_view_id, {})
                    else:
                        active_state = next(iter(legacy_ui_state.values()), {}) if legacy_ui_state else {}

                    active_cell = active_state.get("active_cell")
                    if active_cell is not None:
                        vs.active_cell = tuple(active_cell)
                    selection_mode = active_state.get("selection_mode")
                    if selection_mode is not None:
                        vs.selection_mode = selection_mode
                    selected_indices = active_state.get("selected_indices")
                    if selected_indices is not None:
                        vs.selected_indices = [
                            tuple(idx) if isinstance(idx, (list, tuple)) else idx
                            for idx in selected_indices
                        ]
                    anchor_cell = active_state.get("anchor_cell")
                    if anchor_cell is not None:
                        vs.anchor_cell = tuple(anchor_cell)
                    scroll_pos = active_state.get("scroll_pos")
                    if scroll_pos is not None:
                        vs.scroll_pos = tuple(scroll_pos)

                    # Page selections are canonical view state, copied from the active view
                    active_view = ws.views.get(active_view_id)
                    if active_view is not None:
                        vs.page_selections = dict(active_view.page_selections)

            # Keep engine saved default in sync with loaded workspace.
            engine = getattr(ctx, 'engine', None)
            if engine is not None:
                engine.replace_workspace(ws)
                ctx.workspace = engine.workspace

            variables = getattr(ctx, "variables", None)
            if variables is not None:
                variables["current_file_path"] = path
                variables["current_file_dirty"] = False

            ctx.status(f"Loaded {path}")

            # Notify all observers that a new workspace is now active.
            # Isolated: bus errors must never fail the load command.
            try:
                from lib_command.core.domain_event_publisher import publish_domain_event
                from lib_command.core.message_bus import get_message_bus
                publish_domain_event(
                    get_message_bus(),
                    "event.workspace.loaded",
                    {"workspace_id": getattr(ws, "id", None), "path": path},
                )
            except Exception:
                pass  # Event emission failure is non-fatal

            return {"path": path}
        else:
            raise ValueError(f"Failed to load: {path}")
    except Exception as e:
        ctx.status(f"Error loading: {e}")
        raise


def cmd_quit(ctx) -> None:
    """Quit the application."""
    ctx.status("Quitting...")
    return {"action": "quit"}


def cmd_cancel_recalc(ctx) -> dict:
    """Request cancellation of an in-progress recalculation."""
    engine = ctx.engine
    if not engine:
        raise ValueError("No engine available")

    if hasattr(engine, 'request_cancel'):
        engine.request_cancel()
        ctx.status("Recalc cancellation requested")
        return {"status": "cancelled"}
    else:
        ctx.status("Cancellation not supported by engine")
        return {"status": "not_supported"}


def cmd_set_dependency_tracking(ctx, enabled: bool = True) -> dict:
    """Enable or disable dependency tracking."""
    engine = ctx.engine
    if not engine:
        raise ValueError("No engine available")

    if hasattr(engine, 'enable_dependency_tracking'):
        engine.enable_dependency_tracking(enabled)
        ctx.status(f"Dependency tracking {'enabled' if enabled else 'disabled'}")
        return {"enabled": enabled}
    else:
        ctx.status("Dependency tracking not supported by engine")
        return {"enabled": None}


def cmd_set_multithread_recompute(ctx, enabled: bool = True) -> dict:
    """Enable or disable multithreaded recalculation."""
    engine = ctx.engine
    if not engine:
        raise ValueError("No engine available")

    if hasattr(engine, 'enable_multithread_recompute'):
        engine.enable_multithread_recompute(enabled)
        ctx.status(f"Multithreaded recalculation {'enabled' if enabled else 'disabled'}")

        from lib_command.core.domain_event_publisher import publish_domain_event
        from lib_command.core.message_bus import get_message_bus

        publish_domain_event(
            get_message_bus(),
            "event.system.config_changed",
            {
                "property": "multithread_recompute",
                "enabled": enabled,
            },
            correlation_id=getattr(ctx, "correlation_id", None),
            session_id=getattr(ctx, "session_id", None),
            causation_id=getattr(ctx, "command_message_id", None),
        )

        return {"enabled": enabled}
    else:
        ctx.status("Multithreaded recalculation not supported by engine")
        return {"enabled": None}


def cmd_clear_cache(ctx, scope: str = "all") -> dict:
    """Clear internal evaluation caches.

    Operational command — no domain event unless visible derived values change.

    Args:
        scope: "all" clears cell, slice, and function caches;
               "cell" clears only the cell value cache.
    """
    engine = ctx.engine
    if not engine:
        raise ValueError("No engine available")

    cleared = False
    if scope == "all":
        if hasattr(engine._core, '_clear_caches'):
            engine._core._clear_caches()
            ctx.status("All caches cleared")
            cleared = True
        elif hasattr(engine._core, '_clear_cell_cache'):
            engine._core._clear_cell_cache()
            ctx.status("Cell cache cleared")
            cleared = True
    elif scope == "cell":
        if hasattr(engine._core, '_clear_cell_cache'):
            engine._core._clear_cell_cache()
            ctx.status("Cell cache cleared")
            cleared = True
    else:
        ctx.status(f"Unknown cache scope: {scope}")
        return {"cleared": False, "scope": scope}

    return {"cleared": cleared, "scope": scope}


def cmd_clear_profiler_snapshot(ctx) -> dict:
    """Reset profiler counters (dependency metrics and rule evaluation profile)."""
    engine = ctx.engine
    if not engine:
        raise ValueError("No engine available")

    if hasattr(engine, 'reset_profiler_snapshot'):
        engine.reset_profiler_snapshot()
        ctx.status("Profiler snapshot cleared")
        return {"cleared": True}
    else:
        ctx.status("Profiler snapshot reset not supported by engine")
        return {"cleared": False}


def cmd_run_recalculation(ctx, scope: str = "all") -> dict:
    """Recalculate the model — canonical command.

    Thin wrapper around :func:`cmd_recalc` for canonical naming.
    """
    return cmd_recalc(ctx, scope)


def cmd_cancel_recalculation(ctx) -> dict:
    """Cancel an in-progress recalculation — canonical command.

    Thin wrapper around :func:`cmd_cancel_recalc` for canonical naming.
    """
    return cmd_cancel_recalc(ctx)


def cmd_save_workspace(ctx, path: Optional[str] = None) -> dict:
    """Save the current workspace — canonical command.

    Thin wrapper around :func:`cmd_save` for canonical naming.
    """
    return cmd_save(ctx, path)


def cmd_load_workspace(ctx, path: str) -> dict:
    """Load a workspace — canonical command.

    Thin wrapper around :func:`cmd_load` for canonical naming.
    """
    return cmd_load(ctx, path)


def cmd_create_new_workspace(ctx, engine_type: str = "python") -> dict:
    """Create a new demo workspace and replace the engine.

    Canonical command so remote clients can create workspaces through
    the command spine without direct composition-root access.
    """
    from lib_runtime.session_ops import create_new_workspace

    workspace = create_new_workspace(engine_type=engine_type, context=ctx)

    # Update timeline service to the new workspace's ID
    timeline = getattr(getattr(ctx, "services", None), "timeline", None)
    if timeline is not None:
        ws_id = getattr(workspace, "id", None)
        if ws_id is not None:
            timeline.set_workspace_id(ws_id)

    # Notify all observers that a new workspace is now active.
    # Isolated: bus errors must never fail the create command.
    try:
        from lib_command.core.domain_event_publisher import publish_domain_event
        from lib_command.core.message_bus import get_message_bus
        publish_domain_event(
            get_message_bus(),
            "event.workspace.created",
            {"workspace_id": getattr(workspace, "id", None)},
        )
    except Exception:
        pass  # Event emission failure is non-fatal

    # Reset view selections to top-left and default page for all views
    for view in workspace.views.values():
        view.active_cell = (0, 0)
        view.anchor_cell = (0, 0)
        view.selected_indices = [(0, 0)]
        view.selection_mode = "cell"
        view.scroll_pos = None
        view.page_selections = {}

    return {"workspace_id": workspace.id}


def cmd_undo(ctx) -> dict:
    """Undo the last action — meta-command.

    Does not push itself onto the undo stack. Wraps Engine.undo() directly
    and returns a structured result so UI code can inspect changed state
    without parsing text.
    """
    engine = ctx.engine
    if not engine:
        raise ValueError("No engine available")

    if hasattr(engine, 'undo'):
        desc = engine.undo()
        ctx.status(f"Undone: {desc}" if desc else "Nothing to undo")
        return {
            "changed": desc is not None,
            "description": desc,
            "affected_scope": None,
        }
    else:
        ctx.status("Undo not supported by engine")
        return {"changed": False, "description": None, "affected_scope": None}


def cmd_redo(ctx) -> dict:
    """Redo the last undone action — meta-command.

    Does not push itself onto the undo stack. Wraps Engine.redo() directly
    and returns a structured result so UI code can inspect changed state
    without parsing text.
    """
    engine = ctx.engine
    if not engine:
        raise ValueError("No engine available")

    if hasattr(engine, 'redo'):
        desc = engine.redo()
        ctx.status(f"Redone: {desc}" if desc else "Nothing to redo")
        return {
            "changed": desc is not None,
            "description": desc,
            "affected_scope": None,
        }
    else:
        ctx.status("Redo not supported by engine")
        return {"changed": False, "description": None, "affected_scope": None}


def cmd_set_engine(ctx, engine_type: str = "python", dependency_tracking: bool = True) -> dict:
    """Switch the calculation engine for the current workspace.

    Args:
        engine_type: Type of engine to switch to (e.g. "python").
        dependency_tracking: Whether to enable dependency tracking on the new engine.
    """
    ws = ctx.workspace
    if ws is None:
        raise ValueError("No workspace available")

    from lib_runtime.session_ops import switch_engine

    new_engine = switch_engine(ws, engine_type, context=ctx)
    if hasattr(new_engine, 'enable_dependency_tracking'):
        new_engine.enable_dependency_tracking(dependency_tracking)

    return {"engine_type": engine_type, "dependency_tracking": dependency_tracking, "status": "completed"}
