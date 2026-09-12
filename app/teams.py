"""Infer stable team identity across matches where sides swap and substitutes rotate in.

The API labels sides "1" and "2" per match, but those labels mean nothing across matches:
side 1 in match A and side 1 in match B can be entirely different groups. What *is* stable
is who plays alongside whom. So we build a signed co-occurrence graph — teammates pull
together, opponents push apart — and 2-colour it.

A full side swap produces no contradiction at all in that graph, because the graph never
looks at the numeric side. A substitute gets pulled to whichever team they shared a side
with. Players the evidence can't place confidently are flagged for manual review rather
than silently guessed.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .models import TEAM_A, TEAM_B, Match, TeamAssignment

MAX_REFINEMENT_PASSES = 10


@dataclass
class InferenceResult:
    assignments: dict[str, TeamAssignment] = field(default_factory=dict)
    # match_id -> {side_number: team_letter}
    match_side_team: dict[str, dict[int, str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    components: list[list[str]] = field(default_factory=list)

    def team_of(self, match_id: str, side: int) -> str | None:
        return self.match_side_team.get(match_id, {}).get(side)

    def roster(self, team: str) -> list[TeamAssignment]:
        members = [a for a in self.assignments.values() if a.team == team]
        return sorted(members, key=lambda a: (-a.match_count, a.username.lower()))


def _other(team: str) -> str:
    return TEAM_B if team == TEAM_A else TEAM_A


def _build_graph(matches: list[Match]) -> tuple[dict, dict, dict]:
    """Return (same, diff, match_counts).

    `same[u][v]` counts matches where u and v fought on the same side;
    `diff[u][v]` counts matches where they fought on opposite sides.
    """
    same: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    diff: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    match_counts: dict[str, int] = defaultdict(int)

    for match in matches:
        sides = match.sides()
        for players in sides.values():
            for name in players:
                match_counts[name] += 1

        side_keys = sorted(sides)
        for index, key in enumerate(side_keys):
            roster = sides[key]
            for i, u in enumerate(roster):
                for v in roster[i + 1 :]:
                    same[u][v] += 1
                    same[v][u] += 1
            for other_key in side_keys[index + 1 :]:
                for u in roster:
                    for v in sides[other_key]:
                        diff[u][v] += 1
                        diff[v][u] += 1

    return same, diff, match_counts


def _affinity(player: str, same: dict, diff: dict) -> dict[str, int]:
    """Net signed pull between `player` and everyone they've shared a match with."""
    scores: dict[str, int] = defaultdict(int)
    for other, weight in same.get(player, {}).items():
        scores[other] += weight
    for other, weight in diff.get(player, {}).items():
        scores[other] -= weight
    return scores


def _score_for(player: str, teams: dict[str, str], same: dict, diff: dict) -> float:
    """Positive = belongs on Team A, negative = Team B."""
    total = 0.0
    for other, pull in _affinity(player, same, diff).items():
        placed = teams.get(other)
        if placed == TEAM_A:
            total += pull
        elif placed == TEAM_B:
            total -= pull
    return total


def _evidence_weight(player: str, same: dict, diff: dict) -> int:
    return sum(same.get(player, {}).values()) + sum(diff.get(player, {}).values())


def _connected_components(players: list[str], same: dict, diff: dict) -> list[list[str]]:
    """Groups of players linked by any shared match. Separate groups can't be compared."""
    seen: set[str] = set()
    components: list[list[str]] = []
    for start in players:
        if start in seen:
            continue
        stack, group = [start], []
        seen.add(start)
        while stack:
            node = stack.pop()
            group.append(node)
            neighbours = set(same.get(node, {})) | set(diff.get(node, {}))
            for neighbour in neighbours:
                if neighbour not in seen:
                    seen.add(neighbour)
                    stack.append(neighbour)
        components.append(sorted(group))
    return components


