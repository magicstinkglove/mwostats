"""Head-to-head team totals and averages."""

from __future__ import annotations

from ..models import TEAM_A, TEAM_B
from .base import (
    SeriesContext,
    bar_section,
    fmt,
    mean,
    ratio,
    stats_section,
    table_section,
)
from .registry import register


@register
class CoreAggregates:
    id = "core_aggregates"
    name = "Team Aggregates"
    description = "Totals, averages and win-loss record for each team across the series."
    order = 10

    def compute(self, ctx: SeriesContext) -> dict:
        by_team = ctx.stats_by_team()
        record = ctx.team_record()
        groups = []

        def opponent_kills(team: str) -> int:
            # Deliberately reads raw matches, not `by_team` — the latter is narrowed
            # to `team_filter` on a team's own page, and "kills scored against us"
            # must still reflect the real opponent regardless of which page this is.
            other = TEAM_B if team == TEAM_A else TEAM_A
            return sum(
                player.kills
                for match in ctx.matches
                for player in match.active_players()
                if ctx.team_for(match.match_id, player.username) == other
            )

        for team in ctx.teams:
            lines = by_team.get(team, [])
            damage = [s.damage for s in lines]
            kills = sum(s.kills for s in lines)
            deaths = opponent_kills(team)
            scores = [s.match_score for s in lines]
            roster = {s.username for s in lines}

            groups.append(
                {
                    "label": ctx.team_name(team),
                    "group": team,
                    "stats": [
                        {"label": "Record", "value": f"{record[team]['wins']}-{record[team]['losses']}"},
                        {"label": "Avg Damage", "value": fmt(mean(damage)), "hint": "per player per match"},
                        {"label": "Total Damage", "value": fmt(sum(damage), 0)},
                        {"label": "Kills", "value": str(kills)},
                        {"label": "K/D", "value": fmt(ratio(kills, deaths), 2)},
                        {"label": "Avg Match Score", "value": fmt(mean(scores))},
                        {"label": "Players Used", "value": str(len(roster))},
                    ],
                }
            )

        # Per-match damage, so a blowout doesn't hide inside a series average.
        columns = ["Match", "Map", "Mode", ctx.team_name(TEAM_A), ctx.team_name(TEAM_B), "Winner"]
        rows = []
        damage_items = []
        for match in ctx.matches:
            per_team = {TEAM_A: 0.0, TEAM_B: 0.0}
            for stat in match.active_players():
                team = ctx.team_for(match.match_id, stat.username)
                if team in per_team:
                    per_team[team] += stat.damage
            winner = ctx.match_winner(match)
            rows.append(
                [
                    match.match_id,
                    match.map_name or "—",
                    match.game_mode or "—",
                    fmt(per_team[TEAM_A], 0),
                    fmt(per_team[TEAM_B], 0),
                    ctx.team_name(winner) if winner else "—",
                ]
            )
            for team in ctx.teams:
                damage_items.append(
                    {
                        "label": f"{match.match_id[-6:]} · {ctx.team_name(team)}",
                        "value": round(per_team[team], 1),
                        "group": team,
                    }
                )

        return {
            "sections": [
                stats_section("Series totals", groups),
                table_section(
                    "Per-match team damage",
                    columns,
                    rows,
                    align=["left", "left", "left", "right", "right", "left"],
                ),
                bar_section("Team damage by match", damage_items, unit="dmg"),
            ]
        }
