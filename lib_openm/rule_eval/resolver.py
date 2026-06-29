"""CubeResolver protocol for rule body evaluation."""
from __future__ import annotations

from typing import Any


class CubeResolver:
    """Passed to RuleEvaluator.eval so expressions can look up other cells.

    ``cube_name`` is an optional textual cube/sheet qualifier. Implementations
    that do not support cross-cube addressing may safely ignore it; the engine
    will always pass ``None`` for legacy single-cube expressions.
    """

    def resolve_ref(
        self,
        dim_name: str,
        item_name: str,
        base_addr: tuple[str, ...],
        cube_name: str | None = None,
    ) -> float:
        """Return numeric value of the cell at base_addr with dim_name's slot replaced by item_name."""
        raise NotImplementedError

    def resolve_multi_ref(
        self,
        pairs: list[tuple[str, str]],
        base_addr: tuple[str, ...],
        cube_name: str | None = None,
    ) -> float:
        """Return numeric value after applying multiple dim:item overrides to base_addr."""
        raise NotImplementedError

    def slice_over_ref(
        self,
        pairs: list[tuple[str, str]],
        base_addr: tuple[str, ...],
        cube_name: str | None = None,
    ) -> list[float]:
        """Return a list of values from a reference slice described by (dim,item) pairs.

        Unlike sum_over_ref which returns a single scalar, this returns all values
        in the slice as a list, allowing explicit SLICE() calls before aggregation.
        
        Behaviour:
        - For simple refs in the *same cube*, returns values across all items
          in unconstrained dimensions.
        - When any ``item_name`` uses range syntax ``start..end``, or
          when aggregating across cubes, treats the pairs as a slice in
          the target cube and returns values across remaining unconstrained
          dimensions.
        - Range syntax is only valid for sequential dimensions
          (``dim.dim_type == "seq"``).
        """
        # Default implementation falls back to scalar (single value as list)
        if len(pairs) == 1:
            dim_name, item_name = pairs[0]
            val = self.resolve_ref(dim_name, item_name, base_addr, cube_name)
            return [val] if val is not None else []
        val = self.resolve_multi_ref(pairs, base_addr, cube_name)
        return [val] if val is not None else []

    def sum_over_ref(
        self,
        pairs: list[tuple[str, str]],
        base_addr: tuple[str, ...],
        cube_name: str | None = None,
    ) -> float:
        """Aggregate over a reference slice described by (dim,item) pairs.

        Behaviour:
        - For simple (non-range) refs in the *same cube*, keep legacy
          semantics by delegating to ``resolve_ref`` / ``resolve_multi_ref``
          so SUM behaves like a scalar sum.
        - When any ``item_name`` uses range syntax ``start..end``, or
          when aggregating across cubes, treat the pairs as a slice in
          the target cube and sum across any remaining unconstrained
          dimensions.
        - Range syntax is only valid for sequential dimensions
          (``dim.dim_type == "seq"``); using ``start..end`` on a
          non-sequential dimension raises ``RuleValidationError``.
        - Range bounds may be dynamic ``$<...>`` expressions. These are
          evaluated at runtime (using the same resolver and base
          address) and must reduce to a single-dimension reference from
          anywhere in the model. The resulting cell value is converted
          to a string and matched against the sequential dimension's
          item names.
        """
        raise NotImplementedError

    def dim_item_names(self, dim_name: str) -> list[str]:
        """All item names in the named dimension (for SUM-over-dim)."""
        raise NotImplementedError

    def label_for_dim(
        self,
        dim_name: str,
        base_addr: tuple[str, ...],
        cube_name: str | None = None,
    ) -> str:
        """Return the display label for ``dim_name`` at ``base_addr``."""
        raise NotImplementedError

    def label_for_addr(
        self,
        base_addr: tuple[str, ...],
        cube_name: str | None = None,
    ) -> str:
        """Return the default leaf label for the current address context."""
        raise NotImplementedError

    def pos_for_dim(
        self,
        dim_name: str,
        base_addr: tuple[str, ...],
        cube_name: str | None = None,
    ) -> float:
        """Return 1-based ordinal position for ``dim_name`` at ``base_addr``."""
        raise NotImplementedError
