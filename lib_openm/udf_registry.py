"""
UDF (User-Defined Function) Registry.

Manages user-defined rule functions: definition, parsing, validation,
and evaluation. UDFs are workspace-scoped and stored as plain text
expressions that are parsed into ASTs at definition time.

Design:
- Single-line expression UDFs: define NAME(args) = expr
- Parsed into AST at definition time for fast evaluation
- Registered in workspace-scoped dict accessible by RuleEvaluator
- Errors validated at definition (name collision, duplicate params, syntax)
- Supports loading from .openm script files
- Supports ~/.om/udf/*.openm for global defaults
- Supports <workspace>/.udf/*.openm for workspace defaults
"""

from __future__ import annotations

import re
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from lib_openm.rule_eval.parser import _Parser
from lib_openm.rule_eval.tokenizer import _tokenise
from lib_openm.rule_eval.ast_nodes import _AstCall, _AstRef, _AstCtxRef, _AstNum, _AstStr, _AstBinOp, _AstUnOp, _FUNCTIONS
from lib_openm.rule_eval.utils import CellError, RuleValidationError


# --- UDF Definition Data ---

@dataclass(frozen=True)
class UDFDef:
    """A single UDF definition with parsed AST."""
    name: str                          # UDF name (uppercase)
    params: list[str]                  # Parameter names
    expr_str: str                      # Raw expression string
    ast: Any                           # Pre-parsed AST node (from _Parser)
    
    def signature(self) -> str:
        return f"{self.name}({', '.join(self.params)})"
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "params": list(self.params),
            "expr": self.expr_str,
        }
    
    @staticmethod
    def from_dict(d: dict) -> 'UDFDef':
        """Deserialize from dict (for workspace JSON load)."""
        import lib_openm.rule_eval.engine as engine_mod
        engine = engine_mod.RuleEvaluator()
        name = d["name"]
        params = d["params"]
        expr_str = d["expr"]
        
        # Parse expression string into AST
        tokens = _tokenise(expr_str)
        parser = _Parser(tokens)
        ast = parser.parse()
        
        return UDFDef(name=name, params=params, expr_str=expr_str, ast=ast)


# --- Global Functions Set for Tokenizer ---

# We need a mutable copy of _FUNCTIONS that includes UDFs
# Since _FUNCTIONS is a set, we create a mutable global that merges both
_UdfFunctions: set[str] = set()


def _add_to_functions_set(name: str) -> None:
    """Add a UDF name to the global functions set used by the tokenizer."""
    global _UdfFunctions
    # Ensure UDF names are always uppercase (consistent with built-in convention)
    _UdfFunctions.add(name.upper())


def _remove_from_functions_set(name: str) -> None:
    """Remove a UDF name from the global functions set."""
    global _UdfFunctions
    _UdfFunctions.discard(name.upper())


# --- Validation ---

def _validate_udf_name(name: str) -> str:
    """Validate and normalize a UDF name.
    
    Returns normalized (uppercase) name.
    Raises ValueError on validation failure.
    """
    if not name:
        raise ValueError("UDF name cannot be empty")
    
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
        raise ValueError(f"Invalid UDF name: {name!r}. Must be a valid identifier.")
    
    # Normalize to uppercase
    name = name.upper()
    
    # Check against built-in functions
    all_builtins: set[str] = set()
    # Add common built-in names from engine
    common_builtins = {
        "SUM", "AVERAGE", "IF", "ABS", "ROUND", "PI", "LN", "LOG", "LOG10",
        "EXP", "SQRT", "RAND", "RANDBETWEEN", "MAX", "MIN", "COUNT",
        "CONCAT", "SUBSTITUTE", "REPLACE", "MID", "FIND", "LEN",
        "INDEX", "OFFSET", "MATCH", "ROWS", "COLUMNS", "HLOOKUP", "VLOOKUP",
        "SLOPE", "INTERCEPT", "SUMPRODUCT", "SUMIF", "COUNTIF",
        "XIRR", "NPV", "IRR", "DESC", "REF", "SLICE", "REFS",
    }
    all_builtins.update(common_builtins)
    
    if name in all_builtins:
        raise ValueError(f"UDF name '{name}' conflicts with built-in function")
    
    return name


def _validate_udf_params(params: list[str]) -> list[str]:
    """Validate UDF parameters.
    
    Returns cleaned parameter list (uppercase).
    Raises ValueError on validation failure.
    """
    if not params:
        raise ValueError("UDF must have at least one parameter")
    
    cleaned = []
    seen = set()
    for p in params:
        p = p.strip()
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', p):
            raise ValueError(f"Invalid parameter name: {p!r}")
        p_upper = p.upper()
        if p_upper in seen:
            raise ValueError(f"Duplicate parameter: {p_upper!r}")
        if p_upper == "X" and len(params) == 1:
            # Allow single param named X (special case for single-arg UDFs)
            pass
        cleaned.append(p_upper)
        seen.add(p_upper)
    
    return cleaned


