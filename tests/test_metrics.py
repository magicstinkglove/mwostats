"""Metric maths checked against hand-computed numbers, plus the registry contract."""

from __future__ import annotations

import dataclasses

import pytest

from app.metrics import descriptors, get_module
from app.metrics.base import SeriesContext
from app.metrics.registry import DuplicateModuleError, register
from app.models import TEAM_A, TEAM_B, Match, PlayerStat, Series
from app.teams import infer_teams

# Two matches, sides swapped between them, with damage chosen so every average below
# can be verified by hand.
#
#   Team A = Alice, Bob      Team B = Eve, Fay
#   m1: side1 = A (Alice 500, Bob 300)   side2 = B (Eve 400, Fay 200)   side 1 wins
#   m2: side1 = B (Eve 600, Fay 100)     side2 = A (Alice 700, Bob 500) side 2 wins
#
#   Team A damage: 500+300+700+500 = 2000 over 4 lines -> avg 500.0
#   Team B damage: 400+200+600+100 = 1300 over 4 lines -> avg 325.0
#   Team A wins both matches -> 2-0

LINES = {
    "m1": {1: [("Alice", 500, 2), ("Bob", 300, 1)], 2: [("Eve", 400, 1), ("Fay", 200, 0)]},
    "m2": {1: [("Eve", 600, 2), ("Fay", 100, 0)], 2: [("Alice", 700, 3), ("Bob", 500, 1)]},
}
WINNING_SIDE = {"m1": 1, "m2": 2}


def build_matches() -> list[Match]:
    matches = []
    for match_id, sides in LINES.items():
        match = Match(
            match_id=match_id,
            map_name="Frozen City" if match_id == "m1" else "Canyon Network",
            game_mode="Skirmish",
            winning_side=WINNING_SIDE[match_id],
            completed_at=f"2026-09-0{match_id[-1]}T20:00:00Z",
        )
        for side, players in sides.items():
            for name, damage, kills in players:
                match.players.append(
                    PlayerStat(
                        match_id=match_id, username=name, side=side, damage=damage,
                        kills=kills, match_score=damage / 2, mech_name="TBR-PRIME",
                    )
                )
        matches.append(match)
    return matches


@pytest.fixture
def ctx() -> SeriesContext:
    matches = build_matches()
    inference = infer_teams(matches)
    # Pin labels so the assertions below can name teams concretely.
    if inference.assignments["Alice"].team != TEAM_A:
        inference = infer_teams(matches, overrides={"Alice": TEAM_A}, pinned={"Alice"})
    series = Series(id=1, name="Test", team_a_name="Alpha", team_b_name="Bravo",
                    match_ids=[m.match_id for m in matches])
    return SeriesContext(series=series, matches=matches, inference=inference, match_overrides={})


def find_stat(section, label):
    for group in section["groups"]:
        for stat in group["stats"]:
            if stat["label"] == label:
                return stat, group
    raise AssertionError(f"No stat labelled {label!r}")


# ---------------------------------------------------------------- context


def test_context_groups_players_across_the_swap(ctx):
    by_team = ctx.stats_by_team()
    assert {s.username for s in by_team[TEAM_A]} == {"Alice", "Bob"}
    assert {s.username for s in by_team[TEAM_B]} == {"Eve", "Fay"}
    # Four lines each: two players over two matches.
    assert len(by_team[TEAM_A]) == 4


def test_team_record_follows_the_swap(ctx):
    record = ctx.team_record()
    assert record[TEAM_A] == {"wins": 2, "losses": 0}
    assert record[TEAM_B] == {"wins": 0, "losses": 2}


# ---------------------------------------------------------------- modules


