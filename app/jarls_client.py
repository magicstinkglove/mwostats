"""Client for The Jarl's List (leaderboard.isengrim.org) — a public, unauthenticated,
community-run archive of historical MWO leaderboard stats. Used to enrich the player
drill-down with career-wide standing that's outside the scope of any match this app has
loaded itself.

Confirmed live and documented at https://leaderboard.isengrim.org/about (see the "public
API" link, /api/):
    GET /api/usernames/{name}   -> lifetime aggregate, including an overall Rank/Percentile

That Rank/Percentile is the same "Overall" row the leaderboard's own website leads with —
verified by hand against a real profile with a large game count (both matched exactly). A
player without enough of a track record for a lifetime rank (or a retired one) gets back
Rank 0 / Percentile null instead; service.py treats that as "no rank yet", not an error.

Unknown pilot name -> 404 with a JSON body. No API key, no documented rate limit — which is
exactly why service.get_jarls_profile caches aggressively instead of calling this on every
modal open.
"""

from __future__ import annotations

import requests

JARLS_BASE_URL = "https://leaderboard.isengrim.org/api"
REQUEST_TIMEOUT_SECONDS = 8
# Identifies this app to their server, same courtesy as a browser User-Agent — lets them
# see real traffic isn't a browser if they ever look, without needing to ask us who we are.
USER_AGENT = "mwostats/1.0 (+https://github.com/magicstinkglove/mwostats)"


class JarlsClient:
    def __init__(self, base_url: str = JARLS_BASE_URL, timeout: float = REQUEST_TIMEOUT_SECONDS):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.session.headers["Accept"] = "application/json"

    def get_aggregate(self, username: str) -> dict | None:
        """The pilot's lifetime/"Overall" record. None if they aren't on Jarl's List,
        or the lookup failed."""
        return self._get(f"/usernames/{username}")

    def _get(self, path: str) -> dict | None:
        # Deliberately collapses every failure mode (404, 5xx, timeout, bad JSON) into
        # None — this is a best-effort enrichment, never worth surfacing a scary error
        # for, and the caller can't act differently on "not found" vs. "their site is down".
        url = f"{self.base_url}{path}"
        try:
            response = self.session.get(url, timeout=self.timeout)
            if response.status_code != 200:
                return None
            return response.json()
        except (requests.RequestException, ValueError):
            return None
