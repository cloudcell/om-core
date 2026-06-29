"""Reference parsing helpers for Improv-style syntax."""
from __future__ import annotations

import re

from .tokenizer import _SEQ_KEYWORDS
from .utils import RuleValidationError


def _validate_dynamic_bound(expr: str) -> None:
    """Validate that an expression inside $<...> resolves to a single cell.

    This is a syntactic validation - we check for range syntax (..) and
    wildcards (*) that would make the reference resolve to multiple cells.
    """
    # Check for range syntax
    if ".." in expr:
        raise RuleValidationError(
            f"Dynamic bound $<{expr}> must resolve to a single cell; "
            f"range syntax not allowed in dynamic bounds"
        )

    # Check for wildcard * in item specifications. We treat '*' as an item
    # name when it appears after a '.' or '[' or ',' (Dim.* or [Dim.*]).
    if "*" in expr:
        if re.search(r"[.\[,]\s*\*\s*(?:[,\]]|$)", expr):
            raise RuleValidationError(
                f"Dynamic bound $<{expr}> must resolve to a single cell; "
                f"wildcard not allowed in dynamic bounds"
            )


def _parse_ref_segment(segment: str) -> tuple[str, str]:
    """Parse a single Improv-style reference segment into (dim_name, item_name).

    Supported forms (all case-insensitive for lookup later):

      Dim.Item
      Dim[SEQ]            # Sequential accessor only: FIRST, LAST, PREV, NEXT, THIS
      Sheet::Dim.Item
      *.*                 # Whole-cube wildcard for global aggregates

    The dim/item separator is always a dot. Brackets after a dimension name
    are reserved for sequential accessors only; Dim[Item] for regular items
    is invalid and must use Dim.Item.
    The legacy Dim:Item form is no longer accepted; callers must migrate to
    Dim.Item.
    """

    seg = segment.strip()
    if not seg:
        raise SyntaxError("Empty cell ref segment")

    # Whole-cube wildcard: *.* means aggregate over all dimensions
    if seg == "*.*" or seg == "[*.*]":
        return ("*", "*")

    # Drop optional sheet prefix (e.g. "Balance Sheet::Dim.Item") but avoid
    # treating "::" that appear *inside* dynamic expressions like
    # Year.$<CubeAssumptions::Inputs.YearStart> as a sheet/cube prefix.
    sheet_pos = seg.find("::")
    if sheet_pos != -1:
        specials: list[int] = []
        for marker in (".", "$<", ".."):
            idx = seg.find(marker)
            if idx != -1:
                specials.append(idx)
        first_special = min(specials) if specials else -1
        if first_special == -1 or sheet_pos < first_special:
            seg = seg.split("::", 1)[1].strip()

    range_pos = seg.find("..")
    dyn_pos = seg.find("$<")

    # Validate dynamic bounds if present
    if dyn_pos != -1:
        end_dyn = seg.find(">", dyn_pos)
        if end_dyn != -1:
            dyn_expr = seg[dyn_pos + 2 : end_dyn]
            _validate_dynamic_bound(dyn_expr)

    # Determine where the "dim.item" portion ends (before any ".." or "$<").
    limit = len(seg)
    if range_pos != -1 or dyn_pos != -1:
        limit_candidates = [p for p in (range_pos, dyn_pos) if p != -1]
        limit = min(limit_candidates)

    bracket_sep = seg.rfind("[", 0, limit)
    if bracket_sep != -1 and seg.rstrip().endswith("]"):
        # Brackets after a dimension name are reserved for sequential accessors
        # only (FIRST, LAST, PREV, NEXT, THIS).  Dim[Item] for regular items is
        # invalid per c-03 rule language spec and must use Dim.Item.
        close_pos = seg.rfind("]", bracket_sep)
        if close_pos == -1:
            raise SyntaxError(f"Bad cell ref syntax: [{segment}]")
        dim_name = seg[:bracket_sep].strip()
        item_name = seg[bracket_sep + 1 : close_pos].strip()
        if not dim_name or not item_name:
            raise SyntaxError(f"Bad cell ref syntax: [{segment}]")
        if item_name.upper() not in _SEQ_KEYWORDS:
            raise SyntaxError(
                f"Invalid bracketed item reference [{segment}]. "
                f"Brackets after a dimension name are reserved for sequential "
                f"accessors ({', '.join(sorted(_SEQ_KEYWORDS))}). "
                f"Use {dim_name}.{item_name} for regular item references."
            )
        return dim_name, item_name

    # Only allow Dim.Item separator (dot), never colon.
    sep = seg.rfind(".", 0, limit)
    if sep == -1:
        sep = seg.rfind(".")

    if sep == -1:
        # Dimension-only reference (no item) - e.g., "COUNTA(Cube::Dim)"
        dim_name = seg.strip()
        item_name = ""
        if not dim_name:
            raise SyntaxError(f"Bad cell ref syntax: [{segment}]")
        return dim_name, item_name

    dim_name = seg[:sep].strip()
    item_name = seg[sep + 1 :].strip()
    if not dim_name or not item_name:
        raise SyntaxError(f"Bad cell ref syntax: [{segment}]")
    return dim_name, item_name


