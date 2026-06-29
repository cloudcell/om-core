"""Import commands - Excel/CSV import via command spine."""

from __future__ import annotations

from pathlib import Path


def cmd_run_excel_import(ctx, path: str) -> dict:
    """Import an Excel file into the current workspace."""
    engine = ctx.engine
    if not engine:
        raise ValueError("No engine available")

    p = Path(path)
    if not p.exists():
        raise ValueError(f"File not found: {path}")

    ext = p.suffix.lower()
    if ext not in (".xlsx", ".xls"):
        raise ValueError(f"Unsupported Excel format: {ext}")

    from lib_plugins.excel.xlsx_lite_importer import import_xlsx_lite

    result = import_xlsx_lite(engine, str(p))
    return {
        "status": "completed" if not result.errors else "completed_with_warnings",
        "sheets_imported": result.sheets_imported,
        "cubes_created": result.cubes_created,
        "values_loaded": result.values_loaded,
        "warnings": result.errors,
    }
