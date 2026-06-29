"""Middleware subscribers for the Event Bus.

This module provides middleware subscribers that tap into the command lifecycle
via the event bus. Middleware subscribes to command events and can:
- Validate commands before they execute
- Resolve semantic references
- Publish results back to the bus

Step 7: Middleware Integration — Real validation and semantic resolution.

MIDDLEWARE ARCHITECTURE

The middleware layer sits between event publishing and command execution.
It subscribes to `command.<id>.before` events and performs:

1. VALIDATION:
   - Schema validation (required parameters present, correct types)
   - Business rule validation (cell exists, dimension exists, etc.)
   - Cross-reference validation (target view exists, etc.)

2. SEMANTIC RESOLUTION:
   - Cell reference resolution (A1 → internal address tuple)
   - Dimension name resolution (dimension label → dimension id)
   - Rule expression validation

MIDDLEWARE BLOCKING

In the current implementation (v0), middleware is non-blocking:
- Validation failures are logged but do not prevent execution
- Semantic resolution failures are logged but do not prevent execution

In v1+, middleware will be blocking:
- Validation failures will reject the command before execution
- Semantic resolution results will be injected back into command params

SUBSCRIBER STATE

Each middleware subscriber maintains a cache of results:
- _validation_results: dict of command_id → validation_result
- _semantic_resolutions: dict of command_id → resolution_result

These caches can be queried after execution for debugging or audit.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Middleware state tracking
_validation_results: dict[str, Optional[dict]] = {}
_semantic_resolutions: dict[str, Any] = {}


def _validation_middleware(event: Any) -> None:
    """Schema validation middleware subscriber.

    Subscribes to command.*.before events.
    Validates command parameters before execution.
    
    In v0, validation failures are logged but do not block execution.
    In v1+, validation failures will reject the command.
    """
    command_id = getattr(event, 'command_id', None)
    params = getattr(event, 'params', {})
    context = getattr(event, 'context', None)

    if command_id is None:
        return

    # Run validation logic
    try:
        result = _validate_command(command_id, params, context)
        _validation_results[command_id] = result
    except Exception as e:
        logger.error(f"Validation middleware error for '{command_id}': {e}", exc_info=True)
        _validation_results[command_id] = None


def _semantic_resolution_middleware(event: Any) -> None:
    """Semantic resolution middleware subscriber.

    Subscribes to command.*.before events.
    Resolves cell references and semantic paths before execution.
    
    In v0, resolution failures are logged but do not block execution.
    In v1+, resolution results will be injected back into command params.
    """
    command_id = getattr(event, 'command_id', None)
    params = getattr(event, 'params', {})
    context = getattr(event, 'context', None)

    if command_id is None:
        return

    # Run semantic resolution logic
    try:
        result = _resolve_semantics(command_id, params, context)
        _semantic_resolutions[command_id] = result
    except Exception as e:
        logger.error(f"Semantic resolution middleware error for '{command_id}': {e}", exc_info=True)
        _semantic_resolutions[command_id] = None


def _is_valid_cell_ref(ref: str) -> bool:
    """Check if a string looks like a valid cell reference (e.g., A1, AB123)."""
    return bool(re.match(r'^[A-Z]+\d+$', ref.strip()))


def _parse_cell_ref(ref: str) -> Optional[tuple[str, int]]:
    """Parse a cell reference like 'A1' into (column, row).
    
    Returns (column_letter, row_number) or None if invalid.
    """
    match = re.match(r'^([A-Z]+)(\d+)$', ref.strip())
    if not match:
        return None
    return (match.group(1), int(match.group(2)))


def _validate_command(command_id: str, params: dict[str, Any], context: Any) -> Optional[dict]:
    """Validate a command's parameters using real engine rules.
    
    This performs schema validation and business rule validation:
    - Check required parameters are present
    - Validate cell references format
    - Validate dimension references exist
    - Validate property paths
    
    Returns a dict with validation results:
    - valid: bool
    - errors: list[str] (empty if valid)
    - warnings: list[str] (non-critical issues)
    """
    errors: list[str] = []
    warnings: list[str] = []

    if command_id == "set":
        target = params.get("target")
        property = params.get("property")
        value = params.get("value")

        # Check required parameters
        if not target:
            errors.append("Missing required parameter: target")
        if not property:
            errors.append("Missing required parameter: property")

        # Validate target format (e.g., "cell:A1", "group:MyGroup")
        if target:
            if ":" not in str(target):
                errors.append(f"Invalid target format (expected 'type:id'): {target}")
            else:
                target_type, target_id = str(target).split(":", 1)
                valid_target_types = {"cell", "selection", "group", "view", "dimension", "model"}
                if target_type not in valid_target_types:
                    warnings.append(f"Unknown target type: {target_type} (may still be valid)")

                # Validate cell reference format
                if target_type == "cell":
                    parsed = _parse_cell_ref(target_id)
                    if parsed is None:
                        errors.append(f"Invalid cell reference format: {target_id}")

        # Validate property path (e.g., "format.bold", "data.value")
        if property:
            valid_properties = {"format", "data", "view", "model"}
            prop_base = property.split(".")[0]
            if prop_base not in valid_properties:
                warnings.append(f"Unknown property base: {prop_base} (may still be valid)")

    elif command_id == "recalc":
        # Recalc has no required parameters, just validate include_all type
        include_all = params.get("include_all", False)
        if not isinstance(include_all, bool):
            errors.append(f"include_all must be bool, got {type(include_all).__name__}")

    elif command_id == "create":
        # Validate cube creation parameters
        cube_name = params.get("cube")
        dimensions = params.get("dimensions")

        if not cube_name:
            errors.append("Missing required parameter: cube")
        if not dimensions:
            errors.append("Missing required parameter: dimensions")

        # Validate cube name format (alphanumeric + underscore)
        if cube_name and not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', str(cube_name)):
            errors.append(f"Invalid cube name format: {cube_name} (alphanumeric + underscore only)")

        # Validate dimension reference format
        if dimensions:
            dim_list = [d.strip() for d in str(dimensions).split(",")]
            for dim in dim_list:
                if not dim:
                    errors.append(f"Empty dimension in list: {dimensions}")

    else:
        # Unknown command - log warning but allow
        warnings.append(f"Unknown command '{command_id}' — middleware validation skipped")

    result = {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "command_id": command_id,
    }

    # Log validation failures at error level
    if errors:
        logger.warning(f"Validation errors for '{command_id}': {errors}")

    return result


def _resolve_semantics(command_id: str, params: dict[str, Any], context: Any) -> Optional[dict]:
    """Resolve semantic references in command parameters.

    This performs cell reference resolution and dimension name resolution:
    - Parse cell references (A1 → internal format)
    - Validate dimension references against engine
    - Resolve property paths
    
    Returns a dict with resolution results:
    - resolved_targets: list of resolved targets
    - resolved_dimensions: list of valid dimension IDs
    - warnings: list of unresolved references
    """
    resolved_targets: list[dict] = []
    resolved_dimensions: list[str] = []
    warnings: list[str] = []

    if command_id == "set":
        target = params.get("target")
        if target and ":" in str(target):
            target_type, target_id = str(target).split(":", 1)
            
            # Resolve cell references
            if target_type == "cell":
                parsed = _parse_cell_ref(target_id)
                if parsed:
                    resolved_targets.append({
                        "type": "cell",
                        "original": target_id,
                        "parsed": {
                            "column": parsed[0],
                            "row": parsed[1],
                        },
                    })
                else:
                    warnings.append(f"Could not parse cell reference: {target_id}")

            # Resolve dimension references
            elif target_type == "dimension":
                engine = getattr(context, "engine", None)
                if engine:
                    ws = getattr(engine, "workspace", None)
                    if ws and hasattr(ws, "dimensions"):
                        dim_ids = [d.dim_id for d in ws.dimensions]
                        if target_id in dim_ids:
                            resolved_dimensions.append(target_id)
                        else:
                            warnings.append(f"Dimension '{target_id}' not found in workspace")

            # Resolve group references
            elif target_type == "group":
                # Groups are identified by name, no special resolution needed
                resolved_targets.append({
                    "type": "group",
                    "original": target_id,
                })

    elif command_id == "create":
        dimensions = params.get("dimensions")
        if dimensions:
            dim_list = [d.strip() for d in str(dimensions).split(",") if d.strip()]
            engine = getattr(context, "engine", None)
            if engine:
                ws = getattr(engine, "workspace", None)
                if ws and hasattr(ws, "dimensions"):
                    dim_ids = [d.dim_id for d in ws.dimensions]
                    for dim_name in dim_list:
                        if dim_name in dim_ids:
                            resolved_dimensions.append(dim_name)
                        else:
                            warnings.append(f"Dimension '{dim_name}' not found in workspace")

    result = {
        "resolved_targets": resolved_targets,
        "resolved_dimensions": resolved_dimensions,
        "warnings": warnings,
        "command_id": command_id,
    }

    return result


def get_validation_results() -> dict[str, Optional[dict]]:
    """Get the validation results cache."""
    return _validation_results.copy()


def get_semantic_resolutions() -> dict[str, Any]:
    """Get the semantic resolutions cache."""
    return _semantic_resolutions.copy()


def register_validation_subscribers(bus: Any) -> None:
    """Register validation middleware subscribers.

    Called during middleware initialization.
    
    Subscribers:
    - Validation middleware: subscribes to command.*.before
    """
    # Subscribe to all command.*.before events via wildcard
    bus.subscribe("command.*.before", _validation_middleware)


def register_semantic_subscribers(bus: Any) -> None:
    """Register semantic resolution middleware subscribers.

    Called during middleware initialization.
    
    Subscribers:
    - Semantic resolution middleware: subscribes to command.*.before
    """
    # Subscribe to all command.*.before events via wildcard
    bus.subscribe("command.*.before", _semantic_resolution_middleware)