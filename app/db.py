"""SQLite persistence. Raw bodies live on disk; this is the normalised, queryable view."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings, get_settings
from .models import Match, PlayerStat, Series

SCHEMA = """
CREATE TABLE IF NOT EXISTS match (
    match_id         TEXT PRIMARY KEY,
    map_name         TEXT,
    game_mode        TEXT,
    duration_minutes REAL,
    winning_side     INTEGER,
    side1_score      INTEGER,
    side2_score      INTEGER,
    completed_at     TEXT,
    fetched_at       TEXT NOT NULL,
    raw_path         TEXT,
    extra_json       TEXT
);

CREATE TABLE IF NOT EXISTS player_stat (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id    TEXT NOT NULL REFERENCES match(match_id) ON DELETE CASCADE,
    username    TEXT NOT NULL,
    side        INTEGER NOT NULL,
    mech_name   TEXT,
    kills       INTEGER,
    assists     INTEGER,
    damage      REAL,
    match_score REAL,
    is_spectator INTEGER DEFAULT 0,
    unit_tag    TEXT DEFAULT '',
    extra_json  TEXT,
    UNIQUE(match_id, username)
);
CREATE INDEX IF NOT EXISTS idx_player_stat_match ON player_stat(match_id);
CREATE INDEX IF NOT EXISTS idx_player_stat_user  ON player_stat(username);

