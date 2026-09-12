"""The whole point of the app: same humans group together regardless of numeric side."""

from __future__ import annotations

import pytest

from app.models import TEAM_A, TEAM_B, Match, PlayerStat
from app.teams import infer_clan_tag, infer_teams

ALPHA = ["Alice", "Bob", "Cid", "Dot"]
BRAVO = ["Eve", "Fay", "Gus", "Hal"]


def build(
    match_id: str,
    side1: list[str],
    side2: list[str],
    spectators: list[str] | None = None,
    unit_tags: dict[str, str] | None = None,
) -> Match:
    unit_tags = unit_tags or {}
    match = Match(match_id=match_id, map_name="Frozen City", game_mode="Skirmish")
    for name in side1:
        match.players.append(
            PlayerStat(match_id=match_id, username=name, side=1, damage=500, kills=1,
                       unit_tag=unit_tags.get(name, ""))
        )
    for name in side2:
        match.players.append(
            PlayerStat(match_id=match_id, username=name, side=2, damage=400, kills=1,
                       unit_tag=unit_tags.get(name, ""))
        )
    for name in spectators or []:
        match.players.append(
            PlayerStat(match_id=match_id, username=name, side=1, is_spectator=True)
        )
    return match


def grouped(result) -> set[frozenset[str]]:
    """Partition as an unordered pair of sets, so arbitrary A/B labelling doesn't matter."""
    out: dict[str, set[str]] = {TEAM_A: set(), TEAM_B: set()}
    for assignment in result.assignments.values():
        out[assignment.team].add(assignment.username)
    return {frozenset(out[TEAM_A]), frozenset(out[TEAM_B])}


def test_clean_side_swap_keeps_teams_together():
    """Sides swap between matches; the partition must not."""
    matches = [
        build("m1", ALPHA, BRAVO),
        build("m2", BRAVO, ALPHA),
        build("m3", ALPHA, BRAVO),
    ]
    result = infer_teams(matches)

    assert grouped(result) == {frozenset(ALPHA), frozenset(BRAVO)}
    # And each match's sides resolve to opposite teams.
    for match_id in ("m1", "m2", "m3"):
        mapping = result.match_side_team[match_id]
        assert set(mapping.values()) == {TEAM_A, TEAM_B}
    # The swap is reflected: side 1 flips team between m1 and m2.
    assert result.team_of("m1", 1) != result.team_of("m2", 1)


def test_substitute_is_pulled_to_the_side_they_played_with():
    """A one-off sub should land with the four teammates they shared a side with."""
    matches = [
        build("m1", ALPHA, BRAVO),
        build("m2", BRAVO, ALPHA),
        build("m3", BRAVO, ["Alice", "Bob", "Cid", "Zed"]),  # Zed subs for Dot, sides swapped
    ]
    result = infer_teams(matches)

    zed = result.assignments["Zed"]
    assert zed.team == result.assignments["Alice"].team
    assert zed.team != result.assignments["Eve"].team
    assert zed.match_count == 1
    assert zed.needs_review, "a single-match sub should be flagged for review"


def test_rotating_substitutes_across_many_matches():
    matches = [
        build("m1", ALPHA, BRAVO),
        build("m2", BRAVO, ["Alice", "Bob", "Cid", "Xan"]),
        build("m3", ["Alice", "Bob", "Yun", "Dot"], BRAVO),
        build("m4", ["Eve", "Fay", "Gus", "Zed"], ALPHA),
    ]
    result = infer_teams(matches)

    a_team = result.assignments["Alice"].team
    b_team = result.assignments["Eve"].team
    assert a_team != b_team
    for sub in ("Xan", "Yun"):
        assert result.assignments[sub].team == a_team
    assert result.assignments["Zed"].team == b_team


def test_core_players_are_high_confidence_and_not_flagged():
    matches = [
        build("m1", ALPHA, BRAVO),
        build("m2", BRAVO, ALPHA),
        build("m3", ALPHA, BRAVO),
    ]
    result = infer_teams(matches)

    for name in ALPHA + BRAVO:
        assignment = result.assignments[name]
        assert assignment.match_count == 3
        assert assignment.confidence == pytest.approx(1.0), name
        assert not assignment.needs_review, name


def test_pinned_override_anchors_inference():
    matches = [build("m1", ALPHA, BRAVO), build("m2", BRAVO, ALPHA)]
    result = infer_teams(matches, overrides={"Alice": TEAM_B}, pinned={"Alice"})

    assert result.assignments["Alice"].team == TEAM_B
    assert result.assignments["Alice"].source == "pinned"
    assert not result.assignments["Alice"].needs_review
    # Alice's actual teammates follow her to B; her opponents sit in A.
    assert result.assignments["Bob"].team == TEAM_B
    assert result.assignments["Eve"].team == TEAM_A


