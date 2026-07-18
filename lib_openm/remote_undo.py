"""Remote undo manager — thin proxy for server-side undo/redo.

Delegates can_undo/can_redo/undo/redo to the server via RPC.
No Python-side undo state — the server owns undo history.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lib_openm.rpc_constants import RpcMethod

if TYPE_CHECKING:
    from lib_openm.remote_engine import RemoteEngine


class _RemoteUndoManager:
    """Proxy for server-side undo/redo state.

    Command executors call start_group/end_group/cancel_group on the
    undo manager. In remote mode, the server handles undo atomically
    per mutation — no Python-side grouping is needed.
    """

    def __init__(self, engine: "RemoteEngine") -> None:
        self._engine = engine
        self._conn = engine._conn

    def can_undo(self) -> bool:
        return bool(self._conn.call(RpcMethod.CAN_UNDO))

    def can_redo(self) -> bool:
        return bool(self._conn.call(RpcMethod.CAN_REDO))

    def undo(self) -> str | None:
        result = self._conn.call(RpcMethod.UNDO)
        self._engine._invalidate_workspace_cache()
        if isinstance(result, dict):
            desc = result.get("description")
            return str(desc) if desc is not None else None
        return result if isinstance(result, str) else None

    def redo(self) -> str | None:
        result = self._conn.call(RpcMethod.REDO)
        self._engine._invalidate_workspace_cache()
        if isinstance(result, dict):
            desc = result.get("description")
            return str(desc) if desc is not None else None
        return result if isinstance(result, str) else None

    def get_undo_description(self) -> str | None:
        result = self._conn.call(RpcMethod.GET_UNDO_DESCRIPTION)
        return str(result) if result is not None else None

    def get_redo_description(self) -> str | None:
        result = self._conn.call(RpcMethod.GET_REDO_DESCRIPTION)
        return str(result) if result is not None else None

    def start_group(self, description: str) -> None:
        pass

    def end_group(self) -> None:
        pass

    def cancel_group(self) -> None:
        pass
