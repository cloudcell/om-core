"""OpenModeling formatting subpackage: preset parser, normalizer, and errors.

Rendering lives in `lib_gui.formatting`.
"""

from .errors import (
    DeferredFormatRendering,
    FormatError,
    InvalidFormatArgument,
    InvalidFormatString,
    UnknownFormatPreset,
    UnsupportedFormatPattern,
)
from .normalizer import normalize_format_string
from .preset_parser import FormatArgValue, FormatKind, FormatPreset, PresetParser

__all__ = [
    "DeferredFormatRendering",
    "FormatArgValue",
    "FormatError",
    "FormatKind",
    "FormatPreset",
    "InvalidFormatArgument",
    "InvalidFormatString",
    "PresetParser",
    "UnknownFormatPreset",
    "UnsupportedFormatPattern",
    "normalize_format_string",
]
