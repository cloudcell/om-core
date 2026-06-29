from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from lib_contracts.types import CalculationCancelledError

if TYPE_CHECKING:
    from lib_openm.api import Engine


@dataclass(frozen=True)
class RecalcResult:
    """Plain DTO returned by RecalculationService.run_all()."""

    completed: bool
    cancelled: bool
    error: str | None = None


class RecalculationService:
    """Narrow adapter exposing only recalc/cancel/reset semantics.

    Owned and wired by the composition root.  The GUI worker thread
    receives this adapter — never the full Engine.
    """

    def __init__(self, engine: "Engine") -> None:
        self._engine = engine

    def reset_cancel(self) -> None:
        """Reset the engine cancellation flag before a new run."""
        if hasattr(self._engine, "reset_cancel"):
            self._engine.reset_cancel()

    def run_all(self) -> RecalcResult:
        """Run a full recalculation and return a plain result object.

        This method is intended to be called from a worker thread.
        """
        try:
            if hasattr(self._engine, "recalculate_all"):
                self._engine.recalculate_all(include_all=True)
            else:
                return RecalcResult(
                    completed=False, cancelled=False, error="Engine missing recalculate_all"
                )

            cancelled = (
                self._engine.is_cancel_requested()
                if hasattr(self._engine, "is_cancel_requested")
                else False
            )
            if cancelled:
                return RecalcResult(
                    completed=False, cancelled=True, error="Calculation cancelled"
                )
            return RecalcResult(completed=True, cancelled=False, error=None)
        except CalculationCancelledError:
            return RecalcResult(
                completed=False, cancelled=True, error="Calculation cancelled"
            )
        except Exception as e:
            return RecalcResult(completed=False, cancelled=False, error=str(e))

    def cancel(self) -> None:
        """Request cancellation of an in-progress recalculation."""
        if hasattr(self._engine, "request_cancel"):
            self._engine.request_cancel()
