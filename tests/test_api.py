"""End-to-end HTTP tests with the network mocked out."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import config as config_module
from app.config import Settings
from tests.sample_api import FakeClient, api_payload

ALPHA = ["Alice", "Bob", "Cid"]
BRAVO = ["Eve", "Fay", "Gus"]

PAYLOADS = {
    # Sides swap between m1 and m2; Zed subs for Cid in m3.
    "m1": api_payload(ALPHA, BRAVO, map_name="Frozen City", winner=1),
    "m2": api_payload(BRAVO, ALPHA, map_name="Canyon Network", winner=2),
    "m3": api_payload(BRAVO, ["Alice", "Bob", "Zed"], map_name="Frozen City", winner=2),
    # Alice+Bob share the "EmP" unit tag, a clear majority over Cid's "XYZ"; Bravo
    # has no tags at all, so it should stay generic.
    "m4": api_payload(ALPHA, BRAVO, map_name="Frozen City", winner=1,
                       unit_tags={"Alice": "EmP", "Bob": "EmP", "Cid": "XYZ"}),
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    settings = Settings(
        api_token="test-token",
        api_base_url="http://example.invalid/api/v1",
        auth_mode="query",
        cache_enabled=True,
        cache_dir=tmp_path,
        max_cache_age_hours=24,
        request_delay_seconds=0.0,
        request_timeout_seconds=5.0,
    )
    monkeypatch.setattr(config_module, "_cached", settings)

    fake = FakeClient(PAYLOADS)
    monkeypatch.setattr("app.service.MWOClient", lambda *a, **k: fake)

    from app.main import app

    with TestClient(app) as test_client:
        test_client.fake = fake
        yield test_client


def create_series(client, name="Scrim Night", match_ids=""):
    response = client.post("/api/series", json={"name": name, "match_ids": match_ids})
    assert response.status_code == 200, response.text
    return response.json()["series"]


# ---------------------------------------------------------------- basics


def test_health_reports_registered_modules(client):
    body = client.get("/api/health").json()
    assert body["ok"] is True
    assert "core_aggregates" in body["modules"]
    assert body["token"]["configured"] is True
    assert body["token"]["source"] == "env"


# ---------------------------------------------------------------- API token settings


def test_token_status_defaults_to_env(client):
    body = client.get("/api/settings/token").json()
    assert body["configured"] is True
    assert body["source"] == "env"
    assert body["masked"] == "…oken"  # last 4 chars of "test-token"


def test_setting_a_token_overrides_env_and_is_used_for_ingest(client):
    client.put("/api/settings/token", json={"token": "brand-new-secret"})

    status = client.get("/api/settings/token").json()
    assert status["source"] == "database"
    assert status["masked"] == "…cret"

    # The new token is what future health checks report too.
    assert client.get("/api/health").json()["token"]["masked"] == "…cret"


def test_setting_an_empty_token_is_rejected(client):
    response = client.put("/api/settings/token", json={"token": "   "})
    assert response.status_code == 400


def test_clearing_a_token_reverts_to_env(client):
    client.put("/api/settings/token", json={"token": "brand-new-secret"})
    response = client.delete("/api/settings/token")
    body = response.json()
    assert body["source"] == "env"
    assert body["masked"] == "…oken"


def test_a_saved_token_is_never_returned_in_full(client):
    client.put("/api/settings/token", json={"token": "super-secret-value-123"})
    body = client.get("/api/settings/token").json()
    assert "super-secret-value-123" not in str(body)


def test_index_page_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "MWO Match Stats" in response.text


def test_modules_endpoint_lists_descriptors(client):
    modules = client.get("/api/metrics/modules").json()["modules"]
    assert {m["id"] for m in modules} >= {"core_aggregates", "leaderboards"}
    assert all(m["name"] and "description" in m for m in modules)


# ---------------------------------------------------------------- ingest


def test_add_matches_groups_players_across_swaps_and_subs(client):
    series = create_series(client)
    response = client.post(
        f"/api/series/{series['id']}/matches", json={"match_ids": "m1, m2\nm3"}
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert [r["status"] for r in body["ingest"]] == ["fetched"] * 3

    rosters = body["series"]["rosters"]
    team_of = {
        player["username"]: team
        for team, players in rosters.items()
        for player in players
    }

    # The swap must not split the teams.
    assert team_of["Alice"] == team_of["Bob"] == team_of["Cid"]
    assert team_of["Eve"] == team_of["Fay"] == team_of["Gus"]
    assert team_of["Alice"] != team_of["Eve"]
    # The substitute lands with the side they actually played on.
    assert team_of["Zed"] == team_of["Alice"]


def test_bad_match_id_is_isolated_from_good_ones(client):
    series = create_series(client)
    body = client.post(
        f"/api/series/{series['id']}/matches", json={"match_ids": "m1 nope m2"}
    ).json()

    statuses = {r["match_id"]: r["status"] for r in body["ingest"]}
    assert statuses == {"m1": "fetched", "nope": "error", "m2": "fetched"}
    assert body["series"]["match_ids"] == ["m1", "m2"]

    failure = next(r for r in body["ingest"] if r["status"] == "error")
    assert "not returned by the API" in failure["detail"]


def test_stored_matches_are_not_refetched(client):
    series = create_series(client)
    client.post(f"/api/series/{series['id']}/matches", json={"match_ids": "m1 m2"})
    assert client.fake.requested == ["m1", "m2"]

    second = client.post(f"/api/series/{series['id']}/matches", json={"match_ids": "m1 m2"})
    # No new network calls, and the API says so.
    assert client.fake.requested == ["m1", "m2"]
    assert [r["status"] for r in second.json()["ingest"]] == ["stored", "stored"]


def test_empty_match_list_is_rejected(client):
    series = create_series(client)
    response = client.post(f"/api/series/{series['id']}/matches", json={"match_ids": "   "})
    assert response.status_code == 400


# ---------------------------------------------------------------- overrides


def test_override_moves_a_player_and_pins_them(client):
    series = create_series(client)
    body = client.post(f"/api/series/{series['id']}/matches", json={"match_ids": "m1 m2 m3"}).json()
    rosters = body["series"]["rosters"]
    zed_team = next(t for t, players in rosters.items() if any(p["username"] == "Zed" for p in players))
    other = "B" if zed_team == "A" else "A"

    moved = client.put(
        f"/api/series/{series['id']}/assignments",
        json={"username": "Zed", "team": other},
    ).json()["series"]

    zed = next(
        p for players in moved["rosters"].values() for p in players if p["username"] == "Zed"
    )
    assert zed["team"] == other
    assert zed["source"] == "pinned"
    assert zed["needs_review"] is False


def test_override_can_be_cleared(client):
    series = create_series(client)
    client.post(f"/api/series/{series['id']}/matches", json={"match_ids": "m1 m2"})
    client.put(f"/api/series/{series['id']}/assignments", json={"username": "Alice", "team": "B"})

    cleared = client.put(
        f"/api/series/{series['id']}/assignments", json={"username": "Alice", "team": None}
    ).json()["series"]

    alice = next(
        p for players in cleared["rosters"].values() for p in players if p["username"] == "Alice"
    )
    assert alice["source"] == "inferred"


def test_invalid_team_letter_is_rejected(client):
    series = create_series(client)
    client.post(f"/api/series/{series['id']}/matches", json={"match_ids": "m1"})
    response = client.put(
        f"/api/series/{series['id']}/assignments", json={"username": "Alice", "team": "Z"}
    )
    assert response.status_code == 400


def test_team_names_persist_and_reach_the_metrics(client):
    series = create_series(client)
    client.post(f"/api/series/{series['id']}/matches", json={"match_ids": "m1 m2"})
    client.put(
        f"/api/series/{series['id']}/teams",
        json={"team_a_name": "House Kurita", "team_b_name": "House Davion"},
    )

    payload = client.get(f"/api/series/{series['id']}/metrics/core_aggregates").json()
    labels = {g["label"] for g in payload["sections"][0]["groups"]}
    assert labels == {"House Kurita", "House Davion"}


# ---------------------------------------------------------------- clan tag naming


def test_series_is_auto_named_from_its_dominant_clan_tag(client):
    series = create_series(client)
    body = client.post(
        f"/api/series/{series['id']}/matches", json={"match_ids": "m4"}
    ).json()["series"]

    assert body["team_a_name"] == "[EmP]"
    assert body["team_b_name"] == "Team B"  # Bravo has no tags -> stays generic


def test_manual_team_rename_survives_later_matches(client):
    """A rename via PUT /teams is a sentinel-clearing action — later tag evidence
    must never overwrite what the user explicitly chose."""
    series = create_series(client)
    client.post(f"/api/series/{series['id']}/matches", json={"match_ids": "m1"})
    client.put(
        f"/api/series/{series['id']}/teams",
        json={"team_a_name": "House Kurita", "team_b_name": "House Davion"},
    )

    # m4 shares Alice/Bob/Cid's roster and carries a clear "EmP" majority for Alpha.
    body = client.post(
        f"/api/series/{series['id']}/matches", json={"match_ids": "m4"}
    ).json()["series"]

    assert body["team_a_name"] == "House Kurita"
    assert body["team_b_name"] == "House Davion"


# ---------------------------------------------------------------- metrics


def test_every_module_renders_for_a_real_series(client):
    series = create_series(client)
    client.post(f"/api/series/{series['id']}/matches", json={"match_ids": "m1 m2 m3"})

    for module in client.get("/api/metrics/modules").json()["modules"]:
        response = client.get(f"/api/series/{series['id']}/metrics/{module['id']}")
        assert response.status_code == 200, module["id"]
        body = response.json()
        assert not body.get("error"), f"{module['id']} errored: {body}"
        assert body["sections"], module["id"]
        for section in body["sections"]:
            assert section["type"] in {"stats", "table", "bar", "line", "note"}


def test_metrics_on_an_empty_series_are_a_friendly_note(client):
    series = create_series(client)
    body = client.get(f"/api/series/{series['id']}/metrics/core_aggregates").json()
    assert body["sections"][0]["type"] == "note"


def test_unknown_module_404s(client):
    series = create_series(client)
    assert client.get(f"/api/series/{series['id']}/metrics/nope").status_code == 404


# ---------------------------------------------------------------- team-scoped tabs


def test_team_scoped_metrics_endpoint(client):
    series = create_series(client)
    client.post(f"/api/series/{series['id']}/matches", json={"match_ids": "m1 m2 m3"})

    response = client.get(f"/api/series/{series['id']}/metrics/core_aggregates?team=A")
    assert response.status_code == 200
    assert len(response.json()["sections"][0]["groups"]) == 1


def test_invalid_team_query_param_is_rejected(client):
    series = create_series(client)
    client.post(f"/api/series/{series['id']}/matches", json={"match_ids": "m1"})
    response = client.get(f"/api/series/{series['id']}/metrics/core_aggregates?team=Z")
    assert response.status_code == 400


def test_match_results_rejects_a_team_query_param(client):
    """match_results has no team-scoped view — it's always both teams at once."""
    series = create_series(client)
    client.post(f"/api/series/{series['id']}/matches", json={"match_ids": "m1"})
    response = client.get(f"/api/series/{series['id']}/metrics/match_results?team=A")
    assert response.status_code == 400