def test_core_aggregates_matches_hand_computed_values(ctx):
    payload = get_module("core_aggregates").compute(ctx)
    stats = payload["sections"][0]

    avg, group = find_stat(stats, "Avg Damage")
    assert group["label"] == "Alpha"
    assert avg["value"] == "500.0"

    total, _ = find_stat(stats, "Total Damage")
    assert total["value"] == "2,000"

    record, _ = find_stat(stats, "Record")
    assert record["value"] == "2-0"

    # Team B's group, computed the same way.
    bravo = next(g for g in stats["groups"] if g["label"] == "Bravo")
    assert next(s for s in bravo["stats"] if s["label"] == "Avg Damage")["value"] == "325.0"


def test_core_aggregates_per_match_table(ctx):
    payload = get_module("core_aggregates").compute(ctx)
    table = next(s for s in payload["sections"] if s["type"] == "table")

    m1 = next(row for row in table["rows"] if row[0] == "m1")
    assert m1[3] == "800"   # Alpha: 500 + 300
    assert m1[4] == "600"   # Bravo: 400 + 200
    assert m1[5] == "Alpha"

    m2 = next(row for row in table["rows"] if row[0] == "m2")
    assert m2[3] == "1,200"  # Alpha still Alpha despite the side swap
    assert m2[5] == "Alpha"


def test_leaderboards_pick_the_right_players(ctx):
    """The number leads (`value`); who achieved it is a secondary `name`+`team` field —
    never the username in the bold value slot, which is what made this section look
    cluttered before."""
    payload = get_module("leaderboards").compute(ctx)
    stats = payload["sections"][0]

    avg_damage, _ = find_stat(stats, "Highest Avg Damage")
    assert avg_damage["name"] == "Alice"          # (500+700)/2 = 600
    assert avg_damage["value"] == "600.0"
    assert avg_damage["team"] == TEAM_A
    assert avg_damage["hint"] == "2 matches"

    assert find_stat(stats, "Most Total Damage")[0]["name"] == "Alice"    # 1200
    assert find_stat(stats, "Most Total Damage")[0]["value"] == "1,200"
    assert find_stat(stats, "Most Kills")[0]["name"] == "Alice"           # 2+3 = 5
    assert find_stat(stats, "Most Kills")[0]["value"] == "5"
    assert find_stat(stats, "Biggest Single Game")[0]["name"] == "Alice"  # 700
    assert find_stat(stats, "Biggest Single Game")[0]["value"] == "700"

    # Fay: 200 and 100 -> stdev 50, the smallest swing in the set.
    consistent, _ = find_stat(stats, "Most Consistent")
    assert consistent["name"] == "Fay"
    assert consistent["value"] == "±50.0"
    assert consistent["hint"] == "dmg swing"

    board = payload["sections"][1]
    assert board["rows"][0][1] == "Alice"
    assert board["rows"][0][4] == "600.0"


def test_player_detail_compares_against_own_team(ctx):
    payload = get_module("player_detail").compute(ctx)
    table = payload["sections"][0]

    alice = next(row for row in table["rows"] if row[0] == "Alice")
    assert alice[1] == "Alpha"
    assert alice[3] == "600.0"
    assert alice[4] == "+100.0"   # 600 vs Alpha's 500 average

    fay = next(row for row in table["rows"] if row[0] == "Fay")
    assert fay[4] == "-175.0"     # 150 vs Bravo's 325 average


def test_player_detail_trend_has_a_gap_for_missed_matches(ctx):
    ctx.matches[1].players = [p for p in ctx.matches[1].players if p.username != "Bob"]
    payload = get_module("player_detail").compute(ctx)
    line = next(s for s in payload["sections"] if s["type"] == "line")

    bob = next(l for l in line["lines"] if l["label"] == "Bob")
    assert bob["points"] == [300, None]


