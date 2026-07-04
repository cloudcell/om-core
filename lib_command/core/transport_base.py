"""Backend-neutral transport protocol and endpoint abstraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

from .executor import ExecutionResult


@dataclass(frozen=True)
class TransportEndpoint:
    kind: Literal["unix", "tcp"]
    path: str | None = None
    host: str = "127.0.0.1"
    port: int | None = None

    def __post_init__(self):
        if self.kind == "unix" and not self.path:
            raise ValueError("Unix endpoint requires a path")
        if self.kind == "tcp" and self.port is None:
            raise ValueError("TCP endpoint requires a port")


class TransportClientProtocol(Protocol):
    """Backend-neutral client interface."""

    @property
    def is_connected(self) -> bool: ...
    def connect(self) -> None: ...
    def open_session(self, client_type: str = "repl") -> str: ...
    def send(self, session_id: str, command_id: str, **params) -> ExecutionResult: ...
    def query(self, session_id: str, query_id: str, **params) -> Any: ...
    def subscribe(self, session_id: str, topic: str, callback: Any) -> None: ...
    def unsubscribe(self, session_id: str, topic: str, callback: Any | None = None) -> None: ...
    def ping(self, session_id: str | None = None) -> bool: ...
    def close(self) -> None: ...
