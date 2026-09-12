"""Per-player view: how each pilot tracked across the series and against their team."""

from __future__ import annotations

from .base import (
    SeriesContext,
    fmt,
    line_section,
    mean,
    note_section,
    table_section,
)
from .registry import register

# A line chart's color slots are a limited, order-fixed resource (see the dataviz
# color rules) — 8 is the cap that stays pairwise-distinguishable. A team fielding
# more than that across a series shows its 8 most-frequent players; the rest are
# still fully covered by the summary table above the chart.
MAX_LINES_PER_CHART = 8


@register
class PlayerDetail:
    id = "player_detail"
    name = "Player Breakdown"
    description = "Every pilot's per-match record, their trend, and how they compare to their team."
    order = 30

    def compute(self, ctx: SeriesContext) -> dict:
        by_player = ctx.stats_by_player()
        if not by_player:
            return {"sections": [note_section("No player data in this series yet.")]}

        team_avg = {
            team: mean([s.damage for s in lines])
            for team, lines in ctx.stats_by_team().items()
        }

        # The Team column is redundant on a team's own page — every row is the same team.
        columns = ["Player", "Matches", "Avg Dmg", "vs Team Avg", "Kills", "Avg Score", "Mechs", ""]
        align = ["left", "right", "right", "right", "right", "right", "left", "left"]
        if not ctx.is_scoped:
            columns.insert(1, "Team")
            align.insert(1, "left")

        rows = []
        for username, lines in sorted(by_player.items(), key=lambda kv: kv[0].lower()):
            team = ctx.player_team(username)
            avg_damage = mean([s.damage for s in lines])
            baseline = team_avg.get(team, 0.0)
            delta = avg_damage - baseline
            mechs = sorted({s.mech_name for s in lines if s.mech_name})
            assignment = ctx.inference.assignments.get(username)
            row = [
                username,
                len(lines),
                fmt(avg_damage),
                f"{'+' if delta >= 0 else ''}{fmt(delta)}",
                sum(s.kills for s in lines),
                fmt(mean([s.match_score for s in lines])),
                ", ".join(mechs[:3]) + ("…" if len(mechs) > 3 else "") or "—",
                "review" if assignment and assignment.needs_review else "",
            ]
            if not ctx.is_scoped:
                row.insert(1, ctx.team_name(team) if team else "—")
            rows.append(row)

        sections = [
            table_section(
                "Per-player summary",
                columns,
                rows,
                align=align,
                note="'vs Team Avg' compares each pilot to their own team's average damage.",
            )
        ]

        # Damage trend per player across the series, one chart per team so every
        # player gets a distinct, legible color instead of two teams sharing one
        # color each. A line's color slot is fixed by its position in this list, so
        # the order must be stable across recomputes — alphabetical by username,
        # never by a value like average damage that could reshuffle on new data.
        if len(ctx.matches) > 1:
            x_labels = [m.match_id[-6:] for m in ctx.matches]
            for team in ctx.teams:
                roster = sorted(
                    (u for u in by_player if ctx.player_team(u) == team), key=str.lower
                )
                if not roster:
                    continue

                shown, overflow = roster, 0
                if len(roster) > MAX_LINES_PER_CHART:
                    shown = sorted(
                        roster, key=lambda u: -len(by_player[u])
                    )[:MAX_LINES_PER_CHART]
                    shown.sort(key=str.lower)
                    overflow = len(roster) - len(shown)

                lines_out = []
                for username in shown:
                    per_match = {s.match_id: s.damage for s in by_player[username]}
                    lines_out.append(
                        {"label": username, "points": [per_match.get(m.match_id) for m in ctx.matches]}
                    )

                note = "Gaps mean the pilot did not play that match."
                if overflow:
                    note += (
                        f" Showing the {MAX_LINES_PER_CHART} pilots with the most matches; "
                        f"{overflow} more are in the summary table above."
                    )

                sections.append(
                    line_section(f"{ctx.team_name(team)} — Damage Trend", x_labels, lines_out, note=note)
                )

        return {"sections": sections}
