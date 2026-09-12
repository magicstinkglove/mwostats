"""Application settings: non-secret values from config.json, token from the environment."""

from __future__ import annotations

import json
import os
import warnings
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.json"

load_dotenv(PROJECT_ROOT / ".env")


class ConfigError(RuntimeError):
    """Raised when the app cannot assemble a usable configuration."""


@dataclass(frozen=True)
class Settings:
    api_token: str
    api_base_url: str
    auth_mode: str
    cache_enabled: bool
    cache_dir: Path
    max_cache_age_hours: int
    request_delay_seconds: float
    request_timeout_seconds: float

    @property
    def raw_dir(self) -> Path:
        return self.cache_dir / "raw"

    @property
    def db_path(self) -> Path:
        return self.cache_dir / "mwo.db"


def _resolve_token(file_config: dict) -> str:
    """The .env/environment token, if any — an empty string is not an error here.

    A token saved through the Settings UI lives in the database instead (see
    service.resolve_settings) and is layered on top of this at the point of use,
    so "nothing in .env" is a perfectly normal state, not a startup failure.
    """
    token = os.environ.get("MWO_API_TOKEN", "").strip()
    if token:
        return token

    # Fallback for anyone still carrying the pre-.env layout.
    legacy = str(file_config.get("api_token", "")).strip()
    if legacy:
        warnings.warn(
            "Reading api_token from config.json. Move it to .env as MWO_API_TOKEN — "
            "config.json is not gitignored.",
            stacklevel=2,
        )
        return legacy

    return ""


def load_settings(config_path: Path | None = None) -> Settings:
    path = config_path or CONFIG_PATH
    if not path.exists():
        raise ConfigError(f"Missing config file: {path}")

    try:
        file_config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc}") from exc

    cache_dir = Path(file_config.get("cache_dir", "data"))
    if not cache_dir.is_absolute():
        cache_dir = PROJECT_ROOT / cache_dir

    return Settings(
        api_token=_resolve_token(file_config),
        api_base_url=file_config.get("api_base_url", "https://mwomercs.com/api/v1").rstrip("/"),
        auth_mode=str(file_config.get("auth_mode", "auto")).lower(),
        cache_enabled=bool(file_config.get("cache_enabled", True)),
        cache_dir=cache_dir,
        max_cache_age_hours=int(file_config.get("max_cache_age_hours", 24)),
        request_delay_seconds=float(file_config.get("request_delay_seconds", 0.5)),
        request_timeout_seconds=float(file_config.get("request_timeout_seconds", 20)),
    )


_cached: Settings | None = None


def get_settings() -> Settings:
    """Process-wide settings singleton."""
    global _cached
    if _cached is None:
        _cached = load_settings()
    return _cached
