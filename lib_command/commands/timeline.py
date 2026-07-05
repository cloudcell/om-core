"""
Timeline commands - Checkpoint and restore operations via message bus.

These commands use ctx.services.timeline (TimelineService) so that
checkpoint/restore operations publish command lifecycle events on the
message bus. GUI code must not set payload callbacks directly.
"""

from __future__ import annotations

from typing import Any, Optional

from lib_command.core.engine_event_publisher import BusEventPublisher


def _get_timeline_service(ctx) -> Any:
    """Resolve TimelineService from command context."""
    services = getattr(ctx, "services", None)
    if services is None:
        raise ValueError("No services in execution context")
    timeline = getattr(services, "timeline", None)
    if timeline is None:
        raise ValueError("No timeline service in execution context")
    return timeline


def cmd_checkpoint(ctx, description: str, parent_id: Optional[str] = None, branch: Optional[str] = None) -> dict:
    """
    Create a timeline checkpoint snapshot.

    Args:
        description: Human-readable description of the checkpoint.
        parent_id: Parent snapshot ID (None for root).
        branch: Branch name (defaults to "main").

    Returns:
        Dict with ``snapshot_id`` on success.
    """
    timeline = _get_timeline_service(ctx)

    result = timeline.create_checkpoint(
        description=description,
        parent_id=parent_id,
        branch=branch,
    )
    snapshot_id = result.get("snapshot_id")
    if not snapshot_id:
        raise RuntimeError("TimelineService.create_checkpoint() returned no snapshot_id")

    ctx.status(f"Checkpoint created: {snapshot_id}")

    # Notify all observers that a new checkpoint exists.
    try:
        from lib_command.core.domain_event_publisher import publish_domain_event
        from lib_command.core.message_bus import get_message_bus
        publish_domain_event(
            get_message_bus(),
            "event.workspace.checkpoint_created",
            {"snapshot_id": snapshot_id, "description": description},
        )
    except Exception:
        pass  # Event emission failure is non-fatal

    return {"snapshot_id": snapshot_id, "description": description, "parent_id": parent_id, "branch": branch or "main"}


def _reset_session_view_state(ctx) -> None:
    """Reset session view interaction state after a workspace restore.

    Active view/cube are preserved when they still exist in the restored
    workspace; otherwise they fall back to the first available view/cube.
    Selection and page filters are always cleared.
    """
    session_id = getattr(ctx, "session_id", None)
    if not session_id:
        return

    from lib_command.core.session_store import get_session_store
    from lib_command.core.session_view_state import SessionViewState

    store = get_session_store()
    vs = store.get_view_state(session_id)
    if vs is None:
        vs = SessionViewState(session_id=session_id)
        store.set_view_state(session_id, vs)

    ws = ctx.workspace
    if ws is None:
        return

    # Active view: keep if valid, otherwise fall back to first view.
    if vs.active_view_id and vs.active_view_id in ws.views:
        active_view_id = vs.active_view_id
    else:
        active_view_id = ws.saved_default_view_id or (
            ws.views_order[0] if ws.views_order else (
                next(iter(ws.views.keys())) if ws.views else None
            )
        )
    vs.active_view_id = active_view_id

    # Current cube: keep if valid, otherwise fall back to active view's cube.
    variables = getattr(ctx, "variables", None)
    current_cube = variables.get("_current_cube") if variables else None
    if current_cube and current_cube in ws.cubes:
        chosen_cube = current_cube
    elif active_view_id and active_view_id in ws.views:
        chosen_cube = ws.views[active_view_id].cube_id
    else:
        cube_ids = list(ws.cubes.keys())
        chosen_cube = cube_ids[0] if cube_ids else None
    if variables is not None:
        variables["_current_cube"] = chosen_cube

    # Clear selection and page filters.
    vs.active_cell = (0, 0)
    vs.anchor_cell = (0, 0)
    vs.selection_mode = "cell"
    vs.selection_ranges = []
    vs.selected_indices = []
    vs.page_selections = {}
    vs.scroll_pos = None


