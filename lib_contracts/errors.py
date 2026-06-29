"""lib_contracts.errors — client-facing error codes and exceptions.

Re-exports stable public exceptions from lib_contracts.types.
GUI and other clients import from here.
"""

from lib_contracts.types import CircularReferenceError, RuleValidationError

__all__ = ["CircularReferenceError", "RuleValidationError"]
