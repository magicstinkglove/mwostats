"""Phase 0 discovery: fetch real matches, save verbatim bodies, and report the response shape.

Usage:
    python scripts/probe_schema.py 88117337778826 [more_match_ids ...]

Writes each raw body to <cache_dir>/raw/<match_id>.json and prints a key-path report
(type, sample value, and presence across all sampled matches) so the normalizer can be
written against the real schema instead of guesses.
"""

from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.cache import RawCache  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.mwo_client import MWOApiError, MWOClient  # noqa: E402


def walk(node, prefix: str, out: dict) -> None:
    """Collect key paths -> observed types and a sample value.

    List elements collapse into a single `[]` path segment so a 24-player roster
    reports one schema, not twenty-four.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else key
            walk(value, path, out)
    elif isinstance(node, list):
        out.setdefault(prefix, {"types": set(), "sample": None, "count": 0})
        entry = out[prefix]
        entry["types"].add(f"list[{len(node)}]")
        entry["count"] += 1
        for item in node:
            walk(item, f"{prefix}[]", out)
    else:
        entry = out.setdefault(prefix, {"types": set(), "sample": None, "count": 0})
        entry["types"].add(type(node).__name__)
        entry["count"] += 1
        if entry["sample"] is None and node not in (None, ""):
            entry["sample"] = node


def main(match_ids: list[str]) -> int:
    settings = get_settings()
    settings.raw_dir.mkdir(parents=True, exist_ok=True)
    # Bypass the cache: this is a discovery run, we want a live response every time,
    # and it goes through the same auth-mode fallback the rest of the app uses.
    client = MWOClient(settings, cache=RawCache(settings))

    schemas: dict[str, dict] = {}
    present_in: dict[str, set] = defaultdict(set)
    fetched = 0

    for index, match_id in enumerate(match_ids):
        print(f"\nFetching match {match_id} ...")
        try:
            payload, _ = client.get_match(match_id, force_refresh=True)
        except MWOApiError as exc:
            print(f"  FAILED: {type(exc).__name__}: {exc}")
            continue

        # get_match() already wrote the raw body to the cache on its way back.
        print(f"  saved -> {client.cache.path_for(match_id)}")
        fetched += 1

        per_match: dict[str, dict] = {}
        walk(payload, "", per_match)
        for path, info in per_match.items():
            merged = schemas.setdefault(path, {"types": set(), "sample": None, "count": 0})
            merged["types"] |= info["types"]
            merged["count"] += info["count"]
            if merged["sample"] is None:
                merged["sample"] = info["sample"]
            present_in[path].add(match_id)

        if index < len(match_ids) - 1:
            time.sleep(settings.request_delay_seconds)

    if not fetched:
        print("\nNo matches fetched — nothing to report.")
        return 1

    print("\n" + "=" * 100)
    print(f"SCHEMA REPORT  ({fetched} match(es) sampled)")
    print("=" * 100)
    print(f"{'KEY PATH':<44} {'TYPE(S)':<18} {'IN ALL':<7} SAMPLE")
    print("-" * 100)
    for path in sorted(schemas):
        info = schemas[path]
        types = ",".join(sorted(info["types"]))
        everywhere = "yes" if len(present_in[path]) == fetched else f"{len(present_in[path])}/{fetched}"
        sample = str(info["sample"])
        if len(sample) > 30:
            sample = sample[:27] + "..."
        print(f"{path:<44} {types:<18} {everywhere:<7} {sample}")
    print("-" * 100)
    print(f"{len(schemas)} distinct key paths.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1:]))
