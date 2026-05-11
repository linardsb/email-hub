"""Tests for adapter multimodal serialization (Phase 23.1 + 23.2)."""

from __future__ import annotations

import base64
import struct
from unittest.mock import patch

from app.ai.adapters.anthropic import AnthropicProvider
from app.ai.adapters.openai_compat import OpenAICompatProvider
from app.ai.multimodal import (
    AudioBlock,
    ContentBlock,
    ImageBlock,
    StructuredOutputBlock,
    TextBlock,
    ToolResultBlock,
)
from app.ai.protocols import Message
from app.ai.token_budget import TokenBudgetManager


def _make_png_data() -> bytes:
    header = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">II", 10, 10) + b"\x08\x02\x00\x00\x00"
    ihdr_length = struct.pack(">I", len(ihdr_data))
    return header + ihdr_length + b"IHDR" + ihdr_data + b"\x00\x00\x00\x00"


# ── Anthropic Serialization ──


class TestAnthropicSerialization:
    def test_single_text_block_plain_string(self) -> None:
        blocks: list[ContentBlock] = [TextBlock(text="hello")]
        result = AnthropicProvider._serialize_content_blocks(blocks)
        assert result == "hello"

    def test_mixed_text_image_returns_list(self) -> None:
        png_data = _make_png_data()
        blocks: list[ContentBlock] = [
            TextBlock(text="Look at this"),
            ImageBlock(data=png_data, media_type="image/png"),
        ]
        result = AnthropicProvider._serialize_content_blocks(blocks)
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0] == {"type": "text", "text": "Look at this"}
        assert result[1]["type"] == "image"
        assert result[1]["source"]["type"] == "base64"
        assert result[1]["source"]["media_type"] == "image/png"
        # Verify base64 encoding is valid
        decoded = base64.b64decode(result[1]["source"]["data"])
        assert decoded == png_data

    def test_url_image_source(self) -> None:
        blocks: list[ContentBlock] = [
            ImageBlock(
                data=b"", media_type="image/png", source="url", url="https://example.com/img.png"
            ),
        ]
        result = AnthropicProvider._serialize_content_blocks(blocks)
        assert isinstance(result, list)
        assert result[0]["source"]["type"] == "url"
        assert result[0]["source"]["url"] == "https://example.com/img.png"

    def test_tool_result_serialization(self) -> None:
        blocks: list[ContentBlock] = [
            ToolResultBlock(
                tool_use_id="tool-abc",
                content=[TextBlock(text="result data")],
            ),
        ]
        result = AnthropicProvider._serialize_content_blocks(blocks)
        assert isinstance(result, list)
        assert result[0]["type"] == "tool_result"
        assert result[0]["tool_use_id"] == "tool-abc"
        assert result[0]["content"] == [{"type": "text", "text": "result data"}]

    def test_audio_placeholder(self) -> None:
        blocks: list[ContentBlock] = [
            AudioBlock(data=b"\x00" * 100, media_type="audio/mp3"),
        ]
        result = AnthropicProvider._serialize_content_blocks(blocks)
        assert isinstance(result, list)
        assert result[0]["type"] == "text"
        assert "Audio" in result[0]["text"]


# ── OpenAI Serialization ──


class TestOpenAISerialization:
    def test_single_text_block_plain_string(self) -> None:
        blocks: list[ContentBlock] = [TextBlock(text="hello")]
        result = OpenAICompatProvider._serialize_content_blocks(blocks)
        assert result == "hello"

    def test_mixed_text_image_data_uri(self) -> None:
        png_data = _make_png_data()
        blocks: list[ContentBlock] = [
            TextBlock(text="Describe this"),
            ImageBlock(data=png_data, media_type="image/png"),
        ]
        result = OpenAICompatProvider._serialize_content_blocks(blocks)
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0] == {"type": "text", "text": "Describe this"}
        assert result[1]["type"] == "image_url"
        url = result[1]["image_url"]["url"]
        assert url.startswith("data:image/png;base64,")
        # Verify base64 payload decodes to original
        b64_part = url.split(",", 1)[1]
        assert base64.b64decode(b64_part) == png_data

    def test_url_image_passthrough(self) -> None:
        blocks: list[ContentBlock] = [
            ImageBlock(
                data=b"", media_type="image/jpeg", source="url", url="https://example.com/photo.jpg"
            ),
        ]
        result = OpenAICompatProvider._serialize_content_blocks(blocks)
        assert isinstance(result, list)
        assert result[0]["image_url"]["url"] == "https://example.com/photo.jpg"

    def test_audio_placeholder(self) -> None:
        blocks: list[ContentBlock] = [
            AudioBlock(data=b"\x00" * 50, media_type="audio/wav"),
        ]
        result = OpenAICompatProvider._serialize_content_blocks(blocks)
        assert isinstance(result, list)
        assert "Audio" in result[0]["text"]

    def test_multiple_text_blocks(self) -> None:
        blocks: list[ContentBlock] = [
            TextBlock(text="Part 1"),
            TextBlock(text="Part 2"),
        ]
        result = OpenAICompatProvider._serialize_content_blocks(blocks)
        assert isinstance(result, list)
        assert len(result) == 2


