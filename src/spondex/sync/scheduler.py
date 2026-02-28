"""Sync scheduler — runs sync engine on a configurable interval."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from spondex.storage.models import SyncMode
    from spondex.sync.engine import SyncEngine

log = structlog.get_logger(__name__)


class SyncScheduler:
    """Schedules periodic sync runs with support for pause/resume and manual trigger."""

    def __init__(
        self,
        engine: SyncEngine,
        interval_minutes: int = 30,
        default_mode: SyncMode = "incremental",
    ) -> None:
        self._engine = engine
        self._interval = interval_minutes * 60  # seconds
        self._default_mode = default_mode
        self._paused = False
        self._stop_event = asyncio.Event()
        self._trigger_event = asyncio.Event()
        self._trigger_mode: SyncMode | None = None
        self._task: asyncio.Task | None = None
        self._last_sync_at: datetime | None = None
        self._next_sync_at: datetime | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        """Start the scheduler loop."""
        if self.is_running:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._loop())
        log.info("scheduler_started", interval_minutes=self._interval // 60)

    async def stop(self) -> None:
        """Stop the scheduler, waiting for any in-progress sync to complete."""
        if not self.is_running:
            return
        self._stop_event.set()
        self._trigger_event.set()  # wake up if sleeping
        if self._task:
            await self._task
            self._task = None
        log.info("scheduler_stopped")

    def trigger_now(self, mode: SyncMode | None = None) -> None:
        """Trigger an immediate sync. Optionally override mode."""
        self._trigger_mode = mode
        self._trigger_event.set()

    def pause(self) -> None:
        self._paused = True
        log.info("scheduler_paused")

    def resume(self) -> None:
        self._paused = False
        log.info("scheduler_resumed")

    def get_status(self) -> dict:
        return {
            "running": self.is_running,
            "paused": self._paused,
            "interval_minutes": self._interval // 60,
            "default_mode": self._default_mode,
            "last_sync_at": self._last_sync_at.isoformat() if self._last_sync_at else None,
            "next_sync_at": self._next_sync_at.isoformat() if self._next_sync_at else None,
        }

    async def _loop(self) -> None:
        first_run = True
        while not self._stop_event.is_set():
            if first_run:
                # First run — sync immediately, don't wait
                first_run = False
                self._next_sync_at = datetime.now(UTC).replace(microsecond=0)
            else:
                # Calculate next sync time
                from datetime import timedelta

                self._next_sync_at = datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=self._interval)

                # Interruptible sleep
                self._trigger_event.clear()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(
                        self._wait_for_trigger_or_stop(),
                        timeout=self._interval,
                    )

            if self._stop_event.is_set():
                break

            if self._paused:
                continue

            # Determine mode
            mode = self._trigger_mode or self._default_mode
            self._trigger_mode = None
            self._trigger_event.clear()

            try:
                await self._engine.run_sync(mode)
                self._last_sync_at = datetime.now(UTC)
            except Exception as exc:
                log.error("scheduled_sync_failed", error=str(exc))

    async def _wait_for_trigger_or_stop(self) -> None:
        """Wait until either trigger or stop event is set."""
        trigger_task = asyncio.create_task(self._trigger_event.wait())
        stop_task = asyncio.create_task(self._stop_event.wait())
        try:
            done, pending = await asyncio.wait(
                {trigger_task, stop_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            for t in (trigger_task, stop_task):
                if not t.done():
                    t.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await t
