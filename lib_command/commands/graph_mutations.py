"""Command payloads for Phase 8 GUI mutation commands.

These dataclasses are pure data — no behaviour. The dispatcher maps
each command type to a topic string and a handler function.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RenameGroupNodeCommand:
    dim_id: str
    node_id: str
    new_label: str


@dataclass(frozen=True)
class DeleteGroupNodeCommand:
    dim_id: str
    node_id: str
    promote_children: str = "to_parent"


@dataclass(frozen=True)
class MoveNodesCommand:
    dim_id: str
    node_ids: list[str]
    parent_node_id: str | None
    anchor_node_id: str | None = None
    position: str = "after"
    move_empty_parents: bool = True


@dataclass(frozen=True)
class AddAggregateItemCommand:
    dim_id: str
    group_node_id: str
    name: str


@dataclass(frozen=True)
class PlaceItemNodesCommand:
    dim_id: str
    item_ids: list[str]
    parent_node_id: str | None
    anchor_node_id: str | None = None
    position: str = "after"


@dataclass(frozen=True)
class RenameDimensionItemCommand:
    dim_id: str
    item_id: str
    new_name: str


@dataclass(frozen=True)
class RenameCubeCommand:
    cube_id: str
    new_name: str


@dataclass(frozen=True)
class RenameDimensionCommand:
    dim_id: str
    new_name: str


@dataclass(frozen=True)
class RenameViewCommand:
    view_id: str
    new_name: str


@dataclass(frozen=True)
class DeleteViewCommand:
    view_id: str


@dataclass(frozen=True)
class DetachDimensionFromCubeCommand:
    cube_id: str
    dim_id: str


@dataclass(frozen=True)
class CreateGroupCommand:
    dim_id: str
    label: str
    parent_group_id: str | None = None
    parent_group_label: str | None = None
    child_item_ids: list[str] | None = None


@dataclass(frozen=True)
class AddDimensionItemCommand:
    dim_id: str
    name: str
    position: str = "append"