def infer_teams(
    matches: list[Match],
    overrides: dict[str, str] | None = None,
    pinned: set[str] | None = None,
) -> InferenceResult:
    """Partition every player across `matches` into Team A / Team B.

    `overrides` maps username -> team letter (user corrections). `pinned` marks overrides
    that must also anchor the inference rather than merely relabel the result.
    """
    overrides = dict(overrides or {})
    pinned = set(pinned or set())
    result = InferenceResult()

    if not matches:
        result.warnings.append("No matches to analyse.")
        return result

    same, diff, match_counts = _build_graph(matches)
    players = sorted(match_counts)
    if not players:
        result.warnings.append("No non-spectator players found in these matches.")
        return result

    teams: dict[str, str] = {}

    # 1. Pinned overrides anchor everything else.
    for name in pinned:
        if name in match_counts and overrides.get(name) in (TEAM_A, TEAM_B):
            teams[name] = overrides[name]

    # 2. Seed from the strongest "definitely opponents" edge.
    if not teams:
        best_pair, best_weight = None, 0
        for u, opponents in diff.items():
            for v, weight in opponents.items():
                if weight > best_weight:
                    best_pair, best_weight = (u, v), weight
        if best_pair:
            teams[best_pair[0]] = TEAM_A
            teams[best_pair[1]] = TEAM_B
        else:
            # Single side, or nobody ever faced anybody — fall back to the first match.
            first_sides = matches[0].sides()
            for index, key in enumerate(sorted(first_sides)):
                for name in first_sides[key]:
                    teams[name] = TEAM_A if index == 0 else TEAM_B
            result.warnings.append(
                "No opposing-side evidence found; team labels are arbitrary."
            )

    # 3. Greedy placement, strongest evidence first so anchors land before stragglers.
    remaining = [p for p in players if p not in teams]
    remaining.sort(key=lambda p: -_evidence_weight(p, same, diff))
    for player in remaining:
        score = _score_for(player, teams, same, diff)
        if score == 0:
            # No signal yet; defer by placing opposite the largest current team to
            # keep sides balanced, then let refinement correct it.
            a_count = sum(1 for t in teams.values() if t == TEAM_A)
            b_count = len(teams) - a_count
            teams[player] = TEAM_B if a_count > b_count else TEAM_A
        else:
            teams[player] = TEAM_A if score > 0 else TEAM_B

    # 4. Refinement sweeps — flip anyone whose placement disagrees with the settled graph.
    movable = [p for p in players if p not in pinned]
    for _ in range(MAX_REFINEMENT_PASSES):
        changed = False
        for player in movable:
            score = _score_for(player, teams, same, diff)
            want = TEAM_A if score > 0 else TEAM_B if score < 0 else teams[player]
            if want != teams[player]:
                teams[player] = want
                changed = True
        if not changed:
            break

    # 5. Non-pinned overrides are applied last: relabel without steering the inference.
    for name, team in overrides.items():
        if name in teams and team in (TEAM_A, TEAM_B):
            teams[name] = team

    # 6. Resolve each match's sides to teams via roster majority — this absorbs swaps.
    for match in matches:
        sides = match.sides()
        mapping: dict[int, str] = {}
        tallies: dict[int, int] = {}
        for side, roster in sides.items():
            a = sum(1 for name in roster if teams.get(name) == TEAM_A)
            b = sum(1 for name in roster if teams.get(name) == TEAM_B)
            tallies[side] = a - b
        ordered = sorted(tallies, key=lambda s: -tallies[s])
        if len(ordered) >= 2:
            mapping[ordered[0]] = TEAM_A
            mapping[ordered[1]] = TEAM_B
            for leftover in ordered[2:]:
                mapping[leftover] = TEAM_A if tallies[leftover] > 0 else TEAM_B
            if tallies[ordered[0]] == tallies[ordered[1]]:
                result.warnings.append(
                    f"Match {match.match_id}: sides are evenly split between teams; "
                    "side-to-team mapping is a guess."
                )
        elif ordered:
            only = ordered[0]
            mapping[only] = TEAM_A if tallies[only] >= 0 else TEAM_B
        result.match_side_team[match.match_id] = mapping

    # 7. A player who shows up on both teams' sides across the series is contested.
    appeared: dict[str, set[str]] = defaultdict(set)
    for match in matches:
        mapping = result.match_side_team.get(match.match_id, {})
        for player in match.active_players():
            team = mapping.get(player.side)
            if team:
                appeared[player.username].add(team)

    # 8. Score confidence and assemble.
    for player in players:
        weight = _evidence_weight(player, same, diff)
        raw = _score_for(player, teams, same, diff)
        confidence = min(abs(raw) / weight, 1.0) if weight else 0.0
        if player in pinned:
            source = "pinned"
        elif player in overrides:
            source = "override"
        else:
            source = "inferred"
        result.assignments[player] = TeamAssignment(
            username=player,
            team=teams[player],
            confidence=round(confidence, 3),
            match_count=match_counts[player],
            source=source,
            contested=len(appeared.get(player, set())) > 1,
        )

    # 9. Disconnected groups can't be oriented relative to each other.
    result.components = _connected_components(players, same, diff)
    if len(result.components) > 1:
        sizes = ", ".join(str(len(c)) for c in result.components)
        result.warnings.append(
            f"These matches form {len(result.components)} groups of players with no one "
            f"in common (sizes: {sizes}). Team labels across groups are arbitrary — "
            "check the rosters and correct them if needed."
        )

    if len(matches) == 1:
        result.warnings.append(
            "Only one match in this series, so which side is 'Team A' is arbitrary. "
            "Rename the teams or add more matches."
        )

    return result


# A unit tag shared by just one player isn't a "team identity" — it's a coincidence.
# Two is the minimum for "most of this team is the same clan" to mean anything.
MIN_TAG_SUPPORT = 2


def infer_clan_tag(matches: list[Match], inference: InferenceResult, team: str) -> str | None:
    """The unit tag most of `team`'s roster shares, or None if there isn't one.

    One vote per player, not per match-appearance — a player who dropped in 5 matches
    shouldn't outweigh 4 teammates who dropped once each. Ties (an "even spread" across
    tags, including no tag having a majority) return None so the caller falls back to a
    generic name rather than picking an arbitrary winner.
    """
    player_tag: dict[str, str] = {}
    for match in matches:
        for player in match.active_players():
            if player.username not in player_tag and player.unit_tag.strip():
                player_tag[player.username] = player.unit_tag.strip()

    team_tags = [
        tag
        for username, tag in player_tag.items()
        if (assignment := inference.assignments.get(username)) and assignment.team == team
    ]
    if not team_tags:
        return None

    counts = Counter(team_tags)
    top_count = max(counts.values())
    leaders = [tag for tag, count in counts.items() if count == top_count]
    if len(leaders) != 1 or top_count < MIN_TAG_SUPPORT:
        return None
    return leaders[0]
