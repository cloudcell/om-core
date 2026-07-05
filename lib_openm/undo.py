from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Any
from collections import deque


class Action(Protocol):
    """Protocol for undoable actions."""
    description: str  # Human-readable description for UI

    def do(self) -> None: ...

    def undo(self) -> None: ...


@dataclass
class CompositeAction:
    """Combine multiple actions into one undoable operation."""
    actions: list[Action]
    description: str = "Multiple changes"

    def do(self) -> None:
        for a in self.actions:
            a.do()

    def undo(self) -> None:
        for a in reversed(self.actions):
            a.undo()


class UndoManager:
    """Manages undo/redo stacks with configurable memory limits.
    
    Uses Command pattern - each action knows how to execute and reverse itself.
    Memory efficient: only stores changes, not full state snapshots.
    """
    
    def __init__(self, max_history: int = 100) -> None:
        self._undo: deque[Action] = deque(maxlen=max_history)
        self._redo: deque[Action] = deque(maxlen=max_history)
        self._max_history = max_history
        self._group: list[Action] | None = None
        self._group_description: str = ""

    def start_group(self, description: str) -> None:
        """Start collecting actions into a group instead of pushing directly."""
        self._group = []
        self._group_description = description

    def end_group(self) -> None:
        """Push collected actions as a single CompositeAction."""
        if self._group:
            composite = CompositeAction(self._group, description=self._group_description)
            self._undo.append(composite)
            self._redo.clear()
        self._group = None
        self._group_description = ""

    def cancel_group(self) -> None:
        """Discard collected actions without pushing."""
        self._group = None
        self._group_description = ""

    def clear(self) -> None:
        """Clear both undo and redo stacks. Call on file open/new."""
        self._undo.clear()
        self._redo.clear()

    def push_and_do(self, action: Action) -> None:
        """Execute an action and add it to undo stack."""
        action.do()
        if self._group is not None:
            self._group.append(action)
        else:
            self._undo.append(action)
            self._redo.clear()

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> Action | None:
        """Undo last action and return it (for UI display)."""
        if not self._undo:
            return None
        a = self._undo.pop()
        a.undo()
        self._redo.append(a)
        return a

    def redo(self) -> Action | None:
        """Redo last undone action and return it (for UI display)."""
        if not self._redo:
            return None
        a = self._redo.pop()
        a.do()
        self._undo.append(a)
        return a

    def get_undo_description(self) -> str | None:
        """Get description of next undoable action for UI."""
        if not self._undo:
            return None
        return getattr(self._undo[-1], 'description', 'Unknown action')

    def get_redo_description(self) -> str | None:
        """Get description of next redoable action for UI."""
        if not self._redo:
            return None
        return getattr(self._redo[-1], 'description', 'Unknown action')


# =============================================================================
# Command Classes for All Operations
# =============================================================================

@dataclass
class SetCellValueCommand:
    """Command to set a cell value (override)."""
    engine: Any  # Engine reference
    view_id: str
    row_key: tuple[str, ...]
    col_key: tuple[str, ...]
    new_value: float | None
    old_value: float | None = field(default=None, repr=False)
    old_rule_body: str | None = field(default=None, repr=False)
    description: str = field(default="Change cell value", init=False)

    def __post_init__(self):
        # Capture old state on creation
        cell_ref = {"kind": "ids", "row_key": self.row_key, "col_key": self.col_key}
        try:
            cell = self.engine.get_cell_value(self.view_id, cell_ref)
            if cell:
                self.old_value = cell.value
                self.old_rule_body = cell.rule_body
        except (AttributeError, KeyError):
            pass  # Cell does not exist; old state remains None

    def do(self) -> None:
        cell_ref = {"kind": "ids", "row_key": self.row_key, "col_key": self.col_key}
        self.engine.set_cell_hardvalue(self.view_id, cell_ref, self.new_value)

    def undo(self) -> None:
        cell_ref = {"kind": "ids", "row_key": self.row_key, "col_key": self.col_key}
        if self.old_rule_body:
            self.engine.set_rule_anchored(self.view_id, cell_ref, self.old_rule_body)
        elif self.old_value is not None:
            self.engine.set_cell_hardvalue(self.view_id, cell_ref, self.old_value)
        else:
            # Clear the override by setting to None
            self.engine.set_cell_hardvalue(self.view_id, cell_ref, None)


