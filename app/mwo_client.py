"""HTTP client for the MechWarrior Online match API.

Auth note: probing the live endpoint showed the `api_token` request header (used by the
original match.py) returns 401 "Unauthenticated", while `Authorization: Bearer <token>`
and the `?api_token=` query parameter take a different code path. Because the exact
accepted form isn't documented here, `auth_mode: "auto"` walks the candidates and keeps
whichever one stops returning 401 for the rest of the process.
"""

from __future__ import annotations

import time
from typing import Any

import requests

from .cache import RawCache
from .config import Settings

AUTH_MODES = ("query", "bearer", "header")


class MWOApiError(RuntimeError):
    """Base class for API failures."""


class AuthError(MWOApiError):
    """The API rejected our credentials (401/403)."""


class MatchUnavailable(MWOApiError):
    """The API authenticated us but would not return this match (404/422)."""


class RateLimited(MWOApiError):
    """The API asked us to slow down (429)."""


def _apply_auth(mode: str, url: str, token: str) -> tuple[str, dict[str, str]]:
    headers = {"Accept": "application/json"}
    if mode == "bearer":
        headers["Authorization"] = f"Bearer {token}"
    elif mode == "header":
        headers["api_token"] = token
    elif mode == "query":
        joiner = "&" if "?" in url else "?"
        url = f"{url}{joiner}api_token={token}"
    else:
        raise ValueError(f"Unknown auth mode: {mode}")
    return url, headers


class MWOClient:
    def __init__(self, settings: Settings, cache: RawCache | None = None):
        self.settings = settings
        self.cache = cache or RawCache(settings)
        self.session = requests.Session()
        self._modes = list(AUTH_MODES) if settings.auth_mode == "auto" else [settings.auth_mode]
        self._last_request_at = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        wait = self.settings.request_delay_seconds - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.monotonic()

    def _request(self, match_id: str) -> dict[str, Any]:
        base = f"{self.settings.api_base_url}/matches/{match_id}"
        last_error: Exception | None = None

        for mode in list(self._modes):
            url, headers = _apply_auth(mode, base, self.settings.api_token)
            self._throttle()
            try:
                response = self.session.get(
                    url, headers=headers, timeout=self.settings.request_timeout_seconds
                )
            except requests.RequestException as exc:
                raise MWOApiError(f"Network error contacting the MWO API: {exc}") from exc

            if response.status_code in (401, 403):
                # Wrong auth shape — try the next candidate before giving up.
                last_error = AuthError(
                    f"API rejected credentials via {mode} auth "
                    f"({response.status_code}: {response.text[:120]})"
                )
                continue

            # This mode got past auth; stop paying for the others on later calls.
            self._modes = [mode]

            if response.status_code == 429:
                raise RateLimited("MWO API rate limit hit — wait a moment and retry.")
            if response.status_code in (404, 422):
                raise MatchUnavailable(
                    f"Match {match_id} was not returned by the API "
                    f"({response.status_code}). Check the match ID is correct and that "
                    "your account has access to it."
                )
            if response.status_code >= 400:
                raise MWOApiError(
                    f"MWO API returned {response.status_code}: {response.text[:200]}"
                )

            try:
                return response.json()
            except ValueError as exc:
                raise MWOApiError(
                    f"MWO API returned non-JSON for match {match_id}: {response.text[:200]}"
                ) from exc

        raise last_error or MWOApiError("Could not authenticate against the MWO API.")

    def get_match(self, match_id: str, force_refresh: bool = False) -> tuple[dict[str, Any], bool]:
        """Return (payload, from_cache). Cached matches never touch the network."""
        match_id = str(match_id).strip()
        if not force_refresh:
            cached = self.cache.get(match_id)
            if cached is not None:
                return cached, True

        payload = self._request(match_id)
        self.cache.put(match_id, payload)
        return payload, False