def test_player_detail_trend_is_one_chart_per_team(ctx):
    """Each team gets its own chart so players aren't crammed into one shared palette."""
    payload = get_module("player_detail").compute(ctx)
    line_sections = [s for s in payload["sections"] if s["type"] == "line"]

    assert len(line_sections) == 2
    titles = {s["title"] for s in line_sections}
    assert titles == {"Alpha — Damage Trend", "Bravo — Damage Trend"}

    alpha = next(s for s in line_sections if s["title"] == "Alpha — Damage Trend")
    assert {l["label"] for l in alpha["lines"]} == {"Alice", "Bob"}
    bravo = next(s for s in line_sections if s["title"] == "Bravo — Damage Trend")
    assert {l["label"] for l in bravo["lines"]} == {"Eve", "Fay"}

    # No line carries a color/group field — color is assigned by position on
    # the frontend, and must stay a function of identity, not of a value.
    assert all("group" not in l for l in alpha["lines"])


def test_player_detail_trend_lines_are_ordered_alphabetically(ctx):
    """Line order determines chart color, so it must be stable — not value-ranked."""
    payload = get_module("player_detail").compute(ctx)
    bravo = next(s for s in payload["sections"] if s["title"] == "Bravo — Damage Trend")
    assert [l["label"] for l in bravo["lines"]] == ["Eve", "Fay"]


def test_player_detail_trend_caps_lines_and_notes_the_overflow(ctx):
    """More than 8 players on one team folds the rest into a note, not a 9th color."""
    from app.metrics.player_detail import MAX_LINES_PER_CHART

    extra_names = [f"Sub{i}" for i in range(7)]  # 2 existing + 7 = 9, one over the cap of 8
    for match in ctx.matches:
        alice_side = next(p.side for p in match.players if p.username == "Alice")
        for name in extra_names:
            match.players.append(
                type(match.players[0])(
                    match_id=match.match_id, username=name, side=alice_side, damage=100, kills=0,
                )
            )
    ctx.inference = infer_teams(ctx.matches, overrides={"Alice": TEAM_A}, pinned={"Alice"})

    payload = get_module("player_detail").compute(ctx)
    alpha = next(
        s for s in payload["sections"]
        if s["type"] == "line" and s["title"].startswith("Alpha")
    )
    assert len(alpha["lines"]) == MAX_LINES_PER_CHART
    assert "more are in the summary table" in alpha["note"]


def test_match_results_one_section_per_match_in_order(ctx):
    payload = get_module("match_results").compute(ctx)

    assert [s["title"] for s in payload["sections"]] == [
        "Match 1 — Frozen City (Skirmish)",
        "Match 2 — Canyon Network (Skirmish)",
    ]


def test_match_results_labels_the_score_by_team_despite_the_side_swap(ctx):
    """Sides swap between m1 and m2; the score line must still name the real teams."""
    payload = get_module("match_results").compute(ctx)
    m1, m2 = payload["sections"]

    assert "Alpha 0 – 0 Bravo" in m1["note"]
    assert "Alpha won" in m1["note"]
    assert "Match ID m1" in m1["note"]
    # m2: side 1 is Bravo, side 2 is Alpha — the label must follow the team, not the side.
    assert "Bravo 0 – 0 Alpha" in m2["note"]
    assert "Alpha won" in m2["note"]


def test_match_results_rows_are_grouped_by_team_then_damage(ctx):
    payload = get_module("match_results").compute(ctx)
    m1 = payload["sections"][0]

    assert [row[0] for row in m1["rows"]] == ["Alice", "Bob", "Eve", "Fay"]
    alice = m1["rows"][0]
    assert alice == ["Alice", "Alpha", "TBR-PRIME", 2, 0, "500", "250"]


def test_match_results_survives_spectators_and_missing_map_name(ctx):
    ctx.matches[0].map_name = ""
    ctx.matches[0].players.append(
        PlayerStat(match_id="m1", username="Ghost", side=1, is_spectator=True)
    )
    payload = get_module("match_results").compute(ctx)

    assert payload["sections"][0]["title"] == "Match 1 — Unknown map (Skirmish)"
    assert "Ghost" not in [row[0] for row in payload["sections"][0]["rows"]]


