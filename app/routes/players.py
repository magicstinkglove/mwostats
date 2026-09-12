"""Cross-series player lookups — currently just the Jarl's List career enrichment.
Unlike the series-scoped /api/series/{id}/players/{username}, this isn't about any
match the app has loaded itself, so it isn't nested under a series.
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from ..service import get_jarls_profile
from .deps import get_conn

router = APIRouter(prefix="/api/players", tags=["players"])


@router.get("/{username}/jarls")
def jarls_lookup(username: str, conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    profile = get_jarls_profile(conn, username)
    # get_jarls_profile writes the cache row on a miss — without committing here, that
    # write lives only in this request's transaction and is rolled back when the
    # connection closes, so the "cache" would silently re-hit Jarl's List every time.
    conn.commit()
    if profile is None:
        return {"found": False}
    return {"found": True, **profile}
