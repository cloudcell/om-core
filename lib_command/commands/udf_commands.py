"""UDF commands - create, delete, query user-defined functions."""

from __future__ import annotations

from typing import Any


def cmd_create_udf(ctx, name: str, params: list[str], expression: str) -> dict:
    """Register a user-defined function."""
    engine = ctx.engine
    if not engine:
        raise ValueError("No engine available")
    udf_def = engine.udf_registry.register(name, params, expression)
    return {
        "status": "created",
        "name": udf_def.name,
        "params": udf_def.params,
        "expression": udf_def.expr_str,
    }


def cmd_delete_udf(ctx, name: str) -> dict:
    """Remove a user-defined function."""
    engine = ctx.engine
    if not engine:
        raise ValueError("No engine available")
    engine.udf_registry.unregister(name)
    return {"status": "deleted", "name": name.upper()}


def query_udf_list(ctx) -> list[dict[str, Any]]:
    """List all registered UDFs."""
    engine = ctx.engine
    if not engine:
        return []
    udfs = engine.udf_registry.list_all()
    return [
        {
            "name": u.name,
            "params": u.params,
            "expression": u.expr_str,
        }
        for u in udfs
    ]


def query_udf_detail(ctx, name: str) -> dict[str, Any] | None:
    """Get details of a specific UDF."""
    engine = ctx.engine
    if not engine:
        return None
    udf = engine.udf_registry.get(name)
    if not udf:
        return None
    return {
        "name": udf.name,
        "params": udf.params,
        "expression": udf.expr_str,
    }
