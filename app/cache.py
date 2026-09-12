"""Disk cache for raw API bodies.

Completed matches are immutable, so a successfully fetched match is cached forever and
never re-requested. `max_cache_age_hours` only governs incomplete or failed results.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .config import Settings


class RawCache:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.raw_dir = settings.raw_dir

    def _path(self, match_id: str) -> Path:
        safe = "".join(ch for ch in str(match_id) if ch.isalnum() or ch in "-_")
        return self.raw_dir / f"{safe}.json"

    def has(self, match_id: str) -> bool:
        return self.settings.cache_enabled and self._path(match_id).exists()

    def get(self, match_id: str) -> dict[str, Any] | None:
        if not self.settings.cache_enabled:
            return None
        path = self._path(match_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def put(self, match_id: str, payload: dict[str, Any]) -> Path:
        path = self._path(match_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def path_for(self, match_id: str) -> str:
        return str(self._path(match_id))

    def age_hours(self, match_id: str) -> float | None:
        path = self._path(match_id)
        if not path.exists():
            return None
        return (time.time() - path.stat().st_mtime) / 3600.0
