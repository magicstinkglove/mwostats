"""FastAPI entrypoint. Serves the JSON API and the static frontend from one process.

    uvicorn app.main:app --reload    ->  http://localhost:8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import ConfigError, get_settings
from .db import init_db
from .metrics import descriptors  # noqa: F401  (import triggers module discovery)
from .routes import matches, metrics, players, series, settings as settings_routes
from .routes.deps import get_conn
from .service import token_status

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="MWO Match Stats",
    description="Aggregate MechWarrior Online match statistics by team across many matches.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(matches.router)
app.include_router(series.router)
app.include_router(metrics.router)
app.include_router(settings_routes.router)
app.include_router(players.router)


@app.get("/api/health")
def health(conn=Depends(get_conn)) -> dict:
    """Report whether the app is configured well enough to reach the API."""
    try:
        settings = get_settings()
    except ConfigError as exc:
        return {"ok": False, "detail": str(exc)}
    return {
        "ok": True,
        "api_base_url": settings.api_base_url,
        "auth_mode": settings.auth_mode,
        "cache_dir": str(settings.cache_dir),
        "token": token_status(conn),
        "modules": [d["id"] for d in descriptors()],
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
else:  # pragma: no cover - only if the checkout is incomplete
    @app.get("/{_path:path}")
    def missing_web(_path: str) -> JSONResponse:
        return JSONResponse({"detail": "web/ directory is missing"}, status_code=500)
