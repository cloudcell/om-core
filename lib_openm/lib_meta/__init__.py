"""Self-describing metadata subsystem for OpenModeling.

Reads %CFG and resolves system table/field names dynamically.
"""
from .registry import CfgRegistry, load_cfg
from .bootstrap import ensure_system_cubes

__all__ = ["CfgRegistry", "load_cfg", "ensure_system_cubes"]
