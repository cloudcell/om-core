from __future__ import annotations

import re
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from posixpath import normpath
from pathlib import PurePosixPath
from typing import Any, Callable
from xml.etree import ElementTree

# ARCHITECTURE_DEBT: direct Engine dependency — should produce ImportPlan DTO
# instead of mutating engine directly. Runtime import service should apply plan (F6).
from lib_openm.api import Engine

_NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_NS_DOC_RELS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_NS_PKG_RELS = "{http://schemas.openxmlformats.org/package/2006/relationships}"


@dataclass(frozen=True)
class _SheetCell:
    row: int
    col: int
    value: Any
    rule_body: str | None


@dataclass(frozen=True)
class _SheetData:
    name: str
    cells: tuple[_SheetCell, ...]
    max_row: int
    max_col: int


@dataclass(frozen=True)
class ImportResult:
    sheets_imported: int
    cubes_created: int
    values_loaded: int
    rules_loaded: int
    warnings: tuple[str, ...]


ProgressCallback = Callable[[int, str], None]


def _letters_for_col(index_1_based: int) -> str:
    out = ""
    n = index_1_based
    while n > 0:
        n, rem = divmod(n - 1, 26)
        out = chr(ord("A") + rem) + out
    return out


def _parse_cell_ref(ref: str) -> tuple[int, int]:
    m = re.fullmatch(r"\$?([A-Z]{1,3})\$?([0-9]+)", ref.strip().upper())
    if not m:
        raise ValueError(f"Invalid cell ref {ref!r}")
    letters, row_text = m.groups()
    col = 0
    for ch in letters:
        col = col * 26 + (ord(ch) - ord("A") + 1)
    return int(row_text), col


def _parse_cell_ref_parts(ref: str) -> tuple[int, int, bool, bool]:
    m = re.fullmatch(r"(\$?)([A-Z]{1,3})(\$?)([0-9]+)", ref.strip().upper())
    if not m:
        raise ValueError(f"Invalid cell ref {ref!r}")
    col_abs, letters, row_abs, row_text = m.groups()
    col = 0
    for ch in letters:
        col = col * 26 + (ord(ch) - ord("A") + 1)
    return int(row_text), col, bool(row_abs), bool(col_abs)


def _build_cell_ref(row: int, col: int, *, row_abs: bool, col_abs: bool) -> str:
    col_text = _letters_for_col(col)
    col_part = f"${col_text}" if col_abs else col_text
    row_part = f"${row}" if row_abs else str(row)
    return f"{col_part}{row_part}"


_CELL_REF_TOKEN_PATTERN = re.compile(r"(?<![A-Za-z0-9_])(?P<ref>\$?[A-Z]{1,3}\$?[0-9]+)")


def _expand_shared_rule_refs(rule_body: str, *, row_delta: int, col_delta: int) -> str:
    def _repl(m: re.Match[str]) -> str:
        ref = m.group("ref")
        try:
            row, col, row_abs, col_abs = _parse_cell_ref_parts(ref)
        except ValueError:
            return ref
        if not row_abs:
            row += row_delta
        if not col_abs:
            col += col_delta
        if row < 1 or col < 1:
            return ref
        return _build_cell_ref(row, col, row_abs=row_abs, col_abs=col_abs)

    return _CELL_REF_TOKEN_PATTERN.sub(_repl, rule_body)


def _sheet_token_to_name(token: str | None) -> str | None:
    if not token:
        return None
    t = token.strip()
    if t.endswith("!"):
        t = t[:-1]
    if t.startswith("'") and t.endswith("'") and len(t) >= 2:
        t = t[1:-1].replace("''", "'")
    return t


def _read_xml(zf: zipfile.ZipFile, path: str) -> ElementTree.Element:
    with zf.open(path) as f:
        return ElementTree.fromstring(f.read())


def _load_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = _read_xml(zf, "xl/sharedStrings.xml")
    out: list[str] = []
    for si in root.findall(f"{_NS_MAIN}si"):
        texts = [t.text or "" for t in si.findall(f".//{_NS_MAIN}t")]
        out.append("".join(texts))
    return out


