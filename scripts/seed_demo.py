"""Seed a DEMO series with synthetic matches so the UI can be exercised offline.

This writes fabricated match bodies into the raw cache under DEMO-* IDs and builds a
series from them through the normal ingest path — no network, no real match data.

    python scripts/seed_demo.py          # create/refresh the demo series
    python scripts/seed_demo.py --clear  # remove it and its cached bodies

Nothing here touches real matches; DEMO ids are namespaced so they can't collide.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.cache import RawCache  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import connect, create_series, delete_series, init_db, list_series  # noqa: E402
from app.service import ingest_matches  # noqa: E402

SERIES_NAME = "DEMO — Synthetic Scrim Night"

TEAM_ONE = ["Grimlock", "AshFalcon", "Coldsnap", "VaultWraith", "IronVow", "NullPoint"]
TEAM_TWO = ["RedPike", "Static", "HollowKing", "Marrow", "DustDevil", "Sable"]
SUBS_ONE = ["Kestrel", "Longbarrow"]
SUBS_TWO = ["Tinder", "Quill"]

MECHS = [
    "TBR-PRIME", "TBR-C", "ACH-PRIME", "HBR-B", "MAD-IIC", "EBJ-PRIME",
    "AS7-D-DC", "BLR-1G", "CPLT-K2", "HBK-4G", "SHD-2D", "VTR-9S",
]
MAPS = ["Frozen City", "Canyon Network", "Terra Therma", "Grim Plexus", "Crimson Strait"]
MODES = ["Skirmish", "Domination", "Conquest"]


def make_match(rng: random.Random, index: int, side_one: list[str], side_two: list[str]) -> dict:
    """Build one API-shaped body. Odd matches swap which roster is 'Team 1'."""
    swap = index % 2 == 1
    first, second = (side_two, side_one) if swap else (side_one, side_two)

    users = []
    for side, roster in ((1, first), (2, second)):
        for name in roster:
            damage = max(0, int(rng.gauss(520, 200)))
            kills = min(4, max(0, int(damage / 320 + rng.random())))
            users.append(
                {
                    "Username": name,
                    "Team": str(side),
                    "MechName": rng.choice(MECHS),
                    "Kills": kills,
                    "Assists": rng.randint(0, 5),
                    "Damage": damage,
                    "MatchScore": int(damage * 0.55 + kills * 40 + rng.randint(0, 60)),
                    "IsSpectator": False,
                    "ComponentsDestroyed": rng.randint(0, 6),
                    "HealthPercentage": rng.randint(0, 100),
                }
            )

    winner = rng.choice([1, 2])
    return {
        "MatchDetails": {
            "Map": rng.choice(MAPS),
            "GameMode": rng.choice(MODES),
            "MatchTimeMinutes": rng.randint(6, 14),
            "WinningTeam": winner,
            "Team1Score": 12 if winner == 1 else rng.randint(2, 10),
            "Team2Score": 12 if winner == 2 else rng.randint(2, 10),
            "CompleteTime": f"2026-09-0{index + 1}T20:{index * 7 % 60:02d}:00Z",
        },
        "UserDetails": users,
    }


def build_rosters(rng: random.Random, index: int) -> tuple[list[str], list[str]]:
    """Rotate a substitute in now and then, exactly like a real scrim night."""
    one, two = list(TEAM_ONE), list(TEAM_TWO)
    if index in (2, 4):
        one[rng.randrange(len(one))] = SUBS_ONE[index % len(SUBS_ONE)]
    if index == 3:
        two[rng.randrange(len(two))] = SUBS_TWO[index % len(SUBS_TWO)]
    return one, two


def clear(settings) -> None:
    init_db(settings)
    with connect(settings) as conn:
        for series in list_series(conn):
            if series.name == SERIES_NAME:
                delete_series(conn, series.id)
                print(f"Removed series {series.id} ({series.name})")
        conn.execute("DELETE FROM match WHERE match_id LIKE 'DEMO-%'")
        conn.commit()
    for path in settings.raw_dir.glob("DEMO-*.json"):
        path.unlink()
        print(f"Removed {path.name}")


def main(argv: list[str]) -> int:
    settings = get_settings()
    if "--clear" in argv:
        clear(settings)
        print("Demo data cleared.")
        return 0

    rng = random.Random(20260910)
    cache = RawCache(settings)
    settings.raw_dir.mkdir(parents=True, exist_ok=True)

    match_ids = []
    for index in range(5):
        match_id = f"DEMO-{index + 1}"
        one, two = build_rosters(rng, index)
        cache.put(match_id, make_match(rng, index, one, two))
        match_ids.append(match_id)
        print(f"Wrote {match_id}")

    init_db(settings)
    with connect(settings) as conn:
        clear_existing = [s for s in list_series(conn) if s.name == SERIES_NAME]
        for series in clear_existing:
            delete_series(conn, series.id)

        results = ingest_matches(conn, match_ids)
        stored = [r["match_id"] for r in results if r["status"] != "error"]
        series_id = create_series(conn, SERIES_NAME, stored)
        conn.commit()

    print(f"\nCreated series {series_id}: {SERIES_NAME} with {len(stored)} matches.")
    print("Start the app and pick it from the series dropdown:")
    print("    uvicorn app.main:app --reload")
    print("Remove it later with:  python scripts/seed_demo.py --clear")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
