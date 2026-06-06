# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportGeneralTypeIssues=false
"""Service layer for the scheduling engine — CRUD operations on jobs."""

import json
from datetime import UTC, datetime

from croniter import croniter

from app.core.config import get_settings
from app.core.exceptions import DomainValidationError, NotFoundError
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.scheduling.registry import get_job_callable
from app.scheduling.schemas import (
    JOBS_PREFIX,
    RUNS_PREFIX,
    JobDefinitionResponse,
    JobRunResponse,
    JobStatus,
    JobUpdateRequest,
)

logger = get_logger(__name__)


def _parse_job_hash(data: dict[str, str], name: str) -> JobDefinitionResponse:
    """Convert a Redis hash dict into a ``JobDefinitionResponse``."""
    cron_expr = data.get("cron_expr", "")
    last_run_str = data.get("last_run", "")
    last_run = datetime.fromisoformat(last_run_str) if last_run_str else None

    last_status_str = data.get("last_status", "")
    last_status = JobStatus(last_status_str) if last_status_str else None

    # Compute next_run from cron expression
    next_run: datetime | None = None
    if cron_expr:
        base = last_run or datetime.now(UTC)
        cron = croniter(cron_expr, base)
        next_run = cron.get_next(datetime)
        if next_run.tzinfo is None:
            next_run = next_run.replace(tzinfo=UTC)

    return JobDefinitionResponse(
        name=name,
        cron_expr=cron_expr,
        callable_name=data.get("callable_name", name),
        enabled=data.get("enabled") == "1",
        last_run=last_run,
        last_status=last_status,
        next_run=next_run,
        run_count=int(data.get("run_count", "0")),
    )


def _decode_hash(raw: dict[bytes | str, bytes | str]) -> dict[str, str]:
    """Decode a Redis hash response (may have bytes keys/values)."""
    result: dict[str, str] = {}
    for k, v in raw.items():
        dk = k.decode() if isinstance(k, bytes) else k
        dv = v.decode() if isinstance(v, bytes) else v
        result[dk] = dv
    return result


async def list_jobs() -> list[JobDefinitionResponse]:
    """List all registered scheduled jobs."""
    redis = await get_redis()
    jobs: list[JobDefinitionResponse] = []

    async for key in redis.scan_iter(match=f"{JOBS_PREFIX}:*"):
        key_str: str = key.decode() if isinstance(key, bytes) else str(key)
        name = key_str.removeprefix(f"{JOBS_PREFIX}:")
        raw = await redis.hgetall(key_str)
        if raw:
            data = _decode_hash(raw)
            jobs.append(_parse_job_hash(data, name))

    return sorted(jobs, key=lambda j: j.name)


async def get_job(name: str) -> JobDefinitionResponse:
    """Get a single job by name.

    Raises:
        NotFoundError: If the job does not exist.
    """
    redis = await get_redis()
    key = f"{JOBS_PREFIX}:{name}"
    raw = await redis.hgetall(key)
    if not raw:
        msg = f"Scheduled job {name!r} not found"
        raise NotFoundError(msg)
    data = _decode_hash(raw)
    return _parse_job_hash(data, name)


async def update_job(name: str, request: JobUpdateRequest) -> JobDefinitionResponse:
    """Update a job's enabled state or cron expression.

    Raises:
        NotFoundError: If the job does not exist.
        DomainValidationError: If the cron expression is invalid.
    """
    redis = await get_redis()
    key = f"{JOBS_PREFIX}:{name}"
    raw = await redis.hgetall(key)
    if not raw:
        msg = f"Scheduled job {name!r} not found"
        raise NotFoundError(msg)

    updates: dict[str, str] = {}

    if request.cron_expr is not None:
        if not croniter.is_valid(request.cron_expr):
            msg = f"Invalid cron expression: {request.cron_expr!r}"
            raise DomainValidationError(msg)
        updates["cron_expr"] = request.cron_expr

    if request.enabled is not None:
        updates["enabled"] = "1" if request.enabled else "0"

    if updates:
        # redis-py stubs type `mapping` as Mapping[FieldT, EncodableT]; the
        # invariant key type rejects dict[str, str] though it is valid at runtime.
        await redis.hset(key, mapping=updates)  # type: ignore[arg-type]
        logger.info("scheduling.job_updated", job=name, updates=list(updates.keys()))

    return await get_job(name)


async def trigger_job(name: str) -> JobRunResponse:
    """Manually trigger a job immediately.

    Raises:
        NotFoundError: If the job is not in the registry or Redis.
    """
    # Verify job exists in Redis
    redis = await get_redis()
    key = f"{JOBS_PREFIX}:{name}"
    exists = await redis.exists(key)
    if not exists:
        msg = f"Scheduled job {name!r} not found"
        raise NotFoundError(msg)

    callable_fn = get_job_callable(name)

    started_at = datetime.now(UTC)
    await redis.hset(key, "last_status", JobStatus.running)

    error_msg: str | None = None
    status = JobStatus.success

    try:
        await callable_fn()
    except Exception as exc:
        status = JobStatus.failed
        error_msg = str(exc)
        logger.error("scheduling.trigger_failed", job=name, error=str(exc), exc_info=True)

    ended_at = datetime.now(UTC)
    duration_ms = int((ended_at - started_at).total_seconds() * 1000)

    # Update job hash
    await redis.hset(
        key,
        mapping={
            "last_run": started_at.isoformat(),
            "last_status": status.value,
        },
    )
    await redis.hincrby(key, "run_count", 1)

    # Append to run history
    run = JobRunResponse(
        job_name=name,
        started_at=started_at,
        ended_at=ended_at,
        status=status,
        error=error_msg,
        duration_ms=duration_ms,
    )
    settings = get_settings()
    runs_key = f"{RUNS_PREFIX}:{name}"
    await redis.lpush(runs_key, run.model_dump_json())
    await redis.ltrim(runs_key, 0, settings.scheduling.max_run_history - 1)

    logger.info("scheduling.trigger_completed", job=name, status=status.value)
    return run


async def get_run_history(name: str, limit: int = 20) -> list[JobRunResponse]:
    """Get recent run history for a job.

    Raises:
        NotFoundError: If the job does not exist.
    """
    redis = await get_redis()
    key = f"{JOBS_PREFIX}:{name}"
    exists = await redis.exists(key)
    if not exists:
        msg = f"Scheduled job {name!r} not found"
        raise NotFoundError(msg)

    runs_key = f"{RUNS_PREFIX}:{name}"
    raw_runs = await redis.lrange(runs_key, 0, limit - 1)

    result: list[JobRunResponse] = []
    for raw in raw_runs:
        text = raw.decode() if isinstance(raw, bytes) else raw
        data = json.loads(text)
        result.append(JobRunResponse.model_validate(data))

    return result
