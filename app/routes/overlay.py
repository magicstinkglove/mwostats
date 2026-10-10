"""Broadcast overlay snapshot and the caster's controls for it."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .. import live
from ..db import add_matches_to_series, get_series, load_match
from ..intermission import PAGES, intermission
from ..overlay import (
    ELEMENTS,
    MAX_PLANNED_MAPS,
    MODE_CHOICES,
    _live_series_id,
    get_state,
    map_display_name,
    set_map_plan,
    set_state,
    set_team_names,
    snapshot,
)
from ..service import ingest_matches, maybe_autoname_teams
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


class SlotMatchRequest(BaseModel):
    # The caster's whole map order as shown (blank rows included, so `index` lines up).
    map_plan: list[dict[str, str | None]] = Field(max_length=MAX_PLANNED_MAPS)
    index: int = Field(ge=0)
    match_id: str | None = None  # null/blank clears the slot's match


@router.get("")
def overlay(conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return snapshot(conn)


@router.get("/events")
async def overlay_events(request: Request) -> StreamingResponse:
    """Server-sent events: a message each time anything on stream may have changed."""
    stream = live.changes(request.is_disconnected, request.headers.get("last-event-id"))
    return StreamingResponse(stream, media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


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


@router.post("/map-plan/match")
def set_slot_match(payload: SlotMatchRequest, conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    """Put a match on one map of the order: fetch it, add it to the live series, and
    fill in the map's name from the match if the row has none yet."""
    plan = [dict(slot) for slot in payload.map_plan]
    if payload.index >= len(plan):
        raise HTTPException(status_code=400, detail="No such row in the map order.")
    series_id = _live_series_id(conn, get_state(conn))
    if series_id is None:
        raise HTTPException(status_code=400, detail="Create a series first.")
    match_id = (payload.match_id or "").strip() or None
    slot = plan[payload.index]
    if match_id:
        result = ingest_matches(conn, [match_id])[0]
        if result["status"] == "error":
            raise HTTPException(status_code=502, detail=f"Match {match_id}: {result.get('detail') or 'could not be fetched'}")
        add_matches_to_series(conn, series_id, [match_id])
        maybe_autoname_teams(conn, series_id)
        for other in plan:  # one match belongs to one map
            if other.get("match_id") == match_id:
                other["match_id"] = None
        match = load_match(conn, match_id)
        if not (slot.get("map") or "").strip() and match is not None:
            slot["map"] = map_display_name(match.map_name) or "Unknown map"
        if not slot.get("mode") and match is not None and match.game_mode:
            slot["mode"] = next((m for m in MODE_CHOICES if m.lower() == match.game_mode.lower()), None)
    slot["match_id"] = match_id
    set_map_plan(conn, plan)
    conn.commit()
    return snapshot(conn)
