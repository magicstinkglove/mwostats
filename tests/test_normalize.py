import pytest

from app.normalize import NormalizeError, normalize_match
from tests.sample_api import api_payload


def test_maps_confirmed_fields():
    payload = api_payload(["Alice", "Bob"], ["Eve", "Fay"], winner=2)
    match = normalize_match(payload, "m1")

    assert match.match_id == "m1"
    assert match.map_name == "Frozen City"
    assert match.game_mode == "Skirmish"
    assert match.duration_minutes == 12
    assert match.winning_side == 2
    assert match.completed_at == "2026-09-01T20:00:00Z"
    assert len(match.players) == 4

    alice = next(p for p in match.players if p.username == "Alice")
    assert alice.side == 1
    assert alice.damage == 300
    assert alice.mech_name == "TBR-PRIME"


def test_sides_split_correctly():
    match = normalize_match(api_payload(["Alice", "Bob"], ["Eve"]), "m1")
    sides = match.sides()

    assert sorted(sides[1]) == ["Alice", "Bob"]
    assert sides[2] == ["Eve"]


def test_spectators_flagged_and_excluded_from_active():
    payload = api_payload(["Alice"], ["Eve"], spectators=["Watcher"])
    match = normalize_match(payload, "m1")

    assert len(match.players) == 3
    assert len(match.active_players()) == 2
    assert next(p for p in match.players if p.username == "Watcher").is_spectator


def test_unknown_fields_are_preserved_in_extra():
    """The live schema isn't fully known, so nothing may be silently dropped."""
    payload = api_payload(
        ["Alice"], ["Eve"], extra_user_fields={"ComponentsDestroyed": 7, "SkillTier": 5}
    )
    payload["MatchDetails"]["Region"] = "NA"
    match = normalize_match(payload, "m1")

    alice = next(p for p in match.players if p.username == "Alice")
    assert alice.extra["ComponentsDestroyed"] == 7
    assert alice.extra["SkillTier"] == 5
    assert match.extra["Region"] == "NA"


def test_unit_tag_is_mapped_to_a_typed_field():
    payload = api_payload(["Alice"], ["Eve"], unit_tags={"Alice": "EmP"})
    match = normalize_match(payload, "m1")

    alice = next(p for p in match.players if p.username == "Alice")
    eve = next(p for p in match.players if p.username == "Eve")
    assert alice.unit_tag == "EmP"
    assert eve.unit_tag == ""
    # It's a real field now, not an unknown one left over in extra.
    assert "UnitTag" not in alice.extra


def test_letter_sides_are_tolerated():
    payload = api_payload(["Alice"], ["Eve"])
    payload["UserDetails"][0]["Team"] = "A"
    payload["UserDetails"][1]["Team"] = "B"
    match = normalize_match(payload, "m1")

    assert {p.username: p.side for p in match.players} == {"Alice": 1, "Eve": 2}


def test_missing_numbers_default_instead_of_crashing():
    payload = api_payload(["Alice"], ["Eve"])
    del payload["UserDetails"][0]["Damage"]
    payload["UserDetails"][0]["Kills"] = ""
    match = normalize_match(payload, "m1")

    alice = next(p for p in match.players if p.username == "Alice")
    assert alice.damage == 0.0
    assert alice.kills == 0


def test_chassis_derived_from_variant():
    match = normalize_match(api_payload(["Alice"], ["Eve"]), "m1")
    assert match.players[0].chassis == "TBR"


@pytest.mark.parametrize(
    "payload, message",
    [
        ({}, "MatchDetails"),
        ({"MatchDetails": {}}, "UserDetails"),
        ({"MatchDetails": {}, "UserDetails": []}, "No usable player records"),
    ],
)
def test_bad_payloads_raise_clear_errors(payload, message):
    with pytest.raises(NormalizeError) as info:
        normalize_match(payload, "m1")
    assert message in str(info.value)
