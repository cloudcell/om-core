"""GUI Logger — Dedicated observability for the PySide6 front-end.

Captures widget events, refreshes, selection changes, focus changes,
and user interactions.  Written to its own file so it can eventually be
lifted out into a standalone GUI service.

Usage:
    from lib_gui.gui_logger import get_gui_logger
    gl = get_gui_logger()
    gl.start()
    gl.log_event("mousePress", "row=1,col=1")
    gl.log_refresh("MatrixGrid.reload", "3.0 ms")
    recent = gl.tail(10)
    gl.stop()
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

_GUI_LOGGER_INSTANCE: Optional[GUILogger] = None


@dataclass(frozen=True)
class GUIRecord:
    timestamp: float
    kind: str  # 'event', 'refresh', 'selection', 'focus', 'panel', 'error'
    source: str
    detail: str
    meta: dict[str, Any] = field(default_factory=dict)


class GUILogger:
    """Logger for the graphical user interface.

    Attributes:
        log_file: Path to the dedicated GUI log (default: ./log/gui.log)
        ring_size: In-memory buffer size for fast tail()
    """

    def __init__(self, log_file: Path | str | None = None, ring_size: int = 200) -> None:
        if log_file is None:
            root = Path(__file__).parent.parent
            (root / "log").mkdir(parents=True, exist_ok=True)
            log_file = root / "log" / "gui.log"
        self.log_file = Path(log_file)
        self.ring_size = ring_size
        self._ring: deque[GUIRecord] = deque(maxlen=ring_size)
        self._started = False

        self._logger = logging.getLogger("openm.gui")
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

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._logger.info("GUILogger started")

    def stop(self) -> None:
        if not self._started:
            return
        self._started = False
        self._logger.info("GUILogger stopped")

    # -- public logging API -------------------------------------------------

    def log_event(self, source: str, detail: str, **meta: Any) -> None:
        self._append("event", source, detail, meta)
        self._logger.info(f"EVT | {source} | {detail}")

    def log_refresh(self, source: str, detail: str, **meta: Any) -> None:
        self._append("refresh", source, detail, meta)
        self._logger.info(f"RFR | {source} | {detail}")

    def log_selection(self, source: str, detail: str, **meta: Any) -> None:
        self._append("selection", source, detail, meta)
        self._logger.debug(f"SEL | {source} | {detail}")

    def log_focus(self, source: str, detail: str, **meta: Any) -> None:
        self._append("focus", source, detail, meta)
        self._logger.debug(f"FOC | {source} | {detail}")

    def log_panel(self, source: str, detail: str, **meta: Any) -> None:
        self._append("panel", source, detail, meta)
        self._logger.info(f"PNL | {source} | {detail}")

    def log_error(self, source: str, detail: str, **meta: Any) -> None:
        self._append("error", source, detail, meta)
        self._logger.error(f"ERR | {source} | {detail}")

    # -- query API ----------------------------------------------------------

    def tail(self, n: int = 10) -> list[GUIRecord]:
        return list(self._ring)[-n:][::-1] if self._ring else []

    def filter_by_kind(self, kind: str, n: int = 10) -> list[GUIRecord]:
        matches = [r for r in self._ring if r.kind == kind]
        return matches[-n:][::-1]

    def clear(self) -> None:
        self._ring.clear()

    # -- internal -----------------------------------------------------------

    def _append(self, kind: str, source: str, detail: str, meta: dict[str, Any]) -> None:
        self._ring.append(GUIRecord(
            timestamp=time.perf_counter(),
            kind=kind,
            source=source,
            detail=detail,
            meta=meta,
        ))


def get_gui_logger(log_file: Path | str | None = None, ring_size: int = 200) -> GUILogger:
    global _GUI_LOGGER_INSTANCE
    if _GUI_LOGGER_INSTANCE is None:
        _GUI_LOGGER_INSTANCE = GUILogger(log_file=log_file, ring_size=ring_size)
    return _GUI_LOGGER_INSTANCE
