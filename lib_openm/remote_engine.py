"""RemoteEngine — drop-in replacement for lib_openm.api.Engine.

All workspace/data operations are delegated to a remote server via MsgPack RPC.
State machine, generation, and GUI flags are Python-side.
Workspace property is cached and invalidated on mutation responses.

RemoteEngine is purely an RPC client. It does NOT start or manage the
server process — that is the factory's responsibility (via Launcher).
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Callable

import msgpack as _msgpack

from lib_openm.engine_state import (
    EngineState,
    _EngineStateMachine,
    EngineShuttingDownError,
)
from lib_openm._engine_core import _find_unquoted_equals
from lib_openm.model import Workspace
from lib_openm.remote_connection import Connection, RemoteEngineError
from lib_openm.remote_deserialize import (
    _deserialize_value,
    _dto_to_cell_value,
    _dto_to_cube,
    _dto_to_dimension,
    _dto_to_dimension_item,
    _dto_to_rule,
    _dto_to_view,
    _dto_to_workspace,
)
from lib_openm.remote_events import publish_events
from lib_openm.remote_undo import _RemoteUndoManager
from lib_openm.remote_workspace_sync import workspace_to_msgpack_dict
from lib_openm.rpc_constants import RpcMethod
from lib_openm.technical_ids import CHANNEL_TO_AT_ID
from lib_openm._engine_core import CellValue, Explain

_log = logging.getLogger(__name__)


def _empty_cell_value(cube_id: str = "", addr: tuple[str, ...] = ()) -> CellValue:
    """Return a CellValue representing an empty/uncomputed cell."""
    return CellValue(
        value=None,
        explain=Explain(source="empty", cube_id=cube_id, addr=addr),
    )


def _deserialize_outline_tree(data: Any) -> list:
    """Deserialize the server's outline tree response into OutlineNode objects."""
    from lib_contracts.types import OutlineNode

    if not isinstance(data, list):
        return []

    def _build_node(d: dict) -> OutlineNode:
        children = [_build_node(c) for c in (d.get("children") or []) if isinstance(c, dict)]
        return OutlineNode(
            label=d.get("label", ""),
            item_id=d.get("item_id"),
            children=children,
            node_id=d.get("node_id"),
            display_edge_kind=d.get("display_edge_kind"),
            is_aggregate=bool(d.get("is_aggregate", False)),
        )

    return [_build_node(item) for item in data if isinstance(item, dict)]


def _cell_ref_to_addr_key(cube: Any, view: Any, cell_ref: dict) -> str:
    """Convert a view-based cell_ref dict to a pipe-joined addr_key string.

    The remote server uses cube_id + addr_key (pipe-joined item IDs in dimension
    order) while the Python API uses view_id + cell_ref dict with row_key/col_key.
    This helper reconstructs the full address from the view's dimension layout.
    """
    kind = cell_ref.get("kind", "ids")
    if kind == "ids":
        row_key = list(cell_ref.get("row_key", []))
        col_key = list(cell_ref.get("col_key", []))
        channel = cell_ref.get("channel")

        # Interleave row/col items according to the cube's dimension order
        row_dim_ids = view.row_dim_ids if hasattr(view, "row_dim_ids") else []
        col_dim_ids = view.col_dim_ids if hasattr(view, "col_dim_ids") else []
        page_dim_ids = view.page_dim_ids if hasattr(view, "page_dim_ids") else []

        addr_map: dict[str, str] = {}
        for dim_id, item_id in zip(row_dim_ids, row_key):
            addr_map[dim_id] = str(item_id)
        for dim_id, item_id in zip(col_dim_ids, col_key):
            addr_map[dim_id] = str(item_id)
        for dim_id in page_dim_ids:
            if dim_id not in addr_map:
                addr_map[dim_id] = ""

        # Build addr in cube dimension order, inserting @ channel
        parts: list[str] = []
        for dim_id in cube.dimension_ids:
            if dim_id == "@":
                channel_name = channel if channel else "value"
                parts.append(CHANNEL_TO_AT_ID.get(channel_name, channel_name))
            else:
                parts.append(addr_map.get(dim_id, ""))
        return "|".join(parts)
    elif kind == "name":
        # Resolve names to IDs via workspace dimensions
        ws_dims = {d.id: d for d in cube.dimension_ids}
        row_names = cell_ref.get("row_names", [])
        col_names = cell_ref.get("col_names", [])
        # For name-based refs, we need the workspace to resolve
        # Fall back to joining names directly (server may handle)
        parts = list(row_names) + list(col_names)
        return "|".join(str(p) for p in parts)
    else:
        # idx or other — best effort
        return "|".join(str(v) for v in cell_ref.values() if isinstance(v, (str, int)))


