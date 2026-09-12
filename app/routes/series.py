"""Series management: grouping matches and correcting team assignment."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import (
    add_matches_to_series,
    clear_override,
    create_series,
    delete_series,
    get_series,
    list_series,
    remove_match_from_series,
    rename_teams,
    set_match_override,
    set_override,
)
from ..models import DEFAULT_TEAM_A_NAME, DEFAULT_TEAM_B_NAME, TEAM_A, TEAM_B
from ..service import (
    ingest_matches,
    maybe_autoname_teams,
    parse_match_ids,
    resolve_series,
    serialize_assignment,
    serialize_match,
)
from .deps import get_conn

router = APIRouter(prefix="/api/series", tags=["series"])


class CreateSeriesRequest(BaseModel):
    name: str = Field(default="New Series")
    match_ids: str | list[str] = ""
    ingest: bool = True


class AddMatchesRequest(BaseModel):
    match_ids: str | list[str]
    ingest: bool = True
    force_refresh: bool = False


class TeamNamesRequest(BaseModel):
    team_a_name: str
    team_b_name: str


class OverrideRequest(BaseModel):
    username: str
    team: str | None = Field(default=None, description="'A', 'B', or null to clear")
    match_id: str | None = Field(default=None, description="Set for a single-match override")


def _series_payload(conn: sqlite3.Connection, series_id: int) -> dict:
    resolved = resolve_series(conn, series_id)
    if resolved is None:
        raise HTTPException(status_code=404, detail=f"Series {series_id} not found.")
    series, matches, inference, match_overrides = resolved

    return {
        "id": series.id,
        "name": series.name,
        "team_a_name": series.team_a_name,
        "team_b_name": series.team_b_name,
        "match_ids": series.match_ids,
        "matches": [serialize_match(m, inference) for m in matches],
        "rosters": {
            TEAM_A: [serialize_assignment(a) for a in inference.roster(TEAM_A)],
            TEAM_B: [serialize_assignment(a) for a in inference.roster(TEAM_B)],
        },
        "needs_review": [
            serialize_assignment(a) for a in inference.assignments.values() if a.needs_review
        ],
        "warnings": inference.warnings,
        "match_overrides": [
            {"match_id": mid, "username": user, "team": team}
            for (mid, user), team in match_overrides.items()
        ],
    }


@router.post("")
def new_series(payload: CreateSeriesRequest, conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    ids = parse_match_ids(payload.match_ids)
    ingest_results = ingest_matches(conn, ids) if (ids and payload.ingest) else []
    stored = [r["match_id"] for r in ingest_results if r["status"] != "error"] if ingest_results else ids

    series_id = create_series(conn, payload.name, stored)
    maybe_autoname_teams(conn, series_id)
    conn.commit()
    return {"series": _series_payload(conn, series_id), "ingest": ingest_results}


@router.get("")
def all_series(conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return {
        "series": [
            {
                "id": s.id,
                "name": s.name,
                "match_count": len(s.match_ids),
                "team_a_name": s.team_a_name,
                "team_b_name": s.team_b_name,
                "created_at": s.created_at,
            }
            for s in list_series(conn)
        ]
    }


@router.get("/{series_id}")
def one_series(series_id: int, conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return _series_payload(conn, series_id)


@router.delete("/{series_id}")
def drop_series(series_id: int, conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    delete_series(conn, series_id)
    conn.commit()
    return {"deleted": series_id}


@router.post("/{series_id}/matches")
def add_matches(
    series_id: int, payload: AddMatchesRequest, conn: sqlite3.Connection = Depends(get_conn)
) -> dict:
    if get_series(conn, series_id) is None:
        raise HTTPException(status_code=404, detail=f"Series {series_id} not found.")

    ids = parse_match_ids(payload.match_ids)
    if not ids:
        raise HTTPException(status_code=400, detail="No match IDs provided.")

    ingest_results = (
        ingest_matches(conn, ids, force_refresh=payload.force_refresh) if payload.ingest else []
    )
    stored = [r["match_id"] for r in ingest_results if r["status"] != "error"] if ingest_results else ids
    add_matches_to_series(conn, series_id, stored)
    maybe_autoname_teams(conn, series_id)
    conn.commit()
    return {"series": _series_payload(conn, series_id), "ingest": ingest_results}


@router.delete("/{series_id}/matches/{match_id}")
def drop_match(series_id: int, match_id: str, conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    remove_match_from_series(conn, series_id, match_id)
    conn.commit()
    return {"series": _series_payload(conn, series_id)}


@router.put("/{series_id}/teams")
def update_team_names(
    series_id: int, payload: TeamNamesRequest, conn: sqlite3.Connection = Depends(get_conn)
) -> dict:
    if get_series(conn, series_id) is None:
        raise HTTPException(status_code=404, detail=f"Series {series_id} not found.")
    rename_teams(conn, series_id, payload.team_a_name.strip() or DEFAULT_TEAM_A_NAME,
                 payload.team_b_name.strip() or DEFAULT_TEAM_B_NAME)
    conn.commit()
    return {"series": _series_payload(conn, series_id)}


@router.put("/{series_id}/assignments")
def update_assignment(
    series_id: int, payload: OverrideRequest, conn: sqlite3.Connection = Depends(get_conn)
) -> dict:
    if get_series(conn, series_id) is None:
        raise HTTPException(status_code=404, detail=f"Series {series_id} not found.")

    if payload.team is not None and payload.team not in (TEAM_A, TEAM_B):
        raise HTTPException(status_code=400, detail="team must be 'A', 'B', or null.")

    if payload.match_id:
        if payload.team is None:
            conn.execute(
                "DELETE FROM match_player_override WHERE series_id=? AND match_id=? AND username=?",
                (series_id, payload.match_id, payload.username),
            )
        else:
            set_match_override(conn, series_id, payload.match_id, payload.username, payload.team)
    elif payload.team is None:
        clear_override(conn, series_id, payload.username)
    else:
        set_override(conn, series_id, payload.username, payload.team, pinned=True)

    maybe_autoname_teams(conn, series_id)
    conn.commit()
    return {"series": _series_payload(conn, series_id)}