def _load_sheet_targets(zf: zipfile.ZipFile) -> list[tuple[str, str]]:
    wb = _read_xml(zf, "xl/workbook.xml")
    rels = _read_xml(zf, "xl/_rels/workbook.xml.rels")

    rid_to_target: dict[str, str] = {}
    for rel in rels.findall(f"{_NS_PKG_RELS}Relationship"):
        rid = rel.attrib.get("Id")
        target = rel.attrib.get("Target")
        if rid and target:
            rid_to_target[rid] = target

    out: list[tuple[str, str]] = []
    for sh in wb.findall(f".//{_NS_MAIN}sheet"):
        name = sh.attrib.get("name")
        rid = sh.attrib.get(f"{_NS_DOC_RELS}id")
        if not name or not rid:
            continue
        target = rid_to_target.get(rid)
        if not target:
            continue
        sheet_path = normpath(str(PurePosixPath("xl") / PurePosixPath(target)))
        out.append((name, sheet_path))
    return out


def _load_sheet_data(zf: zipfile.ZipFile, sheet_name: str, sheet_path: str, shared_strings: list[str]) -> _SheetData:
    root = _read_xml(zf, sheet_path)
    cells: list[_SheetCell] = []
    max_row = 0
    max_col = 0
    shared_rule_bases: dict[str, tuple[int, int, str]] = {}

    for c in root.findall(f".//{_NS_MAIN}c"):
        ref = c.attrib.get("r")
        if not ref:
            continue
        try:
            row, col = _parse_cell_ref(ref)
        except ValueError:
            continue
        max_row = max(max_row, row)
        max_col = max(max_col, col)

        f_node = c.find(f"{_NS_MAIN}f")
        v_node = c.find(f"{_NS_MAIN}v")
        t = c.attrib.get("t")

        rule_body = None
        value: Any = None
        if f_node is not None:
            f_text = (f_node.text or "").strip()
            f_type = (f_node.attrib.get("t") or "").strip().lower()
            shared_idx = f_node.attrib.get("si")
            if f_text:
                rule_body = f_text
                if f_type == "shared" and shared_idx is not None:
                    shared_rule_bases[shared_idx] = (row, col, f_text)
            elif f_type == "shared" and shared_idx is not None:
                base = shared_rule_bases.get(shared_idx)
                if base is not None:
                    base_row, base_col, base_rule_body = base
                    _expand_shared_rule_refs(
                        base_rule_body,
                        row_delta=row - base_row,
                        col_delta=col - base_col,
                    )

        if rule_body is not None:
            value = None
        else:
            raw = (v_node.text if v_node is not None else "") or ""
            if t == "s":
                try:
                    idx = int(raw)
                    value = shared_strings[idx] if 0 <= idx < len(shared_strings) else ""
                except Exception:
                    value = ""
            elif t == "b":
                value = 1.0 if raw == "1" else 0.0
            else:
                try:
                    value = float(raw)
                except ValueError:
                    value = raw if raw else None

        cells.append(_SheetCell(row=row, col=col, value=value, rule_body=rule_body))

    return _SheetData(name=sheet_name, cells=tuple(cells), max_row=max_row, max_col=max_col)


