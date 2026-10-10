"""Full-screen between-games scene: the whole series analysed, for an OBS scene
that runs while teams drop into the next lobby. One payload, several pages
(recap, head to head, players, awards); the scene rotates through them.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from typing import Any

from .metrics.base import SeriesContext, mean, stdev
from .metrics.comp_stats import combat_line, combat_totals
from .models import TEAM_A, TEAM_B, Match
from .overlay import _last_match, _map_plan, _team_score, live_context

PAGES = ("recap", "teams", "players", "awards")
MIN_MATCHES_FOR_RATES = 2


def _box_score(ctx: SeriesContext, match: Match) -> dict[str, list[dict[str, Any]]]:
    sides: dict[str, list[dict[str, Any]]] = {TEAM_A: [], TEAM_B: []}
    for stat in match.active_players():
        team = ctx.team_for(match.match_id, stat.username)
        if team not in sides:
            continue
        combat = combat_line(stat)
        sides[team].append({
            "username": stat.username,
            "mech": stat.mech_name,
            "damage": round(stat.damage),
            "kills": stat.kills,
            "assists": stat.assists,
            "solo_kills": combat["solo_kills"],
            "survived": None if combat["survived"] is None else bool(combat["survived"]),
            "health": combat["health"],
        })
    for rows in sides.values():
        rows.sort(key=lambda r: -r["damage"])
    return sides


def _team_comparison(ctx: SeriesContext) -> list[dict[str, Any]]:
    """One row per stat, both teams' values side by side, for mirrored bars."""
    by_team = ctx.stats_by_team()
    totals = {}
    for team in (TEAM_A, TEAM_B):
        lines = by_team.get(team, [])
        combat = combat_totals(lines)
        totals[team] = {
            "avg_damage": mean([s.damage for s in lines]) if lines else None,
            "kills": sum(s.kills for s in lines),
            "assists": sum(s.assists for s in lines),
            "avg_score": mean([s.match_score for s in lines]) if lines else None,
            "survival_rate": combat["survival_rate"],
            "solo_kills": combat["solo_kills"],
            "components": combat["components"],
            "team_damage": combat["team_damage"],
        }

    rows = [
        ("avg_damage", "Avg damage per pilot", "{:,.0f}", False),
        ("kills", "Kills", "{:,.0f}", False),
        ("assists", "Assists", "{:,.0f}", False),
        ("survival_rate", "Survival rate", "pct", False),
        ("solo_kills", "KMDD", "{:,.0f}", False),
        ("components", "Components destroyed", "{:,.0f}", False),
        ("avg_score", "Avg match score", "{:,.0f}", False),
        ("team_damage", "Friendly fire", "{:,.0f}", True),
    ]
    out = []
    for key, label, pattern, lower_is_better in rows:
        a, b = totals[TEAM_A][key], totals[TEAM_B][key]
        if a is None and b is None:
            continue

        def render(v):
            if v is None:
                return "—"
            return f"{v * 100:.0f}%" if pattern == "pct" else pattern.format(v)

        out.append({
            "label": label,
            "A": a, "B": b,
            "A_text": render(a), "B_text": render(b),
            "lower_is_better": lower_is_better,
        })
    return out


def _players(ctx: SeriesContext) -> dict[str, list[dict[str, Any]]]:
    sides: dict[str, list[dict[str, Any]]] = {TEAM_A: [], TEAM_B: []}
    for username, lines in ctx.stats_by_player().items():
        team = ctx.player_team(username)
        if team not in sides:
            continue
        combat = combat_totals(lines)
        mechs = Counter(s.mech_name for s in lines if s.mech_name)
        sides[team].append({
            "username": username,
            "matches": len(lines),
            "avg_damage": round(mean([s.damage for s in lines])),
            "total_damage": round(sum(s.damage for s in lines)),
            "best_damage": round(max(s.damage for s in lines)),
            "kills": sum(s.kills for s in lines),
            "assists": sum(s.assists for s in lines),
            "avg_score": round(mean([s.match_score for s in lines])),
            "solo_kills": combat["solo_kills"],
            "survival_rate": combat["survival_rate"],
            "components": combat["components"],
            "team_damage": combat["team_damage"],
            "mechs": [m for m, _ in mechs.most_common(2)],
        })
    for rows in sides.values():
        rows.sort(key=lambda r: (-r["avg_damage"], r["username"].lower()))
    return sides


