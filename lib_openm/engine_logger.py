"""Engine Logger — Dedicated observability for the DAG Engine core.

Captures recalculation events, dirty propagation, rule evaluation,
cell changes, and dependency tracking.  Written to its own file so it
can eventually be lifted out into a standalone Engine service.

Usage:
    from lib_openm.engine_logger import get_engine_logger
    el = get_engine_logger()
    el.start()
    el.log_recalc("dirty=12, processed=8")
    el.log_rule_eval("A1", "=B1+C1", 42.0)
    recent = el.tail(10)
    el.stop()
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

_ENGINE_LOGGER_INSTANCE: Optional[EngineLogger] = None


@dataclass(frozen=True)
class EngineRecord:
    timestamp: float
    kind: str  # 'recalc', 'rule_eval', 'dirty_mark', 'dep_track', 'cell_change', 'error'
    detail: str
    meta: dict[str, Any] = field(default_factory=dict)


class EngineLogger:
    """Logger for the OpenM calculation engine.

    Attributes:
        log_file: Path to the dedicated engine log (default: ./log/engine.log)
        ring_size: In-memory buffer size for fast tail()
    """

    def __init__(self, log_file: Path | str | None = None, ring_size: int = 500) -> None:
        if log_file is None:
            root = Path(__file__).parent.parent
            (root / "log").mkdir(parents=True, exist_ok=True)
            log_file = root / "log" / "engine.log"
        self.log_file = Path(log_file)
        self.ring_size = ring_size
        self._ring: deque[EngineRecord] = deque(maxlen=ring_size)
        self._started = False

        self._logger = logging.getLogger("openm.engine")
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
        self._logger.info("EngineLogger started")

    def stop(self) -> None:
        if not self._started:
            return
        self._started = False
        self._logger.info("EngineLogger stopped")

    # -- public logging API -------------------------------------------------

    def log_recalc(self, detail: str, **meta: Any) -> None:
        self._append("recalc", detail, meta)
        self._logger.info(f"RCL | {detail}")

    def log_rule_eval(self, addr: str, rule: str, result: Any, **meta: Any) -> None:
        detail = f"{addr} = {rule} -> {result}"
        self._append("rule_eval", detail, meta)
        self._logger.debug(f"FEV | {detail}")

    def log_dirty_mark(self, addr: str, reason: str, **meta: Any) -> None:
        detail = f"{addr} reason={reason}"
        self._append("dirty_mark", detail, meta)
        self._logger.debug(f"DIR | {detail}")

    def log_dep_track(self, source: str, target: str, **meta: Any) -> None:
        detail = f"{source} -> {target}"
        self._append("dep_track", detail, meta)
        self._logger.debug(f"DEP | {detail}")

    def log_cell_change(self, addr: str, old_val: Any, new_val: Any, **meta: Any) -> None:
        detail = f"{addr} {old_val!r} -> {new_val!r}"
        self._append("cell_change", detail, meta)
        self._logger.info(f"CHG | {detail}")

    def log_error(self, detail: str, **meta: Any) -> None:
        self._append("error", detail, meta)
        self._logger.error(f"ERR | {detail}")

    # -- query API ----------------------------------------------------------

    def tail(self, n: int = 10) -> list[EngineRecord]:
        return list(self._ring)[-n:][::-1] if self._ring else []

    def filter_by_kind(self, kind: str, n: int = 10) -> list[EngineRecord]:
        matches = [r for r in self._ring if r.kind == kind]
        return matches[-n:][::-1]

    def clear(self) -> None:
        self._ring.clear()

    # -- internal -----------------------------------------------------------

    def _append(self, kind: str, detail: str, meta: dict[str, Any]) -> None:
        self._ring.append(EngineRecord(
            timestamp=time.perf_counter(),
            kind=kind,
            detail=detail,
            meta=meta,
        ))


def get_engine_logger(log_file: Path | str | None = None, ring_size: int = 500) -> EngineLogger:
    global _ENGINE_LOGGER_INSTANCE
    if _ENGINE_LOGGER_INSTANCE is None:
        _ENGINE_LOGGER_INSTANCE = EngineLogger(log_file=log_file, ring_size=ring_size)
    return _ENGINE_LOGGER_INSTANCE
