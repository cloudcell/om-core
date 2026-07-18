"""Neutral engine ports for lib_openm.

This module contains the ports the engine accepts as injected dependencies.
Engine ports are extension points that sit *inside* the engine boundary: they
allow the engine to delegate specific concerns to alternate implementations
without exposing engine internals to the command, runtime, GUI, persistence,
import/export, or other non-engine layers.

Current and anticipated engine ports:

- EventPublisher: the engine publishes domain events through this port. The
  command/bus layer provides the canonical implementation (BusEventPublisher).
- WorkspacePersistenceAdapter: the engine can save/load workspaces through
  this port without depending on the persistence implementation.
- ImportPort / ExportPort: forward-looking stubs for import/export operations
  so the engine can request data exchange without depending on lib_plugins.
- Future computation backends: a high-performance engine implementation
  may be plugged in as a port for heavy evaluation workloads
  while the Python engine retains the workspace graph and the public API.
- Future evaluation strategy ports: native solvers, sparse-array engines, or
  external compute adapters may be injected here without moving command or
  persistence concerns into the engine.

Command, runtime, GUI, persistence, import/export, and other non-engine
concerns are defined as ports in their own layers and must not be referenced
inside lib_openm.

All ports defined here are language-neutral: the same interfaces must be
implementable in any target language without Python-specific
dependencies.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Engine event topic constants
#
# These are the topic suffixes the engine publishes via EventPublisher.
# They are defined here (not in lib_contracts.events) because they are
# engine-internal topics, not client-facing event topics.  A remote engine
# implementation must publish the same topic strings so that the command/bus
# layer can subscribe uniformly.
# ---------------------------------------------------------------------------

EVENT_CELL_UPDATED = "cell.updated"
EVENT_CELLS_UPDATED = "cells.updated"
EVENT_DIMENSION_CREATED = "dimension.created"
EVENT_DIMENSION_DELETED = "dimension.deleted"
EVENT_DIMENSION_RENAMED = "dimension.renamed"
EVENT_DIMENSION_ITEM_CREATED = "dimension_item.created"
EVENT_DIMENSION_ITEM_RENAMED = "dimension_item.renamed"
EVENT_DIMENSION_STRUCTURE_CHANGED = "dimension.structure_changed"
EVENT_CUBE_CREATED = "cube.created"
EVENT_VIEW_CREATED = "view.created"
EVENT_VIEW_LAYOUT_CHANGED = "view.layout_changed"
EVENT_WORKSPACE_DIRTY_CHANGED = "workspace.dirty_changed"


class EventPublisher(ABC):
    """Abstract interface for publishing engine events.

    Implementations are provided by the command/bus layer (lib_command).
    The Engine never imports lib_command directly.

    This interface is language-neutral: a remote engine must provide an
    equivalent publish(topic_suffix, payload, engine_handle) function
    that the bus layer can subscribe to.
    """

    @abstractmethod
    def publish(self, topic_suffix: str, payload: dict, engine: Any) -> None:
        """Publish an event. Must never raise — caller must not be affected."""
        ...


# ---------------------------------------------------------------------------
# Workspace persistence port
#
# Moved from lib_storeadapters/ports.py so that lib_openm owns the port
# it consumes.  lib_storeadapters implementations import from here.
# ---------------------------------------------------------------------------

WorkspaceLike = Any


class WorkspacePersistenceAdapter(ABC):
    """Port for workspace file save/load.

    The engine is the consumer of this port; the implementation is provided
    by the persistence layer (lib_storeadapters).  This keeps lib_openm
    self-contained: it defines the contract it needs without depending on
    outer layers.
    """

    @abstractmethod
    def save_workspace(self, path: str | Path, workspace: WorkspaceLike) -> None:
        """Persist the workspace to the given path.

        This method must not mutate the workspace.
        """
        raise NotImplementedError

    @abstractmethod
    def load_workspace(self, path: str | Path) -> WorkspaceLike:
        """Load and return a new workspace instance from the given path."""
        raise NotImplementedError

    @abstractmethod
    def load_workspace_profiled(
        self, path: str | Path
    ) -> tuple[WorkspaceLike, dict]:
        """Load a workspace and return it with a diagnostic profile."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Import / Export ports (forward-looking stubs)
#
# These ports allow the engine to request import/export operations without
# depending on lib_plugins or lib_scripting.  The current Python engine
# does not use them yet, but they are defined here so a remote engine can
# stay self-contained when import/export support is added.
# ---------------------------------------------------------------------------


class ImportPort(ABC):
    """Port for importing external data into a workspace.

    Implementations are provided by the plugin/scripting layer.
    The engine delegates import requests through this port to avoid
    direct dependencies on lib_plugins.
    """

    @abstractmethod
    def import_data(
        self,
        source: str | Path,
        *,
        format: str | None = None,
        options: dict | None = None,
    ) -> WorkspaceLike:
        """Import data from *source* and return a workspace.

        Args:
            source: Path or URL to the data source.
            format: Optional format hint (e.g. "xlsx", "csv").
            options: Format-specific import options.

        Returns:
            A workspace populated with the imported data.
        """
        raise NotImplementedError


class ExportPort(ABC):
    """Port for exporting workspace data to external formats.

    Implementations are provided by the plugin/scripting layer.
    The engine delegates export requests through this port to avoid
    direct dependencies on lib_plugins.
    """

    @abstractmethod
    def export_data(
        self,
        workspace: WorkspaceLike,
        destination: str | Path,
        *,
        format: str | None = None,
        options: dict | None = None,
    ) -> None:
        """Export workspace data to *destination*.

        Args:
            workspace: The workspace to export.
            destination: Path or URL for the output.
            format: Optional format hint (e.g. "xlsx", "csv").
            options: Format-specific export options.
        """
        raise NotImplementedError