def _split_ref_inner(raw: str) -> list[str]:
    """Split the inside of a [..] reference on top-level commas.

    Commas that appear inside dynamic $<...> expressions or function call
    parentheses should *not* split the string.
    """

    parts: list[str] = []
    buf: list[str] = []
    dyn_depth = 0
    paren_depth = 0
    i = 0
    n = len(raw)
    while i < n:
        ch = raw[i]
        # Enter a dynamic expression when we see $<
        if ch == "$" and i + 1 < n and raw[i + 1] == "<":
            dyn_depth += 1
            buf.append(ch)
            buf.append("<")
            i += 2
            continue
        # Leave a dynamic expression when we see '>'
        if ch == ">" and dyn_depth > 0:
            dyn_depth -= 1
            buf.append(ch)
            i += 1
            continue
        # Track parentheses for function calls like DESC(...)
        if ch == "(" and dyn_depth == 0:
            paren_depth += 1
            buf.append(ch)
            i += 1
            continue
        if ch == ")" and dyn_depth == 0 and paren_depth > 0:
            paren_depth -= 1
            buf.append(ch)
            i += 1
            continue
        # Top-level comma splits segments; commas inside $<...> or (...) are kept.
        if ch == "," and dyn_depth == 0 and paren_depth == 0:
            part = "".join(buf).strip()
            if part:
                parts.append(part)
            buf = []
            i += 1
            continue

        buf.append(ch)
        i += 1

    last = "".join(buf).strip()
    if last:
        parts.append(last)
    return parts


def _split_ref_chain(segment: str) -> list[str]:
    """Split a ref segment on top-level ':' to support DimA.ItemA:DimB.ItemB sugar."""

    parts: list[str] = []
    buf: list[str] = []
    bracket_depth = 0
    dyn_depth = 0
    i = 0
    n = len(segment)
    while i < n:
        ch = segment[i]
        nxt = segment[i + 1] if i + 1 < n else ""

        if ch == "$" and nxt == "<":
            dyn_depth += 1
            buf.append(ch)
            buf.append("<")
            i += 2
            continue
        if ch == ">" and dyn_depth > 0:
            dyn_depth -= 1
            buf.append(ch)
            i += 1
            continue

        if ch == "[":
            bracket_depth += 1
            buf.append(ch)
            i += 1
            continue
        if ch == "]" and bracket_depth > 0:
            bracket_depth -= 1
            buf.append(ch)
            i += 1
            continue

        if ch == ":" and nxt == ":":
            # Part of a cube qualifier (::); keep both colons together.
            buf.append("::")
            i += 2
            continue

        if ch == ":" and bracket_depth == 0 and dyn_depth == 0:
            part = "".join(buf).strip()
            if part:
                parts.append(part)
            buf = []
            i += 1
            continue

        buf.append(ch)
        i += 1

    last = "".join(buf).strip()
    if last:
        parts.append(last)
    return parts or [segment.strip()]


def parse_rule_target(lhs: str) -> list[tuple[str, str]]:
    """Parse a rule left-hand side into one or more (dim_name, item_name) pairs.

    Supported forms (Improv-style punctuation):

      Dim:Item
      Dim.Item
      Sheet::Dim.Item
      Sheet::Dim:Item

    For multi-dimension rule targets, a bracketed, comma-separated list is
    accepted:

      [Dim1.Item1, Dim2.Item2, ...]

    Technical dimension (@) targeting for format channels:

      @.fill, @.format_number, @.font_family, etc.
      [@, fill], [@, format_number], etc.

    Each segment inside the brackets uses the same syntax as the single-dim
    case above. The caller is responsible for mapping these dimension/item
    names onto a specific cube.
    """

    text = lhs.strip()
    if not text:
        raise SyntaxError("Empty rule target")

    # Technical dimension @ targeting: @.channel or @.fill, @.number_format, etc.
    # Only apply when it's a bare @.target — not when part of a colon chain.
    if text.startswith("@.") and ":" not in text:
        channel = text[2:].strip()
        if channel:
            return [("@", channel)]
        raise SyntaxError(f"Invalid @ dimension target: {text!r}")

    # Cube-qualified wildcard sugar: allow "CubeName::*" to mean the same
    # as a bare "*" (whole-cube rule). We ignore the cube name here because
    # the active view already determines which cube the rule is applied to.
    if "::" in text and text.endswith("::*"):
        return [("*", "*")]

    # Wildcard sugar: a bare "*" on the left-hand side means "entire cube"
    # (all dimensions wildcarded). The engine interprets this special
    # (dim_name, item_name) pair when building the rule's addr_mask.
    if text == "*":
        return [("*", "*")]

    # Sugar: allow Dim1.Item1:Dim2.Item2:... on the LHS, equivalent to
    # [Dim1.Item1, Dim2.Item2, ...]. We only treat ':' as a chain separator
    # when each segment looks like a valid Dim.Item or Dim[Item] (no support
    # for sheet prefixes here); legacy Dim:Item single-dimension targets still
    # go through the normal _parse_ref_segment path below.
    if ":" in text and "." in text and not text.startswith("["):
        parts = [p.strip() for p in re.split(r"\s*:\s*", text) if p.strip()]
        # Each segment must contain a dot (Dim.Item) or brackets (Dim[Item])
        if len(parts) > 1 and all(("[" in p and "]" in p) or "." in p for p in parts):
            return [_parse_ref_segment(seg) for seg in parts]

    # Multi-dimension form: [Dim1.Item1, Dim2.Item2, ...]
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            raise SyntaxError("Empty rule target list []")
        segments = [seg.strip() for seg in inner.split(",") if seg.strip()]
        if not segments:
            raise SyntaxError("Empty rule target list []")
        return [_parse_ref_segment(seg) for seg in segments]

    # Single-dimension form.
    return [_parse_ref_segment(text)]