@dataclass
class SetCellRuleCommand:
    """Command to set a cell rule."""
    engine: Any
    view_id: str
    row_key: tuple[str, ...]
    col_key: tuple[str, ...]
    new_rule_body: str | None
    old_rule_body: str | None = field(default=None, repr=False)
    old_value: float | None = field(default=None, repr=False)
    description: str = field(default="Set rule", init=False)

    def __post_init__(self):
        cell_ref = {"kind": "ids", "row_key": self.row_key, "col_key": self.col_key}
        try:
            cell = self.engine.get_cell_value(self.view_id, cell_ref)
            if cell:
                self.old_rule_body = cell.rule_body
                self.old_value = cell.value
        except (AttributeError, KeyError):
            pass  # Cell does not exist; old state remains None

    def do(self) -> None:
        cell_ref = {"kind": "ids", "row_key": self.row_key, "col_key": self.col_key}
        self.engine.set_rule_anchored(self.view_id, cell_ref, self.new_rule_body)

    def undo(self) -> None:
        cell_ref = {"kind": "ids", "row_key": self.row_key, "col_key": self.col_key}
        if self.old_rule_body:
            self.engine.set_rule_anchored(self.view_id, cell_ref, self.old_rule_body)
        elif self.old_value is not None:
            self.engine.set_cell_hardvalue(self.view_id, cell_ref, self.old_value)
        else:
            self.engine.set_cell_hardvalue(self.view_id, cell_ref, None)


@dataclass
class ApplyFormatCommand:
    """Command to apply cell formatting."""
    engine: Any
    cube_id: str
    address: tuple[str, ...]
    format_key: str  # e.g., "bg_color", "fg_color", "font_size", "bold", etc.
    new_value: Any
    old_value: Any = field(default=None, repr=False)
    description: str = field(default="Apply format", init=False)

    def __post_init__(self):
        self.description = f"Apply {self.format_key}"
        cube = self.engine._get_cube(self.cube_id)
        cell = self.engine._get_cell_by_addr(cube, self.address)
        if cell and cell.format:
            self.old_value = getattr(cell.format, self.format_key, None)

    def do(self) -> None:
        cube = self.engine._get_cube(self.cube_id)
        cell = self.engine._get_cell_by_addr(cube, self.address)
        if cell:
            if not cell.format:
                from lib_openm.model import CellFormat
                cell.format = CellFormat()
            setattr(cell.format, self.format_key, self.new_value)

    def undo(self) -> None:
        cube = self.engine._get_cube(self.cube_id)
        cell = self.engine._get_cell_by_addr(cube, self.address)
        if cell and cell.format:
            setattr(cell.format, self.format_key, self.old_value)


@dataclass
class AddDimensionItemCommand:
    """Command to add an item to a dimension."""
    engine: Any
    dim_id: str
    item_name: str
    item_id: str | None = field(default=None, repr=False)
    description: str = field(default="Add dimension item", init=False)

    def __post_init__(self):
        self.description = f"Add item '{self.item_name}'"

    def do(self) -> None:
        item = self.engine.create_dimension_item(self.dim_id, self.item_name)
        self.item_id = item.id

    def undo(self) -> None:
        if self.item_id:
            self.engine.delete_dimension_item(self.dim_id, self.item_id)


@dataclass
class DeleteDimensionItemCommand:
    """Command to delete a dimension item (with full restore info)."""
    engine: Any
    dim_id: str
    item_id: str
    # Stored for undo
    item_data: dict = field(default_factory=dict, repr=False)
    cube_overrides: dict = field(default_factory=dict, repr=False)
    description: str = field(default="Delete dimension item", init=False)

    def __post_init__(self):
        dim = self.engine.require_dimension_by_id(self.dim_id)
        item = dim.get_item(self.item_id)
        if item:
            self.item_data = {
                'id': item.id,
                'name': item.name,
                'sequence': item.sequence,
            }
            # Store any cube cell overrides that reference this item
            for cube in self.engine._ws.cubes.values():
                if self.dim_id in cube.dimension_ids:
                    # Find all cells using this item
                    for addr, cell in cube.cells.items():
                        if self.item_id in addr:
                            self.cube_overrides[(cube.id, addr)] = {
                                'value': cell.value,
                                'rule_body': cell.rule_body,
                                'format': cell.format,
                            }
        self.description = f"Delete item '{self.item_data.get('name', 'Unknown')}'"

    def do(self) -> None:
        self.engine.delete_dimension_item(self.dim_id, self.item_id)

    def undo(self) -> None:
        # Recreate the item
        from lib_openm.model import DimensionItem
        item = DimensionItem(
            id=self.item_data['id'],
            name=self.item_data['name'],
            sequence=self.item_data['sequence'],
        )
        dim = self.engine.require_dimension_by_id(self.dim_id)
        dim.items.append(item)
        dim.items.sort(key=lambda x: x.sequence)

        # Restore cell overrides
        for (cube_id, addr), data in self.cube_overrides.items():
            cube = self.engine._get_cube(cube_id)
            cell = self.engine._get_cell_by_addr(cube, addr)
            if cell:
                cell.value = data['value']
                cell.rule_body = data['rule_body']
                cell.format = data['format']