def _validate_udf_body(expr_str: str) -> Any:
    """Validate and parse the UDF expression body.
    
    Returns the parsed AST node.
    Raises RuleValidationError on parse failure.
    """
    if not expr_str or not expr_str.strip():
        raise RuleValidationError("UDF expression body cannot be empty")
    
    try:
        tokens = _tokenise(expr_str)
        parser = _Parser(tokens)
        ast = parser.parse()
        return ast
    except Exception as e:
        raise RuleValidationError(f"Invalid UDF expression: {e}")


# --- Registry ---

@dataclass
class UDFRegistry:
    """Workspace-scoped UDF registry.
    
    Stores UDF definitions for a single workspace.
    Supports loading from .openm script files.
    """
    # Map of uppercase UDF name -> UDFDef
    udfs: dict[str, UDFDef] = field(default_factory=dict)
    
    # Path to workspace .udf/ directory (optional)
    workspace_udf_dir: Optional[Path] = None
    
    # Global UDF directory (~/.om/udf/)
    global_udf_dir: Optional[Path] = None
    
    def register(self, name: str, params: list[str], expr_str: str) -> UDFDef:
        """Register a UDF definition.
        
        Validates name, params, and expression body.
        Adds UDF name to global functions set for tokenizer.
        Returns the UDFDef on success.
        """
        # Validate name
        name = _validate_udf_name(name)
        
        # Validate params
        params = _validate_udf_params(params)
        
        # Validate and parse expression body
        ast = _validate_udf_body(expr_str)
        
        # Create UDF definition
        udf_def = UDFDef(name=name, params=params, expr_str=expr_str, ast=ast)
        
        # Store in registry
        self.udfs[name] = udf_def
        
        # Add to global functions set so tokenizer accepts it
        _add_to_functions_set(name)
        
        return udf_def
    
    def unregister(self, name: str) -> None:
        """Remove a UDF from the registry."""
        name = name.upper()
        if name in self.udfs:
            del self.udfs[name]
            _remove_from_functions_set(name)
    
    def get(self, name: str) -> Optional[UDFDef]:
        """Get a UDF definition by name (case-insensitive)."""
        return self.udfs.get(name.upper())
    
    def list_all(self) -> list[UDFDef]:
        """List all registered UDFs sorted by name."""
        return sorted(self.udfs.values(), key=lambda u: u.name)
    
    def serialize(self) -> list[dict]:
        """Serialize UDFs for workspace JSON storage."""
        return [udf.to_dict() for udf in self.udfs.values()]
    
    def deserialize(self, udf_dicts: list[dict]) -> None:
        """Deserialize UDFs from workspace JSON."""
        for d in udf_dicts:
            try:
                udf_def = UDFDef.from_dict(d)
                # Also register in global functions set
                _add_to_functions_set(udf_def.name)
                self.udfs[udf_def.name] = udf_def
            except Exception as e:
                # Skip invalid UDFs during load
                print(f"[udf] Warning: skipping invalid UDF '{d.get('name', '?')}': {e}")
    
    def load_from_dir(self, dir_path: Optional[Path]) -> int:
        """Load UDFs from a directory of .openm script files.
        
        Returns number of UDFs loaded.
        """
        if not dir_path or not dir_path.is_dir():
            return 0
        
        count = 0
        for script_file in sorted(dir_path.glob("*.openm")):
            try:
                loaded = self._load_script_file(script_file)
                count += loaded
            except Exception as e:
                print(f"[udf] Warning: failed to load {script_file}: {e}")
        return count
    
    def _load_script_file(self, filepath: Path) -> int:
        """Parse and register UDFs from a single .openm script file."""
        content = filepath.read_text(encoding="utf-8")
        count = 0
        
        for line_num, line in enumerate(content.splitlines(), 1):
            line = line.strip()
            
            # Skip empty lines and comments
            if not line or line.startswith("#") or line.startswith("//"):
                continue
            
            # Try to parse as UDF definition
            match = re.match(
                r'^define\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(\s*([^)]*)\s*\)\s*=\s*(.+)$',
                line,
                re.IGNORECASE
            )
            if match:
                name = match.group(1)
                params_str = match.group(2)
                expr_str = match.group(3).strip()
                
                # Parse parameters (comma-separated, may be single)
                params = [p.strip() for p in params_str.split(",") if p.strip()]
                
                try:
                    self.register(name, params, expr_str)
                    count += 1
                except (ValueError, RuleValidationError) as e:
                    print(f"[udf] Warning in {filepath}:{line_num}: {e}")
        
        return count
    
    def clear(self) -> None:
        """Remove all UDFs and unregister from functions set."""
        for name in list(self.udfs.keys()):
            _remove_from_functions_set(name)
        self.udfs.clear()