class RemoteEngine:
    """Drop-in replacement for lib_openm.api.Engine.

    Identical public API. All workspace/data operations delegated to remote server.
    State machine, generation, and GUI flags are Python-side.
    Workspace property is cached and invalidated on mutation responses.
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        endpoint: str,
        event_publisher: Any = None,
        connection: Any = None,
    ) -> None:
        self._endpoint = endpoint
        if connection is not None:
            self._conn = connection
            self._shared_conn = True
        else:
            self._conn = Connection(endpoint)
            self._conn.connect()
            self._shared_conn = False

        # Handshake: validate protocol compatibility before any calls.
        info = self._conn.call(RpcMethod.HELLO)
        self._server_info = info
        server_major = int(info.get("protocol_version", "0.0.0").split(".")[0])
        if server_major != 1:
            raise RemoteEngineError(
                f"Protocol version mismatch: client expects 1.x, "
                f"server reports {info.get('protocol_version')}"
            )

        self._event_publisher = event_publisher
        self._state_machine = _EngineStateMachine(
            event_publisher=event_publisher, engine_facade=self
        )
        self._gui_ready = False
        self._calculating = False
        self._generation = 0
        self._cancel_requested = False
        self._dep_tracking_enabled = True
        self._batch_invalidation_pending = False
        self._cached_workspace: Workspace | None = None
        self._local_ws: Workspace | None = workspace

        # Load initial workspace into the server.
        self._suppress_events = True
        self.replace_workspace(workspace)
        self._cached_workspace = workspace
        self._suppress_events = False

    # ------------------------------------------------------------------
    # Workspace management
    # ------------------------------------------------------------------

    def replace_workspace(self, ws: Workspace) -> None:
        import tempfile
        from pathlib import Path

        data = workspace_to_msgpack_dict(ws)
        payload = _msgpack.packb(data, use_bin_type=True)

        # The server's load_workspace_msgpack handler currently expects a
        # file path string, not raw bytes. Write to a temp file and send the path.
        # This will be updated to send raw bytes inline once the server handler
        # is modified to accept bytes directly.
        with tempfile.NamedTemporaryFile(
            suffix=".msgpack", delete=False
        ) as f:
            f.write(payload)
            tmp_path = f.name

        try:
            self._conn.call(RpcMethod.LOAD_WORKSPACE_MSGPACK, tmp_path)
        finally:
            try:
                Path(tmp_path).unlink()
            except OSError:
                pass

        # Cache the local workspace object. The server's GET_WORKSPACE may not
        # return views (the remote server only tracks dimensions/cubes/rules),
        # so re-fetching would lose view metadata. We just sent the full
        # workspace to the server, so the local copy is authoritative.
        self._local_ws = ws
        self._cached_workspace = ws

    @property
    def workspace(self) -> Workspace:
        if self._cached_workspace is None:
            result = self._conn.call(RpcMethod.GET_WORKSPACE)
            ws_from_server = _dto_to_workspace(result)
            # The server may not return views; merge from local copy if missing.
            if not ws_from_server.views and self._local_ws is not None:
                ws_from_server.views = self._local_ws.views
                ws_from_server.views_order = self._local_ws.views_order
                ws_from_server.saved_default_view_id = self._local_ws.saved_default_view_id
            # Restore dimension item order from the local copy. The server may
            # serialize dimension items in a different order (e.g., sorted), which
            # breaks page chip dropdowns and the @ dimension layout.
            if self._local_ws is not None:
                self._restore_dimension_item_order(ws_from_server, self._local_ws)
            self._cached_workspace = ws_from_server
        return self._cached_workspace

    def _restore_dimension_item_order(self, server_ws: Workspace, local_ws: Workspace) -> None:
        """Reorder items in server_ws dimensions to match local_ws order.

        Items that exist in both are placed in the order they appear in the local
        copy. Any items present only on the server are appended at the end in
        server order. Dimensions that exist only on the server are left unchanged.
        """
        for dim_id, server_dim in server_ws.dimensions.items():
            local_dim = local_ws.dimensions.get(dim_id)
            if local_dim is None:
                continue
            local_order = {it.id: i for i, it in enumerate(local_dim.items)}
            server_items_by_id = {it.id: it for it in server_dim.items}
            ordered: list[Any] = []
            remainder: list[Any] = []
            for it in server_dim.items:
                if it.id in local_order:
                    ordered.append(it)
                else:
                    remainder.append(it)
            if not ordered:
                continue
            ordered.sort(key=lambda it: local_order.get(it.id, len(local_order)))
            # Avoid duplicates while preserving server-only additions.
            seen = set()
            new_items: list[Any] = []
            for it in ordered + remainder:
                if it.id in seen:
                    continue
                seen.add(it.id)
                new_items.append(it)
            server_dim.items = new_items

    @property
    def _ws(self) -> Workspace:
        return self.workspace

    def _invalidate_workspace_cache(self) -> None:
        if self._batch_invalidation_pending:
            return
        self._cached_workspace = None

    def _sync_dim_to_local_ws(self, dim) -> None:
        if self._local_ws is not None:
            self._local_ws.dimensions[dim.id] = dim

    def _sync_cube_to_local_ws(self, cube) -> None:
        if self._local_ws is not None:
            self._local_ws.cubes[cube.id] = cube

    def _sync_rule_to_local_ws(self, rule) -> None:
        if self._local_ws is not None:
            self._local_ws.rules[rule.id] = rule

    def _delete_rule_from_local_ws(self, rule_id: str) -> None:
        if self._local_ws is not None:
            self._local_ws.delete_rule(rule_id)
        if self._cached_workspace is not None:
            self._cached_workspace.delete_rule(rule_id)

    @contextmanager
    def batch_cache_scope(self):
        old = self._batch_invalidation_pending
        self._batch_invalidation_pending = True
        try:
            yield
        finally:
            self._batch_invalidation_pending = old
            self._cached_workspace = None

    # ------------------------------------------------------------------
    # Engine lifecycle / state machine
    # ------------------------------------------------------------------

    @property
    def undo_manager(self) -> _RemoteUndoManager:
        return _RemoteUndoManager(self)

    @property
    def generation(self) -> int:
        return self._generation

    def bump_generation(self) -> int:
        self._generation += 1
        return self._generation

    @property
    def is_gui_ready(self) -> bool:
        return self._gui_ready

    @property
    def is_calculating(self) -> bool:
        return self._calculating

    def read_engine_state(self) -> EngineState:
        return self._state_machine.get_engine_state()

    def read_engine_diagnostics(self) -> dict[str, Any]:
        return self._state_machine.get_diagnostics()

    def execute_serialized_command(
        self,
        command_id: str,
        allowed_states: set,
        target_state: EngineState,
        body: Callable[[], Any],
        *,
        is_recovery: bool = False,
        next_state: EngineState | None = None,
        next_state_reason: str | None = None,
    ) -> Any:
        return self._state_machine.execute_serialized_command(
            command_id,
            allowed_states,
            target_state,
            body,
            is_recovery=is_recovery,
            next_state=next_state,
            next_state_reason=next_state_reason,
        )

    def transition_to_state(
        self, new_state: EngineState, *, reason: str | None = None
    ) -> None:
        self._state_machine.transition_to(new_state, reason=reason)

    def shutdown_engine(self) -> None:
        self._state_machine.shutdown()
        if not getattr(self, "_shared_conn", False):
            self._conn.close()
        launcher = getattr(self, "_launcher", None)
        if launcher is not None:
            launcher.stop()

    def _engine_version(self) -> dict[str, Any]:
        """Return server version info (from the hello handshake)."""
        return self._server_info

    def engine_info(self) -> dict[str, Any]:
        return {
            "type": "remote",
            "engine_name": self._server_info.get("engine_name", "unknown"),
            "version": self._server_info.get("engine_version", "unknown"),
            "engine_version": self._server_info.get("engine_version", "unknown"),
            "protocol_version": self._server_info.get("protocol_version", "0.0.0"),
            "capabilities": self._server_info.get("capabilities", []),
            "connected": self._conn.is_connected,
        }

    def supports(self, capability: str) -> bool:
        return capability in self._server_info.get("capabilities", [])

    # --- Cancel flags ---

    def request_cancel_operation(self) -> None:
        self._state_machine.request_cancel()

    def is_cancel_operation_requested(self) -> bool:
        return self._state_machine.is_cancel_requested()

    def request_cancel(self) -> None:
        self._cancel_requested = True

    def is_cancel_requested(self) -> bool:
        return self._cancel_requested

    def reset_cancel(self) -> None:
        self._cancel_requested = False

    # --- Dependency tracking ---

    def enable_dependency_tracking(self, enabled: bool = True) -> None:
        self._dep_tracking_enabled = enabled
        try:
            self._conn.call(RpcMethod.SET_DEP_TRACKING, enabled=enabled)
        except Exception:
            _log.debug("SET_DEP_TRACKING not supported by server, ignoring")

    @contextmanager
    def dependency_tracking_disabled(self):
        old = getattr(self, "_dep_tracking_disabled", False)
        self._dep_tracking_disabled = True
        try:
            yield
        finally:
            self._dep_tracking_disabled = old

    def is_dependency_tracking_enabled(self) -> bool:
        return self._dep_tracking_enabled and not getattr(
            self, "_dep_tracking_disabled", False
        )

    # --- Multithread recompute (not supported in remote mode) ---

    def enable_multithread_recompute(self, *args, **kwargs) -> None:
        raise NotImplementedError(
            "enable_multithread_recompute is not supported in remote mode"
        )

    def multithread_recompute_config(self) -> dict[str, Any]:
        return {
            "enabled": False,
            "workers": 0,
            "threshold": 0,
            "batch_size": 0,
            "reuse_pool": False,
        }

    # ------------------------------------------------------------------
    # Dimension methods
    # ------------------------------------------------------------------

    def create_dimension(self, name: str, dim_type: str = "set") -> Any:
        result = self._conn.call(
            RpcMethod.CREATE_DIMENSION, name=name, dim_type=dim_type
        )
        publish_events(self, result.get("events", []))
        self._invalidate_workspace_cache()
        dim = _dto_to_dimension(d=result["data"])
        self._sync_dim_to_local_ws(dim)
        return dim

    def create_dimension_item(
        self, dim_id: str, name: str, position: str = "append"
    ) -> Any:
        result = self._conn.call(
            RpcMethod.CREATE_DIMENSION_ITEM,
            dim_id=dim_id,
            name=name,
            position=position,
        )
        publish_events(self, result.get("events", []))
        self._invalidate_workspace_cache()
        return result["data"]

    def rename_dimension(self, dim_id: str, new_name: str) -> None:
        result = self._conn.call(
            RpcMethod.RENAME_DIMENSION, dim_id=dim_id, new_name=new_name
        )
        publish_events(self, result.get("events", []))
        self._invalidate_workspace_cache()

    def rename_dimension_item(
        self, dim_id: str, item_id: str, new_name: str
    ) -> None:
        result = self._conn.call(
            RpcMethod.RENAME_DIMENSION_ITEM,
            dim_id=dim_id,
            item_id=item_id,
            new_name=new_name,
        )
        publish_events(self, result.get("events", []))
        self._invalidate_workspace_cache()

    def delete_dimension(self, dim_id: str) -> None:
        result = self._conn.call(RpcMethod.DELETE_DIMENSION, dim_id=dim_id)
        publish_events(self, result.get("events", []))
        self._invalidate_workspace_cache()

    def delete_dimension_items(self, dim_id: str, item_ids: list[str]) -> None:
        result = self._conn.call(
            RpcMethod.DELETE_DIMENSION_ITEMS, dim_id=dim_id, item_ids=item_ids
        )
        publish_events(self, result.get("events", []))
        self._invalidate_workspace_cache()

    def set_dimension_item_order(self, dim_id: str, item_ids: list[str]) -> None:
        result = self._conn.call(
            RpcMethod.SET_DIMENSION_ITEM_ORDER, dim_id=dim_id, item_ids=item_ids
        )
        publish_events(self, result.get("events", []))
        self._invalidate_workspace_cache()

    def require_dimension_by_id(self, dim_id: str) -> Any:
        ws = self.workspace
        dim = ws.dimensions.get(dim_id)
        if dim is None:
            raise KeyError(f"dimension '{dim_id}' not found")
        return dim

    def dimension_outline_for_dim(self, dim_id: str) -> Any:
        result = self._conn.call(RpcMethod.DIMENSION_OUTLINE, dim_id=dim_id)
        if not result:
            return []
        return _deserialize_outline_tree(result)

    # ------------------------------------------------------------------
    # Cube methods
    # ------------------------------------------------------------------

    def create_cube(self, name: str, dimension_ids: list[str]) -> Any:
        # Auto-add @ dimension at the start if not present, matching
        # Python Engine's Cube.create behavior.
        dim_ids = list(dimension_ids)
        if "@" not in dim_ids:
            dim_ids.insert(0, "@")
        result = self._conn.call(
            RpcMethod.CREATE_CUBE, name=name, dimension_ids=dim_ids
        )
        publish_events(self, result.get("events", []))
        self._invalidate_workspace_cache()
        cube = _dto_to_cube(d=result["data"])
        self._sync_cube_to_local_ws(cube)
        return cube

    def rename_cube(self, cube_id: str, new_name: str) -> None:
        result = self._conn.call(
            RpcMethod.RENAME_CUBE, cube_id=cube_id, new_name=new_name
        )
        publish_events(self, result.get("events", []))
        self._invalidate_workspace_cache()

    def delete_cube(self, cube_id: str) -> None:
        result = self._conn.call(RpcMethod.DELETE_CUBE, cube_id=cube_id)
        publish_events(self, result.get("events", []))
        self._invalidate_workspace_cache()

    def attach_dimension_to_cube(self, cube_id: str, dim_id: str) -> None:
        result = self._conn.call(
            RpcMethod.ATTACH_DIMENSION, cube_id=cube_id, dim_id=dim_id
        )
        publish_events(self, result.get("events", []))
        self._invalidate_workspace_cache()

    def detach_dimension_from_cube(self, cube_id: str, dim_id: str) -> None:
        result = self._conn.call(
            RpcMethod.DETACH_DIMENSION, cube_id=cube_id, dim_id=dim_id
        )
        publish_events(self, result.get("events", []))
        self._invalidate_workspace_cache()

    def find_cube_by_id(self, cube_id: str) -> Any:
        ws = self.workspace
        return ws.cubes.get(cube_id)

    def require_cube_by_id(self, cube_id: str) -> Any:
        result = self.find_cube_by_id(cube_id)
        if result is None:
            raise KeyError(f"cube '{cube_id}' not found")
        return result

    def find_cube_by_name(self, name: str) -> Any:
        result = self._conn.call(RpcMethod.FIND_CUBE_BY_NAME, name=name)
        return _dto_to_cube(d=result) if result else None

    def list_cube_ids(self) -> list[str]:
        result = self._conn.call(RpcMethod.LIST_CUBE_IDS)
        return [str(x) for x in result] if result else []

    # ------------------------------------------------------------------
    # Rule methods
    # ------------------------------------------------------------------

    def set_rule(
        self,
        cube_id: str,
        targets: list[tuple[str, str]],
        expression: str,
        is_anchored: bool = False,
        max_cells: int | None = None,
    ) -> None:
        result = self._conn.call(
            RpcMethod.SET_RULE,
            cube_id=cube_id,
            targets=targets,
            expression=expression,
            is_anchored=is_anchored,
        )
        publish_events(self, result.get("events", []))
        self._invalidate_workspace_cache()

    def update_rule(self, rule_id: str, expression: str) -> None:
        result = self._conn.call(
            RpcMethod.UPDATE_RULE, rule_id=rule_id, expression=expression
        )
        publish_events(self, result.get("events", []))
        self._invalidate_workspace_cache()

    def update_rule_full(
        self,
        rule_id: str,
        targets: list[tuple[str, str]],
        expression: str,
        is_anchored: bool = False,
    ) -> None:
        result = self._conn.call(
            RpcMethod.UPDATE_RULE_FULL,
            rule_id=rule_id,
            expression=expression,
            targets=[list(t) for t in targets],
            is_anchored=is_anchored,
        )
        publish_events(self, result.get("events", []))
        self._invalidate_workspace_cache()

    def delete_rule(self, rule_id: str) -> bool:
        result = self._conn.call(RpcMethod.DELETE_RULE, rule_id=rule_id)
        publish_events(self, result.get("events", []))
        self._delete_rule_from_local_ws(rule_id)
        self._invalidate_workspace_cache()
        return True

    def set_rule_order(self, rule_ids: list[str]) -> None:
        result = self._conn.call(RpcMethod.SET_RULE_ORDER, rule_ids=rule_ids)
        publish_events(self, result.get("events", []))
        self._invalidate_workspace_cache()

    def apply_rule_batch(self, rules: list[dict]) -> Any:
        result = self._conn.call(RpcMethod.APPLY_RULE_BATCH, rules=rules)
        publish_events(self, result.get("events", [])) if isinstance(result, dict) else None
        self._invalidate_workspace_cache()
        return result

    def find_rule(self, cube_id: str, addr: tuple, dim_ids: list[str]) -> Any:
        addr_list = list(addr)
        result = self._conn.call(
            RpcMethod.FIND_RULE, cube_id=cube_id, addr=addr_list
        )
        return _dto_to_rule(result) if result else None

    def find_anchored_rule(self, cube_id: str, addr: tuple) -> Any:
        result = self._conn.call(
            RpcMethod.FIND_ANCHORED_RULE, cube_id=cube_id, addr=list(addr)
        )
        return _dto_to_rule(result) if result else None

    def delete_rule_anchored(self, view_id: str, cell_ref: dict) -> None:
        cube_id, addr = self._cell_ref_to_cube_addr(view_id, cell_ref)
        result = self._conn.call(
            RpcMethod.DELETE_RULE_ANCHORED, cube_id=cube_id, addr=list(addr)
        )
        publish_events(self, result.get("events", [])) if isinstance(result, dict) else None
        self._invalidate_workspace_cache()

    def set_rule_anchored(self, view_id: str, cell_ref: dict, expression: str) -> None:
        cube_id, addr = self._cell_ref_to_cube_addr(view_id, cell_ref)
        result = self._conn.call(
            RpcMethod.SET_RULE_ANCHORED, cube_id=cube_id, addr=list(addr), expression=expression
        )
        publish_events(self, result.get("events", [])) if isinstance(result, dict) else None
        self._invalidate_workspace_cache()

    def set_rule_anchored_by_addr(
        self, cube_id: str, addr: tuple, expression: str
    ) -> None:
        result = self._conn.call(
            RpcMethod.SET_RULE_ANCHORED_BY_ADDR, cube_id=cube_id, addr=list(addr), expression=expression
        )
        publish_events(self, result.get("events", [])) if isinstance(result, dict) else None
        self._invalidate_workspace_cache()

    def update_cell_rule(self, view_id: str, cell_ref: dict, expression: str) -> None:
        cube_id, addr = self._cell_ref_to_cube_addr(view_id, cell_ref)
        rule = self.find_anchored_rule(cube_id, addr)
        if rule is None:
            self.set_rule_anchored(view_id, cell_ref, expression)
            return
        result = self._conn.call(
            RpcMethod.UPDATE_CELL_RULE, rule_id=rule["id"], expression=expression
        )
        publish_events(self, result.get("events", [])) if isinstance(result, dict) else None
        self._invalidate_workspace_cache()

    def rule_counts_for_cube(self, cube_id: str) -> dict:
        return self._conn.call(RpcMethod.RULE_COUNTS_FOR_CUBE, cube_id=cube_id)

    # ------------------------------------------------------------------
    # Cell methods
    # ------------------------------------------------------------------

    def _cell_ref_to_cube_addr(self, view_id: str, cell_ref: dict) -> tuple[str, tuple]:
        """Resolve view_id + cell_ref to (cube_id, addr_tuple) in cube dimension order."""
        ws = self.workspace
        view = ws.views.get(view_id)
        if view is None:
            raise KeyError(f"View {view_id} not found")
        cube = ws.cubes.get(view.cube_id)
        if cube is None:
            raise KeyError(f"Cube {view.cube_id} not found")
        addr_key = _cell_ref_to_addr_key(cube, view, cell_ref)
        addr = tuple(addr_key.split("|"))
        return view.cube_id, addr

    def get_cell_by_addr(self, cube: Any, addr: tuple) -> Any:
        cube_id = cube.id if hasattr(cube, "id") else cube
        addr_key = "|".join(str(a) for a in addr)
        result = self._conn.call(
            RpcMethod.EVALUATE_CELL, cube_id, addr_key
        )
        value, _ = _deserialize_value(result)
        return value

    _get_cell_by_addr = get_cell_by_addr

    def get_cells_batch(self, cube: Any, addrs: list[tuple]) -> list:
        cube_id = cube.id if hasattr(cube, "id") else cube
        addr_keys = ["|".join(str(a) for a in addr) for addr in addrs]
        result = self._conn.call(
            RpcMethod.EVALUATE_CELLS, cube_id, addr_keys
        )
        return [_dto_to_cell_value(v) for v in result] if result else []

    def set_cell_hardvalue(self, view_id: str, cell_ref: dict, value: Any) -> None:
        # Resolve view_id + cell_ref to cube_id + addr_key
        ws = self.workspace
        view = ws.views.get(view_id)
        if view is None:
            raise KeyError(f"View {view_id} not found")
        cube = ws.cubes.get(view.cube_id)
        if cube is None:
            raise KeyError(f"Cube {view.cube_id} not found")
        addr_key = _cell_ref_to_addr_key(cube, view, cell_ref)
        result = self._conn.call(
            RpcMethod.SET_CELL_HARDVALUE,
            view.cube_id, addr_key,
            value=value,
        )
        publish_events(self, result.get("events", []))
        # Cell value changes don't affect workspace structure.

    def set_cell_hardvalue_by_addr(
        self, cube_id: str, addr: tuple, value: Any
    ) -> None:
        addr_key = "|".join(str(a) for a in addr)
        result = self._conn.call(
            RpcMethod.SET_CELL_HARDVALUE_BY_ADDR,
            cube_id, addr_key,
            value=value,
        )
        publish_events(self, result.get("events", []))
        # Cell value changes don't affect workspace structure.

    def clear_cell_hardvalue_by_addr(
        self, cube_id: str, addr: tuple
    ) -> None:
        addr_key = "|".join(str(a) for a in addr)
        result = self._conn.call(
            RpcMethod.CLEAR_CELL_HARDVALUE,
            cube_id, addr_key,
        )
        publish_events(self, result.get("events", []))
        # Cell value changes don't affect workspace structure.

    def clear_cell_hardvalue(self, view_id: str, cell_ref: dict) -> None:
        ws = self.workspace
        view = ws.views.get(view_id)
        if view is None:
            raise KeyError(f"View {view_id} not found")
        cube = ws.cubes.get(view.cube_id)
        if cube is None:
            raise KeyError(f"Cube {view.cube_id} not found")
        addr_key = _cell_ref_to_addr_key(cube, view, cell_ref)
        result = self._conn.call(
            RpcMethod.CLEAR_CELL_HARDVALUE,
            view.cube_id, addr_key,
        )
        publish_events(self, result.get("events", []))
        # Cell value changes don't affect workspace structure.

    def get_cell_value(self, view_id: str, cell_ref: dict) -> Any:
        ws = self.workspace
        view = ws.views.get(view_id)
        if view is None:
            raise KeyError(f"View {view_id} not found")
        cube = ws.cubes.get(view.cube_id)
        if cube is None:
            raise KeyError(f"Cube {view.cube_id} not found")
        addr_key = _cell_ref_to_addr_key(cube, view, cell_ref)
        result = self._conn.call(
            RpcMethod.GET_CELL_VALUE,
            cube_id=view.cube_id, addr_key=addr_key,
        )
        return _dto_to_cell_value(result) if result else _empty_cell_value(view.cube_id)

    def get_cached_cell_value_by_addr(self, cube, addr: tuple) -> Any:
        cube_id = cube.id if hasattr(cube, "id") else str(cube)
        cube_obj = cube if hasattr(cube, "id") else self.require_cube_by_id(cube_id)
        from lib_openm._engine_core import _normalize_addr_for_cube

        full_addr = _normalize_addr_for_cube(cube_obj, addr)
        addr_key = "|".join(str(a) for a in full_addr)
        result = self._conn.call(RpcMethod.GET_CACHED_CELL_VALUE, cube_id=cube_id, addr_key=addr_key)
        if result is not None:
            cv = _dto_to_cell_value(result)
            return cv.value if cv is not None else None
        # The remote server's get_cached_cell_value only returns hardcoded values.
        # Fall back to evaluate_cell for rule-computed cells so the grid shows data.
        eval_result = self._conn.call(RpcMethod.EVALUATE_CELL, cube_id, addr_key)
        if eval_result is None:
            return None
        value, _ = _deserialize_value(eval_result)
        return value

    def batch_set_cell_data(
        self,
        view_id: str = None,
        cells: list = None,
        cube_id: str = None,
        values: dict | None = None,
        rules: dict | None = None,
    ) -> None:
        from lib_openm._engine_core import _normalize_addr_for_cube
        # Support both the view_id/cells API and the cube_id/values/rules API
        if cube_id is not None:
            cube = self.require_cube_by_id(cube_id)
            values_map = {}
            if values:
                for addr, val in values.items():
                    full_addr = _normalize_addr_for_cube(cube, addr)
                    addr_key = "|".join(str(a) for a in full_addr)
                    values_map[addr_key] = val
            rules_map = {}
            if rules:
                for addr, expr in rules.items():
                    full_addr = _normalize_addr_for_cube(cube, addr)
                    addr_key = "|".join(str(a) for a in full_addr)
                    rules_map[addr_key] = expr
            result = self._conn.call(
                RpcMethod.BATCH_SET_CELL_DATA,
                cube_id=cube_id, values=values_map, rules=rules_map,
            )
            publish_events(self, result.get("events", []))
            self._invalidate_workspace_cache()
        elif view_id is not None and cells is not None:
            # Legacy view_id/cells API — convert to addr-based calls
            view = self.require_view_by_id(view_id)
            cube_id = view.cube_id
            values_map = {}
            for cell in cells:
                if isinstance(cell, dict) and "addr_key" in cell:
                    values_map[cell["addr_key"]] = cell.get("value")
            result = self._conn.call(
                RpcMethod.BATCH_SET_CELL_DATA,
                cube_id=cube_id, values=values_map, rules={},
            )
            publish_events(self, result.get("events", []))
            self._invalidate_workspace_cache()

    def set_range(self, view_id: str, top: int, left: int, values: list[list[Any]]) -> None:
        result = self._conn.call(
            RpcMethod.SET_RANGE,
            view_id=view_id, top=top, left=left, values=values,
        )
        publish_events(self, result.get("events", []))
        self._invalidate_workspace_cache()

    def get_range(self, view_id: str, top: int, left: int, bottom: int, right: int) -> list[list[Any]]:
        result = self._conn.call(
            RpcMethod.GET_RANGE,
            view_id=view_id, top=top, left=left, bottom=bottom, right=right,
        )
        return result if result else []

    def cell_value_for_view_rc(self, view_id: str, row: int, col: int) -> Any:
        result = self._conn.call(
            RpcMethod.CELL_VALUE_FOR_VIEW_RC,
            view_id=view_id, row=row, col=col,
        )
        if result is None:
            from lib_openm._engine_core import CellValue, Explain, CellError
            return CellValue(value=None, explain=Explain(source="empty", cube_id="", addr=()))
        # Build a CellValue-like object from the DTO
        from lib_openm._engine_core import CellValue, Explain, CellError
        source = result.get("source", "empty")
        val_type = result.get("type", "null")
        raw_val = result.get("value")
        if val_type == "number":
            value = raw_val
        elif val_type == "text":
            value = raw_val
        elif val_type == "error":
            value = CellError(raw_val) if raw_val else None
        else:
            value = None
        return CellValue(
            value=value,
            explain=Explain(
                source=source,
                cube_id=result.get("cube_id", ""),
                addr=tuple(result.get("addr_key", "").split("|")) if result.get("addr_key") else (),
                rule_body=result.get("rule_expression"),
            ),
        )

    def resolve_cell_meta(self, cube, addr: tuple) -> Any:
        from lib_openm._engine_core import CellMeta, _normalize_addr_for_cube
        cube_id = cube.id if hasattr(cube, "id") else str(cube)
        cube_obj = cube if hasattr(cube, "id") else self.require_cube_by_id(cube_id)
        full_addr = _normalize_addr_for_cube(cube_obj, addr)
        addr_key = "|".join(str(a) for a in full_addr)
        result = self._conn.call(RpcMethod.RESOLVE_CELL_META, cube_id=cube_id, addr_key=addr_key)
        if result is None:
            return CellMeta(source="empty", has_rule=False, is_override=False, is_dirty=False, is_tracked=False, error=None)
        source = result.get("source", "empty")
        has_rule = bool(result.get("has_rule", False))
        # The remote server has no Python-style dependency graph, so it always
        # reports is_tracked=false.  For rule cells this would trigger
        # SnapshotInvariantError in the viewport snapshot path.  Since the
        # server evaluates rules on demand, rule cells are always "tracked".
        is_tracked = bool(result.get("is_tracked", False)) or has_rule
        return CellMeta(
            source=source,
            has_rule=has_rule,
            is_override=bool(result.get("is_override", False)),
            is_dirty=bool(result.get("is_dirty", False)),
            is_tracked=is_tracked,
            error=result.get("error"),
        )

    def addr_to_cell_ref(self, cube_id: str, addr: tuple) -> Any:
        from lib_openm._engine_core import _normalize_addr_for_cube
        cube = self.require_cube_by_id(cube_id)
        full_addr = _normalize_addr_for_cube(cube, addr)
        addr_key = "|".join(str(a) for a in full_addr)
        result = self._conn.call(RpcMethod.ADDR_TO_CELL_REF, cube_id=cube_id, addr_key=addr_key)
        return result if result else {}

    # ------------------------------------------------------------------
    # View methods
    # ------------------------------------------------------------------

    def create_view(
        self,
        name: str,
        cube_id: str,
        row_dim_id: str = "",
        col_dim_id: str = "",
        page_dim_ids: list[str] | None = None,
        layout: Any = None,
    ) -> Any:
        row_dim_ids = [row_dim_id] if row_dim_id else []
        col_dim_ids = [col_dim_id] if col_dim_id else []
        result = self._conn.call(
            RpcMethod.CREATE_VIEW,
            name=name,
            cube_id=cube_id,
            row_dim_ids=row_dim_ids,
            col_dim_ids=col_dim_ids,
        )
        publish_events(self, result.get("events", []))
        view = _dto_to_view(d=result["data"])
        if self._local_ws is not None:
            self._local_ws.views[view.id] = view
            if view.id not in self._local_ws.views_order:
                self._local_ws.views_order.append(view.id)
        self._invalidate_workspace_cache()
        return view

    def create_default_view_for_cube(self, cube_id: str) -> Any:
        result = self._conn.call(
            RpcMethod.CREATE_DEFAULT_VIEW, cube_id=cube_id
        )
        publish_events(self, result.get("events", []))
        view = _dto_to_view(d=result["data"])
        if self._local_ws is not None:
            self._local_ws.views[view.id] = view
            if view.id not in self._local_ws.views_order:
                self._local_ws.views_order.append(view.id)
        self._invalidate_workspace_cache()
        return view.id

    def set_view_axes(self, view_id: str, row_dimension_id: str, col_dimension_id: str) -> None:
        result = self._conn.call(
            RpcMethod.SET_VIEW_AXES,
            view_id=view_id, row_dimension_id=row_dimension_id, col_dimension_id=col_dimension_id,
        )
        publish_events(self, result.get("events", []))
        if self._local_ws is not None and view_id in self._local_ws.views:
            view = self._local_ws.views[view_id]
            view.row_dim_ids = [row_dimension_id] if row_dimension_id else []
            view.col_dim_ids = [col_dimension_id] if col_dimension_id else []
        self._invalidate_workspace_cache()

    def set_view_layout(self, view_id: str, layout: Any = None, **kwargs) -> None:
        row_dim_ids = kwargs.get("row_dim_ids", [])
        col_dim_ids = kwargs.get("col_dim_ids", [])
        page_dim_ids = kwargs.get("page_dim_ids", [])
        if layout is not None and hasattr(layout, "row_dim_ids"):
            row_dim_ids = layout.row_dim_ids
            col_dim_ids = layout.col_dim_ids
            page_dim_ids = getattr(layout, "page_dim_ids", [])
        result = self._conn.call(
            RpcMethod.SET_VIEW_LAYOUT,
            view_id=view_id,
            row_dim_ids=row_dim_ids,
            col_dim_ids=col_dim_ids,
            page_dim_ids=page_dim_ids,
        )
        publish_events(self, result.get("events", []))
        if self._local_ws is not None and view_id in self._local_ws.views:
            view = self._local_ws.views[view_id]
            view.row_dim_ids = list(row_dim_ids)
            view.col_dim_ids = list(col_dim_ids)
            view.page_dim_ids = list(page_dim_ids)
        self._invalidate_workspace_cache()

    def move_view_dimension(self, view_id: str, dim_id: str, dest: str, index: int | None = None) -> None:
        kwargs = dict(view_id=view_id, dim_id=dim_id, dest=dest)
        if index is not None:
            kwargs["index"] = index
        result = self._conn.call(RpcMethod.MOVE_VIEW_DIMENSION, **kwargs)
        publish_events(self, result.get("events", []))
        # Update _local_ws view to stay in sync with server state
        if self._local_ws is not None:
            view = self._local_ws.views.get(view_id)
            if view is not None:
                # Remove dim from all axes
                for axis in ("row_dim_ids", "col_dim_ids", "page_dim_ids"):
                    lst = getattr(view, axis, [])
                    if dim_id in lst:
                        lst.remove(dim_id)
                # Insert into destination
                if dest == "row":
                    view.row_dim_ids.insert(index if index is not None and index <= len(view.row_dim_ids) else len(view.row_dim_ids), dim_id)
                elif dest == "col":
                    view.col_dim_ids.insert(index if index is not None and index <= len(view.col_dim_ids) else len(view.col_dim_ids), dim_id)
                elif dest == "page":
                    view.page_dim_ids.insert(index if index is not None and index <= len(view.page_dim_ids) else len(view.page_dim_ids), dim_id)
        self._invalidate_workspace_cache()

    def list_views(self) -> list:
        result = self._conn.call(RpcMethod.LIST_VIEWS)
        return [_dto_to_view(d=v) for v in result] if result else []

    def view_row_keys(self, view_id: str) -> list:
        result = self._conn.call(RpcMethod.VIEW_ROW_KEYS, view_id=view_id)
        return [tuple(str(x) for x in row) if isinstance(row, (list, tuple)) else (str(row),) for row in result] if result else []

    def view_col_keys(self, view_id: str) -> list:
        result = self._conn.call(RpcMethod.VIEW_COL_KEYS, view_id=view_id)
        return [tuple(str(x) for x in col) if isinstance(col, (list, tuple)) else (str(col),) for col in result] if result else []

    def view_row_items(self, view_id: str) -> list:
        result = self._conn.call(RpcMethod.VIEW_ROW_ITEMS, view_id=view_id)
        return [_dto_to_dimension_item(str(item.get("id", "")), item) for item in result] if result else []

    def view_col_items(self, view_id: str) -> list:
        result = self._conn.call(RpcMethod.VIEW_COL_ITEMS, view_id=view_id)
        return [_dto_to_dimension_item(str(item.get("id", "")), item) for item in result] if result else []

    def view_row_dim_ids(self, view_id: str) -> list:
        result = self._conn.call(RpcMethod.VIEW_ROW_DIM_IDS, view_id=view_id)
        return [str(x) for x in result] if result else []

    def view_col_dim_ids(self, view_id: str) -> list:
        result = self._conn.call(RpcMethod.VIEW_COL_DIM_IDS, view_id=view_id)
        return [str(x) for x in result] if result else []

    def view_page_dim_ids(self, view_id: str) -> list:
        result = self._conn.call(RpcMethod.VIEW_PAGE_DIM_IDS, view_id=view_id)
        return [str(x) for x in result] if result else []

    def view_page_dimensions(self, view_id: str) -> list:
        result = self._conn.call(RpcMethod.VIEW_PAGE_DIMENSIONS, view_id=view_id)
        return [_dto_to_dimension(d=dim) for dim in result] if result else []

    def view_col_count(self, view_id: str) -> int:
        result = self._conn.call(RpcMethod.VIEW_COL_COUNT, view_id=view_id)
        return int(result) if result is not None else 0

    def view_col_header(self, view_id: str, section: int) -> Any:
        result = self._conn.call(RpcMethod.VIEW_COL_HEADER, view_id=view_id, col_index=section)
        return str(result) if result is not None else ""

    def resolve_default_view_id_by_cube(self, cube_id: str) -> str:
        result = self._conn.call(RpcMethod.RESOLVE_DEFAULT_VIEW, cube_id=cube_id)
        return str(result) if result else None

    def require_view_by_id(self, view_id: str) -> Any:
        ws = self.workspace
        view = ws.views.get(view_id)
        if view is None:
            raise KeyError(f"View {view_id} not found")
        return view

    # ------------------------------------------------------------------
    # Group/outline methods
    # ------------------------------------------------------------------

    def create_group(
        self,
        dim_id: str,
        label: str,
        parent_group_id: str | None = None,
        child_item_ids: list[str] | None = None,
    ) -> str:
        kw: dict[str, Any] = {
            "dim_id": dim_id,
            "label": label,
            "child_item_ids": child_item_ids or [],
        }
        if parent_group_id is not None:
            kw["parent_group_id"] = parent_group_id
        result = self._conn.call(RpcMethod.CREATE_GROUP, **kw)
        if isinstance(result, dict):
            publish_events(self, result.get("events", []))
            self._invalidate_workspace_cache()
            data = result.get("data", result)
            if isinstance(data, dict):
                return str(data.get("group_node_id", data.get("group_id", "")))
            return str(data) if data else ""
        return str(result) if result else ""

    def create_aggregate_item(self, dim_id: str, group_node_id: str, name: str) -> Any:
        result = self._conn.call(
            RpcMethod.CREATE_AGGREGATE_ITEM,
            dim_id=dim_id,
            group_node_id=group_node_id,
            name=name,
        )
        if isinstance(result, dict):
            publish_events(self, result.get("events", []))
            self._invalidate_workspace_cache()
            return result.get("data", result)
        return result

    def move_items_to_group(self, dim_id: str, item_ids: list[str], group_node_id: str) -> None:
        result = self._conn.call(
            RpcMethod.MOVE_ITEMS_TO_GROUP,
            dim_id=dim_id,
            item_ids=item_ids,
            group_node_id=group_node_id,
        )
        if isinstance(result, dict):
            publish_events(self, result.get("events", []))
        self._invalidate_workspace_cache()

    def ungroup_items(self, dim_id: str, item_ids: list[str]) -> None:
        result = self._conn.call(
            RpcMethod.UNGROUP_ITEMS,
            dim_id=dim_id,
            item_ids=item_ids,
        )
        if isinstance(result, dict):
            publish_events(self, result.get("events", []))
        self._invalidate_workspace_cache()

    def rename_group_node(self, dim_id: str, node_id: str, new_label: str) -> None:
        result = self._conn.call(
            RpcMethod.RENAME_GROUP_NODE,
            dim_id=dim_id,
            node_id=node_id,
            new_label=new_label,
        )
        if isinstance(result, dict):
            publish_events(self, result.get("events", []))
        self._invalidate_workspace_cache()

    def delete_group_node(
        self,
        dim_id: str,
        group_node_id: str,
        promote_children: str = "to_parent",
    ) -> None:
        result = self._conn.call(
            RpcMethod.DELETE_GROUP_NODE,
            dim_id=dim_id,
            group_node_id=group_node_id,
            promote_children=promote_children,
        )
        if isinstance(result, dict):
            publish_events(self, result.get("events", []))
        self._invalidate_workspace_cache()

    def move_nodes(
        self,
        dim_id: str,
        node_ids: list[str],
        new_parent_node_id: str | None,
        anchor_node_id: str | None = None,
        position: str = "last",
        reduce_enclosed_groups: bool = False,
        move_empty_parents: bool = True,
    ) -> None:
        kw: dict[str, Any] = {
            "dim_id": dim_id,
            "node_ids": node_ids,
            "position": position,
            "reduce_enclosed_groups": reduce_enclosed_groups,
            "move_empty_parents": move_empty_parents,
        }
        if new_parent_node_id is not None:
            kw["new_parent_node_id"] = new_parent_node_id
        if anchor_node_id is not None:
            kw["anchor_node_id"] = anchor_node_id
        result = self._conn.call(RpcMethod.MOVE_NODES, **kw)
        if isinstance(result, dict):
            publish_events(self, result.get("events", []))
        self._invalidate_workspace_cache()

    def place_item_nodes(
        self,
        dim_id: str,
        item_ids: list[str],
        parent_node_id: str | None,
        anchor_node_id: str | None = None,
        position: str = "after",
    ) -> list[str]:
        kw: dict[str, Any] = {
            "dim_id": dim_id,
            "item_ids": item_ids,
            "position": position,
        }
        if parent_node_id is not None:
            kw["parent_node_id"] = parent_node_id
        if anchor_node_id is not None:
            kw["anchor_node_id"] = anchor_node_id
        result = self._conn.call(RpcMethod.PLACE_ITEM_NODES, **kw)
        if isinstance(result, dict):
            publish_events(self, result.get("events", []))
            self._invalidate_workspace_cache()
            return result.get("data", result.get("node_ids", []))
        self._invalidate_workspace_cache()
        return result if isinstance(result, list) else []

    def reorder_nodes(
        self,
        dim_id: str,
        parent_node_id: str | None,
        node_ids: list[str],
        anchor_node_id: str,
        position: str,
    ) -> None:
        kw: dict[str, Any] = {
            "dim_id": dim_id,
            "node_ids": node_ids,
            "position": position,
        }
        if parent_node_id is not None:
            kw["parent_node_id"] = parent_node_id
        if anchor_node_id is not None:
            kw["anchor_node_id"] = anchor_node_id
        result = self._conn.call(RpcMethod.REORDER_NODES, **kw)
        if isinstance(result, dict):
            publish_events(self, result.get("events", []))
        self._invalidate_workspace_cache()

    # ------------------------------------------------------------------
    # Recompute methods
    # ------------------------------------------------------------------

    def recalculate_all(self, *, include_all: bool = True) -> None:
        self._calculating = True
        try:
            self._conn.call(RpcMethod.RECALCULATE_ALL, include_all=include_all)
        except Exception:
            _log.debug("RECALCULATE_ALL not supported by server, ignoring")
        finally:
            self._calculating = False
        # Cell value changes don't affect workspace structure (views, cubes,
        # dimensions, rules), so no need to invalidate the workspace cache.

    def recompute_dirty_nodes(
        self,
        *,
        include_all: bool = False,
        max_nodes: int | None = None,
        mode: str | None = None,
    ) -> int:
        self._calculating = True
        try:
            result = self._conn.call(
                RpcMethod.RECOMPUTE_DIRTY,
                include_all=include_all,
                max_nodes=max_nodes,
                mode=mode,
            )
            if isinstance(result, dict):
                count = result.get("processed", result.get("count", 0))
                # Apply published values to the local workspace cache.
                values = result.get("values")
                if isinstance(values, dict):
                    from lib_openm.remote_deserialize import _deserialize_value

                    for cache_key, tagged in values.items():
                        parts = cache_key.split("|", 1)
                        if len(parts) != 2:
                            continue
                        cube_id, addr_key = parts
                        cube = self.workspace.cubes.get(cube_id)
                        if cube is None:
                            continue
                        addr = tuple(addr_key.split("|"))
                        value, _ = _deserialize_value(tagged)
                        cube.set(addr, value)
            else:
                count = result
        except Exception:
            _log.debug("RECOMPUTE_DIRTY not supported by server, returning 0")
            count = 0
        finally:
            self._calculating = False
        # Cell value changes don't affect workspace structure.
        return count

    def dirty_count(self) -> int:
        try:
            return int(self._conn.call(RpcMethod.DIRTY_COUNT))
        except Exception:
            return 0

    def has_dirty_nodes(self) -> bool:
        try:
            return bool(self._conn.call(RpcMethod.HAS_DIRTY_NODES))
        except Exception:
            return False

    def bootstrap_dependency_graph(self) -> dict[str, Any]:
        self._gui_ready = True
        self.bump_generation()
        self._invalidate_workspace_cache()
        try:
            result = self._conn.call(RpcMethod.BOOTSTRAP_DEP_GRAPH)
            if isinstance(result, dict) and "evaluated" in result:
                return result
            count = result.get("count", 0) if isinstance(result, dict) else result
            return {"evaluated": count, "duration_ms": 0.0}
        except Exception:
            return {"evaluated": 0, "duration_ms": 0.0}

    def clear_caches(self, scope: str = "all") -> None:
        try:
            self._conn.call(RpcMethod.CLEAR_CACHES, scope=scope)
        except Exception:
            _log.debug("CLEAR_CACHES not supported by server, ignoring")

    def dimension_effective_order(self, dim_id: str) -> list[str]:
        try:
            result = self._conn.call(
                RpcMethod.DIMENSION_EFFECTIVE_ORDER, dim_id=dim_id
            )
            return [str(x) for x in result] if result else []
        except Exception:
            return []

    def dimension_effective_order_window(
        self, dim_id: str, offset: int, limit: int
    ) -> list[str]:
        try:
            result = self._conn.call(
                RpcMethod.DIMENSION_EFFECTIVE_ORDER_WINDOW,
                dim_id=dim_id,
                offset=offset,
                limit=limit,
            )
            return [str(x) for x in result] if result else []
        except Exception:
            return []

    def dirty_keys(self) -> list[str]:
        try:
            result = self._conn.call(RpcMethod.DIRTY_KEYS)
            return [str(x) for x in result] if result else []
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Undo/redo methods
    # ------------------------------------------------------------------

    def undo(self) -> str | None:
        result = self._conn.call(RpcMethod.UNDO)
        self._invalidate_workspace_cache()
        if isinstance(result, dict):
            desc = result.get("description")
            return str(desc) if desc is not None else None
        return result if isinstance(result, str) else None

    def redo(self) -> str | None:
        result = self._conn.call(RpcMethod.REDO)
        self._invalidate_workspace_cache()
        if isinstance(result, dict):
            desc = result.get("description")
            return str(desc) if desc is not None else None
        return result if isinstance(result, str) else None

    def can_undo(self) -> bool:
        return bool(self._conn.call(RpcMethod.CAN_UNDO))

    def can_redo(self) -> bool:
        return bool(self._conn.call(RpcMethod.CAN_REDO))

    def get_undo_description(self) -> str | None:
        result = self._conn.call(RpcMethod.GET_UNDO_DESCRIPTION)
        return str(result) if result is not None else None

    def get_redo_description(self) -> str | None:
        result = self._conn.call(RpcMethod.GET_REDO_DESCRIPTION)
        return str(result) if result is not None else None

    # ------------------------------------------------------------------
    # Query/diagnostic methods
    # ------------------------------------------------------------------

    def list_dependents(self, cube_id: str = None, addr: tuple = None, *args, **kwargs) -> list[str]:
        try:
            result = self._conn.call(RpcMethod.LIST_DEPENDENTS, cube_id=cube_id, addr=list(addr) if addr else [])
            return result if result else []
        except Exception:
            return []

    def list_precedents(self, cube_id: str = None, addr: tuple = None, *args, **kwargs) -> list[str]:
        try:
            result = self._conn.call(RpcMethod.LIST_PRECEDENTS, cube_id=cube_id, addr=list(addr) if addr else [])
            return result if result else []
        except Exception:
            return []

    def trace_calculation_flow(
        self,
        cube_id: str,
        addr: tuple,
        *,
        max_depth: int | None = None,
        max_precedents_per_node: int | None = None,
    ) -> Any:
        try:
            return self._conn.call(
                RpcMethod.TRACE_CALCULATION_FLOW,
                cube_id=cube_id,
                addr=list(addr),
                max_depth=max_depth if max_depth is not None else 2,
                max_precedents_per_node=max_precedents_per_node if max_precedents_per_node is not None else 12,
            )
        except Exception:
            return []

    def trace_circular_references(self) -> list[str]:
        try:
            result = self._conn.call(RpcMethod.TRACE_CIRCULAR_REFERENCES)
            return result if result else []
        except Exception:
            return []

    def dependency_metrics(self) -> dict:
        try:
            return self._conn.call(RpcMethod.DEPENDENCY_METRICS)
        except Exception:
            return {}

    def rule_eval_profile_snapshot(self, *, top_n: int = 10) -> dict:
        try:
            return self._conn.call(RpcMethod.RULE_EVAL_PROFILE, top_n=top_n)
        except Exception:
            return {}

    def reset_profiler_snapshot(self) -> None:
        try:
            self._conn.call(RpcMethod.RESET_PROFILER)
        except Exception:
            pass

    def reset_rule_eval_profile(self) -> None:
        try:
            self._conn.call(RpcMethod.RESET_RULE_EVAL_PROFILE)
        except Exception:
            pass

    def analyze_detach_dimension_from_cube(self, cube_id: str, dim_id: str) -> dict:
        try:
            return self._conn.call(RpcMethod.ANALYZE_DETACH, cube_id=cube_id, dim_id=dim_id)
        except Exception:
            return {}

    def analyze_dimension_deletion_impact(self, dim_id: str) -> dict:
        try:
            return self._conn.call(RpcMethod.ANALYZE_DIM_DELETION, dim_id=dim_id, item_ids=[])
        except Exception:
            return {}

    def analyze_dimension_item_deletion(self, dim_id: str, item_ids: list[str]) -> dict:
        try:
            return self._conn.call(RpcMethod.ANALYZE_ITEM_DELETION, dim_id=dim_id, item_ids=item_ids)
        except Exception:
            return {}

    def evaluate_all_cubes_bruteforce(self) -> dict:
        try:
            return self._conn.call(RpcMethod.EVALUATE_ALL_BRUTEFORCE)
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # Lifecycle methods
    # ------------------------------------------------------------------

    def resolve_item_node_id(self, dim_id: str, label: str) -> str | None:
        try:
            result = self._conn.call(
                RpcMethod.RESOLVE_ITEM_NODE_ID, dim_id=dim_id, label=label
            )
            return str(result) if result is not None else None
        except Exception:
            return None

    def resolve_cube_id_by_name(self, name: str) -> str | None:
        try:
            result = self._conn.call(
                RpcMethod.RESOLVE_CUBE_ID_BY_NAME, name=name
            )
            return str(result) if result is not None else None
        except Exception:
            return None

    def has_system_graph_cubes(self) -> bool:
        try:
            return bool(self._conn.call(RpcMethod.HAS_SYSTEM_GRAPH_CUBES))
        except Exception:
            return False

    @property
    def engine_lock(self):
        """No-op lock context — RemoteEngine is single-threaded."""
        from contextlib import nullcontext
        return nullcontext()

    def addr_for_view_ids(
        self, view_id: str, *, row_key=None, col_key=None
    ) -> tuple[str, ...]:
        ws = self.workspace
        view = ws.views.get(view_id)
        if view is None:
            raise KeyError(f"View {view_id} not found")
        cube = ws.cubes.get(view.cube_id)
        if cube is None:
            raise KeyError(f"Cube {view.cube_id} not found")
        row_index = {did: i for i, did in enumerate(view.row_dim_ids)}
        col_index = {did: i for i, did in enumerate(view.col_dim_ids)}
        addr: list[str] = []
        for dim_id in cube.dimension_ids:
            if dim_id in row_index:
                i = row_index[dim_id]
                if 0 <= i < len(row_key):
                    addr.append(row_key[i])
                else:
                    addr.append(self.get_page_item_id(view_id, dim_id) or "")
            elif dim_id in col_index:
                i = col_index[dim_id]
                if 0 <= i < len(col_key):
                    addr.append(col_key[i])
                else:
                    addr.append(self.get_page_item_id(view_id, dim_id) or "")
            elif dim_id == "@":
                addr.append(view.page_selections.get("@", CHANNEL_TO_AT_ID["value"]))
            else:
                addr.append(self.get_page_item_id(view_id, dim_id) or "")
        return tuple(addr)

    def get_page_item_id(self, view_id: str, dim_id: str) -> str | None:
        ws = self.workspace
        view = ws.views.get(view_id)
        if view is None:
            return None
        if dim_id == "@":
            return view.page_selections.get("@", CHANNEL_TO_AT_ID["value"])
        item_id = view.page_selections.get(dim_id)
        if item_id is not None:
            return item_id
        dim = ws.dimensions.get(dim_id)
        if dim is None or not dim.items:
            return None
        return dim.items[0].id

    def ensure_group_in_graph(
        self, dim_id: str, group_node, parent_group_id: str | None = None
    ) -> str:
        from lib_openm.model import OutlineNode
        payload = {
            "dim_id": dim_id,
            "group_node": {
                "label": group_node.label,
                "item_id": getattr(group_node, "item_id", None),
                "children": [
                    {"label": c.label, "item_id": getattr(c, "item_id", None)}
                    for c in (group_node.children or [])
                ],
            },
            "parent_group_id": parent_group_id,
        }
        result = self._conn.call(RpcMethod.ENSURE_GROUP_IN_GRAPH, **payload)
        return str(result) if result else ""

    # ------------------------------------------------------------------
    # Expression utilities (pure Python, no server round-trip needed)
    # ------------------------------------------------------------------

    def _normalize_expression(self, expression: str) -> str:
        """Accept assignment-like input and keep only the RHS."""
        expr = expression.strip()
        if not expr:
            return expr
        if any(tok in expr for tok in ("==", "<=", ">=", "!=", "<>")):
            return expr
        eq_pos = _find_unquoted_equals(expr)
        if eq_pos >= 0:
            if "(" not in expr[:eq_pos]:
                rhs = expr[eq_pos + 1:]
                if rhs.strip():
                    expr = rhs.strip()
        return expr

    def _extract_trace_refs(self, expression: str) -> list[tuple[str | None, list[tuple[str, str]]]]:
        """Extract dimension/item references from an expression string."""
        from lib_openm.rule_eval.deps import extract_trace_refs as _extract_trace_refs_fn
        return _extract_trace_refs_fn(expression)

    # ------------------------------------------------------------------
    # __getattr__ — raise AttributeError for unknown internal attrs
    # ------------------------------------------------------------------

    def __getattr__(self, name: str):
        if name == "_conn":
            raise AttributeError(
                f"{type(self).__name__!r} object has no attribute {name!r} "
                f"(not initialized — __init__ has not been called)"
            )
        raise AttributeError(
            f"{type(self).__name__!r} object has no attribute {name!r}"
        )