@dataclass
class RenameDimensionItemCommand:
    """Command to rename a dimension item."""
    engine: Any
    dim_id: str
    item_id: str
    new_name: str
    old_name: str = field(default="", repr=False)
    description: str = field(default="Rename item", init=False)

    def __post_init__(self):
        dim = self.engine.require_dimension_by_id(self.dim_id)
        item = dim.get_item(self.item_id)
        if item:
            self.old_name = item.name
        self.description = f"Rename '{self.old_name}' to '{self.new_name}'"

    def do(self) -> None:
        self.engine.rename_dimension_item(self.dim_id, self.item_id, self.new_name)

    def undo(self) -> None:
        self.engine.rename_dimension_item(self.dim_id, self.item_id, self.old_name)


@dataclass
class CreateDimensionCommand:
    """Command to create a new dimension."""
    engine: Any
    name: str
    dim_type: str = "set"
    dim_id: str | None = field(default=None, repr=False)
    description: str = field(default="Create dimension", init=False)

    def __post_init__(self):
        self.description = f"Create dimension '{self.name}'"

    def do(self) -> None:
        from lib_openm.model import Dimension
        dim = Dimension.create(self.name, dim_type=self.dim_type)
        self.dim_id = dim.id
        self.engine._ws.add_dimension(dim)

    def undo(self) -> None:
        if self.dim_id:
            self.engine._ws.dimensions.pop(self.dim_id, None)


@dataclass
class DeleteDimensionCommand:
    """Command to delete a dimension."""
    engine: Any
    dim_id: str
    dim_data: dict = field(default_factory=dict, repr=False)
    description: str = field(default="Delete dimension", init=False)

    def __post_init__(self):
        dim = self.engine.require_dimension_by_id(self.dim_id)
        if dim:
            self.dim_data = {
                'id': dim.id,
                'name': dim.name,
                'type': dim.type,
                'items': [(it.id, it.name, it.sequence) for it in dim.items],
            }
        self.description = f"Delete dimension '{dim.name if dim else 'Unknown'}'"

    def do(self) -> None:
        self.engine._ws.dimensions.pop(self.dim_id, None)

    def undo(self) -> None:
        from lib_openm.model import Dimension, DimensionItem
        dim = Dimension(
            id=self.dim_data['id'],
            name=self.dim_data['name'],
            type=self.dim_data['type'],
        )
        for item_id, name, seq in self.dim_data['items']:
            dim.items.append(DimensionItem(id=item_id, name=name, sequence=seq))
        self.engine._ws.add_dimension(dim)


@dataclass
class CreateCubeCommand:
    """Command to create a new cube."""
    engine: Any
    name: str
    dimension_ids: list[str]
    cube_id: str | None = field(default=None, repr=False)
    description: str = field(default="Create cube", init=False)

    def __post_init__(self):
        self.description = f"Create cube '{self.name}'"

    def do(self) -> None:
        from lib_openm.model import Cube
        cube = Cube.create(self.name, dimension_ids=self.dimension_ids)
        self.cube_id = cube.id
        self.engine._ws.add_cube(cube)

    def undo(self) -> None:
        if self.cube_id:
            self.engine._ws.cubes.pop(self.cube_id, None)


@dataclass
class DeleteCubeCommand:
    """Command to delete a cube (preserves all data)."""
    engine: Any
    cube_id: str
    cube_data: dict = field(default_factory=dict, repr=False)
    description: str = field(default="Delete cube", init=False)

    def __post_init__(self):
        cube = self.engine._get_cube(self.cube_id)
        if cube:
            self.cube_data = {
                'id': cube.id,
                'name': cube.name,
                'dimension_ids': list(cube.dimension_ids),
                'cells': {},
            }
            for addr, cell in cube.cells.items():
                self.cube_data['cells'][addr] = {
                    'value': cell.value,
                    'rule_body': cell.rule_body,
                    'format': cell.format,
                }
        self.description = f"Delete cube '{cube.name if cube else 'Unknown'}'"

    def do(self) -> None:
        self.engine._ws.cubes.pop(self.cube_id, None)

    def undo(self) -> None:
        from lib_openm.model import Cube, Cell
        cube = Cube(
            id=self.cube_data['id'],
            name=self.cube_data['name'],
            dimension_ids=self.cube_data['dimension_ids'],
        )
        for addr, data in self.cube_data['cells'].items():
            cell = Cell()
            cell.value = data['value']
            cell.rule_body = data['rule_body']
            cell.format = data['format']
            cube.cells[addr] = cell
        self.engine._ws.add_cube(cube)


