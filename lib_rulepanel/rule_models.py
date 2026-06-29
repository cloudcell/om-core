"""Data models for rule body display and editing."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _parse_lhs_mask(lhs: str, dimension_names: list[str] | None = None) -> tuple[int, str]:
    """Parse LHS pattern and return (specificity, mask_display).
    
    LHS format: "dim1.item1:dim2.item2" or "[@.value, A.a, B.b]" for cell rules.
    Specificity = count of non-wildcard dimensions.
    Mask = human-readable like "@=value, A=a, B=*, Q=*" (all dimensions shown).
    """
    # Strip $ anchor prefix if present
    if lhs.startswith("$"):
        lhs = lhs[1:].strip()

    # Cell rule - parse the address components
    if lhs.startswith("[") and lhs.endswith("]"):
        inner = lhs[1:-1].strip()
        parts = [p.strip() for p in inner.split(",")]
        constraints = []
        constrained_count = 0
        has_at_constraint = False
        
        for part in parts:
            if "." in part:
                dim, item = part.split(".", 1)
                if dim == "@":
                    has_at_constraint = True
                if item == "*":
                    constraints.append(f"{dim}=*")
                else:
                    constraints.append(f"{dim}={item}")
                    constrained_count += 1
            else:
                constraints.append(f"{part}=*")
        
        # Default to @=value if no explicit @ dimension specified
        if not has_at_constraint:
            constraints.insert(0, "@=value")
        
        mask_str = ", ".join(constraints)
        return constrained_count, mask_str
    
    # Empty or invalid
    if not lhs:
        return 0, ""
    
    # Parse pattern like "a.a:b.a" or "*.*" or "A.a" or ".item"
    dim_item_map = {}
    constrained_count = 0

    # Handle ".item" shorthand for "@.item"
    if lhs.startswith("."):
        lhs = "@" + lhs

    # Handle both colon-separated and single dimension patterns
    if ":" in lhs:
        # Multi-dimension pattern: "dim.item:dim.item"
        parts = lhs.split(":")
        for part in parts:
            if "." in part:
                dim, item = part.split(".", 1)
                dim_item_map[dim] = item
                if item != "*":
                    constrained_count += 1
    elif "." in lhs:
        # Single dimension pattern: "dim.item" (e.g., "*.*")
        dim, item = lhs.split(".", 1)
        dim_item_map[dim] = item
        if item != "*":
            constrained_count = 1

    # Build mask showing @=value + all dimensions (except @ itself)
    constraints = ["@=value"]

    # If @ is explicitly in the pattern, update the @ constraint
    if "@" in dim_item_map:
        constraints[0] = f"@={dim_item_map['@']}"

    if dimension_names:
        # Map pattern dims to full dimension list by position,
        # skipping any @ entries already handled above.
        pattern_dims = list(dim_item_map.keys())
        pattern_idx = 0

        for dim_name in dimension_names:
            if dim_name == "@":
                continue  # Already handled above

            # Skip pattern dimensions that are @ (already handled)
            while pattern_idx < len(pattern_dims) and pattern_dims[pattern_idx] == "@":
                pattern_idx += 1

            if pattern_idx < len(pattern_dims):
                pattern_dim = pattern_dims[pattern_idx]
                item = dim_item_map[pattern_dim]
                constraints.append(f"{dim_name}={item}")
                pattern_idx += 1
            else:
                constraints.append(f"{dim_name}=*")
    else:
        for d, i in dim_item_map.items():
            if d != "@":
                constraints.append(f"{d}={i}")

    mask_str = ", ".join(constraints)
    return constrained_count, mask_str


@dataclass
class RuleData:
    """Data class representing a rule for display/editing."""
    lhs: str
    rhs: str
    channel: str
    specificity: int = 0  # Constrained dimensions count
    mask: str = ""  # Effective mask display (e.g., "A=a, B=*, C=c")
    status: str = "<Unique>"  # "<Unique>", "Overrules #2", "Overruled by #5"

    # Optional fields for production use
    rule_id: str | None = None
    cube_id: str | None = None
    addr_mask: tuple[str | None, ...] | None = None  # Raw mask for overlap detection
    precedence_info: dict[str, Any] = field(default_factory=dict)
    rule_index: int = 0  # 1-based original position in full ordered rule list

    @classmethod
    def from_mock(cls, lhs: str, rhs: str, channel: str,
                  specificity: int | None = None, mask: str | None = None,
                  status: str = "<Unique>", dimension_names: list[str] | None = None,
                  rule_id: str | None = None, cube_id: str | None = None,
                  addr_mask: tuple[str | None, ...] | None = None,
                  rule_index: int = 0) -> "RuleData":
        """Create from mock/test data. Auto-calculates specificity if not provided."""
        # Auto-calculate specificity and mask from LHS if not provided
        if specificity is None or mask is None or mask == "":
            calc_spec, calc_mask = _parse_lhs_mask(lhs, dimension_names)
            specificity = specificity if specificity is not None else calc_spec
            mask = mask if mask not in (None, "") else calc_mask

        return cls(
            lhs=lhs,
            rhs=rhs,
            channel=channel,
            specificity=specificity,
            mask=mask,
            status=status,
            rule_id=rule_id,
            cube_id=cube_id,
            addr_mask=addr_mask,
            rule_index=rule_index,
        )
    
    def __post_init__(self):
        """Ensure specificity and mask are set correctly after initialization."""
        if self.specificity == 0 and self.mask == "":
            spec, mask = _parse_lhs_mask(self.lhs)
            self.specificity = spec
            self.mask = mask


@dataclass 
class ChannelMetrics:
    """Metrics for a rule channel (for pill display)."""
    channel_id: str
    icon_name: str
    count: int
    context_matches: int  # Rules affecting selected cell
    viewport_matches: int  # Rules in current view
    is_computing: bool = False
    is_new: bool = False
    
    @classmethod
    def from_channel_id(cls, channel_id: str, rules: list[RuleData]) -> "ChannelMetrics":
        """Calculate metrics from a list of rules."""
        count = len([f for f in rules if f.channel == channel_id])
        # Icon mapping handled by channel_pill module
        icon_map = {
            "@.value": "calculator",
            "@.fill": "palette",
            "@.format_number": "hash",
            "@.format_text": "type",
            "@.format_null": "circle",
            "@.format_error": "alert-circle",
            "@.font_family": "type",
            "@.font_color": "palette",
            "@.font_size": "text",
            "@.font_weight": "bold",
            "@.font_italic": "italic",
            "@.text_h_align": "align-left",
            "@.text_v_align": "align-vertical",
            "@.text_indent": "indent",
            "@.text_wrap": "wrap-text",
            "@.comment": "message-square",
        }
        return cls(
            channel_id=channel_id,
            icon_name=icon_map.get(channel_id, "circle"),
            count=count,
            context_matches=0,  # Calculated by caller
            viewport_matches=count,
        )
