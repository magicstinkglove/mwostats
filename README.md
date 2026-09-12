# MWO Match Stats

See who actually carried your scrim night. This tool pulls your MechWarrior Online match
stats and adds them up **by team** — even when players swap sides between games or someone
subs in for a match or two, it figures out who's really on which team.

Runs entirely on your own computer. Nothing gets uploaded, and nobody but you can see your data.

No command line needed — one launcher file installs everything and starts the app when you
double-click it. First time takes about 10 minutes (mostly installing Python); every time
after that takes about 10 seconds.

Jump to: **[Windows setup](#windows-setup)** · **[macOS setup](#macos-setup)** ·
**[Using the app](#using-the-app)** · **[Troubleshooting](#troubleshooting)**

---

## Windows setup

### 1. Install Python

1. Go to **[python.org/downloads](https://www.python.org/downloads/)** and click **Download Python**.
2. Run the downloaded installer. If Windows shows "Windows protected your PC," click
   **More info → Run anyway** — that's normal for anything downloaded from the internet.
3. **Important:** on the installer's first screen, check the box **"Add python.exe to PATH"**
   before clicking anything else. This is the step people miss, and it breaks everything later.
4. Click **Install Now**, then **Close**.

### 2. Download this project

1. On the GitHub page, click **`<> Code` → Download ZIP**.
2. Right-click the downloaded ZIP → **Extract All** → **Extract**.
3. Open the extracted folder. If it just contains another folder with the same name, open
   that one too — you want the folder that directly contains `start.bat`, `app`, and `web`.

### 3. Double-click `start.bat`

A window pops up, installs what the app needs (first run only), and starts the app —
your browser opens automatically. **Leave that window open** while using the app; closing it
stops the app. To use the app again later, just double-click `start.bat` again.

If Windows asks about the firewall, click **Allow access** — that's it asking permission to
talk to your own browser, nothing goes out to the internet except match data.

Anything go wrong? See **[Troubleshooting](#troubleshooting)**.

---

## macOS setup

### 1. Install Python

1. Go to **[python.org/downloads](https://www.python.org/downloads/)** and click **Download Python**.
2. Run the downloaded `.pkg` installer: **Continue → Continue → Agree → Install** (it may ask
   for your Mac password), then **Close**.

### 2. Download this project

1. On the GitHub page, click **`<> Code` → Download ZIP**.
2. Safari usually unzips it automatically; Chrome/Firefox leave a `.zip` to double-click.
3. Open the extracted folder. If it just contains another folder with the same name, open
   that one too — you want the folder that directly contains `start.command`, `app`, and `web`.

### 3. Double-click `start.command`

The first time, macOS will refuse with **"cannot be opened because it is from an unidentified
developer."** This is normal for any downloaded script. To get past it once:

1. **Right-click** `start.command` → **Open**.
2. Click **Open** again in the dialog that appears.

After that, a plain double-click works. A Terminal window pops up, installs what the app
needs (first run only), and starts the app — your browser opens automatically. **Leave that
window open** while using the app; closing it stops the app. To use the app again later, just
double-click `start.command` again.

Anything go wrong? See **[Troubleshooting](#troubleshooting)**.

---

## Add your MWO API token

This lets the app read your match data from MWO's website.

1. Log into MWO, go to **[mwomercs.com/profile/api](https://mwomercs.com/profile/api)**, and
   generate/copy your API token.
2. In the app, click the **⚙ gear icon** (top right), paste the token in, and click **Save**.

The token is saved locally in the app's own database — not sent anywhere except mwomercs.com
when fetching your matches — and remembered next time you start the app. **Keep it private**:
anyone with it can pull your match data.

<details>
<summary>Prefer the command line? Click here for the manual version.</summary>

**Windows** (in the project folder, `cmd`):
```
pip install -r requirements.txt
uvicorn app.main:app --reload
```

**macOS** (Terminal, `cd` into the project folder):
```
pip3 install -r requirements.txt
python3 -m uvicorn app.main:app --reload
```

Once you see `Application startup complete`, open `http://localhost:8000`.

</details>

---

## Using the app

1. **Get a Game ID from a private match, not Quick Play.** After a match ends, the end-round
   screen shows a Game ID. Only private/custom lobby matches (scrims, league nights) work —
   this is a limitation of MWO's own API.
2. **Paste Game IDs** into the "Matches" box (one per line or comma-separated) and click
   **Add matches**.
3. **Check the Teams panel.** The app infers teams from who played alongside whom, even
   across side swaps and substitutes. Anything it's unsure about gets a yellow warning and a
   dropdown to fix it.
4. **Name your teams** by clicking the team name at the top of each roster — auto-named from
   a shared unit tag when one exists.
5. **Use the tabs:** **Summary** (both teams compared), your two **team tabs** (that team's
   own numbers), and **Matches** (full scoreboard per game).
6. **Click a player's name** for a drill-down modal — their match history, trend, and mechs.
   If they're tracked on [The Jarl's List](https://leaderboard.isengrim.org), their overall
   (lifetime) rank, percentile, K/D, and weight-class tendency appear too, with a link to
   their full profile. Not every player is tracked there — when that's the case, the section
   just doesn't appear.

You can keep multiple **series** (named groups of matches) — switch between them from the
top-right switcher, or start a new one with **+ New series**.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| (Win) Black window flashes and closes immediately | Right-click `start.bat` → **Edit**, or run it from a `cmd` window instead of double-clicking, so the error stays on screen. |
| (Mac) "cannot be opened because it is from an unidentified developer" | One-time: right-click `start.command` → **Open** → **Open**. Normal double-click works after. |
| (Mac) Double-click opens it in a text editor instead of running | In Terminal: `chmod +x ` then drag `start.command` in and press Enter. Try again. |
| "Python isn't found" even though you installed it | **Win:** the "Add python.exe to PATH" box wasn't checked — reinstall and check it. **Mac:** re-run the `.pkg` installer to completion. |
| (Win) Typing a `python` command opens the Microsoft Store | Python isn't actually installed — install it from python.org, not the Store. |
| Wall of red/pink text during setup, or a network error | The dependency install failed — check your internet connection; a work/school firewall can block it. |
| Antivirus / Gatekeeper flagged the project | False positive — downloaded ZIPs of code trigger this often. Allow/restore the file, or see the "unidentified developer" fix above. |
| Browser didn't open by itself | Open one and go to `http://localhost:8000` manually. |
| "Can't reach this page" / connection refused | The launcher window (black/Terminal) got closed — reopen it by double-clicking the launcher again. |
| Matches won't fetch / "no API token configured" | Add your token via the **⚙** icon — see [above](#add-your-mwo-api-token). If already set, re-paste it (a copy can pick up a stray space). |
| A match won't load / "not returned by the API" | It's almost certainly a Quick Play match — only private/custom lobby matches work. Double-check the Game ID's source. |
| "Address already in use" | The app is already running in another window — close it, or add `--port 8001` to the manual `uvicorn` command and use that port instead. |
| Closed the launcher window, site stopped working | Expected — double-click the launcher again. Nothing you entered is lost. |
| None of the above | Note the exact error text and which step you were on — that's what actually helps track it down. |

---
<br>

<details>
<summary><strong>Technical reference</strong> (for anyone who wants to read or extend the code)</summary>

### Team identification

MWO's API labels sides `1`/`2` per match — meaningless across matches. What's stable is who
plays alongside whom, so `app/teams.py` builds a **signed co-occurrence graph** (same side =
positive edge, opposite side = negative edge) and 2-colors it:

1. Seed from the strongest "definitely opponents" edge.
2. Place remaining players greedily, strongest evidence first.
3. Sweep repeatedly, flipping anyone who disagrees with the settled graph.
4. Resolve each match's sides to teams by roster majority.

A full side swap produces no contradiction (the graph ignores numeric side); a substitute is
pulled toward whoever they shared a side with. Thin-evidence placements (one appearance,
genuinely conflicting sides) are flagged in the UI instead of silently guessed.

UI corrections are **pinned** — they anchor inference rather than just relabeling the result.
Edge cases handled explicitly: single-match series (arbitrary labels, flagged), disjoint
match groups with no shared players, and a mercenary who played both sides (flagged `both sides`).

### Auto-naming from unit tags

If most of a team shares a unit tag (e.g. `[V1LE]`), the team is named after it —
`infer_clan_tag()` votes once per *player*, not per appearance, so no one player's five drops
outweighs four teammates' one drop each. Ties, no tags, or a lone tagged pickup fall back to
"Team A"/"Team B". Once you rename a team yourself, auto-naming never overwrites it again.

### API token storage

Token comes from `.env` (`MWO_API_TOKEN`) or the in-app ⚙ Settings panel (saved to the
`app_settings` table). The database value wins when set; every request resolves it fresh, so
a new token takes effect with no restart. Clearing it reverts to `.env`, if any. Never echoed
back over the API — always masked to the last 4 characters (`service.mask_token`).

### Jarl's List enrichment

The player modal enriches itself with lifetime career stats from
[The Jarl's List](https://leaderboard.isengrim.org), a community-run public API.
`app/jarls_client.py` calls one endpoint:

```
GET /api/usernames/{name}   lifetime "Overall" record — same numbers the site's own
                            search page leads with
```

A player without enough games for a lifetime rank (or a retired one) gets `Rank: 0,
Percentile: null` back; `service._build_jarls_profile()` turns that into `has_rank: false` so
the UI shows real numbers (games, K/D, weight class) without inventing a rank. This
intentionally isn't filtered to the current season — an inactive account's most-recent season
can be a year+ stale, so only the lifetime figure is shown.

Cached in the `jarls_cache` table for `JARLS_CACHE_TTL_HOURS` (12h), including negative
results, since there's no documented rate limit and repeat lookups are common. The route
handler explicitly commits after the cache write — a real bug during development had this
write living only in the request's own transaction, silently defeating the cache every time;
`test_jarls_cache_persists_across_separate_requests` guards it with two genuinely separate
HTTP requests, since a same-connection test fixture can't catch this class of bug.

Best-effort throughout: any failure (unknown pilot, site down, timeout) collapses to
`None`/`{"found": false}`, and the frontend fetches it *after* the modal's own data has
rendered, so it can never block or break the rest of the modal. Only weight-class tendency is
available here (not specific chassis) — chassis-level detail comes from your own loaded
matches via MWO's own API.

### Summary vs. team-scoped views

Tabs, not one long scroll: **Summary** (both teams), one tab per team, and **Matches** (every
game's box score). `SeriesContext` carries an optional `team_filter`; most modules just loop
`for team in ctx.teams` or build off `ctx.lines()`, both scope-aware automatically. A module
needs its own scoped logic only when it has a hardcoded two-team layout to collapse (see
`breakdowns.py`/`leaderboards.py`: branch on `ctx.is_scoped`). Things like "kills scored
against this team" deliberately read `ctx.matches` directly so the real opponent stays correct
even on a single team's page.

A module opts out of team pages with `tabs = ("matches",)` (e.g. `match_results` — a box score
is inherently both teams). Everything else defaults to `("summary", "team")`.

### The MWO API

`GET https://mwomercs.com/api/v1/matches/<game-id>?api_token=<token>` — private-match data
only. Public Quick Play is rejected with the same generic `422` as a malformed ID; a bad
token returns `401`. Auth is via the `api_token` query param, not a header.

Confirmed response shape:

```jsonc
{
  "MatchDetails": {
    "Map": "ForestColony", "GameMode": "Assault", "MatchTimeMinutes": "15",
    "WinningTeam": "2", "Team1Score": 0, "Team2Score": 1, "CompleteTime": "2017-07-14T18:09:54+00:00"
  },
  "UserDetails": [
    {
      "Username": "...", "IsSpectator": false, "Team": "2", "MechName": "hbr-fc",
      "Kills": 0, "Assists": 0, "MatchScore": 28, "Damage": 0, "UnitTag": "_2ez"
    }
  ]
}
```

`app/normalize.py` maps the fields the app uses into typed columns; everything else is
preserved verbatim in `extra_json` so a metric module can use it without a schema migration.

`python scripts/probe_schema.py <GAME_ID>` fetches a real match, saves the raw body to
`data/raw/`, and prints every key path with its type — useful before building a metric around
a new field.

### See it working without a real Game ID

```
python scripts/seed_demo.py          # builds a DEMO series from synthetic matches
python scripts/seed_demo.py --clear  # removes it
```

Five matches with sides swapping and substitutes rotating in, loaded through the normal
ingest path. No network, IDs namespaced `DEMO-*`.

### Adding a metric module

One file, no frontend/route/registry changes:

```python
from .base import SeriesContext, stats_section, mean
from .registry import register

@register
class MyMetric:
    id = "my_metric"
    name = "My Metric"
    description = "What it shows."
    order = 50

    def compute(self, ctx: SeriesContext) -> dict:
        by_team = ctx.stats_by_team()
        return {"sections": [
            stats_section("Damage", [
                {"label": ctx.team_name(team), "group": team, "stats": [
                    {"label": "Avg", "value": f"{mean([s.damage for s in lines]):,.1f}"},
                ]}
                for team, lines in by_team.items()
            ])
        ]}
```

Restart and the card appears on Summary and each team tab automatically. `SeriesContext`:

| | |
|---|---|
| `ctx.matches` | `Match` objects, chronological |
| `ctx.teams` | `(TEAM_A, TEAM_B)`, or just the one when scoped |
| `ctx.is_scoped` | `True` on a team's own page |
| `ctx.lines()` | every non-spectator player line + team, scope-aware |
| `ctx.filtered_active_players(match)` | one match's roster, scope-aware |
| `ctx.stats_by_team()` / `ctx.stats_by_player()` | pre-bucketed stats, scope-aware |
| `ctx.team_for(match_id, username)` | team in a specific match (respects overrides) |
| `ctx.team_name(team)` / `ctx.match_winner(match)` / `ctx.team_record()` | always the real opponent, regardless of scope |

Section builders in `app/metrics/base.py`: `stats_section`, `table_section`, `bar_section`,
`line_section`, `note_section` — tables sort on click, line charts skip unplayed matches for
free. Shipped modules: `core_aggregates`, `leaderboards`, `match_results`, `player_detail`,
`breakdowns`.

### Layout

```
start.bat          Windows launcher: installs deps, runs uvicorn, opens browser
start.command      macOS equivalent
app/
  main.py          FastAPI app; serves the API and web/ from one process
  config.py        config.json + MWO_API_TOKEN from .env (fallback default)
  db.py            SQLite schema and queries, incl. api_token override
  mwo_client.py    HTTP client: auth-mode fallback, throttling, typed errors
  jarls_client.py  client for the third-party Jarl's List career-stats API
  cache.py         raw JSON on disk — completed matches cached forever
  normalize.py     raw API body -> Match / PlayerStat
  teams.py         co-occurrence inference          <- the core logic
  service.py       ingest, context assembly, token resolution, Jarl's List caching
  metrics/         auto-discovered metric modules
  routes/          matches, series, metrics, settings, players
web/               index.html + app.js + modules.js + style.css (no build step)
scripts/           probe_schema.py, seed_demo.py
tests/             114 tests
```

### Caching

A completed match is immutable and never re-fetched — raw body in `data/raw/<id>.json`,
normalized rows in `data/mwo.db`. Re-adding a stored match reports `stored`, no network call.
Tick *Re-fetch even if cached* to force one. Batch ingest is partial-success: one bad ID
reports its own error, the rest still load.

### API

```
POST   /api/matches                            {match_ids, force_refresh}
GET    /api/matches            /api/matches/{id}
POST   /api/series                             {name, match_ids}
GET    /api/series             /api/series/{id}
DELETE /api/series/{id}
POST   /api/series/{id}/matches                {match_ids, force_refresh}
DELETE /api/series/{id}/matches/{match_id}
PUT    /api/series/{id}/teams                  {team_a_name, team_b_name}
PUT    /api/series/{id}/assignments            {username, team, match_id?}
GET    /api/metrics/modules
GET    /api/series/{id}/metrics/{module_id}    ?team=A|B for that team's own page
GET    /api/series/{id}/players/{username}
GET    /api/players/{username}/jarls           career stats from The Jarl's List, cached 12h
GET    /api/settings/token                     {configured, source: env|database|none, masked}
PUT    /api/settings/token                     {token}
DELETE /api/settings/token                     reverts to .env, if any
GET    /api/health
```

Interactive docs at `http://localhost:8000/docs`.

### Tests

```
python -m pytest -q
```

114 tests: inference (clean swaps, rotating subs, pinned overrides, contested players,
disjoint groups), clan-tag auto-naming, normalization of partial/malformed payloads, metric
values on summary and team-scoped views, the HTTP layer with the network mocked, token
resolution/masking, Jarl's List caching (incl. the per-request-commit regression test), and a
concurrency test (SQLite needs `check_same_thread=False` or concurrent requests 500 — exactly
what the dashboard sends on load).

</details>
