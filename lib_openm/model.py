from __future__ import annotations

from dataclasses import dataclass, field
import os
import random
import string
from typing import Any

from lib_openm.rule_eval import Rule
from lib_utils.ids import new_id

# Debug flag for rule matching
_DEBUG_RULE_MATCH = bool(int(os.environ.get("OPENM_DEBUG_RULE_MATCH", "0")))

from lib_contracts.types import CellFormat, OutlineNode, get_value_type, TECHNICAL_CHANNELS
from lib_openm.technical_ids import (
    AT_PREFIX,
    AT_ID_TO_CHANNEL,
    CHANNEL_TO_AT_ID,
    normalize_technical_item_id,
    normalize_addr,
)


@dataclass(frozen=True)
class DimensionItem:
    id: str
    name: str


@dataclass
class Dimension:
    id: str
    name: str
    items: list[DimensionItem] = field(default_factory=list)
    outline: list["OutlineNode"] = field(default_factory=list)
    dim_type: str = "set"  # "set" (unordered) or "seq" (ordered, only extend at ends)
    is_technical: bool = False  # True for system dimensions like '@' (cannot rename/delete)
    _outline_cache: list["OutlineNode"] | None = field(default=None, repr=False)
    # Sparse root-level order overrides for ungrouped items.
    # Key: item_id, Value: int order (lower = earlier).
    _root_order_override: dict[str, int] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        object.__setattr__(self, "_outline_frozen", True)

    def invalidate_outline_cache(self) -> None:
        """Mark cached outline as stale. Next read will rebuild."""
        object.__setattr__(self, "_outline_cache", None)

    def __setattr__(self, name, value):
        if name == "outline" and getattr(self, "_outline_frozen", False):
            raise AttributeError(
                "dim.outline is read-only in Phase 4. Use graph primitives to mutate hierarchy."
            )
        super().__setattr__(name, value)

    @staticmethod
    def create(name: str, dim_type: str = "set", is_technical: bool = False) -> "Dimension":
        dim_type = dim_type if dim_type in ("set", "seq") else "set"
        return Dimension(id=new_id("dim"), name=name, dim_type=dim_type, is_technical=is_technical)

    def add_item(self, name: str, position: str = "append") -> DimensionItem:
        # Check for duplicate names (case-insensitive, trimmed)
        clean_name = name.strip().casefold()
        for it in self.items:
            if it.name.strip().casefold() == clean_name:
                raise ValueError(f"Duplicate item name in dimension '{self.name}': {name}")
        item = DimensionItem(id=new_id("item"), name=name.strip())
        if self.dim_type == "seq" and position == "prepend":
            self.items.insert(0, item)
        else:
            self.items.append(item)
        self.invalidate_outline_cache()
        return item

    def item_index(self, item_id: str) -> int:
        for i, it in enumerate(self.items):
            if it.id == item_id:
                return i
        raise KeyError(item_id)


