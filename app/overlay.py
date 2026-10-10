"""Broadcast overlay: one compact snapshot of a series for an OBS browser source,
plus the small bit of caster-controlled state (which series is live, who is in the
spotlight) that the overlay and the caster control page share.
"""

from __future__ import annotations

import dataclasses
import json
import re
import sqlite3
from collections import Counter
from typing import Any

from .db import get_app_setting, list_series, set_app_setting
from .metrics.base import SeriesContext, mean
from .metrics.comp_stats import combat_totals
from .models import TEAM_A, TEAM_B, Match
from .service import build_context

_STATE_KEY = "overlay_state"

# Overlay elements the caster switches on and off (the sidebars and spotlight
# have their own state below). Everything here starts on.
ELEMENTS = ("score", "last", "maps", "leaders")


def get_state(conn: sqlite3.Connection) -> dict[str, Any]:
    """{series_id, spotlight, team_names}; series_id None means "the newest series".

    team_names maps a series id (as a string, it round-trips through JSON) to
    overlay-only names for that series, e.g. {"3": {"A": "Emperors"}}. Keyed by
    series so following "the newest series" never carries last night's names over.
    """
    raw = get_app_setting(conn, _STATE_KEY)
    try:
        state = json.loads(raw) if raw else {}
    except ValueError:
        state = {}
    return {
        "series_id": state.get("series_id"),
        "spotlight": state.get("spotlight"),
        # The pilot most recently on the player card, so switching it back on brings them back.
        "last_spotlight": state.get("last_spotlight"),
        "team_names": state.get("team_names") or {},
        "elements": {name: bool((state.get("elements") or {}).get(name, True)) for name in ELEMENTS},
        "sidebars": bool(state.get("sidebars")),
        "intermission_page": state.get("intermission_page"),
        "map_plans": state.get("map_plans") or {},
    }


def set_state(conn: sqlite3.Connection, **changes: Any) -> dict[str, Any]:
    state = get_state(conn)
    if "series_id" in changes and changes["series_id"] != state["series_id"]:
        # A pilot from last night's series isn't on screen tonight.
        state["spotlight"] = state["last_spotlight"] = None
    state.update(changes)
    if state["spotlight"]:
        state["last_spotlight"] = state["spotlight"]
    set_app_setting(conn, _STATE_KEY, json.dumps(state))
    return state


def set_team_names(conn: sqlite3.Connection, names: dict[str, str | None]) -> None:
    """Overlay-only team names for the live series; a blank or null name clears it."""
    state = get_state(conn)
    series_id = _live_series_id(conn, state)
    if series_id is None:
        return
    current = dict(state["team_names"].get(str(series_id), {}))
    for team in (TEAM_A, TEAM_B):
        if team in names:
            name = (names[team] or "").strip()
            if name:
                current[team] = name
            else:
                current.pop(team, None)
    state["team_names"][str(series_id)] = current
    set_app_setting(conn, _STATE_KEY, json.dumps(state))


# The maps casters pick from. Free text is allowed too (new maps, night variants).
MAP_CHOICES = (
    "Alpine Peaks", "Canyon Network", "Caustic Valley", "Crimson Strait", "Emerald Taiga",
    "Forest Colony", "Frozen City", "Grim Plexus", "Hellebore Springs", "HPG Manifold",
    "Mining Collective", "Polar Highlands", "River City", "Rubellite Oasis", "Solaris City",
    "Terra Therma", "Tourmaline Desert", "Viridian Bog", "Vitric Forge",
)
MODE_CHOICES = ("Skirmish", "Domination", "Conquest", "Assault", "Incursion", "Escort")
MAX_PLANNED_MAPS = 20


def set_map_plan(conn: sqlite3.Connection, plan: list[dict[str, str | None]]) -> None:
    """The live series' map order: [{map, mode}], first drop first. Blank maps are dropped."""
    state = get_state(conn)
    series_id = _live_series_id(conn, state)
    if series_id is None:
        return
    cleaned = []
    for slot in plan[:MAX_PLANNED_MAPS]:
        name = str(slot.get("map") or "").strip()[:40]
        if name:
            cleaned.append({"map": name, "mode": str(slot.get("mode") or "").strip()[:20] or None})
    state["map_plans"][str(series_id)] = cleaned
    set_app_setting(conn, _STATE_KEY, json.dumps(state))


