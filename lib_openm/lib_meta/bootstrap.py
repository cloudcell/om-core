"""Bootstrap missing system cubes so every workspace is self-describing.

Runs after load_workspace(). Creates dimensions and cubes only if they do not
already exist by name. Existing data is never overwritten.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lib_openm.technical_ids import CHANNEL_TO_AT_ID

if TYPE_CHECKING:
    from lib_openm.model import Workspace


# ── Bootstrap edge table for %SIG ──
# Each row: (adr_name, src_target, tgt_target)
# Maps the defensible table from THEBLUEPRINT_PART_102.md
_SIG_EDGES: list[tuple[str, str, str]] = [
    ("ADR", "NUL", "NUL"),
    ("ARG", "ADR", "ADR"),
    ("SRC", "NUL", "ARG"),
    ("TGT", "ARG", "NUL"),
    ("FLD", "ADR", "ARG"),
    ("SIG", "ADR", "FLD"),
    ("OBJ", "ADR", "SIG"),
    ("REL", "OBJ", "OBJ"),
    ("REI", "ADR", "REL"),
    ("PRD", "REI", "REI"),
    ("GRD", "ADR", "PRD"),
]

# ── Default %CFG entries ──
_CFG_ENTRIES: list[tuple[str, str]] = [
    ("system_table_typ", "%TYP"),
    ("system_table_sig", "%SIG"),
    ("system_table_recnod", "%RECNOD"),
    ("system_table_recedg", "%RECEDG"),
]

# ── %TYP field code descriptions ──
# Item names use system_type_ prefix so the dimension shows stable IDs, not bare codes.
# Value format: (item_id, 3_letter_code, description)
_TYP_CODES: list[tuple[str, str, str]] = [
    ("system_type_nul", "NUL", "bootstrap type"),
    ("system_type_knd", "KND", "kind / relation type"),
    ("system_type_dim", "DIM", "dimension / context"),
    ("system_type_ref", "REF", "reference to existing object"),
    ("system_type_lbl", "LBL", "display label"),
    # ("system_type_act", "ACT", "active flag"),  # keep this
    # ("system_type_met", "MET", "metadata"),    # keep this
    # ("system_type_vis", "VIS", "visibility state"),  # keep this
    ("system_type_src", "SRC", "source node"),
    ("system_type_tgt", "TGT", "target node"),
    ("system_type_ord", "ORD", "order among siblings"),
]

# ── %RECNOD field codes ──
# These are the 3-letter codes from %TYP[*, NUL], matching system_type_* definitions
_RECNODFLD_CODES: list[str] = [
    "KND",
    "DIM",
    "REF",
    "LBL",
    "ORD",
]

# ── %RECEDG field codes ──
_RECEDGFLD_CODES: list[str] = [
    "KND",
    "SRC",
    "TGT",
    "DIM",
    "ORD",
]


def _dim_by_name(ws: "Workspace", name: str):
    """Find a dimension by its human-readable name."""
    for dim in ws.dimensions.values():
        if dim.name == name:
            return dim
    return None


def _cube_by_name(ws: "Workspace", name: str):
    """Find a cube by its human-readable name."""
    for cube in ws.cubes.values():
        if cube.name == name:
            return cube
    return None


def _item_id(dim, name: str) -> str | None:
    """Get item id by name within a dimension."""
    for it in dim.items:
        if it.name == name:
            return it.id
    return None


def _view_by_name(ws: "Workspace", name: str) -> bool:
    """Check whether a view with the given name already exists."""
    for v in ws.views.values():
        if v.name == name:
            return True
    return False


def ensure_system_cubes(ws: "Workspace") -> None:
    """Create system dimensions, cubes, and default views if missing.

    Idempotent: safe to call on every loaded workspace. Existing objects
    are left untouched.
    """
    from lib_openm.model import Cube, Dimension, TableViewSpec

    # ── 1. Ensure %CFG ──
    if _cube_by_name(ws, "%CFG") is None:
        cfgitm = _dim_by_name(ws, "%CFGITM")
        if cfgitm is None:
            cfgitm = Dimension.create("%CFGITM")
            for name, _ in _CFG_ENTRIES:
                cfgitm.add_item(name)
            ws.dimensions[cfgitm.id] = cfgitm

        cfgmet = _dim_by_name(ws, "%CFGMET")
        if cfgmet is None:
            cfgmet = Dimension.create("%CFGMET")
            cfgmet.add_item("NUL")
            ws.dimensions[cfgmet.id] = cfgmet

        cfg = Cube.create("%CFG", [cfgitm.id, cfgmet.id])
        ws.cubes[cfg.id] = cfg

        # Seed values: @.value | cfg_key | NUL -> table_name
        for key_name, table_name in _CFG_ENTRIES:
            key_id = _item_id(cfgitm, key_name)
            met_id = _item_id(cfgmet, "NUL")
            if key_id and met_id:
                addr = (key_id, met_id)
                cfg.set(addr, table_name)
                cfg.user_override_addrs.add((CHANNEL_TO_AT_ID["value"],) + addr)

        # Default view for %CFG
        if not _view_by_name(ws, "%CFG"):
            ws.add_view(TableViewSpec.create("%CFG", cfg.id, cfgitm.id, cfgmet.id, page_dim_ids=["@"]))

    # ── 2. Ensure %SIG ──
    if _cube_by_name(ws, "%SIG") is None:
        adr = _dim_by_name(ws, "%ADR")
        if adr is None:
            adr = Dimension.create("%ADR")
            for name, _, _ in _SIG_EDGES:
                if adr.items and any(it.name == name for it in adr.items):
                    continue
                adr.add_item(name)
            ws.dimensions[adr.id] = adr

        fld = _dim_by_name(ws, "%FLD")
        if fld is None:
            fld = Dimension.create("%FLD")
            fld.add_item("SRC")
            fld.add_item("TGT")
            ws.dimensions[fld.id] = fld

        sig = Cube.create("%SIG", [adr.id, fld.id])
        ws.cubes[sig.id] = sig

        # Seed bootstrap edges
        for adr_name, src_tgt, tgt_tgt in _SIG_EDGES:
            adr_id = _item_id(adr, adr_name)
            src_id = _item_id(fld, "SRC")
            tgt_id = _item_id(fld, "TGT")
            if adr_id and src_id and tgt_id:
                sig.set((adr_id, src_id), src_tgt)
                sig.user_override_addrs.add((CHANNEL_TO_AT_ID["value"], adr_id, src_id))
                sig.set((adr_id, tgt_id), tgt_tgt)
                sig.user_override_addrs.add((CHANNEL_TO_AT_ID["value"], adr_id, tgt_id))

        # Default view for %SIG
        if not _view_by_name(ws, "%SIG"):
            ws.add_view(TableViewSpec.create("%SIG", sig.id, adr.id, fld.id, page_dim_ids=["@"]))

    # ── 3. Ensure %TYP ──
    if _cube_by_name(ws, "%TYP") is None:
        typadr = _dim_by_name(ws, "%TYPADR")
        if typadr is None:
            typadr = Dimension.create("%TYPADR")
            for code_name, _, _ in _TYP_CODES:
                typadr.add_item(code_name)
            ws.dimensions[typadr.id] = typadr

        typfld = _dim_by_name(ws, "%TYPFLD")
        if typfld is None:
            typfld = Dimension.create("%TYPFLD")
            typfld.add_item("NUL")
            ws.dimensions[typfld.id] = typfld

        typ = Cube.create("%TYP", [typadr.id, typfld.id])
        ws.cubes[typ.id] = typ

        # Seed: NUL column = 3-letter code
        for code_name, code_letters, _description in _TYP_CODES:
            code_id = _item_id(typadr, code_name)
            nul_id = _item_id(typfld, "NUL")
            if code_id and nul_id:
                addr_nul = (code_id, nul_id)
                typ.set(addr_nul, code_letters)
                typ.user_override_addrs.add((CHANNEL_TO_AT_ID["value"],) + addr_nul)

        # Default view for %TYP
        if not _view_by_name(ws, "%TYP"):
            ws.add_view(TableViewSpec.create("%TYP", typ.id, typadr.id, typfld.id, page_dim_ids=["@"]))

    # ── 4. Ensure %RECNOD ──
    if _cube_by_name(ws, "%RECNOD") is None:
        recnodadr = _dim_by_name(ws, "%RECNODADR")
        if recnodadr is None:
            recnodadr = Dimension.create("%RECNODADR")
            recnodadr.add_item("NUL")
            ws.dimensions[recnodadr.id] = recnodadr

        recnodfld = _dim_by_name(ws, "%RECNODFLD")
        if recnodfld is None:
            recnodfld = Dimension.create("%RECNODFLD")
            for name in _RECNODFLD_CODES:
                recnodfld.add_item(name)
            ws.dimensions[recnodfld.id] = recnodfld
        else:
            # Upgrade: add any missing field codes
            existing_names = {it.name for it in recnodfld.items}
            for name in _RECNODFLD_CODES:
                if name not in existing_names:
                    recnodfld.add_item(name)

        recnod = Cube.create("%RECNOD", [recnodadr.id, recnodfld.id])
        ws.cubes[recnod.id] = recnod
        # %RECNOD starts empty — nodes are added by the engine / commands

        # Default view for %RECNOD
        if not _view_by_name(ws, "%RECNOD"):
            ws.add_view(TableViewSpec.create("%RECNOD", recnod.id, recnodadr.id, recnodfld.id, page_dim_ids=["@"]))

    # ── 5. Ensure %RECEDG ──
    if _cube_by_name(ws, "%RECEDG") is None:
        recedgadr = _dim_by_name(ws, "%RECEDGADR")
        if recedgadr is None:
            recedgadr = Dimension.create("%RECEDGADR")
            recedgadr.add_item("NUL")
            ws.dimensions[recedgadr.id] = recedgadr

        recedgfld = _dim_by_name(ws, "%RECEDGFLD")
        if recedgfld is None:
            recedgfld = Dimension.create("%RECEDGFLD")
            for name in _RECEDGFLD_CODES:
                recedgfld.add_item(name)
            ws.dimensions[recedgfld.id] = recedgfld

        recedg = Cube.create("%RECEDG", [recedgadr.id, recedgfld.id])
        ws.cubes[recedg.id] = recedg
        # %RECEDG starts empty — edges are added by the engine / commands

        # Default view for %RECEDG
        if not _view_by_name(ws, "%RECEDG"):
            ws.add_view(TableViewSpec.create("%RECEDG", recedg.id, recedgadr.id, recedgfld.id, page_dim_ids=["@"]))
