"""Broadcast overlay: one compact snapshot of a series for an OBS browser source,
plus the small bit of caster-controlled state (which series is live, who is in the
spotlight) that the overlay and the caster control page share.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from typing import Any

from .db import get_app_setting, list_series, set_app_setting
from .metrics.base import SeriesContext, mean
from .metrics.comp_stats import combat_totals
from .models import TEAM_A, TEAM_B, Match
from .service import build_context

_STATE_KEY = "overlay_state"


def get_state(conn: sqlite3.Connection) -> dict[str, Any]:
    """{series_id, spotlight}; series_id None means "the newest series"."""
    raw = get_app_setting(conn, _STATE_KEY)
    try:
        state = json.loads(raw) if raw else {}
    except ValueError:
        state = {}
    return {"series_id": state.get("series_id"), "spotlight": state.get("spotlight")}


def set_state(conn: sqlite3.Connection, **changes: Any) -> dict[str, Any]:
    state = get_state(conn)
    if "series_id" in changes and changes["series_id"] != state["series_id"]:
        state["spotlight"] = None  # a pilot from last night's series isn't on screen tonight
    state.update(changes)
    set_app_setting(conn, _STATE_KEY, json.dumps(state))
    return state


def _live_series_id(conn: sqlite3.Connection, state: dict) -> int | None:
    if state["series_id"] is not None:
        return state["series_id"]
    newest = max(list_series(conn), key=lambda s: s.id, default=None)
    return newest.id if newest else None


def _team_score(ctx: SeriesContext, match: Match) -> dict[str, int]:
    scores = {}
    for side, score in ((1, match.side1_score), (2, match.side2_score)):
        team = ctx.inference.team_of(match.match_id, side)
        if team:
            scores[team] = score
    return scores


def _player_brief(ctx: SeriesContext, stat) -> dict[str, Any]:
    team = ctx.team_for(stat.match_id, stat.username)
    return {
        "username": stat.username,
        "team": team,
        "mech": stat.mech_name,
        "damage": round(stat.damage),
        "kills": stat.kills,
        "assists": stat.assists,
    }


def _last_match(ctx: SeriesContext) -> dict[str, Any] | None:
    if not ctx.matches:
        return None
    match = ctx.matches[-1]
    active = match.active_players()
    mvp = None
    if active:
        key = (lambda s: s.match_score) if any(s.match_score for s in active) else (lambda s: s.damage)
        mvp = _player_brief(ctx, max(active, key=key))
    winner = ctx.match_winner(match)
    return {
        "number": len(ctx.matches),
        "match_id": match.match_id,
        "map": match.map_name,
        "mode": match.game_mode,
        "winner": winner,
        "winner_name": ctx.team_name(winner) if winner else None,
        "score": _team_score(ctx, match),
        "mvp": mvp,
    }


def _leaders(ctx: SeriesContext) -> list[dict[str, Any]]:
    by_player = ctx.stats_by_player()
    if not by_player:
        return []
    rows = []
    for username, lines in by_player.items():
        combat = combat_totals(lines)
        rows.append({
            "username": username,
            "team": ctx.player_team(username),
            "avg_damage": mean([s.damage for s in lines]),
            "kills": sum(s.kills for s in lines),
            "solo_kills": combat["solo_kills"],
            "survival_rate": combat["survival_rate"] if combat["reported"] >= 2 else None,
        })

    def lead(key: str, label: str, render) -> dict | None:
        pool = [r for r in rows if r[key]]
        if not pool:
            return None
        best = max(pool, key=lambda r: r[key])
        return {"label": label, "value": render(best[key]),
                "username": best["username"], "team": best["team"]}

    picks = [
        lead("avg_damage", "Avg Damage", lambda v: f"{v:,.0f}"),
        lead("kills", "Kills", lambda v: str(v)),
        lead("solo_kills", "Solo Kills", lambda v: str(v)),
        lead("survival_rate", "Survival", lambda v: f"{v * 100:.0f}%"),
    ]
    return [p for p in picks if p]


def _spotlight(ctx: SeriesContext, username: str | None) -> dict[str, Any] | None:
    if not username:
        return None
    lines = ctx.stats_by_player().get(username)
    if not lines:
        return None
    team = ctx.player_team(username)
    combat = combat_totals(lines)
    mechs = Counter(s.mech_name for s in lines if s.mech_name)
    return {
        "username": username,
        "team": team,
        "team_name": ctx.team_name(team) if team else None,
        "matches": len(lines),
        "avg_damage": round(mean([s.damage for s in lines])),
        "kills": sum(s.kills for s in lines),
        "assists": sum(s.assists for s in lines),
        "solo_kills": combat["solo_kills"],
        "survival_rate": combat["survival_rate"],
        "top_mech": mechs.most_common(1)[0][0] if mechs else None,
        "last": _player_brief(ctx, lines[-1]),
    }


def snapshot(conn: sqlite3.Connection) -> dict[str, Any]:
    """Everything the overlay draws, in one poll."""
    state = get_state(conn)
    series_id = _live_series_id(conn, state)
    ctx = build_context(conn, series_id) if series_id is not None else None
    if ctx is None:
        return {"state": state, "series": None}

    record = ctx.team_record()
    return {
        "state": state,
        "series": {"id": ctx.series.id, "name": ctx.series.name},
        "teams": {
            team: {"name": ctx.team_name(team), "wins": record[team]["wins"]}
            for team in (TEAM_A, TEAM_B)
        },
        "matches_played": len(ctx.matches),
        "last_match": _last_match(ctx),
        "leaders": _leaders(ctx),
        "spotlight": _spotlight(ctx, state["spotlight"]),
        "rosters": {
            team: [a.username for a in ctx.inference.roster(team)] for team in (TEAM_A, TEAM_B)
        },
    }
