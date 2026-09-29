"""Shared HTTP resilience layer for ESP sync providers."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Mapping, Sequence

import httpx

from app.connectors.exceptions import ESPConflictError
from app.core.logging import get_logger

logger = get_logger(__name__)

# Types matching httpx parameter signatures
type HeadersType = Mapping[str, str] | None
type ParamsType = (
    Mapping[str, str | int | float | bool | Sequence[str | int | float | bool | None] | None] | None
)
type JsonType = object | None
type DataType = Mapping[str, str] | None


async def resilient_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    headers: HeadersType = None,
    params: ParamsType = None,
    json: JsonType = None,
    data: DataType = None,
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> httpx.Response:
    """Execute an HTTP request with retry and exponential backoff.

    Retries on: 429, 503, 504, httpx.TimeoutException.
    Fails fast on: 401, 403, 404, 409, 422.
    On 409, raises ESPConflictError with the response body.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            resp = await client.request(
                method, url, headers=headers, params=params, json=json, data=data
            )

            # Fail-fast status codes
            if resp.status_code == 409:
                raise ESPConflictError(f"ESP conflict on {url}: {resp.text}")
            if resp.status_code in {401, 403, 404, 422}:
                return resp

            # Retryable status codes
            if resp.status_code in {429, 503, 504}:
                if attempt == max_retries:
                    resp.raise_for_status()
                delay = _compute_delay(resp, attempt, base_delay)
                logger.warning(
                    "esp.http.retry",
                    status=resp.status_code,
                    attempt=attempt + 1,
                    delay=delay,
                    url=url,
                )
                await asyncio.sleep(delay)
                continue

            return resp

        except httpx.TimeoutException as exc:
            last_exc = exc
            if attempt == max_retries:
                raise
            delay = min(base_delay * math.pow(2, attempt), 30.0)
            logger.warning(
                "esp.http.timeout_retry",
                attempt=attempt + 1,
                delay=delay,
                url=url,
            )
            await asyncio.sleep(delay)

    # Should not reach here, but satisfy type checker
    if last_exc:
        raise last_exc
    msg = f"Request to {url} failed after {max_retries} retries"
    raise httpx.HTTPError(msg)


def _compute_delay(resp: httpx.Response, attempt: int, base_delay: float) -> float:
    """Compute retry delay, respecting Retry-After header."""
    retry_after = resp.headers.get("Retry-After")
    if retry_after:
        try:
            return float(retry_after)
        except ValueError:
            pass
    return min(base_delay * math.pow(2, attempt), 30.0)