CREATE TABLE IF NOT EXISTS series (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    team_a_name  TEXT DEFAULT 'Team A',
    team_b_name  TEXT DEFAULT 'Team B',
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS series_match (
    series_id INTEGER NOT NULL REFERENCES series(id) ON DELETE CASCADE,
    match_id  TEXT NOT NULL REFERENCES match(match_id) ON DELETE CASCADE,
    PRIMARY KEY (series_id, match_id)
);

CREATE TABLE IF NOT EXISTS team_override (
    series_id INTEGER NOT NULL REFERENCES series(id) ON DELETE CASCADE,
    username  TEXT NOT NULL,
    team      TEXT NOT NULL,
    pinned    INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (series_id, username)
);

CREATE TABLE IF NOT EXISTS match_player_override (
    series_id INTEGER NOT NULL REFERENCES series(id) ON DELETE CASCADE,
    match_id  TEXT NOT NULL,
    username  TEXT NOT NULL,
    team      TEXT NOT NULL,
    PRIMARY KEY (series_id, match_id, username)
);

-- Generic key/value store for settings set through the app itself (e.g. an API
-- token entered in the UI) rather than .env — see service.resolve_settings.
CREATE TABLE IF NOT EXISTS app_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(settings: Settings | None = None) -> sqlite3.Connection:
    """Open a per-request connection.

    `check_same_thread=False` is required, not merely convenient: FastAPI runs sync
    dependencies and sync endpoints on its threadpool, and the two can land on different
    threads. The connection opened in `get_conn` would then be used from another thread
    and raise ProgrammingError. Each request still gets its own connection, so no
    connection is ever shared between concurrent requests.

    WAL lets readers run while a match is being written, and busy_timeout makes any
    remaining write contention wait rather than fail.
    """
    settings = settings or get_settings()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path, check_same_thread=False, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Lightweight, idempotent migrations for columns added after a db already exists.

    `CREATE TABLE IF NOT EXISTS` is a no-op against an existing table, so a new
    column needs its own ALTER TABLE — guarded by checking it isn't already there,
    since SQLite has no `ADD COLUMN IF NOT EXISTS`.
    """
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(player_stat)")}
    if "unit_tag" not in existing:
        conn.execute("ALTER TABLE player_stat ADD COLUMN unit_tag TEXT DEFAULT ''")


def init_db(settings: Settings | None = None) -> None:
    with connect(settings) as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)


# ---------------------------------------------------------------- matches


def save_match(conn: sqlite3.Connection, match: Match, raw_path: str | None = None) -> None:
    conn.execute(
        """INSERT INTO match (match_id, map_name, game_mode, duration_minutes,
                              winning_side, side1_score, side2_score, completed_at,
                              fetched_at, raw_path, extra_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(match_id) DO UPDATE SET
               map_name=excluded.map_name, game_mode=excluded.game_mode,
               duration_minutes=excluded.duration_minutes,
               winning_side=excluded.winning_side, side1_score=excluded.side1_score,
               side2_score=excluded.side2_score, completed_at=excluded.completed_at,
               fetched_at=excluded.fetched_at, raw_path=excluded.raw_path,
               extra_json=excluded.extra_json""",
        (
            match.match_id, match.map_name, match.game_mode, match.duration_minutes,
            match.winning_side, match.side1_score, match.side2_score, match.completed_at,
            _now(), raw_path, json.dumps(match.extra),
        ),
    )
    conn.execute("DELETE FROM player_stat WHERE match_id = ?", (match.match_id,))
    conn.executemany(
        """INSERT INTO player_stat (match_id, username, side, mech_name, kills, assists,
                                    damage, match_score, is_spectator, unit_tag, extra_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        [
            (
                p.match_id, p.username, p.side, p.mech_name, p.kills, p.assists,
                p.damage, p.match_score, int(p.is_spectator), p.unit_tag, json.dumps(p.extra),
            )
            for p in match.players
        ],
    )


def _row_to_match(row: sqlite3.Row, players: list[sqlite3.Row]) -> Match:
    return Match(
        match_id=row["match_id"],
        map_name=row["map_name"] or "",
        game_mode=row["game_mode"] or "",
        duration_minutes=row["duration_minutes"] or 0.0,
        winning_side=row["winning_side"],
        side1_score=row["side1_score"] or 0,
        side2_score=row["side2_score"] or 0,
        completed_at=row["completed_at"],
        extra=json.loads(row["extra_json"] or "{}"),
        players=[
            PlayerStat(
                match_id=p["match_id"],
                username=p["username"],
                side=p["side"],
                mech_name=p["mech_name"] or "",
                kills=p["kills"] or 0,
                assists=p["assists"] or 0,
                damage=p["damage"] or 0.0,
                match_score=p["match_score"] or 0.0,
                is_spectator=bool(p["is_spectator"]),
                unit_tag=p["unit_tag"] or "",
                extra=json.loads(p["extra_json"] or "{}"),
            )
            for p in players
        ],
    )


def load_match(conn: sqlite3.Connection, match_id: str) -> Match | None:
    row = conn.execute("SELECT * FROM match WHERE match_id = ?", (match_id,)).fetchone()
    if row is None:
        return None
    players = conn.execute(
        "SELECT * FROM player_stat WHERE match_id = ? ORDER BY side, username", (match_id,)
    ).fetchall()
    return _row_to_match(row, players)


def load_matches(conn: sqlite3.Connection, match_ids: list[str]) -> list[Match]:
    return [m for m in (load_match(conn, mid) for mid in match_ids) if m is not None]


def list_match_ids(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT match_id FROM match ORDER BY fetched_at DESC").fetchall()
    return [r["match_id"] for r in rows]


# ---------------------------------------------------------------- series


def create_series(conn: sqlite3.Connection, name: str, match_ids: list[str]) -> int:
    cursor = conn.execute(
        "INSERT INTO series (name, created_at) VALUES (?,?)", (name, _now())
    )
    series_id = int(cursor.lastrowid)
    add_matches_to_series(conn, series_id, match_ids)
    return series_id


def add_matches_to_series(conn: sqlite3.Connection, series_id: int, match_ids: list[str]) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO series_match (series_id, match_id) VALUES (?,?)",
        [(series_id, mid) for mid in match_ids],
    )


def remove_match_from_series(conn: sqlite3.Connection, series_id: int, match_id: str) -> None:
    conn.execute(
        "DELETE FROM series_match WHERE series_id = ? AND match_id = ?", (series_id, match_id)
    )


def get_series(conn: sqlite3.Connection, series_id: int) -> Series | None:
    row = conn.execute("SELECT * FROM series WHERE id = ?", (series_id,)).fetchone()
    if row is None:
        return None
    matches = conn.execute(
        "SELECT match_id FROM series_match WHERE series_id = ?", (series_id,)
    ).fetchall()
    return Series(
        id=row["id"],
        name=row["name"],
        team_a_name=row["team_a_name"],
        team_b_name=row["team_b_name"],
        match_ids=[m["match_id"] for m in matches],
        created_at=row["created_at"],
    )


def list_series(conn: sqlite3.Connection) -> list[Series]:
    rows = conn.execute("SELECT id FROM series ORDER BY created_at DESC").fetchall()
    return [s for s in (get_series(conn, r["id"]) for r in rows) if s is not None]


def delete_series(conn: sqlite3.Connection, series_id: int) -> None:
    conn.execute("DELETE FROM series WHERE id = ?", (series_id,))


def rename_teams(conn: sqlite3.Connection, series_id: int, team_a: str, team_b: str) -> None:
    conn.execute(
        "UPDATE series SET team_a_name = ?, team_b_name = ? WHERE id = ?",
        (team_a, team_b, series_id),
    )


# ---------------------------------------------------------------- overrides


def set_override(
    conn: sqlite3.Connection, series_id: int, username: str, team: str, pinned: bool = True
) -> None:
    conn.execute(
        """INSERT INTO team_override (series_id, username, team, pinned) VALUES (?,?,?,?)
           ON CONFLICT(series_id, username) DO UPDATE SET
               team=excluded.team, pinned=excluded.pinned""",
        (series_id, username, team, int(pinned)),
    )


def clear_override(conn: sqlite3.Connection, series_id: int, username: str) -> None:
    conn.execute(
        "DELETE FROM team_override WHERE series_id = ? AND username = ?", (series_id, username)
    )


def get_overrides(conn: sqlite3.Connection, series_id: int) -> tuple[dict[str, str], set[str]]:
    rows = conn.execute(
        "SELECT username, team, pinned FROM team_override WHERE series_id = ?", (series_id,)
    ).fetchall()
    overrides = {r["username"]: r["team"] for r in rows}
    pinned = {r["username"] for r in rows if r["pinned"]}
    return overrides, pinned


def set_match_override(
    conn: sqlite3.Connection, series_id: int, match_id: str, username: str, team: str
) -> None:
    conn.execute(
        """INSERT INTO match_player_override (series_id, match_id, username, team)
           VALUES (?,?,?,?)
           ON CONFLICT(series_id, match_id, username) DO UPDATE SET team=excluded.team""",
        (series_id, match_id, username, team),
    )


def get_match_overrides(conn: sqlite3.Connection, series_id: int) -> dict[tuple[str, str], str]:
    rows = conn.execute(
        "SELECT match_id, username, team FROM match_player_override WHERE series_id = ?",
        (series_id,),
    ).fetchall()
    return {(r["match_id"], r["username"]): r["team"] for r in rows}


# ---------------------------------------------------------------- app settings


def get_app_setting(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_app_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """INSERT INTO app_settings (key, value) VALUES (?,?)
           ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
        (key, value),
    )


def delete_app_setting(conn: sqlite3.Connection, key: str) -> None:
    conn.execute("DELETE FROM app_settings WHERE key = ?", (key,))
