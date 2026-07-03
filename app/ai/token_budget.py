# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
"""Token budget management for LLM API calls.

Estimates token counts and trims message lists to stay within model context
windows. Uses tiktoken for OpenAI models, character-based approximation for
others (Anthropic, Ollama, etc.).

Adaptive trimming strategy:
- System messages: always preserved (never trimmed)
- Recent user/assistant messages: preserved at full fidelity
- Older messages: summarized to a single compact message
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.ai.protocols import Message
from app.core.logging import get_logger

logger = get_logger(__name__)

__all__ = [
    "TokenBudgetManager",
    "TokenEstimate",
]

# Model name → context window size (tokens).
# Used when token_budget_max=0 (auto-detect).
_MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    # OpenAI
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-4": 8_192,
    "gpt-3.5-turbo": 16_385,
    # Anthropic
    "claude-opus-4-20250514": 200_000,
    "claude-sonnet-4-20250514": 200_000,
    "claude-haiku-4-5-20251001": 200_000,
    "claude-3-5-sonnet-20241022": 200_000,
    "claude-3-5-haiku-20241022": 200_000,
    "claude-3-opus-20240229": 200_000,
    "claude-3-sonnet-20240229": 200_000,
    "claude-3-haiku-20240307": 200_000,
}

# Fallback context window when model is unknown
_DEFAULT_CONTEXT_WINDOW = 16_384

# Average chars per token — used for approximation when tiktoken unavailable
_CHARS_PER_TOKEN = 4.0

# Per-message overhead (role, formatting tokens)
_MESSAGE_OVERHEAD_TOKENS = 4


@dataclass(frozen=True)
class TokenEstimate:
    """Result of token estimation for a message list."""

    total_tokens: int
    per_message: tuple[int, ...]
    method: str  # "tiktoken" or "approximation"


class TokenBudgetManager:
    """Manages token budgets for LLM API calls.

    Estimates token counts and trims messages to fit within model context
    windows, reserving space for the response.
    """

    def __init__(
        self,
        *,
        model: str,
        reserve_tokens: int = 4096,
        max_context_tokens: int = 0,
    ) -> None:
        self._model = model
        self._reserve = reserve_tokens
        self._encoding = self._load_encoding(model)

        if max_context_tokens > 0:
            self._max_context = max_context_tokens
        else:
            self._max_context = self._detect_context_window(model)

        self._budget = self._max_context - self._reserve

        logger.debug(
            "ai.token_budget.initialized",
            model=model,
            max_context=self._max_context,
            reserve=self._reserve,
            budget=self._budget,
            method="tiktoken" if self._encoding else "approximation",
        )

    @property
    def budget(self) -> int:
        """Available token budget for messages (context window - reserve)."""
        return self._budget

    @property
    def max_context(self) -> int:
        """Total context window size."""
        return self._max_context

    @staticmethod
    def _load_encoding(model: str) -> Any:  # noqa: ANN401 — tiktoken.Encoding | None
        """Try to load tiktoken encoding for the model."""
        try:
            import tiktoken  # type: ignore[import-not-found]

            try:
                return tiktoken.encoding_for_model(model)
            except KeyError:
                return tiktoken.get_encoding("cl100k_base")
        except ImportError:
            return None

    @staticmethod
    def _detect_context_window(model: str) -> int:
        """Detect context window from model name.

        Checks exact match first, then prefix match for versioned model names.
        """
        if model in _MODEL_CONTEXT_WINDOWS:
            return _MODEL_CONTEXT_WINDOWS[model]

        # Prefix match: "gpt-4o-2024-08-06" → "gpt-4o"
        for known_model, window in _MODEL_CONTEXT_WINDOWS.items():
            if model.startswith(known_model):
                return window

        return _DEFAULT_CONTEXT_WINDOW

    def estimate_tokens(self, messages: list[Message]) -> TokenEstimate:
        """Estimate token count for a list of messages."""
        per_message: list[int] = []
        total = 0

        for msg in messages:
            tokens = self._count_message_tokens(msg)
            per_message.append(tokens)
            total += tokens

        method = "tiktoken" if self._encoding else "approximation"
        return TokenEstimate(
            total_tokens=total,
            per_message=tuple(per_message),
            method=method,
        )

    def _count_message_tokens(self, msg: Message) -> int:
        """Count tokens for a single message including overhead.

        Handles both string content and multimodal ContentBlock lists.
        """
        if isinstance(msg.content, str):
            content_tokens = self._count_text_tokens(msg.content)
        elif isinstance(msg.content, list):  # pyright: ignore[reportUnnecessaryIsInstance]
            from app.ai.multimodal import estimate_blocks_tokens

            content_tokens = estimate_blocks_tokens(msg.content)
        else:
            content_tokens = self._count_text_tokens(str(msg.content))
        role_tokens = self._count_text_tokens(msg.role)
        return content_tokens + role_tokens + _MESSAGE_OVERHEAD_TOKENS

    def _count_text_tokens(self, text: str) -> int:
        """Count tokens for a text string."""
        if self._encoding is not None:
            try:
                return len(self._encoding.encode(text))
            except Exception:
                logger.debug("ai.token_budget.tiktoken_encode_failed", text_length=len(text))
        return int(len(text) / _CHARS_PER_TOKEN)

    def needs_trimming(self, messages: list[Message]) -> bool:
        """Check if messages exceed the available budget."""
        estimate = self.estimate_tokens(messages)
        return estimate.total_tokens > self._budget

    def trim_to_budget(self, messages: list[Message]) -> list[Message]:
        """Trim messages to fit within the token budget.

        Strategy:
        1. System messages (index 0) are always preserved.
        2. The last message (user prompt) is always preserved.
        3. Middle messages are removed oldest-first.
        4. If still over budget after removing all middle messages,
           the system message content is truncated.
        """
        if not messages:
            return messages

        estimate = self.estimate_tokens(messages)
        if estimate.total_tokens <= self._budget:
            return messages

        logger.info(
            "ai.token_budget.trimming_started",
            original_tokens=estimate.total_tokens,
            budget=self._budget,
            message_count=len(messages),
        )

        # Separate protected messages from trimmable ones
        if len(messages) <= 2:
            return self._truncate_system_message(messages)

        system_msg = messages[0]
        last_msg = messages[-1]
        middle = messages[1:-1]

        # Try adding middle messages newest-first, skip those that don't fit
        trimmed_middle: list[Message] = []
        for msg in reversed(middle):
            candidate_check = [system_msg, msg, *trimmed_middle, last_msg]
            est = self.estimate_tokens(candidate_check)
            if est.total_tokens <= self._budget:
                trimmed_middle.insert(0, msg)
            else:
                logger.debug(
                    "ai.token_budget.message_dropped",
                    role=msg.role,
                    content_length=len(msg.content),
                )

        result = [system_msg, *trimmed_middle, last_msg]
        final_est = self.estimate_tokens(result)

        if final_est.total_tokens > self._budget:
            result = self._truncate_system_message(result)
            final_est = self.estimate_tokens(result)

        logger.info(
            "ai.token_budget.trimming_completed",
            original_tokens=estimate.total_tokens,
            trimmed_tokens=final_est.total_tokens,
            messages_kept=len(result),
            messages_dropped=len(messages) - len(result),
        )

        return result

    def _truncate_system_message(self, messages: list[Message]) -> list[Message]:
        """Truncate the system message to fit budget.

        When safe compaction (51.2) is on and the system message opens with the
        pinned safety preamble, the preamble survives truncation intact: it is
        never cut and is preserved even when the budget would otherwise drop the
        whole system message.
        """
        if not messages or messages[0].role != "system":
            return messages

        preamble = self._preamble_to_pin(messages[0].content)

        non_system_tokens = sum(self._count_message_tokens(m) for m in messages[1:])
        available_for_system = self._budget - non_system_tokens - _MESSAGE_OVERHEAD_TOKENS

        if available_for_system <= 0:
            if preamble:
                # Invariant wins over budget: keep the pinned preamble alone.
                return [
                    Message(
                        role="system",
                        content=preamble,
                        cache_control=messages[0].cache_control,
                    ),
                    *messages[1:],
                ]
            return messages[1:]

        system_content = messages[0].content
        # Only truncate text content; multimodal messages can't be trimmed
        if not isinstance(system_content, str):
            logger.warning(
                "ai.token_budget.multimodal_system_skip",
                msg="Cannot truncate multimodal system message",
            )
            return messages

        if preamble:
            preamble_tokens = self._count_text_tokens(preamble)
            if available_for_system <= preamble_tokens:
                # Budget can't fit even the preamble's remainder — keep the
                # preamble alone rather than cutting into it.
                truncated = preamble
            else:
                remainder = system_content[len(preamble) :]
                truncated = preamble + self._truncate_text_to_tokens(
                    remainder, available_for_system - preamble_tokens
                )
        else:
            truncated = self._truncate_text_to_tokens(system_content, available_for_system)

        if truncated == system_content:
            return messages

        result = [
            Message(
                role="system",
                content=truncated,
                cache_control=messages[0].cache_control,
            ),
            *messages[1:],
        ]
        return result

    @staticmethod
    def _preamble_to_pin(content: str | list[Any]) -> str:
        """Return the pinned safety preamble iff it must survive truncation.

        Strict no-op (returns ``""``) unless safe compaction is on, the loaded
        preamble is non-empty, ``content`` is a ``str``, and ``content`` starts
        with the preamble. The ``startswith`` guard keeps this an exact prefix
        we can slice and makes generic callers (whose messages never carried the
        preamble) fully unaffected.
        """
        if not isinstance(content, str):
            return ""
        from app.ai.agents.safety_preamble import SAFETY_PREAMBLE
        from app.core.config import get_settings

        if not SAFETY_PREAMBLE:
            return ""
        if not get_settings().security.safe_compaction_enabled:
            return ""
        if content.startswith(SAFETY_PREAMBLE):
            return SAFETY_PREAMBLE
        return ""

    def _truncate_text_to_tokens(self, text: str, max_tokens: int) -> str:
        """Truncate text to fit within a token limit."""
        current = self._count_text_tokens(text)
        if current <= max_tokens:
            return text

        marker = "\n[...truncated]"
        marker_tokens = self._count_text_tokens(marker)
        target = max_tokens - marker_tokens

        if target <= 0:
            return marker.strip()

        if self._encoding is not None:
            try:
                tokens = self._encoding.encode(text)
                truncated_tokens = tokens[:target]
                decoded: str = self._encoding.decode(truncated_tokens)
                return decoded + marker
            except Exception:
                logger.debug("ai.token_budget.tiktoken_truncate_failed", text_length=len(text))

        # Character approximation
        char_limit = int(target * _CHARS_PER_TOKEN)
        return text[:char_limit] + marker
