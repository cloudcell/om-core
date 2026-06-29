"""lib_contracts.discriminators — object-kind discrimination helpers.

Provides a uniform way for GUI code to identify what kind of object
it is dealing with without importing engine domain classes.
"""

from typing import Any


def object_kind(obj: Any) -> str | None:
    """Return the kind of object as a string, or None if unknown.

    Supported kinds (extensible):
        - "dimension"
        - "dimension_item"
        - "cube"
        - "view"
        - "rule"
        - "outline_node"
        - "cell_format"
        - "workspace"
    """
    if obj is None:
        return None

    # DTO objects with explicit kind field
    if isinstance(obj, dict):
        kind = obj.get("kind")
        if kind is not None:
            return kind
        # Fallback: _type discriminator used in some DTOs
        return obj.get("_type")

    # Engine domain objects — transitional while migration is in progress.
    # These isinstance checks are only for backward compatibility during
    # the GUI-to-engine decoupling transition. Once all callers pass DTOs
    # or dicts, these branches can be removed.
    module = getattr(type(obj), "__module__", "")
    name = type(obj).__name__

    if module.startswith("lib_openm"):
        kind_map = {
            "Dimension": "dimension",
            "DimensionItem": "dimension_item",
            "Cube": "cube",
            "TableViewSpec": "view",
            "Rule": "rule",
            "OutlineNode": "outline_node",
            "CellFormat": "cell_format",
            "Workspace": "workspace",
        }
        return kind_map.get(name)

    return None


def is_dimension_dto(obj: Any) -> bool:
    return object_kind(obj) == "dimension"


def is_dimension_item_dto(obj: Any) -> bool:
    return object_kind(obj) == "dimension_item"


def is_cube_dto(obj: Any) -> bool:
    return object_kind(obj) == "cube"


def is_view_dto(obj: Any) -> bool:
    return object_kind(obj) == "view"


def is_rule_dto(obj: Any) -> bool:
    return object_kind(obj) == "rule"


def is_outline_node_dto(obj: Any) -> bool:
    return object_kind(obj) == "outline_node"


def is_cell_format_dto(obj: Any) -> bool:
    return object_kind(obj) == "cell_format"


def is_workspace_dto(obj: Any) -> bool:
    return object_kind(obj) == "workspace"
