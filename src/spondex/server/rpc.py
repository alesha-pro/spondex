"""RPC server module for the Spondex daemon."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog
from fastapi import FastAPI
from pydantic import BaseModel

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Wire models
# ---------------------------------------------------------------------------


class RpcRequest(BaseModel):
    """Incoming RPC call from the CLI client."""

    cmd: str
    params: dict = {}


class RpcResponse(BaseModel):
    """Outgoing RPC response sent back to the CLI client."""

    ok: bool = True
    data: dict = {}
    error: str | None = None


# ---------------------------------------------------------------------------
# Daemon runtime state
# ---------------------------------------------------------------------------


class DaemonState:
    """Holds mutable runtime state shared across the daemon."""

    def __init__(self) -> None:
        self.started_at: datetime = datetime.now(timezone.utc)
        self.shutdown_event: asyncio.Event = asyncio.Event()

    # -- queries ------------------------------------------------------------

    def get_status(self) -> dict:
        """Return a snapshot of the current daemon status."""
        uptime = (datetime.now(timezone.utc) - self.started_at).total_seconds()
        return {
            "state": "idle",
            "uptime_seconds": round(uptime, 2),
            "started_at": self.started_at.isoformat(),
        }

    # -- mutations ----------------------------------------------------------

    def request_shutdown(self) -> None:
        """Signal the daemon to shut down gracefully."""
        log.info("shutdown_requested")
        self.shutdown_event.set()


# ---------------------------------------------------------------------------
# RPC command dispatch
# ---------------------------------------------------------------------------

_KNOWN_COMMANDS = ("status", "shutdown", "health", "ping")


def _dispatch(cmd: str, state: DaemonState) -> RpcResponse:
    """Route an RPC command string to the appropriate handler."""
    if cmd == "ping":
        return RpcResponse()

    if cmd == "status":
        return RpcResponse(data=state.get_status())

    if cmd == "health":
        uptime = (datetime.now(timezone.utc) - state.started_at).total_seconds()
        return RpcResponse(data={"uptime_seconds": round(uptime, 2)})

    if cmd == "shutdown":
        state.request_shutdown()
        return RpcResponse(data={"message": "shutdown initiated"})

    return RpcResponse(ok=False, error=f"unknown command: {cmd}")


# ---------------------------------------------------------------------------
# FastAPI application factory
# ---------------------------------------------------------------------------


def create_rpc_app(state: DaemonState) -> FastAPI:
    """Build the FastAPI application that serves the RPC endpoint."""
    app = FastAPI(title="spondex-daemon", docs_url=None, redoc_url=None)

    @app.post("/rpc", response_model=RpcResponse)
    async def rpc_endpoint(request: RpcRequest) -> RpcResponse:
        log.info("rpc_request", cmd=request.cmd)
        response = _dispatch(request.cmd, state)
        if not response.ok:
            log.warning("rpc_error", cmd=request.cmd, error=response.error)
        return response

    @app.get("/health", response_model=RpcResponse)
    async def health_endpoint() -> RpcResponse:
        uptime = (datetime.now(timezone.utc) - state.started_at).total_seconds()
        return RpcResponse(data={"uptime_seconds": round(uptime, 2)})

    return app
