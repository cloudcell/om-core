"""Dependency extraction for rule body evaluation ordering."""
from __future__ import annotations

from .tokenizer import _tokenise, _TT_REF
from .refs import _split_ref_inner, _split_ref_chain, _parse_ref_segment
from lib_contracts.types import RuleValidationError


def extract_refs(expression: str) -> list[tuple[str, str]]:
    """Return list of (dim_name, item_name) for all explicit [Dim:Item] refs in expression.

    Contextual refs (bare names) cannot be resolved without a cube, so are not returned here.
    """
    out: list[tuple[str, str]] = []
    try:
        tokens = _tokenise(expression.strip())
        for t in tokens:
            if t.kind == _TT_REF:
                parts = t.value.split(":", 1)
                if len(parts) == 2:
                    out.append((parts[0].strip(), parts[1].strip()))
    except (ValueError, TypeError):
        pass  # Malformed expression; return empty dependency list
    return out


def extract_trace_refs(expression: str) -> list[tuple[str | None, list[tuple[str, str]]]]:
    """Extract cube-qualified and loose dimension/item references from an expression.

    Uses the tokenizer to find REF tokens, then parses each one to extract
    the cube name and dim/item pairs.  Handles the @ dimension prefix,
    Dim[SEQ] sequential accessors, and multi-segment colon-separated refs
    that the old regex-based approach missed.
    """
    refs: list[tuple[str | None, list[tuple[str, str]]]] = []
    try:
        tokens = _tokenise(expression.strip())
    except Exception:
        return refs
    for t in tokens:
        if t.kind != _TT_REF:
            continue
        raw = t.value
        if not raw:
            continue
        cube_name: str | None = None
        if "::" in raw:
            prefix, rest = raw.split("::", 1)
            cube_name = prefix.strip() or None
            raw = rest.strip()
        if raw.startswith("[") and raw.endswith("]"):
            raw = raw[1:-1].strip()
        segments = _split_ref_inner(raw)
        pairs: list[tuple[str, str]] = []
        for part in segments:
            part_clean = part.strip()
            if not part_clean:
                continue
            if part_clean.startswith("[") and part_clean.endswith("]"):
                part_clean = part_clean[1:-1].strip()
            chain_segments = _split_ref_chain(part_clean)
            for seg in chain_segments:
                try:
                    dim_name, item_name = _parse_ref_segment(seg)
                    if dim_name or item_name:
                        pairs.append((dim_name, item_name))
                except (SyntaxError, ValueError, RuleValidationError):
                    continue
        if pairs:
            refs.append((cube_name, pairs))
    out: list[tuple[str | None, list[tuple[str, str]]]] = []
    seen: set[tuple[str | None, tuple[tuple[str, str], ...]]] = set()
    for cube_name, pairs in refs:
        key = (
            cube_name.strip().lower() if cube_name else None,
            tuple((dim.strip().lower(), item.strip()) for dim, item in pairs),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append((cube_name, pairs))
    return out