def _load_sheet_data_streaming(
    zf: zipfile.ZipFile,
    sheet_name: str,
    sheet_path: str,
    shared_strings: list[str],
    batch_size: int = 5000,
) -> _SheetData:
    """Memory-efficient streaming parser for large sheets using iterparse."""
    from xml.etree.ElementTree import iterparse

    cells: list[_SheetCell] = []
    max_row = 0
    max_col = 0
    shared_rule_bases: dict[str, tuple[int, int, str]] = {}

    with zf.open(sheet_path) as f:
        # iterparse yields (event, element) pairs
        # We use 'end' event to capture fully parsed elements
        context = iterparse(f, events=("end",))
        context = iter(context)

        for event, elem in context:
            if not elem.tag.endswith("c"):  # Skip non-cell elements
                continue

            ref = elem.attrib.get("r")
            if not ref:
                elem.clear()
                continue

            try:
                row, col = _parse_cell_ref(ref)
            except ValueError:
                elem.clear()
                continue

            max_row = max(max_row, row)
            max_col = max(max_col, col)

            # Parse formula and value nodes
            f_node = elem.find(f"{_NS_MAIN}f")
            v_node = elem.find(f"{_NS_MAIN}v")
            t = elem.attrib.get("t")

            rule_body = None
            value: Any = None

            if f_node is not None:
                f_text = (f_node.text or "").strip()
                f_type = (f_node.attrib.get("t") or "").strip().lower()
                shared_idx = f_node.attrib.get("si")
                if f_text:
                    rule_body = f_text
                    if f_type == "shared" and shared_idx is not None:
                        shared_rule_bases[shared_idx] = (row, col, f_text)
                elif f_type == "shared" and shared_idx is not None:
                    base = shared_rule_bases.get(shared_idx)
                    if base is not None:
                        base_row, base_col, base_rule_body = base
                        _expand_shared_rule_refs(
                            base_rule_body,
                            row_delta=row - base_row,
                            col_delta=col - base_col,
                        )

            if rule_body is not None:
                value = None
            else:
                raw = (v_node.text if v_node is not None else "") or ""
                if t == "s":
                    try:
                        idx = int(raw)
                        value = shared_strings[idx] if 0 <= idx < len(shared_strings) else ""
                    except Exception:
                        value = ""
                elif t == "b":
                    value = 1.0 if raw == "1" else 0.0
                else:
                    try:
                        value = float(raw)
                    except ValueError:
                        value = raw if raw else None

            cells.append(_SheetCell(row=row, col=col, value=value, rule_body=rule_body))

            # Clear element to free memory
            elem.clear()

    return _SheetData(name=sheet_name, cells=tuple(cells), max_row=max_row, max_col=max_col)


def _load_xlsx_lite_sheets(path: str) -> list[_SheetData]:
    with zipfile.ZipFile(path) as zf:
        shared = _load_shared_strings(zf)
        sheets_raw = _load_sheet_targets(zf)
        return [_load_sheet_data(zf, name, target, shared) for name, target in sheets_raw]


def _load_xlsx_lite_sheets_streaming(path: str) -> list[_SheetData]:
    """Memory-efficient loader using streaming XML parser for large files."""
    with zipfile.ZipFile(path) as zf:
        shared = _load_shared_strings(zf)
        sheets_raw = _load_sheet_targets(zf)
        return [_load_sheet_data_streaming(zf, name, target, shared) for name, target in sheets_raw]


def _load_xls_lite_sheets(path: str) -> list[_SheetData]:
    try:
        import xlrd  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("Importing .xls requires the optional dependency 'xlrd'") from exc

    workbook = xlrd.open_workbook(path)
    out: list[_SheetData] = []
    for sheet in workbook.sheets():
        cells: list[_SheetCell] = []
        max_row = 0
        max_col = 0
        for row_idx in range(sheet.nrows):
            for col_idx in range(sheet.ncols):
                cell = sheet.cell(row_idx, col_idx)
                value: Any = None

                if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
                    value = None
                elif cell.ctype == xlrd.XL_CELL_TEXT:
                    value = str(cell.value)
                elif cell.ctype == xlrd.XL_CELL_BOOLEAN:
                    value = 1.0 if bool(cell.value) else 0.0
                elif cell.ctype in (xlrd.XL_CELL_NUMBER, xlrd.XL_CELL_DATE):
                    value = float(cell.value)
                elif cell.ctype == xlrd.XL_CELL_ERROR:
                    value = None
                else:
                    value = cell.value

                rule_body = None
                if hasattr(sheet, "cell_formula"):
                    try:
                        maybe_formula = sheet.cell_formula(row_idx, col_idx)  # type: ignore[attr-defined]
                    except Exception:
                        maybe_formula = ""
                    if maybe_formula:
                        formula = maybe_formula

                if rule_body is None and value is None:
                    continue

                row_1 = row_idx + 1
                col_1 = col_idx + 1
                max_row = max(max_row, row_1)
                max_col = max(max_col, col_1)
                cells.append(_SheetCell(row=row_1, col=col_1, value=value, rule_body=rule_body))

        out.append(_SheetData(name=sheet.name, cells=tuple(cells), max_row=max_row, max_col=max_col))
    return out


