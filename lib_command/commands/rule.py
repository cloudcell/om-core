"""
Rule commands - Set rules on cubes.

Creates rules that define how cells are computed.
"""

from __future__ import annotations

from typing import Any, Optional


def cmd_rule(
    ctx,
    cube_id: str,
    targets: list,
    expression: str,
    is_anchored: bool = False,
) -> dict:
    """
    Set a rule on a cube.

    REPL method: do_rule()
    Bus command: "rule"
    Events: command.rule.before / command.rule.succeeded / command.rule.failed

    Args:
        cube_id: Cube ID to set the rule on
        targets: List of (dim_name, item_name) pairs or special markers
        expression: Rule expression (e.g., "A1 * 1.1", "SUM(B1:B10)")
        is_anchored: If True, anchor to exactly one cell (default items for unspecified dims)
    """
    engine = ctx.engine
    if not engine:
        raise ValueError("No engine available")

    if not engine.workspace:
        raise ValueError("No workspace available")

    ws = engine.workspace

    # Validate cube exists
    cube = ws.cubes.get(cube_id)
    if not cube:
        # Try to find by name
        cube = engine.find_cube_by_name(cube_id)
        if not cube:
            raise ValueError(f"Cube not found: {cube_id}")

    try:
        if hasattr(engine, 'set_rule'):
            engine.set_rule(cube_id, targets, expression, is_anchored=is_anchored)
            ctx.status(f"Rule set: {targets} = {expression}")
            return {"cube_id": cube_id, "targets": targets, "expression": expression}
        else:
            raise NotImplementedError("Rule engine not available")
    except Exception as e:
        ctx.status(f"Error setting rule: {e}")
        raise


def cmd_delete_rule(
    ctx,
    rule_id: str,
) -> dict:
    """Delete a rule by ID.

    Maps to engine.delete_rule(rule_id).
    """
    engine = ctx.engine
    if not engine:
        raise ValueError("No engine available")
    if not rule_id:
        raise ValueError("rule_id is required")

    removed = engine.delete_rule(rule_id)
    return {"affected": 1 if removed else 0, "property": "rule_deleted", "rule_id": rule_id}


def cmd_update_rule(
    ctx,
    rule_id: str,
    targets: list,
    expression: str,
    is_anchored: bool = False,
) -> dict:
    """Update an existing rule's target and expression.

    Maps to engine.update_rule_full(rule_id, targets, expression, is_anchored).
    """
    engine = ctx.engine
    if not engine:
        raise ValueError("No engine available")
    if not rule_id:
        raise ValueError("rule_id is required")
    if not targets:
        raise ValueError("targets is required")
    if not expression:
        raise ValueError("expression is required")

    engine.update_rule_full(rule_id, targets, expression, is_anchored=is_anchored)
    return {"affected": 1, "property": "rule", "rule_id": rule_id}


def cmd_set_rule_order(
    ctx,
    rule_ids: list,
) -> dict:
    """Set the execution order of rules.

    Maps to engine.set_rule_order(rule_ids).
    """
    engine = ctx.engine
    if not engine:
        raise ValueError("No engine available")
    if not rule_ids:
        raise ValueError("rule_ids is required")

    engine.set_rule_order(rule_ids)
    processed = engine.recompute_dirty_nodes()
    return {"affected": len(rule_ids), "property": "rule_order", "recalculated": processed}


def cmd_set_rule(
    ctx,
    cube_id: str,
    targets: list,
    expression: str,
    is_anchored: bool = False,
) -> dict:
    """Set a rule on a cube — canonical command.

    Thin wrapper around :func:`cmd_rule` for canonical naming.
    """
    return cmd_rule(ctx, cube_id, targets, expression, is_anchored)


def cmd_apply_rule_batch(ctx, rules: list) -> dict:
    """Apply a list of rules atomically. Used by script/macro paths.

    Each rule dict must contain: cube_id, targets, expression, is_anchored.
    """
    engine = ctx.engine
    if not engine:
        raise ValueError("No engine available")

    success, error = engine.apply_rule_batch(rules)
    if not success:
        raise ValueError(error or "Rule batch failed")
    return {"affected": len(rules), "property": "rule_batch", "applied": len(rules)}


def cmd_list_rules(ctx, cube_id: str) -> dict:
    """List all rules for a cube.

    Returns {"type": "rule_list", "cube_id": str, "rules": list[dict]}.
    Each rule dict has: id, targets, expression, addr_mask, cube_id.
    """
    engine = ctx.engine
    if not engine:
        raise ValueError("No engine available")
    ws = engine.workspace
    cube = ws.cubes.get(cube_id)
    if not cube:
        cube = engine.find_cube_by_name(cube_id)
    if not cube:
        raise ValueError(f"Cube not found: {cube_id}")

    rules = [
        {
            "id": r.id,
            "targets": r.targets,
            "expression": r.expression,
            "addr_mask": r.addr_mask,
            "cube_id": r.cube_id,
        }
        for r in ws.rules.values()
        if r.cube_id == cube.id
    ]
    return {"type": "rule_list", "cube_id": cube.id, "rules": rules}