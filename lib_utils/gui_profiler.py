"""Lightweight GUI span profiler with aggregate duration statistics.

The profiler is intentionally cheap when inactive: ``span(...)`` performs a
single boolean check and returns a shared no-op context manager. No lock, no
timestamp, and no allocation happen on hot GUI paths unless profiling is
actively running.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Optional


class _NoopSpan:
    """Shared context manager used when profiling is inactive.

    Can also be used as a stand-in for ``profiler.span`` so callers do not
    need to branch on whether a profiler is wired.
    """

    def __enter__(self) -> "_NoopSpan":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        return None

    def __call__(self, name: str, parent: Any = None) -> "_NoopSpan":
        return self


NOOP_SPAN = _NoopSpan()


class _ActiveSpan:
    """Context manager that records an active span."""

    __slots__ = ("_profiler", "_name", "_parent", "_start_ns")

    def __init__(self, profiler: "GuiProfiler", name: str, parent: Optional[str]) -> None:
        self._profiler = profiler
        self._name = name
        self._parent = parent
        self._start_ns = 0

    def __enter__(self) -> "_ActiveSpan":
        self._start_ns = time.perf_counter_ns()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        elapsed_ms = (time.perf_counter_ns() - self._start_ns) / 1_000_000.0
        self._profiler._record(self._name, self._parent, elapsed_ms)


class GuiProfiler:
    """Aggregates span durations for GUI data display operations.

    Only records while ``start_profiling()`` has been called and
    ``stop_profiling()`` has not yet been called. When inactive, the
    overhead of ``span(...)`` is negligible.
    """

    def __init__(self, endpoint_id: str) -> None:
        self.endpoint_id = endpoint_id
        self._active = False
        self._lock = threading.Lock()
        self._table: dict[str, dict[str, Any]] = {}
        # Per-thread span stacks and per-thread child totals.
        self._local = threading.local()

    def start_profiling(self) -> None:
        """Start a fresh profiling session."""
        with self._lock:
            self._table.clear()
            self._active = True
        # Discard old per-thread state; new threads will get fresh locals.
        self._local = threading.local()

    def stop_profiling(self) -> None:
        """Stop profiling. Does not clear data so snapshot() can be called."""
        with self._lock:
            self._active = False

    def is_active(self) -> bool:
        """Return whether profiling is currently running."""
        return self._active

    def span(self, name: str, parent: Optional[str] = None) -> Any:
        """Return a context manager for the named span.

        If ``parent`` is provided, it overrides the current per-thread stack
        top. If ``parent`` is ``None`` and the stack is empty, the span has no
        parent. If profiling is inactive, a shared no-op is returned.
        """
        if not self._active:
            return NOOP_SPAN

        stack = self._get_stack()
        resolved_parent = parent if parent is not None else (stack[-1] if stack else None)
        stack.append(name)
        return _ActiveSpan(self, name, resolved_parent)

    def _get_stack(self) -> list[str]:
        stack = getattr(self._local, "stack", None)
        if stack is None:
            self._local.stack = stack = []
        return stack

    def _get_child_totals(self) -> dict[str, float]:
        totals = getattr(self._local, "child_totals", None)
        if totals is None:
            self._local.child_totals = totals = {}
        return totals

    def _record(self, name: str, parent: Optional[str], elapsed_ms: float) -> None:
        stack = self._get_stack()
        # Pop before recording so the child totals are updated correctly.
        if stack and stack[-1] == name:
            stack.pop()
        child_totals = self._get_child_totals()
        with self._lock:
            record = self._table.get(name)
            if record is None:
                record = {
                    "parent": parent,
                    "count": 0,
                    "total_ms": 0.0,
                    "min_ms": float("inf"),
                    "max_ms": 0.0,
                    "_same_thread_child_total_ms": 0.0,
                }
                self._table[name] = record
            record["count"] += 1
            record["total_ms"] += elapsed_ms
            if elapsed_ms < record["min_ms"]:
                record["min_ms"] = elapsed_ms
            if elapsed_ms > record["max_ms"]:
                record["max_ms"] = elapsed_ms
            # Consume child totals accumulated for this span on this thread.
            child_total = child_totals.pop(name, 0.0)
            record["_same_thread_child_total_ms"] += child_total
            # Add this span's elapsed time to its parent's same-thread child total.
            if parent is not None:
                child_totals[parent] = child_totals.get(parent, 0.0) + elapsed_ms

    def current_span_name(self) -> Optional[str]:
        """Return the current per-thread span stack top, or None."""
        if not self._active:
            return None
        stack = getattr(self._local, "stack", None)
        if not stack:
            return None
        return stack[-1]

    def snapshot(self) -> dict[str, dict[str, Any]]:
        """Return a flat mapping of span name -> aggregate stats.

        ``avg_ms`` and ``exclusive_ms`` are derived here so that runtime span
        recording stays cheap. Exclusive time subtracts only same-thread
        child totals; cross-thread logical parents do not have their child
        time subtracted.
        """
        with self._lock:
            result = {}
            for name, record in self._table.items():
                count = record["count"]
                total = record["total_ms"]
                child_total = record["_same_thread_child_total_ms"]
                exclusive = max(0.0, total - child_total)
                avg = total / count if count > 0 else 0.0
                result[name] = {
                    "parent": record["parent"],
                    "count": count,
                    "total_ms": total,
                    "avg_ms": avg,
                    "exclusive_ms": exclusive,
                    "min_ms": record["min_ms"] if record["min_ms"] != float("inf") else 0.0,
                    "max_ms": record["max_ms"],
                }
            return result
