"""lib_runtime.session_ops — session-level workspace/engine operations.

These live in lib_runtime (the composition root) because they construct
Engine instances and mutate session context.  GUI must never perform
these steps directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from lib_command.core.session import CommandSession


def replace_session_workspace(
    *,
    session: "CommandSession | None" = None,
    context: Any = None,
    engine: Any = None,
    workspace: Any = None,
) -> None:
    """Replace the active workspace and rebind the session or context.

    Accepts either a CommandSession or a raw ExecutionContext.
    """
    if engine is not None and workspace is not None:
        engine.replace_workspace(workspace)
    if session is not None and hasattr(session, "context") and session.context is not None:
        session.context.engine = engine
        session.context.workspace = workspace
    if context is not None:
        context.engine = engine
        context.workspace = workspace


def switch_engine(
    workspace: Any,
    engine_type: str = "python",
    *,
    session: "CommandSession | None" = None,
    context: Any = None,
) -> Any:
    """Create a new engine for the given workspace and update session/context.

    Returns the new engine.
    """
    from lib_openm.api import Engine
    from lib_command.core.engine_event_publisher import BusEventPublisher

    new_engine = Engine(workspace, event_publisher=BusEventPublisher())
    replace_session_workspace(
        session=session, context=context, engine=new_engine, workspace=workspace
    )
    return new_engine


def create_new_workspace(
    engine_type: str = "python",
    *,
    session: "CommandSession | None" = None,
    context: Any = None,
) -> Any:
    """Create a demo workspace, attach a new engine, and update session/context.

    Returns the new workspace.
    """
    from lib_openm.model import demo_workspace

    workspace = demo_workspace()
    switch_engine(workspace, engine_type, session=session, context=context)
    return workspace


def load_workspace(
    session: "CommandSession", path: str, engine_type: str = "python"
) -> tuple[Any, dict]:
    """Load a workspace from disk, attach a new engine, and update session context.

    Returns (workspace, load_profile).

    This is a transitional runtime helper; command-layer load should use
    ``WorkspacePersistenceAdapter`` via the command spine.
    """
    from lib_storeadapters.json_file_adapter import JsonFileAdapter

    workspace, profile = JsonFileAdapter().load_workspace_profiled(path)
    switch_engine(session, workspace, engine_type)
    return workspace, profile