def test_modules_endpoint_reports_tabs(client):
    modules = client.get("/api/metrics/modules").json()["modules"]
    match_results = next(m for m in modules if m["id"] == "match_results")
    other = next(m for m in modules if m["id"] == "core_aggregates")
    assert match_results["tabs"] == ["matches"]
    assert other["tabs"] == ["summary", "team"]


def test_player_endpoint_returns_history(client):
    series = create_series(client)
    client.post(f"/api/series/{series['id']}/matches", json={"match_ids": "m1 m2 m3"})

    body = client.get(f"/api/series/{series['id']}/players/Alice").json()
    assert body["totals"]["matches"] == 3
    assert len(body["matches"]) == 3
    assert body["team_name"]


def test_unknown_player_404s(client):
    series = create_series(client)
    client.post(f"/api/series/{series['id']}/matches", json={"match_ids": "m1"})
    assert client.get(f"/api/series/{series['id']}/players/Nobody").status_code == 404


# ---------------------------------------------------------------- persistence


def test_series_and_matches_survive_a_new_client(client):
    series = create_series(client, name="Persisted")
    client.post(f"/api/series/{series['id']}/matches", json={"match_ids": "m1 m2"})

    from app.main import app

    with TestClient(app) as second:
        listing = second.get("/api/series").json()["series"]
        assert any(s["name"] == "Persisted" and s["match_count"] == 2 for s in listing)
        reloaded = second.get(f"/api/series/{series['id']}").json()
        assert len(reloaded["matches"]) == 2

    # Reading it back hit no network.
    assert client.fake.requested == ["m1", "m2"]


