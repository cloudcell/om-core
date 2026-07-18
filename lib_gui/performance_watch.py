from __future__ import annotations

import logging
from typing import Callable

from PySide6 import QtCore, QtWidgets

from lib_utils.config import engine as engine_config


class PerformanceWatchDock(QtWidgets.QDockWidget):
    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        *,
        session=None,
        refresh_callback: Callable[[], None] | None = None,
        desired_state: bool | None = None,
        desired_mt_state: bool | None = None,
    ) -> None:
        super().__init__("Performance Watch", parent)
        self._session = session
        self._refresh_callback = refresh_callback

        body = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(body)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self._toggle = QtWidgets.QCheckBox("Enable incremental recompute", body)
        self._toggle.stateChanged.connect(self._on_toggle_changed)
        layout.addWidget(self._toggle)

        self._metrics_group = QtWidgets.QGroupBox("Dependency Graph Metrics", body)
        group_layout = QtWidgets.QFormLayout(self._metrics_group)
        group_layout.setContentsMargins(8, 8, 8, 8)
        group_layout.setSpacing(4)

        self._slice_hits = QtWidgets.QLabel("0", self._metrics_group)
        self._slice_hits.setToolTip(
            "Slice hits: number of cached slice/range evaluations that were reused \n"
            "during recalculation since dependency tracking was enabled."
        )
        self._slice_misses = QtWidgets.QLabel("0", self._metrics_group)
        self._slice_misses.setToolTip(
            "Slice misses: number of slice/range evaluations that had to be recomputed \n"
            "because their cache entry was missing or invalid."
        )
        self._func_hits = QtWidgets.QLabel("0", self._metrics_group)
        self._func_hits.setToolTip(
            "Function hits: number of function-node results (e.g., SUM/ABS macros) served \n"
            "from the dependency graph cache."
        )
        self._func_misses = QtWidgets.QLabel("0", self._metrics_group)
        self._func_misses.setToolTip(
            "Function misses: number of function nodes that required full recomputation \n"
            "instead of using a cached value."
        )

        group_layout.addRow("Slice hits", self._slice_hits)
        group_layout.addRow("Slice misses", self._slice_misses)
        group_layout.addRow("Function hits", self._func_hits)
        group_layout.addRow("Function misses", self._func_misses)

        layout.addWidget(self._metrics_group)

        self._refresh_btn = QtWidgets.QPushButton("Refresh", body)
        self._refresh_btn.clicked.connect(self.update_metrics)
        layout.addWidget(self._refresh_btn)

        self._separator = QtWidgets.QFrame(body)
        self._separator.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        self._separator.setFrameShadow(QtWidgets.QFrame.Shadow.Plain)
        self._separator.setStyleSheet("color: #e8ecf2;")
        self._separator.setFixedHeight(1)
        layout.addWidget(self._separator)

        self._mt_group = QtWidgets.QGroupBox("Multithreaded Recompute", body)
        mt_layout = QtWidgets.QFormLayout(self._mt_group)
        mt_layout.setContentsMargins(8, 8, 8, 8)
        mt_layout.setSpacing(4)

        self._mt_toggle = QtWidgets.QCheckBox("Enable multithreaded calculation", self._mt_group)
        self._mt_toggle.setChecked(engine_config("performance", "enable_multithreading", False))
        self._mt_toggle.stateChanged.connect(self._on_mt_toggle_changed)
        mt_layout.addRow(self._mt_toggle)

        self._mt_workers = QtWidgets.QLabel("0", self._mt_group)
        self._mt_workers.setToolTip(
            "Workers: active thread-pool size used for multithreaded dirty-node recomputation."
        )
        self._mt_parallel_runs = QtWidgets.QLabel("0", self._mt_group)
        self._mt_parallel_runs.setToolTip(
            "Parallel runs: number of times dirty-node recompute executed in multithread mode."
        )
        self._mt_parallel_nodes = QtWidgets.QLabel("0", self._mt_group)
        self._mt_parallel_nodes.setToolTip(
            "Parallel nodes: cumulative count of dirty dependency nodes processed by multithread recompute."
        )
        self._mt_parallel_frontiers = QtWidgets.QLabel("0", self._mt_group)
        self._mt_parallel_frontiers.setToolTip(
            "Parallel frontiers: cumulative topological batches processed in multithread recompute."
        )
        self._mt_last_run_ms = QtWidgets.QLabel("0", self._mt_group)
        self._mt_last_run_ms.setToolTip(
            "Last run (ms): wall-clock duration of the latest multithread dirty-node recompute run."
        )

        mt_layout.addRow("Workers", self._mt_workers)
        mt_layout.addRow("Parallel runs", self._mt_parallel_runs)
        mt_layout.addRow("Parallel nodes", self._mt_parallel_nodes)
        mt_layout.addRow("Parallel frontiers", self._mt_parallel_frontiers)
        mt_layout.addRow("Last run (ms)", self._mt_last_run_ms)

        layout.addWidget(self._mt_group)

        self._separator_after_mt = QtWidgets.QFrame(body)
        self._separator_after_mt.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        self._separator_after_mt.setFrameShadow(QtWidgets.QFrame.Shadow.Plain)
        self._separator_after_mt.setStyleSheet("color: #e8ecf2;")
        self._separator_after_mt.setFixedHeight(1)
        layout.addWidget(self._separator_after_mt)

        self._profiler_group = QtWidgets.QGroupBox("Profiler Snapshot", body)
        profiler_layout = QtWidgets.QFormLayout(self._profiler_group)
        profiler_layout.setContentsMargins(8, 8, 8, 8)
        profiler_layout.setSpacing(4)

        self._prof_hit_rate = QtWidgets.QLabel("0.0%", self._profiler_group)
        self._prof_hit_rate.setToolTip(
            "Combined cache hit rate from slice/function memoization: "
            "(slice_hits + func_hits) / (all hits + all misses)."
        )
        self._prof_mt_avg_nodes = QtWidgets.QLabel("0.00", self._profiler_group)
        self._prof_mt_avg_nodes.setToolTip(
            "Average nodes processed per multithread recompute run."
        )
        self._prof_mt_avg_frontier = QtWidgets.QLabel("0.00", self._profiler_group)
        self._prof_mt_avg_frontier.setToolTip(
            "Average nodes per topological frontier batch in multithread recompute."
        )
        self._prof_mt_max_frontier = QtWidgets.QLabel("0", self._profiler_group)
        self._prof_mt_max_frontier.setToolTip(
            "Max nodes in a single frontier batch during the latest multithread recompute run."
        )
        self._prof_mt_last_throughput = QtWidgets.QLabel("0.0 nodes/s", self._profiler_group)
        self._prof_mt_last_throughput.setToolTip(
            "Throughput on the most recent multithread recompute run: "
            "last_run_nodes / last_run_ms."
        )
        self._prof_rule_eval_eval_count = QtWidgets.QLabel("0", self._profiler_group)
        self._prof_rule_eval_eval_count.setToolTip(
            "Rule eval count captured by the internal rule profiler."
        )
        self._prof_rule_eval_eval_avg = QtWidgets.QLabel("0.000 ms", self._profiler_group)
        self._prof_rule_eval_eval_avg.setToolTip(
            "Average rule evaluation wall time from profiler snapshot."
        )
        self._prof_rule_eval_slow_count = QtWidgets.QLabel("0", self._profiler_group)
        self._prof_rule_eval_slow_count.setToolTip(
            "Number of rule evaluations above the slow-eval threshold."
        )
        self._prof_rule_eval_top_function = QtWidgets.QLabel("-", self._profiler_group)
        self._prof_rule_eval_top_function.setToolTip(
            "Most expensive function by cumulative rule evaluation time."
        )
        self._prof_top_by_count_totals = QtWidgets.QLabel("count=0 | time=0.000 ms", self._profiler_group)
        self._prof_top_by_count_totals.setToolTip(
            "Totals across top 5 rules ranked by evaluation count."
        )
        self._prof_top_by_count_list = QtWidgets.QPlainTextEdit(self._profiler_group)
        self._prof_top_by_count_list.setReadOnly(True)
        self._prof_top_by_count_list.setMaximumHeight(110)
        self._prof_top_by_count_list.setPlainText("-")
        self._prof_top_by_count_list.setToolTip(
            "Top 5 rules by evaluation count."
        )

        # Labels whose meaning changes when the remote engine is active.
        self._fidelity_labels = (
            self._slice_hits,
            self._slice_misses,
            self._func_hits,
            self._func_misses,
            self._prof_hit_rate,
            self._prof_mt_avg_nodes,
            self._prof_mt_avg_frontier,
            self._prof_mt_max_frontier,
            self._prof_mt_last_throughput,
        )
        self._original_tooltips = {label: label.toolTip() for label in self._fidelity_labels}

        self._prof_top_by_time_totals = QtWidgets.QLabel("count=0 | time=0.000 ms", self._profiler_group)
        self._prof_top_by_time_totals.setToolTip(
            "Totals across top 5 rules ranked by cumulative evaluation time."
        )
        self._prof_top_by_time_list = QtWidgets.QPlainTextEdit(self._profiler_group)
        self._prof_top_by_time_list.setReadOnly(True)
        self._prof_top_by_time_list.setMaximumHeight(110)
        self._prof_top_by_time_list.setPlainText("-")
        self._prof_top_by_time_list.setToolTip(
            "Top 5 rules by cumulative evaluation time."
        )

        profiler_layout.addRow("Cache hit rate", self._prof_hit_rate)
        profiler_layout.addRow("MT avg nodes/run", self._prof_mt_avg_nodes)
        profiler_layout.addRow("MT avg nodes/frontier", self._prof_mt_avg_frontier)
        profiler_layout.addRow("MT max nodes/frontier", self._prof_mt_max_frontier)
        profiler_layout.addRow("MT last throughput", self._prof_mt_last_throughput)
        profiler_layout.addRow("Rule eval count", self._prof_rule_eval_eval_count)
        profiler_layout.addRow("Rule avg eval", self._prof_rule_eval_eval_avg)
        profiler_layout.addRow("Rule slow evals", self._prof_rule_eval_slow_count)
        profiler_layout.addRow("Top rule function", self._prof_rule_eval_top_function)
        profiler_layout.addRow("Top 5 by count totals", self._prof_top_by_count_totals)
        profiler_layout.addRow("Top 5 rules by count", self._prof_top_by_count_list)
        profiler_layout.addRow("Top 5 by time totals", self._prof_top_by_time_totals)
        profiler_layout.addRow("Top 5 rules by time", self._prof_top_by_time_list)

        self._prof_reset_btn = QtWidgets.QPushButton("Reset profiler snapshot", self._profiler_group)
        self._prof_reset_btn.clicked.connect(self._on_profiler_reset_clicked)
        profiler_layout.addRow(self._prof_reset_btn)

        layout.addWidget(self._profiler_group)

        layout.addStretch(1)
        self.setWidget(body)

        self._refresh_timer = QtCore.QTimer(self)
        self._refresh_timer.setInterval(2000)
        self._refresh_timer.timeout.connect(self.update_metrics)

        self._apply_state(desired_state, desired_mt_state)
        # Auto-refresh is disabled by default to avoid flooding the message bus
        # with diagnostic queries when the panel is open. Users can click the
        # Refresh button to update metrics on demand.

    def _apply_state(
        self,
        desired_state: bool | None = None,
        desired_mt_state: bool | None = None,
    ) -> None:
        target_state = desired_state
        if target_state is None and self._session is not None:
            try:
                state_data = self._session.query("diagnostics_dependency_tracking_state")
                target_state = bool(state_data.get("dependency_tracking_enabled", False)) if state_data else False
            except Exception:
                target_state = False
        elif target_state is None:
            target_state = False
        self._toggle.blockSignals(True)
        self._toggle.setChecked(target_state)
        self._toggle.blockSignals(False)
        if self._session is not None and hasattr(self._session, "execute"):
            try:
                self._session.execute("set_dependency_tracking", enabled=target_state)
            except Exception:
                pass

            mt_target_state = desired_mt_state
            if mt_target_state is None:
                mt_target_state = self._mt_toggle.isChecked()
            try:
                self._session.execute("set_multithread_recompute", enabled=bool(mt_target_state))
            except Exception:
                pass

            try:
                config = self._session.query("diagnostics_multithread_config") or {}
                mt_enabled = bool(config.get("enabled", 0))
            except Exception:
                mt_enabled = False
            self._mt_toggle.blockSignals(True)
            self._mt_toggle.setChecked(mt_enabled)
            self._mt_toggle.blockSignals(False)
        self.update_metrics()

    def closeEvent(self, event):  # noqa: N802
        self._refresh_timer.stop()
        super().closeEvent(event)

    def _on_toggle_changed(self, state: int) -> None:
        if self._session is None:
            return
        enabled = state == QtCore.Qt.CheckState.Checked.value
        if hasattr(self._session, "execute"):
            self._session.execute("set_dependency_tracking", enabled=enabled)
        if self._refresh_callback is not None:
            try:
                self._refresh_callback()
            except Exception:
                pass
        self.update_metrics()

    def _on_profiler_reset_clicked(self) -> None:
        if self._session is None:
            return
        try:
            if hasattr(self._session, "execute"):
                self._session.execute("clear_profiler_snapshot")
        except Exception:
            pass
        self.update_metrics()

    def _on_mt_toggle_changed(self, state: int) -> None:
        if self._session is None:
            return
        enabled = state == QtCore.Qt.CheckState.Checked.value
        if hasattr(self._session, "execute"):
            self._session.execute("set_multithread_recompute", enabled=enabled)
        if self._refresh_callback is not None:
            try:
                self._refresh_callback()
            except Exception:
                pass
        self.update_metrics()

    def _apply_remote_fidelity(self, remote_active: bool) -> None:
        """Gray out or annotate counters not produced by the remote engine."""
        gray = "color: gray;" if remote_active else ""
        suffix = "\n[Not available while the remote engine is active.]"
        for label in self._fidelity_labels:
            label.setStyleSheet(gray)
            original = self._original_tooltips.get(label, "")
            if remote_active:
                label.setToolTip(original + suffix)
            else:
                label.setToolTip(original)

        self._mt_toggle.setEnabled(not remote_active)
        self._mt_group.setEnabled(not remote_active)

    def update_metrics(self) -> None:
        if self._session is None:
            return
        if hasattr(self._session, "is_connected") and not self._session.is_connected:
            return
        try:
            backend_info = self._session.query("diagnostics_engine_backend") or {}
        except Exception as e:
            logging.debug(f"PerformanceWatch: diagnostics_engine_backend failed: {e}")
            backend_info = {}
        remote_active = bool(
            backend_info.get("type") == "remote" and backend_info.get("connected", False)
        )
        self._apply_remote_fidelity(remote_active)

        try:
            metrics = self._session.query("diagnostics_dependency_metrics") or {}
        except Exception as e:
            # Log error but don't crash - metrics are non-critical
            logging.debug(f"PerformanceWatch: diagnostics_dependency_metrics failed: {e}")
            metrics = {}
        self._slice_hits.setText(str(metrics.get("slice_hits", 0)))
        self._slice_misses.setText(str(metrics.get("slice_misses", 0)))
        self._func_hits.setText(str(metrics.get("func_hits", 0)))
        self._func_misses.setText(str(metrics.get("func_misses", 0)))
        self._mt_workers.setText(str(metrics.get("mt_workers", 0)))
        self._mt_parallel_runs.setText(str(metrics.get("mt_parallel_runs", 0)))
        self._mt_parallel_nodes.setText(str(metrics.get("mt_parallel_nodes", 0)))
        self._mt_parallel_frontiers.setText(str(metrics.get("mt_parallel_frontiers", 0)))
        self._mt_last_run_ms.setText(str(metrics.get("mt_last_run_ms", 0)))

        slice_hits = float(metrics.get("slice_hits", 0))
        slice_misses = float(metrics.get("slice_misses", 0))
        func_hits = float(metrics.get("func_hits", 0))
        func_misses = float(metrics.get("func_misses", 0))
        total_cache_events = slice_hits + slice_misses + func_hits + func_misses
        if total_cache_events > 0:
            hit_rate = ((slice_hits + func_hits) / total_cache_events) * 100.0
            self._prof_hit_rate.setText(f"{hit_rate:.1f}%")
        else:
            self._prof_hit_rate.setText("0.0%")

        mt_runs = float(metrics.get("mt_parallel_runs", 0))
        mt_nodes = float(metrics.get("mt_parallel_nodes", 0))
        mt_frontiers = float(metrics.get("mt_parallel_frontiers", 0))
        avg_nodes_run = (mt_nodes / mt_runs) if mt_runs > 0 else 0.0
        avg_nodes_frontier = (mt_nodes / mt_frontiers) if mt_frontiers > 0 else 0.0
        self._prof_mt_avg_nodes.setText(f"{avg_nodes_run:.2f}")
        self._prof_mt_avg_frontier.setText(f"{avg_nodes_frontier:.2f}")
        self._prof_mt_max_frontier.setText(str(metrics.get("mt_last_run_max_frontier", 0)))

        last_run_ms = float(metrics.get("mt_last_run_ms", 0))
        last_run_nodes = float(metrics.get("mt_last_run_nodes", 0))
        if last_run_ms > 0:
            throughput = last_run_nodes / (last_run_ms / 1000.0)
            self._prof_mt_last_throughput.setText(f"{throughput:.1f} nodes/s")
        else:
            self._prof_mt_last_throughput.setText("0.0 nodes/s")

        try:
            snapshot = self._session.query("diagnostics_rule_eval_profile", top_n=5) or {}
        except Exception:
            snapshot = {
                "eval_count": 0,
                "eval_ms_avg": 0.0,
                "slow_eval_count": 0,
                "top_functions": [],
                "top_expressions_by_count": [],
                "top_expressions_by_time": [],
                "top_expressions_by_count_totals": {"count_total": 0, "eval_ms_total": 0.0},
                "top_expressions_by_time_totals": {"count_total": 0, "eval_ms_total": 0.0},
            }

        eval_count = int(snapshot.get("eval_count", 0))
        eval_ms_avg = float(snapshot.get("eval_ms_avg", 0.0))
        slow_eval_count = int(snapshot.get("slow_eval_count", 0))
        top_functions = snapshot.get("top_functions", [])

        self._prof_rule_eval_eval_count.setText(str(eval_count))
        self._prof_rule_eval_eval_avg.setText(f"{eval_ms_avg:.3f} ms")
        self._prof_rule_eval_slow_count.setText(str(slow_eval_count))
        if isinstance(top_functions, list) and top_functions:
            top_fn = str(top_functions[0].get("function", "-")).strip() or "-"
            self._prof_rule_eval_top_function.setText(top_fn)
        else:
            self._prof_rule_eval_top_function.setText("-")

        by_count = snapshot.get("top_expressions_by_count", [])
        by_time = snapshot.get("top_expressions_by_time", [])
        totals_by_count = snapshot.get("top_expressions_by_count_totals", {})
        totals_by_time = snapshot.get("top_expressions_by_time_totals", {})

        count_total = int(totals_by_count.get("count_total", 0)) if isinstance(totals_by_count, dict) else 0
        count_ms_total = float(totals_by_count.get("eval_ms_total", 0.0)) if isinstance(totals_by_count, dict) else 0.0
        time_total = int(totals_by_time.get("count_total", 0)) if isinstance(totals_by_time, dict) else 0
        time_ms_total = float(totals_by_time.get("eval_ms_total", 0.0)) if isinstance(totals_by_time, dict) else 0.0

        self._prof_top_by_count_totals.setText(f"count={count_total} | time={count_ms_total:.3f} ms")
        self._prof_top_by_time_totals.setText(f"count={time_total} | time={time_ms_total:.3f} ms")

        def _format_expr_rows(rows: object) -> str:
            if not isinstance(rows, list) or not rows:
                return "-"
            lines: list[str] = []
            for i, row in enumerate(rows[:5], start=1):
                if not isinstance(row, dict):
                    continue
                expr = str(row.get("expression", "")).strip() or "<empty>"
                count = int(row.get("count", 0))
                total_ms = float(row.get("total_ms", 0.0))
                lines.append(f"{i}. count={count} | time={total_ms:.3f} ms | {expr}")
            return "\n".join(lines) if lines else "-"

        self._prof_top_by_count_list.setPlainText(_format_expr_rows(by_count))
        self._prof_top_by_time_list.setPlainText(_format_expr_rows(by_time))

        self._mt_toggle.blockSignals(True)
        self._mt_toggle.setChecked(bool(metrics.get("mt_enabled", 0)))
        self._mt_toggle.blockSignals(False)
