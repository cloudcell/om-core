"""Socket transport client — Unix-domain or TCP backend."""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
from typing import Any

from .transport_base import TransportClientProtocol, TransportEndpoint
from .transport_serde import encode_envelope, decode_envelope, envelope_to_wire, wire_to_envelope
from .message_bus import MessageEnvelope
from .executor import ExecutionResult, ExecutionStatus

logger = logging.getLogger(__name__)


class SocketTransportClient:
    """Transport client that connects to a Unix-domain or TCP socket."""

    def __init__(
        self,
        endpoint: TransportEndpoint,
        timeout: float = 30.0,
        poll_interval: float = 0.1,
    ) -> None:
        self.endpoint = endpoint
        self.timeout = timeout
        self.poll_interval = poll_interval
        self._sock: socket.socket | None = None
        self._subscriptions: dict[str, list[Any]] = {}
        self._poll_thread: threading.Thread | None = None
        self._poll_stop = threading.Event()
        self._send_lock = threading.Lock()
        self._recv_buf: bytes = b""
        self._pending_replies: dict[str, MessageEnvelope] = {}
        self._pending_lock = threading.Lock()

    def connect(self) -> None:
        """Connect to the transport server and start event polling thread."""
        if self.endpoint.kind == "unix":
            path = self.endpoint.path
            assert path is not None
            self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._sock.settimeout(self.timeout)
            self._sock.connect(path)
        else:
            host = self.endpoint.host
            port = self.endpoint.port
            assert port is not None
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(self.timeout)
            self._sock.connect((host, port))
        self._recv_buf = b""
        logger.info("Connected to transport server at %s", self.endpoint)

        # Start background event polling thread
        self._poll_stop.clear()
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def open_session(self, client_type: str = "repl") -> str:
        """Send a session.open request and return the session ID."""
        request = MessageEnvelope(
            message_id="open_session",
            message_type="control",
            topic="request.session.open",
            correlation_id=self._make_corr(),
            session_id=None,
            client_type=client_type,
            workspace_id=None,
            actor_id=None,
            timestamp=time.perf_counter(),
            payload={"client_type": client_type},
            context=None,
        )
        reply = self._send_and_wait(request)
        payload = reply.payload or {}
        data = payload.get("data", {})
        session_id = data.get("session_id")
        if not session_id:
            error = payload.get("error", "Unknown error")
            raise RuntimeError(f"Session open failed: {error}")
        return session_id

    def send(self, session_id: str, command_id: str, **params) -> ExecutionResult:
        """Send a command and return the ExecutionResult."""
        request = MessageEnvelope(
            message_id="cmd",
            message_type="command",
            topic="request.command",
            correlation_id=self._make_corr(),
            session_id=session_id,
            client_type="repl",
            workspace_id=None,
            actor_id=None,
            timestamp=time.perf_counter(),
            payload={"command_id": command_id, **params},
            context=None,
        )
        reply = self._send_and_wait(request)
        payload = reply.payload or {}
        status_name = payload.get("status", "error")
        status = ExecutionStatus.SUCCESS if status_name == "success" else ExecutionStatus.ERROR
        return ExecutionResult(
            status=status,
            command_id=command_id,
            data=payload.get("data"),
            error=payload.get("error"),
        )

    def query(self, session_id: str, query_id: str, **params) -> Any:
        """Send a query and return the data."""
        request = MessageEnvelope(
            message_id="query",
            message_type="query",
            topic="request.query",
            correlation_id=self._make_corr(),
            session_id=session_id,
            client_type="repl",
            workspace_id=None,
            actor_id=None,
            timestamp=time.perf_counter(),
            payload={"query_id": query_id, **params},
            context=None,
        )
        reply = self._send_and_wait(request)
        payload = reply.payload or {}
        return payload.get("data")

    def subscribe(self, session_id: str, topic: str, callback: Any) -> None:
        """Subscribe to a bus topic. Events are delivered via the polling thread."""
        self._subscriptions.setdefault(topic, []).append(callback)

    def unsubscribe(self, session_id: str, topic: str, callback: Any | None = None) -> None:
        """Unsubscribe from a bus topic."""
        if topic not in self._subscriptions:
            return
        if callback is None:
            del self._subscriptions[topic]
        else:
            self._subscriptions[topic] = [c for c in self._subscriptions[topic] if c is not callback]
            if not self._subscriptions[topic]:
                del self._subscriptions[topic]

    def ping(self, session_id: str | None = None) -> bool:
        """Send a transport ping and return whether the server replied."""
        request = MessageEnvelope(
            message_id="ping",
            message_type="control",
            topic="request.transport.ping",
            correlation_id=self._make_corr(),
            session_id=session_id,
            client_type="repl",
            workspace_id=None,
            actor_id=None,
            timestamp=time.perf_counter(),
            payload={},
            context=None,
        )
        try:
            reply = self._send_and_wait(request)
            payload = reply.payload or {}
            data = payload.get("data", {})
            return bool(data.get("pong"))
        except Exception:
            return False

    def close(self) -> None:
        """Close the connection and stop event polling."""
        self._poll_stop.set()
        if self._poll_thread:
            self._poll_thread.join(timeout=1.0)
            self._poll_thread = None
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
            self._recv_buf = b""

    def _poll_loop(self) -> None:
        """Background thread: periodically poll for events from the server."""
        while not self._poll_stop.is_set():
            if not self._subscriptions or self._sock is None:
                time.sleep(self.poll_interval)
                continue

            topics = list(self._subscriptions.keys())
            try:
                request = MessageEnvelope(
                    message_id="poll_events",
                    message_type="control",
                    topic="request.poll_events",
                    correlation_id=self._make_corr(),
                    session_id=None,
                    client_type="repl",
                    workspace_id=None,
                    actor_id=None,
                    timestamp=time.perf_counter(),
                    payload={"topics": topics},
                    context=None,
                )
                reply = self._send_and_wait(request)
                payload = reply.payload or {}
                events = payload.get("data", {}).get("events", [])
                for event_data in events:
                    try:
                        event = wire_to_envelope(event_data)
                        topic = event.topic
                        # Match against wildcard subscription patterns (e.g.
                        # "command.*.succeeded" must match "command.restore_checkpoint.succeeded")
                        for pattern, cbs in self._subscriptions.items():
                            from .message_bus import _topic_matches
                            if _topic_matches(pattern, topic):
                                for cb in cbs:
                                    try:
                                        cb(event)
                                    except Exception:
                                        logger.exception("Event callback error for topic %s", topic)
                    except Exception:
                        logger.exception("Event dispatch error")
            except Exception:
                # Poll errors are non-fatal; connection issues handled by send/query
                pass

            time.sleep(self.poll_interval)

    def _make_corr(self) -> str:
        import uuid
        return uuid.uuid4().hex

    def _send_and_wait(self, request: MessageEnvelope) -> MessageEnvelope:
        """Send a request and block until the correlated reply arrives."""
        # If another thread already received our reply, return it immediately.
        with self._pending_lock:
            if request.correlation_id in self._pending_replies:
                return self._pending_replies.pop(request.correlation_id)

        with self._send_lock:
            # Re-check after acquiring the lock: another thread may have
            # stashed our reply while we were waiting.
            with self._pending_lock:
                if request.correlation_id in self._pending_replies:
                    return self._pending_replies.pop(request.correlation_id)

            if self._sock is None:
                raise ConnectionError("Not connected")

            try:
                self._sock.sendall(encode_envelope(request))
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                self._sock = None
                self._recv_buf = b""
                raise ConnectionError("Transport connection lost")

            start = time.monotonic()
            while True:
                # Drain buffered lines first
                while b"\n" in self._recv_buf:
                    line, self._recv_buf = self._recv_buf.split(b"\n", 1)
                    reply = decode_envelope(line)
                    if reply.correlation_id == request.correlation_id:
                        return reply
                    # Stash for the correct waiter
                    with self._pending_lock:
                        self._pending_replies[reply.correlation_id] = reply

                if time.monotonic() - start > self.timeout:
                    raise TimeoutError("Transport reply timeout")

                self._sock.settimeout(max(0.1, self.timeout - (time.monotonic() - start)))
                try:
                    chunk = self._sock.recv(4096)
                    if not chunk:
                        self._sock = None
                        self._recv_buf = b""
                        raise ConnectionError("Transport connection closed")
                    self._recv_buf += chunk
                except socket.timeout:
                    continue
                except (ConnectionResetError, BrokenPipeError, OSError):
                    self._sock = None
                    self._recv_buf = b""
                    raise ConnectionError("Transport connection lost")
