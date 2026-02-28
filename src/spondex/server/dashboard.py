"""Web dashboard server for the Spondex daemon."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

if TYPE_CHECKING:
    from spondex.server.rpc import DaemonState
    from spondex.storage.database import Database

log = structlog.get_logger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"


class ConnectionManager:
    """Manages WebSocket connections and broadcasts status updates."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)

    async def broadcast(self, message: dict) -> None:
        payload = json.dumps(message)
        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.discard(ws)


async def _get_counts(db: Database) -> dict:
    """Gather aggregate counts from the database."""
    tracks = await db.count_track_mappings()
    unmatched = await db.count_unmatched()
    collections = await db.count_collections()
    sync_runs = await db.count_sync_runs()
    return {
        "tracks": tracks,
        "unmatched": unmatched,
        "collections": collections,
        "sync_runs": sync_runs,
    }


async def _build_status(state: DaemonState, db: Database) -> dict:
    """Build the full status payload."""
    from datetime import datetime, timezone

    status = state.get_status()
    status["counts"] = await _get_counts(db)

    # Enrich scheduler with computed fields for the frontend.
    if "scheduler" in status:
        sched = status["scheduler"]
        next_at = sched.get("next_sync_at")
        if next_at:
            try:
                dt = datetime.fromisoformat(next_at)
                delta = (dt - datetime.now(timezone.utc)).total_seconds()
                sched["next_run_in_seconds"] = max(0, round(delta))
            except (ValueError, TypeError):
                sched["next_run_in_seconds"] = None
        else:
            sched["next_run_in_seconds"] = None
        sched["total_runs"] = status["counts"]["sync_runs"]

    return status


def create_dashboard_app(state: DaemonState, db: Database) -> FastAPI:
    """Build the FastAPI application for the web dashboard."""
    manager = ConnectionManager()

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # noqa: ARG001, ANN001
        async def _broadcast_loop() -> None:
            while True:
                await asyncio.sleep(2)
                try:
                    data = await _build_status(state, db)
                    await manager.broadcast({"type": "status", "data": data})
                except Exception:
                    pass

        task = asyncio.create_task(_broadcast_loop())
        yield
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    app = FastAPI(title="spondex-dashboard", docs_url=None, redoc_url=None, lifespan=lifespan)

    # -- REST endpoints -------------------------------------------------------

    @app.get("/api/status")
    async def api_status() -> dict:
        return await _build_status(state, db)

    @app.get("/api/history")
    async def api_history(
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> dict:
        items = await db.list_sync_runs_paginated(limit, offset)
        total = await db.count_sync_runs()
        return {
            "items": [r.model_dump() for r in items],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @app.get("/api/tracks")
    async def api_tracks(
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        search: str = Query(default=""),
    ) -> dict:
        search_q = search.strip() or None
        items = await db.list_track_mappings_paginated(limit, offset, search_q)
        total = await db.count_track_mappings(search_q)
        return {
            "items": [t.model_dump() for t in items],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @app.get("/api/unmatched")
    async def api_unmatched(
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> dict:
        items = await db.list_unmatched_paginated(limit, offset)
        total = await db.count_unmatched()
        return {
            "items": [u.model_dump() for u in items],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @app.get("/api/collections")
    async def api_collections() -> list[dict]:
        return await db.list_collections_with_counts()

    @app.get("/api/config")
    async def api_config() -> dict:
        from spondex.config import load_config

        cfg = load_config()
        return {
            "daemon": {
                "dashboard_port": cfg.daemon.dashboard_port,
                "log_level": cfg.daemon.log_level,
            },
            "sync": {
                "interval_minutes": cfg.sync.interval_minutes,
                "mode": cfg.sync.mode,
                "propagate_deletions": cfg.sync.propagate_deletions,
            },
            "spotify": {"configured": cfg.is_spotify_configured()},
            "yandex": {"configured": cfg.is_yandex_configured()},
        }

    @app.get("/api/charts/confidence")
    async def api_charts_confidence() -> list[dict]:
        return await db.get_confidence_distribution()

    @app.get("/api/charts/activity")
    async def api_charts_activity(
        limit: int = Query(default=12, ge=1, le=30),
    ) -> list[dict]:
        return await db.get_sync_chart_data(limit)

    @app.post("/api/sync")
    async def api_sync_now(body: dict | None = None):  # noqa: ANN201
        if not state.scheduler:
            return JSONResponse({"error": "sync not configured"}, status_code=503)
        mode = (body or {}).get("mode")
        state.scheduler.trigger_now(mode=mode)
        return {"message": f"sync triggered (mode={mode or 'default'})"}

    @app.post("/api/pause")
    async def api_pause():  # noqa: ANN201
        if not state.scheduler:
            return JSONResponse({"error": "sync not configured"}, status_code=503)
        state.scheduler.pause()
        return {"message": "sync paused"}

    @app.post("/api/resume")
    async def api_resume():  # noqa: ANN201
        if not state.scheduler:
            return JSONResponse({"error": "sync not configured"}, status_code=503)
        state.scheduler.resume()
        return {"message": "sync resumed"}

    # -- WebSocket ------------------------------------------------------------

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await manager.connect(ws)
        try:
            while True:
                # Keep connection alive — wait for client pings or messages
                await ws.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(ws)

    # -- Static file serving --------------------------------------------------

    index_html = _STATIC_DIR / "index.html"

    if _STATIC_DIR.is_dir() and (_STATIC_DIR / "assets").is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=str(_STATIC_DIR / "assets")),
            name="assets",
        )

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):  # noqa: ANN201
        # Never serve HTML for API or WebSocket paths.
        if full_path.startswith(("api/", "ws")):
            return JSONResponse({"error": "not found"}, status_code=404)
        # Try serving the exact static file.
        file_path = _STATIC_DIR / full_path
        if full_path and file_path.is_file():
            return FileResponse(file_path)
        # SPA fallback — serve index.html.
        if index_html.is_file():
            return FileResponse(index_html)
        return JSONResponse(
            {"error": "dashboard not built — run 'npm run build' in src/dashboard/"},
            status_code=404,
        )

    return app