@dataclass
class CreateViewCommand:
    """Command to create a new view."""
    engine: Any
    name: str
    cube_id: str
    row_dim_id: str
    col_dim_id: str
    view_id: str | None = field(default=None, repr=False)
    description: str = field(default="Create view", init=False)

    def __post_init__(self):
        self.description = f"Create view '{self.name}'"

    def do(self) -> None:
        from lib_openm.model import TableViewSpec
        view = TableViewSpec.create(self.name, self.cube_id, self.row_dim_id, self.col_dim_id)
        self.view_id = view.id
        self.engine._ws.add_view(view)

    def undo(self) -> None:
        if self.view_id:
            self.engine._ws.views.pop(self.view_id, None)


@dataclass
class DeleteViewCommand:
    """Command to delete a view."""
    engine: Any
    view_id: str
    view_data: dict = field(default_factory=dict, repr=False)
    description: str = field(default="Delete view", init=False)

    def __post_init__(self):
        view = self.engine._ws.views.get(self.view_id)
        if view:
            self.view_data = {
                'id': view.id,
                'name': view.name,
                'cube_id': view.cube_id,
                'row_dim_id': getattr(view, 'row_dim_id', None),
                'col_dim_id': getattr(view, 'col_dim_id', None),
                'row_outline': getattr(view, 'row_outline', []),
                'col_outline': getattr(view, 'col_outline', []),
            }
        self.description = f"Delete view '{view.name if view else 'Unknown'}'"

    def do(self) -> None:
        self.engine._ws.views.pop(self.view_id, None)

    def undo(self) -> None:
        from lib_openm.model import TableViewSpec
        view = TableViewSpec(
            id=self.view_data['id'],
            name=self.view_data['name'],
            cube_id=self.view_data['cube_id'],
            row_dim_id=self.view_data['row_dim_id'],
            col_dim_id=self.view_data['col_dim_id'],
        )
        view.row_outline = self.view_data.get('row_outline', [])
        view.col_outline = self.view_data.get('col_outline', [])
        self.engine._ws.add_view(view)


@dataclass
class RenameViewCommand:
    """Command to rename a view."""
    engine: Any
    view_id: str
    new_name: str
    old_name: str = field(default="", repr=False)
    description: str = field(default="Rename view", init=False)

    def __post_init__(self):
        view = self.engine._ws.views.get(self.view_id)
        if view:
            self.old_name = view.name
        self.description = f"Rename view to '{self.new_name}'"

    def do(self) -> None:
        view = self.engine._ws.views.get(self.view_id)
        if view:
            view.name = self.new_name

    def undo(self) -> None:
        view = self.engine._ws.views.get(self.view_id)
        if view:
            view.name = self.old_name


@dataclass
class MoveViewDimensionCommand:
    """Command to move a dimension to different axis."""
    engine: Any
    view_id: str
    dim_id: str
    dest: str  # "row", "col", or "page"
    old_row_id: str | None = field(default=None, repr=False)
    old_col_id: str | None = field(default=None, repr=False)
    old_page_ids: list[str] = field(default_factory=list, repr=False)
    description: str = field(default="Move dimension", init=False)

    def __post_init__(self):
        view = self.engine._ws.views.get(self.view_id)
        if view:
            self.old_row_id = getattr(view, 'row_dim_id', None)
            self.old_col_id = getattr(view, 'col_dim_id', None)
            self.old_page_ids = list(getattr(view, 'page_dim_ids', []))
        self.description = f"Move dimension to {self.dest}"

    def do(self) -> None:
        self.engine.move_view_dimension(self.view_id, self.dim_id, self.dest)

    def undo(self) -> None:
        view = self.engine._ws.views.get(self.view_id)
        if not view:
            return
        view.row_dim_id = self.old_row_id
        view.col_dim_id = self.old_col_id
        view.page_dim_ids = list(self.old_page_ids)


@dataclass
class SetViewAxesCommand:
    """Command to change view axes configuration."""
    engine: Any
    view_id: str
    new_row_dim_id: str
    new_col_dim_id: str
    old_row_dim_id: str | None = field(default=None, repr=False)
    old_col_dim_id: str | None = field(default=None, repr=False)
    description: str = field(default="Change view axes", init=False)

    def __post_init__(self):
        view = self.engine._ws.views.get(self.view_id)
        if view:
            self.old_row_dim_id = getattr(view, 'row_dim_id', None)
            self.old_col_dim_id = getattr(view, 'col_dim_id', None)

    def do(self) -> None:
        self.engine.set_view_axes(self.view_id, self.new_row_dim_id, self.new_col_dim_id)

    def undo(self) -> None:
        view = self.engine._ws.views.get(self.view_id)
        if view:
            view.row_dim_id = self.old_row_dim_id
            view.col_dim_id = self.old_col_dim_id


