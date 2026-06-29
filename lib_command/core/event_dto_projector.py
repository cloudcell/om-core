"""DTO projector that enriches canonical engine event payloads with read-only DTOs.

Must not emit events, execute commands, mutate the Engine, or call SessionGateway.
"""

from __future__ import annotations

from typing import Any

from lib_command.commands.query import cmd_cube_detail, cmd_dimension_detail, cmd_view_detail


class EventDTOProjector:
    """Enriches canonical engine event payloads with read-only DTOs.

    All enrichment is pure: it inspects engine state and returns TypedDict
    snapshots. It must not mutate the engine, emit events, or route through
    SessionGateway.
    """

    def enrich(self, topic_suffix: str, payload: dict, engine: Any) -> dict:
        enriched = dict(payload)

        if topic_suffix == "view.created":
            view_id = payload.get("view_id")
            if view_id:
                enriched["view_data"] = cmd_view_detail(engine, view_id)
        elif topic_suffix == "cube.created":
            cube_id = payload.get("cube_id")
            if cube_id:
                enriched["cube_data"] = cmd_cube_detail(engine, cube_id)
        elif topic_suffix == "dimension.created":
            dim_id = payload.get("dim_id")
            if dim_id:
                enriched["dim_data"] = cmd_dimension_detail(engine, dim_id)

        return enriched
