"""The metric-module contract.

A module receives a fully-resolved `SeriesContext` — matches, player lines, and the
team assignment already computed — and returns a payload of typed *sections*. The
frontend renders sections generically, so a new module needs no frontend changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import pstdev
from typing import Any, Protocol, runtime_checkable

from ..models import TEAM_A, TEAM_B, Match, PlayerStat, Series
from ..teams import InferenceResult


@dataclass
class SeriesContext:
    series: Series
    matches: list[Match]
    inference: InferenceResult
    match_overrides: dict[tuple[str, str], str]
    # None = the summary/comparison view (both teams). Set to TEAM_A/TEAM_B for a
    # team's own page — every method below then reports only that team's data, so
    # most modules need no code changes at all to support both views: they already
    # loop `for team in ctx.teams` or build off `ctx.lines()`, which do the filtering.
    team_filter: str | None = None

    # ------------------------------------------------ team lookups

    def team_name(self, team: str) -> str:
        return self.series.team_a_name if team == TEAM_A else self.series.team_b_name

    @property
    def teams(self) -> tuple[str, ...]:
        return (self.team_filter,) if self.team_filter else (TEAM_A, TEAM_B)

    @property
    def is_scoped(self) -> bool:
        """True on a team's own page; False on the summary/comparison view."""
        return self.team_filter is not None

    def team_for(self, match_id: str, username: str) -> str | None:
        """Which team a player counted for in a specific match.

        A per-match override wins; otherwise the player's series-wide assignment applies.
        """
        override = self.match_overrides.get((match_id, username))
        if override:
            return override
        assignment = self.inference.assignments.get(username)
        return assignment.team if assignment else None

    def player_team(self, username: str) -> str | None:
        assignment = self.inference.assignments.get(username)
        return assignment.team if assignment else None

    # ------------------------------------------------ stat lookups

    def filtered_active_players(self, match: Match) -> list[PlayerStat]:
        """A match's non-spectator players, narrowed to `team_filter` when scoped.

        Use this instead of `match.active_players()` directly whenever a module
        needs one match's roster (an MVP pick, a per-match scoreboard) — reaching
        past `ctx` for the raw list is what would leak the other team back in on a
        team-scoped page.
        """
        players = match.active_players()
        if self.team_filter is None:
            return players
        return [p for p in players if self.team_for(match.match_id, p.username) == self.team_filter]

    def lines(self) -> list[tuple[PlayerStat, str]]:
        """Every non-spectator player line paired with the team it counted for."""
        out: list[tuple[PlayerStat, str]] = []
        for match in self.matches:
            for stat in self.filtered_active_players(match):
                team = self.team_for(match.match_id, stat.username)
                if team:
                    out.append((stat, team))
        return out

    def stats_by_team(self) -> dict[str, list[PlayerStat]]:
        buckets: dict[str, list[PlayerStat]] = {team: [] for team in self.teams}
        for stat, team in self.lines():
            buckets.setdefault(team, []).append(stat)
        return buckets

    def stats_by_player(self) -> dict[str, list[PlayerStat]]:
        buckets: dict[str, list[PlayerStat]] = {}
        for stat, _ in self.lines():
            buckets.setdefault(stat.username, []).append(stat)
        return buckets

    def match_winner(self, match: Match) -> str | None:
        """Which team won a given match, translating the reported side to a team."""
        if match.winning_side is None:
            return None
        return self.inference.team_of(match.match_id, match.winning_side)

    def team_record(self) -> dict[str, dict[str, int]]:
        record = {TEAM_A: {"wins": 0, "losses": 0}, TEAM_B: {"wins": 0, "losses": 0}}
        for match in self.matches:
            winner = self.match_winner(match)
            if winner in record:
                record[winner]["wins"] += 1
                record[TEAM_B if winner == TEAM_A else TEAM_A]["losses"] += 1
        return record


@runtime_checkable
class MetricModule(Protocol):
    id: str
    name: str
    description: str
    order: int
    # Optional class attribute (defaults to True via getattr where it's read).
    # False means "always a whole-series view" — the module is skipped on a
    # team's own page rather than fetched with team_filter set. A match, for
    # instance, is inherently both teams at once; there's no single-team version
    # of it worth showing separately from the summary.
    #     team_scoped: bool = True

    def compute(self, ctx: SeriesContext) -> dict[str, Any]: ...


# ---------------------------------------------------------------- section builders
# Small helpers so modules stay declarative and every payload has the same shape.


def stats_section(title: str, groups: list[dict[str, Any]], note: str = "") -> dict:
    """groups: [{"label": "Team A", "stats": [{"label": ..., "value": ..., "hint": ...}]}]

    A stat's `value` should be the number the label names ("Highest Avg Damage" ->
    a damage figure) — keep it short, it renders bold and large. When the stat is
    really about *who* achieved it, add `name` (and optional `team`) rather than
    putting the username in `value`: a long name at headline size is what makes a
    leaderboard look cluttered. The frontend renders `name` as a secondary line
    with a small team-colored dot, never in the bold numeric slot.
    """
    return {"type": "stats", "title": title, "groups": groups, "note": note}


def table_section(
    title: str, columns: list[str], rows: list[list[Any]], note: str = "", align: list[str] | None = None
) -> dict:
    return {
        "type": "table",
        "title": title,
        "columns": columns,
        "rows": rows,
        "align": align or [],
        "note": note,
    }


def bar_section(title: str, items: list[dict[str, Any]], unit: str = "", note: str = "") -> dict:
    """items: [{"label": ..., "value": float, "group": "A"|"B"}]"""
    return {"type": "bar", "title": title, "items": items, "unit": unit, "note": note}


def line_section(title: str, x_labels: list[str], lines: list[dict[str, Any]], note: str = "") -> dict:
    """lines: [{"label": ..., "points": [float|None, ...]}]

    Color is assigned by each line's position in this list (a fixed 8-slot
    categorical palette), not by a field on the line — so callers must order
    `lines` by something stable (e.g. username), never by a value that could
    reorder between recomputes. Keep a single section under ~8 lines; beyond
    that, colors repeat and the chart stops being legible — split into more
    than one `line_section` (e.g. one per team) instead.
    """
    return {"type": "line", "title": title, "x": x_labels, "lines": lines, "note": note}


def note_section(text: str) -> dict:
    return {"type": "note", "text": text}


# ---------------------------------------------------------------- numeric helpers


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def stdev(values: list[float]) -> float:
    return pstdev(values) if len(values) > 1 else 0.0


def fmt(value: float, places: int = 1) -> str:
    return f"{value:,.{places}f}"


def ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0
