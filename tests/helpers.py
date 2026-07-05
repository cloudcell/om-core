"""Test helpers for OpenM test suite.

Provides canonical helpers used across multiple test modules.
"""

from __future__ import annotations

import os
import tempfile
import time
import uuid

from lib_command.core.message_bus import MessageEnvelope


def make_unique_sock_path(suffix: str = ".sock") -> str:
    """Return a unique Unix socket path safe for parallel test execution.

    Combines a temporary directory, a UUID, and the pytest-xdist worker ID
    (if present) to prevent collisions across parallel workers.

    Usage:
        path = make_unique_sock_path()
        endpoint = TransportEndpoint(kind="unix", path=path)
    """
    worker = os.environ.get("PYTEST_XDIST_WORKER", "")
    unique = uuid.uuid4().hex[:12]
    prefix = f"openm-test-{unique}"
    if worker:
        prefix = f"{prefix}-{worker}"
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=suffix)
    os.close(fd)
    os.unlink(path)
    return path


def make_test_session(engine, workspace=None):
    """Create a CommandSession for tests via SessionGateway.

    Usage:
        from tests.helpers import make_test_session
        session = make_test_session(engine, ws)
        grid = MatrixGrid(view_id=view.id, session=session)
    """
    from lib_command.core.session_gateway import get_session_gateway, SessionGateway
    from lib_command.core.bootstrap import init_command_services
    # Ensure gateway is recreated if the bus was reset by a prior test
    SessionGateway._instance = None
    init_command_services()
    ws = workspace or getattr(engine, "workspace", None)
    if ws is not None:
        from lib_openm.lib_meta.bootstrap import ensure_system_cubes
        from lib_openm.outline_graph_bridge import migrate_workspace_outline_to_graph
        ensure_system_cubes(ws)
        migrate_workspace_outline_to_graph(ws)
    gateway = get_session_gateway()
    return gateway.create_session(
        client_type="test",
        engine=engine,
        workspace=ws,
    )


def make_test_envelope(
    command_id: str,
    payload: dict,
    context=None,
    topic: str | None = None,
) -> MessageEnvelope:
    """Construct a canonical MessageEnvelope for testing (replaces CommandEvent)."""
    return MessageEnvelope(
        message_id=str(uuid.uuid4()),
        message_type="command",
        topic=topic or f"command.{command_id}",
        correlation_id=str(uuid.uuid4()),
        session_id=None,
        client_type=None,
        workspace_id=None,
        actor_id=None,
        timestamp=time.perf_counter(),
        payload=dict(payload),
        context=context,
        status="accepted",
        command_id=command_id,
    )


class _MockResult:
    """Minimal result stand-in for mock-session execute."""
    __slots__ = ("success", "data", "error")

    def __init__(self, success: bool = False, data=None, error: str | None = None):
        self.success = success
        self.data = data
        self.error = error


class _MockSession:
    """Minimal session stand-in for tests that need manual engine/workspace injection.

    Provides local variable storage and dispatches execute/query through a
    real executor when one is attached and context.engine is available.
    """

    def __init__(self, executor=None):
        self.executor = executor
        if executor is not None:
            try:
                from lib_command.core.bootstrap import register_default_commands
                register_default_commands()
            except Exception:
                pass
        self.context = type("Context", (), {
            "engine": None,
            "workspace": None,
            "variables": {},
            "global_vars": {},
        })()

    def get_variables(self) -> dict:
        return self.context.variables

    def get_global_vars(self) -> dict:
        return self.context.global_vars

    def execute(self, command_id: str, **kwargs):
        if self.executor is not None and self.context.engine is not None:
            try:
                from lib_command.core.executor import ExecutionContext
                ctx = ExecutionContext(
                    engine=self.context.engine,
                    workspace=self.context.workspace,
                )
                ctx.variables = self.context.variables
                return self.executor.execute(command_id, context=ctx, **kwargs)
            except Exception as e:
                return _MockResult(success=False, data={}, error=str(e))
        return _MockResult(success=False, data={}, error="No engine available")

    def query(self, query_type: str, **kwargs):
        if self.executor is not None and self.context.engine is not None:
            try:
                from lib_command.commands.query import cmd_query
                from lib_command.core.executor import ExecutionContext
                workspace = self.context.workspace
                if workspace is None and hasattr(self.context.engine, "workspace"):
                    workspace = self.context.engine.workspace
                ctx = ExecutionContext(
                    engine=self.context.engine,
                    workspace=workspace,
                )
                ctx.variables = self.context.variables
                return cmd_query(ctx, query_type, **kwargs)
            except Exception:
                pass
        return None