def test_breakdowns_mech_variant_split_by_team(ctx):
    payload = get_module("breakdowns").compute(ctx)
    by_mech = next(s for s in payload["sections"] if s["title"] == "By mech variant")

    assert by_mech["columns"][2:4] == ["Alpha Avg", "Bravo Avg"]
    row = next(r for r in by_mech["rows"] if r[0] == "TBR-PRIME")
    assert row[2] == "500.0"   # Alpha: Alice+Bob across both matches
    assert row[3] == "325.0"   # Bravo: Eve+Fay across both matches


def test_breakdowns_mech_variant_blanks_a_team_that_never_used_it(ctx):
    """A mech only one team piloted should not fabricate a zero for the other."""
    ctx.matches[0].players.append(
        PlayerStat(match_id="m1", username="Alice", side=1, damage=999, mech_name="AS7-D", kills=0)
    )
    payload = get_module("breakdowns").compute(ctx)
    by_mech = next(s for s in payload["sections"] if s["title"] == "By mech variant")

    row = next(r for r in by_mech["rows"] if r[0] == "AS7-D")
    assert row[2] == "999.0"
    assert row[3] == "—"


def test_breakdowns_group_by_map(ctx):
    payload = get_module("breakdowns").compute(ctx)
    by_map = next(s for s in payload["sections"] if s["title"] == "By map")

    frozen = next(row for row in by_map["rows"] if row[0] == "Frozen City")
    assert frozen[1] == 1          # one match
    assert frozen[2] == "400.0"    # Alpha: (500+300)/2
    assert frozen[3] == "300.0"    # Bravo: (400+200)/2


def test_modules_survive_an_empty_series():
    """A series with no matches must not blow up any module."""
    series = Series(id=1, name="Empty", match_ids=[])
    ctx = SeriesContext(series=series, matches=[], inference=infer_teams([]), match_overrides={})
    for descriptor in descriptors():
        payload = get_module(descriptor["id"]).compute(ctx)
        assert "sections" in payload


# ---------------------------------------------------------------- team-scoped views


def scoped(ctx: SeriesContext, team: str) -> SeriesContext:
    return dataclasses.replace(ctx, team_filter=team)


def test_context_scoping_narrows_teams_and_lines(ctx):
    a = scoped(ctx, TEAM_A)
    assert a.teams == (TEAM_A,)
    assert a.is_scoped
    assert {s.username for s, _ in a.lines()} == {"Alice", "Bob"}
    assert set(a.stats_by_team().keys()) == {TEAM_A}
    assert set(a.stats_by_player().keys()) == {"Alice", "Bob"}


def test_context_filtered_active_players_narrows_a_single_match(ctx):
    a = scoped(ctx, TEAM_A)
    names = {p.username for p in a.filtered_active_players(ctx.matches[0])}
    assert names == {"Alice", "Bob"}
    # Unscoped, the same match still shows everyone.
    assert {p.username for p in ctx.filtered_active_players(ctx.matches[0])} == {
        "Alice", "Bob", "Eve", "Fay",
    }


def test_core_aggregates_scoped_shows_one_group_with_correct_kd(ctx):
    """K/D must still reflect the real opponent's kills, not an empty scoped bucket."""
    payload = get_module("core_aggregates").compute(scoped(ctx, TEAM_A))
    stats = payload["sections"][0]

    assert len(stats["groups"]) == 1
    assert stats["groups"][0]["label"] == "Alpha"
    # Alpha kills: 2+1+2+1=6 (m1: Alice 2,Bob 1; m2: Eve/Fay's... wait Alpha plays
    # both matches: m1 side1, m2 side2). Bravo kills (the real opponent) are unchanged
    # by scoping, so K/D must match the unscoped computation exactly.
    unscoped = get_module("core_aggregates").compute(ctx)
    alpha_group = next(g for g in unscoped["sections"][0]["groups"] if g["label"] == "Alpha")
    kd_scoped = next(s["value"] for s in stats["groups"][0]["stats"] if s["label"] == "K/D")
    kd_unscoped = next(s["value"] for s in alpha_group["stats"] if s["label"] == "K/D")
    assert kd_scoped == kd_unscoped != "0.00"


