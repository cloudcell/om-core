"""lib_runtime.runtime_host — standalone runtime process entry point.

Starts the runtime (Engine + Bus + Services + TransportServer) without
any client UI. Clients connect separately via transport.
"""

from __future__ import annotations

import logging
import signal
import sys
import threading
from typing import Any

from lib_runtime.app_host import create_runtime_context

logger = logging.getLogger(__name__)


def start_runtime(endpoint: Any | None = None) -> None:
    """Start the runtime host and block until shutdown.

    Creates Engine, MessageBus, CommandService, QueryService, SessionGateway,
    and TransportServer. Does not start any client UI.
    """
    from lib_command.core.transport_socket_server import SocketTransportServer
    from lib_command.core.transport_base import TransportEndpoint

    if endpoint is None:
        endpoint = _resolve_default_endpoint()

    logger.info("Starting runtime host...")

    # Create runtime context (Engine + Bus + Services + Session)
    ctx = create_runtime_context()

    # Start transport server for remote clients
    transport_server = SocketTransportServer(endpoint)
    try:
        transport_server.start()
    except RuntimeError as exc:
        if endpoint.kind == "tcp" and "already in use" in str(exc).lower():
            logger.error("Port %s is already in use.", endpoint.port)
            sys.exit(1)
        if endpoint.kind == "unix" and "already in use" in str(exc).lower():
            logger.error("Failed to start transport server: %s", exc)
            logger.error(
                "Another runtime process is already listening on this socket. "
                "Kill it or use a different socket: --socket <path>"
            )
            sys.exit(1)
        logger.error("Failed to start transport server: %s", exc)
        sys.exit(1)

    logger.info("Runtime host ready. Transport endpoint: %s", endpoint)
    print(f"Runtime host ready. Transport endpoint: {endpoint}")
    print("Press Ctrl+C to shutdown.")

    # Block until shutdown signal
    _shutdown_event = threading.Event()

    def _on_signal(signum, frame):
        logger.info("Shutdown signal received (%s).", signum)
        _shutdown_event.set()

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    try:
        _shutdown_event.wait()
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("Shutting down runtime host...")
        transport_server.stop()
        logger.info("Runtime host stopped.")


def _resolve_default_endpoint() -> Any:
    """Resolve default transport endpoint for the runtime host."""
    import os
    from lib_command.core.transport_base import TransportEndpoint

    # Environment variables
    socket_path = os.environ.get("OPENM_TRANSPORT_SOCKET")
    if socket_path:
        return TransportEndpoint(kind="unix", path=socket_path)

    env_host = os.environ.get("OPENM_TRANSPORT_HOST")
    env_port = os.environ.get("OPENM_TRANSPORT_PORT")
    if env_host is not None or env_port is not None:
        try:
            p = int(env_port) if env_port else 17391
        except ValueError:
            p = 17391
        return TransportEndpoint(kind="tcp", host=env_host or "127.0.0.1", port=p)

    # Platform default
    if os.name == "nt":
        return TransportEndpoint(kind="tcp", host="127.0.0.1", port=17391)
    else:
        return TransportEndpoint(
            kind="unix",
            path=f"/tmp/openm-{os.environ.get('USER', 'unknown')}.sock",
        )
