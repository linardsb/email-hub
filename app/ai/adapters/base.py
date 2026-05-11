# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
"""Shared infrastructure for LLM provider adapters.

Concrete adapters (AnthropicProvider, OpenAICompatProvider) inherit from
BaseLLMProvider and implement complete()/stream()/_format_payload()/close().
The base provides token budget trimming, cost governance, structured-output
extraction, and vision capability lookup — features that are byte-for-byte
identical between providers.

Subclasses must set ``self._model: str`` in ``__init__`` (used by
``_apply_token_budget`` as the fallback when ``kwargs`` lacks ``model_override``).

Subclasses MUST override ``_get_settings()`` to delegate through their own
module-local ``get_settings`` binding so test-patching of
``app.ai.adapters.{anthropic,openai_compat}.get_settings`` continues to take
effect on the inherited helpers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from app.ai.multimodal import StructuredOutputBlock
from app.ai.protocols import CompletionResponse, Message
from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.core.config import Settings

logger = get_logger(__name__)


class BaseLLMProvider(ABC):
    """Abstract base for LLM provider adapters.

    Provides shared utilities for token budget enforcement, cost governance,
    structured-output payload extraction, and vision capability lookup.
    Concrete subclasses implement the provider-specific
    complete()/stream()/close()/_format_payload() surface and the
    _get_settings() hook (so existing per-module `get_settings` patches still
    apply through inheritance).
    """

    _model: str  # subclass __init__ must set this

    # ── Abstract surface ──

    @abstractmethod
    async def complete(self, messages: list[Message], **kwargs: object) -> CompletionResponse:
        """Send a chat completion request. Subclass-specific."""
        ...

    @abstractmethod
    def stream(self, messages: list[Message], **kwargs: object) -> AsyncIterator[str]:
        """Stream completion tokens as they are generated. Subclass-specific.

        Declared as ``def`` (not ``async def``) so pyright treats the return type
        as ``AsyncIterator[str]`` directly — matching the async-generator
        subclass override (``async def stream(...): yield ...``) under Liskov
        substitution. Calling code uses ``async for chunk in provider.stream(...)``.
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Release underlying HTTP/SDK clients. Subclass-specific."""
        ...

    @abstractmethod
    def _get_settings(self) -> Settings:
        """Return the application settings via the subclass's local binding.

        Subclasses implement as ``return get_settings()`` so the inherited
        helpers below pick up the test-patched function on the subclass
        module without 24 test sites having to add a second patch on
        ``app.ai.adapters.base.get_settings``.
        """
        ...

    # ── Shared helpers ──

    def _apply_token_budget(
        self, messages: list[Message], kwargs: dict[str, object]
    ) -> list[Message]:
        """Trim messages to fit token budget if enabled."""
        settings = self._get_settings()
        if not settings.ai.token_budget_enabled:
            return messages
        from app.ai.token_budget import TokenBudgetManager

        model = str(kwargs.get("model_override", self._model))
        budget_mgr = TokenBudgetManager(
            model=model,
            reserve_tokens=settings.ai.token_budget_reserve,
            max_context_tokens=settings.ai.token_budget_max,
        )
        return budget_mgr.trim_to_budget(messages)

    async def _check_cost_budget(self) -> None:
        """Check budget before making an API call. Raises BudgetExceededError if over budget."""
        settings = self._get_settings()
        if not settings.ai.cost_governor_enabled:
            return
        from app.ai.cost_governor import BudgetStatus, get_cost_governor

        governor = get_cost_governor()
        status = await governor.check_budget()
        if status == BudgetStatus.EXCEEDED:
            from app.ai.exceptions import BudgetExceededError

            raise BudgetExceededError("Monthly AI budget exceeded")

    async def _report_cost(
        self, model: str, usage: dict[str, int] | None, kwargs: dict[str, object]
    ) -> None:
        """Report token usage to cost governor if enabled. Fire-and-forget."""
        settings = self._get_settings()
        if not settings.ai.cost_governor_enabled or usage is None:
            return
        try:
            from app.ai.cost_governor import get_cost_governor

            governor = get_cost_governor()
            await governor.record(
                model=model,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                agent=str(kwargs.get("agent_name", "")),
                project_id=str(kwargs.get("project_id", "")),
            )
        except Exception:
            logger.debug("cost_governor.report_failed", model=model)

    @staticmethod
    def _extract_structured_output(
        messages: list[Message],
    ) -> StructuredOutputBlock | None:
        """Extract StructuredOutputBlock from the last message, if present."""
        if not messages:
            return None
        last = messages[-1]
        if isinstance(last.content, list):
            for block in last.content:
                if isinstance(block, StructuredOutputBlock):
                    return block
        return None

    def _check_vision_capability(self, model: str) -> bool:
        """Check if the model supports vision via capability registry."""
        try:
            from app.ai.capability_registry import (
                ModelCapability,
                get_capability_registry,
            )

            registry = get_capability_registry()
            spec = registry.get(model)
            if spec is None:
                return True  # Unknown model — assume capable
            return ModelCapability.VISION in spec.capabilities
        except Exception:
            return True  # Registry unavailable — don't block