def _awards(ctx: SeriesContext, players: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    everyone = [dict(p, team=team) for team, rows in players.items() for p in rows]
    if not everyone:
        return []
    veterans = [p for p in everyone if p["matches"] >= MIN_MATCHES_FOR_RATES]
    awards: list[dict[str, Any]] = []

    def award(title: str, pool: list[dict], key, value, detail, lowest: bool = False) -> None:
        pool = [p for p in pool if key(p) is not None]
        if not pool:
            return
        pick = (min if lowest else max)(pool, key=key)
        if not lowest and not key(pick):
            return
        awards.append({"title": title, "username": pick["username"], "team": pick["team"],
                       "value": value(pick), "detail": detail(pick)})

    award("Damage Dealer", everyone, lambda p: p["avg_damage"],
          lambda p: f"{p['avg_damage']:,}", lambda p: f"avg damage over {p['matches']} drops")
    award("Executioner", everyone, lambda p: p["kills"],
          lambda p: str(p["kills"]), lambda p: "kills in the series")
    award("KMDD King", everyone, lambda p: p["solo_kills"],
          lambda p: str(p["solo_kills"]), lambda p: "kills where they did the most damage")
    award("Last Mech Standing", veterans, lambda p: p["survival_rate"],
          lambda p: f"{p['survival_rate'] * 100:.0f}%", lambda p: "of drops survived")
    award("Component Shredder", everyone, lambda p: p["components"],
          lambda p: str(p["components"]), lambda p: "components destroyed")
    award("Team Player", everyone, lambda p: p["assists"],
          lambda p: str(p["assists"]), lambda p: "assists")

    # Biggest single game and steadiest pilot need the per-match lines.
    by_player = ctx.stats_by_player()
    best = max(((s, u) for u, lines in by_player.items() for s in lines), key=lambda x: x[0].damage, default=None)
    if best and best[0].damage:
        stat, username = best
        match = next((m for m in ctx.matches if m.match_id == stat.match_id), None)
        awards.append({"title": "Biggest Game", "username": username,
                       "team": ctx.team_for(stat.match_id, username),
                       "value": f"{stat.damage:,.0f}",
                       "detail": f"damage in {stat.mech_name or 'one drop'}"
                                 + (f" on {match.map_name}" if match and match.map_name else "")})
    steady = [(stdev([s.damage for s in lines]), u) for u, lines in by_player.items()
              if len(lines) >= MIN_MATCHES_FOR_RATES]
    if steady:
        swing, username = min(steady)
        awards.append({"title": "Steady Hands", "username": username, "team": ctx.player_team(username),
                       "value": f"±{swing:,.0f}", "detail": "smallest damage swing match to match"})

    award("Friendly Fire Award", everyone, lambda p: p["team_damage"],
          lambda p: f"{p['team_damage']:,.0f}", lambda p: "damage to their own team")
    return awards


def _history(ctx: SeriesContext) -> list[dict[str, Any]]:
    out = []
    for number, match in enumerate(ctx.matches, start=1):
        active = match.active_players()
        mvp = None
        if active:
            key = (lambda s: s.match_score) if any(s.match_score for s in active) else (lambda s: s.damage)
            mvp = max(active, key=key).username
        winner = ctx.match_winner(match)
        out.append({"number": number, "map": match.map_name, "mode": match.game_mode,
                    "winner": winner, "score": _team_score(ctx, match), "mvp": mvp})
    return out


def intermission(conn: sqlite3.Connection) -> dict[str, Any]:
    state, ctx, _, _ = live_context(conn)
    if ctx is None:
        return {"state": state, "series": None, "pages": list(PAGES)}

    record = ctx.team_record()
    players = _players(ctx)
    last = _last_match(ctx)
    if last:
        last["box_score"] = _box_score(ctx, ctx.matches[-1])
    return {
        "state": state,
        "pages": list(PAGES),
        "series": {"id": ctx.series.id, "name": ctx.series.name},
        "teams": {t: {"name": ctx.team_name(t), "wins": record[t]["wins"]} for t in (TEAM_A, TEAM_B)},
        "matches_played": len(ctx.matches),
        "last_match": last,
        "comparison": _team_comparison(ctx),
        "history": _history(ctx),
        "map_plan": _map_plan(ctx, state["map_plans"].get(str(ctx.series.id), [])),
        "players": players,
        "awards": _awards(ctx, players),
    }
