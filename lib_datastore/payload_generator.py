"""Workspace serialization adapter.

NO GUI DEPENDENCIES.
Generates and restores workspace state payloads for snapshots.
This module bridges lib_datastore with lib_openm's workspace/engine.

The payload format is versioned for future compatibility:
    version: "1.0"
    cubes: Dict[cube_id, cube_data]
    dimensions: Dict[dim_id, dim_data]
    views: Dict[view_id, view_data]
    cells: Dict[cell_address, cell_value]
    metadata: workspace-level metadata
"""

from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


# Payload version for compatibility checking
PAYLOAD_VERSION = "1.0"


@dataclass
class PayloadContext:
    """Context object passed to payload operations.
    
    This allows the payload generator to access workspace state
    without direct coupling to the Engine class.
    """
    # Callbacks provided by the application
    get_workspace: Callable[[], Any]
    get_engine: Callable[[], Any]
    
    # Optional pre-computed data
    cell_count: int = 0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class PayloadGenerator:
    """Generates workspace state payloads for snapshot storage.
    
    This class serializes the current workspace state into a dictionary
    that can be JSON-encoded and stored in the DataStore.
    
    Usage:
        context = PayloadContext(
            get_workspace=lambda: ws,
            get_engine=lambda: engine,
        )
        generator = PayloadGenerator(context)
        payload = generator.generate()
    """
    
    def __init__(self, context: PayloadContext):
        self._context = context
    
    def generate(self) -> Dict[str, Any]:
        """Generate payload from current workspace state.
        
        Returns:
            Dictionary containing complete workspace state
        """
        try:
            ws = self._context.get_workspace()
            engine = self._context.get_engine()
            
            payload = {
                "version": PAYLOAD_VERSION,
                "metadata": self._extract_metadata(ws, engine),
                "cubes": self._extract_cubes(ws, engine),
                "dimensions": self._extract_dimensions(ws, engine),
                "views": self._extract_views(ws, engine),
                "cells": self._extract_cells(ws, engine),
                "cell_count": self._context.cell_count or self._count_cells(ws, engine),
            }
            
            return payload
        
        except Exception as e:
            logger.error(f"Error generating payload: {e}")
            return self._generate_minimal_payload()
    
    def _extract_metadata(self, ws: Any, engine: Any) -> Dict[str, Any]:
        """Extract workspace metadata."""
        metadata = {
            "name": getattr(ws, "name", "Untitled"),
            "description": getattr(ws, "description", ""),
        }
        metadata.update(self._context.metadata)
        return metadata
    
    def _extract_cubes(self, ws: Any, engine: Any) -> Dict[str, Any]:
        """Extract cube definitions."""
        cubes = {}
        try:
            for cube_id in engine.list_cubes():
                cube = engine.get_cube(cube_id)
                if cube:
                    cubes[cube_id] = {
                        "id": cube.id,
                        "name": cube.name,
                        "dimension_ids": list(getattr(cube, "dimension_ids", [])),
                    }
        except Exception as e:
            logger.error(f"Error extracting cubes: {e}")
        return cubes
    
    def _extract_dimensions(self, ws: Any, engine: Any) -> Dict[str, Any]:
        """Extract dimension definitions."""
        dims = {}
        try:
            for dim_id in engine.list_dimensions():
                dim = engine.get_dimension(dim_id)
                if dim:
                    dims[dim_id] = {
                        "id": dim.id,
                        "name": dim.name,
                        "items": [
                            {"id": item.id, "name": item.name}
                            for item in getattr(dim, "items", [])
                        ],
                        "dim_type": getattr(dim, "dim_type", "set"),
                        "is_technical": getattr(dim, "is_technical", False),
                    }
        except Exception as e:
            logger.error(f"Error extracting dimensions: {e}")
        return dims
    
    def _extract_views(self, ws: Any, engine: Any) -> Dict[str, Any]:
        """Extract view definitions."""
        views = {}
        try:
            for view_id in engine.list_views():
                view = engine.get_view(view_id)
                if view:
                    views[view_id] = {
                        "id": view.id,
                        "name": view.name,
                        "cube_id": view.cube_id,
                        "row_dim_ids": list(getattr(view, "row_dim_ids", [])),
                        "col_dim_ids": list(getattr(view, "col_dim_ids", [])),
                        "page_dim_ids": list(getattr(view, "page_dim_ids", [])),
                    }
        except Exception as e:
            logger.error(f"Error extracting views: {e}")
        return views
    
    def _extract_cells(self, ws: Any, engine: Any) -> Dict[str, Any]:
        """Extract cell values.
        
        Cell address format: "cube_id:row_key:col_key"
        """
        cells = {}
        try:
            for cube_id in engine.list_cubes():
                cube = engine.get_cube(cube_id)
                if not cube:
                    continue
                
                # Iterate over cube cells
                for cell in getattr(cube, "cells", {}).values():
                    addr = f"{cube_id}:{cell.row_key}:{cell.col_key}"
                    cells[addr] = {
                        "value": cell.value,
                        "formula": cell.formula,
                        "override": cell.override,
                    }
        except Exception as e:
            logger.error(f"Error extracting cells: {e}")
        return cells
    
    def _count_cells(self, ws: Any, engine: Any) -> int:
        """Count total cells in workspace."""
        try:
            count = 0
            for cube_id in engine.list_cubes():
                cube = engine.get_cube(cube_id)
                if cube:
                    count += len(getattr(cube, "cells", {}))
            return count
        except Exception:
            return 0
    
    def _generate_minimal_payload(self) -> Dict[str, Any]:
        """Generate minimal payload on error."""
        return {
            "version": PAYLOAD_VERSION,
            "metadata": self._context.metadata,
            "cubes": {},
            "dimensions": {},
            "views": {},
            "cells": {},
            "cell_count": 0,
            "error": "Failed to extract full workspace state",
        }


