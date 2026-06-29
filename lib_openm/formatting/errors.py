"""lib_openm.formatting.errors — compatibility re-export.

The canonical location is lib_contracts.types.
"""

from lib_contracts.types import (
    DeferredFormatRendering,
    FormatError,
    InvalidFormatArgument,
    InvalidFormatString,
    UnknownFormatPreset,
    UnsupportedFormatPattern,
)

__all__ = [
    "DeferredFormatRendering",
    "FormatError",
    "InvalidFormatArgument",
    "InvalidFormatString",
    "UnknownFormatPreset",
    "UnsupportedFormatPattern",
]
