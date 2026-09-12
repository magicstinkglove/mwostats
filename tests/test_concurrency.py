"""Guards against the cross-thread SQLite failure the dashboard triggers on every load.

The frontend requests all metric modules in parallel, so several requests run at once.
FastAPI serves sync endpoints from a threadpool and can run a request's dependency and its
endpoint body on *different* threads — which made every connection a ProgrammingError
waiting to happen. TestClient issues requests sequentially, so none of the other tests see
this; these do.
"""

from __future__ import annotations

import sqlite3
import threading

import pytest
from fastapi.testclient import TestClient

from app import config as config_module
from app.config import Settings
from app.db import connect, init_db
from tests.sample_api import FakeClient, api_payload

PAYLOADS = {
    "m1": api_payload(["Alice", "Bob"], ["Eve", "Fay"], winner=1),
    "m2": api_payload(["Eve", "Fay"], ["Alice", "Bob"], winner=2),
}


@pytest.fixture
def settings(tmp_path, monkeypatch) -> Settings:
    configured = Settings(
        api_token="test-token",
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


def test_connection_is_usable_from_another_thread(settings):
    """The exact failure mode: open here, use over there."""
    init_db(settings)
    conn = connect(settings)
    error: list[Exception] = []

    def use_it():
        try:
            conn.execute("SELECT COUNT(*) FROM match").fetchone()
        except Exception as exc:  # noqa: BLE001 - recording it is the point
            error.append(exc)

    thread = threading.Thread(target=use_it)
    thread.start()
    thread.join()
    conn.close()

    assert not error, f"connection rejected a second thread: {error[0]}"


def test_wal_mode_is_enabled(settings):
    """Readers must not be blocked by an in-flight match write."""
    init_db(settings)
    conn = connect(settings)
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    finally:
        conn.close()


def test_concurrent_metric_requests_all_succeed(settings, monkeypatch):
    """Hit every module at once, the way the dashboard does on load."""
    monkeypatch.setattr("app.service.MWOClient", lambda *a, **k: FakeClient(PAYLOADS))

    from app.main import app

    with TestClient(app) as client:
        series_id = client.post(
            "/api/series", json={"name": "Concurrent", "match_ids": "m1 m2"}
        ).json()["series"]["id"]
        module_ids = [m["id"] for m in client.get("/api/metrics/modules").json()["modules"]]

    results: dict[str, int] = {}
    lock = threading.Lock()

    def fetch(module_id: str) -> None:
        # A client per thread, so the concurrency is real rather than serialised.
        with TestClient(app) as thread_client:
            response = thread_client.get(f"/api/series/{series_id}/metrics/{module_id}")
        with lock:
            results[module_id] = response.status_code

    for _ in range(3):  # repeat: the thread-assignment race is intermittent
        threads = [threading.Thread(target=fetch, args=(mid,)) for mid in module_ids]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert all(code == 200 for code in results.values()), results


def test_sqlite_still_rejects_cross_thread_use_by_default(tmp_path):
    """Documents why the flag is needed — remove it and the app breaks again."""
    path = tmp_path / "default.db"
    conn = sqlite3.connect(path)  # no check_same_thread=False
    conn.execute("CREATE TABLE t (x INTEGER)")
    captured: list[Exception] = []

    def use_it():
        try:
            conn.execute("SELECT * FROM t").fetchall()
        except Exception as exc:  # noqa: BLE001
            captured.append(exc)

    thread = threading.Thread(target=use_it)
    thread.start()
    thread.join()
    conn.close()

    assert captured and isinstance(captured[0], sqlite3.ProgrammingError)