@dataclass
class Cube:
    id: str
    name: str
    dimension_ids: list[str]
    # Sparse storage: key is tuple of item_ids aligned to dimension_ids (including @ dimension)
    # Address format: ("at_value", dim1_item, dim2_item, ...) for values
    #                  ("at_fill", dim1_item, dim2_item, ...) for background color, etc.
    data: dict[tuple[str, ...], Any] = field(default_factory=dict)
    # Track addresses where user explicitly entered a value (override)
    # Addresses are full tuples including @ dimension coordinate
    user_override_addrs: set[tuple[str, ...]] = field(default_factory=set)
    # Store base values for cells that have rules - used during rule evaluation
    # to ensure rules reference original values, not computed values
    base_values: dict[tuple[str, ...], Any] = field(default_factory=dict)

    @staticmethod
    def create(name: str, dimension_ids: list[str]) -> "Cube":
        # Auto-add @ dimension at the start if not present
        dim_ids = list(dimension_ids)
        if "@" not in dim_ids:
            dim_ids.insert(0, "@")
        return Cube(id=new_id("cube"), name=name, dimension_ids=dim_ids)

    def __contains__(self, addr: tuple[str, ...]) -> bool:
        """Check if address exists in cube data. Supports both old and new address formats."""
        # Try full address first
        if addr in self.data:
            return True
        
        # Normalize legacy @.value/@.fill etc. to canonical at_ prefix in @ dimension slot
        if "@" in self.dimension_ids and len(addr) == len(self.dimension_ids):
            at_idx = self.dimension_ids.index("@")
            if addr[at_idx].startswith("@."):
                normalized_addr = addr[:at_idx] + (normalize_technical_item_id(addr[at_idx]),) + addr[at_idx + 1:]
                if normalized_addr in self.data:
                    return True
        
        # Backward compatibility: if @ dimension exists and address is shorter, check with at_value prepended
        if "@" in self.dimension_ids and len(addr) < len(self.dimension_ids):
            padded_addr = (CHANNEL_TO_AT_ID["value"], *addr)
            if padded_addr in self.data:
                return True

        # Also check if a longer address matches a shorter key (reverse of above)
        if "@" in self.dimension_ids and len(addr) == len(self.dimension_ids):
            channel = self.get_channel_from_addr(addr)
            if channel == "value":
                at_idx = self.dimension_ids.index("@")
                short_addr = addr[:at_idx] + addr[at_idx + 1:]
                if short_addr in self.data:
                    return True

        return False

    def is_user_override(self, addr: tuple[str, ...]) -> bool:
        """Check if address is a user override (hardnumber). Supports both old and new address formats."""
        # Try full address first
        if addr in self.user_override_addrs:
            return True
        
        # Normalize legacy @.value/@.fill etc. to canonical at_ prefix in @ dimension slot
        if "@" in self.dimension_ids and len(addr) == len(self.dimension_ids):
            at_idx = self.dimension_ids.index("@")
            if addr[at_idx].startswith("@."):
                normalized_addr = addr[:at_idx] + (normalize_technical_item_id(addr[at_idx]),) + addr[at_idx + 1:]
                if normalized_addr in self.user_override_addrs:
                    return True

        # Backward compatibility: if @ dimension exists and address is shorter, check with at_value prepended
        if "@" in self.dimension_ids and len(addr) < len(self.dimension_ids):
            padded_addr = (CHANNEL_TO_AT_ID["value"], *addr)
            if padded_addr in self.user_override_addrs:
                return True

        # Also check if a longer address matches a shorter key (reverse of above)
        if "@" in self.dimension_ids and len(addr) == len(self.dimension_ids):
            channel = self.get_channel_from_addr(addr)
            if channel == "value":
                at_idx = self.dimension_ids.index("@")
                short_addr = addr[:at_idx] + addr[at_idx + 1:]
                if short_addr in self.user_override_addrs:
                    return True

        # Handle case where stored addresses have at_value prefix but cube doesn't have @ dimension
        # This can happen with *.* wildcard aggregation on cubes without @ dimension
        if "@" not in self.dimension_ids:
            # Check if any stored address ends with the query addr (has at_ prefix)
            for stored_addr in self.user_override_addrs:
                if len(stored_addr) == len(addr) + 1 and stored_addr[0].startswith(AT_PREFIX):
                    # Stored addr has at_ prefix, check if rest matches
                    if stored_addr[1:] == addr:
                        return True

        return False

    def get(self, addr: tuple[str, ...]) -> Any:
        """Get value at address. Supports both old (N-tuple) and new (N+1-tuple with at_value) formats."""
        # Try full address first
        if addr in self.data:
            return self.data[addr]
        
        # Normalize legacy @.value/@.fill etc. to canonical at_ prefix in @ dimension slot
        if "@" in self.dimension_ids and len(addr) == len(self.dimension_ids):
            at_idx = self.dimension_ids.index("@")
            if addr[at_idx].startswith("@."):
                normalized_addr = addr[:at_idx] + (normalize_technical_item_id(addr[at_idx]),) + addr[at_idx + 1:]
                if normalized_addr in self.data:
                    return self.data[normalized_addr]
        
        # Backward compatibility: if @ dimension exists and address is shorter, try with at_value prepended
        if "@" in self.dimension_ids and len(addr) < len(self.dimension_ids):
            padded_addr = (CHANNEL_TO_AT_ID["value"], *addr)
            return self.data.get(padded_addr)

        return None

    def set(self, addr: tuple[str, ...], value: Any) -> None:
        """Set value at address. Supports both old (N-tuple) and new (N+1-tuple with at_value) formats.

        DEPRECATED: Using N-tuple addresses without @ dimension is deprecated and will be removed.
        Migrate to full addresses including at_{channel} coordinate.
        """
        # Backward compatibility: if @ dimension exists and address is shorter, insert at_value
        if "@" in self.dimension_ids and len(addr) < len(self.dimension_ids):
            at_idx = self.dimension_ids.index("@")
            addr = addr[:at_idx] + (CHANNEL_TO_AT_ID["value"],) + addr[at_idx:]
        
        # Normalize legacy @.value/@.fill etc. to canonical at_ prefix in @ dimension slot
        if "@" in self.dimension_ids and len(addr) == len(self.dimension_ids):
            at_idx = self.dimension_ids.index("@")
            if addr[at_idx].startswith("@."):
                addr = addr[:at_idx] + (normalize_technical_item_id(addr[at_idx]),) + addr[at_idx + 1:]
        
        if value is None:
            self.data.pop(addr, None)
        else:
            self.data[addr] = value

    def migrate_data_for_new_dimensions(self, ws: "Workspace") -> None:
        """Migrate data and user_override_addrs when dimensions are added.
        
        This should be called after adding dimensions to the cube.
        Old N-dimensional addresses are padded to match new dimensionality
        using first items of new dimensions.
        """
        expected_dims = len(self.dimension_ids)
        
        # Migrate cube.data - only pad with DEFAULT (first) item of new dimensions
        if self.data and any(len(addr) < expected_dims for addr in list(self.data.keys())):
            migrated_data: dict[tuple[str, ...], Any] = {}
            for old_addr, value in list(self.data.items()):
                if len(old_addr) < expected_dims:
                    padded = list(old_addr)
                    for i in range(len(old_addr), expected_dims):
                        dim_id = self.dimension_ids[i]
                        dim = ws.dimensions.get(dim_id)
                        if dim and dim.items:
                            # Only use default (first) item for data
                            padded.append(dim.items[0].id)
                        else:
                            padded.append("")
                    migrated_data[tuple(padded)] = value
                else:
                    migrated_data[old_addr] = value
            self.data = migrated_data
        
        # Migrate user_override_addrs - only pad with DEFAULT (first) item of new dimensions
        # Hardcoded values should only appear at the default intersection
        if self.user_override_addrs and any(len(addr) < expected_dims for addr in list(self.user_override_addrs)):
            migrated_overrides: set[tuple[str, ...]] = set()
            for old_addr in list(self.user_override_addrs):
                if len(old_addr) < expected_dims:
                    padded = list(old_addr)
                    for i in range(len(old_addr), expected_dims):
                        dim_id = self.dimension_ids[i]
                        dim = ws.dimensions.get(dim_id)
                        if dim and dim.items:
                            # Only use default (first) item for overrides
                            padded.append(dim.items[0].id)
                        else:
                            padded.append("")
                    migrated_overrides.add(tuple(padded))
                else:
                    migrated_overrides.add(old_addr)
            self.user_override_addrs = migrated_overrides

    def migrate_to_v2_with_at_dimension(self, ws: "Workspace") -> None:
        """Migrate cube from v1 (without @ dimension) to v2 (with @ dimension).
        
        This prepends at_value coordinate to all addresses (technical dimension first).
        """
        if "@" in self.dimension_ids:
            return  # Already migrated
        
        # Add @ dimension at the start of dimension_ids
        self.dimension_ids = ["@"] + self.dimension_ids
        
        # Migrate data: prepend at_value to all addresses
        if self.data:
            migrated_data: dict[tuple[str, ...], Any] = {}
            for old_addr, value in list(self.data.items()):
                new_addr = (CHANNEL_TO_AT_ID["value"], *old_addr)
                migrated_data[new_addr] = value
            self.data = migrated_data

        # Migrate user_override_addrs: prepend at_value
        if self.user_override_addrs:
            self.user_override_addrs = {
                (CHANNEL_TO_AT_ID["value"], *old_addr) for old_addr in self.user_override_addrs
            }

    def get_channel_from_addr(self, addr: tuple[str, ...]) -> str:
        """Extract channel name from address (e.g., 'value' from at_value)."""
        if "@" not in self.dimension_ids:
            return "value"
        at_idx = self.dimension_ids.index("@")
        if at_idx >= len(addr):
            return "value"
        channel_id = normalize_technical_item_id(addr[at_idx])
        if channel_id in AT_ID_TO_CHANNEL:
            return AT_ID_TO_CHANNEL[channel_id]
        # Unknown channel: extract from at_ prefix (supports user-created channels)
        if channel_id.startswith(AT_PREFIX):
            return channel_id[len(AT_PREFIX):]
        return channel_id

    def set_channel_in_addr(self, addr: tuple[str, ...], channel: str) -> tuple[str, ...]:
        """Return new address with @ dimension set to specified channel."""
        if "@" not in self.dimension_ids:
            return addr  # Can't modify, no @ dimension
        at_idx = self.dimension_ids.index("@")
        addr_list = list(addr)
        # Extend if needed
        while len(addr_list) <= at_idx:
            addr_list.append("")
        addr_list[at_idx] = CHANNEL_TO_AT_ID.get(channel, f"{AT_PREFIX}{channel}")
        return tuple(addr_list)