def test_removing_a_match_updates_the_series(client):
    series = create_series(client)
    client.post(f"/api/series/{series['id']}/matches", json={"match_ids": "m1 m2"})

    body = client.delete(f"/api/series/{series['id']}/matches/m1").json()["series"]
    assert body["match_ids"] == ["m2"]


def test_series_404s_when_missing(client):
    assert client.get("/api/series/9999").status_code == 404


def test_deleting_a_series_removes_it_from_the_list(client):
    series = create_series(client, name="Throwaway")
    other = create_series(client, name="Keep Me")

    response = client.delete(f"/api/series/{series['id']}")
    assert response.status_code == 200
    assert response.json() == {"deleted": series["id"]}

    listing = {s["id"] for s in client.get("/api/series").json()["series"]}
    assert series["id"] not in listing
    assert other["id"] in listing
    assert client.get(f"/api/series/{series['id']}").status_code == 404


def test_deleting_a_series_does_not_delete_the_cached_matches(client):
    """Match data is shared/reusable — only the series' own grouping is deleted."""
    series = create_series(client)
    client.post(f"/api/series/{series['id']}/matches", json={"match_ids": "m1"})
    client.delete(f"/api/series/{series['id']}")

    other = create_series(client, name="Reuses cached match")
    result = client.post(
        f"/api/series/{other['id']}/matches", json={"match_ids": "m1"}
    ).json()
    assert result["ingest"][0]["status"] == "stored"
    assert client.fake.requested == ["m1"]  # never fetched a second time
