"""API token management — lets the token be set from the UI instead of only .env."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..service import clear_api_token, set_api_token, token_status
from .deps import get_conn

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SetTokenRequest(BaseModel):
    token: str


@router.get("/token")
def get_token_status(conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return token_status(conn)


@router.put("/token")
def put_token(payload: SetTokenRequest, conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    try:
        set_api_token(conn, payload.token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    conn.commit()
    return token_status(conn)


@router.delete("/token")
def delete_token(conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    clear_api_token(conn)
    conn.commit()
    return token_status(conn)
