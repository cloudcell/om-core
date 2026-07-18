"""Endpoint-agnostic RPC connection for the remote engine.

Supports both Unix sockets (unix:///path) and TCP (tcp://host:port).
Uses MsgPack over length-prefixed frames (4-byte big-endian length).

Wire format:
  request  = {"id": str, "method": str, "args": list, "kwargs": dict, "meta": dict}
  response = {"id": str, "result": ..., "error": str|dict|None, "meta": dict}
"""

from __future__ import annotations

import logging
import os
import socket
import struct
import threading
import uuid
from typing import Any
from urllib.parse import urlparse

import msgpack

_log = logging.getLogger(__name__)


class RemoteEngineError(Exception):
    """Error returned by the remote engine server."""


def _map_error(error: Any) -> Exception:
    """Map a server error response to the appropriate Python exception.

    Handles both plain string errors (backward compat) and structured
    dict errors with a 'type' field.
    """
    if isinstance(error, str):
        return RemoteEngineError(error)

    if isinstance(error, dict):
        err_type = error.get("type", "")
        message = error.get("message", str(error))

        mapping = _ERROR_TYPE_MAP.get(err_type)
        if mapping is not None:
            return mapping(message)

        return RemoteEngineError(f"[{err_type}] {message}" if err_type else message)

    return RemoteEngineError(str(error))


def _import_exception(module_path: str, class_name: str) -> type[Exception]:
    """Lazily import an exception class to avoid circular imports."""
    import importlib

    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)


# Lazy error type mapping — populated on first use to avoid circular imports.
_ERROR_TYPE_MAP: dict[str, type[Exception]] | None = None


def _get_error_type_map() -> dict[str, type[Exception]]:
    global _ERROR_TYPE_MAP
    if _ERROR_TYPE_MAP is None:
        from lib_contracts.types import (
            RuleValidationError,
            CircularReferenceError,
            CalculationCancelledError,
        )
        from lib_openm.engine_state import (
            EngineBusyError,
            EngineFaultedError,
            EngineShuttingDownError,
        )

        _ERROR_TYPE_MAP = {
            "rule_validation": RuleValidationError,
            "circular_reference": CircularReferenceError,
            "calculation_cancelled": CalculationCancelledError,
            "engine_busy": EngineBusyError,
            "engine_faulted": EngineFaultedError,
            "engine_shutting_down": EngineShuttingDownError,
            "connection_lost": EngineShuttingDownError,
        }
    return _ERROR_TYPE_MAP


def _map_error_v2(error: Any) -> Exception:
    """Map a server error response to the appropriate Python exception."""
    if isinstance(error, str):
        return RemoteEngineError(error)

    if isinstance(error, dict):
        err_type = error.get("type", "")
        message = error.get("message", str(error))

        type_map = _get_error_type_map()
        exc_cls = type_map.get(err_type)
        if exc_cls is not None:
            return exc_cls(message)

        return RemoteEngineError(f"[{err_type}] {message}" if err_type else message)

    return RemoteEngineError(str(error))


class Connection:
    """Synchronous connection to a remote engine server.

    Endpoint format:
      unix:///tmp/om-engine.sock  — Unix socket
      tcp://localhost:7654        — TCP
    """

    _DEFAULT_TIMEOUT = 60.0  # seconds

    def __init__(self, endpoint: str, timeout: float | None = None) -> None:
        self._endpoint = endpoint
        self._parsed = urlparse(endpoint)
        self._sock: socket.socket | None = None
        self._connected = False
        self._timeout = timeout or self._DEFAULT_TIMEOUT
        self._lock = threading.Lock()

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        if self._connected and self._sock is not None:
            return

        scheme = self._parsed.scheme
        if scheme == "unix":
            path = self._parsed.path
            self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._sock.settimeout(self._timeout)
            self._sock.connect(path)
        elif scheme == "tcp":
            host = self._parsed.hostname or "localhost"
            port = self._parsed.port or 7654
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(self._timeout)
            self._sock.connect((host, port))
        else:
            raise ValueError(f"unsupported endpoint scheme: {scheme!r} in {self._endpoint!r}")

        self._connected = True

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        self._connected = False

    def call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        """Send an RPC request and return the result.

        Thread-safe: serializes concurrent calls so multiple threads can
        share a single connection without corrupting the wire protocol.

        Raises RemoteEngineError (or a mapped subclass) on server errors.
        Raises EngineShuttingDownError if the connection is lost.
        """
        with self._lock:
            return self._call_locked(method, *args, **kwargs)

    def _call_locked(self, method: str, *args: Any, **kwargs: Any) -> Any:
        if not self._connected or self._sock is None:
            self.connect()
        assert self._sock is not None

        payload = msgpack.packb(
            {
                "id": str(uuid.uuid4()),
                "method": method,
                "args": list(args),
                "kwargs": kwargs,
                "meta": {},
            },
            use_bin_type=True,
        )
        self._sock.sendall(struct.pack(">I", len(payload)) + payload)

        resp_bytes = self._recv_frame()
        if not resp_bytes:
            self._connected = False
            from lib_openm.engine_state import EngineShuttingDownError

            raise EngineShuttingDownError("server closed connection before responding")

        resp = msgpack.unpackb(
            resp_bytes,
            raw=False,
            strict_map_key=False,
            max_str_len=2**31 - 1,
            max_bin_len=2**31 - 1,
            max_array_len=2**31 - 1,
            max_map_len=2**31 - 1,
            max_ext_len=2**31 - 1,
        )

        error = resp.get("error")
        if error is not None:
            raise _map_error_v2(error)

        return resp.get("result")

    def _recv_frame(self) -> bytes:
        assert self._sock is not None
        try:
            len_bytes = self._sock.recv(4)
        except socket.timeout:
            raise TimeoutError(f"socket recv timeout after {self._timeout}s waiting for frame header")
        if len(len_bytes) < 4:
            return b""
        length = int.from_bytes(len_bytes, "big")
        chunks: list[bytes] = []
        remaining = length
        while remaining > 0:
            try:
                chunk = self._sock.recv(min(remaining, 65536))
            except socket.timeout:
                raise TimeoutError(f"socket recv timeout after {self._timeout}s reading frame body")
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def __enter__(self) -> "Connection":
        self.connect()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