def _map_key(name: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _same_map(planned: str, played: str | None) -> bool:
    """The API names maps by code ("TerraThermaQP", "FrozenCityNight"), so a planned
    "Terra Therma" matches any variant that starts with it."""
    plan_key, played_key = _map_key(planned), _map_key(played)
    return bool(plan_key and played_key) and (played_key.startswith(plan_key) or plan_key.startswith(played_key))


def map_display_name(played: str | None) -> str | None:
    """A readable name for an API map name: "TerraThermaQP" -> "Terra Therma"."""
    for choice in MAP_CHOICES:
        if _same_map(choice, played):
            return choice
    return played or None


def _map_plan(ctx: SeriesContext, plan: list[dict]) -> list[dict[str, Any]]:
    """The planned maps with progress. Each match, oldest first, ticks off the first
    open slot for the map it was actually played on; a match on a map that isn't in
    the plan ticks off nothing. The first open slot is up next."""
    out = [{"number": index + 1, "map": slot["map"], "mode": slot.get("mode"), "status": "upcoming",
            "winner": None, "winner_name": None, "score": None, "match_number": None}
           for index, slot in enumerate(plan)]
    for number, match in enumerate(ctx.matches, start=1):
        entry = next((e for e in out if e["status"] == "upcoming" and _same_map(e["map"], match.map_name)), None)
        if entry is None:
            continue
        winner = ctx.match_winner(match)
        entry.update(status="done", winner=winner, winner_name=ctx.team_name(winner) if winner else None,
                     score=_team_score(ctx, match), match_number=number)
    upcoming = next((e for e in out if e["status"] == "upcoming"), None)
    if upcoming:
        upcoming["status"] = "next"
    return out


def _off_plan(ctx: SeriesContext, plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Matches that didn't tick off a planned map: [{number, map}]."""
    counted = {e["match_number"] for e in plan}
    return [{"number": n, "map": map_display_name(m.map_name) or "Unknown map"}
            for n, m in enumerate(ctx.matches, start=1) if n not in counted]


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
        lead("solo_kills", "KMDD", lambda v: str(v)),
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


def _sidebars(ctx: SeriesContext) -> dict[str, list[dict[str, Any]]]:
    """Each team's pilots with their series numbers, best average damage first."""
    by_player = ctx.stats_by_player()
    sides: dict[str, list[dict[str, Any]]] = {TEAM_A: [], TEAM_B: []}
    for username, lines in by_player.items():
        team = ctx.player_team(username)
        if team not in sides:
            continue
        combat = combat_totals(lines)
        sides[team].append({
            "username": username,
            "matches": len(lines),
            "avg_damage": round(mean([s.damage for s in lines])),
            "kills": sum(s.kills for s in lines),
            "survival_rate": combat["survival_rate"],
        })
    for pilots in sides.values():
        pilots.sort(key=lambda p: (-p["avg_damage"], p["username"].lower()))
    return sides


def live_context(conn: sqlite3.Connection):
    """(state, ctx, app_names, overrides) for the live series; ctx is None without one.

    The overlay-only team names are swapped into ctx so every team_name() call uses
    them, without touching the series itself (the stats pages keep the real names).
    """
    state = get_state(conn)
    series_id = _live_series_id(conn, state)
    ctx = build_context(conn, series_id) if series_id is not None else None
    if ctx is None:
        return state, None, {}, {}

    app_names = {TEAM_A: ctx.series.team_a_name, TEAM_B: ctx.series.team_b_name}
    overrides = state["team_names"].get(str(ctx.series.id), {})
    ctx.series = dataclasses.replace(
        ctx.series,
        team_a_name=overrides.get(TEAM_A) or app_names[TEAM_A],
        team_b_name=overrides.get(TEAM_B) or app_names[TEAM_B],
    )
    return state, ctx, app_names, overrides


def snapshot(conn: sqlite3.Connection) -> dict[str, Any]:
    """Everything the overlay draws, in one poll."""
    state, ctx, app_names, overrides = live_context(conn)
    if ctx is None:
        return {"state": state, "series": None}

    record = ctx.team_record()
    map_plan = _map_plan(ctx, state["map_plans"].get(str(ctx.series.id), []))
    return {
        "state": state,
        "series": {"id": ctx.series.id, "name": ctx.series.name},
        "teams": {
            team: {
                "name": ctx.team_name(team),
                "app_name": app_names[team],
                "overlay_name": overrides.get(team),
                "wins": record[team]["wins"],
            }
            for team in (TEAM_A, TEAM_B)
        },
        "matches_played": len(ctx.matches),
        "last_match": _last_match(ctx),
        "leaders": _leaders(ctx),
        "spotlight": _spotlight(ctx, state["spotlight"]),
        "sidebars": _sidebars(ctx),
        "map_plan": map_plan,
        "off_plan": _off_plan(ctx, map_plan) if map_plan else [],
        "map_choices": sorted(set(MAP_CHOICES) | {map_display_name(m.map_name) for m in ctx.matches if m.map_name}),
        "mode_choices": list(MODE_CHOICES),
        "rosters": {
            team: [a.username for a in ctx.inference.roster(team)] for team in (TEAM_A, TEAM_B)
        },
    }
