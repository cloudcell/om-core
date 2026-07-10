from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from .import_progress_dialog import ImportProgressDialog
from .import_worker import ImportWorker


def register_plugin(main_window: QtWidgets.QMainWindow, plugins_menu: QtWidgets.QMenu) -> None:
    submenu = plugins_menu.addMenu("Import *.xls / *.xlsx (lite)")
    action = submenu.addAction("Select Workbook…")

    def _run_import() -> None:
        # ARCHITECTURE_DEBT: the Excel plugin still needs direct Engine access
        # until import is exposed as a command through the command spine. The
        # engine lives on the local session context, not on MainWindow itself.
        if main_window.is_remote:  # type: ignore[attr-defined]
            QtWidgets.QMessageBox.warning(
                main_window,
                "Import unavailable",
                "Excel import is not supported in remote session mode.",
            )
            return
        ctx = main_window.session.context  # type: ignore[attr-defined]
        if ctx is None:
            QtWidgets.QMessageBox.warning(
                main_window,
                "Import unavailable",
                "No active session context is available for import.",
            )
            return
        engine = ctx.engine

        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            main_window,
            "Import Excel (lite)",
            filter="Excel Workbook (*.xlsx *.xls);;XLSX Workbook (*.xlsx);;XLS Workbook (*.xls);;All Files (*)",
        )
        if not path:
            return

        # Create and show progress dialog
        dialog = ImportProgressDialog(main_window)

        # Create worker thread for import
        worker = ImportWorker(
            engine,
            path,
            streaming_threshold_mb=5.0,
        )

        # Track stats for dialog updates
        current_sheet_idx = 0
        total_sheets_count = 0
        total_values = 0
        total_formulas = 0

        # Ensure dialog shows 0/total immediately
        def _init_stats_from_extraction(msg):
            nonlocal total_sheets_count
            try:
                if "[EXTRACTED]" in msg and "sheets" in msg:
                    parts = msg.split("sheets")[0].split()
                    if parts:
                        total_sheets_count = int(parts[-1])
                        dialog._sheets_total = total_sheets_count
                        dialog._update_stats()
            except Exception:
                pass

        dialog.update_progress(0, "Starting import...")

        def _on_progress_updated(pct, msg):
            nonlocal current_sheet_idx, total_sheets_count, total_values, total_formulas

            # Update progress bar
            dialog.update_progress(pct, msg)

            # Parse stats from message
            # Format: "[EXTRACTED] 2 sheets, 2809482 total cells, 200672 formulas, 2608810 values"
            # Format: "[LOAD] 15% | Sheet 1/2 'Sheet1': 45% | Cells: 420000/2809482 | Rate: 12500/s | ETA: 3m 15s"
            # or: "Sheet 1/2 'Sheet1' COMPLETE: 9000 formulas, 16000 values loaded"
            try:
                if "[EXTRACTED]" in msg and "sheets" in msg:
                    # Extract total sheets from extraction stats
                    # "[EXTRACTED] 2 sheets, ..."
                    parts = msg.split("sheets")[0].split()
                    if parts:
                        try:
                            total_sheets_count = int(parts[-1])
                            dialog._sheets_total = total_sheets_count
                            dialog._update_stats()  # Refresh display
                        except ValueError:
                            pass

                if "Sheet" in msg and "/" in msg:
                    # Extract sheet number
                    sheet_part = msg.split("Sheet")[1].split("/")[0].strip()
                    current_sheet_idx = int(sheet_part)

                if "COMPLETE" in msg and "formulas" in msg and "values" in msg:
                    # Extract sheet stats from completion message
                    formulas_part = msg.split("formulas")[0].strip().split()[-1]
                    values_part = msg.split("values")[0].strip().split()[-1]
                    try:
                        sheet_formulas = int(formulas_part.replace(",", ""))
                        sheet_values = int(values_part.replace(",", ""))
                        total_values += sheet_values
                        total_formulas += sheet_formulas
                    except ValueError:
                        pass

                # Update stats display
                if total_sheets_count > 0:
                    dialog._sheets_done = current_sheet_idx
                    dialog._values_loaded = total_values
                    dialog._formulas_loaded = total_formulas
                    dialog._update_stats()
            except Exception:
                pass  # Don't fail if parsing fails

        # Wire up signals from worker to dialog (thread-safe)
        worker.phase_changed.connect(
            lambda phase, msg: dialog.set_phase(phase, msg)
        )
        worker.progress_updated.connect(_on_progress_updated)
        worker.log_message.connect(
            lambda level, msg: getattr(dialog, f"log_{level.lower()}", dialog.log_info)(msg)
        )

        def _on_import_finished(result, success, message):
            dialog.mark_finished(success=success, result_message=message)

            if success and result:
                # Refresh GUI after successful import
                try:
                    main_window._dock_browser.rebuild()  # type: ignore[attr-defined]
                    main_window._reload_active_view()  # type: ignore[attr-defined]
                    main_window._flash_status_message(  # type: ignore[attr-defined]
                        f"Import complete: {result.sheets_imported} sheet(s)"
                    )
                except Exception:
                    pass

                # Log warnings if any
                if result.warnings:
                    for warning in result.warnings:
                        dialog.log_warn(warning)
            else:
                try:
                    main_window._flash_status_message("Import failed")  # type: ignore[attr-defined]
                except Exception:
                    pass

        worker.import_finished.connect(_on_import_finished)

        # Wire cancel button to worker
        dialog.cancel_requested.connect(worker.cancel)

        # Start the worker and show dialog
        worker.start()
        dialog.exec()

        # Clean up worker
        if worker.isRunning():
            worker.cancel()
            worker.wait(5000)  # Wait up to 5 seconds for clean exit
            if worker.isRunning():
                worker.terminate()  # Force terminate if still running

    action.triggered.connect(_run_import)
