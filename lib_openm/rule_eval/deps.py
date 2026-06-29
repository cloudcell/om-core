"""Dependency extraction for rule body evaluation ordering."""
from __future__ import annotations

from .tokenizer import _tokenise, _TT_REF


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
