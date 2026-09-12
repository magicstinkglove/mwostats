"""Match ingestion and inspection."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import list_match_ids, load_match
from ..service import ingest_matches, parse_match_ids, serialize_match
from .deps import get_conn

router = APIRouter(prefix="/api/matches", tags=["matches"])


class IngestRequest(BaseModel):
    match_ids: str | list[str] = Field(
        ..., description="Match IDs as a list, or one blob separated by spaces/commas/newlines"
    )
    force_refresh: bool = False


@router.post("")
def add_matches(payload: IngestRequest, conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    ids = parse_match_ids(payload.match_ids)
    if not ids:
        raise HTTPException(status_code=400, detail="No match IDs provided.")
    results = ingest_matches(conn, ids, force_refresh=payload.force_refresh)
    ok = [r["match_id"] for r in results if r["status"] != "error"]
    return {"results": results, "succeeded": ok, "failed": len(results) - len(ok)}


@router.get("")
def all_matches(conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return {"match_ids": list_match_ids(conn)}


@router.get("/{match_id}")
def one_match(match_id: str, conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    match = load_match(conn, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail=f"Match {match_id} is not stored locally.")
    return serialize_match(match)
