"""set_variable command handler - client-side scripting variable assignment.

This command is intercepted client-side and must not cross remote transport.
It mutates the execution context's variable store, not workspace state.
"""

from __future__ import annotations


def cmd_set_variable(ctx, name: str, value, global_scope: bool = False) -> dict:
    """Set a scripting variable in the execution context.

    Args:
        ctx: ExecutionContext with a variables dict
        name: Variable name
        value: Variable value (any JSON-serializable type)
        global_scope: If True, store in global_vars; otherwise local variables

    Returns:
        dict with name and value
    """
    if not name or not isinstance(name, str):
        raise ValueError("Variable name must be a non-empty string")

    store = ctx.global_vars if global_scope else getattr(ctx, "variables", {})
    store[name] = value

    return {"name": name, "value": value, "global": global_scope}
