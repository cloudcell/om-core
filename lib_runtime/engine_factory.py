"""lib_runtime.engine_factory — engine construction factory.

Encapsulates Engine creation and configuration. Lives in lib_runtime,
not lib_gui.
"""

from __future__ import annotations

from lib_openm.api import Engine
from lib_openm.model import Workspace
from lib_command.core.engine_event_publisher import BusEventPublisher


def create_engine(
    workspace: Workspace,
    *,
    enable_dependency_tracking: bool = True,
) -> Engine:
    """Create and configure an Engine instance."""
    engine = Engine(workspace, event_publisher=BusEventPublisher())
    engine.enable_dependency_tracking(enable_dependency_tracking)
    return engine
