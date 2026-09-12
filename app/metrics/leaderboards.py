"""Superlatives: who carried, who was steady, who had the one big game."""

from __future__ import annotations

from .base import (
    SeriesContext,
    fmt,
    mean,
    note_section,
    stats_section,
    stdev,
    table_section,
)
from .registry import register

MIN_MATCHES_FOR_CONSISTENCY = 2


@register
class Leaderboards:
    id = "leaderboards"
    name = "Leaderboards & Superlatives"
    description = "Top performers across the series, plus each match's standout player."
    order = 20

    def compute(self, ctx: SeriesContext) -> dict:
        by_player = ctx.stats_by_player()
        if not by_player:
            return {"sections": [note_section("No player data in this series yet.")]}

        aggregates = []
        for username, lines in by_player.items():
            damage = [s.damage for s in lines]
            scores = [s.match_score for s in lines]
            aggregates.append(
                {
                    "username": username,
                    "team": ctx.player_team(username),
                    "matches": len(lines),
                    "avg_damage": mean(damage),
                    "total_damage": sum(damage),
                    "best_damage": max(damage) if damage else 0.0,
                    "kills": sum(s.kills for s in lines),
                    "avg_score": mean(scores),
                    "damage_stdev": stdev(damage),
                }
            )

        # The number leads (it's what "highest"/"most" refers to); the player is a
        # secondary name+team-dot line, not crammed into the same bold slot — a long
        # username at headline size is what made this section look cluttered.
        def top(key: str, label: str, places: int = 1, show_sample: bool = False) -> dict:
            if not aggregates:
                return {"label": label, "value": "—"}
            best = max(aggregates, key=lambda a: a[key])
            hint = None
            # For averages, a leader with one drop is not comparable to one with five —
            # show the sample size so the number can be read honestly.
            if show_sample:
                hint = f"{best['matches']} match{'' if best['matches'] == 1 else 'es'}"
            return {
                "label": label,
                "value": fmt(best[key], places),
                "name": best["username"],
                "team": best["team"],
                "hint": hint,
            }

        steady_pool = [a for a in aggregates if a["matches"] >= MIN_MATCHES_FOR_CONSISTENCY]
        if steady_pool:
            steady = min(steady_pool, key=lambda a: a["damage_stdev"])
            steady_stat = {
                "label": "Most Consistent",
                "value": f"±{fmt(steady['damage_stdev'])}",
                "name": steady["username"],
                "team": steady["team"],
                "hint": "dmg swing",
            }
        else:
            steady_stat = {
                "label": "Most Consistent",
                "value": "—",
                "hint": "needs 2+ matches",
            }

        headline = stats_section(
            "Series leaders",
            [
                {
                    "label": "Standouts",
                    "stats": [
                        top("avg_damage", "Highest Avg Damage", show_sample=True),
                        top("total_damage", "Most Total Damage", 0),
                        top("kills", "Most Kills", 0),
                        top("avg_score", "Best Avg Match Score", show_sample=True),
                        top("best_damage", "Biggest Single Game", 0),
                        steady_stat,
                    ],
                }
            ],
        )

        ranked = sorted(aggregates, key=lambda a: -a["avg_damage"])
        # The Team column is redundant on a team's own page — every row is the same team.
        columns = ["#", "Player", "Matches", "Avg Dmg", "Total Dmg", "Kills", "Avg Score"]
        align = ["right", "left", "right", "right", "right", "right", "right"]
        if not ctx.is_scoped:
            columns.insert(2, "Team")
            align.insert(2, "left")

        board_rows = []
        for index, a in enumerate(ranked, start=1):
            row = [index, a["username"], a["matches"], fmt(a["avg_damage"]),
                   fmt(a["total_damage"], 0), a["kills"], fmt(a["avg_score"])]
            if not ctx.is_scoped:
                row.insert(2, ctx.team_name(a["team"]) if a["team"] else "—")
            board_rows.append(row)

        board = table_section("Player leaderboard", columns, board_rows, align=align)

        # Per-match MVP by match score, falling back to damage if scores are all zero.
        # `filtered_active_players` narrows this to one team on that team's own page,
        # so the "MVP" there is that team's own best performer, not the match winner.
        mvp_rows = []
        for match in ctx.matches:
            active = ctx.filtered_active_players(match)
            if not active:
                continue
            key = (lambda s: s.match_score) if any(s.match_score for s in active) else (lambda s: s.damage)
            mvp = max(active, key=key)
            row = [match.match_id, match.map_name or "—", mvp.username]
            if not ctx.is_scoped:
                team = ctx.team_for(match.match_id, mvp.username)
                row.append(ctx.team_name(team) if team else "—")
            row += [mvp.mech_name or "—", fmt(mvp.damage, 0), mvp.kills, fmt(mvp.match_score, 0)]
            mvp_rows.append(row)

        mvp_title = "Best Performer Per Match" if ctx.is_scoped else "Match MVPs"
        mvp_columns = ["Match", "Map", "Player", "Mech", "Dmg", "Kills", "Score"]
        mvp_align = ["left", "left", "left", "left", "right", "right", "right"]
        if not ctx.is_scoped:
            mvp_columns.insert(3, "Team")
            mvp_align.insert(3, "left")

        return {
            "sections": [
                headline,
                board,
                table_section(mvp_title, mvp_columns, mvp_rows, align=mvp_align),
            ]
        }
