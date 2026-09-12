"""Print a single match as a table — the original script, now sharing the app's plumbing.

    python match.py 88117337778826

Uses MWO_API_TOKEN from .env (no hardcoded token), goes through the same cache as the web
app, and tries each auth form until one works. For the full dashboard across many matches:

    uvicorn app.main:app --reload
"""

from __future__ import annotations

import sys

from app.config import ConfigError, get_settings
from app.mwo_client import MWOApiError, MWOClient
from app.normalize import NormalizeError, normalize_match


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2

    match_id = argv[0]
    try:
        settings = get_settings()
    except ConfigError as exc:
        print(f"Config error: {exc}")
        return 1

    client = MWOClient(settings)
    try:
        payload, from_cache = client.get_match(match_id)
        match = normalize_match(payload, match_id)
    except (MWOApiError, NormalizeError) as exc:
        print(f"Could not load match {match_id}: {exc}")
        return 1

    source = "cache" if from_cache else "API"
    print("=" * 66)
    print(f"  MWO MATCH  #{match.match_id}   (from {source})")
    print("=" * 66)
    print(f"  Map:     {match.map_name or '—'}")
    print(f"  Mode:    {match.game_mode or '—'} ({match.duration_minutes:g} min)")
    print(f"  Winner:  Side {match.winning_side}  "
          f"({match.side1_score} - {match.side2_score})")
    print("=" * 66)
    print(f"\n{'Player':<18} {'Side':<5} {'Mech':<14} {'Kills':>5} {'Dmg':>7} {'Score':>7}")
    print("-" * 66)
    for player in sorted(match.active_players(), key=lambda p: (p.side, -p.damage)):
        print(
            f"{player.username:<18} {player.side:<5} {player.mech_name:<14} "
            f"{player.kills:>5} {player.damage:>7,.0f} {player.match_score:>7,.0f}"
        )
    print("-" * 66)
    print(f"{len(match.active_players())} players")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
