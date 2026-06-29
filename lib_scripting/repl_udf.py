"""
REPL UDF (User-Defined Function) commands.

Commands:
- define NAME(args) = expr    : Define a UDF
- udfs                        : List all UDFs
- udfs NAME                   : Show UDF details
- undefine NAME               : Remove a UDF
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib_repl.repl_core import OpenMREPLCore


class REPLUDFMixin:
    """Mixin for UDF management commands."""

    def do_define(self: OpenMREPLCore, arg: str):
        """
        Define a user-defined function.
        Usage: define NAME(param1, param2, ...) = expression
        Example: define MYADD(x, y) = x + y
                 define GROWTH(val) = val * 1.05
                 define PCT(part, whole) = (part / whole) * 100

        UDFs are workspace-scoped and persisted with the workspace JSON.
        """
        arg = arg.strip()
        if not arg:
            print("Usage: define NAME(params) = expression")
            return

        # Parse: NAME(params) = expr
        match = re.match(
            r'^([a-zA-Z_][a-zA-Z0-9_]*)\s*\(\s*([^)]*)\s*\)\s*=\s*(.+)$',
            arg,
            re.IGNORECASE,
        )
        if not match:
            print(f"Error: Could not parse '{arg}'. Expected 'define NAME(params) = expression'")
            return

        name = match.group(1)
        params_str = match.group(2)
        expr = match.group(3).strip()

        # Parse parameters
        params = [p.strip() for p in params_str.split(",") if p.strip()]

        # Route through command spine
        from lib_contracts.errors import RuleValidationError
        try:
            result = self.session.execute("create_udf", name=name, params=params, expression=expr)
            if result.success:
                data = result.data
                print(f"UDF '{data['name']}' defined (params: {', '.join(data['params'])})")
            else:
                print(f"Error: {result.error}")
        except RuleValidationError as e:
            print(f"Error: {e}")
        except Exception as e:
            print(f"Error: Unexpected error defining UDF: {e}")

    def do_udfs(self: OpenMREPLCore, arg: str):
        """
        List user-defined functions.
        Usage: udfs [name]
        Example: udfs                        # List all UDFs
                 udfs MYFUNC                # Show details of MYFUNC
        """
        udfs = self.session.query("udf_list")

        if not udfs:
            print("No UDFs defined.")
            return

        if arg.strip():
            # Show details of specific UDF
            name = arg.strip().upper()
            udf_def = self.session.query("udf_detail", name=name)
            if udf_def:
                print(f"UDF: {udf_def['name']}({', '.join(udf_def['params'])})")
                print(f"  Expression: {udf_def['expression']}")
            else:
                print(f"UDF '{name}' not found")
                print(f"Available UDFs: {', '.join(u['name'] for u in udfs)}")
        else:
            # List all UDFs
            print(f"{'Name':<25} {'Params':<20} {'Expression'}")
            print("-" * 70)
            for udf in udfs:
                print(f"{udf['name']:<25} {', '.join(udf['params']):<20} {udf['expression']}")

    def do_undefine(self: OpenMREPLCore, arg: str):
        """
        Remove a user-defined function.
        Usage: undefine NAME
        Example: undefine MYFUNC
        """
        name = arg.strip()
        if not name:
            print("Usage: undefine NAME")
            return

        try:
            result = self.session.execute("delete_udf", name=name)
            if result.success:
                print(f"UDF '{name.upper()}' removed")
            else:
                print(f"Error: {result.error}")
        except Exception as e:
            print(f"Error: {e}")