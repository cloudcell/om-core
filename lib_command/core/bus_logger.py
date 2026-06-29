"""Bus Logger — Dedicated observability for the Event Bus backbone.

Captures every publish and subscribe operation, every command event,
and every subscriber callback (success or failure).  Written to its own
file so it can eventually be lifted out into a standalone Bus service.

Usage:
    from lib_command.core.bus_logger import get_bus_logger
    bl = get_bus_logger()
    bl.start()
    recent = bl.tail(10)
    bl.stop()
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from .message_bus import get_message_bus

_BUS_LOGGER_INSTANCE: Optional[BusLogger] = None


@dataclass(frozen=True)
class BusRecord:
    timestamp: float
    kind: str  # 'publish', 'subscribe', 'unsubscribe', 'subscriber_ok', 'subscriber_err'
    topic: str
    detail: str
    meta: dict[str, Any] = field(default_factory=dict)


class BusLogger:
    """Logger for the Event Bus.

    Attributes:
        log_file: Path to the dedicated bus log (default: ./log/bus.log)
        ring_size: In-memory buffer size for fast tail()
    """

    def __init__(
        self,
        log_file: Path | str | None = None,
        ring_size: int = 500,
        bus: Any = None,
    ) -> None:
        if log_file is None:
            root = Path(__file__).parent.parent.parent
            (root / "log").mkdir(parents=True, exist_ok=True)
            log_file = root / "log" / "bus.log"
        self.log_file = Path(log_file)
        self.ring_size = ring_size
        self._ring: deque[BusRecord] = deque(maxlen=ring_size)
        self._started = False
        self._handlers: list[tuple[str, Callable[[Any], None]]] = []
        self._bus = bus or get_message_bus()

        self._logger = logging.getLogger("openm.bus")
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False
        self._handler: Optional[logging.FileHandler] = None
        self._ensure_handler()

    def _ensure_handler(self) -> None:
        if self._handler is not None:
            return
        fh = logging.FileHandler(self.log_file, mode="a", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fmt = logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        fh.setFormatter(fmt)
        self._logger.addHandler(fh)
        self._handler = fh

    def _reset_handler(self) -> None:
        """Close existing handler and truncate the log file for a fresh start."""
        if self._handler is not None:
            self._logger.removeHandler(self._handler)
            self._handler.close()
            self._handler = None
        self.log_file.write_text("", encoding="utf-8")
        self._ensure_handler()

    def start(self) -> None:
        if self._started:
            return
        self._reset_handler()
        self._bus.add_publish_hook(self._on_publish)
        self._started = True
        self._logger.info("BusLogger started")

    def stop(self) -> None:
        if not self._started:
            return
        self._bus.remove_publish_hook(self._on_publish)
        self._started = False
        self._logger.info("BusLogger stopped")

    # -- event handler ------------------------------------------------------

    def _on_publish(self, topic: str, event: Any) -> None:
        import dataclasses

        payload = getattr(event, "payload", None)
        if isinstance(payload, dict):
            cid = payload.get("command_id", "unknown")
            err = payload.get("__error", None)
            detail = f"payload={payload}"
        elif dataclasses.is_dataclass(event):
            d = dataclasses.asdict(event)  # type: ignore[arg-type]
            cid = d.get("command", d.get("dim_id", d.get("reason", "event")))
            err = d.get("error", None)
            # Compact summary: limit list lengths, stringify
            summary = ", ".join(
                f"{k}={v if not isinstance(v, list) else '[' + ', '.join(str(x)[:24] for x in v[:5]) + ('...' if len(v) > 5 else '') + ']' }"
                for k, v in d.items()
            )
            detail = summary[:200]
        else:
            cid = "unknown"
            err = None
            detail = repr(event)[:120]

        self._append("publish", topic, str(cid), meta={"payload_type": type(event).__name__, "detail": detail})

        if topic.endswith(".succeeded"):
            self._logger.info(f"PUB | {topic} | {cid} | {detail}")
        elif topic.endswith(".failed") and err:
            self._logger.warning(f"PUB | {topic} | {cid} | error={err} | {detail}")
        else:
            self._logger.debug(f"PUB | {topic} | {cid} | {detail}")

    # -- query API ----------------------------------------------------------

    def tail(self, n: int = 10) -> list[BusRecord]:
        return list(self._ring)[-n:][::-1] if self._ring else []

    def filter_by_topic(self, topic: str, n: int = 10) -> list[BusRecord]:
        matches = [r for r in self._ring if r.topic == topic]
        return matches[-n:][::-1]

    def filter_by_command(self, command_id: str, n: int = 10) -> list[BusRecord]:
        matches = [r for r in self._ring if r.detail == command_id]
        return matches[-n:][::-1]

    def clear(self) -> None:
        self._ring.clear()

    # -- internal -----------------------------------------------------------

    def _append(self, kind: str, topic: str, detail: str, meta: Optional[dict] = None) -> None:
        self._ring.append(BusRecord(
            timestamp=time.perf_counter(),
            kind=kind,
            topic=topic,
            detail=detail,
            meta=meta or {},
        ))


def get_bus_logger(log_file: Path | str | None = None, ring_size: int = 500) -> BusLogger:
    global _BUS_LOGGER_INSTANCE
    if _BUS_LOGGER_INSTANCE is None:
        _BUS_LOGGER_INSTANCE = BusLogger(log_file=log_file, ring_size=ring_size)
    return _BUS_LOGGER_INSTANCE
