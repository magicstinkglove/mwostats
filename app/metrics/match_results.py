"""The full scoreboard for every match in the series — the raw box score behind
every aggregate and leaderboard elsewhere in the dashboard.
"""

from __future__ import annotations

from .base import SeriesContext, fmt, table_section
from .registry import register


@register
class MatchResults:
    id = "match_results"
    name = "Match Results"
    description = "Every match's full scoreboard, in chronological order."
    order = 10
    # A match is inherently both teams at once — there's no single-team version of
    # it worth splitting into per-team pages, so it lives only on its own tab.
    tabs = ("matches",)

    def compute(self, ctx: SeriesContext) -> dict:
        sections = []

        for index, match in enumerate(ctx.matches, start=1):
            # Sides swap between matches, so the score is only meaningful labelled
            # by team — never as a fixed "side 1 / side 2" pair.
            mapping = ctx.inference.match_side_team.get(match.match_id, {})
            winner = ctx.match_winner(match)

            summary = []
            if winner:
                if mapping.get(1) and mapping.get(2):
                    summary.append(
                        f"{ctx.team_name(mapping[1])} {match.side1_score} – "
                        f"{match.side2_score} {ctx.team_name(mapping[2])}"
                    )
                summary.append(f"{ctx.team_name(winner)} won")
            elif mapping.get(1) and mapping.get(2):
                summary.append(
                    f"{ctx.team_name(mapping[1])} {match.side1_score} – "
                    f"{match.side2_score} {ctx.team_name(mapping[2])} · draw"
                )
            if match.duration_minutes:
                summary.append(f"{match.duration_minutes:g} min")
            summary.append(f"Match ID {match.match_id}")

            rows = [
                [
                    player.username,
                    ctx.team_name(ctx.team_for(match.match_id, player.username))
                    if ctx.team_for(match.match_id, player.username)
                    else "—",
                    player.mech_name or "—",
                    player.kills,
                    player.assists,
                    fmt(player.damage, 0),
                    fmt(player.match_score, 0),
                ]
                for player in sorted(
                    match.active_players(),
                    key=lambda p: (
                        ctx.team_for(match.match_id, p.username) or "",
                        -p.damage,
                    ),
                )
            ]

            sections.append(
                table_section(
                    f"Match {index} — {match.map_name or 'Unknown map'} "
                    f"({match.game_mode or 'Unknown mode'})",
                    ["Player", "Team", "Mech", "Kills", "Assists", "Dmg", "Score"],
                    rows,
                    align=["left", "left", "left", "right", "right", "right", "right"],
                    note=" · ".join(summary),
                )
            )

        return {"sections": sections}
