"""Broadcast overlay snapshot and the caster's controls for it."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import get_series
from ..intermission import PAGES, intermission
from ..overlay import ELEMENTS, MAX_PLANNED_MAPS, get_state, set_map_plan, set_state, set_team_names, snapshot
from .deps import get_conn

router = APIRouter(prefix="/api/overlay", tags=["overlay"])


class OverlayStateRequest(BaseModel):
    # Omit a field to leave it alone; send null to clear it (series_id null = follow
    # the newest series, spotlight null = hide the player card).
    series_id: int | None = None
    spotlight: str | None = None
    sidebars: bool | None = None  # both teams' player stats down the screen edges
    # Switch overlay elements on/off, e.g. {"leaders": false}; omitted ones are left alone.
    elements: dict[str, bool] | None = None
    # The live series' map order, first drop first: [{"map": ..., "mode": ...}].
    map_plan: list[dict[str, str | None]] | None = Field(default=None, max_length=MAX_PLANNED_MAPS)
    # Pin the between-games scene to one page; null = rotate through them all.
    intermission_page: str | None = None
    # Overlay-only names for the live series, e.g. {"A": "Emperors"}; blank/null
    # reverts that team to its name in the app.
    team_names: dict[str, str | None] | None = None


@router.get("")
def overlay(conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return snapshot(conn)


@router.get("/intermission")
def overlay_intermission(conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return intermission(conn)


@router.put("")
def update_overlay(payload: OverlayStateRequest, conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    changes = {k: getattr(payload, k) for k in payload.model_fields_set if k not in ("team_names", "map_plan")}
    if changes.get("intermission_page") is not None and changes["intermission_page"] not in PAGES:
        raise HTTPException(status_code=400, detail=f"intermission_page must be one of {', '.join(PAGES)}.")
    if "elements" in changes:
        unknown = set(changes["elements"] or {}) - set(ELEMENTS)
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown overlay element(s): {', '.join(sorted(unknown))}.")
        changes["elements"] = {**get_state(conn)["elements"], **(changes["elements"] or {})}
    if "sidebars" in changes:
        changes["sidebars"] = bool(changes["sidebars"])
    if changes.get("series_id") is not None and get_series(conn, changes["series_id"]) is None:
        raise HTTPException(status_code=404, detail=f"Series {changes['series_id']} not found.")
    if isinstance(changes.get("spotlight"), str):
        changes["spotlight"] = changes["spotlight"].strip() or None
    if changes:
        set_state(conn, **changes)
    if payload.team_names:
        set_team_names(conn, payload.team_names)
    if payload.map_plan is not None:
        set_map_plan(conn, payload.map_plan)
    conn.commit()
    return snapshot(conn)