# ── Backward Compatibility ──


class TestBackwardCompatibility:
    def test_str_content_in_message(self) -> None:
        """Message(content='hello') still works — adapters normalize str to TextBlock."""
        msg = Message(role="user", content="hello world")
        assert msg.content == "hello world"

    def test_list_content_in_message(self) -> None:
        """Message with list[ContentBlock] content works."""
        blocks: list[ContentBlock] = [TextBlock(text="hi")]
        msg = Message(role="user", content=blocks)
        assert isinstance(msg.content, list)

    def test_token_budget_handles_str_content(self) -> None:
        """TokenBudgetManager still handles string content unchanged."""
        mgr = TokenBudgetManager(model="gpt-4o-mini", reserve_tokens=100, max_context_tokens=1000)
        messages = [
            Message(role="system", content="You are helpful."),
            Message(role="user", content="Hi there"),
        ]
        estimate = mgr.estimate_tokens(messages)
        assert estimate.total_tokens > 0

    def test_token_budget_handles_multimodal_content(self) -> None:
        """TokenBudgetManager handles multimodal content."""
        mgr = TokenBudgetManager(model="gpt-4o", reserve_tokens=100, max_context_tokens=200_000)
        messages = [
            Message(role="system", content="Analyze images."),
            Message(
                role="user",
                content=[
                    TextBlock(text="Look at this"),
                    ImageBlock(
                        data=_make_png_data(), media_type="image/png", width=100, height=100
                    ),
                ],
            ),
        ]
        estimate = mgr.estimate_tokens(messages)
        assert estimate.total_tokens > 0

    def test_trim_skips_multimodal_system(self) -> None:
        """Trimming doesn't break on multimodal system messages."""
        mgr = TokenBudgetManager(model="gpt-4o-mini", reserve_tokens=100, max_context_tokens=200)
        messages = [
            Message(role="system", content=[TextBlock(text="sys")]),
            Message(role="user", content="hi"),
        ]
        # Should not raise
        result = mgr.trim_to_budget(messages)
        assert len(result) >= 1


# ── Phase 23.2: Structured Output Extraction ──


class TestStructuredOutputExtraction:
    """StructuredOutputBlock extraction from messages."""

    def test_openai_extract_from_last_message(self) -> None:
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        messages = [
            Message(role="system", content="Be helpful."),
            Message(
                role="user",
                content=[
                    TextBlock(text="Parse this"),
                    StructuredOutputBlock(schema=schema, name="my_schema"),
                ],
            ),
        ]
        result = OpenAICompatProvider._extract_structured_output(messages)
        assert result is not None
        assert result.name == "my_schema"
        assert result.schema == schema

    def test_anthropic_extract_from_last_message(self) -> None:
        schema = {"type": "object", "properties": {"score": {"type": "number"}}}
        messages = [
            Message(
                role="user",
                content=[
                    TextBlock(text="Evaluate"),
                    StructuredOutputBlock(schema=schema, name="eval_result"),
                ],
            ),
        ]
        result = AnthropicProvider._extract_structured_output(messages)
        assert result is not None
        assert result.name == "eval_result"

    def test_no_structured_output_returns_none(self) -> None:
        messages = [
            Message(role="user", content="Just text"),
        ]
        assert OpenAICompatProvider._extract_structured_output(messages) is None
        assert AnthropicProvider._extract_structured_output(messages) is None

    def test_empty_messages_returns_none(self) -> None:
        assert OpenAICompatProvider._extract_structured_output([]) is None
        assert AnthropicProvider._extract_structured_output([]) is None

    def test_str_content_returns_none(self) -> None:
        messages = [Message(role="user", content="hello")]
        assert OpenAICompatProvider._extract_structured_output(messages) is None

    def test_no_structured_block_in_list_returns_none(self) -> None:
        messages = [
            Message(
                role="user",
                content=[TextBlock(text="no structured output here")],
            ),
        ]
        assert OpenAICompatProvider._extract_structured_output(messages) is None


# ── Phase 23.2: Vision Capability Check ──


