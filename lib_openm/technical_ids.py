"""Technical dimension ID constants and normalization helpers.

Provides dimension-namespaced canonical IDs for system dimensions
and legacy-address normalization.
"""

from lib_openm.technical_channels import TECHNICAL_CHANNELS

TECHNICAL_DIM_PREFIXES = {
    "@": "at_",
}

SYSTEM_RESERVED_PREFIXES = (
    "sys_",
    "at_",
    "grp_",
    "rec_",
    "lin_",
    "aud_",
)

AT_DIM_ID = "@"
AT_PREFIX = TECHNICAL_DIM_PREFIXES[AT_DIM_ID]

# Strict bidirectional lookup: at_value <-> value
AT_ID_TO_CHANNEL = {
    f"{AT_PREFIX}{ch}": ch
    for ch in TECHNICAL_CHANNELS
}

CHANNEL_TO_AT_ID = {
    ch: f"{AT_PREFIX}{ch}"
    for ch in TECHNICAL_CHANNELS
}

# Legacy @.value -> at_value compatibility map
LEGACY_AT_ID_COMPAT = {
    f"@.{ch}": CHANNEL_TO_AT_ID[ch]
    for ch in TECHNICAL_CHANNELS
}


def normalize_technical_item_id(part: str) -> str:
    """Convert legacy @.value style IDs to canonical at_value style."""
    return LEGACY_AT_ID_COMPAT.get(part, part)


def normalize_addr(addr: tuple[str, ...]) -> tuple[str, ...]:
    """Normalize every component of an address tuple.

    The @ dimension may not always be axis 0, so we normalize all parts.
    """
    return tuple(normalize_technical_item_id(part) for part in addr)
