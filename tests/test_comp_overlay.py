"""Combat Detail module (extra API fields) and the broadcast overlay endpoints."""

from __future__ import annotations

from app.metrics import get_module
from app.metrics.base import SeriesContext
from app.metrics.comp_stats import combat_totals
from app.models import PlayerStat, Series
from app.teams import infer_teams
from tests.test_api import client, create_series  # noqa: F401  (fixture)
from tests.test_metrics import build_matches


def line(**extra) -> PlayerStat:
    return PlayerStat(match_id="m", username="X", side=1, extra=extra)


def test_combat_totals_tells_zero_from_not_reported():
    totals = combat_totals([
        line(HealthPercentage=0, KillsMostDamage=1, TeamDamage="12"),
        line(HealthPercentage=40, KillsMostDamage=2),
        line(),  # an older payload without the fields
    ])
    assert totals["reported"] == 2
    assert totals["survived"] == 1
    assert totals["survival_rate"] == 0.5
    assert totals["avg_health"] == 20
    assert totals["solo_kills"] == 3
    assert totals["team_damage"] == 12
    assert totals["components"] is None


def _ctx_with_extras(extras_by_user):
    matches = build_matches()
    for match in matches:
        for p in match.players:
            p.extra = dict(extras_by_user.get(p.username, {}))
    series = Series(id=1, name="T", team_a_name="Alpha", team_b_name="Bravo",
                    match_ids=[m.match_id for m in matches])
    return SeriesContext(series=series, matches=matches, inference=infer_teams(matches), match_overrides={})


def test_comp_stats_awards_name_the_right_pilots():
    ctx = _ctx_with_extras({
        "Alice": {"HealthPercentage": 60, "KillsMostDamage": 2, "TeamDamage": 0, "Lance": "1"},
        "Bob": {"HealthPercentage": 0, "KillsMostDamage": 0, "TeamDamage": 45, "Lance": "1"},
        "Eve": {"HealthPercentage": 10, "KillsMostDamage": 1, "Lance": "2"},
        "Fay": {"HealthPercentage": 0, "Lance": "2"},
    })
    sections = get_module("comp_stats").compute(ctx)["sections"]
    awards = {s["label"]: s for s in sections[1]["groups"][0]["stats"]}
    assert awards["KMDD King"]["name"] == "Alice"
    assert awards["KMDD King"]["value"] == "4"
    assert awards["Friendly Fire Award"]["name"] == "Bob"
    assert awards["Last Mech Standing"]["name"] in {"Alice", "Eve"}  # both survived 2/2
    assert sections[-1]["title"] == "By lance"


def test_comp_stats_without_the_fields_is_a_note():
    sections = get_module("comp_stats").compute(_ctx_with_extras({}))["sections"]
    assert [s["type"] for s in sections] == ["note"]


# ---------------------------------------------------------------- overlay


def test_overlay_with_no_series(client):  # noqa: F811
    body = client.get("/api/overlay").json()
    assert body["series"] is None


def test_overlay_follows_the_newest_series_and_scores_it(client):  # noqa: F811
    create_series(client, "Old")
    series = create_series(client, "League Night")
    client.post(f"/api/series/{series['id']}/matches", json={"match_ids": "m1 m2 m3"})

    body = client.get("/api/overlay").json()
    assert body["series"]["name"] == "League Night"
    assert body["matches_played"] == 3
    wins = sorted(t["wins"] for t in body["teams"].values())
    assert sum(wins) == 3
    assert body["last_match"]["number"] == 3
    assert body["last_match"]["mvp"]["username"]
    assert body["leaders"]


def test_overlay_spotlight_and_pinned_series(client):  # noqa: F811
    first = create_series(client, "First")
    client.post(f"/api/series/{first['id']}/matches", json={"match_ids": "m1 m2"})
    create_series(client, "Second")

    body = client.put("/api/overlay", json={"series_id": first["id"], "spotlight": "Alice"}).json()
    assert body["series"]["name"] == "First"
    assert body["spotlight"]["username"] == "Alice"
    assert body["spotlight"]["matches"] == 2

    # Changing only the spotlight leaves the pinned series alone.
    body = client.put("/api/overlay", json={"spotlight": None}).json()
    assert body["spotlight"] is None
    assert body["state"]["series_id"] == first["id"]

    # Switching series clears a spotlight from the old one.
    client.put("/api/overlay", json={"spotlight": "Alice"})
    body = client.put("/api/overlay", json={"series_id": None}).json()
    assert body["series"]["name"] == "Second"
    assert body["state"]["spotlight"] is None


def test_overlay_rejects_unknown_series(client):  # noqa: F811
    assert client.put("/api/overlay", json={"series_id": 999}).status_code == 404


def test_overlay_and_caster_pages_are_served(client):  # noqa: F811
    assert "OBS" in client.get("/overlay").text
    assert "Caster Controls" in client.get("/caster").text


