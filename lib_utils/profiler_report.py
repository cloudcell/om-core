"""Formatter for GUI profiler span snapshots."""

from __future__ import annotations

from typing import Any


def format_profiler_report(
    snapshot: dict[str, dict[str, Any]],
    title: str = "grid profile (last <N>s)",
) -> str:
    """Render an indented span table from a flat snapshot dict.

    Roots and children are sorted by ``total_ms`` descending. Ties break by
    span name alphabetically. Spans that reference a missing parent are
    rendered as roots. Values are formatted to two decimal places.
    """
    if not snapshot:
        lines = [title, _header_line([])]
        return "\n".join(lines)

    # Build parent -> children map
    children_by_parent: dict[str | None, list[str]] = {}
    for name, record in snapshot.items():
        parent = record.get("parent")
        if parent is not None and parent not in snapshot:
            parent = None
        children_by_parent.setdefault(parent, []).append(name)

    roots = children_by_parent.get(None, [])
    roots.sort(key=lambda n: (-snapshot[n]["total_ms"], n))

    # Gather all rows (name + indent) so column widths reflect actual content.
    max_depth = 0
    rows: list[tuple[int, str, dict[str, Any]]] = []

    def _collect(names: list[str], indent: int) -> None:
        nonlocal max_depth
        max_depth = max(max_depth, indent)
        for name in names:
            rows.append((indent, name, snapshot[name]))
            children = children_by_parent.get(name, [])
            children.sort(key=lambda n: (-snapshot[n]["total_ms"], n))
            _collect(children, indent + 1)

    _collect(roots, 0)

    indent_width = 2
    max_name_width = max(len(name) for name in snapshot.keys()) if snapshot else 0
    span_width = max(max_name_width + max_depth * indent_width, len("Span"))

    # Compute numeric column widths from actual formatted values plus header lengths.
    counts = [r["count"] for _, _, r in rows]
    avgs = [r["avg_ms"] for _, _, r in rows]
    excls = [r["exclusive_ms"] for _, _, r in rows]
    totals = [r["total_ms"] for _, _, r in rows]
    mins = [r["min_ms"] for _, _, r in rows]
    maxs = [r["max_ms"] for _, _, r in rows]

    col_widths = {
        "span": span_width,
        "calls": max(len("Calls"), max((len(str(v)) for v in counts), default=0)),
        "avg": max(len("Avg (ms)"), max((len(f"{v:.2f}") for v in avgs), default=0)),
        "excl": max(len("Excl (ms)"), max((len(f"{v:.2f}") for v in excls), default=0)),
        "total": max(len("Total (ms)"), max((len(f"{v:.2f}") for v in totals), default=0)),
        "min": max(len("Min (ms)"), max((len(f"{v:.2f}") for v in mins), default=0)),
        "max": max(len("Max (ms)"), max((len(f"{v:.2f}") for v in maxs), default=0)),
    }
    gap = 2

    lines = [title]
    lines.append(
        "Span".ljust(col_widths["span"])
        + " " * gap
        + "Calls".rjust(col_widths["calls"])
        + " " * gap
        + "Avg (ms)".rjust(col_widths["avg"])
        + " " * gap
        + "Excl (ms)".rjust(col_widths["excl"])
        + " " * gap
        + "Total (ms)".rjust(col_widths["total"])
        + " " * gap
        + "Min (ms)".rjust(col_widths["min"])
        + " " * gap
        + "Max (ms)".rjust(col_widths["max"])
    )

    def _format_row(indent: int, name: str, record: dict[str, Any]) -> str:
        span_col = "  " * indent + name
        return (
            span_col.ljust(col_widths["span"])
            + " " * gap
            + f"{record['count']}".rjust(col_widths["calls"])
            + " " * gap
            + f"{record['avg_ms']:.2f}".rjust(col_widths["avg"])
            + " " * gap
            + f"{record['exclusive_ms']:.2f}".rjust(col_widths["excl"])
            + " " * gap
            + f"{record['total_ms']:.2f}".rjust(col_widths["total"])
            + " " * gap
            + f"{record['min_ms']:.2f}".rjust(col_widths["min"])
            + " " * gap
            + f"{record['max_ms']:.2f}".rjust(col_widths["max"])
        )

    for indent, name, record in rows:
        lines.append(_format_row(indent, name, record))

    return "\n".join(lines)


def _header_line(col_widths: dict[str, int]) -> str:
    # Fallback when snapshot is empty; use sensible defaults.
    if not col_widths:
        col_widths = {
            "span": 36,
            "calls": 8,
            "avg": 10,
            "excl": 11,
            "total": 12,
            "min": 10,
            "max": 10,
        }
    gap = 2
    return (
        "Span".ljust(col_widths["span"])
        + " " * gap
        + "Calls".rjust(col_widths["calls"])
        + " " * gap
        + "Avg (ms)".rjust(col_widths["avg"])
        + " " * gap
        + "Excl (ms)".rjust(col_widths["excl"])
        + " " * gap
        + "Total (ms)".rjust(col_widths["total"])
        + " " * gap
        + "Min (ms)".rjust(col_widths["min"])
        + " " * gap
        + "Max (ms)".rjust(col_widths["max"])
    )
