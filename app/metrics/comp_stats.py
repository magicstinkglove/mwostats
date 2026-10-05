"""Combat detail from API fields the core stats ignore: survival, solo kills,
components destroyed, friendly fire and lance.

MWO's API documents these per-player fields (HealthPercentage, KillsMostDamage,
ComponentsDestroyed, TeamDamage, Lance); `normalize` keeps them in `extra`. Every
read is defensive: a field that never appears just drops its column or stat.
"""

from __future__ import annotations

from .base import (
    SeriesContext,
    extra_num,
    fmt,
    mean,
    note_section,
    stats_section,
    table_section,
)
from ..models import PlayerStat
from .registry import register

HEALTH = ("HealthPercentage", "Health")
SOLO_KILLS = ("KillsMostDamage",)
COMPONENTS = ("ComponentsDestroyed",)
TEAM_DAMAGE = ("TeamDamage",)
LANCE = ("Lance",)

MIN_MATCHES_FOR_SURVIVAL = 2


def combat_line(stat: PlayerStat) -> dict[str, float | None]:
    """One player line's combat-detail fields, None where the API didn't report them."""
    health = extra_num(stat, *HEALTH)
    return {
        "health": health,
        "survived": None if health is None else (1.0 if health > 0 else 0.0),
        "solo_kills": extra_num(stat, *SOLO_KILLS),
        "components": extra_num(stat, *COMPONENTS),
        "team_damage": extra_num(stat, *TEAM_DAMAGE),
    }


def combat_totals(lines: list[PlayerStat]) -> dict[str, float | int | None]:
    """Aggregate `combat_line` over many lines; each stat is None if never reported."""
    rows = [combat_line(s) for s in lines]

    def present(key: str) -> list[float]:
        return [r[key] for r in rows if r[key] is not None]

    health = present("health")
    survived = present("survived")
    solo, comps, ff = present("solo_kills"), present("components"), present("team_damage")
    return {
        "matches": len(lines),
        "reported": len(health),
        "survived": int(sum(survived)) if survived else None,
        "survival_rate": mean(survived) if survived else None,
        "avg_health": mean(health) if health else None,
        "solo_kills": int(sum(solo)) if solo else None,
        "components": int(sum(comps)) if comps else None,
        "team_damage": sum(ff) if ff else None,
    }


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.0f}%"


def _num(value: float | int | None, places: int = 0) -> str:
    return "—" if value is None else fmt(value, places)