class TestVisionCapabilityCheck:
    """Vision capability fallback when model lacks vision."""

    def test_unknown_model_assumes_capable(self) -> None:
        """Models not in the registry are assumed to have vision."""
        provider = object.__new__(OpenAICompatProvider)
        provider._model = "unknown-model"
        assert provider._check_vision_capability("unknown-model") is True

    def test_registry_unavailable_assumes_capable(self) -> None:
        """If capability registry fails, assume vision is available."""
        provider = object.__new__(OpenAICompatProvider)
        provider._model = "gpt-4o"
        with patch(
            "app.ai.capability_registry.get_capability_registry",
            side_effect=RuntimeError("not available"),
        ):
            assert provider._check_vision_capability("gpt-4o") is True

    def test_model_with_vision_returns_true(self) -> None:
        """Model with VISION capability returns True."""
        from app.ai.capability_registry import (
            CapabilityRegistry,
            ModelCapability,
            ModelSpec,
        )

        registry = CapabilityRegistry()
        registry.register(
            ModelSpec(
                model_id="gpt-4o",
                provider="openai",
                capabilities=frozenset({ModelCapability.VISION, ModelCapability.STREAMING}),
            )
        )

        provider = object.__new__(OpenAICompatProvider)
        provider._model = "gpt-4o"
        with patch(
            "app.ai.capability_registry.get_capability_registry",
            return_value=registry,
        ):
            assert provider._check_vision_capability("gpt-4o") is True

    def test_model_without_vision_returns_false(self) -> None:
        """Model without VISION capability returns False."""
        from app.ai.capability_registry import (
            CapabilityRegistry,
            ModelCapability,
            ModelSpec,
        )

        registry = CapabilityRegistry()
        registry.register(
            ModelSpec(
                model_id="gpt-3.5-turbo",
                provider="openai",
                capabilities=frozenset({ModelCapability.STREAMING}),
            )
        )

        provider = object.__new__(OpenAICompatProvider)
        provider._model = "gpt-3.5-turbo"
        with patch(
            "app.ai.capability_registry.get_capability_registry",
            return_value=registry,
        ):
            assert provider._check_vision_capability("gpt-3.5-turbo") is False

    def test_anthropic_vision_check_works(self) -> None:
        """Anthropic adapter has the same vision check."""
        provider = object.__new__(AnthropicProvider)
        provider._model = "claude-sonnet-4-20250514"
        # Unknown model in registry → assume capable
        assert provider._check_vision_capability("claude-sonnet-4-20250514") is True


# ── Phase 23.2: Vision Fallback in Message Payload ──


class TestVisionFallbackInPayload:
    """Images replaced with text when model lacks vision."""

    def test_openai_replaces_images_for_non_vision_model(self) -> None:
        """Non-vision model gets text descriptions instead of images."""
        from app.ai.capability_registry import (
            CapabilityRegistry,
            ModelCapability,
            ModelSpec,
        )

        registry = CapabilityRegistry()
        registry.register(
            ModelSpec(
                model_id="text-only-model",
                provider="openai",
                capabilities=frozenset({ModelCapability.STREAMING}),
            )
        )

        provider = object.__new__(OpenAICompatProvider)
        provider._model = "text-only-model"

        png_data = _make_png_data()
        messages = [
            Message(
                role="user",
                content=[
                    TextBlock(text="Describe this"),
                    ImageBlock(data=png_data, media_type="image/png"),
                ],
            ),
        ]

        with patch(
            "app.ai.capability_registry.get_capability_registry",
            return_value=registry,
        ):
            result = provider._format_payload(messages, "text-only-model")

        assert len(result) == 1
        content = result[0]["content"]
        assert isinstance(content, list)
        # Second block should be text (replaced image)
        assert content[1]["type"] == "text"
        assert "[Image:" in content[1]["text"]

    def test_openai_keeps_images_for_vision_model(self) -> None:
        """Vision-capable model keeps actual images."""
        provider = object.__new__(OpenAICompatProvider)
        provider._model = "gpt-4o"

        png_data = _make_png_data()
        messages = [
            Message(
                role="user",
                content=[
                    TextBlock(text="Look"),
                    ImageBlock(data=png_data, media_type="image/png"),
                ],
            ),
        ]

        # Unknown model → assumes vision capable
        result = provider._format_payload(messages, "gpt-4o")
        content = result[0]["content"]
        assert isinstance(content, list)
        assert content[1]["type"] == "image_url"

    def test_anthropic_replaces_images_for_non_vision_model(self) -> None:
        """Anthropic non-vision fallback works too."""
        from app.ai.capability_registry import (
            CapabilityRegistry,
            ModelCapability,
            ModelSpec,
        )

        registry = CapabilityRegistry()
        registry.register(
            ModelSpec(
                model_id="text-only",
                provider="anthropic",
                capabilities=frozenset({ModelCapability.STREAMING}),
            )
        )

        provider = object.__new__(AnthropicProvider)
        provider._model = "text-only"

        png_data = _make_png_data()
        messages = [
            Message(
                role="user",
                content=[
                    TextBlock(text="See image"),
                    ImageBlock(data=png_data, media_type="image/png"),
                ],
            ),
        ]

        with patch(
            "app.ai.capability_registry.get_capability_registry",
            return_value=registry,
        ):
            _system_parts, chat_msgs, _ = provider._format_payload(
                messages,
                "text-only",
            )

        assert len(chat_msgs) == 1
        content = chat_msgs[0]["content"]
        assert isinstance(content, list)
        assert content[1]["type"] == "text"
        assert "[Image:" in content[1]["text"]