@dataclass
class ViewLayout:
    """Neutral layout data shape for view dimension placement.

    ViewLayout must remain a plain data shape: no cube lookup, no semantic
    validation, and no mutation side effects. Command handlers own policy.
    """

    rows: list[str] = field(default_factory=list)
    cols: list[str] = field(default_factory=list)
    page: list[str] = field(default_factory=list)


@dataclass
class TableViewSpec:
    id: str
    name: str
    cube_id: str
    row_dim_ids: list[str]
    col_dim_ids: list[str]
    page_dim_ids: list[str] = field(default_factory=list)
    row_outline: list[OutlineNode] = field(default_factory=list)
    col_outline: list[OutlineNode] = field(default_factory=list)
    col_widths: dict[int, int] = field(default_factory=dict)  # Custom column widths
    row_header_widths: dict[int, int] = field(default_factory=dict)  # Custom row header level widths
    # Cell formats: key is (row_key_tuple, col_key_tuple) or (row_index, col_index) for display
    cell_formats: dict[str, CellFormat] = field(default_factory=dict)
    # Group header formats: key is outline path as string "0,1,2"
    group_formats: dict[str, CellFormat] = field(default_factory=dict)
    # Dimension item formats: key is "dim_id:item_id"
    item_formats: dict[str, CellFormat] = field(default_factory=dict)
    # Page dimension selections: dim_id -> item_id (which page item is selected)
    page_selections: dict[str, str] = field(default_factory=dict)

    @staticmethod
    def create(
        name: str,
        cube_id: str,
        row_dimension_id: str,
        col_dimension_id: str,
        page_dim_ids: list[str] | None = None,
    ) -> "TableViewSpec":
        return TableViewSpec(
            id=new_id("view"),
            name=name,
            cube_id=cube_id,
            row_dim_ids=[row_dimension_id],
            col_dim_ids=[col_dimension_id],
            page_dim_ids=list(page_dim_ids or []),
        )

    def set_page_item_id(self, dim_id: str, item_id: str | None) -> None:
        """Set the selected item for a page dimension.

        Validates that dim_id is a page dimension of this view, normalizes
        item_id for the special @ dimension, and updates self.page_selections.
        """
        if item_id is None:
            self.page_selections.pop(dim_id, None)
            return
        if dim_id == "@":
            if not (item_id.startswith("@.") or item_id.startswith(AT_PREFIX)):
                raise ValueError(
                    f"Invalid @ dimension item: {item_id}. Must start with '@.' or '{AT_PREFIX}'"
                )
            self.page_selections[dim_id] = normalize_technical_item_id(item_id)
            return
        if dim_id not in self.page_dim_ids:
            raise ValueError(f"Dimension {dim_id} is not a page dimension of view {self.id}")
        self.page_selections[dim_id] = item_id

    def set_col_width(self, col_index: int, width: int) -> None:
        """Set one persisted column width for this view."""
        if col_index < 0:
            raise ValueError("col_index must be non-negative")
        if width < 0:
            raise ValueError("width must be non-negative")
        self.col_widths[col_index] = width

    def set_row_header_width(self, depth_or_index: int, width: int) -> None:
        """Set one persisted row-header width for this view."""
        if depth_or_index < 0:
            raise ValueError("depth_or_index must be non-negative")
        if width < 0:
            raise ValueError("width must be non-negative")
        self.row_header_widths[depth_or_index] = width


def view_layout_from_legacy(view: TableViewSpec) -> ViewLayout:
    """Pure conversion from stored legacy fields to ViewLayout."""
    return ViewLayout(
        rows=list(view.row_dim_ids),
        cols=list(view.col_dim_ids),
        page=list(view.page_dim_ids),
    )


def apply_layout_to_view(view: TableViewSpec, layout: ViewLayout) -> None:
    """Temporary compatibility helper: copy a ViewLayout into stored legacy fields.

    Internal use only. Must be called exclusively from approved mutation paths
    such as CommandService / command handlers or engine methods invoked by
    the command layer. Must not be used by REPL, GUI, CLI, or query code.
    """
    view.row_dim_ids = list(layout.rows)
    view.col_dim_ids = list(layout.cols)
    view.page_dim_ids = list(layout.page)