@dataclass
class InsertOutlineNodeCommand:
    """Command to insert a node into view outline."""
    engine: Any
    view_id: str
    axis: str  # "row" or "col"
    parent_path: tuple[int, ...]
    index: int
    node_data: dict  # {'label': str, 'item_id': str | None}
    description: str = field(default="Insert outline node", init=False)

    def __post_init__(self):
        self.description = f"Insert {self.axis} outline node"

    def do(self) -> None:
        view = self.engine._ws.views.get(self.view_id)
        if not view:
            return
        from lib_openm.model import OutlineNode
        outline = getattr(view, f'{self.axis}_outline', None)
        if outline is None:
            outline = []
            setattr(view, f'{self.axis}_outline', outline)
        # Insert at path
        self._insert_at_path(outline, self.parent_path, self.index, self.node_data)

    def undo(self) -> None:
        view = self.engine._ws.views.get(self.view_id)
        if not view:
            return
        outline = getattr(view, f'{self.axis}_outline', None)
        if outline:
            self._remove_at_path(outline, self.parent_path, self.index)

    def _insert_at_path(self, nodes: list, path: tuple[int, ...], index: int, data: dict) -> None:
        from lib_openm.model import OutlineNode
        if not path:
            node = OutlineNode(label=data.get('label', ''), item_id=data.get('item_id'))
            nodes.insert(index, node)
        else:
            self._insert_at_path(nodes[path[0]].children, path[1:], index, data)

    def _remove_at_path(self, nodes: list, path: tuple[int, ...], index: int) -> None:
        if not path:
            if index < len(nodes):
                nodes.pop(index)
        else:
            self._remove_at_path(nodes[path[0]].children, path[1:], index)


@dataclass
class DeleteOutlineNodeCommand:
    """Command to delete a node from view outline."""
    engine: Any
    view_id: str
    axis: str
    parent_path: tuple[int, ...]
    index: int
    deleted_node_data: dict = field(default_factory=dict, repr=False)
    description: str = field(default="Delete outline node", init=False)

    def __post_init__(self):
        self.description = f"Delete {self.axis} outline node"
        # Capture the node being deleted
        view = self.engine._ws.views.get(self.view_id)
        if view:
            node = self._get_node_at_path(
                getattr(view, f'{self.axis}_outline', []),
                self.parent_path, self.index
            )
            if node:
                self.deleted_node_data = {
                    'label': node.label,
                    'item_id': node.item_id,
                    'children': node.children,
                }

    def do(self) -> None:
        view = self.engine._ws.views.get(self.view_id)
        if not view:
            return
        outline = getattr(view, f'{self.axis}_outline', None)
        if outline:
            self._remove_at_path(outline, self.parent_path, self.index)

    def undo(self) -> None:
        view = self.engine._ws.views.get(self.view_id)
        if not view:
            return
        from lib_openm.model import OutlineNode
        outline = getattr(view, f'{self.axis}_outline', None)
        if outline is None:
            outline = []
            setattr(view, f'{self.axis}_outline', outline)
        node = OutlineNode(
            label=self.deleted_node_data.get('label', ''),
            item_id=self.deleted_node_data.get('item_id'),
            children=self.deleted_node_data.get('children', []),
        )
        self._insert_at_path(outline, self.parent_path, self.index, {
            'label': node.label,
            'item_id': node.item_id,
        })

    def _get_node_at_path(self, nodes: list, path: tuple[int, ...], index: int):
        if not path:
            if index < len(nodes):
                return nodes[index]
            return None
        return self._get_node_at_path(nodes[path[0]].children, path[1:], index)

    def _remove_at_path(self, nodes: list, path: tuple[int, ...], index: int) -> None:
        if not path:
            if index < len(nodes):
                nodes.pop(index)
        else:
            self._remove_at_path(nodes[path[0]].children, path[1:], index)

    def _insert_at_path(self, nodes: list, path: tuple[int, ...], index: int, data: dict) -> None:
        from lib_openm.model import OutlineNode
        if not path:
            node = OutlineNode(label=data.get('label', ''), item_id=data.get('item_id'))
            nodes.insert(index, node)
        else:
            self._insert_at_path(nodes[path[0]].children, path[1:], index, data)


