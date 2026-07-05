"""Workspace DTO schemas — TypedDict definitions for view/cube/workspace snapshots.

These schemas define the boundary contract between engine data and GUI state.
No engine domain objects cross this boundary — only plain dicts with primitive
types.

Import:
    from lib_openm.dto.workspace import ViewSnapshotDTO, WorkspaceSnapshotDTO
"""

from __future__ import annotations

from typing import TypedDict


class ViewLayoutDTO(TypedDict):
    """Neutral layout shape for view dimension placement."""

    rows: list[str]
    cols: list[str]
    page: list[str]


class CellFormatDTO(TypedDict):
    """Plain-dict serialization of a cell format. Never contains engine objects."""

    bg_color: str | None
    font_color: str | None
    font_family: str | None
    font_size: int | None
    font_weight: int
    font_italic: bool
    format_number: str
    format_text: str
    format_null: str
    format_error: str
    text_h_align: str
    text_v_align: str
    text_indent: int
    text_wrap: bool
    text_rotation: int
    border_top: str
    border_bottom: str
    border_left: str
    border_right: str
    border_style: str
    border_color: str


class ViewSnapshotDTO(TypedDict):
    """Snapshot of a single view's state. Never contains engine objects."""

    id: str
    cube_id: str
    row_dim_ids: list[str]
    col_dim_ids: list[str]
    page_dim_ids: list[str]
    layout: ViewLayoutDTO
    name: str
    # Formatting and sizing fields (F6e.2: migrated from direct engine reads)
    item_formats: dict[str, CellFormatDTO]
    group_formats: dict[str, CellFormatDTO]
    cell_formats: dict[str, CellFormatDTO]
    col_widths: dict[int, int]
    row_header_widths: dict[int, int]


class CubeSnapshotDTO(TypedDict):
    """Snapshot of a single cube's state. Never contains engine objects."""

    id: str
    dimension_ids: list[str]
    name: str
    user_override_count: int


class DimensionItemDTO(TypedDict):
    """Minimal dimension item snapshot."""

    id: str
    name: str


class DimensionSnapshotDTO(TypedDict):
    """Snapshot of a single dimension's state. Never contains engine objects."""

    id: str
    name: str
    dim_type: str
    item_count: int
    item_ids: list[str]
    item_names: list[str]
    items: list[DimensionItemDTO]
    outline: list[dict]


class WorkspaceSummaryDTO(TypedDict):
    """Lightweight workspace state: IDs only, no DTOs. Used for quick queries."""

    saved_default_view_id: str | None
    view_ids: list[str]
    cube_ids: list[str]


class WorkspaceSnapshotDTO(TypedDict):
    """Full workspace state: IDs + view/cube/dimension DTOs. Used for bootstrap.

    IMPORTANT: view_snapshots, cube_snapshots, and dimension_snapshots are
    REQUIRED, not optional. The entire purpose of workspace_snapshot is full
    hydration. If these maps are missing or empty, bootstrap produces an empty
    ViewModel.
    """

    id: str
    saved_default_view_id: str | None
    view_ids: list[str]
    cube_ids: list[str]
    dimension_ids: list[str]
    view_snapshots: dict[str, ViewSnapshotDTO]
    cube_snapshots: dict[str, CubeSnapshotDTO]
    dimension_snapshots: dict[str, DimensionSnapshotDTO]