"""Model tier routing for AI provider calls.

Maps task complexity tiers to specific model identifiers.
Agents specify their required tier; the router resolves to a concrete model.
Also supports capability-aware resolution via the model capability registry (22.1).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from app.core.config import get_settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.ai.capability_registry import ModelCapability
    from app.ai.fallback import FallbackChain

logger = get_logger(__name__)

TaskTier = Literal["complex", "standard", "lightweight"]


def resolve_model(tier: TaskTier | None = None) -> str:
    """Resolve a task complexity tier to a concrete model identifier.

    Falls back to the default model (settings.ai.model) when:
    - No tier is specified
    - The tier's model is not configured (empty string)

    Args:
        tier: Task complexity tier, or None for default model.

    Returns:
        Model identifier string to pass to the provider.
    """
    settings = get_settings()
    default_model = settings.ai.model

    if tier is None:
        return default_model

    tier_model_map: dict[TaskTier, str] = {
        "complex": settings.ai.model_complex,
        "standard": settings.ai.model_standard,
        "lightweight": settings.ai.model_lightweight,
    }

    model = tier_model_map.get(tier, "") or default_model

    if model != default_model:
        logger.debug(
            "ai.routing.tier_resolved",
            tier=tier,
            model=model,
        )

    return model


def resolve_model_by_capabilities(
    requirements: set[ModelCapability] | None = None,
    min_context: int = 0,
    min_output_tokens: int = 0,
    tier: TaskTier | None = None,
    provider: str | None = None,
) -> str | None:
    """Resolve a model by capability requirements.

    Returns the cheapest model matching all requirements, or None if no match.
    Falls back to None (caller should use resolve_model() as fallback).

    Args:
        requirements: Required model capabilities.
        min_context: Minimum context window in tokens.
        min_output_tokens: Minimum max output tokens.
        tier: Optional tier filter.
        provider: Optional provider filter.

    Returns:
        Model identifier string, or None if no model matches.
    """
    from app.ai.capability_registry import get_capability_registry

    registry = get_capability_registry()
    if registry.size == 0:
        return None

    matches = registry.find_models(
        requirements=requirements,
        min_context=min_context,
        min_output_tokens=min_output_tokens,
        tier=tier,
        provider=provider,
    )
    if not matches:
        logger.debug(
            "ai.routing.no_capability_match",
            requirements=[r.value for r in (requirements or set())],
            min_context=min_context,
            tier=tier,
        )
        return None

    model_id = matches[0].model_id
    logger.debug(
        "ai.routing.capability_resolved",
        model=model_id,
        requirements=[r.value for r in (requirements or set())],
        candidates=len(matches),
    )
    return model_id


# ── Fallback chains (Phase 22.4) ──

_fallback_chains: dict[str, FallbackChain] | None = None


def get_fallback_chain(tier: TaskTier) -> FallbackChain | None:
    """Get the fallback chain for a tier, or None if not configured."""
    global _fallback_chains
    if _fallback_chains is None:
        from app.ai.fallback import parse_fallback_chains

        settings = get_settings()
        raw = settings.ai.fallback_chains
        _fallback_chains = parse_fallback_chains(raw) if raw else {}
    return _fallback_chains.get(tier)


def reset_fallback_chains() -> None:
    """Reset cached fallback chains (for testing)."""
    global _fallback_chains
    _fallback_chains = None
