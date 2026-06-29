"""Abstract event publisher interface for lib_openm.

The Engine delegates event publication to an injected EventPublisher.
Implementations are provided by the command/bus layer (lib_command).
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
