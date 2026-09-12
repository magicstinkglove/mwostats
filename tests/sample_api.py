"""Builders for API-shaped payloads, matching the fields match.py proved exist."""

from __future__ import annotations


def api_payload(
    side1: list[str],
    side2: list[str],
    map_name: str = "Frozen City",
    game_mode: str = "Skirmish",
    winner: int = 1,
    spectators: list[str] | None = None,
    extra_user_fields: dict | None = None,
    unit_tags: dict | None = None,
) -> dict:
    """Build a MatchDetails/UserDetails body like the live endpoint returns.

    `unit_tags` optionally maps username -> UnitTag (real MWO field, e.g. "EmP");
    anyone not in the mapping gets an empty tag, matching a pickup player in-game.
    """
    users = []
    unit_tags = unit_tags or {}

    def add(name: str, side: int, index: int, spectator: bool = False) -> None:
        record = {
            "Username": name,
            "Team": str(side),
            "MechName": f"TBR-{'PRIME' if index % 2 == 0 else 'C'}",
            "Kills": index % 3,
            "Assists": index % 4,
            "Damage": 300 + index * 100,
            "MatchScore": 200 + index * 50,
            "IsSpectator": spectator,
            "UnitTag": unit_tags.get(name, ""),
        }
        if extra_user_fields:
            record.update(extra_user_fields)
        users.append(record)

    for index, name in enumerate(side1):
        add(name, 1, index)
    for index, name in enumerate(side2):
        add(name, 2, index)
    for index, name in enumerate(spectators or []):
        add(name, 1, index, spectator=True)

    return {
        "MatchDetails": {
            "Map": map_name,
            "GameMode": game_mode,
            "MatchTimeMinutes": 12,
            "WinningTeam": winner,
            "Team1Score": 12 if winner == 1 else 5,
            "Team2Score": 12 if winner == 2 else 5,
            "CompleteTime": "2026-09-01T20:00:00Z",
        },
        "UserDetails": users,
    }


class FakeClient:
    """Drop-in for MWOClient that serves canned payloads and records what was asked for."""

    def __init__(self, payloads: dict[str, dict], *args, **kwargs):
        self.payloads = payloads
        self.requested: list[str] = []

    def get_match(self, match_id: str, force_refresh: bool = False):
        self.requested.append(match_id)
        if match_id not in self.payloads:
            from app.mwo_client import MatchUnavailable

            raise MatchUnavailable(f"Match {match_id} was not returned by the API (422).")
        return self.payloads[match_id], False