def cmd_restore(ctx, snapshot_id: str, new_description: Optional[str] = None) -> dict:
    """
    Restore workspace to a timeline snapshot.

    Args:
        snapshot_id: Snapshot ID to restore to.
        new_description: Optional custom description for the restored snapshot.

    Returns:
        Dict with ``new_snapshot_id`` on success.
    """
    timeline = _get_timeline_service(ctx)

    restored = timeline.restore_checkpoint(checkpoint_id=snapshot_id, new_description=new_description)
    new_id = restored.diagnostics.get("new_snapshot_id")
    if not new_id:
        raise RuntimeError("TimelineService.restore_checkpoint() returned no new_snapshot_id")

    # Preserve the original workspace file path; the restored state is dirty
    # because it no longer matches the saved file.
    variables = getattr(ctx, "variables", None)
    if variables is not None:
        variables["current_file_dirty"] = True

    # Reset session view state to a valid state in the restored workspace.
    _reset_session_view_state(ctx)

    # Post-restore: clear caches (only when engine is available)
    if getattr(ctx, "engine", None) is not None:
        from .system import cmd_clear_cache
        cmd_clear_cache(ctx, scope="all")

    ctx.status(f"Restored to snapshot: {snapshot_id} (new id: {new_id})")

    # Notify all observers that a checkpoint restore occurred.
    try:
        publisher = BusEventPublisher()
        publisher.publish(
            topic_suffix="workspace.checkpoint_restored",
            payload={
                "checkpoint_id": snapshot_id,
                "workspace_id": getattr(ctx.workspace, "id", None),
            },
            engine=ctx.engine,
            correlation_id=ctx.correlation_id,
            session_id=ctx.session_id,
        )
    except Exception:
        pass  # Event emission failure is non-fatal

    return {"snapshot_id": snapshot_id, "new_snapshot_id": new_id}


def cmd_create_checkpoint(ctx, description: str, parent_id: Optional[str] = None, branch: Optional[str] = None) -> dict:
    """Create a timeline checkpoint snapshot — canonical command.

    Thin wrapper around :func:`cmd_checkpoint` for canonical naming.
    """
    return cmd_checkpoint(ctx, description, parent_id, branch)


def cmd_restore_checkpoint(ctx, snapshot_id: str, new_description: Optional[str] = None) -> dict:
    """Restore workspace to a timeline snapshot — canonical command.

    Thin wrapper around :func:`cmd_restore` for canonical naming.
    """
    return cmd_restore(ctx, snapshot_id, new_description)


def cmd_rename_checkpoint(
    ctx, checkpoint_id: str, description: str
) -> dict[str, str]:
    """Rename a timeline checkpoint.

    Args:
        checkpoint_id: Snapshot ID to rename.
        description: New human-readable description.

    Returns:
        Dict with ``checkpoint_id`` and ``description`` on success.
    """
    timeline = _get_timeline_service(ctx)
    result = timeline.rename_checkpoint(
        checkpoint_id=checkpoint_id, description=description
    )

    ctx.status(f"Checkpoint renamed: {checkpoint_id}")

    try:
        publisher = BusEventPublisher()
        publisher.publish(
            topic_suffix="workspace.checkpoint_renamed",
            payload={
                "checkpoint_id": checkpoint_id,
                "description": description,
                "workspace_id": getattr(ctx.workspace, "id", None),
            },
            engine=ctx.engine,
            correlation_id=ctx.correlation_id,
            session_id=ctx.session_id,
        )
    except Exception:
        pass  # Event emission failure is non-fatal

    return result


def cmd_delete_checkpoint(ctx, checkpoint_id: str) -> dict[str, str]:
    """Delete a timeline checkpoint.

    Args:
        checkpoint_id: Snapshot ID to delete.

    Returns:
        Dict with ``checkpoint_id`` on success.
    """
    timeline = _get_timeline_service(ctx)
    result = timeline.delete_checkpoint(checkpoint_id=checkpoint_id)

    ctx.status(f"Checkpoint deleted: {checkpoint_id}")

    try:
        publisher = BusEventPublisher()
        publisher.publish(
            topic_suffix="workspace.checkpoint_deleted",
            payload={
                "checkpoint_id": checkpoint_id,
                "workspace_id": getattr(ctx.workspace, "id", None),
            },
            engine=ctx.engine,
            correlation_id=ctx.correlation_id,
            session_id=ctx.session_id,
        )
    except Exception:
        pass  # Event emission failure is non-fatal

    return result
