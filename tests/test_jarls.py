"""Jarl's List enrichment: caching (including negative results), TTL expiry, and
shaping the aggregate endpoint into a profile — all with the real network client
mocked out, since this must never depend on a live third-party service.

The aggregate endpoint's Rank/Percentile is the site's own "Overall" row (lifetime,
not per-season) — confirmed by hand against a real profile with a large game count.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db import connect, init_db
from app.service import JARLS_CACHE_TTL_HOURS, get_jarls_profile

# A veteran account — real "Overall" row shape, large sample size, has a lifetime rank.
VETERAN = {
    "PilotName": "Chimera_", "Rank": 3, "Percentile": 99.988, "UnitTag": "V1LE",
    "TotalWins": 4927, "TotalLosses": 1114, "TotalKills": 14294, "WLRatio": 4.42,
    "TotalDeaths": 1963, "KDRatio": 7.28, "SurvivalRate": 68, "GamesPlayed": 6044,
    "KillsPerMatch": 2.36, "AverageMatchScore": 508, "AdjustedScore": 506.8,
    "Progress": -14, "FirstSeason": 0, "LastSeason": 121,
    "LightPercent": 3, "MediumPercent": 10, "HeavyPercent": 27, "AssaultPercent": 54,
    "ServerSeason": 121,
}
# A low-sample/retired account — real shape, Rank 0 / Percentile null (no lifetime rank).
UNRANKED = {
    "PilotName": "Magic Stink Glove", "Rank": 0, "Percentile": None, "UnitTag": None,
    "TotalWins": 27, "TotalLosses": 5, "TotalKills": 106, "WLRatio": 5.4,
    "TotalDeaths": 6, "KDRatio": 17.67, "SurvivalRate": 81, "GamesPlayed": 32,
    "KillsPerMatch": 3.31, "AverageMatchScore": 628, "AdjustedScore": 123.1,
    "Progress": None, "FirstSeason": 105, "LastSeason": 106,
    "LightPercent": 0, "MediumPercent": 0, "HeavyPercent": 56, "AssaultPercent": 41,
    "ServerSeason": 121,
}


class FakeJarlsClient:
    """Records every call so tests can assert the cache actually prevented one."""

    calls = []

    def __init__(self, *a, **k):
        pass

    def get_aggregate(self, username):
        FakeJarlsClient.calls.append(username)
        return {"Chimera_": VETERAN, "Magic Stink Glove": UNRANKED}.get(username)


@pytest.fixture(autouse=True)
def reset_calls():
    FakeJarlsClient.calls = []
    yield


@pytest.fixture
def conn(tmp_path, monkeypatch):
    from app.config import Settings
    from app import config as config_module

    settings = Settings(
        api_token="x", api_base_url="http://x", auth_mode="query", cache_enabled=True,
        cache_dir=tmp_path, max_cache_age_hours=24,
        request_delay_seconds=0.0, request_timeout_seconds=5.0,
    )
    monkeypatch.setattr(config_module, "_cached", settings)
    monkeypatch.setattr("app.service.JarlsClient", FakeJarlsClient)
    init_db(settings)
    connection = connect(settings)
    yield connection
    connection.close()


def test_veteran_player_gets_the_overall_rank(conn):
    profile = get_jarls_profile(conn, "Chimera_")

    assert profile["has_rank"] is True
    assert profile["rank"] == 3
    assert profile["percentile"] == 99.988
    assert profile["wins"] == 4927 and profile["losses"] == 1114
    assert profile["games_played"] == 6044
    assert profile["kd_ratio"] == 7.28
    assert profile["unit_tag"] == "V1LE"
    assert profile["weight_class"] == {"light": 3, "medium": 10, "heavy": 27, "assault": 54}
    assert profile["first_season"] == 0 and profile["last_season"] == 121
    assert profile["profile_url"] == "https://leaderboard.isengrim.org/search?u=Chimera_"


def test_unranked_player_has_no_rank_but_keeps_real_numbers(conn):
    """Rank 0 / Percentile null means no lifetime rank yet — not an error, and not a
    reason to hide the numbers that do exist."""
    profile = get_jarls_profile(conn, "Magic Stink Glove")

    assert profile["has_rank"] is False
    assert profile["rank"] == 0
    assert profile["percentile"] is None
    assert profile["games_played"] == 32
    assert profile["kd_ratio"] == 17.67


def test_unknown_player_returns_none_not_an_error(conn):
    assert get_jarls_profile(conn, "NobodyOnJarlsList") is None


def test_second_lookup_hits_cache_not_the_network(conn):
    get_jarls_profile(conn, "Chimera_")
    assert FakeJarlsClient.calls == ["Chimera_"]

    get_jarls_profile(conn, "Chimera_")
    assert FakeJarlsClient.calls == ["Chimera_"]  # unchanged — served from cache


def test_negative_result_is_also_cached(conn):
    """A player nobody tracks shouldn't get re-queried on every modal open either."""
    get_jarls_profile(conn, "NobodyOnJarlsList")
    get_jarls_profile(conn, "NobodyOnJarlsList")
    assert FakeJarlsClient.calls == ["NobodyOnJarlsList"]


def test_expired_cache_is_refetched(conn):
    get_jarls_profile(conn, "Chimera_")
    assert len(FakeJarlsClient.calls) == 1

    stale = (datetime.now(timezone.utc) - timedelta(hours=JARLS_CACHE_TTL_HOURS + 1)).isoformat(
        timespec="seconds"
    )
    conn.execute("UPDATE jarls_cache SET fetched_at = ? WHERE username = ?",
                 (stale, "Chimera_"))
    conn.commit()

    get_jarls_profile(conn, "Chimera_")
    assert len(FakeJarlsClient.calls) == 2  # queried again after expiry