class PayloadRestorer:
    """Restores workspace state from a payload.
    
    This class deserializes a payload and applies it to the workspace.
    It works with the Engine to recreate cubes, dimensions, views, and cells.
    
    Usage:
        restorer = PayloadRestorer(context)
        success = restorer.restore(payload)
    """
    
    def __init__(self, context: PayloadContext):
        self._context = context
    
    def restore(self, payload: Dict[str, Any]) -> bool:
        """Restore workspace from payload.
        
        Args:
            payload: Dictionary containing workspace state
        
        Returns:
            True if successful
        """
        try:
            version = payload.get("version", PAYLOAD_VERSION)
            if version != PAYLOAD_VERSION:
                logger.warning(f"Payload version {version} may not be fully compatible")
            
            ws = self._context.get_workspace()
            engine = self._context.get_engine()
            
            # Restore in order: dimensions -> cubes -> views -> cells
            self._restore_dimensions(payload.get("dimensions", {}), ws, engine)
            self._restore_cubes(payload.get("cubes", {}), ws, engine)
            self._restore_views(payload.get("views", {}), ws, engine)
            self._restore_cells(payload.get("cells", {}), ws, engine)
            
            return True
        
        except Exception as e:
            logger.error(f"Error restoring payload: {e}")
            return False
    
    def _restore_dimensions(self, dims: Dict[str, Any], ws: Any, engine: Any):
        """Restore dimensions."""
        for dim_id, dim_data in dims.items():
            try:
                # Check if dimension exists
                existing = engine.get_dimension(dim_id)
                if not existing:
                    # Create new dimension
                    # Note: This requires Engine API for creating dimensions
                    pass  # TODO: Implement when Engine API available
            except Exception as e:
                logger.error(f"Error restoring dimension {dim_id}: {e}")
    
    def _restore_cubes(self, cubes: Dict[str, Any], ws: Any, engine: Any):
        """Restore cubes."""
        for cube_id, cube_data in cubes.items():
            try:
                existing = engine.get_cube(cube_id)
                if not existing:
                    # Create new cube
                    pass  # TODO: Implement when Engine API available
            except Exception as e:
                logger.error(f"Error restoring cube {cube_id}: {e}")
    
    def _restore_views(self, views: Dict[str, Any], ws: Any, engine: Any):
        """Restore views."""
        for view_id, view_data in views.items():
            try:
                existing = engine.get_view(view_id)
                if not existing:
                    # Create new view
                    pass  # TODO: Implement when Engine API available
            except Exception as e:
                logger.error(f"Error restoring view {view_id}: {e}")
    
    def _restore_cells(self, cells: Dict[str, Any], ws: Any, engine: Any):
        """Restore cell values."""
        for addr, cell_data in cells.items():
            try:
                # Parse address: "cube_id:row_key:col_key"
                parts = addr.split(":")
                if len(parts) != 3:
                    continue
                
                cube_id, row_key, col_key = parts
                cube = engine.get_cube(cube_id)
                if not cube:
                    continue
                
                # Set cell value
                # Note: This requires Engine API for setting cell values
                pass  # TODO: Implement when Engine API available
            
            except Exception as e:
                logger.error(f"Error restoring cell {addr}: {e}")


def create_payload_callbacks(workspace_provider: Callable[[], Any], engine_provider: Callable[[], Any]) -> tuple:
    """Create payload generator and restorer callbacks for SnapshotEngine.
    
    Args:
        workspace_provider: Callable that returns the current Workspace
        engine_provider: Callable that returns the current Engine
    
    Returns:
        Tuple of (payload_generator_callback, payload_restorer_callback)
    """
    context = PayloadContext(
        get_workspace=workspace_provider,
        get_engine=engine_provider,
    )
    
    generator = PayloadGenerator(context)
    restorer = PayloadRestorer(context)
    
    return generator.generate, restorer.restore
