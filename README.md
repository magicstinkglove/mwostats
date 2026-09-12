# MWO Match Stats

See who actually carried your scrim night. This tool pulls your MechWarrior Online match
stats and adds them up **by team**, even when your team's players swap sides between games
or someone subs in for a match or two — it figures out who's really on which team.

You run it on your own computer. Nothing gets uploaded anywhere, and nobody but you can see
your data.

This guide assumes you've never written code before, never used a command line, and don't
know what half these words mean. That's fine — you won't need a command line for this.
Follow the steps **in order** and don't skip anything.

---

## Read this before you start

- **There are only four steps**, and only Step 1 involves anything resembling "computer
  stuff." The rest is double-clicking things.
- **No typing commands, no terminal.** A file called `start.bat` does everything for you —
  installing what the app needs and launching it — when you double-click it.
- **After every step, there's a "✅ You'll know it worked when" line.** Check it before moving
  on. If your screen doesn't match it, jump to **[Troubleshooting](#troubleshooting)** at the
  bottom and find the message closest to what you're seeing.
- **You cannot break your computer by doing this.** Worst case, you delete the folder and
  start over from Step 2.

---

## What you'll need

- A Windows computer (see the note at the very bottom if you're on a Mac)
- About 10 minutes the first time; about 10 *seconds* every time after that
- Your MWO API token (Step 4 below tells you exactly how to get one — you don't need it yet)

---

## Step 1 — Install Python

This app needs something called Python to run. Your computer almost certainly doesn't have
it yet — that's normal, it's not something Windows comes with.

1. Go to **[python.org/downloads](https://www.python.org/downloads/)** and click the big
   yellow "Download Python" button.
2. Once it's downloaded, double-click the file to run it. It'll be named something like
   `python-3.xx.x-amd64.exe` in your Downloads folder.
3. Windows may show a blue screen that says **"Windows protected your PC."** This is normal
   for anything downloaded from the internet, not a sign of a virus — click **"More info"**,
   then **"Run anyway."**
4. **This is the step people miss most often, and it breaks everything later if you skip it:**
   on the very first screen of the installer, at the bottom, there's a checkbox that says
   **"Add python.exe to PATH"** (sometimes "Add Python to PATH"). **Check that box** before
   clicking anything else.
5. Click **"Install Now"** and let it finish, then click **Close**.

✅ **You'll know it worked when:** the installer says the install was successful. That's it
for this step — Step 3 will confirm it actually worked.

## Step 2 — Download this project

If someone sent you a link to this project on GitHub:

1. Click the green **`<> Code`** button near the top of the page.
2. Click **Download ZIP**.
3. Find the downloaded file (usually in your **Downloads** folder — it'll be named something
   like `mwostats-main.zip`).
4. Right-click that ZIP file and choose **Extract All...**, then click **Extract**.

You should now have a folder with a name like `mwostats-main`. Open it and look inside.

⚠️ **If the only thing inside is *another* folder with almost the same name** (e.g. you open
`mwostats-main` and find `mwostats-main` again inside it), open that inner one too — that's
the real project folder.

✅ **You'll know it worked when:** the folder you're looking at directly contains a file
called **`start.bat`**, sitting right next to folders named `app` and `web`.

## Step 3 — Double-click `start.bat`

That's the whole step. Find the file named **`start.bat`** in that folder and double-click it.

A black window will pop up and do everything for you — checking Python is installed
correctly, installing what the app needs (only the first time; instant every time after), and
starting the app. After a few seconds, **your browser will open by itself** to the app.

✅ **You'll know it worked when:** a dark-themed page titled "MWO Match Stats" opens in your
browser automatically, with a message near the top saying no API token is configured yet —
that's expected, Step 4 fixes it. **Leave the black window open** while you're using the app;
closing it stops the app. Minimize it if it's in the way.

❌ **If a window flashes and disappears instead** — that means something went wrong before it
could even show you the message. See **[Troubleshooting](#troubleshooting)**.

❌ **If the black window opens but shows a message about Python not being found** — it'll open
the Python download page for you automatically. Go do Step 1 again, making extra sure to
check the "Add python.exe to PATH" box, then double-click `start.bat` again.

❌ **If Windows pops up a firewall box** asking whether to allow Python through the firewall —
click **"Allow access."** This is Windows asking permission for the app to talk to your own
browser on your own computer; nothing goes out to the internet except the match data it fetches.

**To use the app again later** (tomorrow, next week, whenever): just double-click `start.bat`
again. That's the only step you ever repeat — Steps 1 and 2 are one-time setup.

## Step 4 — Add your MWO API token

This is a password-like code that lets the app read your match data from MWO's website.

1. Log into your MWO account, then go to
   **[mwomercs.com/profile/api](https://mwomercs.com/profile/api)** and generate/copy your
   token from there. It'll be a long jumble of letters and numbers.
2. Back in the app (the browser tab that opened in Step 3), click the **⚙ gear icon** in the
   top-right corner.
3. Click into the box, paste the token in, and click **Save**.

✅ **You'll know it worked when:** the box changes to say "Using a token saved in this app,"
showing the last few characters of your token.

That's it — no files to find or edit. The token lives in the app's own local database on your
computer (not anywhere online, and not sent anywhere except to mwomercs.com when fetching
your matches), and it's remembered the next time you start the app — you only do this once.

**Keep this token private** — anyone who has it can pull your match data. Don't post it
anywhere, don't paste it into a chat with anyone, and never put it in a file you upload to
GitHub.

<details>
<summary>Prefer typing commands yourself, or <code>start.bat</code> isn't working? Click here for the manual version.</summary>

Open a command window in the project folder (click the address bar in File Explorer, type
`cmd`, press Enter), then run these two commands, each followed by Enter:

```
pip install -r requirements.txt
```

```
uvicorn app.main:app --reload
```

Once you see `Application startup complete`, open your browser to `http://localhost:8000`
yourself. This is exactly what `start.bat` automates — useful if you want to see error output
directly, or if something about your setup makes the automatic version misbehave.

</details>

---

## Using the app

1. **Get a Game ID — from a private match, not Quick Play.** After a match finishes, the
   end-round screen shows a Game ID. **This only works for private/custom lobby matches**
   (the kind you'd use for a scrim or league night) — **public Quick Play matches will not
   work**, no matter how correctly you copy the ID. This is a limitation of MWO's API
   itself, not something this app can work around.
2. **Paste in your Game IDs.** In the "Matches" box at the top, paste in one or more Game
   IDs (one per line, or separated by commas) and click **Add matches**. Do this for every
   match from the scrim night you want to look at.
3. **Check the Teams panel.** The app guesses who's on which team by looking at who played
   alongside whom — it works even if your team's players swapped sides or a sub jumped in
   for a match. If anyone looks wrong (there's a yellow warning box for anyone it wasn't
   sure about), use the dropdown next to their name to fix it.
4. **Name your teams.** Click the team name at the top of each roster box to rename it from
   "Team A" / "Team B" to whatever you actually call them. If most of a team shares the same
   in-game unit tag, the app names it after that automatically (you can still overwrite it).
5. **Use the tabs to explore.** Right under the header:
   - **Summary** — team-vs-team comparisons: totals, leaderboards across everyone, mech and
     map breakdowns with both teams side by side.
   - **Your two team tabs** (named after each team) — that team's own numbers only: its own
     leaderboard, its own best performer per match, its own damage trend chart, its own mech
     and map usage.
   - **Matches** — the full scoreboard for every game, one after another, in order.
6. **Click any player's name** (in the Teams panel or a leaderboard) for a drill-down modal —
   their per-match history, trend, and mechs piloted.

You can keep more than one **series** (a named group of matches) — click the switcher in the
top-right to see all of them, click one to switch, or click its **×** to delete it. **+ New
series** starts a fresh one; handy for keeping separate scrim nights apart.

---

## Troubleshooting

Find the message closest to what's actually on your screen. If none of these match exactly,
scroll to the very bottom of this list anyway — the last entry covers what to do when nothing
else fits.

**The black window flashes and disappears immediately**
It hit an error before it could print anything readable. Instead of double-clicking
`start.bat`, right-click it and choose **"Edit"** (or open a black window yourself — address
bar, type `cmd`, Enter — then drag `start.bat` into that window and press Enter). Either way
the window stays open and you can read the actual error, which is usually one of the entries
below.

**It says Python isn't installed, but you're sure you installed it**
`start.bat` opens the Python download page for you automatically when it can't find Python.
The most common reason this happens even after installing: the **"Add python.exe to PATH"**
box wasn't checked during install (it's easy to miss). Reinstall Python (Step 1), definitely
check that box this time, then double-click `start.bat` again.

**Typing anything with `python` in it opened the Microsoft Store instead**
This is Windows trying to be "helpful," and it means Python genuinely isn't installed yet,
even if you thought you already did Step 1. Close the Store window and redo Step 1, making
sure you run the installer you downloaded from **python.org**, not anything from the Store.

**The black window shows a wall of red text during setup, or something about a network error**
That's the "installing what the app needs" part failing. Check your internet connection —
this step downloads a few files. A work or school network's firewall can also block it; a
home network usually works if you have one available.

**Antivirus flagged or deleted something from the project folder**
Some antivirus tools are overly cautious about downloaded ZIPs containing code. This project
doesn't do anything malicious — you can safely tell your antivirus to allow it / restore the
file. If you're not comfortable doing that, it's fine to leave it blocked; just know that's
why something stopped working.

**The browser didn't open by itself**
Open one yourself (Chrome, Edge, Firefox — whichever you normally use) and type
`http://localhost:8000` into the **address bar** at the top (not a search engine). This can
happen on the very first run if your computer is slower to start the app than `start.bat`
expects to wait.

**The page won't load ("can't reach this page" / "connection refused")**
Check the black window from Step 3 is still open. If you accidentally closed it, double-click
`start.bat` again.

**Matches won't fetch / says no API token is configured**
Click the **⚙** button in the top-right and add your token there (Step 4 above). If you
already added one and it's still not working, click ⚙ again, clear the box, and paste a fresh
copy of your token — a copy-paste can silently pick up a trailing space or a missing
character.

**A match won't load / says "not returned by the API"**
The most common cause by far: **it was a public Quick Play match.** MWO's API only serves
private/custom lobby matches (scrims, league games) — it will reject a Quick Play Game ID
even if you copied it perfectly. Double-check it came from a private match. If it did and
it's still failing, confirm the ID is copied exactly from the end-round screen with no typos.

**"Address already in use" / the app won't start**
Something else is already using port 8000, possibly the app already running in another window
you forgot about (look for another black window and close it). If that's not it, see the
manual-method box in Step 3 above and add `--port 8001` to the `uvicorn` command, then go to
`http://localhost:8001` instead.

**I closed the black window and now the site won't load**
That's expected — closing it stops the app. Double-click `start.bat` again. Nothing you've
entered gets lost; it's all saved on your computer, not in that window.

**None of the above matches what you're seeing**
Note down the *exact* text of any error message (copy it if you can) and which numbered step
you were on when it happened — that's the information that actually matters for tracking down
what went wrong, far more than a description like "it didn't work."

**On a Mac?** `start.bat` is Windows-only. Use the manual-method box in Step 3 above instead:
install Python from python.org (no PATH checkbox needed on Mac), use the **Terminal** app
instead of `cmd`, and the `pip install` / `uvicorn` commands are identical.

---
<br>

<details>
<summary><strong>Technical reference</strong> (for anyone who wants to read or extend the code)</summary>

### How team identification works

The API labels sides `1` and `2` *per match*. Those labels mean nothing across matches — side
1 in one match and side 1 in the next can be completely different groups. What is stable is
who plays alongside whom.

So `app/teams.py` builds a **signed co-occurrence graph**: every pair of players on the same
side gains a positive edge, every pair on opposite sides a negative one. Then it 2-colours
that graph:

1. Seed from the strongest "definitely opponents" edge.
2. Place remaining players greedily, strongest evidence first.
3. Sweep repeatedly, flipping anyone whose placement disagrees with the settled graph.
4. Resolve each match's sides to teams by roster majority.

A full side swap produces no contradiction at all, because the graph never looks at the
numeric side. A substitute is pulled to whichever team they shared a side with. Players
placed on thin evidence — a single appearance, or genuinely conflicting sides — are flagged
in the UI rather than silently guessed.

Corrections made in the UI are **pinned**: they anchor the inference rather than just
relabelling the result, so fixing one player improves the placement of everyone connected to
them. Edge cases handled explicitly: a single-match series (labels are arbitrary — you're
told so), disjoint groups of matches with no players in common, and a genuine mercenary who
played for both teams (flagged `both sides`).

### Auto-naming from unit tags

If most of a team's roster shares the same in-game unit tag (e.g. `[V1LE]`), the team is
automatically named after it — `app/teams.py`'s `infer_clan_tag()` takes one vote per
*player*, not per match-appearance, so someone who dropped five times doesn't outweigh four
teammates who dropped once. A tie between two or more tags (an "even spread"), no tags at
all, or a single tagged player among pickups all fall back to the generic "Team A"/"Team B".

This only ever fires while a team's name is still the untouched default — the moment you
rename a team yourself (via the team-name fields or `PUT /series/{id}/teams`), that name is
never auto-overwritten again, even if later matches shift who's on the roster.

### API token storage

The token can come from two places: `.env` (`MWO_API_TOKEN`, read once at startup) or the
in-app ⚙ Settings panel, which saves it to the `app_settings` table in `data/mwo.db`.
`service.resolve_settings()` prefers the database value when one exists — it's the more
recent, more explicit choice — and every request resolves it fresh from that connection, so
saving a new token takes effect immediately with no restart. Clearing it (the "Clear saved
token" button, or `DELETE /api/settings/token`) reverts to whatever `.env` provides, if
anything; the app itself no longer requires `.env` to have a token at all, which matters if
this ever runs somewhere `.env` isn't yours to edit. The token is never echoed back over the
API — every response reports it masked (`service.mask_token`, last 4 characters only).

### Summary vs. team-scoped views

The dashboard is tabs, not one long scroll: **Summary** (both teams compared) plus one tab
per team (that team's own numbers only), plus **Matches** (every game's full scoreboard).
Almost none of that is special-cased per module — `SeriesContext` carries an optional
`team_filter`, and most modules already loop `for team in ctx.teams` or build off
`ctx.lines()`, both of which narrow to one team automatically when scoped. A module only
needs its own logic for a scoped view when it has a hardcoded two-team layout to collapse
(see `breakdowns.py` or `leaderboards.py` for the pattern: branch on `ctx.is_scoped` to drop
the now-redundant "Team" column). A few things — like "kills scored against this team" —
deliberately read `ctx.matches` directly instead of the (possibly narrowed) team buckets,
because the true opponent must stay real even when only one team's page is showing.

A module opts out of team pages entirely with a `tabs` class attribute — `match_results` sets
`tabs = ("matches",)` because a single match is inherently both teams at once; there's no
single-team version of a box score worth splitting out. Everything else defaults to
`("summary", "team")` and needs no `tabs` line at all.

### The MWO API

`GET https://mwomercs.com/api/v1/matches/<game-id>?api_token=<token>` — this is a **private
match data** endpoint, confirmed the hard way: it only serves matches from private/custom
lobbies (scrims, league games). **Public Quick Play matches are rejected**, and the API gives
no distinct error for that case — a Quick Play ID, a malformed ID, and a real private-match ID
belonging to someone else all return the identical generic `422 {"message":"Unable to fulfill
request, please try again"}`. A missing or invalid token instead returns `401
{"error":"Unauthenticated"}`, which is how the two failure modes were told apart. Auth is via
the `api_token` query parameter; a request header of the same name (what the original
prototype script used) returns 401.

Confirmed response shape (per Piranha's own documentation):

```jsonc
{
  "MatchDetails": {
    "Map": "ForestColony", "ViewMode": "Both", "TimeOfDay": "Random",
    "GameMode": "Assault", "Region": "NorthAmerica", "MatchTimeMinutes": "15",
    "UseStockLoadout": false, "NoMechQuirks": false, "NoMechEfficiencies": false,
    "WinningTeam": "2", "Team1Score": 0, "Team2Score": 1,
    "MatchDuration": "69", "CompleteTime": "2017-07-14T18:09:54+00:00"
  },
  "UserDetails": [
    {
      "Username": "...", "IsSpectator": false, "Team": "2", "Lance": "1",
      "MechItemID": 532, "MechName": "hbr-fc", "SkillTier": 5,
      "HealthPercentage": 100, "Kills": 0, "KillsMostDamage": 0, "Assists": 0,
      "ComponentsDestroyed": 0, "MatchScore": 28, "Damage": 0, "TeamDamage": 0,
      "UnitTag": "_2ez"
    }
  ]
}
```

`app/normalize.py` maps the fields the app actively uses (map, mode, winner, scores,
username, side, mech, kills, assists, damage, match score, spectator flag) into typed
columns. Everything else — `Lance`, `UnitTag`, `SkillTier`, `TeamDamage`, `MatchDuration`,
etc. — is preserved verbatim in an `extra` dict (`extra_json` in the database) rather than
dropped, so a metric module can use it without a schema migration.

`python scripts/probe_schema.py <GAME_ID>` fetches a real match, saves the raw body to
`data/raw/`, and prints every key path with its type and a sample value — useful for
confirming the shape of a field before building a metric around it.

### See it working without a real Game ID

```
python scripts/seed_demo.py          # builds a DEMO series from synthetic matches
python scripts/seed_demo.py --clear  # removes it
```

Fabricates five matches with sides swapping and substitutes rotating in, loaded through the
normal ingest path. No network, no real match data, IDs are namespaced `DEMO-*`.

### Adding a metric module

One file, no frontend changes, no route changes, no registry edits. Drop a file in
`app/metrics/`:

```python
from .base import SeriesContext, stats_section, mean
from .registry import register

@register
class MyMetric:
    id = "my_metric"           # unique
    name = "My Metric"         # card title
    description = "What it shows."
    order = 50                 # display position

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

Restart the server and the card appears on both the Summary tab and each team's own tab —
scoping to one team needs no code on your part unless you're building a comparison table (see
above). `SeriesContext` hands you fully-resolved data — modules never touch SQL or the API:

| | |
|---|---|
| `ctx.matches` | `Match` objects, chronological |
| `ctx.teams` | `(TEAM_A, TEAM_B)` normally; just the one team when scoped |
| `ctx.is_scoped` | `True` on a team's own page, `False` on Summary |
| `ctx.lines()` | every non-spectator player line paired with the team it counted for (narrowed when scoped) |
| `ctx.filtered_active_players(match)` | one match's roster, narrowed when scoped — use instead of `match.active_players()` for anything per-match (an MVP pick, a scoreboard row) |
| `ctx.stats_by_team()` / `ctx.stats_by_player()` | pre-bucketed stats, built on `ctx.lines()` so they're scope-aware too |
| `ctx.team_for(match_id, username)` | team in a specific match (respects per-match overrides) |
| `ctx.team_name(team)` / `ctx.match_winner(match)` / `ctx.team_record()` | naming and results — always the real opponent, regardless of scope |

Section builders in `app/metrics/base.py`: `stats_section`, `table_section`, `bar_section`,
`line_section`, `note_section`. The frontend renders each type generically — tables get
click-to-sort for free, line charts skip matches a pilot didn't play. Add `tabs = ("matches",)`
to a module class only if it has no meaningful single-team view (see previous section).

Shipped modules: `core_aggregates`, `leaderboards`, `match_results`, `player_detail`, `breakdowns`.

### Layout

```
start.bat          double-click launcher: installs deps, runs uvicorn, opens the browser
app/
  main.py          FastAPI app; serves the API and web/ from one process
  config.py        config.json + MWO_API_TOKEN from .env (the fallback default)
  db.py            SQLite schema and queries, incl. the api_token override
  mwo_client.py    HTTP client: auth-mode fallback, throttling, typed errors
  cache.py         raw JSON on disk — completed matches are cached forever
  normalize.py     raw API body -> Match / PlayerStat
  teams.py         co-occurrence inference          <- the core logic
  service.py       ingest, context assembly, token resolution (.env vs saved-in-app)
  metrics/         auto-discovered metric modules
  routes/          matches, series, metrics, settings
web/               index.html + app.js + modules.js + style.css (no build step)
scripts/           probe_schema.py, seed_demo.py
tests/             104 tests
```

### Caching

A completed match is immutable, so once fetched it is never re-requested — the raw body sits
in `data/raw/<id>.json` and the normalised rows in `data/mwo.db`. Re-adding a stored match
reports `stored` and makes no network call. Tick *Re-fetch even if cached* to force one.
Batch ingest is partial-success: one bad ID reports its own error and the rest still load.

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

104 tests covering the inference algorithm (clean swaps, rotating substitutes, pinned
overrides, contested players, disjoint groups), clan-tag auto-naming, normalization of
partial and malformed payloads, hand-computed metric values on both the summary and
team-scoped views, the HTTP layer end to end with the network mocked, token
resolution/masking, and a concurrency regression test (FastAPI can run a request's dependency
and endpoint body on different threadpool threads — SQLite connections need
`check_same_thread=False` or every concurrent request 500s, which is exactly what the
dashboard sends on load).

</details>
