"""API token management: DB override beats .env, masking never leaks the secret,
and clearing reverts to whatever (if anything) .env provides."""

from __future__ import annotations

import pytest

from app import config as config_module
from app.config import Settings
from app.db import connect, init_db
from app.service import (
    clear_api_token,
    mask_token,
    resolve_settings,
    set_api_token,
    token_status,
)


@pytest.fixture
def settings(tmp_path, monkeypatch) -> Settings:
    configured = Settings(
        api_token="env-token-abcd",
        api_base_url="http://example.invalid/api/v1",
        auth_mode="query",
        cache_enabled=True,
        cache_dir=tmp_path,
        max_cache_age_hours=24,
        request_delay_seconds=0.0,
        request_timeout_seconds=5.0,
    )
    monkeypatch.setattr(config_module, "_cached", configured)
    return configured


@pytest.fixture
def conn(settings):
    init_db(settings)
    connection = connect(settings)
    yield connection
    connection.close()


def test_mask_token_shows_only_last_four_chars():
    assert mask_token("abcd1234wxyz") == "…wxyz"
    assert "1234wxyz" not in mask_token("abcd1234wxyz")


def test_mask_token_handles_short_and_empty_values():
    assert mask_token("") == ""
    assert mask_token("ab") == "…••"


def test_status_falls_back_to_env_when_nothing_stored(conn):
    status = token_status(conn)
    assert status == {"configured": True, "source": "env", "masked": "…abcd"}


def test_status_reports_none_when_nothing_configured_anywhere(conn, tmp_path, monkeypatch):
    empty = Settings(
        api_token="", api_base_url="http://x", auth_mode="query", cache_enabled=True,
        cache_dir=tmp_path, max_cache_age_hours=24,
        request_delay_seconds=0.0, request_timeout_seconds=5.0,
    )
    monkeypatch.setattr(config_module, "_cached", empty)
    status = token_status(conn)
    assert status == {"configured": False, "source": "none", "masked": None}


def test_set_api_token_overrides_env(conn):
    set_api_token(conn, "database-token-9999")
    status = token_status(conn)
    assert status["source"] == "database"
    assert status["masked"] == "…9999"


def test_set_api_token_rejects_empty_or_whitespace(conn):
    with pytest.raises(ValueError):
        set_api_token(conn, "   ")


def test_set_api_token_strips_whitespace(conn):
    set_api_token(conn, "  padded-token-1111  ")
    resolved = resolve_settings(conn)
    assert resolved.api_token == "padded-token-1111"


def test_clear_api_token_reverts_to_env(conn, settings):
    set_api_token(conn, "database-token-9999")
    assert resolve_settings(conn).api_token == "database-token-9999"

    clear_api_token(conn)

    assert resolve_settings(conn).api_token == settings.api_token
    assert token_status(conn)["source"] == "env"


def test_resolve_settings_only_changes_the_token(conn, settings):
    set_api_token(conn, "database-token-9999")
    resolved = resolve_settings(conn)

    assert resolved.api_token == "database-token-9999"
    assert resolved.api_base_url == settings.api_base_url
    assert resolved.auth_mode == settings.auth_mode
    assert resolved.cache_dir == settings.cache_dir
