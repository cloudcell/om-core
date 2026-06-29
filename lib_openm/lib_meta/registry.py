"""%CFG registry reader.

The %CFG cube is a system configuration table with shape:
    %CFG[@, %CFGITM, %CFGMET]

For now we only read @.value from %CFGITM rows and ignore %CFGMET.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lib_openm.technical_ids import CHANNEL_TO_AT_ID

if TYPE_CHECKING:
    from lib_openm.model import Workspace


# Keys we recognize. Values are the human-readable defaults if %CFG is missing.
_KNOWN_KEYS: dict[str, str] = {
    "system_table_typ": "%TYP",
    "system_table_sig": "%SIG",
    "system_table_recnod": "%RECNOD",
    "system_table_recedg": "%RECEDG",
}


class CfgRegistry:
    """In-memory view of the %CFG table."""

    def __init__(self, mapping: dict[str, str]) -> None:
        self._map = dict(mapping)

    def get(self, key: str, default: str | None = None) -> str | None:
        """Look up a configuration key.

        If the key was not present in %CFG and no default is given,
        the hard-coded default from _KNOWN_KEYS is returned.
        """
        if key in self._map:
            return self._map[key]
        if default is not None:
            return default
        return _KNOWN_KEYS.get(key)

    def __contains__(self, key: str) -> bool:
        return key in self._map or key in _KNOWN_KEYS

    def items(self) -> dict[str, str]:
        """Return a merged view: explicit %CFG entries + hard-coded defaults."""
        merged = dict(_KNOWN_KEYS)
        merged.update(self._map)
        return merged


def load_cfg(workspace: "Workspace") -> CfgRegistry:
    """Read the %CFG cube from a loaded workspace.

    Steps:
      1. Find the cube named exactly "%CFG".
      2. Find the row dimension named exactly "%CFGITM".
      3. For each item in %CFGITM, read the cell at (@.value, item, ...).
         (We ignore %CFGMET for now — there is only NUL anyway.)
      4. Keep only keys that exist in _KNOWN_KEYS.
      5. Return a CfgRegistry.

    If %CFG or %CFGITM is missing, return an empty CfgRegistry
    backed entirely by hard-coded defaults.
    """
    cfg_cube = None
    for cube in workspace.cubes.values():
        if cube.name == "%CFG":
            cfg_cube = cube
            break

    if cfg_cube is None:
        return CfgRegistry({})

    # Find which dimension is %CFGITM
    cfgitm_dim_id = None
    for dim_id in cfg_cube.dimension_ids:
        dim = workspace.dimensions.get(dim_id)
        if dim is not None and dim.name == "%CFGITM":
            cfgitm_dim_id = dim_id
            break

    if cfgitm_dim_id is None:
        return CfgRegistry({})

    raw: dict[str, str] = {}
    dim = workspace.dimensions[cfgitm_dim_id]
    for item in dim.items:
        key = item.name
        # Only recognize known keys; ignore stray items like "4rqj5"
        if key not in _KNOWN_KEYS:
            continue
        # Address: @.value | item_id | (first item of %CFGMET, ignored)
        # We read the shortest valid address: (@.value, item.id)
        # because %CFGMET is not part of the lookup key for now.
        addr = (CHANNEL_TO_AT_ID["value"], item.id)
        try:
            value = cfg_cube.get(addr)
        except Exception:
            continue
        if value is not None:
            raw[key] = str(value)

    return CfgRegistry(raw)