# ---------------------------------------------------------------------------
# Dimension-aware cell addressing helpers
# ---------------------------------------------------------------------------

# TRANSITIONAL_TEST_HELPERS:
# The helpers below adapt legacy positional-tuple test addressing to the
# public Engine cell_ref API.  They no longer call private or deprecated
# Engine methods.  Once all tests are migrated to cell_ref_by_dim, these
# helpers can be deleted.

def _find_default_view_for_cube(engine, cube_id: str) -> str:
    """Return the first view whose cube_id matches ``cube_id``.

    If no view exists for the cube, create a default view with the first
    dimension as rows and the remaining dimensions as columns.  This is a
    transitional convenience for tests that still address cells by positional
    tuple.
    """
    for view in engine.list_views():
        view_id = getattr(view, "id", view)
        view_obj = engine.require_view_by_id(view_id)
        if getattr(view_obj, "cube_id", None) == cube_id:
            return view_id

    cube = engine.require_cube_by_id(cube_id)
    dim_ids = [d for d in cube.dimension_ids if d != "@"]
    if not dim_ids:
        raise ValueError(f"Cube {cube_id} has no dimensions; cannot create a default view")
    row_dim_ids = [dim_ids[0]]
    col_dim_ids = dim_ids[1:]
    view = engine.create_view(
        name=f"test_default_view_{cube_id[:8]}",
        cube_id=cube_id,
        row_dim_id=row_dim_ids[0] if row_dim_ids else None,
        col_dim_id=col_dim_ids[0] if col_dim_ids else None,
        page_dim_ids=col_dim_ids[1:] if len(col_dim_ids) > 1 else [],
    )
    return view.id


def cell_ref_by_dim(engine, cube_id: str, addr_by_dim_id: dict[str, str]) -> dict:
    """Build a ``cell_ref`` of kind ``ids`` from a dimension-aware address.

    ``addr_by_dim_id`` maps dimension IDs to item IDs.  The function reads the
    default view's row/col/page dimensions and builds ``row_key``/``col_key``/
    ``page_key`` from that mapping.
    """
    view_id = _find_default_view_for_cube(engine, cube_id)
    view = engine.require_view_by_id(view_id)

    row_key = tuple(addr_by_dim_id[dim_id] for dim_id in view.row_dim_ids)
    col_key = tuple(addr_by_dim_id[dim_id] for dim_id in view.col_dim_ids)
    page_key = {
        dim_id: addr_by_dim_id.get(dim_id)
        for dim_id in getattr(view, "page_dim_ids", [])
        if dim_id in addr_by_dim_id
    }

    return {"kind": "ids", "row_key": row_key, "col_key": col_key, "page_key": page_key}


def set_cell_by_dim(engine, cube_id: str, addr_by_dim_id: dict[str, str], value):
    """Set a cell hardvalue using dimension-aware addressing."""
    view_id = _find_default_view_for_cube(engine, cube_id)
    cell_ref = cell_ref_by_dim(engine, cube_id, addr_by_dim_id)
    engine.set_cell_hardvalue(view_id, cell_ref, value)


def set_rule_by_dim(engine, cube_id: str, addr_by_dim_id: dict[str, str], expression: str):
    """Set an anchored rule using dimension-aware addressing."""
    view_id = _find_default_view_for_cube(engine, cube_id)
    cell_ref = cell_ref_by_dim(engine, cube_id, addr_by_dim_id)
    engine.set_rule_anchored(view_id, cell_ref, expression)


def get_cell_by_dim(engine, cube_id: str, addr_by_dim_id: dict[str, str]):
    """Read a cell value using dimension-aware addressing."""
    view_id = _find_default_view_for_cube(engine, cube_id)
    cell_ref = cell_ref_by_dim(engine, cube_id, addr_by_dim_id)
    return engine.get_cell_value(view_id, cell_ref).value

