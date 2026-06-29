"""REPL Logger — Dedicated observability for the interactive shell.

Captures every command typed, every response, every error, and every
history operation.  Written to its own file so it can eventually be
lifted out into a standalone REPL service.

Usage:
    from lib_command.core.repl_logger import get_repl_logger
    rl = get_repl_logger()
    rl.start()
    rl.log_input("cube C dim1 dim2")
    rl.log_output("Cube C created")
    rl.log_error("Unknown command: foo")
    recent = rl.tail(10)
    rl.stop()
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

_REPL_LOGGER_INSTANCE: Optional[REPLLogger] = None


@dataclass(frozen=True)
class REPLRecord:
    timestamp: float
    kind: str  # 'input', 'output', 'error', 'history', 'completion'
    text: str
    meta: dict[str, Any] = field(default_factory=dict)


class REPLLogger:
    """Logger for the Read-Eval-Print Loop.

    Attributes:
        log_file: Path to the dedicated REPL log (default: ./log/repl.log)
        ring_size: In-memory buffer size for fast tail()
    """

    def __init__(self, log_file: Path | str | None = None, ring_size: int = 200) -> None:
        if log_file is None:
            root = Path(__file__).parent.parent.parent
            (root / "log").mkdir(parents=True, exist_ok=True)
            log_file = root / "log" / "repl.log"
        self.log_file = Path(log_file)
        self.ring_size = ring_size
        self._ring: deque[REPLRecord] = deque(maxlen=ring_size)
        self._started = False

        self._logger = logging.getLogger("openm.repl")
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
        self._logger.info("REPLLogger started")

    def stop(self) -> None:
        if not self._started:
            return
        self._started = False
        self._logger.info("REPLLogger stopped")

    # -- public logging API -------------------------------------------------

    def log_input(self, text: str) -> None:
        self._append("input", text)
        self._logger.info(f"IN  | {text}")

    def log_output(self, text: str) -> None:
        self._append("output", text)
        self._logger.info(f"OUT | {text}")

    def log_error(self, text: str) -> None:
        self._append("error", text)
        self._logger.error(f"ERR | {text}")

    def log_history(self, action: str, command: str) -> None:
        self._append("history", command, meta={"action": action})
        self._logger.debug(f"HIST | {action}: {command}")

    def log_completion(self, prefix: str, matches: list[str]) -> None:
        self._append("completion", prefix, meta={"matches": matches})
        self._logger.debug(f"COMP | {prefix} -> {matches}")

    # -- query API ----------------------------------------------------------

    def tail(self, n: int = 10) -> list[REPLRecord]:
        return list(self._ring)[-n:][::-1] if self._ring else []

    def filter_by_kind(self, kind: str, n: int = 10) -> list[REPLRecord]:
        matches = [r for r in self._ring if r.kind == kind]
        return matches[-n:][::-1]

    def clear(self) -> None:
        self._ring.clear()

    # -- internal -----------------------------------------------------------

    def _append(self, kind: str, text: str, meta: Optional[dict] = None) -> None:
        self._ring.append(REPLRecord(
            timestamp=time.perf_counter(),
            kind=kind,
            text=text,
            meta=meta or {},
        ))


def get_repl_logger(log_file: Path | str | None = None, ring_size: int = 200) -> REPLLogger:
    global _REPL_LOGGER_INSTANCE
    if _REPL_LOGGER_INSTANCE is None:
        _REPL_LOGGER_INSTANCE = REPLLogger(log_file=log_file, ring_size=ring_size)
    return _REPL_LOGGER_INSTANCE
