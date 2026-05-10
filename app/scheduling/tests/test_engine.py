"""Tests for the CronScheduler engine."""

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import structlog.testing

from app.core.config import SchedulingConfig
from app.scheduling.engine import CronScheduler
from app.scheduling.registry import scheduled_job


class TestStartStop:
    async def test_start_stop_clean(self, scheduling_config: SchedulingConfig) -> None:
        """Scheduler starts a background task and stops cleanly."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.exists = AsyncMock(return_value=0)
        mock_redis.hset = AsyncMock()
        mock_redis.eval = AsyncMock(return_value=1)

        with patch("app.scheduling.engine.get_redis", return_value=mock_redis):
            scheduler = CronScheduler(scheduling_config)
            await scheduler.start()
            assert scheduler._running is True
            assert scheduler._task is not None

            await scheduler.stop()
            assert scheduler._running is False
            assert scheduler._task is None


class TestEvaluateJobs:
    async def test_fires_due_job(
        self, scheduling_config: SchedulingConfig, mock_redis: AsyncMock
    ) -> None:
        """A job whose cron time has passed gets executed."""
        executed = False

        @scheduled_job(cron="* * * * *")
        async def every_minute() -> None:
            nonlocal executed
            executed = True

        # Set up Redis mock with an overdue job
        past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
        job_data = {
            b"name": b"every_minute",
            b"cron_expr": b"* * * * *",
            b"callable_name": b"every_minute",
            b"enabled": b"1",
            b"last_run": past.encode(),
            b"last_status": b"success",
            b"run_count": b"3",
        }

        async def _scan_iter(match: str = "*") -> AsyncGenerator[bytes]:
            yield b"scheduling:jobs:every_minute"

        mock_redis.scan_iter = _scan_iter
        mock_redis.hgetall = AsyncMock(return_value=job_data)
        mock_redis.set = AsyncMock(return_value=True)  # Leader lock

        with patch("app.scheduling.engine.get_redis", return_value=mock_redis):
            scheduler = CronScheduler(scheduling_config)
            await scheduler._acquire_leader()
            await scheduler._evaluate_jobs()
            # F039: _execute_job now runs as a fire-and-forget task — drain to await it.
            await scheduler.drain()

        assert executed is True

    async def test_skips_disabled_job(
        self, scheduling_config: SchedulingConfig, mock_redis: AsyncMock
    ) -> None:
        """A disabled job is not executed."""
        executed = False

        @scheduled_job(cron="* * * * *")
        async def disabled_task() -> None:
            nonlocal executed
            executed = True

        job_data = {
            b"name": b"disabled_task",
            b"cron_expr": b"* * * * *",
            b"callable_name": b"disabled_task",
            b"enabled": b"0",
            b"last_run": b"",
            b"last_status": b"",
            b"run_count": b"0",
        }

        async def _scan_iter(match: str = "*") -> AsyncGenerator[bytes]:
            yield b"scheduling:jobs:disabled_task"

        mock_redis.scan_iter = _scan_iter
        mock_redis.hgetall = AsyncMock(return_value=job_data)

        with patch("app.scheduling.engine.get_redis", return_value=mock_redis):
            scheduler = CronScheduler(scheduling_config)
            await scheduler._evaluate_jobs()

        assert executed is False


class TestExecuteJob:
    async def test_records_success(
        self, scheduling_config: SchedulingConfig, mock_redis: AsyncMock
    ) -> None:
        """Successful job execution records success in Redis."""

        @scheduled_job(cron="* * * * *")
        async def success_task() -> None:
            pass

        mock_redis.set = AsyncMock(return_value=True)

        with patch("app.scheduling.engine.get_redis", return_value=mock_redis):
            scheduler = CronScheduler(scheduling_config)
            await scheduler._execute_job("success_task", "scheduling:jobs:success_task")

        # Check that hset was called with success status
        hset_calls = mock_redis.hset.call_args_list
        status_update = next(
            c for c in hset_calls if c.kwargs.get("mapping", {}).get("last_status") == "success"
        )
        assert status_update is not None
        mock_redis.hincrby.assert_called_once_with("scheduling:jobs:success_task", "run_count", 1)
        mock_redis.lpush.assert_called_once()

    async def test_records_failure(
        self, scheduling_config: SchedulingConfig, mock_redis: AsyncMock
    ) -> None:
        """Failed job execution records error in Redis."""

        @scheduled_job(cron="* * * * *")
        async def failing_task() -> None:
            msg = "boom"
            raise RuntimeError(msg)

        mock_redis.set = AsyncMock(return_value=True)

        with patch("app.scheduling.engine.get_redis", return_value=mock_redis):
            scheduler = CronScheduler(scheduling_config)
            await scheduler._execute_job("failing_task", "scheduling:jobs:failing_task")

        # Check that hset was called with failed status
        hset_calls = mock_redis.hset.call_args_list
        status_update = next(
            c for c in hset_calls if c.kwargs.get("mapping", {}).get("last_status") == "failed"
        )
        assert status_update is not None

        # Check run history includes error
        lpush_call = mock_redis.lpush.call_args
        run_record = json.loads(lpush_call[0][1])
        assert run_record["status"] == "failed"
        assert "boom" in run_record["error"]


def _make_due_job_data(name: str) -> dict[bytes, bytes]:
    """Helper: build a Redis hash for an overdue, enabled job."""
    past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    return {
        b"name": name.encode(),
        b"cron_expr": b"* * * * *",
        b"callable_name": name.encode(),
        b"enabled": b"1",
        b"last_run": past.encode(),
        b"last_status": b"success",
        b"run_count": b"0",
    }


class TestLeaderRelease:
    """F038 — UUID identity + Lua CAS release."""

    async def test_identity_is_unique_per_instance(
        self, scheduling_config: SchedulingConfig
    ) -> None:
        """Two scheduler instances get distinct identities (no pid collision)."""
        a = CronScheduler(scheduling_config)
        b = CronScheduler(scheduling_config)
        assert a._identity != b._identity

    async def test_release_when_owner(
        self, scheduling_config: SchedulingConfig, mock_redis: AsyncMock
    ) -> None:
        """Release succeeds and emits leader_released when we still own the lock."""
        mock_redis.eval = AsyncMock(return_value=1)

        with (
            patch("app.scheduling.engine.get_redis", return_value=mock_redis),
            structlog.testing.capture_logs() as logs,
        ):
            scheduler = CronScheduler(scheduling_config)
            await scheduler._release_leader()

        released = [e for e in logs if e.get("event") == "scheduling.leader_released"]
        assert len(released) == 1
        assert released[0].get("identity") == scheduler._identity
        # Lua CAS path was taken; we never call DEL directly.
        mock_redis.delete.assert_not_called()

    async def test_release_no_op_when_stolen(
        self, scheduling_config: SchedulingConfig, mock_redis: AsyncMock
    ) -> None:
        """If the lock was stolen, release is a no-op and emits the no_op event."""
        mock_redis.eval = AsyncMock(return_value=0)

        with (
            patch("app.scheduling.engine.get_redis", return_value=mock_redis),
            structlog.testing.capture_logs() as logs,
        ):
            scheduler = CronScheduler(scheduling_config)
            await scheduler._release_leader()

        no_op = [e for e in logs if e.get("event") == "scheduling.leader_release_no_op"]
        assert len(no_op) == 1
        mock_redis.delete.assert_not_called()


class TestNonBlockingExecution:
    """F039 — _evaluate_jobs schedules jobs without blocking; drain awaits them."""

    async def _setup_due_jobs(self, mock_redis: AsyncMock, names: list[str]) -> None:
        """Wire mock_redis to return one overdue job per name."""
        keys = [f"scheduling:jobs:{n}".encode() for n in names]

        async def _scan_iter(match: str = "*") -> AsyncGenerator[bytes]:
            for k in keys:
                yield k

        async def _hgetall(key: str | bytes) -> dict[bytes, bytes]:
            decoded = key.decode() if isinstance(key, bytes) else key
            name = decoded.rsplit(":", 1)[-1]
            return _make_due_job_data(name)

        mock_redis.scan_iter = _scan_iter
        mock_redis.hgetall = AsyncMock(side_effect=_hgetall)

    async def test_evaluate_jobs_returns_before_slow_job_completes(
        self, scheduling_config: SchedulingConfig, mock_redis: AsyncMock
    ) -> None:
        """_evaluate_jobs spawns a task and returns immediately, even if the job is slow."""

        @scheduled_job(cron="* * * * *")
        async def slow_task() -> None:
            await asyncio.sleep(0.5)

        await self._setup_due_jobs(mock_redis, ["slow_task"])

        with patch("app.scheduling.engine.get_redis", return_value=mock_redis):
            scheduler = CronScheduler(scheduling_config)
            start = time.perf_counter()
            await scheduler._evaluate_jobs()
            elapsed = time.perf_counter() - start
            assert elapsed < 0.1
            assert len(scheduler._pending_tasks) == 1
            await scheduler.drain()  # Cleanup

    async def test_drain_awaits_all_pending(
        self, scheduling_config: SchedulingConfig, mock_redis: AsyncMock
    ) -> None:
        """drain() waits for every spawned task to complete and clears the set."""
        ran: list[str] = []

        @scheduled_job(cron="* * * * *")
        async def job_a() -> None:
            await asyncio.sleep(0.05)
            ran.append("a")

        @scheduled_job(cron="* * * * *")
        async def job_b() -> None:
            await asyncio.sleep(0.02)
            ran.append("b")

        @scheduled_job(cron="* * * * *")
        async def job_c() -> None:
            ran.append("c")

        await self._setup_due_jobs(mock_redis, ["job_a", "job_b", "job_c"])

        with patch("app.scheduling.engine.get_redis", return_value=mock_redis):
            scheduler = CronScheduler(scheduling_config)
            await scheduler._evaluate_jobs()
            await scheduler.drain()

        assert sorted(ran) == ["a", "b", "c"]
        assert scheduler._pending_tasks == set()

    async def test_max_concurrent_jobs_caps_inflight(
        self, scheduling_config: SchedulingConfig, mock_redis: AsyncMock
    ) -> None:
        """Excess due jobs are skipped this tick once the cap is reached."""
        scheduling_config.max_concurrent_jobs = 2

        @scheduled_job(cron="* * * * *")
        async def capped_0() -> None:
            await asyncio.sleep(0.5)

        @scheduled_job(cron="* * * * *")
        async def capped_1() -> None:
            await asyncio.sleep(0.5)

        @scheduled_job(cron="* * * * *")
        async def capped_2() -> None:
            await asyncio.sleep(0.5)

        @scheduled_job(cron="* * * * *")
        async def capped_3() -> None:
            await asyncio.sleep(0.5)

        @scheduled_job(cron="* * * * *")
        async def capped_4() -> None:
            await asyncio.sleep(0.5)

        names = ["capped_0", "capped_1", "capped_2", "capped_3", "capped_4"]
        await self._setup_due_jobs(mock_redis, names)

        with (
            patch("app.scheduling.engine.get_redis", return_value=mock_redis),
            structlog.testing.capture_logs() as logs,
        ):
            scheduler = CronScheduler(scheduling_config)
            await scheduler._evaluate_jobs()
            assert len(scheduler._pending_tasks) <= 2
            await scheduler.drain()

        capped = [e for e in logs if e.get("event") == "scheduling.max_concurrent_reached"]
        assert len(capped) >= 3

    async def test_stop_drains_before_cancel(
        self, scheduling_config: SchedulingConfig, mock_redis: AsyncMock
    ) -> None:
        """stop() drains in-flight jobs so their success is recorded before cancel."""
        finished = asyncio.Event()

        @scheduled_job(cron="* * * * *")
        async def stop_task() -> None:
            await asyncio.sleep(0.1)
            finished.set()

        await self._setup_due_jobs(mock_redis, ["stop_task"])

        with patch("app.scheduling.engine.get_redis", return_value=mock_redis):
            scheduler = CronScheduler(scheduling_config)
            await scheduler._acquire_leader()
            await scheduler._evaluate_jobs()
            # Don't start the loop — drive stop() directly with the spawned task.
            scheduler._task = asyncio.create_task(asyncio.sleep(10))
            scheduler._running = True
            await scheduler.stop()

        assert finished.is_set()
        # Job's terminal hset (last_status update) ran.
        last_status_calls = [
            c
            for c in mock_redis.hset.call_args_list
            if c.kwargs.get("mapping", {}).get("last_status") == "success"
        ]
        assert last_status_calls