def test_unpinned_override_relabels_only_that_player():
    matches = [build("m1", ALPHA, BRAVO), build("m2", BRAVO, ALPHA)]
    baseline = infer_teams(matches)
    flipped = _other(baseline.assignments["Alice"].team)

    result = infer_teams(matches, overrides={"Alice": flipped})

    assert result.assignments["Alice"].team == flipped
    assert result.assignments["Alice"].source == "override"
    # Bob was not overridden, so he stays where the evidence put him.
    assert result.assignments["Bob"].team == baseline.assignments["Bob"].team


def test_single_match_warns_that_labels_are_arbitrary():
    result = infer_teams([build("m1", ALPHA, BRAVO)])

    assert grouped(result) == {frozenset(ALPHA), frozenset(BRAVO)}
    assert any("arbitrary" in w for w in result.warnings)
    for name in ALPHA:
        assert result.assignments[name].needs_review


def test_disjoint_match_groups_are_detected():
    matches = [
        build("m1", ALPHA, BRAVO),
        build("m2", ["Ren", "Sol", "Tam", "Ula"], ["Vex", "Wyn", "Xy", "Yor"]),
    ]
    result = infer_teams(matches)

    assert len(result.components) == 2
    assert any("no one in common" in w for w in result.warnings)


def test_contested_player_is_flagged():
    """Someone who genuinely plays for both teams must be surfaced, not silently placed."""
    matches = [
        build("m1", ALPHA, BRAVO),
        build("m2", ALPHA, BRAVO),
        build("m3", ["Alice", "Bob", "Cid", "Merc"], BRAVO),
        build("m4", ALPHA, ["Eve", "Fay", "Gus", "Merc"]),
    ]
    result = infer_teams(matches)

    assert result.assignments["Merc"].contested
    assert result.assignments["Merc"].needs_review


def test_spectators_are_excluded_entirely():
    matches = [
        build("m1", ALPHA, BRAVO, spectators=["Watcher"]),
        build("m2", BRAVO, ALPHA, spectators=["Watcher"]),
    ]
    result = infer_teams(matches)

    assert "Watcher" not in result.assignments


def test_empty_input_is_handled():
    result = infer_teams([])
    assert result.assignments == {}
    assert result.warnings


# ---------------------------------------------------------------- clan tag naming


def test_clan_tag_wins_on_clear_majority():
    tags = {"Alice": "EmP", "Bob": "EmP", "Cid": "EmP", "Dot": "XYZ"}
    matches = [build("m1", ALPHA, BRAVO, unit_tags=tags)]
    result = infer_teams(matches)

    assert infer_clan_tag(matches, result, TEAM_A) == "EmP"


def test_clan_tag_is_one_vote_per_player_not_per_match():
    """A player who dropped twice shouldn't out-vote two teammates who dropped once."""
    tags = {"Alice": "XYZ", "Bob": "EmP", "Cid": "EmP"}
    matches = [
        build("m1", ALPHA, BRAVO, unit_tags=tags),
        build("m2", BRAVO, ALPHA, unit_tags=tags),  # Alice's "XYZ" counted again here
    ]
    result = infer_teams(matches)

    # EmP (Bob+Cid, 2 distinct players) beats XYZ (Alice, 1 player x2 appearances = still 1 vote).
    assert infer_clan_tag(matches, result, TEAM_A) == "EmP"


def test_clan_tag_is_none_on_a_tie():
    """An even spread across tags falls back to a generic name, not an arbitrary pick."""
    tags = {"Alice": "EmP", "Bob": "EmP", "Cid": "XYZ", "Dot": "XYZ"}
    matches = [build("m1", ALPHA, BRAVO, unit_tags=tags)]
    result = infer_teams(matches)

    assert infer_clan_tag(matches, result, TEAM_A) is None


def test_clan_tag_is_none_with_no_tags_at_all():
    matches = [build("m1", ALPHA, BRAVO)]
    result = infer_teams(matches)

    assert infer_clan_tag(matches, result, TEAM_A) is None
    assert infer_clan_tag(matches, result, TEAM_B) is None


def test_clan_tag_requires_at_least_two_players():
    """One tagged player among four pickups isn't a team identity — it's a coincidence."""
    tags = {"Alice": "EmP"}
    matches = [build("m1", ALPHA, BRAVO, unit_tags=tags)]
    result = infer_teams(matches)

    assert infer_clan_tag(matches, result, TEAM_A) is None


def test_clan_tag_only_counts_players_on_that_team():
    tags = {"Alice": "EmP", "Bob": "EmP", "Eve": "EmP", "Fay": "EmP"}
    matches = [build("m1", ALPHA, BRAVO, unit_tags=tags)]
    result = infer_teams(matches)

    # Both teams happen to share the literal tag "EmP" here, but each team's count
    # is evaluated independently against its own roster.
    assert infer_clan_tag(matches, result, TEAM_A) == "EmP"
    assert infer_clan_tag(matches, result, TEAM_B) == "EmP"


def _other(team: str) -> str:
    return TEAM_B if team == TEAM_A else TEAM_A
