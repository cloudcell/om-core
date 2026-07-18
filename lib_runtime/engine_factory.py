"""lib_runtime.engine_factory — engine construction factory.

Encapsulates Engine creation and configuration. Lives in lib_runtime,
not lib_gui.

Engine modes:
  - "python"  (default): Pure-Python Engine with _EngineCore
  - "remote": RemoteEngine — all operations delegated to a remote server
"""

from __future__ import annotations

import logging
import os

from lib_openm.api import Engine
from lib_openm.model import Workspace
from lib_command.core.engine_event_publisher import BusEventPublisher

_log = logging.getLogger(__name__)


def create_engine(
    workspace: Workspace,
    *,
    enable_dependency_tracking: bool = True,
    engine_mode: str | None = None,
) -> Engine:
    """Create and configure an Engine instance.

    Args:
        workspace: The initial workspace to load.
        enable_dependency_tracking: Whether to enable dep tracking.
        engine_mode: "python" or "remote". If None,
            reads OMENGINE_MODE env var (default: "python").
    """
    mode = engine_mode or os.environ.get("OMENGINE_MODE", "python")

    if mode == "remote":
        return _create_remote_engine(workspace, enable_dependency_tracking)
    else:
        engine = Engine(workspace, event_publisher=BusEventPublisher())
        engine.enable_dependency_tracking(enable_dependency_tracking)
        return engine


def _create_remote_engine(
    workspace: Workspace,
    enable_dependency_tracking: bool,
) -> Engine:
    """Create a RemoteEngine that delegates all operations to a remote server."""
    from lib_openm.remote_engine import RemoteEngine
    from lib_runtime.launcher import Launcher
    from lib_utils.config import engine as engine_cfg

    endpoint = os.environ.get(
        "OM_ENGINE_ENDPOINT",
        str(engine_cfg("remote", "endpoint", "unix:///tmp/om-engine.sock")),
    )

    launcher = Launcher(endpoint=endpoint)
    launcher.start()

    try:
        engine = RemoteEngine(
            workspace,
            endpoint=endpoint,
            event_publisher=BusEventPublisher(),
        )
        engine.enable_dependency_tracking(enable_dependency_tracking)
        engine._launcher = launcher
        _log.info("Remote engine active on endpoint %s", endpoint)
        return engine
    except Exception:
        launcher.stop()
        raise
