"""Real-time token cost tracking and budget enforcement.

Redis-backed cost ledger with per-model pricing, budget caps, and
warning thresholds. Integrates at the adapter layer — called before
and after each LLM completion.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from app.core.logging import get_logger

logger = get_logger(__name__)

_SECONDS_PER_90_DAYS: int = 90 * 86_400


class BudgetStatus(StrEnum):
    """Budget check result."""

    OK = "ok"
    WARNING = "warning"
    EXCEEDED = "exceeded"


@dataclass(frozen=True)
class ModelPricing:
    """Cost per 1M tokens in GBP."""

    input_per_million: float  # £ per 1M input tokens
    output_per_million: float  # £ per 1M output tokens


# Pricing table — update when provider pricing changes.
# Sources: OpenAI/Anthropic pricing pages. GBP approximation (1 USD ≈ 0.79 GBP).
_MODEL_PRICING: dict[str, ModelPricing] = {
    # OpenAI
    "gpt-4o": ModelPricing(input_per_million=1.97, output_per_million=7.90),
    "gpt-4o-mini": ModelPricing(input_per_million=0.12, output_per_million=0.47),
    "gpt-4-turbo": ModelPricing(input_per_million=7.90, output_per_million=23.70),
    "gpt-4.1": ModelPricing(input_per_million=1.58, output_per_million=6.32),
    "gpt-4.1-mini": ModelPricing(input_per_million=0.32, output_per_million=1.26),
    "gpt-4.1-nano": ModelPricing(input_per_million=0.08, output_per_million=0.32),
    # Anthropic
    "claude-opus-4-20250514": ModelPricing(input_per_million=11.85, output_per_million=59.25),
    "claude-sonnet-4-20250514": ModelPricing(input_per_million=2.37, output_per_million=11.85),
    "claude-haiku-4-5-20251001": ModelPricing(input_per_million=0.79, output_per_million=3.16),
}

# Fallback for unknown models — conservative estimate
_DEFAULT_PRICING = ModelPricing(input_per_million=2.0, output_per_million=8.0)


def _get_pricing(model: str) -> ModelPricing:
    """Resolve pricing for a model, with prefix matching for versioned names."""
    if model in _MODEL_PRICING:
        return _MODEL_PRICING[model]
    # Prefix match (e.g., "gpt-4o-2024-08-06" → "gpt-4o")
    for prefix, pricing in sorted(_MODEL_PRICING.items(), key=lambda x: -len(x[0])):
        if model.startswith(prefix):
            return pricing
    return _DEFAULT_PRICING


def _current_month_key() -> str:
    """Return YYYY-MM for the current UTC month."""
    return datetime.now(UTC).strftime("%Y-%m")


def _month_ttl_seconds() -> int:
    """Seconds remaining in current month + 90 day buffer for reporting."""
    return _SECONDS_PER_90_DAYS


@dataclass(frozen=True)
class CostRecord:
    """Result of a cost tracking operation."""

    model: str
    input_tokens: int
    output_tokens: int
    cost_gbp: float  # Actual £ cost
    monthly_total_pence: int  # Running monthly total in pence


@dataclass(frozen=True)
class CostReport:
    """Monthly cost summary for the dashboard."""

    month: str  # YYYY-MM
    total_gbp: float
    budget_gbp: float
    utilization_pct: float
    status: BudgetStatus
    by_model: dict[str, float]  # model → £
    by_agent: dict[str, float]  # agent → £
    by_project: dict[str, float]  # project_id → £


class CostGovernor:
    """Redis-backed cost tracking with budget enforcement.

    All costs stored as integer pence to avoid floating point drift.
    Falls back to in-memory tracking when Redis is unavailable.
    """

    def __init__(self, monthly_budget_gbp: float, warning_threshold: float = 0.8) -> None:
        self._budget_pence = int(monthly_budget_gbp * 100)
        self._warning_pence = int(self._budget_pence * warning_threshold)
        self._fallback_totals: dict[str, int] = {}  # key → pence

    def _cost_pence(self, model: str, input_tokens: int, output_tokens: int) -> int:
        """Calculate cost in pence for a completion."""
        pricing = _get_pricing(model)
        input_cost = (input_tokens / 1_000_000) * pricing.input_per_million * 100
        output_cost = (output_tokens / 1_000_000) * pricing.output_per_million * 100
        return max(1, int(input_cost + output_cost))  # Minimum 1 pence granularity

    async def check_budget(self) -> BudgetStatus:
        """Check if budget allows another request."""
        if self._budget_pence == 0:  # 0 = unlimited
            return BudgetStatus.OK

        month = _current_month_key()
        total = await self._get_monthly_total(month)

        if total >= self._budget_pence:
            logger.warning(
                "cost_governor.budget_exceeded",
                month=month,
                total_pence=total,
                budget_pence=self._budget_pence,
            )
            return BudgetStatus.EXCEEDED

        if total >= self._warning_pence:
            logger.warning(
                "cost_governor.budget_warning",
                month=month,
                total_pence=total,
                budget_pence=self._budget_pence,
                utilization_pct=round(total / self._budget_pence * 100, 1),
            )
            return BudgetStatus.WARNING

        return BudgetStatus.OK

    async def record(
        self,
        *,
        model: str,
        input_tokens: int,
        output_tokens: int,
        agent: str = "",
        project_id: str = "",
    ) -> CostRecord:
        """Record token usage and cost after a completion.

        Fire-and-forget safe — never raises on Redis errors.
        """
        pence = self._cost_pence(model, input_tokens, output_tokens)
        month = _current_month_key()
        ttl = _month_ttl_seconds()

        monthly_total = await self._increment(f"cost:monthly:{month}", pence, ttl)

        # Per-dimension counters (fire-and-forget, don't block on failure)
        try:
            await self._increment(f"cost:monthly:{month}:model:{model}", pence, ttl)
            if agent:
                await self._increment(f"cost:monthly:{month}:agent:{agent}", pence, ttl)
            if project_id:
                await self._increment(f"cost:monthly:{month}:project:{project_id}", pence, ttl)
        except Exception:
            logger.debug("cost_governor.dimension_tracking_failed", month=month)

        cost_gbp = pence / 100.0

        logger.info(
            "cost_governor.recorded",
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_gbp=round(cost_gbp, 4),
            monthly_total_gbp=round(monthly_total / 100.0, 2),
            agent=agent or None,
            project_id=project_id or None,
        )

        return CostRecord(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_gbp=cost_gbp,
            monthly_total_pence=monthly_total,
        )

    async def get_report(self, month: str | None = None) -> CostReport:
        """Build a cost report for the given month (default: current)."""
        month = month or _current_month_key()
        total_pence = await self._get_monthly_total(month)

        by_model = await self._get_dimension_breakdown(month, "model")
        by_agent = await self._get_dimension_breakdown(month, "agent")
        by_project = await self._get_dimension_breakdown(month, "project")

        budget_gbp = self._budget_pence / 100.0
        total_gbp = total_pence / 100.0
        utilization = (total_pence / self._budget_pence * 100) if self._budget_pence > 0 else 0.0

        status = BudgetStatus.OK
        if self._budget_pence > 0:
            if total_pence >= self._budget_pence:
                status = BudgetStatus.EXCEEDED
            elif total_pence >= self._warning_pence:
                status = BudgetStatus.WARNING

        return CostReport(
            month=month,
            total_gbp=round(total_gbp, 2),
            budget_gbp=round(budget_gbp, 2),
            utilization_pct=round(utilization, 1),
            status=status,
            by_model={k: round(v / 100.0, 2) for k, v in by_model.items()},
            by_agent={k: round(v / 100.0, 2) for k, v in by_agent.items()},
            by_project={k: round(v / 100.0, 2) for k, v in by_project.items()},
        )

    # ── Redis operations ──

    async def _increment(self, key: str, pence: int, ttl: int) -> int:
        """Increment a Redis counter, return new value. Falls back to memory."""
        try:
            from app.core.redis import get_redis

            r = await get_redis()
            new_total = await r.incrby(key, pence)
            if new_total == pence:  # First write — set TTL
                await r.expire(key, ttl)
            return int(new_total)
        except Exception:
            logger.debug("cost_governor.redis_fallback", key=key)
            self._fallback_totals[key] = self._fallback_totals.get(key, 0) + pence
            return self._fallback_totals[key]

    async def _get_monthly_total(self, month: str) -> int:
        """Get total spend for a month in pence."""
        key = f"cost:monthly:{month}"
        try:
            from app.core.redis import get_redis

            r = await get_redis()
            raw = await r.get(key)
            return int(raw) if raw else 0
        except Exception:
            return self._fallback_totals.get(key, 0)

    async def _get_dimension_breakdown(self, month: str, dimension: str) -> dict[str, int]:
        """Scan Redis for all keys matching a dimension pattern."""
        pattern = f"cost:monthly:{month}:{dimension}:*"
        prefix_len = len(f"cost:monthly:{month}:{dimension}:")
        result: dict[str, int] = {}
        try:
            from app.core.redis import get_redis

            r = await get_redis()
            cursor: int | str = 0
            while True:
                scan_result = await r.scan(cursor=int(cursor), match=pattern, count=100)  # pyright: ignore[reportUnknownMemberType]
                cursor, keys = scan_result
                for k in keys:
                    val = await r.get(k)
                    if val:
                        name = k[prefix_len:] if isinstance(k, str) else k.decode()[prefix_len:]
                        result[name] = int(val)
                if cursor == 0:
                    break
        except Exception:
            logger.debug("cost_governor.scan_failed", dimension=dimension)
            for k, v in self._fallback_totals.items():
                if k.startswith(f"cost:monthly:{month}:{dimension}:"):
                    name = k[prefix_len:]
                    result[name] = v
        return result


# ── Module-level singleton ──

_governor: CostGovernor | None = None


def get_cost_governor() -> CostGovernor:
    """Get or create the cost governor singleton."""
    global _governor
    if _governor is None:
        from app.core.config import get_settings

        settings = get_settings()
        _governor = CostGovernor(
            monthly_budget_gbp=settings.ai.monthly_budget_gbp,
            warning_threshold=settings.ai.budget_warning_threshold,
        )
    return _governor


def reset_cost_governor() -> None:
    """Reset singleton (for testing)."""
    global _governor
    _governor = None
