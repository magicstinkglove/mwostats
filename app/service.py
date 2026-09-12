"""Application logic shared by the routes: ingesting matches and assembling contexts."""

from __future__ import annotations

import dataclasses
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus

from .cache import RawCache
from .config import Settings, get_settings
from .db import (
    delete_app_setting,
    get_app_setting,
    get_jarls_cache,
    get_match_overrides,
    get_overrides,
    get_series,
    load_matches,
    load_match,
    rename_teams,
    save_match,
    set_app_setting,
    set_jarls_cache,
)
from .jarls_client import JarlsClient
from .metrics.base import SeriesContext
from .models import TEAM_A, TEAM_B, DEFAULT_TEAM_A_NAME, DEFAULT_TEAM_B_NAME, Match
from .mwo_client import MatchUnavailable, MWOApiError, MWOClient
from .normalize import NormalizeError, normalize_match
from .teams import InferenceResult, infer_clan_tag, infer_teams

_ID_SPLIT = re.compile(r"[\s,;]+")
_API_TOKEN_KEY = "api_token"


# ---------------------------------------------------------------- settings (API token)


def mask_token(token: str) -> str:
    """Show just enough to recognise a token without exposing it — the point of
    ever surfacing a secret back to the UI is confirming *which* one is active,
    not letting someone read it off the screen or a network log."""
    if not token:
        return ""
    return f"…{token[-4:]}" if len(token) > 4 else "…" + "•" * len(token)


def resolve_settings(conn: sqlite3.Connection) -> Settings:
    """The token saved via the Settings UI overrides .env, not the other way round —
    it's the more recent, more explicit choice. Everything else still comes from
    config.json/.env; only the token is ever settable through the app itself.
    """
    settings = get_settings()
    stored = get_app_setting(conn, _API_TOKEN_KEY)
    if stored:
        return dataclasses.replace(settings, api_token=stored)
    return settings


def token_status(conn: sqlite3.Connection) -> dict[str, Any]:
    stored = get_app_setting(conn, _API_TOKEN_KEY)
    if stored:
        return {"configured": True, "source": "database", "masked": mask_token(stored)}
    env_token = get_settings().api_token
    if env_token:
        return {"configured": True, "source": "env", "masked": mask_token(env_token)}
    return {"configured": False, "source": "none", "masked": None}


def set_api_token(conn: sqlite3.Connection, token: str) -> None:
    token = token.strip()
    if not token:
        raise ValueError("Token cannot be empty.")
    set_app_setting(conn, _API_TOKEN_KEY, token)


def clear_api_token(conn: sqlite3.Connection) -> None:
    """Revert to whatever (if anything) .env provides."""
    delete_app_setting(conn, _API_TOKEN_KEY)


# ---------------------------------------------------------------- Jarl's List enrichment

JARLS_CACHE_TTL_HOURS = 12


def _hours_since(iso_timestamp: str) -> float:
    then = datetime.fromisoformat(iso_timestamp)
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - then).total_seconds() / 3600.0


def _build_jarls_profile(username: str, aggregate: dict) -> dict:
    """Shape the aggregate endpoint into a compact profile — this *is* the "Overall" row
    the leaderboard's own website leads with, verified by hand against a real profile
    with a large game count (every field matched). `has_rank` is False when Rank is 0 /
    Percentile is null — seen for accounts without enough of a lifetime track record (or
    a retired one); the caller shows what real numbers exist without inventing a rank.
    """
    rank = aggregate.get("Rank")
    percentile = aggregate.get("Percentile")
    return {
        "profile_url": f"https://leaderboard.isengrim.org/search?u={quote_plus(username)}",
        "unit_tag": aggregate.get("UnitTag"),
        "has_rank": bool(rank) and percentile is not None,
        "rank": rank,
        "percentile": percentile,
        "wins": aggregate.get("TotalWins"),
        "losses": aggregate.get("TotalLosses"),
        "kd_ratio": aggregate.get("KDRatio"),
        "wl_ratio": aggregate.get("WLRatio"),
        "survival_rate": aggregate.get("SurvivalRate"),
        "games_played": aggregate.get("GamesPlayed"),
        "avg_match_score": aggregate.get("AverageMatchScore"),
        "first_season": aggregate.get("FirstSeason"),
        "last_season": aggregate.get("LastSeason"),
        "weight_class": {
            "light": aggregate.get("LightPercent"),
            "medium": aggregate.get("MediumPercent"),
            "heavy": aggregate.get("HeavyPercent"),
            "assault": aggregate.get("AssaultPercent"),
        },
    }


def get_jarls_profile(conn: sqlite3.Connection, username: str) -> dict | None:
    """Best-effort career lookup on the third-party Jarl's List. None if the pilot isn't
    tracked there, or the lookup failed — either way, callers must treat this as optional
    enrichment, never a required part of showing a player.

    Cached for JARLS_CACHE_TTL_HOURS regardless of outcome, so a player nobody tracks
    doesn't get re-queried on every single modal open — see jarls_cache in db.py.
    """
    cached = get_jarls_cache(conn, username)
    if cached is not None:
        profile, fetched_at = cached
        if _hours_since(fetched_at) < JARLS_CACHE_TTL_HOURS:
            return profile

    aggregate = JarlsClient().get_aggregate(username)
    profile = _build_jarls_profile(username, aggregate) if aggregate else None

    set_jarls_cache(conn, username, profile)
    return profile