_FN_PATTERN = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_RANGE_PATTERN = re.compile(
    r"(?:(?P<sheet>'(?:[^']|'')+'|[A-Za-z_][A-Za-z0-9_ ]*)!)?"
    r"(?P<a>\$?[A-Z]{1,3}\$?[0-9]+):(?P<b>\$?[A-Z]{1,3}\$?[0-9]+)"
)
_SINGLE_PATTERN = re.compile(
    r"(?:(?P<sheet>'(?:[^']|'')+'|[A-Za-z_][A-Za-z0-9_ ]*)!)?"
    r"(?P<a>\$?[A-Z]{1,3}\$?[0-9]+)"
)


def _to_openm_ref(
    a_ref: str,
    b_ref: str | None,
    *,
    sheet_token: str | None,
    current_sheet_name: str,
    sheet_to_cube: dict[str, str],
) -> str:
    r1, c1 = _parse_cell_ref(a_ref)
    if b_ref is not None:
        r2, c2 = _parse_cell_ref(b_ref)
        row_part = f"Row.{min(r1, r2)}..Row.{max(r1, r2)}"
        col_part = f"Column.{_letters_for_col(min(c1, c2))}..Column.{_letters_for_col(max(c1, c2))}"
    else:
        row_part = f"Row.{r1}"
        col_part = f"Column.{_letters_for_col(c1)}"

    ref_body = f"[{row_part}, {col_part}]"
    source_sheet = _sheet_token_to_name(sheet_token) or current_sheet_name
    if source_sheet == current_sheet_name:
        return ref_body

    source_cube = sheet_to_cube.get(source_sheet, source_sheet)
    return f"{source_cube}::{ref_body}"


def translate_excel_rule_to_openm(
    rule_body: str,
    *,
    current_sheet_name: str,
    sheet_to_cube: dict[str, str],
) -> str:
    expr = rule_body.strip()
    if expr.startswith("="):
        expr = expr[1:].strip()

    expr = expr.replace(";", ",")

    def _range_repl(m: re.Match[str]) -> str:
        return _to_openm_ref(
            m.group("a"),
            m.group("b"),
            sheet_token=m.group("sheet"),
            current_sheet_name=current_sheet_name,
            sheet_to_cube=sheet_to_cube,
        )

    expr = _RANGE_PATTERN.sub(_range_repl, expr)

    def _single_repl(m: re.Match[str]) -> str:
        return _to_openm_ref(
            m.group("a"),
            None,
            sheet_token=m.group("sheet"),
            current_sheet_name=current_sheet_name,
            sheet_to_cube=sheet_to_cube,
        )

    expr = _SINGLE_PATTERN.sub(_single_repl, expr)

    def _fn_repl(m: re.Match[str]) -> str:
        fn = m.group(1)
        return f"xls_{fn.lower()}("

    expr = _FN_PATTERN.sub(_fn_repl, expr)
    return expr


def _find_dimension_id_by_name(engine: Engine, name: str, *, dim_type: str | None = None) -> str | None:
    target = name.strip().lower()
    for dim in engine.workspace.dimensions.values():
        if dim.name.strip().lower() != target:
            continue
        if dim_type is not None and dim.dim_type != dim_type:
            continue
        return dim.id
    return None


def _is_dimension_used_in_cubes(engine: Engine, dim_id: str) -> bool:
    """Check if a dimension is referenced by any cube."""
    for cube in engine.workspace.cubes.values():
        if dim_id in cube.dimension_ids:
            return True
    return False