def test_overlay_team_names_change_only_the_overlay(client):  # noqa: F811
    series = create_series(client, "League Night")
    client.post(f"/api/series/{series['id']}/matches", json={"match_ids": "m1 m2"})
    client.put(f"/api/series/{series['id']}/teams", json={"team_a_name": "[EmP] Emperors", "team_b_name": "Bravo"})

    body = client.put("/api/overlay", json={"team_names": {"A": "  Emperors ", "B": ""}}).json()
    assert body["teams"]["A"]["name"] == "Emperors"
    assert body["teams"]["A"]["app_name"] == "[EmP] Emperors"
    assert body["teams"]["B"]["name"] == "Bravo"
    assert body["last_match"]["winner_name"] in {"Emperors", "Bravo"}

    # The app's own series and stats keep the real name.
    assert client.get(f"/api/series/{series['id']}").json()["team_a_name"] == "[EmP] Emperors"

    # Names are per series: a new newest series starts with its own names.
    create_series(client, "Next Night")
    assert client.get("/api/overlay").json()["teams"]["A"]["name"] == "Team A"

    # Blank reverts to the app's name.
    client.put("/api/overlay", json={"series_id": series["id"]})
    body = client.put("/api/overlay", json={"team_names": {"A": None}}).json()
    assert body["teams"]["A"]["name"] == "[EmP] Emperors"


def test_overlay_sidebars_toggle_and_list_each_team(client):  # noqa: F811
    series = create_series(client, "League Night")
    client.post(f"/api/series/{series['id']}/matches", json={"match_ids": "m1 m2"})

    body = client.get("/api/overlay").json()
    assert body["state"]["sidebars"] is False
    names = {p["username"] for team in ("A", "B") for p in body["sidebars"][team]}
    assert names == {"Alice", "Bob", "Cid", "Eve", "Fay", "Gus"}
    for pilots in body["sidebars"].values():
        damage = [p["avg_damage"] for p in pilots]
        assert damage == sorted(damage, reverse=True)

    assert client.put("/api/overlay", json={"sidebars": True}).json()["state"]["sidebars"] is True
    # Other changes leave the toggle alone.
    assert client.put("/api/overlay", json={"spotlight": "Alice"}).json()["state"]["sidebars"] is True
    assert client.put("/api/overlay", json={"sidebars": False}).json()["state"]["sidebars"] is False


def test_intermission_breaks_down_the_live_series(client):  # noqa: F811
    assert client.get("/api/overlay/intermission").json()["series"] is None

    series = create_series(client, "League Night")
    client.post(f"/api/series/{series['id']}/matches", json={"match_ids": "m1 m2 m3"})
    client.put("/api/overlay", json={"team_names": {"A": "Stream Name"}})

    body = client.get("/api/overlay/intermission").json()
    assert body["pages"] == ["recap", "teams", "players", "awards"]
    assert "Stream Name" in {t["name"] for t in body["teams"].values()}
    assert [m["number"] for m in body["history"]] == [1, 2, 3]
    assert body["last_match"]["box_score"]["A"] and body["last_match"]["box_score"]["B"]
    assert {r["label"] for r in body["comparison"]} >= {"Avg damage per pilot", "Kills"}
    pilots = {p["username"] for rows in body["players"].values() for p in rows}
    assert {"Alice", "Zed", "Eve"} <= pilots
    titles = [a["title"] for a in body["awards"]]
    assert "Damage Dealer" in titles and "Biggest Game" in titles


def test_intermission_page_can_be_pinned_and_released(client):  # noqa: F811
    create_series(client)
    assert client.put("/api/overlay", json={"intermission_page": "awards"}).json()["state"]["intermission_page"] == "awards"
    assert client.put("/api/overlay", json={"intermission_page": None}).json()["state"]["intermission_page"] is None
    assert client.put("/api/overlay", json={"intermission_page": "nope"}).status_code == 400
    assert "Between games" in client.get("/intermission").text


def test_map_plan_ticks_off_maps_as_matches_arrive(client):  # noqa: F811
    series = create_series(client, "League Night")
    plan = [{"map": "Frozen City", "mode": "Skirmish"}, {"map": "Canyon Network"},
            {"map": "  "}, {"map": "River City", "mode": "Conquest"}]
    body = client.put("/api/overlay", json={"map_plan": plan}).json()
    assert [m["map"] for m in body["map_plan"]] == ["Frozen City", "Canyon Network", "River City"]
    assert [m["status"] for m in body["map_plan"]] == ["next", "upcoming", "upcoming"]
    assert "Frozen City" in body["map_choices"] and "Skirmish" in body["mode_choices"]

    client.post(f"/api/series/{series['id']}/matches", json={"match_ids": "m1 m2"})
    body = client.get("/api/overlay").json()
    assert [m["status"] for m in body["map_plan"]] == ["done", "done", "next"]
    assert body["map_plan"][0]["winner_name"]
    assert body["map_plan"][0]["played_map"] == "Frozen City"
    assert client.get("/api/overlay/intermission").json()["map_plan"][2]["status"] == "next"

    # Plans are per series.
    create_series(client, "Next Night")
    assert client.get("/api/overlay").json()["map_plan"] == []


def test_map_plan_is_capped(client):  # noqa: F811
    create_series(client)
    too_many = [{"map": f"Map {i}"} for i in range(21)]
    assert client.put("/api/overlay", json={"map_plan": too_many}).status_code == 422


def test_overlay_elements_switch_on_and_off(client):  # noqa: F811
    create_series(client)
    state = client.get("/api/overlay").json()["state"]
    assert state["elements"] == {"score": True, "last": True, "maps": True, "leaders": True}

    state = client.put("/api/overlay", json={"elements": {"leaders": False}}).json()["state"]
    assert state["elements"]["leaders"] is False and state["elements"]["score"] is True
    # Unrelated changes keep the switches as they are.
    state = client.put("/api/overlay", json={"sidebars": True}).json()["state"]
    assert state["elements"]["leaders"] is False and state["sidebars"] is True
    assert client.put("/api/overlay", json={"elements": {"bogus": True}}).status_code == 400