def parse_match_ids(raw: str | list[str]) -> list[str]:
    """Accept a textarea blob or a list; return de-duplicated, order-preserving IDs."""
    if isinstance(raw, str):
        candidates = _ID_SPLIT.split(raw)
    else:
        candidates = [str(item) for item in raw]

    seen: set[str] = set()
    out: list[str] = []
    for candidate in candidates:
        cleaned = candidate.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            out.append(cleaned)
    return out


def ingest_matches(
    conn: sqlite3.Connection, match_ids: list[str], force_refresh: bool = False
) -> list[dict[str, Any]]:
    """Fetch/normalise/store each match. One bad ID never sinks the batch."""
    settings = resolve_settings(conn)
    cache = RawCache(settings)
    client = MWOClient(settings, cache)
    results: list[dict[str, Any]] = []

    for match_id in match_ids:
        if not force_refresh and load_match(conn, match_id) is not None:
            results.append({"match_id": match_id, "status": "stored", "detail": "Already in database"})
            continue
        if not settings.api_token:
            results.append({
                "match_id": match_id, "status": "error",
                "detail": "No MWO API token configured — add one in Settings.",
            })
            continue
        try:
            payload, from_cache = client.get_match(match_id, force_refresh=force_refresh)
            match = normalize_match(payload, match_id)
            save_match(conn, match, cache.path_for(match_id))
            conn.commit()
            results.append(
                {
                    "match_id": match_id,
                    "status": "cached" if from_cache else "fetched",
                    "detail": (
                        f"{len(match.active_players())} players · "
                        f"{match.map_name or 'unknown map'}"
                    ),
                    "map": match.map_name,
                    "game_mode": match.game_mode,
                }
            )
        except MatchUnavailable as exc:
            results.append({"match_id": match_id, "status": "error", "detail": str(exc)})
        except NormalizeError as exc:
            results.append(
                {
                    "match_id": match_id,
                    "status": "error",
                    "detail": f"Unexpected response shape: {exc}",
                }
            )
        except MWOApiError as exc:
            results.append({"match_id": match_id, "status": "error", "detail": str(exc)})

    return results


def resolve_series(conn: sqlite3.Connection, series_id: int):
    """Load a series and run inference over its matches.

    Returns (series, matches, inference, match_overrides) or None if the series is gone.
    """
    series = get_series(conn, series_id)
    if series is None:
        return None

    matches = load_matches(conn, series.match_ids)
    matches.sort(key=lambda m: (m.completed_at or "", m.match_id))
    overrides, pinned = get_overrides(conn, series_id)
    inference = infer_teams(matches, overrides=overrides, pinned=pinned)
    match_overrides = get_match_overrides(conn, series_id)
    return series, matches, inference, match_overrides


def maybe_autoname_teams(conn: sqlite3.Connection, series_id: int) -> None:
    """Name a team after its dominant unit tag, e.g. "[EmP]" — a fun default, not
    a forced one. Only touches a team name that's still the untouched "Team A" /
    "Team B" sentinel, so a manual rename (via PUT /series/{id}/teams) always wins
    and is never overwritten by a later match or roster change.
    """
    resolved = resolve_series(conn, series_id)
    if resolved is None:
        return
    series, matches, inference, _ = resolved

    new_a = series.team_a_name
    new_b = series.team_b_name
    if series.team_a_name == DEFAULT_TEAM_A_NAME:
        tag = infer_clan_tag(matches, inference, TEAM_A)
        if tag:
            new_a = f"[{tag}]"
    if series.team_b_name == DEFAULT_TEAM_B_NAME:
        tag = infer_clan_tag(matches, inference, TEAM_B)
        if tag:
            new_b = f"[{tag}]"

    if new_a != series.team_a_name or new_b != series.team_b_name:
        rename_teams(conn, series_id, new_a, new_b)


def build_context(
    conn: sqlite3.Connection, series_id: int, team_filter: str | None = None
) -> SeriesContext | None:
    resolved = resolve_series(conn, series_id)
    if resolved is None:
        return None
    series, matches, inference, match_overrides = resolved
    return SeriesContext(
        series=series,
        matches=matches,
        inference=inference,
        match_overrides=match_overrides,
        team_filter=team_filter,
    )


def serialize_assignment(assignment) -> dict[str, Any]:
    return {
        "username": assignment.username,
        "team": assignment.team,
        "confidence": assignment.confidence,
        "match_count": assignment.match_count,
        "source": assignment.source,
        "contested": assignment.contested,
        "needs_review": assignment.needs_review,
    }


def serialize_match(match: Match, inference: InferenceResult | None = None) -> dict[str, Any]:
    mapping = inference.match_side_team.get(match.match_id, {}) if inference else {}
    return {
        "match_id": match.match_id,
        "map": match.map_name,
        "game_mode": match.game_mode,
        "duration_minutes": match.duration_minutes,
        "winning_side": match.winning_side,
        "winning_team": mapping.get(match.winning_side) if match.winning_side else None,
        "side1_score": match.side1_score,
        "side2_score": match.side2_score,
        "completed_at": match.completed_at,
        "side_team_map": {str(k): v for k, v in mapping.items()},
        "players": [
            {
                "username": p.username,
                "side": p.side,
                "team": mapping.get(p.side),
                "mech": p.mech_name,
                "kills": p.kills,
                "assists": p.assists,
                "damage": p.damage,
                "match_score": p.match_score,
            }
            for p in match.active_players()
        ],
    }