@dataclass
class Workspace:
    id: str
    name: str
    dimensions: dict[str, Dimension] = field(default_factory=dict)
    cubes: dict[str, Cube] = field(default_factory=dict)
    views: dict[str, TableViewSpec] = field(default_factory=dict)
    rules: dict[str, Rule] = field(default_factory=dict)
    rule_order: list[str] = field(default_factory=list)
    views_order: list[str] = field(default_factory=list)
    # File-level saved default view ID (loaded at open, persisted at save).
    saved_default_view_id: str | None = None

    # ── graph lookup indexes ──
    # In-memory index for fast ITEM_REF node resolution.
    # Key: (dim_id, item_id) -> node_id.  Rebuild on load; update on mutation.
    _item_ref_index: dict[tuple[str, str], str] = field(default_factory=dict)

    # Lazy per-cube ordered rule-id cache.  None = stale; rebuilt on first use.
    _cube_rule_index: dict[str, list[str]] | None = field(default=None, repr=False)

    # Lazy per-cube anchored-rule index: cube_id -> {addr_mask -> rule_id}
    _cube_anchored_index: dict[str, dict[tuple[str, ...], str]] | None = field(default=None, repr=False)

    # Lazy per-cube effective mask + specificity cache.
    # _cube_rule_masks: cube_id -> list[mask_tuple | None]
    # _cube_rule_specificity: cube_id -> list[int]
    _cube_rule_masks: dict[str, list[tuple[str | None, ...] | None]] | None = field(default=None, repr=False)
    _cube_rule_specificity: dict[str, list[int]] | None = field(default=None, repr=False)

    @staticmethod
    def create(name: str = "Untitled") -> "Workspace":
        ws = Workspace(id=new_id("ws"), name=name)
        # Auto-create @ technical dimension
        ws._ensure_at_dimension()
        # Ensure self-describing system cubes exist
        from lib_openm.lib_meta.bootstrap import ensure_system_cubes
        ensure_system_cubes(ws)
        return ws

    def set_saved_default_view_id(self, view_id: str | None) -> None:
        """Set the workspace file-level saved default view ID.

        Rules:
        - If view_id is None, set saved_default_view_id to None.
        - If view_id is non-None and exists in self.views, set it.
        - If view_id is non-None but not in self.views, fall back to the first
          available view or None.
        """
        if view_id is None:
            self.saved_default_view_id = None
        elif view_id in self.views:
            self.saved_default_view_id = view_id
        else:
            self.saved_default_view_id = next(iter(self.views), None)

    def rebuild_item_ref_index(self) -> int:
        """Scan %RECNOD once and rebuild the in-memory (dim_id, item_id) -> node_id index.

        Returns the number of ITEM_REF entries indexed.
        """
        from lib_openm.outline_graph_bridge import _dim_by_name, _cube_by_name, _item_id
        from lib_openm.technical_ids import CHANNEL_TO_AT_ID

        self._item_ref_index.clear()

        recnodadr = _dim_by_name(self, "%RECNODADR")
        recnodfld = _dim_by_name(self, "%RECNODFLD")
        recnod = _cube_by_name(self, "%RECNOD")

        if recnodadr is None or recnodfld is None or recnod is None:
            return 0

        knd_id = _item_id(recnodfld, "KND")
        dim_fld_id = _item_id(recnodfld, "DIM")
        ref_id = _item_id(recnodfld, "REF")

        if not (knd_id and dim_fld_id and ref_id):
            return 0

        count = 0
        for adr_item in recnodadr.items:
            if adr_item.name == "NUL":
                continue
            if recnod.get((CHANNEL_TO_AT_ID["value"], adr_item.id, knd_id)) != "ITEM_REF":
                continue
            dim_val = recnod.get((CHANNEL_TO_AT_ID["value"], adr_item.id, dim_fld_id))
            ref_val = recnod.get((CHANNEL_TO_AT_ID["value"], adr_item.id, ref_id))
            if dim_val and ref_val:
                self._item_ref_index[(dim_val, ref_val)] = adr_item.name
                count += 1
        return count

    def get_outline(self, dim_id: str) -> list["OutlineNode"]:
        """Return cached outline for dim_id; rebuild lazily if stale."""
        dim = self.dimensions.get(dim_id)
        if dim is None:
            return []
        if dim._outline_cache is not None:
            return dim._outline_cache

        # %RECEDGADR / %RECNODADR items are edge/node addresses that do not
        # have ITEM_REF nodes in %RECNOD, and newly-added nodes belong to
        # user dimensions, so graph rebuild would miss them. Build a flat
        # outline directly from items instead.
        if dim.name in ("%RECEDGADR", "%RECNODADR") and dim.items:
            from lib_openm.model import OutlineNode
            rebuilt = [OutlineNode(label=it.name, item_id=it.id, children=[]) for it in dim.items]
        else:
            from lib_openm.outline_graph_bridge import rebuild_outline_from_graph
            rebuilt = rebuild_outline_from_graph(dim, self)
            # Transitional fallback: if graph is empty but dim.outline has content,
            # preserve the manual outline (e.g. from tests that don't build graph yet)
            if not rebuilt and dim.outline:
                rebuilt = dim.outline

        object.__setattr__(dim, "_outline_cache", rebuilt)
        object.__setattr__(dim, "outline", rebuilt)
        return rebuilt

    def _ensure_at_dimension(self) -> None:
        """Ensure the @ technical dimension exists with all channel items.

        Creates the @ dimension if missing, OR upgrades existing @ dimension
        to include any missing TECHNICAL_CHANNELS items (for backward compatibility
        with old files that have partial channel sets).

        Items are sorted so current TECHNICAL_CHANNELS come first (in defined order),
        and any deprecated/extra items come last.
        """
        if "@" not in self.dimensions:
            # Create new @ dimension with all channels in canonical order
            at_dim = Dimension(
                id="@",
                name="@",
                is_technical=True,
                items=[DimensionItem(id=f"{AT_PREFIX}{ch}", name=ch) for ch in TECHNICAL_CHANNELS]
            )
            self.dimensions["@"] = at_dim
            return

        # @ dimension exists - check for missing items and add them
        at_dim = self.dimensions["@"]
        existing_items_by_name: dict[str, DimensionItem] = {item.name: item for item in at_dim.items}
        existing_names = set(existing_items_by_name.keys())

        # Migrate existing canonical channel items from old @. prefix to new at_ prefix
        for ch in TECHNICAL_CHANNELS:
            if ch in existing_items_by_name:
                item = existing_items_by_name[ch]
                canonical_id = f"{AT_PREFIX}{ch}"
                if item.id.startswith("@.") and item.id != canonical_id:
                    existing_items_by_name[ch] = DimensionItem(id=canonical_id, name=item.name)

        # Find missing canonical channels
        missing_channels = [ch for ch in TECHNICAL_CHANNELS if ch not in existing_names]

        if missing_channels:
            print(f"[Workspace] Upgrading @ dimension: adding {len(missing_channels)} missing channel(s): {missing_channels}")
            for ch in missing_channels:
                existing_items_by_name[ch] = DimensionItem(id=f"{AT_PREFIX}{ch}", name=ch)

        # Find deprecated/extra items (not in TECHNICAL_CHANNELS)
        tech_channels_set = set(TECHNICAL_CHANNELS)
        deprecated_names = [name for name in existing_names if name not in tech_channels_set]

        # Rebuild items list: canonical channels first (in TECHNICAL_CHANNELS order), then deprecated
        new_items: list[DimensionItem] = []
        # Add canonical channels in defined order
        for ch in TECHNICAL_CHANNELS:
            if ch in existing_items_by_name:
                new_items.append(existing_items_by_name[ch])
        # Add deprecated items last (alphabetically for stability)
        for name in sorted(deprecated_names):
            new_items.append(existing_items_by_name[name])

        at_dim.items = new_items

        if missing_channels or deprecated_names:
            print(f"[Workspace] @ dimension now has {len(at_dim.items)} channels ({len(TECHNICAL_CHANNELS)} canonical, {len(deprecated_names)} deprecated)")

    def add_dimension(self, dim: Dimension) -> None:
        # Check for duplicate names (case-insensitive, trimmed)
        name_clean = dim.name.strip().casefold()
        for existing in self.dimensions.values():
            if existing.name.strip().casefold() == name_clean:
                raise ValueError(f"Dimension with name '{dim.name}' already exists")
        self.dimensions[dim.id] = dim

    def add_cube(self, cube: Cube) -> None:
        # Check for duplicate names (case-insensitive, trimmed)
        name_clean = cube.name.strip().casefold()
        for existing in self.cubes.values():
            if existing.name.strip().casefold() == name_clean:
                raise ValueError(f"Cube with name '{cube.name}' already exists")
        self.cubes[cube.id] = cube

    def add_view(self, view: TableViewSpec) -> None:
        # Check for duplicate names (case-insensitive, trimmed)
        name_clean = view.name.strip().casefold()
        for existing in self.views.values():
            if existing.name.strip().casefold() == name_clean:
                raise ValueError(f"View with name '{view.name}' already exists")
        self.views[view.id] = view
        if view.id not in self.views_order:
            self.views_order.append(view.id)

    def get_dimension(self, dim_id: str) -> Dimension | None:
        return self.dimensions.get(dim_id)

    def get_cube(self, cube_id: str) -> Cube:
        return self.cubes[cube_id]

    def upsert_cell_rule(
        self,
        cube_id: str,
        addr: tuple[str, ...],
        expression: str,
        *,
        normalize: Callable[[str], str] | None = None,
    ) -> Rule:
        """Create or update an anchored rule for a single cell address.

        Cell rules are now stored as anchored ``Rule`` objects in
        ``rules``.  This method builds the ``addr_mask`` and
        ``targets`` from the address and delegates to
        :meth:`upsert_rule`.
        """
        cube = self.get_cube(cube_id)
        normalized_addr = normalize_addr(addr)

        # Build targets from address, skipping @ dimension. The address may be a
        # full N-tuple (including @) or a short tuple aligned to non-@ dims.
        targets: list[tuple[str, str]] = []
        if "@" in cube.dimension_ids and len(normalized_addr) == len(cube.dimension_ids):
            # Full address: consume each position in lockstep.
            for i, dim_id in enumerate(cube.dimension_ids):
                if dim_id == "@":
                    continue
                item_id = normalized_addr[i]
                dim = self.dimensions.get(dim_id)
                item_name = (
                    next((it.name for it in dim.items if it.id == item_id), item_id)
                    if dim else item_id
                )
                targets.append((dim.name, item_name))
        else:
            # Short address: map elements to non-@ dimensions in order.
            addr_idx = 0
            for dim_id in cube.dimension_ids:
                if dim_id == "@":
                    continue
                if addr_idx < len(normalized_addr):
                    item_id = normalized_addr[addr_idx]
                    addr_idx += 1
                    dim = self.dimensions.get(dim_id)
                    item_name = (
                        next((it.name for it in dim.items if it.id == item_id), item_id)
                        if dim else item_id
                    )
                    targets.append((dim.name, item_name))

        rule = self.upsert_rule(
            cube_id,
            expression=normalize(expression) if normalize else expression,
            addr_mask=normalized_addr,
            targets=tuple(targets) if targets else None,
            is_anchored=True,
        )

        # Preserve base_values for self-referencing rules
        if normalized_addr in cube.data:
            cube.base_values[normalized_addr] = cube.data[normalized_addr]
        cube.user_override_addrs.discard(normalized_addr)
        if "@" in cube.dimension_ids and len(normalized_addr) < len(cube.dimension_ids):
            padded_addr = (CHANNEL_TO_AT_ID["value"], *normalized_addr)
            cube.user_override_addrs.discard(padded_addr)
            if padded_addr in cube.data:
                cube.base_values[padded_addr] = cube.data[padded_addr]

        return rule

    def delete_cell_rule(self, cube_id: str, addr: tuple[str, ...]) -> bool:
        """Delete the anchored rule matching *addr* on *cube_id*."""
        cube = self.cubes.get(cube_id)
        padded_addr: tuple[str, ...] | None = None
        if cube and "@" in cube.dimension_ids and len(addr) < len(cube.dimension_ids):
            padded_addr = (CHANNEL_TO_AT_ID["value"], *addr)

        to_delete: str | None = None
        for rid, r in self.rules.items():
            if r.cube_id != cube_id or not r.is_anchored:
                continue
            mask = r.addr_mask
            if mask is None:
                continue
            if mask == addr or mask == padded_addr:
                to_delete = rid
                break
            if cube and "@" in cube.dimension_ids:
                if len(mask) < len(cube.dimension_ids) and len(addr) == len(cube.dimension_ids):
                    r_padded = (CHANNEL_TO_AT_ID["value"], *mask)
                    if r_padded == addr:
                        to_delete = rid
                        break

        if to_delete is None:
            return False
        self.delete_rule(to_delete)
        return True

    def delete_cell_rule_by_id(self, rule_id: str) -> bool:
        """Delete by ID — cell rule IDs now live in ``rules``."""
        return self.delete_rule(rule_id)

    # -- rule index helpers ------------------------------------------
    def _invalidate_rule_index(self) -> None:
        """Mark all per-cube rule indexes as stale."""
        self._cube_rule_index = None
        self._cube_anchored_index = None
        self._cube_rule_masks = None
        self._cube_rule_specificity = None

    def _build_rule_index(self) -> None:
        """Build and cache per-cube ordered rule-id and anchored-rule indexes."""
        ordered_index: dict[str, list[str]] = {}
        anchored_index: dict[str, dict[tuple[str, ...], str]] = {}
        mask_index: dict[str, list[tuple[str | None, ...] | None]] = {}
        spec_index: dict[str, list[int]] = {}
        for rid in self._ordered_rule_ids():
            r = self.rules[rid]
            cube = self.cubes.get(r.cube_id)
            ordered_index.setdefault(r.cube_id, []).append(rid)
            if r.is_anchored and r.addr_mask is not None:
                anchored_index.setdefault(r.cube_id, {})[r.addr_mask] = rid
            # Precompute effective mask and specificity
            if cube is not None:
                mask = self._effective_rule_mask(r, cube.dimension_ids, cube)
                mask_index.setdefault(r.cube_id, []).append(mask)
                spec = sum(1 for x in mask if x is not None) if mask is not None else -1
                spec_index.setdefault(r.cube_id, []).append(spec)
            else:
                mask_index.setdefault(r.cube_id, []).append(None)
                spec_index.setdefault(r.cube_id, []).append(-1)
        self._cube_rule_index = ordered_index
        self._cube_anchored_index = anchored_index
        self._cube_rule_masks = mask_index
        self._cube_rule_specificity = spec_index

    def _cube_ordered_rule_ids(self, cube_id: str) -> list[str]:
        """Return ordered rule IDs for *cube_id*, building the index lazily."""
        if self._cube_rule_index is None:
            self._build_rule_index()
        return self._cube_rule_index.get(cube_id, []) if self._cube_rule_index is not None else []

    def find_anchored_rule(self, cube_id: str, addr: tuple[str, ...]) -> Rule | None:
        """Return the anchored rule matching *addr* on *cube_id*, or *None*."""
        cube = self.cubes.get(cube_id)
        normalized_addr = normalize_addr(addr)

        # Fast path: anchored-rule index lookup
        if self._cube_anchored_index is None:
            self._build_rule_index()
        anchored = self._cube_anchored_index
        if anchored is not None:
            cube_map = anchored.get(cube_id)
            if cube_map is not None:
                rid = cube_map.get(normalized_addr)
                if rid is not None:
                    return self.rules.get(rid)
                if cube and "@" in cube.dimension_ids and len(normalized_addr) < len(cube.dimension_ids):
                    padded = (CHANNEL_TO_AT_ID["value"], *normalized_addr)
                    rid = cube_map.get(padded)
                    if rid is not None:
                        return self.rules.get(rid)
                if cube and "@" in cube.dimension_ids and len(normalized_addr) == len(cube.dimension_ids):
                    # try stripping leading @ value and matching shorter mask
                    if normalized_addr[0] == CHANNEL_TO_AT_ID["value"]:
                        rid = cube_map.get(normalized_addr[1:])
                        if rid is not None:
                            return self.rules.get(rid)

        # Fallback: linear scan over cube's rules
        padded_addr: tuple[str, ...] | None = None
        if cube and "@" in cube.dimension_ids and len(normalized_addr) < len(cube.dimension_ids):
            padded_addr = (CHANNEL_TO_AT_ID["value"], *normalized_addr)

        for rid in self._cube_ordered_rule_ids(cube_id):
            r = self.rules[rid]
            if not r.is_anchored:
                continue
            mask = r.addr_mask
            if mask is None:
                continue
            if mask == normalized_addr or mask == padded_addr:
                return r
            if cube and "@" in cube.dimension_ids:
                if len(mask) < len(cube.dimension_ids) and len(normalized_addr) == len(cube.dimension_ids):
                    r_padded = (CHANNEL_TO_AT_ID["value"], *mask)
                    if r_padded == normalized_addr:
                        return r
        return None

    def is_anchored_rule(self, rule: Rule) -> bool:
        """Check if a rule is "anchored" (targets exactly one cell).

        An anchored rule has a full mask with no wildcards (no None values),
        meaning it applies to exactly one address. This is inferred from the
        mask state, not stored separately.
        """
        if rule.addr_mask is None:
            return False
        return None not in rule.addr_mask

    def upsert_rule(
        self,
        cube_id: str,
        dim_id: str = "",
        item_id: str = "",
        expression: str = "",
        addr_mask: tuple[str | None, ...] | None = None,
        targets: tuple[tuple[str, str], ...] | None = None,
        is_anchored: bool = False,
    ) -> Rule:
        """Create or update a rule rule for this cube.

        ``addr_mask`` describes the full multi-dimension target of the rule,
        aligned to the cube's ``dimension_ids``. When omitted, a mask is
        constructed that constrains only ``dim_id``/``item_id`` and wildcards
        all other dimensions (legacy behavior). Prefer passing ``addr_mask``
        directly. There is at most one rule per ``(cube, addr_mask)``;
        calling this again with the same mask updates the expression of the
        existing rule.
        """

        cube = self.cubes[cube_id]
        if addr_mask is None:
            # Back-compat: single-dimension rule targeting just dim_id/item_id.
            mask_list: list[str | None] = [None] * len(cube.dimension_ids)
            try:
                slot = cube.dimension_ids.index(dim_id)
            except ValueError:
                slot = -1
            if 0 <= slot < len(mask_list):
                mask_list[slot] = item_id
            addr_mask = tuple(mask_list)

        # Update existing rule with identical mask (if any).
        # Use per-cube ordered index to avoid scanning all rules.
        for rid in self._cube_ordered_rule_ids(cube_id):
            r = self.rules[rid]
            if r.addr_mask == addr_mask:
                self.rules[r.id] = Rule(
                    id=r.id,
                    cube_id=cube_id,
                    expression=expression,
                    addr_mask=addr_mask,
                    targets=targets if targets is not None else r.targets,
                    is_anchored=is_anchored if is_anchored else r.is_anchored,
                )
                self._invalidate_rule_index()
                return self.rules[r.id]

        # Otherwise create a new rule.
        rule = Rule(
            id=new_id("r"),
            cube_id=cube_id,
            expression=expression,
            addr_mask=addr_mask,
            targets=targets,
            is_anchored=is_anchored,
        )
        self.rules[rule.id] = rule
        if rule.id not in self.rule_order:
            self.rule_order.append(rule.id)

        # Clear cached values at addresses matching this rule's mask.
        # This ensures the rule gets evaluated instead of using a stale cached value
        # that was set before the rule was created.
        # NOTE: Do NOT clear user overrides (hardnumbers) - they take precedence over rules.
        if addr_mask is not None:
            # Find and clear all matching addresses in the cube
            addrs_to_clear = []
            for addr in list(cube.data.keys()):
                if len(addr) != len(addr_mask):
                    continue
                # Skip hardnumbers - user overrides take precedence over rule rules
                if cube.is_user_override(addr):
                    continue
                matches = True
                for i, mask_item in enumerate(addr_mask):
                    if mask_item is not None and addr[i] != mask_item:
                        matches = False
                        break
                if matches:
                    addrs_to_clear.append(addr)
            for addr in addrs_to_clear:
                cube.set(addr, None)

        self._invalidate_rule_index()
        return rule

    def delete_rule(self, rule_id: str) -> bool:
        if rule_id not in self.rules:
            return False
        rule = self.rules[rule_id]

        # Clear cached values at addresses matching this rule's mask.
        # This prevents stale calculated values from remaining after the rule is removed.
        # NOTE: Do NOT clear user overrides (hardnumbers) - they are independent of rules.
        cube = self.cubes.get(rule.cube_id)
        if cube is not None and rule.addr_mask is not None:
            addrs_to_clear = []
            for addr in list(cube.data.keys()):
                if len(addr) != len(rule.addr_mask):
                    continue
                # Skip hardnumbers - user overrides take precedence
                if cube.is_user_override(addr):
                    continue
                matches = True
                for i, mask_item in enumerate(rule.addr_mask):
                    if mask_item is not None and addr[i] != mask_item:
                        matches = False
                        break
                if matches:
                    addrs_to_clear.append(addr)
            for addr in addrs_to_clear:
                cube.set(addr, None)

        self.rules.pop(rule_id, None)
        if rule_id in self.rule_order:
            self.rule_order = [rid for rid in self.rule_order if rid != rule_id]
        self._invalidate_rule_index()
        return True

    def _ordered_rule_ids(self) -> list[str]:
        """Return all rule rule ids in effective precedence order.

        The ordering respects ``rule_order`` (including any explicit
        reordering done via the GUI) and then appends any rules that do not
        yet appear in that list in insertion order. This matches the behaviour
        expected by :meth:`find_rule` where "last statement wins" for
        rules with identical specificity.
        """

        ordered_ids = [rid for rid in self.rule_order if rid in self.rules]
        if len(ordered_ids) != len(self.rules):
            for rid in self.rules:
                if rid not in ordered_ids:
                    ordered_ids.append(rid)
        return ordered_ids

    def _effective_rule_mask(self, r: Rule, dimension_ids: list[str], cube: Any | None = None) -> tuple[str | None, ...] | None:
        """Return ``r``'s mask aligned to ``dimension_ids`` or ``None``.

        Uses the stored ``addr_mask`` if present. If the cube has gained extra
        dimensions since the rule was created, pads with wildcards (``None``)
        so existing rules continue to apply across new dimensions.
        Returns ``None`` if no mask is available.
        """

        # Primary path: use the stored mask if it is present. If the cube has
        # gained extra dimensions since the rule was created, pad with
        # wildcards (``None``) so existing rules continue to apply across the
        # new dimension.
        if r.addr_mask is not None:
            if len(r.addr_mask) == len(dimension_ids):
                # Check if mask has right length but @ dimension is None (should be at_value not wildcard)
                if "@" in dimension_ids:
                    at_slot = dimension_ids.index("@")
                    if at_slot < len(r.addr_mask) and r.addr_mask[at_slot] is None:
                        # @ slot is None but should default to at_value for rules without explicit @ channel
                        mask_list = list(r.addr_mask)
                        mask_list[at_slot] = CHANNEL_TO_AT_ID["value"]
                        return tuple(mask_list)
                return r.addr_mask
            if len(r.addr_mask) < len(dimension_ids):
                # If the rule has parsed targets, rebuild the mask from them using
                # the current cube dimensions.  This is more robust than positional
                # shifting when dimensions have been added, reordered, or when @
                # was inserted.
                if cube is not None and r.targets:
                    rebuilt = self._rebuild_mask_from_targets(r, cube)
                    if rebuilt is not None:
                        # Default @ slot to at_value if it is not already set
                        if "@" in dimension_ids:
                            at_slot = dimension_ids.index("@")
                            if at_slot < len(rebuilt) and rebuilt[at_slot] is None:
                                rebuilt_list = list(rebuilt)
                                rebuilt_list[at_slot] = CHANNEL_TO_AT_ID["value"]
                                return tuple(rebuilt_list)
                        return rebuilt
                # Check if @ dimension was prepended and not in mask
                if "@" in dimension_ids and not any(str(m).startswith(AT_PREFIX) for m in r.addr_mask if m):
                    # @ dimension exists in cube but not in mask - default to at_value
                    # (NOT wildcard - rules without explicit @ channel should only apply to at_value)
                    at_slot = dimension_ids.index("@")
                    # Build mask: at_value at at_slot, then original mask, then None for remaining
                    new_mask = [None] * len(dimension_ids)
                    new_mask[at_slot] = CHANNEL_TO_AT_ID["value"]  # Default @ channel
                    # Copy original mask into remaining slots
                    original_idx = 0
                    for i in range(len(dimension_ids)):
                        if i == at_slot:
                            continue  # Skip @ slot, already set
                        if original_idx < len(r.addr_mask):
                            new_mask[i] = r.addr_mask[original_idx]
                            original_idx += 1
                    return tuple(new_mask)
                else:
                    # Pad at the end (old behavior for backward compatibility)
                    pad = [None] * (len(dimension_ids) - len(r.addr_mask))
                    return tuple(list(r.addr_mask) + pad)

        # No addr_mask available - rule cannot be applied
        return None

    def _rebuild_mask_from_targets(self, r: Rule, cube: Any) -> tuple[str | None, ...] | None:
        """Rebuild a rule's addr_mask from its parsed targets and current cube.

        Returns ``None`` if any non-wildcard target cannot be resolved, so that
        callers can fall back to positional mask shifting instead of turning a
        constrained rule into an unintended whole-cube wildcard.
        """
        if not r.targets:
            return None

        mask: list[str | None] = [None] * len(cube.dimension_ids)

        for dim_name, item_name in r.targets:
            # Whole-cube wildcard
            if dim_name == "*" and item_name == "*":
                continue

            # Find dimension by name
            dim = next(
                (d for d in self.dimensions.values() if d.name.lower() == dim_name.lower()),
                None,
            )
            if dim is None or dim.id not in cube.dimension_ids:
                # Try *.Item syntax: infer dimension from item name
                if dim_name == "*" and item_name != "*":
                    item_lower = item_name.lower()
                    candidate_dims = [
                        d for d in self.dimensions.values()
                        if d.id in cube.dimension_ids
                        and any(it.name.lower() == item_lower for it in d.items)
                    ]
                    if len(candidate_dims) == 1:
                        dim = candidate_dims[0]
                    else:
                        return None
                else:
                    return None

            slot = cube.dimension_ids.index(dim.id)

            # Dimension-level wildcard
            if item_name == "*":
                continue

            # Sequential keywords - only THIS is allowed on LHS (treated as wildcard)
            item_upper = item_name.upper()
            if item_upper == "THIS":
                continue
            if item_upper in {"FIRST", "LAST", "PREV", "NEXT"}:
                return None

            item = next((it for it in dim.items if it.name.lower() == item_name.lower()), None)
            if item is None:
                return None

            mask[slot] = item.id

        return tuple(mask)

    def find_rule(self, cube_id: str, addr: tuple[str, ...], dimension_ids: list[str]) -> Rule | None:
        """Return the best matching rule for ``addr``.

        Selection rules:
        - Only rules for this cube are considered.
        - A rule applies if all non-``None`` entries in its mask match the
          corresponding slots in ``addr``.
        - Specificity is the number of constrained dimensions in the mask.
        - The most specific rule wins.
        - If multiple rules with the same maximum specificity apply, the
          *last* such rule in ``rule_order`` wins ("last statement wins").
        """

        # Backward compatibility: prepend at_value if @ dimension exists
        # and address is shorter than expected
        if "@" in dimension_ids and len(addr) < len(dimension_ids):
            addr = (CHANNEL_TO_AT_ID["value"], *addr)

        # Fast path: exact anchored-rule match has maximum specificity
        anchored = self.find_anchored_rule(cube_id, addr)
        if anchored is not None:
            return anchored

        best_rule: Rule | None = None
        best_specificity = -1

        rule_ids = self._cube_ordered_rule_ids(cube_id)
        masks = self._cube_rule_masks.get(cube_id, []) if self._cube_rule_masks is not None else []
        specs = self._cube_rule_specificity.get(cube_id, []) if self._cube_rule_specificity is not None else []

        cube = self.cubes.get(cube_id)
        for idx, rid in enumerate(rule_ids):
            r = self.rules[rid]
            mask = masks[idx] if idx < len(masks) else self._effective_rule_mask(r, dimension_ids, cube)
            if _DEBUG_RULE_MATCH:
                print(f"[DEBUG RULE MATCH] rid={rid[:8]}, addr={addr}, mask={mask}, dim_ids={dimension_ids}")
            if mask is None or len(mask) != len(addr):
                if _DEBUG_RULE_MATCH:
                    print(f"[DEBUG RULE MATCH]   -> SKIP: mask={mask}, len(mask)={len(mask) if mask else None}, len(addr)={len(addr)}")
                continue

            # Check whether this rule applies to the given address.
            applies = True
            for i, item_id in enumerate(mask):
                if item_id is not None and addr[i] != item_id:
                    applies = False
                    if _DEBUG_RULE_MATCH:
                        print(f"[DEBUG RULE MATCH]   -> mismatch at slot {i}: mask={item_id}, addr={addr[i]}")
                    break
            if not applies:
                continue

            specificity = specs[idx] if idx < len(specs) else sum(1 for x in mask if x is not None)
            if _DEBUG_RULE_MATCH:
                print(f"[DEBUG RULE MATCH]   -> APPLIES! specificity={specificity}")

            if specificity > best_specificity:
                best_specificity = specificity
                best_rule = r
            elif specificity == best_specificity and specificity >= 0:
                # Same specificity: later rule overrides earlier one (last wins).
                best_rule = r

        return best_rule

    def compute_rule_precedence_for_cube(self, cube_id: str) -> dict[str, dict[str, list[str]]]:
        """Compute rule precedence/overlap information for a single cube.

        The result maps each rule id for ``cube_id`` to a structure of the
        form ``{"overrules": [...], "overruled_by": [...]}`` listing other
        rules of the *same cube* that it dominates or is dominated by.

        Two rules are considered to overlap if their effective masks admit at
        least one common address. When they overlap, the more specific rule
        (with more constrained dimensions) wins; for identical specificity,
        the later rule in ``rule_order`` wins. These are the same
        semantics used by :meth:`find_rule`.
        """

        cube = self.cubes.get(cube_id)
        if cube is None:
            return {}

        dimension_ids = list(cube.dimension_ids)
        if not dimension_ids:
            return {}

        ordered_ids = self._ordered_rule_ids()
        # Restrict to rules for this cube, preserving relative order.
        cube_rule_ids = [rid for rid in ordered_ids if rid in self.rules and self.rules[rid].cube_id == cube_id]
        if not cube_rule_ids:
            return {}

        id_to_pos = {rid: idx for idx, rid in enumerate(cube_rule_ids)}

        # Precompute masks and specificities; skip rules that do not yield a
        # usable mask for this cube.
        rules: list[tuple[Rule, tuple[str | None, ...], int]] = []
        for rid in cube_rule_ids:
            r = self.rules[rid]
            mask = self._effective_rule_mask(r, dimension_ids, cube)
            if mask is None or len(mask) != len(dimension_ids):
                continue
            specificity = sum(1 for x in mask if x is not None)
            rules.append((r, mask, specificity))

        result: dict[str, dict[str, set[str]]] = {}
        for r, _mask, _spec in rules:
            result[r.id] = {"overrules": set(), "overruled_by": set()}

        def masks_intersect(a: tuple[str | None, ...], b: tuple[str | None, ...]) -> bool:
            for va, vb in zip(a, b):
                if va is not None and vb is not None and va != vb:
                    return False
            return True

        # Pairwise comparison: precedence is uniform across all common
        # addresses of two overlapping rules, so we do not need to enumerate
        # the address space.
        for i in range(len(rules)):
            r1, m1, s1 = rules[i]
            for j in range(i + 1, len(rules)):
                r2, m2, s2 = rules[j]
                if not masks_intersect(m1, m2):
                    continue

                if s1 > s2:
                    result[r1.id]["overrules"].add(r2.id)
                    result[r2.id]["overruled_by"].add(r1.id)
                elif s2 > s1:
                    result[r2.id]["overrules"].add(r1.id)
                    result[r1.id]["overruled_by"].add(r2.id)
                else:
                    # Same specificity: later rule in order wins.
                    pos1 = id_to_pos.get(r1.id, -1)
                    pos2 = id_to_pos.get(r2.id, -1)
                    if pos1 == -1 or pos2 == -1 or pos1 == pos2:
                        continue
                    if pos1 > pos2:
                        winner, loser = r1, r2
                    else:
                        winner, loser = r2, r1
                    result[winner.id]["overrules"].add(loser.id)
                    result[loser.id]["overruled_by"].add(winner.id)

        # Normalise sets to sorted lists (preserving cube-local rule order).
        def sort_ids(ids: set[str]) -> list[str]:
            return sorted(ids, key=lambda rid: id_to_pos.get(rid, 0))

        return {
            rid: {
                "overrules": sort_ids(info["overrules"]),
                "overruled_by": sort_ids(info["overruled_by"]),
            }
            for rid, info in result.items()
        }

    def set_rule_order(self, rule_ids: list[str]) -> None:
        seen: set[str] = set()
        ordered: list[str] = []
        for rid in rule_ids:
            if rid in self.rules and rid not in seen:
                ordered.append(rid)
                seen.add(rid)
        for rid in self.rules:
            if rid not in seen:
                ordered.append(rid)
        self.rule_order = ordered
        self._invalidate_rule_index()

    # --- Method aliases (Phase 5A) ---
    # (all aliases migrated)


def demo_workspace() -> Workspace:
    """Create a demo workspace with dimensions A and B, cube C, view C, and random items."""
    ws = Workspace.create("Demo")

    def _random_name(existing: set[str]) -> str:
        """Generate a unique 5-char lowercase alphanumeric name."""
        alphabet = string.ascii_lowercase + string.digits
        while True:
            name = "".join(random.choice(alphabet) for _ in range(5))
            if name not in existing:
                return name

    dim_a = Dimension.create("A")
    existing_a = set()
    for _ in range(3):
        name = _random_name(existing_a)
        existing_a.add(name)
        dim_a.add_item(name)

    dim_b = Dimension.create("B")
    existing_b = set()
    for _ in range(3):
        name = _random_name(existing_b)
        existing_b.add(name)
        dim_b.add_item(name)

    ws.add_dimension(dim_a)
    ws.add_dimension(dim_b)

    cube = Cube.create("C", [dim_a.id, dim_b.id])
    ws.add_cube(cube)

    view = TableViewSpec.create("C", cube.id, dim_a.id, dim_b.id, page_dim_ids=["@"])
    ws.add_view(view)
    ws.set_saved_default_view_id(view.id)

    return ws