def _ensure_dimension_with_items(engine: Engine, name: str, item_names: list[str]) -> str:
    # Look for an existing seq dimension with this name
    dim_id = _find_dimension_id_by_name(engine, name, dim_type="seq")
    if dim_id is not None:
        # Found existing seq dimension, use it
        dim = engine.require_dimension_by_id(dim_id)
    else:
        # No seq dimension found - check if there's a non-seq dimension with this name
        existing_non_seq_id = _find_dimension_id_by_name(engine, name, dim_type=None)
        if existing_non_seq_id is not None:
            # If the non-seq dimension is unused, remove it and create seq
            if not _is_dimension_used_in_cubes(engine, existing_non_seq_id):
                engine.workspace.dimensions.pop(existing_non_seq_id, None)
            # Otherwise we'll need a unique name, handled by create_dimension
        # Create the seq dimension (will use original name if we removed the non-seq one)
        dim = engine.create_dimension(name, dim_type="seq")
        dim_id = dim.id
    dim = engine.require_dimension_by_id(dim_id)

    existing = {it.name for it in dim.items}
    for item_name in item_names:
        if item_name not in existing:
            engine.create_dimension_item(dim_id, item_name)
            existing.add(item_name)
    return dim_id


def _unique_cube_name(engine: Engine, base_name: str) -> str:
    existing = {cube.name for cube in engine.workspace.cubes.values()}
    if base_name not in existing:
        return base_name
    i = 2
    while f"{base_name}_{i}" in existing:
        i += 1
    return f"{base_name}_{i}"


