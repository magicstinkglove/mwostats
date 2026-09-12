"""Typed records the rest of the app works with, decoupled from the API's wire format."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

TEAM_A = "A"
TEAM_B = "B"

# The sentinel that means "never renamed" — service.py auto-names a team to its
# dominant unit tag only while its name is still exactly this, so a real manual
# rename (including back to literal "Team A") is never clobbered afterward.
DEFAULT_TEAM_A_NAME = "Team A"
DEFAULT_TEAM_B_NAME = "Team B"


@dataclass
class PlayerStat:
    """One player's line in one match."""

    match_id: str
    username: str
    side: int
    mech_name: str = ""
    kills: int = 0
    assists: int = 0
    damage: float = 0.0
    match_score: float = 0.0
    is_spectator: bool = False
    unit_tag: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def chassis(self) -> str:
        """Best-effort chassis from a variant name (e.g. 'TBR-PRIME' -> 'TBR')."""
        name = self.mech_name or ""
        return name.split("-", 1)[0].strip().upper() if "-" in name else name.strip().upper()


@dataclass
class Match:
    """A single match plus its player lines."""

    match_id: str
    map_name: str = ""
    game_mode: str = ""
    duration_minutes: float = 0.0
    winning_side: int | None = None
    side1_score: int = 0
    side2_score: int = 0
    completed_at: str | None = None
    players: list[PlayerStat] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def active_players(self) -> list[PlayerStat]:
        """Players who actually fought — spectators skew every average."""
        return [p for p in self.players if not p.is_spectator]

    def sides(self) -> dict[int, list[str]]:
        out: dict[int, list[str]] = {}
        for p in self.active_players():
            out.setdefault(p.side, []).append(p.username)
        return out


@dataclass
class TeamAssignment:
    """Where the inference engine placed one player, and how sure it is."""

    username: str
    team: str
    confidence: float
    match_count: int
    source: str = "inferred"  # inferred | pinned | override
    contested: bool = False

    @property
    def needs_review(self) -> bool:
        if self.source in ("pinned", "override"):
            return False
        return self.contested or self.match_count <= 1 or self.confidence < 0.35


@dataclass
class Series:
    """A named collection of matches analysed together."""

    id: int | None
    name: str
    team_a_name: str = DEFAULT_TEAM_A_NAME
    team_b_name: str = DEFAULT_TEAM_B_NAME
    match_ids: list[str] = field(default_factory=list)
    created_at: str | None = None
