"""Metric module discovery and computation."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from ..metrics import descriptors, get_module
from ..metrics.base import mean
from ..models import TEAM_A, TEAM_B
from ..service import build_context
from .deps import get_conn

router = APIRouter(prefix="/api", tags=["metrics"])


@router.get("/metrics/modules")
def modules() -> dict:
    """Everything the frontend needs to render one card per registered module."""
    return {"modules": descriptors()}


@router.get("/series/{series_id}/metrics/{module_id}")
def compute_one(
    series_id: int,
    module_id: str,
    team: str | None = Query(default=None, description="'A' or 'B' for a team's own page"),
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict:
    module = get_module(module_id)
    if module is None:
        raise HTTPException(status_code=404, detail=f"No metric module '{module_id}'.")

    if team is not None and team not in (TEAM_A, TEAM_B):
        raise HTTPException(status_code=400, detail="team must be 'A' or 'B'.")
    if team is not None and "team" not in getattr(module, "tabs", ("summary", "team")):
        raise HTTPException(
            status_code=400, detail=f"Module '{module_id}' has no team-scoped view."
        )

    ctx = build_context(conn, series_id, team_filter=team)
    if ctx is None:
        raise HTTPException(status_code=404, detail=f"Series {series_id} not found.")

    if not ctx.matches:
        return {
            "module": {"id": module.id, "name": module.name},
            "sections": [{"type": "note", "text": "Add some matches to this series first."}],
        }

    try:
        payload = module.compute(ctx)
    except Exception as exc:  # noqa: BLE001 - one broken module must not kill the dashboard
        return {
            "module": {"id": module.id, "name": module.name},
            "sections": [
                {
                    "type": "note",
                    "text": f"This module failed: {type(exc).__name__}: {exc}",
                }
            ],
            "error": True,
        }

    return {
        "module": {"id": module.id, "name": module.name, "description": module.description},
        **payload,
    }


@router.get("/series/{series_id}/players/{username}")
def player_detail(
    series_id: int, username: str, conn: sqlite3.Connection = Depends(get_conn)
) -> dict:
    ctx = build_context(conn, series_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail=f"Series {series_id} not found.")

    stats = ctx.stats_by_player().get(username)
    if not stats:
        raise HTTPException(status_code=404, detail=f"{username} did not play in this series.")

    team = ctx.player_team(username)
    assignment = ctx.inference.assignments.get(username)
    by_match = {m.match_id: m for m in ctx.matches}

    return {
        "username": username,
        "team": team,
        "team_name": ctx.team_name(team) if team else None,
        "assignment": {
            "confidence": assignment.confidence if assignment else 0.0,
            "source": assignment.source if assignment else "inferred",
            "contested": assignment.contested if assignment else False,
            "needs_review": assignment.needs_review if assignment else False,
        },
        "totals": {
            "matches": len(stats),
            "avg_damage": round(mean([s.damage for s in stats]), 1),
            "total_damage": round(sum(s.damage for s in stats), 1),
            "kills": sum(s.kills for s in stats),
            "assists": sum(s.assists for s in stats),
            "avg_match_score": round(mean([s.match_score for s in stats]), 1),
        },
        "matches": [
            {
                "match_id": s.match_id,
                "map": by_match[s.match_id].map_name if s.match_id in by_match else "",
                "side": s.side,
                "team": ctx.team_for(s.match_id, username),
                "mech": s.mech_name,
                "kills": s.kills,
                "assists": s.assists,
                "damage": s.damage,
                "match_score": s.match_score,
            }
            for s in stats
        ],
    }
