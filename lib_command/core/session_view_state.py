"""SessionViewState — per-session interaction state for view, cursor, and selection.

Runtime live selection / cursor / active-view state.  Not canonical workspace data.
See plan-20260605-0027--session-view-state-refactor.md for architecture.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SelectionRange:
    """Compact rectangular selection, not a materialised cell set."""

    start_row: int
    start_col: int
    end_row: int
    end_col: int

    def __post_init__(self) -> None:
        # Normalise so start <= end
        if self.start_row > self.end_row:
            self.start_row, self.end_row = self.end_row, self.start_row
        if self.start_col > self.end_col:
            self.start_col, self.end_col = self.end_col, self.start_col


@dataclass
class SessionViewState:
    """Per-session view interaction state.  One instance per session in SessionStore."""

    session_id: str
    active_view_id: str | None = None
    cursor_row: int = 0
    cursor_col: int = 0
    anchor_row: int = 0
    anchor_col: int = 0
    selection_mode: str = "cell"          # "cell" | "row" | "col" | "range"
    selection_ranges: list[SelectionRange] = field(default_factory=list)
    selected_indices: list[tuple[int, int] | int] = field(default_factory=list)
    page_selections: dict[str, str] = field(default_factory=dict)
    scroll_x: int = 0
    scroll_y: int = 0

    @property
    def active_cell(self) -> tuple[int, int] | None:
        return (self.cursor_row, self.cursor_col)

    @active_cell.setter
    def active_cell(self, value: tuple[int, int] | None) -> None:
        if value is None:
            self.cursor_row = 0
            self.cursor_col = 0
        else:
            self.cursor_row, self.cursor_col = value

    @property
    def scroll_pos(self) -> tuple[int, int]:
        return (self.scroll_x, self.scroll_y)

    @scroll_pos.setter
    def scroll_pos(self, value: tuple[int, int] | None) -> None:
        if value is None:
            self.scroll_x = 0
            self.scroll_y = 0
        else:
            self.scroll_x, self.scroll_y = value

    @property
    def anchor_cell(self) -> tuple[int, int]:
        return (self.anchor_row, self.anchor_col)

    @anchor_cell.setter
    def anchor_cell(self, value: tuple[int, int] | None) -> None:
        if value is None:
            self.anchor_row = 0
            self.anchor_col = 0
        else:
            self.anchor_row, self.anchor_col = value

    def clamp_to_grid(self, max_row: int, max_col: int) -> None:
        """Clamp cursor and anchor to valid grid bounds."""
        self.cursor_row = max(0, min(self.cursor_row, max_row))
        self.cursor_col = max(0, min(self.cursor_col, max_col))
        self.anchor_row = max(0, min(self.anchor_row, max_row))
        self.anchor_col = max(0, min(self.anchor_col, max_col))

        # Clamp selection ranges
        clamped: list[SelectionRange] = []
        for r in self.selection_ranges:
            sr = max(0, min(r.start_row, max_row))
            sc = max(0, min(r.start_col, max_col))
            er = max(0, min(r.end_row, max_row))
            ec = max(0, min(r.end_col, max_col))
            if sr <= er and sc <= ec:
                clamped.append(SelectionRange(sr, sc, er, ec))
        self.selection_ranges = clamped
