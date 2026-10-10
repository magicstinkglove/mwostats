"""Change notifications for the stream pages.

Every successful write to the API bumps a counter; the overlay pages listen on
/api/overlay/events and refetch the moment it moves, instead of waiting for their
next poll. Polling stays as the fallback.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable

_version = 0


def bump() -> None:
    global _version
    _version += 1


def version() -> int:
    return _version


async def changes(
    is_disconnected: Callable[[], Awaitable[bool]],
    last_seen: str | None = None,
    lifetime: float = 2.0,
    interval: float = 0.1,
) -> AsyncIterator[str]:
    """Server-sent events: one message per change, tagged with the counter.

    Each stream ends after `lifetime` seconds and the browser reconnects at once,
    so an open page never holds up stopping or restarting the server. On reconnect
    the browser sends the last counter it saw (`last_seen`); a change made while it
    was reconnecting is sent straight away rather than missed.
    """
    seen = _version
    yield "retry: 100\n\n"
    if last_seen is not None and last_seen != str(seen):
        yield _event(seen)
    waited = 0.0
    while waited < lifetime:
        await asyncio.sleep(interval)
        waited += interval
        if await is_disconnected():
            return
        if _version != seen:
            seen = _version
            yield _event(seen)


def _event(version: int) -> str:
    return f"id: {version}\ndata: {version}\n\n"


class NotifyOnWrite:
    """ASGI middleware: bump the counter after any successful non-GET /api/ request
    (overlay controls, new matches, roster fixes) since any of them can change what's on stream."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "OPTIONS") or not scope["path"].startswith("/api/"):
            await self.app(scope, receive, send)
            return
        status = 500

        async def send_status(message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        await self.app(scope, receive, send_status)
        if status < 400:
            bump()
