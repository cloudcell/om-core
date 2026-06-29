"""lib_contracts.formatting — client-facing formatting contracts.

Re-exports formatting presets and errors from lib_contracts.types.
GUI formatting layer imports from here.
"""

from lib_contracts.types import (
    DeferredFormatRendering,
    FormatError,
    FormatPreset,
    InvalidFormatArgument,
    InvalidFormatString,
    UnknownFormatPreset,
    UnsupportedFormatPattern,
)

__all__ = [
    "DeferredFormatRendering",
    "FormatError",
    "FormatPreset",
    "InvalidFormatArgument",
    "InvalidFormatString",
    "UnknownFormatPreset",
    "UnsupportedFormatPattern",
]