def _import_sheet_data(
    engine: Engine,
    sheets: list[_SheetData],
    *,
    progress_cb: ProgressCallback | None = None,
) -> ImportResult:
    if not sheets:
        return ImportResult(0, 0, 0, 0, ("Workbook has no readable sheets",))

    # Calculate extraction stats before loading
    total_cells = sum(len(sh.cells) for sh in sheets)
    extracted_rules = sum(
        1 for sh in sheets for cell in sh.cells if cell.rule_body is not None
    )
    extracted_values = sum(
        1 for sh in sheets for cell in sh.cells
        if cell.rule_body is None and cell.value is not None
    )

    if progress_cb is not None:
        progress_cb(
            0,
            f"[EXTRACTED] {len(sheets)} sheets, "
            f"{total_cells} total cells, "
            f"{extracted_rules} formulas, "
            f"{extracted_values} values"
        )

    # Disable dependency tracking during import to prevent computations
    prev_dep_tracking = getattr(engine, "_dep_tracking_enabled", False)
    engine.enable_dependency_tracking(False)

    # Immediate feedback that load phase is starting
    if progress_cb is not None:
        progress_cb(0, f"[LOAD START] Creating dimensions and cubes for {len(sheets)} sheets...")

    try:
        max_row = max((sh.max_row for sh in sheets), default=0)
        max_col = max((sh.max_col for sh in sheets), default=0)
        row_items = [str(i) for i in range(1, max_row + 1)]
        col_items = [_letters_for_col(i) for i in range(1, max_col + 1)]

        row_dim_id = _ensure_dimension_with_items(engine, "Row", row_items)
        col_dim_id = _ensure_dimension_with_items(engine, "Column", col_items)

        row_dim = engine.require_dimension_by_id(row_dim_id)
        col_dim = engine.require_dimension_by_id(col_dim_id)
        row_name_to_id = {it.name: it.id for it in row_dim.items}
        col_name_to_id = {it.name: it.id for it in col_dim.items}

        sheet_to_cube: dict[str, str] = {}
        for sh in sheets:
            cube_name = _unique_cube_name(engine, sh.name)
            cube = engine.create_cube(cube_name, [row_dim_id, col_dim_id])
            sheet_to_cube[sh.name] = cube.name

        warnings: list[str] = []
        values_loaded = 0
        rules_loaded = 0

        cube_name_to_id = {cube.name: cube.id for cube in engine.workspace.cubes.values()}

        total_sheets = len(sheets)
        next_milestone = 10
        if progress_cb is not None:
            progress_cb(0, f"Importing workbook: 0/{total_sheets} sheets")

        # Batch size for cell processing - balance between speed and UI responsiveness
        BATCH_SIZE = 1000
        PROGRESS_REPORT_INTERVAL = 1000  # Report every 1000 cells (2.8M = ~2800 updates)

        # Track total progress across all sheets with timing
        cells_processed_total = 0
        load_start_time = time.time()
        last_report_time = load_start_time
        last_report_cells = 0

        for idx, sh in enumerate(sheets, start=1):
            cube_name = sheet_to_cube[sh.name]
            cube_id = cube_name_to_id[cube_name]
            sheet_cells_total = len(sh.cells)
            sheet_cells_processed = 0

            # Report sheet start immediately
            if progress_cb is not None:
                overall_pct = int(((idx - 1) * 100) / total_sheets)
                progress_cb(
                    overall_pct,
                    f"[SHEET START {idx}/{total_sheets}] '{sh.name}': {sheet_cells_total} cells"
                )

            # Collect cells in batches for efficient loading
            batch_values: dict[tuple[str, ...], Any] = {}
            batch_rules: dict[tuple[str, ...], str] = {}
            sheet_rules = 0
            sheet_values = 0

            # Report immediately when starting cell processing
            if progress_cb is not None:
                progress_cb(
                    int((cells_processed_total * 100) / total_cells),
                    f"[PROCESSING] Sheet {idx}/{total_sheets} '{sh.name}': Starting {sheet_cells_total} cells..."
                )

            # Diagnostic: report first cell processing
            first_cell_processed = False

            for cell in sh.cells:
                # Diagnostic: report when we start actually processing cells
                if not first_cell_processed and progress_cb is not None:
                    progress_cb(
                        int((cells_processed_total * 100) / total_cells),
                        f"[FIRST CELL] Starting cell processing loop for sheet '{sh.name}'"
                    )
                    first_cell_processed = True
                row_name = str(cell.row)
                col_name = _letters_for_col(cell.col)
                row_id = row_name_to_id.get(row_name)
                col_id = col_name_to_id.get(col_name)
                if row_id is None or col_id is None:
                    sheet_cells_processed += 1
                    cells_processed_total += 1
                    continue
                addr = (row_id, col_id)

                if cell.rule_body:
                    try:
                        expr = translate_excel_rule_to_openm(
                            cell.rule_body,
                            current_sheet_name=sh.name,
                            sheet_to_cube=sheet_to_cube,
                        )
                        batch_rules[addr] = expr
                        rules_loaded += 1
                        sheet_rules += 1
                    except Exception as exc:
                        warnings.append(f"{sh.name}!{col_name}{row_name}: rule skipped ({exc})")
                        if cell.value is not None:
                            batch_values[addr] = cell.value
                            values_loaded += 1
                            sheet_values += 1
                else:
                    if cell.value is not None:
                        batch_values[addr] = cell.value
                        values_loaded += 1
                        sheet_values += 1

                sheet_cells_processed += 1
                cells_processed_total += 1

                # Report progress at intervals
                if progress_cb is not None and (cells_processed_total % PROGRESS_REPORT_INTERVAL == 0):
                    elapsed = time.time() - load_start_time
                    sheet_pct = int((sheet_cells_processed * 100) / sheet_cells_total)
                    overall_pct = int((cells_processed_total * 100) / total_cells)

                    # Calculate ETA
                    if overall_pct > 0:
                        rate = cells_processed_total / elapsed  # cells per second
                        remaining_cells = total_cells - cells_processed_total
                        eta_seconds = remaining_cells / rate if rate > 0 else 0
                        eta_str = f"{int(eta_seconds // 60)}m {int(eta_seconds % 60)}s"
                    else:
                        eta_str = "calculating..."

                    progress_cb(
                        overall_pct,
                        f"[LOAD] {overall_pct}% | "
                        f"Sheet {idx}/{total_sheets} '{sh.name}': {sheet_pct}% | "
                        f"Cells: {cells_processed_total}/{total_cells} | "
                        f"Rate: {cells_processed_total/elapsed:.0f}/s | "
                        f"ETA: {eta_str}"
                    )
                    last_report_time = time.time()
                    last_report_cells = cells_processed_total

                # Flush batch when it reaches threshold
                if len(batch_values) + len(batch_rules) >= BATCH_SIZE:
                    batch_flush_start = time.time()
                    engine.batch_set_cell_data(cube_id, batch_values, batch_rules)
                    batch_flush_elapsed = time.time() - batch_flush_start
                    batch_values.clear()
                    batch_rules.clear()
                    # Report batch flush with timing
                    if progress_cb is not None:
                        elapsed = time.time() - load_start_time
                        sheet_pct = int((sheet_cells_processed * 100) / sheet_cells_total)
                        overall_pct = int((cells_processed_total * 100) / total_cells)
                        progress_cb(
                            overall_pct,
                            f"[BATCH] {overall_pct}% | "
                            f"Sheet '{sh.name}': {sheet_pct}% | "
                            f"Flush: {batch_flush_elapsed:.2f}s | "
                            f"Total: {elapsed:.1f}s"
                        )

            # Flush remaining cells in final batch
            if batch_values or batch_rules:
                engine.batch_set_cell_data(cube_id, batch_values, batch_rules)

            # Log sheet completion
            if progress_cb is not None:
                overall_pct = int((cells_processed_total * 100) / total_cells)
                progress_cb(
                    overall_pct,
                    f"Sheet {idx}/{total_sheets} '{sh.name}' COMPLETE: "
                    f"{sheet_rules} formulas, {sheet_values} values loaded"
                )

        if progress_cb is not None and next_milestone <= 100:
            progress_cb(100, f"Importing workbook: {total_sheets}/{total_sheets} sheets (100%)")

        # Trigger full recompute to evaluate all rules before returning
        # This ensures the model is fully computed when views are created
        if progress_cb is not None:
            progress_cb(100, "[COMPUTE] Computing all rules...")
        try:
            engine.evaluate_all_cubes()
        except Exception as exc:
            warnings.append(f"Recompute warning: {exc}")

        return ImportResult(
            sheets_imported=len(sheets),
            cubes_created=len(sheet_to_cube),
            values_loaded=values_loaded,
            rules_loaded=rules_loaded,
            warnings=tuple(warnings),
        )
    finally:
        engine.enable_dependency_tracking(prev_dep_tracking)


