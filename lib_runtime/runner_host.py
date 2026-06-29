"""lib_runtime.runner_host — macro runner client entry point.

Connects to a running runtime via transport and executes macro playback.

Note: Full MacroRunner migration to pure ClientSession is owned by H4.
This module provides the client-side transport connection only.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)


def start_macro(endpoint: Any | None = None) -> int:
    """Start macro runner as a pure client connecting to an existing runtime.

    Creates RemoteCommandSession over transport.
    Macro execution delegates to MacroPlaybackRunner (H4 completes the
    migration to remove bus internals from the runner).

    Returns exit code (0 = success, 1 = error).
    """
    from lib_command.core.transport_socket_client import SocketTransportClient
    from lib_command.core.remote_session import RemoteCommandSession
    from lib_command.core.transport_base import TransportEndpoint

    if endpoint is None:
        endpoint = _resolve_client_endpoint()

    client = SocketTransportClient(endpoint)
    try:
        client.connect()
        session_id = client.open_session(client_type="runner")
        logger.info("Runner session opened: %s", session_id)

        remote_session = RemoteCommandSession(client, session_id)
        print(f"Runner connected to runtime at {endpoint}")

        from lib_runner.macro_runner import MacroPlaybackRunner
        runner = MacroPlaybackRunner(session=remote_session)
        print("Runner client ready. Macro execution via remote session.")
        return 0

    except Exception as exc:
        print(f"Error: Cannot connect to OM runtime at {endpoint}.")
        print("Start the runtime first with: python main.py --runtime")
        print(f"  Detail: {exc}")
        return 1
    finally:
        client.close()


def _resolve_client_endpoint() -> Any:
    """Resolve transport endpoint for the runner client."""
    import os
    from lib_command.core.transport_base import TransportEndpoint

    args = sys.argv

    if '--socket' in args:
        idx = args.index('--socket')
        if idx + 1 < len(args):
            return TransportEndpoint(kind="unix", path=args[idx + 1])

    host = None
    port = None
    if '--host' in args:
        idx = args.index('--host')
        if idx + 1 < len(args):
            host = args[idx + 1]
    if '--port' in args:
        idx = args.index('--port')
        if idx + 1 < len(args):
            try:
                port = int(args[idx + 1])
            except ValueError:
                port = None

    if host is not None or port is not None:
        return TransportEndpoint(kind="tcp", host=host or "127.0.0.1", port=port or 17391)

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

    if os.name == "nt":
        return TransportEndpoint(kind="tcp", host="127.0.0.1", port=17391)
    else:
        return TransportEndpoint(
            kind="unix",
            path=f"/tmp/openm-{os.environ.get('USER', 'unknown')}.sock",
        )
