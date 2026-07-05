"""Neutral engine ports for lib_openm.

This module contains the ports the engine accepts as injected dependencies.
Engine ports are extension points that sit *inside* the engine boundary: they
allow the engine to delegate specific concerns to alternate implementations
without exposing engine internals to the command, runtime, GUI, persistence,
import/export, or other non-engine layers.

Current and anticipated engine ports:

- EventPublisher: the engine publishes domain events through this port. The
  command/bus layer provides the canonical implementation (BusEventPublisher).
- Future computation backends: a Julia, Zig, or other high-performance engine
  implementation may be plugged in as a port for heavy evaluation workloads
  while the Python engine retains the workspace graph and the public API.
- Future evaluation strategy ports: native solvers, sparse-array engines, or
  external compute adapters may be injected here without moving command or
  persistence concerns into the engine.

Command, runtime, GUI, persistence, import/export, and other non-engine
concerns are defined as ports in their own layers and must not be referenced
inside lib_openm.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class EventPublisher(ABC):
    """Abstract interface for publishing engine events.

    Implementations are provided by the command/bus layer (lib_command).
    The Engine never imports lib_command directly.
    """

    @abstractmethod
    def publish(self, topic_suffix: str, payload: dict, engine: Any) -> None:
        """Publish an event. Must never raise — caller must not be affected."""
        ...
