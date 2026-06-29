"""lib_runtime.cli_host — CLI/batch client entry point.

Connects to a running runtime via transport and executes a script file.
The script is read locally; commands are sent over transport.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def start_batch(script_path: str, endpoint: Any | None = None) -> int:
    """Execute a script file as a pure client connecting to an existing runtime.

    Reads the script locally, parses each line, and sends commands via
    session.execute(). The runtime does not read script files directly.

    Returns exit code (0 = success, 1 = error, 2 = assertion failure).
    """
    from lib_utils.logging import setup_logging, get_logger
    from lib_command.core.transport_socket_client import SocketTransportClient
    from lib_command.core.remote_session import RemoteCommandSession
    from lib_command.core.transport_base import TransportEndpoint

    setup_logging(level=logging.DEBUG)
    startup_logger = get_logger("startup")

    if not os.path.exists(script_path):
        print(f"Error: Script file not found: {script_path}", file=sys.stderr)
        return 1

    if endpoint is None:
        endpoint = _resolve_client_endpoint()

    client = SocketTransportClient(endpoint)
    session = None
    try:
        client.connect()
        session_id = client.open_session(client_type="batch")
        logger.info("Batch session opened: %s", session_id)

        session = RemoteCommandSession(client, session_id)
        startup_logger.info("Connected to runtime at %s", endpoint)

        # Create REPL with remote session for command parsing and execution
        from lib_repl import OpenMREPL
        repl = OpenMREPL(session=session)

        # Seed the source stack so any `source` commands inside the script
        # resolve relative paths against the script's directory.
        script_path_abs = str(Path(script_path).resolve())
        repl._source_stack = [script_path_abs]
        try:
            with open(script_path, 'r') as f:
                lines = f.readlines()

            print(f"Executing {script_path} ({len(lines)} lines)...")
            executed = 0

            for line_num, line in enumerate(lines, 1):
                stripped = line.strip()
                if not stripped or stripped.startswith('#'):
                    continue

                startup_logger.debug("Executing line %s: %s", line_num, stripped)
                print(f"> {stripped}")

                try:
                    # Use REPL's onecmd for full command support (parsing,
                    # variable expansion, macro placeholders, etc.)
                    result = repl.onecmd(stripped)
                    # Check for assertion failure (do_assert returns True to halt)
                    if result is True:
                        print(f"\n*** SCRIPT HALTED at line {line_num}: {stripped[:60]}...")
                        return 2  # Special exit code for assertion failure
                    executed += 1
                except SystemExit:
                    raise
                except Exception as e:
                    startup_logger.error("Error at line %s: %s", line_num, e)
                    print(f"Error at line {line_num}: {e}", file=sys.stderr)
                    print(f"  Line: {stripped[:60]}...")
                    return 1

            startup_logger.info("Batch execution completed: %s commands executed", executed)
            print(f"Script executed successfully ({executed} commands)")
            return 0
        finally:
            repl._source_stack.clear()

    except Exception as exc:
        print(f"Error: Cannot connect to OM runtime at {endpoint}.")
        print("Start the runtime first with: python main.py --runtime")
        print(f"  Detail: {exc}")
        return 1
    finally:
        if session is not None:
            session.close()
        else:
            client.close()


def _resolve_client_endpoint() -> Any:
    """Resolve transport endpoint for the CLI/batch client."""
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