def test_leaderboards_scoped_drops_team_column_and_only_ranks_that_team(ctx):
    payload = get_module("leaderboards").compute(scoped(ctx, TEAM_B))
    board = payload["sections"][1]

    assert "Team" not in board["columns"]
    assert {row[1] for row in board["rows"]} == {"Eve", "Fay"}

    mvp_table = payload["sections"][2]
    assert mvp_table["title"] == "Best Performer Per Match"
    assert "Team" not in mvp_table["columns"]
    # The scoped MVP is Bravo's own best player, not the match's overall winner.
    assert all(row[2] in ("Eve", "Fay") for row in mvp_table["rows"])


def test_breakdowns_scoped_collapses_to_one_avg_column(ctx):
    payload = get_module("breakdowns").compute(scoped(ctx, TEAM_A))
    by_mech = next(s for s in payload["sections"] if s["title"] == "By mech variant")

    assert by_mech["columns"] == ["Mech", "Drops", "Avg Dmg", "Total Dmg", "Kills", "Piloted by"]
    row = next(r for r in by_mech["rows"] if r[0] == "TBR-PRIME")
    assert row[2] == "500.0"  # Alpha's own average, matching the unscoped figure

    by_map = next(s for s in payload["sections"] if s["title"] == "By map")
    assert by_map["columns"] == ["Map", "Matches", "Avg Dmg", "Record (W-L)"]


def test_player_detail_scoped_has_only_that_teams_chart(ctx):
    payload = get_module("player_detail").compute(scoped(ctx, TEAM_A))
    line_sections = [s for s in payload["sections"] if s["type"] == "line"]

    assert len(line_sections) == 1
    assert line_sections[0]["title"] == "Alpha — Damage Trend"
    table = payload["sections"][0]
    assert "Team" not in table["columns"]
    assert {row[0] for row in table["rows"]} == {"Alice", "Bob"}


def test_match_results_declares_matches_only_tab():
    descriptor = next(d for d in descriptors() if d["id"] == "match_results")
    assert descriptor["tabs"] == ["matches"]


def test_other_modules_default_to_summary_and_team_tabs():
    for descriptor in descriptors():
        if descriptor["id"] == "match_results":
            continue
        assert descriptor["tabs"] == ["summary", "team"]


def test_all_modules_survive_scoping_to_each_team(ctx):
    """No module should crash when narrowed to a single team's page."""
    for team in (TEAM_A, TEAM_B):
        scoped_ctx = scoped(ctx, team)
        for descriptor in descriptors():
            if "team" not in descriptor["tabs"]:
                continue
            payload = get_module(descriptor["id"]).compute(scoped_ctx)
            assert "sections" in payload


# ---------------------------------------------------------------- registry


def test_all_shipped_modules_are_registered():
    ids = {d["id"] for d in descriptors()}
    assert {
        "core_aggregates", "leaderboards", "match_results", "player_detail", "breakdowns",
    } <= ids


def test_modules_are_ordered_for_display():
    orders = [d["order"] for d in descriptors()]
    assert orders == sorted(orders)


def test_duplicate_module_ids_are_rejected():
    with pytest.raises(DuplicateModuleError):
        @register
        class Clash:
            id = "core_aggregates"
            name = "Clash"
            description = ""
            order = 1

            def compute(self, ctx):
                return {"sections": []}


def test_registering_a_new_module_exposes_it_without_other_changes():
    """The modularity contract: register a class, it shows up in the descriptor list."""
    @register
    class Hello:
        id = "test_hello"
        name = "Hello"
        description = "Test module"
        order = 999

        def compute(self, ctx):
            return {"sections": [{"type": "note", "text": "hi"}]}

    try:
        assert any(d["id"] == "test_hello" for d in descriptors())
        assert get_module("test_hello").compute(None)["sections"][0]["text"] == "hi"
    finally:
        from app.metrics.registry import _MODULES
        _MODULES.pop("test_hello", None)