@register
class CompStats:
    id = "comp_stats"
    name = "Combat Detail"
    description = "Survival, solo kills, components destroyed, friendly fire and lance splits."
    order = 25

    def compute(self, ctx: SeriesContext) -> dict:
        by_player = ctx.stats_by_player()
        if not by_player:
            return {"sections": [note_section("No player data in this series yet.")]}

        players = [
            {"username": u, "team": ctx.player_team(u), **combat_totals(lines)}
            for u, lines in by_player.items()
        ]
        reported = {
            key: any(p[key] is not None for p in players)
            for key in ("survival_rate", "solo_kills", "components", "team_damage")
        }
        if not any(reported.values()):
            return {"sections": [note_section(
                "These matches don't include survival, solo-kill, component or friendly-fire "
                "fields, so there's nothing extra to show."
            )]}

        sections = [self._team_summary(ctx, reported), self._superlatives(players, reported)]
        sections.append(self._player_table(ctx, players, reported))
        lance = self._lance_table(ctx)
        if lance:
            sections.append(lance)
        return {"sections": sections}

    # ------------------------------------------------------------------ sections

    def _team_summary(self, ctx: SeriesContext, reported: dict) -> dict:
        groups = []
        for team, lines in ctx.stats_by_team().items():
            t = combat_totals(lines)
            stats = []
            if reported["survival_rate"]:
                stats.append({"label": "Survival Rate", "value": _pct(t["survival_rate"]),
                              "hint": f"{t['survived'] or 0} of {t['reported']} drops"})
                stats.append({"label": "Avg Health Left", "value": _pct(
                    None if t["avg_health"] is None else t["avg_health"] / 100)})
            if reported["solo_kills"]:
                stats.append({"label": "Solo Kills", "value": _num(t["solo_kills"])})
            if reported["components"]:
                stats.append({"label": "Components Destroyed", "value": _num(t["components"])})
            if reported["team_damage"]:
                stats.append({"label": "Friendly Fire", "value": _num(t["team_damage"])})
            groups.append({"label": ctx.team_name(team), "group": team, "stats": stats})
        return stats_section("Combat detail", groups)

    def _superlatives(self, players: list[dict], reported: dict) -> dict:
        def leader(key: str, label: str, value, hint=None, pool=None, lowest=False) -> dict:
            pool = [p for p in (pool or players) if p[key] is not None]
            if not pool:
                return {"label": label, "value": "—", "hint": hint}
            pick = (min if lowest else max)(pool, key=lambda p: p[key])
            if not lowest and not pick[key]:
                return {"label": label, "value": "—", "hint": "nobody yet"}
            return {"label": label, "value": value(pick), "name": pick["username"],
                    "team": pick["team"], "hint": hint(pick) if callable(hint) else hint}

        stats = []
        if reported["survival_rate"]:
            veterans = [p for p in players if p["reported"] >= MIN_MATCHES_FOR_SURVIVAL]
            stats.append(leader(
                "survival_rate", "Last Mech Standing", lambda p: _pct(p["survival_rate"]),
                hint=lambda p: f"survived {p['survived']} of {p['reported']}", pool=veterans,
            ) if veterans else {"label": "Last Mech Standing", "value": "—", "hint": "needs 2+ matches"})
        if reported["solo_kills"]:
            stats.append(leader("solo_kills", "Solo Kill King", lambda p: _num(p["solo_kills"]),
                                hint="kills with most damage"))
        if reported["components"]:
            stats.append(leader("components", "Component Shredder", lambda p: _num(p["components"]),
                                hint="components destroyed"))
        if reported["team_damage"]:
            stats.append(leader("team_damage", "Friendly Fire Award", lambda p: _num(p["team_damage"]),
                                hint="damage to own team"))
        return stats_section("Combat awards", [{"label": "Awards", "stats": stats}])

    def _player_table(self, ctx: SeriesContext, players: list[dict], reported: dict) -> dict:
        columns, align = ["Player"], ["left"]
        if not ctx.is_scoped:
            columns.append("Team"); align.append("left")
        columns.append("Matches"); align.append("right")
        cols = []
        if reported["survival_rate"]:
            cols += [("Survived", lambda p: f"{p['survived'] or 0}/{p['reported']}"),
                     ("Avg HP", lambda p: _pct(None if p["avg_health"] is None else p["avg_health"] / 100))]
        if reported["solo_kills"]:
            cols.append(("Solo Kills", lambda p: _num(p["solo_kills"])))
        if reported["components"]:
            cols.append(("Comps", lambda p: _num(p["components"])))
        if reported["team_damage"]:
            cols.append(("Team Dmg", lambda p: _num(p["team_damage"])))
        columns += [c[0] for c in cols]
        align += ["right"] * len(cols)

        rows = []
        for p in sorted(players, key=lambda p: (-(p["solo_kills"] or 0), p["username"].lower())):
            row = [p["username"]]
            if not ctx.is_scoped:
                row.append(ctx.team_name(p["team"]) if p["team"] else "—")
            row.append(p["matches"])
            row += [render(p) for _, render in cols]
            rows.append(row)
        return table_section("Combat detail by player", columns, rows, align=align)

    def _lance_table(self, ctx: SeriesContext) -> dict | None:
        buckets: dict[tuple[str, str], list[PlayerStat]] = {}
        for stat, team in ctx.lines():
            lance = stat.extra.get(LANCE[0])
            if lance is None or str(lance).strip() == "":
                continue
            buckets.setdefault((team, str(lance).strip()), []).append(stat)
        if not buckets:
            return None

        columns = ["Lance", "Drops", "Avg Dmg", "Kills", "Survival"]
        align = ["left", "right", "right", "right", "right"]
        if not ctx.is_scoped:
            columns.insert(0, "Team"); align.insert(0, "left")
        rows = []
        for (team, lance), lines in sorted(buckets.items()):
            t = combat_totals(lines)
            row = [f"Lance {lance}", len(lines), fmt(mean([s.damage for s in lines])),
                   sum(s.kills for s in lines), _pct(t["survival_rate"])]
            if not ctx.is_scoped:
                row.insert(0, ctx.team_name(team))
            rows.append(row)
        return table_section("By lance", columns, rows, align=align,
                             note="Lance numbers are as MWO reports them for each drop.")