# ── Phase 23.2: Structured Output in Payload ──


class TestStructuredOutputPayload:
    """StructuredOutputBlock → provider request format verification."""

    def test_openai_response_format_structure(self) -> None:
        """OpenAI structured output produces correct response_format."""
        schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
        block = StructuredOutputBlock(schema=schema, name="qa_response", strict=True)
        messages = [
            Message(role="user", content=[TextBlock(text="Q"), block]),
        ]
        result = OpenAICompatProvider._extract_structured_output(messages)
        assert result is not None

        # Simulate what complete() would do
        payload: dict[str, object] = {}
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": result.name,
                "schema": result.schema,
                "strict": result.strict,
            },
        }
        rf = payload["response_format"]
        assert isinstance(rf, dict)
        assert rf["type"] == "json_schema"
        js = rf["json_schema"]
        assert isinstance(js, dict)
        assert js["name"] == "qa_response"
        assert js["schema"] == schema
        assert js["strict"] is True

    def test_anthropic_tool_use_structure(self) -> None:
        """Anthropic structured output produces correct tool definition."""
        schema = {"type": "object", "properties": {"score": {"type": "number"}}}
        block = StructuredOutputBlock(schema=schema, name="eval_result")
        messages = [
            Message(role="user", content=[TextBlock(text="Evaluate"), block]),
        ]
        result = AnthropicProvider._extract_structured_output(messages)
        assert result is not None

        # Simulate what complete() would build
        tools = [
            {
                "name": result.name,
                "description": f"Return structured output matching the {result.name} schema",
                "input_schema": result.schema,
            },
        ]
        tool_choice = {"type": "tool", "name": result.name}

        assert tools[0]["name"] == "eval_result"
        assert tools[0]["input_schema"] == schema
        assert tool_choice["name"] == "eval_result"


# ── Phase 23.2: Multimodal Token Budget ──


class TestMultimodalTokenBudget:
    """Token budget estimation for multimodal messages."""

    def test_image_block_fixed_estimate(self) -> None:
        """Image without dimensions uses default 1000 tokens."""
        mgr = TokenBudgetManager(model="gpt-4o", reserve_tokens=100, max_context_tokens=200_000)
        messages = [
            Message(
                role="user",
                content=[ImageBlock(data=b"\xff\xd8\xff", media_type="image/jpeg")],
            ),
        ]
        estimate = mgr.estimate_tokens(messages)
        # Default image tokens (1000) + role + overhead
        assert estimate.total_tokens > 1000

    def test_mixed_content_estimation(self) -> None:
        """Mixed text + image message gives combined estimate."""
        mgr = TokenBudgetManager(model="gpt-4o", reserve_tokens=100, max_context_tokens=200_000)
        messages = [
            Message(
                role="user",
                content=[
                    TextBlock(text="a" * 400),  # ~100 tokens
                    ImageBlock(data=b"", media_type="image/png", width=600, height=450),  # 360
                ],
            ),
        ]
        estimate = mgr.estimate_tokens(messages)
        # 100 (text) + 360 (image) + role + overhead > 460
        assert estimate.total_tokens >= 460

    def test_trim_preserves_recent_images(self) -> None:
        """Trimming strategy keeps last message (with images) intact."""
        mgr = TokenBudgetManager(model="gpt-4o-mini", reserve_tokens=100, max_context_tokens=2000)
        messages = [
            Message(role="system", content="Short sys."),
            Message(role="user", content="Old message 1"),
            Message(role="assistant", content="Old response"),
            Message(
                role="user",
                content=[
                    TextBlock(text="Latest"),
                    ImageBlock(data=_make_png_data(), media_type="image/png"),
                ],
            ),
        ]
        result = mgr.trim_to_budget(messages)
        # Last message should always be preserved
        assert isinstance(result[-1].content, list)
