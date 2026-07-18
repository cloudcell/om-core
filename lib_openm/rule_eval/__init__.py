"""OpenM rule evaluation engine - refactored package.

This package provides the rule body evaluation engine for OpenM.
All public APIs are exported here for backward compatibility.
"""
from __future__ import annotations

import random  # Re-export for backward compatibility (tests patch this)

# Data models
from .models import Rule

# Errors
from lib_contracts.types import RuleValidationError

# Tokenizer
from .tokenizer import _Tok, _tokenise, _TT_NUM, _TT_STR, _TT_NAME, _TT_REF, _TT_OP, _TT_COMMA, _TT_LPAREN, _TT_RPAREN, _TT_ANCHOR, _TT_EOF, _SEQ_KEYWORDS

# AST nodes
from .ast_nodes import (
    _AstNum, _AstStr, _AstBinOp, _AstUnOp, _AstRef, _AstMultiRef,
    _AstDynamicMultiRef, _AstCtxRef, _AstCall, _FUNCTIONS
)

# Reference parsing
from .refs import (
    _validate_dynamic_bound, _parse_ref_segment, _split_ref_inner,
    _split_ref_chain, parse_rule_target
)

# Parser
from .parser import _Parser

# Resolver
from .resolver import CubeResolver

# Engine
from .engine import RuleEvaluator

# Dependency extraction
from .deps import extract_refs, extract_trace_refs

__all__ = [
    # Data models
    "Rule",
    # Errors
    "RuleValidationError",
    # Tokenizer (private but used by other modules)
    "_Tok",
    "_tokenise",
    "_TT_NUM",
    "_TT_STR",
    "_TT_NAME",
    "_TT_REF",
    "_TT_OP",
    "_TT_COMMA",
    "_TT_LPAREN",
    "_TT_RPAREN",
    "_TT_ANCHOR",
    "_TT_EOF",
    "_SEQ_KEYWORDS",
    # AST nodes (private but used by other modules)
    "_AstNum",
    "_AstStr",
    "_AstBinOp",
    "_AstUnOp",
    "_AstRef",
    "_AstMultiRef",
    "_AstDynamicMultiRef",
    "_AstCtxRef",
    "_AstCall",
    "_FUNCTIONS",
    # Reference parsing (private but used by other modules)
    "_validate_dynamic_bound",
    "_parse_ref_segment",
    "_split_ref_inner",
    "_split_ref_chain",
    "parse_rule_target",
    # Parser (private but used by other modules)
    "_Parser",
    # Resolver
    "CubeResolver",
    # Engine
    "RuleEvaluator",
    # Dependency extraction
    "extract_refs",
    "extract_trace_refs",
]
