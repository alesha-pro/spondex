"""Tests for the SyncScheduler."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from spondex.sync.scheduler import SyncScheduler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class MockEngine:
    """Mock SyncEngine for scheduler tests."""

    def __init__(self):
        self.run_sync = AsyncMock()
        self.sync_count = 0

    async def _count_sync(self, mode=None):
        self.sync_count += 1


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_stop():
    """Scheduler should start and stop cleanly."""
    engine = MockEngine()
    sched = SyncScheduler(engine, interval_minutes=1)

    await sched.start()
    assert sched.is_running

    await sched.stop()
    assert not sched.is_running


@pytest.mark.asyncio
async def test_trigger_now():
    """trigger_now should cause an immediate sync."""
    engine = MockEngine()
    sched = SyncScheduler(engine, interval_minutes=60)  # long interval

    await sched.start()
    # Give scheduler a moment to enter the wait
    await asyncio.sleep(0.05)

    sched.trigger_now(mode="full")
    # Wait for sync to run
    await asyncio.sleep(0.1)

    await sched.stop()

    engine.run_sync.assert_called()
    # Should have been called with "full" mode
    args, kwargs = engine.run_sync.call_args
    assert args[0] == "full"


@pytest.mark.asyncio
async def test_pause_resume():
    """Paused scheduler should skip triggered syncs."""
    engine = MockEngine()
    sched = SyncScheduler(engine, interval_minutes=60)

    await sched.start()
    # Wait for the immediate first sync to complete
    await asyncio.sleep(0.1)
    initial_call_count = engine.run_sync.call_count

    sched.pause()
    assert sched.get_status()["paused"] is True

    # Trigger while paused — should not sync
    sched.trigger_now()
    await asyncio.sleep(0.1)

    assert engine.run_sync.call_count == initial_call_count

    sched.resume()
    assert sched.get_status()["paused"] is False

    # Now trigger should work
    sched.trigger_now()
    await asyncio.sleep(0.1)

    await sched.stop()
    assert engine.run_sync.call_count > initial_call_count


@pytest.mark.asyncio
async def test_get_status():
    """get_status should reflect scheduler state."""
    engine = MockEngine()
    sched = SyncScheduler(engine, interval_minutes=15, default_mode="full")

    status = sched.get_status()
    assert status["running"] is False
    assert status["paused"] is False
    assert status["interval_minutes"] == 15
    assert status["default_mode"] == "full"


@pytest.mark.asyncio
async def test_double_start():
    """Starting an already running scheduler should be a no-op."""
    engine = MockEngine()
    sched = SyncScheduler(engine, interval_minutes=60)

    await sched.start()
    task = sched._task
    await sched.start()  # should not create a new task
    assert sched._task is task

    await sched.stop()


@pytest.mark.asyncio
async def test_sync_error_doesnt_crash_scheduler():
    """Scheduler should survive engine errors and keep running."""
    engine = MockEngine()
    engine.run_sync.side_effect = RuntimeError("Boom")

    sched = SyncScheduler(engine, interval_minutes=60)
    await sched.start()
    await asyncio.sleep(0.05)

    sched.trigger_now()
    await asyncio.sleep(0.1)

    # Scheduler should still be running despite error
    assert sched.is_running

    await sched.stop()
