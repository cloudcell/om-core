from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable

from PySide6 import QtCore, QtWidgets

# ARCHITECTURE_DEBT: direct Engine dependency — should be replaced with ImportPlan DTO
# and runtime import service via session.execute("import_excel", ...) (F6).
from lib_openm.api import Engine
from .xlsx_lite_importer import import_excel_lite, ImportResult


@dataclass
class ImportPhase:
    name: str  # "extract" or "load"
    current: int
    total: int
    message: str


class ImportWorker(QtCore.QThread):
    """Worker thread for Excel import to keep UI responsive."""

    # Signals for UI updates
    phase_changed = QtCore.Signal(str, str)  # phase_name, message
    progress_updated = QtCore.Signal(int, str)  # percent, message
    stats_updated = QtCore.Signal(int, int, int)  # sheets_done, values_loaded, formulas_loaded
    sheet_completed = QtCore.Signal(str, int, int)  # sheet_name, values, formulas
    log_message = QtCore.Signal(str, str)  # level, message
    import_finished = QtCore.Signal(object, bool, str)  # result, success, message

    def __init__(
        self,
        engine: Engine,
        path: str,
        streaming_threshold_mb: float = 5.0,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._path = path
        self._streaming_threshold_mb = streaming_threshold_mb
        self._cancelled = threading.Event()
        self._current_phase: str = "idle"
        self._extracted_data: list[Any] = []

    def cancel(self) -> None:
        """Request cancellation of the import."""
        self._cancelled.set()
        self.log_message.emit("WARN", "[CANCEL] Cancellation requested by user")

    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    def _check_cancelled(self) -> bool:
        """Check if import should stop. Call this frequently during processing."""
        if self._cancelled.is_set():
            self.log_message.emit("WARN", "[CANCEL] Import aborted")
            return True
        return False

    def _progress_callback(self, pct: int, message: str) -> None:
        """Callback passed to the importer - called from worker thread."""
        if self.is_cancelled():
            return  # Stop providing updates if cancelled

        # Emit signal which will be queued to main thread
        self.progress_updated.emit(pct, message)

        # Yield to allow main thread to process signals
        # This is critical for UI responsiveness
        self.msleep(10)  # 10ms yield allows signal processing

        # Check for cancellation after each progress update
        if self._check_cancelled():
            raise ImportCancelledError("Import cancelled by user")

    def run(self) -> None:
        """Main worker thread entry point - performs two-phase import."""
        try:
            # Phase 1: Extract data from Excel
            self._run_extraction_phase()

            if self._check_cancelled():
                self.import_finished.emit(None, False, "Import cancelled during extraction")
                return

            # Phase 2: Load data into model
            self._run_load_phase()

        except ImportCancelledError:
            self.import_finished.emit(None, False, "Import cancelled by user")
        except Exception as exc:
            self.log_message.emit("ERROR", f"Import failed: {exc}")
            self.import_finished.emit(None, False, f"Import failed: {exc}")

    def _run_extraction_phase(self) -> None:
        """Phase 1: Extract all data from Excel file into memory."""
        self._current_phase = "extract"
        self.phase_changed.emit("extract", "Reading Excel file...")
        self.log_message.emit("INFO", f"[EXTRACT] Starting extraction from: {self._path}")

        # The import_excel_lite function will be modified to support
        # two-phase operation. For now, we do extraction in one go.
        # TODO: Split import_excel_lite into extract + load phases

        self.log_message.emit("INFO", "[EXTRACT] Extraction phase complete")

    def _run_load_phase(self) -> None:
        """Phase 2: Load extracted data into the model."""
        self._current_phase = "load"
        self.phase_changed.emit("load", "Loading data into model...")
        self.log_message.emit("INFO", "[LOAD] Starting data load phase")

        # Run the actual import
        result = import_excel_lite(
            self._engine,
            self._path,
            progress_cb=self._progress_callback,
            streaming_threshold_mb=self._streaming_threshold_mb,
        )

        if self._check_cancelled():
            self.import_finished.emit(None, False, "Import cancelled during load")
            return

        # Report success
        success_msg = (
            f"Import complete: {result.sheets_imported} sheet(s), "
            f"{result.cubes_created} cube(s), "
            f"{result.values_loaded} value(s), "
            f"{result.formulas_loaded} formula(s)"
        )
        self.log_message.emit("SUCCESS", f"[COMPLETE] {success_msg}")
        self.import_finished.emit(result, True, success_msg)


class ImportCancelledError(Exception):
    """Raised when user cancels the import."""
    pass
