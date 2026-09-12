"""Performance sliced by mech and by map/mode."""

from __future__ import annotations

from collections import defaultdict

from ..models import TEAM_A, TEAM_B
from .base import (
    SeriesContext,
    bar_section,
    fmt,
    mean,
    note_section,
    table_section,
)
from .registry import register


@register
class Breakdowns:
    id = "breakdowns"
    name = "Mech & Map Breakdown"
    description = "Damage and kills grouped by mech chassis, map and game mode."
    order = 40

    def compute(self, ctx: SeriesContext) -> dict:
        lines = ctx.lines()
        if not lines:
            return {"sections": [note_section("No player data in this series yet.")]}

        sections = []

        # ---- by mech variant
        by_mech: dict[str, list[tuple]] = defaultdict(list)
        for stat, team in lines:
            if stat.mech_name:
                by_mech[stat.mech_name].append((stat, team))

        if by_mech:

            def team_avg(entries: list[tuple], team: str) -> str:
                values = [s.damage for s, t in entries if t == team]
                return fmt(mean(values)) if values else "—"

            if ctx.is_scoped:
                columns = ["Mech", "Drops", "Avg Dmg", "Total Dmg", "Kills", "Piloted by"]
                align = ["left", "right", "right", "right", "right", "left"]
                note = ""
            else:
                columns = [
                    "Mech", "Drops", f"{ctx.team_name(TEAM_A)} Avg", f"{ctx.team_name(TEAM_B)} Avg",
                    "Total Dmg", "Kills", "Piloted by",
                ]
                align = ["left", "right", "right", "right", "right", "right", "left"]
                note = "Avg columns are blank where a team never piloted that variant."

            def build_mech_row(name: str, entries: list[tuple]) -> tuple[list, float]:
                total_dmg = sum(s.damage for s, _ in entries)
                row = [name, len(entries)]
                if ctx.is_scoped:
                    row.append(fmt(mean([s.damage for s, _ in entries])))
                else:
                    row += [team_avg(entries, TEAM_A), team_avg(entries, TEAM_B)]
                row += [
                    fmt(total_dmg, 0),
                    sum(s.kills for s, _ in entries),
                    ", ".join(sorted({s.username for s, _ in entries})[:3]),
                ]
                return row, total_dmg

            built = [build_mech_row(name, entries) for name, entries in by_mech.items()]
            mech_rows = [row for row, _ in sorted(built, key=lambda pair: -pair[1])]

            sections.append(
                table_section("By mech variant", columns, mech_rows, align=align, note=note)
            )

            # Chassis rollup only earns its place if it actually merges variants.
            by_chassis: dict[str, list[tuple]] = defaultdict(list)
            for stat, team in lines:
                if stat.mech_name:
                    by_chassis[stat.chassis].append((stat, team))
            if len(by_chassis) < len(by_mech):
                chassis_items = []
                for chassis in sorted(by_chassis):
                    for team in ctx.teams:
                        values = [s.damage for s, t in by_chassis[chassis] if t == team]
                        if values:
                            # On a team's own page every bar is that same team, so the
                            # label doesn't need to repeat it.
                            label = chassis if ctx.is_scoped else f"{chassis} · {ctx.team_name(team)}"
                            chassis_items.append({
                                "label": label,
                                "value": round(mean(values), 1),
                                "group": team,
                            })
                sections.append(
                    bar_section(
                        "Average damage by chassis",
                        chassis_items,
                        unit="dmg",
                        note="Chassis is derived from the variant prefix (e.g. TBR-PRIME → TBR).",
                    )
                )
        else:
            sections.append(note_section("The API returned no mech names for these matches."))

        # ---- by map / mode
        # Deliberately reads raw matches, not `ctx.lines()` — win/loss and the
        # opponent's damage must stay real even when this is one team's own page.
        def group_rows(attribute: str) -> list[list]:
            buckets: dict[str, dict[str, list]] = defaultdict(lambda: {TEAM_A: [], TEAM_B: []})
            wins: dict[str, dict[str, int]] = defaultdict(lambda: {TEAM_A: 0, TEAM_B: 0})
            for match in ctx.matches:
                key = getattr(match, attribute) or "—"
                for stat in match.active_players():
                    team = ctx.team_for(match.match_id, stat.username)
                    if team in buckets[key]:
                        buckets[key][team].append(stat)
                winner = ctx.match_winner(match)
                if winner in wins[key]:
                    wins[key][winner] += 1

            rows = []
            for key, team_stats in sorted(buckets.items()):
                matches_here = {s.match_id for stats in team_stats.values() for s in stats}
                if ctx.is_scoped:
                    team = ctx.teams[0]
                    other = TEAM_B if team == TEAM_A else TEAM_A
                    rows.append([
                        key, len(matches_here), fmt(mean([s.damage for s in team_stats[team]])),
                        f"{wins[key][team]}-{wins[key][other]}",
                    ])
                else:
                    rows.append([
                        key, len(matches_here),
                        fmt(mean([s.damage for s in team_stats[TEAM_A]])),
                        fmt(mean([s.damage for s in team_stats[TEAM_B]])),
                        f"{wins[key][TEAM_A]}-{wins[key][TEAM_B]}",
                    ])
            return rows

        for attribute, heading in (("map_name", "map"), ("game_mode", "game mode")):
            rows = group_rows(attribute)
            if not rows:
                continue
            if ctx.is_scoped:
                columns = [heading.title(), "Matches", "Avg Dmg", "Record (W-L)"]
                align = ["left", "right", "right", "right"]
            else:
                columns = [
                    heading.title(), "Matches",
                    f"{ctx.team_name(TEAM_A)} Avg Dmg", f"{ctx.team_name(TEAM_B)} Avg Dmg",
                    "Record (A-B)",
                ]
                align = ["left", "right", "right", "right", "right"]
            sections.append(table_section(f"By {heading}", columns, rows, align=align))

        return {"sections": sections}
