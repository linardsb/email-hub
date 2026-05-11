# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""Native Anthropic SDK adapter for Claude models.

Uses the official anthropic Python SDK with async support.
Supports both single-shot completion and SSE streaming.
"""

import contextlib
from collections.abc import AsyncIterator
from typing import Any, cast

from app.ai.adapters.base import BaseLLMProvider
from app.ai.exceptions import AIConfigurationError, AIExecutionError
from app.ai.multimodal import (
    AudioBlock,
    ContentBlock,
    ImageBlock,
    StructuredOutputBlock,
    TextBlock,
    ToolResultBlock,
    normalize_content,
    validate_content_blocks,
)
from app.ai.protocols import CompletionResponse, Message
from app.core.config import get_settings
from app.core.credentials import CredentialLease, CredentialPool
from app.core.logging import get_logger

logger = get_logger(__name__)

_REQUEST_TIMEOUT = 120.0
_DEFAULT_MAX_TOKENS = 4096


class AnthropicProvider(BaseLLMProvider):
    """LLM provider using the native Anthropic SDK.

    Reads settings from Settings.ai at instantiation time:
    - ai.api_key: Anthropic API key (required)
    - ai.model: Model identifier (claude-opus-4-20250514, claude-sonnet-4-20250514, etc.)
    """

    def __init__(self) -> None:
        """Initialize the provider from application settings.

        Raises:
            AIConfigurationError: If the anthropic package is not installed
                or AI__API_KEY is not configured.
        """
        try:
            import anthropic
        except ImportError as e:
            raise AIConfigurationError(
                "anthropic package not installed. Run: pip install anthropic"
            ) from e

        settings = get_settings()
        self._model = settings.ai.model
        self._client_cache: dict[str, Any] = {}  # key_hash → AsyncAnthropic

        # Credential pool (Phase 46.2)
        # isinstance guard prevents MagicMock in tests from triggering pool init
        self._pool: CredentialPool | None = None
        if (
            settings.credentials.enabled
            and isinstance(settings.credentials.pools, dict)  # pyright: ignore[reportUnnecessaryIsInstance] — guards against MagicMock in tests
            and "anthropic" in settings.credentials.pools
        ):
            from app.core.credentials import get_credential_pool

            self._pool = get_credential_pool("anthropic")
            self._client: Any = None
            logger.info(
                "ai.provider.anthropic_initialized",
                model=self._model,
                pool=True,
            )
        else:
            api_key = settings.ai.api_key
            if not api_key:
                raise AIConfigurationError(
                    "AI__API_KEY is required for Anthropic provider. "
                    "Set it via environment variable or .env file."
                )
            self._client = anthropic.AsyncAnthropic(
                api_key=api_key,
                timeout=_REQUEST_TIMEOUT,
            )
            logger.info(
                "ai.provider.anthropic_initialized",
                model=self._model,
                pool=False,
            )

    def _get_client(self, api_key: str, key_hash: str) -> Any:  # noqa: ANN401
        """Get or create a cached client for a specific API key."""
        import anthropic

        if key_hash not in self._client_cache:
            self._client_cache[key_hash] = anthropic.AsyncAnthropic(
                api_key=api_key,
                timeout=_REQUEST_TIMEOUT,
            )
        return self._client_cache[key_hash]

    def _get_settings(self) -> Any:  # noqa: ANN401
        """Hook for inherited helpers — delegates to this module's `get_settings`.

        Lets tests that patch `app.ai.adapters.anthropic.get_settings` continue
        to affect the base-class helpers (`_apply_token_budget`, `_check_cost_budget`,
        `_report_cost`) without 24 test sites needing a second patch on the base module.
        """
        return get_settings()

    def _format_payload(
        self,
        messages: list[Message],
        model: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
        """Build Anthropic messages payload with vision capability check.

        Returns:
            Tuple of (system_parts, chat_messages, has_cache_control).
        """
        has_vision = self._check_vision_capability(model)

        system_parts: list[dict[str, Any]] = []
        has_cache_control = False
        chat_messages: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "system":
                blocks = normalize_content(m.content)
                validate_content_blocks(blocks)
                for b in blocks:
                    if isinstance(b, TextBlock):
                        block: dict[str, Any] = {"type": "text", "text": b.text}
                        if m.cache_control:
                            block["cache_control"] = m.cache_control
                            has_cache_control = True
                        system_parts.append(block)
            else:
                blocks = normalize_content(m.content)
                validate_content_blocks(blocks)
                if not has_vision:
                    blocks = cast(
                        "list[ContentBlock]",
                        [
                            TextBlock(text=f"[Image: {b.media_type}, {len(b.data)} bytes]")
                            if isinstance(b, ImageBlock)
                            else b
                            for b in blocks
                        ],
                    )
                serialized = self._serialize_content_blocks(blocks)
                chat_messages.append({"role": m.role, "content": serialized})

        return system_parts, chat_messages, has_cache_control

    async def complete(self, messages: list[Message], **kwargs: object) -> CompletionResponse:
        """Send a chat completion request via Anthropic SDK.

        Args:
            messages: Conversation history as Message objects.
            **kwargs: Additional parameters. Supports model_override, max_tokens,
                temperature, top_p, stop_sequences.

        Returns:
            CompletionResponse with generated content and usage statistics.

        Raises:
            AIConfigurationError: If authentication fails.
            AIExecutionError: If the API call fails or times out.
        """
        import anthropic

        # Token budget trimming (Phase 22.3)
        messages = self._apply_token_budget(messages, dict(kwargs))

        # Cost budget check (Phase 22.5)
        await self._check_cost_budget()

        model = str(kwargs.get("model_override", self._model))
        system_parts, chat_messages, has_cache_control = self._format_payload(
            messages,
            model,
        )

        # Build kwargs for Anthropic API
        api_kwargs: dict[str, Any] = {
            "model": model,
            "messages": chat_messages,
            "max_tokens": int(str(kwargs.get("max_tokens", _DEFAULT_MAX_TOKENS))),
        }
        if system_parts:
            if has_cache_control:
                api_kwargs["system"] = system_parts
            else:
                api_kwargs["system"] = "\n".join(p["text"] for p in system_parts).strip()

        # Structured output via tool_use pattern (Phase 23.2)
        structured_block = self._extract_structured_output(messages)
        if structured_block:
            api_kwargs["tools"] = [
                {
                    "name": structured_block.name,
                    "description": (
                        f"Return structured output matching the {structured_block.name} schema"
                    ),
                    "input_schema": structured_block.schema,
                },
            ]
            api_kwargs["tool_choice"] = {"type": "tool", "name": structured_block.name}

        for key in ("temperature", "top_p", "stop_sequences"):
            if key in kwargs:
                api_kwargs[key] = kwargs[key]

        logger.debug(
            "ai.provider.completion_started",
            model=model,
            message_count=len(chat_messages),
        )

        lease: CredentialLease | None = None
        client = self._client
        try:
            if self._pool:
                lease = await self._pool.get_key()
                client = self._get_client(lease.key, lease.key_hash)

            response = await client.messages.create(**api_kwargs)

            if lease:
                await lease.report_success()
        except anthropic.APITimeoutError as e:
            msg = f"Anthropic API request timed out after {_REQUEST_TIMEOUT}s"
            logger.error("ai.provider.completion_timeout", model=model)
            raise AIExecutionError(msg) from e
        except anthropic.RateLimitError as e:
            if lease:
                await lease.report_failure(429)
            msg = "Anthropic API rate limit exceeded"
            logger.error("ai.provider.completion_rate_limited", model=model)
            raise AIExecutionError(msg) from e
        except anthropic.AuthenticationError as e:
            if lease:
                await lease.report_failure(401)
            msg = "AI provider authentication failed"
            logger.error("ai.provider.completion_auth_failed")
            raise AIConfigurationError(msg) from e
        except anthropic.APIError as e:
            if lease:
                status = getattr(e, "status_code", 500)
                await lease.report_failure(status)
            msg = "AI provider request failed"
            logger.error(
                "ai.provider.completion_failed",
                model=model,
                status_code=getattr(e, "status_code", None),
                detail=str(e.message),
            )
            raise AIExecutionError(msg) from e

        # Extract content — handle both text and tool_use blocks
        content = ""
        parsed: dict[str, object] | None = None
        for block in response.content:
            block_any: Any = block
            if block_any.type == "text":
                content += block_any.text
            elif block_any.type == "tool_use" and structured_block:
                import json

                tool_input = block_any.input
                content = json.dumps(tool_input)
                parsed = dict(tool_input) if isinstance(tool_input, dict) else None

        usage: dict[str, int] = {
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
            "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
        }

        # Track cache metrics when available
        cache_creation = getattr(response.usage, "cache_creation_input_tokens", 0) or 0
        cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
        if cache_creation or cache_read:
            usage["cache_creation_input_tokens"] = cache_creation
            usage["cache_read_input_tokens"] = cache_read

        logger.info(
            "ai.provider.completion_completed",
            model=response.model,
            content_length=len(content),
            usage=usage,
            cache_read=cache_read,
            cache_creation=cache_creation,
        )

        # Cost tracking (Phase 22.5)
        await self._report_cost(response.model, usage, dict(kwargs))

        return CompletionResponse(
            content=content,
            model=response.model,
            usage=usage,
            parsed=parsed,
        )

    async def stream(self, messages: list[Message], **kwargs: object) -> AsyncIterator[str]:
        """Stream completion tokens via Anthropic SDK.

        Args:
            messages: Conversation history as Message objects.
            **kwargs: Additional parameters. Supports model_override, max_tokens,
                temperature, top_p, stop_sequences.

        Yields:
            Individual text chunks as they are generated.

        Raises:
            AIExecutionError: If the API call fails.
        """
        import anthropic

        # Token budget trimming (Phase 22.3)
        messages = self._apply_token_budget(messages, dict(kwargs))

        model = str(kwargs.get("model_override", self._model))
        system_parts_s, chat_messages, has_cache_s = self._format_payload(
            messages,
            model,
        )

        api_kwargs: dict[str, Any] = {
            "model": model,
            "messages": chat_messages,
            "max_tokens": int(str(kwargs.get("max_tokens", _DEFAULT_MAX_TOKENS))),
        }
        if system_parts_s:
            if has_cache_s:
                api_kwargs["system"] = system_parts_s
            else:
                api_kwargs["system"] = "\n".join(p["text"] for p in system_parts_s).strip()

        for key in ("temperature", "top_p", "stop_sequences"):
            if key in kwargs:
                api_kwargs[key] = kwargs[key]

        logger.debug(
            "ai.provider.stream_started",
            model=model,
            message_count=len(chat_messages),
        )

        lease: CredentialLease | None = None
        client = self._client
        try:
            if self._pool:
                lease = await self._pool.get_key()
                client = self._get_client(lease.key, lease.key_hash)

            async with client.messages.stream(**api_kwargs) as stream:
                async for text in stream.text_stream:
                    yield text

            if lease:
                await lease.report_success()
        except anthropic.APITimeoutError as e:
            msg = f"Anthropic streaming timed out after {_REQUEST_TIMEOUT}s"
            logger.error("ai.provider.stream_timeout", model=model)
            raise AIExecutionError(msg) from e
        except anthropic.RateLimitError as e:
            if lease:
                await lease.report_failure(429)
            msg = "Anthropic API rate limit exceeded"
            logger.error("ai.provider.stream_rate_limited", model=model)
            raise AIExecutionError(msg) from e
        except anthropic.APIError as e:
            if lease:
                status = getattr(e, "status_code", 500)
                await lease.report_failure(status)
            msg = "AI provider streaming failed"
            logger.error("ai.provider.stream_failed", model=model)
            raise AIExecutionError(msg) from e

        logger.debug("ai.provider.stream_completed", model=model)

    @staticmethod
    def _serialize_content_blocks(
        blocks: list[ContentBlock],
    ) -> str | list[dict[str, Any]]:
        """Serialize content blocks to Anthropic API format.

        Returns a plain string if all blocks are text (for backward compat),
        otherwise returns Anthropic content block dicts.
        """
        import base64 as b64mod

        # Fast path: single text block → plain string
        if len(blocks) == 1 and isinstance(blocks[0], TextBlock):
            return blocks[0].text

        result: list[dict[str, Any]] = []
        for b in blocks:
            if isinstance(b, TextBlock):
                result.append({"type": "text", "text": b.text})
            elif isinstance(b, ImageBlock):
                if b.source == "base64":
                    result.append(
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": b.media_type,
                                "data": b64mod.b64encode(b.data).decode("ascii"),
                            },
                        }
                    )
                elif b.source == "url":
                    result.append(
                        {
                            "type": "image",
                            "source": {
                                "type": "url",
                                "url": b.url,
                            },
                        }
                    )
            elif isinstance(b, AudioBlock):
                # Anthropic doesn't support audio blocks natively yet — encode as text placeholder
                result.append(
                    {
                        "type": "text",
                        "text": f"[Audio: {b.media_type}, {len(b.data)} bytes]",
                    }
                )
            elif isinstance(b, ToolResultBlock):
                nested = AnthropicProvider._serialize_content_blocks(b.content)
                content = nested if isinstance(nested, list) else [{"type": "text", "text": nested}]
                result.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": b.tool_use_id,
                        "content": content,
                    }
                )
            elif isinstance(b, StructuredOutputBlock):  # pyright: ignore[reportUnnecessaryIsInstance]
                pass  # Handled via tool_use, not content blocks
        return result

    async def close(self) -> None:
        """Close the underlying HTTP client(s).

        Should be called during application shutdown to release connections.
        """
        with contextlib.suppress(RuntimeError):
            if self._client is not None:
                await self._client.close()
        for cached_client in self._client_cache.values():
            with contextlib.suppress(RuntimeError):
                await cached_client.close()
        self._client_cache.clear()
