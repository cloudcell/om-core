from __future__ import annotations

from PySide6 import QtCore, QtWidgets


class ImportProgressDialog(QtWidgets.QDialog):
    """Modal progress dialog for Excel import with progress bar and terminal-like log."""

    # Signal to request cancellation (thread-safe)
    cancel_requested = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Importing Excel Workbook")
        self.setModal(True)
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Phase indicator
        self._phase_frame = QtWidgets.QFrame()
        phase_layout = QtWidgets.QHBoxLayout(self._phase_frame)
        phase_layout.setSpacing(16)

        self._phase_extract_label = QtWidgets.QLabel("1. Extract")
        self._phase_extract_label.setStyleSheet("color: #555; padding: 4px 8px;")
        self._phase_load_label = QtWidgets.QLabel("2. Load")
        self._phase_load_label.setStyleSheet("color: #555; padding: 4px 8px;")

        phase_layout.addWidget(self._phase_extract_label)
        phase_layout.addWidget(QtWidgets.QLabel("→"))
        phase_layout.addWidget(self._phase_load_label)
        phase_layout.addStretch()

        layout.addWidget(self._phase_frame)

        # Status label
        self._status_label = QtWidgets.QLabel("Initializing...")
        self._status_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(self._status_label)

        # Progress bar
        self._progress_bar = QtWidgets.QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFormat("%p%")
        layout.addWidget(self._progress_bar)

        # Stats summary
        self._stats_label = QtWidgets.QLabel("Sheets: 0 | Values: 0 | Formulas: 0")
        self._stats_label.setStyleSheet("color: #555;")
        layout.addWidget(self._stats_label)

        # Terminal-like log area
        log_label = QtWidgets.QLabel("Import Log:")
        log_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(log_label)

        self._log_text = QtWidgets.QPlainTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setMaximumBlockCount(1000)  # Prevent unbounded growth
        self._log_text.setStyleSheet(
            "font-family: 'Consolas', 'Monaco', monospace;"
            "font-size: 11px;"
            "background-color: #1e1e1e;"
            "color: #d4d4d4;"
            "border: 1px solid #333;"
        )
        self._log_text.setPlainText("Ready to import...\n")
        layout.addWidget(self._log_text, stretch=1)

        # Button row
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()

        self._cancel_btn = QtWidgets.QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self._on_cancel)
        button_layout.addWidget(self._cancel_btn)

        self._close_btn = QtWidgets.QPushButton("Close")
        self._close_btn.setEnabled(False)
        self._close_btn.clicked.connect(self.accept)
        button_layout.addWidget(self._close_btn)

        layout.addLayout(button_layout)

        self._cancelled = False
        self._finished = False

        # Stats tracking
        self._sheets_total = 0
        self._sheets_done = 0
        self._values_loaded = 0
        self._formulas_loaded = 0

    def _on_cancel(self) -> None:
        self._cancelled = True
        self._status_label.setText("Cancelling...")
        self._log_message("[CANCEL] User requested cancellation", level="WARN")
        self._cancel_btn.setEnabled(False)
        self.cancel_requested.emit()  # Emit signal for worker thread

    def is_cancelled(self) -> bool:
        return self._cancelled

    def set_phase(self, phase: str, message: str = "") -> None:
        """Update the phase indicator (extract or load)."""
        if phase == "extract":
            self._phase_extract_label.setStyleSheet(
                "color: #fff; background-color: #2196f3; padding: 4px 12px; border-radius: 4px; font-weight: bold;"
            )
            self._phase_load_label.setStyleSheet("color: #555; padding: 4px 8px;")
            self._status_label.setText(message or "Extracting data from Excel...")
        elif phase == "load":
            self._phase_extract_label.setStyleSheet(
                "color: #4caf50; padding: 4px 8px; text-decoration: line-through;"
            )
            self._phase_load_label.setStyleSheet(
                "color: #fff; background-color: #ff9800; padding: 4px 12px; border-radius: 4px; font-weight: bold;"
            )
            self._status_label.setText(message or "Loading data into model...")
        elif phase == "complete":
            self._phase_extract_label.setStyleSheet(
                "color: #4caf50; padding: 4px 8px; text-decoration: line-through;"
            )
            self._phase_load_label.setStyleSheet(
                "color: #4caf50; padding: 4px 8px; text-decoration: line-through;"
            )

    def _log_message(self, message: str, level: str = "INFO") -> None:
        """Add a timestamped message to the log."""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        level_colors = {
            "INFO": "#569cd6",
            "WARN": "#ce9178",
            "ERROR": "#f44747",
            "SUCCESS": "#b5cea8",
            "DEBUG": "#808080",
        }
        color = level_colors.get(level, "#d4d4d4")
        html = f'<span style="color: {color}">[{timestamp}] [{level}] {message}</span>'
        self._log_text.appendHtml(html)
        # Auto-scroll to bottom
        scrollbar = self._log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        QtWidgets.QApplication.processEvents()

    def set_sheets_total(self, total: int) -> None:
        """Set total number of sheets to import."""
        self._sheets_total = total
        self._status_label.setText(f"Importing {total} sheet(s)...")
        self._log_message(f"Starting import of {total} sheet(s)", level="INFO")
        self._update_stats()

    def update_progress(self, percent: int, message: str) -> None:
        """Update progress bar and status."""
        self._progress_bar.setValue(percent)
        self._status_label.setText(message)
        self._log_message(message, level="DEBUG")
        # Force immediate UI update
        QtWidgets.QApplication.processEvents()

    def log_sheet_complete(self, sheet_name: str, values: int, formulas: int) -> None:
        """Log completion of a sheet."""
        self._sheets_done += 1
        self._values_loaded += values
        self._formulas_loaded += formulas
        self._log_message(
            f"Sheet '{sheet_name}' complete: {values} values, {formulas} formulas",
            level="SUCCESS"
        )
        self._update_stats()

    def log_error(self, message: str) -> None:
        """Log an error message."""
        self._log_message(message, level="ERROR")

    def log_info(self, message: str) -> None:
        """Log an info message."""
        self._log_message(message, level="INFO")

    def log_warn(self, message: str) -> None:
        """Log a warning message."""
        self._log_message(message, level="WARN")

    def log_success(self, message: str) -> None:
        """Log a success message."""
        self._log_message(message, level="SUCCESS")

    def _update_stats(self) -> None:
        """Update the stats label."""
        self._stats_label.setText(
            f"Sheets: {self._sheets_done}/{self._sheets_total} | "
            f"Values: {self._values_loaded} | "
            f"Formulas: {self._formulas_loaded}"
        )

    def mark_finished(self, success: bool, result_message: str) -> None:
        """Mark import as finished, enabling close button."""
        self._finished = True
        self._close_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)

        if success:
            self._progress_bar.setValue(100)
            self._status_label.setText("Import Complete")
            self._status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #4caf50;")
            self._log_message(result_message, level="SUCCESS")
        else:
            self._status_label.setText("Import Failed")
            self._status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #f44336;")
            self._log_message(result_message, level="ERROR")

        QtWidgets.QApplication.processEvents()