def import_excel_lite(
    engine: Engine,
    path: str,
    *,
    progress_cb: ProgressCallback | None = None,
    streaming_threshold_mb: float = 5.0,
) -> ImportResult:
    """Import Excel file with automatic optimization for large files.

    Args:
        engine: OpenM Engine instance
        path: Path to .xlsx or .xls file
        progress_cb: Optional callback for progress updates
        streaming_threshold_mb: Use memory-efficient streaming parser for files larger than this
    """
    suffix = Path(path).suffix.lower()
    file_size_mb = Path(path).stat().st_size / (1024 * 1024)
    use_streaming = file_size_mb > streaming_threshold_mb

    if suffix == ".xlsx":
        if use_streaming:
            sheets = _load_xlsx_lite_sheets_streaming(path)
        else:
            sheets = _load_xlsx_lite_sheets(path)
        return _import_sheet_data(engine, sheets, progress_cb=progress_cb)
    if suffix == ".xls":
        sheets = _load_xls_lite_sheets(path)
        result = _import_sheet_data(engine, sheets, progress_cb=progress_cb)
        xls_rule_warning = (
            ".xls rules are not exposed by xlrd; cached values were imported where available"
        )
        return ImportResult(
            sheets_imported=result.sheets_imported,
            cubes_created=result.cubes_created,
            values_loaded=result.values_loaded,
            rules_loaded=result.rules_loaded,
            warnings=(*result.warnings, xls_rule_warning),
        )
    raise ValueError(f"Unsupported workbook extension: {suffix or '(none)'}")


def import_xlsx_lite(
    engine: Engine,
    path: str,
    *,
    progress_cb: ProgressCallback | None = None,
) -> ImportResult:
    sheets = _load_xlsx_lite_sheets(path)
    return _import_sheet_data(engine, sheets, progress_cb=progress_cb)
