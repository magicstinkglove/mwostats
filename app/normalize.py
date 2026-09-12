"""Turn a raw MWO API body into Match/PlayerStat records.

Deliberately tolerant: the live response shape is only partly confirmed, so every field
is looked up through an alias list and anything unrecognised is preserved verbatim in
`extra`. Metric modules can then opt into extra fields defensively without a migration.
"""

from __future__ import annotations

from typing import Any

from .models import Match, PlayerStat

# Confirmed present (match.py dereferences these); aliases cover plausible variants.
_MATCH_FIELDS = {
    "map_name": ("Map", "MapName", "map"),
    "game_mode": ("GameMode", "Mode", "gameMode"),
    "duration_minutes": ("MatchTimeMinutes", "MatchDurationMinutes", "Duration"),
    "winning_side": ("WinningTeam", "Winner", "WinningSide"),
    "side1_score": ("Team1Score", "TeamAScore"),
    "side2_score": ("Team2Score", "TeamBScore"),
    "completed_at": ("CompleteTime", "MatchTime", "CompletedAt", "Timestamp"),
}

_PLAYER_FIELDS = {
    "username": ("Username", "UserName", "Name"),
    "side": ("Team", "TeamId", "Side"),
    "mech_name": ("MechName", "Mech", "MechVariant"),
    "kills": ("Kills",),
    "assists": ("Assists",),
    "damage": ("Damage", "DamageDone"),
    "match_score": ("MatchScore", "Score"),
    "is_spectator": ("IsSpectator", "Spectator"),
    "unit_tag": ("UnitTag", "Unit", "ClanTag"),
}


class NormalizeError(ValueError):
    """The payload did not look like a match response."""


def _pick(source: dict, names: tuple[str, ...]) -> Any:
    for name in names:
        if name in source:
            return source[name]
    return None


def _consumed(names_map: dict) -> set[str]:
    return {alias for aliases in names_map.values() for alias in aliases}


def _num(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    return int(_num(value, default))


def _side(value: Any) -> int:
    """Normalise a side identifier to 1 or 2.

    The API reports '1'/'2' but letter forms ('A'/'B') are cheap to tolerate.
    """
    if value is None:
        return 0
    text = str(value).strip().upper()
    if text in ("1", "A", "TEAM1", "TEAMA"):
        return 1
    if text in ("2", "B", "TEAM2", "TEAMB"):
        return 2
    try:
        return int(float(text))
    except ValueError:
        return 0


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ("1", "true", "yes")


def normalize_match(payload: dict, match_id: str) -> Match:
    """Map one raw API body onto a Match. Raises NormalizeError if it isn't one."""
    if not isinstance(payload, dict):
        raise NormalizeError(f"Expected a JSON object, got {type(payload).__name__}")

    details = payload.get("MatchDetails")
    if not isinstance(details, dict):
        raise NormalizeError("Response has no 'MatchDetails' object")

    users = payload.get("UserDetails")
    if not isinstance(users, list):
        raise NormalizeError("Response has no 'UserDetails' list")

    winning_raw = _pick(details, _MATCH_FIELDS["winning_side"])
    match = Match(
        match_id=str(match_id),
        map_name=str(_pick(details, _MATCH_FIELDS["map_name"]) or ""),
        game_mode=str(_pick(details, _MATCH_FIELDS["game_mode"]) or ""),
        duration_minutes=_num(_pick(details, _MATCH_FIELDS["duration_minutes"])),
        winning_side=_side(winning_raw) or None,
        side1_score=_int(_pick(details, _MATCH_FIELDS["side1_score"])),
        side2_score=_int(_pick(details, _MATCH_FIELDS["side2_score"])),
        completed_at=(lambda v: str(v) if v is not None else None)(
            _pick(details, _MATCH_FIELDS["completed_at"])
        ),
        extra={k: v for k, v in details.items() if k not in _consumed(_MATCH_FIELDS)},
    )

    consumed = _consumed(_PLAYER_FIELDS)
    for record in users:
        if not isinstance(record, dict):
            continue
        username = _pick(record, _PLAYER_FIELDS["username"])
        if not username:
            continue
        match.players.append(
            PlayerStat(
                match_id=str(match_id),
                username=str(username).strip(),
                side=_side(_pick(record, _PLAYER_FIELDS["side"])),
                mech_name=str(_pick(record, _PLAYER_FIELDS["mech_name"]) or ""),
                kills=_int(_pick(record, _PLAYER_FIELDS["kills"])),
                assists=_int(_pick(record, _PLAYER_FIELDS["assists"])),
                damage=_num(_pick(record, _PLAYER_FIELDS["damage"])),
                match_score=_num(_pick(record, _PLAYER_FIELDS["match_score"])),
                is_spectator=_bool(_pick(record, _PLAYER_FIELDS["is_spectator"])),
                unit_tag=str(_pick(record, _PLAYER_FIELDS["unit_tag"]) or "").strip(),
                extra={k: v for k, v in record.items() if k not in consumed},
            )
        )

    if not match.players:
        raise NormalizeError("No usable player records in 'UserDetails'")
    return match