# --- Global Registry ---

# Global registry accessible from any module
# Each workspace gets its own UDFRegistry instance
_default_registry: Optional[UDFRegistry] = None


def get_default_registry() -> UDFRegistry:
    """Get or create the default UDF registry."""
    global _default_registry
    if _default_registry is None:
        _default_registry = UDFRegistry()
    return _default_registry


def create_workspace_udf_registry(
    workspace_udf_dir: Optional[Path] = None,
    global_udf_dir: Optional[Path] = None,
) -> UDFRegistry:
    """Create a new workspace-scoped UDF registry.
    
    Auto-loads from ~/.om/udf/ (global defaults) and <workspace>/.udf/ (workspace UDFs).
    """
    registry = UDFRegistry(
        workspace_udf_dir=workspace_udf_dir,
        global_udf_dir=global_udf_dir,
    )
    
    # Load global defaults first (~/.om/udf/)
    if global_udf_dir:
        registry.load_from_dir(global_udf_dir)
    
    # Then load workspace-specific UDFs (override globals)
    if workspace_udf_dir:
        registry.load_from_dir(workspace_udf_dir)
    
    return registry


# --- UDF Evaluation ---

class UDFResolver:
    """Resolves UDF parameter names to their argument values during evaluation.
    
    Used by RuleEvaluator to substitute UDF arguments into the pre-parsed AST.
    """
    
    def __init__(self, params: list[str], args: list[Any]):
        """
        Args:
            params: UDF parameter names (uppercase)
            args: Evaluated argument values
        """
        self.params = params
        self.args = args
        # Create binding dict: param_name -> arg_value
        self._bindings: dict[str, Any] = {}
        for i, param in enumerate(params):
            if i < len(args):
                self._bindings[param] = args[i]
            else:
                self._bindings[param] = None
    
    def resolve_param(self, param_name: str) -> Any:
        """Resolve a parameter name to its value."""
        return self._bindings.get(param_name.upper())
    
    def eval_body(self, body_ast: Any) -> Any:
        """Evaluate the UDF body AST with current parameter bindings."""
        from lib_openm.rule_eval.engine import RuleEvaluator
        engine = RuleEvaluator()
        
        # We need to evaluate body_ast with parameter values substituted.
        # The body AST uses parameter names as identifiers.
        # We substitute each param ref with its value before evaluation.
        substituted = self._substitute_params(body_ast)
        
        # Evaluate the substituted AST using _eval with a resolver
        return engine._eval(substituted, None, ())
    
    def _substitute_params(self, node: Any) -> Any:
        """Recursively substitute parameter references with their values.
        
        The rule parser interprets bare identifiers as _AstCtxRef (contextual
        references), so we need to handle those as parameter lookups too.
        """
        if isinstance(node, _AstRef):
            # Explicit cell reference like [Dim.Item] — treat param name if matches
            param_name = node.item_name.upper()
            if param_name in self._bindings:
                return self._to_literal(self._bindings[param_name])
            return _AstNum(0.0)
        
        if isinstance(node, _AstCtxRef):
            # Bare identifier like 'a', 'b' in 'a - b' — treat as param if matches
            # Note: tokenizer may include trailing spaces (e.g., 'a ' from 'a - b')
            name_upper = node.name.strip().upper()
            if name_upper in self._bindings:
                return self._to_literal(self._bindings[name_upper])
            # Not a parameter — return 0.0 (should not happen for valid UDFs)
            return _AstNum(0.0)
        
        if isinstance(node, _AstNum):
            return node
        
        if isinstance(node, _AstStr):
            return node
        
        if isinstance(node, _AstBinOp):
            # Binary operation
            left = self._substitute_params(node.l)
            right = self._substitute_params(node.r)
            return _AstBinOp(op=node.op, l=left, r=right)
        
        if isinstance(node, _AstCall):
            # Function call - recursively substitute args, then evaluate via engine
            new_args = [self._substitute_params(arg) for arg in node.args]
            return _AstCall(fn=node.fn, args=new_args)
        
        if isinstance(node, _AstUnOp):
            # Unary operation
            arg = self._substitute_params(node.operand)
            return _AstUnOp(op=node.op, operand=arg)
        
        # Unknown node type - return as-is
        return node
    
    @staticmethod
    def _to_literal(val: Any) -> Any:
        """Convert a Python value to the appropriate AST literal node."""
        if val is None:
            return _AstNum(0.0)
        if isinstance(val, float):
            return _AstNum(val)
        if isinstance(val, int):
            return _AstNum(float(val))
        if isinstance(val, str):
            return _AstStr(val)
        return _AstNum(float(val)) if val is not None and val != "" else _AstNum(0.0)
