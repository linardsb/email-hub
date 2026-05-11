"""MCP agent tool tests — all 9 AI agents exposed as tools."""
# pyright: reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.fastmcp import FastMCP

# ── Helpers ──


def _register_agents(mcp: FastMCP) -> None:
    from app.mcp.tools.agents import register_agent_tools

    register_agent_tools(mcp)


def _mock_response(**overrides: Any) -> MagicMock:
    """Create a mock Pydantic response with model_dump."""
    defaults: dict[str, Any] = {
        "html": "<html><body>Generated</body></html>",
        "model": "test-model",
        "confidence": 0.92,
        "skills_loaded": ["SKILL.md"],
    }
    defaults.update(overrides)
    mock = MagicMock()
    mock.model_dump.return_value = defaults
    return mock


_VALID_HTML = "<html><body>" + "x" * 50 + "</body></html>"


# ── Scaffolder ──


class TestScaffoldTool:
    @pytest.mark.anyio
    async def test_scaffold_happy_path(self) -> None:
        """Scaffold returns formatted result with confidence."""
        with patch("app.ai.agents.scaffolder.service.get_scaffolder_service") as mock_get:
            svc = AsyncMock()
            svc.process = AsyncMock(
                return_value=_mock_response(
                    qa_passed=None,
                    qa_results=None,
                    mso_warnings=[],
                    plan=None,
                )
            )
            mock_get.return_value = svc

            mcp = FastMCP("test")
            _register_agents(mcp)
            tool_fn = mcp._tool_manager._tools["agent_scaffold"].fn
            result = await tool_fn(
                brief="Create a summer sale promotional email with hero image and 3 product cards",
                ctx=MagicMock(),
            )
            assert "92%" in result
            assert "Scaffolder" in result

    @pytest.mark.anyio
    async def test_scaffold_brief_too_short(self) -> None:
        """Brief under 10 chars returns validation error."""
        mcp = FastMCP("test")
        _register_agents(mcp)
        tool_fn = mcp._tool_manager._tools["agent_scaffold"].fn
        result = await tool_fn(brief="short", ctx=MagicMock())
        assert "too short" in result.lower()

    @pytest.mark.anyio
    async def test_scaffold_brief_too_long(self) -> None:
        """Brief over 4000 chars returns validation error."""
        mcp = FastMCP("test")
        _register_agents(mcp)
        tool_fn = mcp._tool_manager._tools["agent_scaffold"].fn
        result = await tool_fn(brief="x" * 4001, ctx=MagicMock())
        assert "too long" in result.lower()

    @pytest.mark.anyio
    async def test_scaffold_service_error(self) -> None:
        """Service exception returns generic error."""
        with patch("app.ai.agents.scaffolder.service.get_scaffolder_service") as mock_get:
            svc = AsyncMock()
            svc.process = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
            mock_get.return_value = svc

            mcp = FastMCP("test")
            _register_agents(mcp)
            tool_fn = mcp._tool_manager._tools["agent_scaffold"].fn
            result = await tool_fn(
                brief="Create a basic newsletter email",
                ctx=MagicMock(),
            )
            assert "internal error" in result.lower()
            assert "LLM unavailable" not in result


# ── Dark Mode ──


class TestDarkModeTool:
    @pytest.mark.anyio
    async def test_dark_mode_happy_path(self) -> None:
        with patch("app.ai.agents.dark_mode.service.get_dark_mode_service") as mock_get:
            svc = AsyncMock()
            svc.process = AsyncMock(
                return_value=_mock_response(
                    meta_tags_injected=["color-scheme"],
                    qa_passed=None,
                    qa_results=None,
                    plan=None,
                    decisions=None,
                )
            )
            mock_get.return_value = svc

            mcp = FastMCP("test")
            _register_agents(mcp)
            tool_fn = mcp._tool_manager._tools["agent_dark_mode"].fn
            result = await tool_fn(html=_VALID_HTML, ctx=MagicMock())
            assert "Dark Mode" in result
            assert "92%" in result

    @pytest.mark.anyio
    async def test_dark_mode_html_too_short(self) -> None:
        mcp = FastMCP("test")
        _register_agents(mcp)
        tool_fn = mcp._tool_manager._tools["agent_dark_mode"].fn
        result = await tool_fn(html="<html>short</html>", ctx=MagicMock())
        assert "too short" in result.lower()

    @pytest.mark.anyio
    async def test_dark_mode_html_too_large(self) -> None:
        mcp = FastMCP("test")
        _register_agents(mcp)
        tool_fn = mcp._tool_manager._tools["agent_dark_mode"].fn
        result = await tool_fn(html="x" * 500_001, ctx=MagicMock())
        assert "too large" in result.lower()


# ── Content ──


class TestContentTool:
    @pytest.mark.anyio
    async def test_content_subject_line(self) -> None:
        with patch("app.ai.agents.content.service.get_content_service") as mock_get:
            svc = AsyncMock()
            svc.process = AsyncMock(
                return_value=_mock_response(
                    html="",
                    content=["Line A", "Line B", "Line C"],
                    operation="subject_line",
                    spam_warnings=[],
                    length_warnings=[],
                    decisions=None,
                )
            )
            mock_get.return_value = svc

            mcp = FastMCP("test")
            _register_agents(mcp)
            tool_fn = mcp._tool_manager._tools["agent_content"].fn
            result = await tool_fn(
                operation="subject_line",
                text="Summer sale campaign for outdoor gear",
                ctx=MagicMock(),
            )
            assert "Content" in result

    @pytest.mark.anyio
    async def test_content_invalid_operation(self) -> None:
        mcp = FastMCP("test")
        _register_agents(mcp)
        tool_fn = mcp._tool_manager._tools["agent_content"].fn
        result = await tool_fn(
            operation="invalid_op",
            text="Some text",
            ctx=MagicMock(),
        )
        assert "Invalid operation" in result

    @pytest.mark.anyio
    async def test_content_empty_text(self) -> None:
        mcp = FastMCP("test")
        _register_agents(mcp)
        tool_fn = mcp._tool_manager._tools["agent_content"].fn
        result = await tool_fn(
            operation="subject_line",
            text="   ",
            ctx=MagicMock(),
        )
        assert "empty" in result.lower()

    @pytest.mark.anyio
    async def test_content_text_too_long(self) -> None:
        mcp = FastMCP("test")
        _register_agents(mcp)
        tool_fn = mcp._tool_manager._tools["agent_content"].fn
        result = await tool_fn(
            operation="body_copy",
            text="x" * 10_001,
            ctx=MagicMock(),
        )
        assert "too long" in result.lower()


# ── Outlook Fixer ──


class TestOutlookFixerTool:
    @pytest.mark.anyio
    async def test_outlook_fix_happy_path(self) -> None:
        with patch("app.ai.agents.outlook_fixer.service.get_outlook_fixer_service") as mock_get:
            svc = AsyncMock()
            svc.process = AsyncMock(
                return_value=_mock_response(
                    fixes_applied=["ghost_table", "vml_background"],
                    mso_validation_warnings=[],
                    diagnostic=None,
                    qa_passed=None,
                    qa_results=None,
                    plan=None,
                )
            )
            mock_get.return_value = svc

            mcp = FastMCP("test")
            _register_agents(mcp)
            tool_fn = mcp._tool_manager._tools["agent_outlook_fix"].fn
            result = await tool_fn(html=_VALID_HTML, ctx=MagicMock())
            assert "Outlook Fixer" in result

    @pytest.mark.anyio
    async def test_outlook_fix_with_csv_issues(self) -> None:
        """Comma-separated issues are split correctly."""
        with patch("app.ai.agents.outlook_fixer.service.get_outlook_fixer_service") as mock_get:
            svc = AsyncMock()
            svc.process = AsyncMock(
                return_value=_mock_response(
                    fixes_applied=["vml"],
                    mso_validation_warnings=[],
                    diagnostic=None,
                    qa_passed=None,
                    qa_results=None,
                    plan=None,
                )
            )
            mock_get.return_value = svc

            mcp = FastMCP("test")
            _register_agents(mcp)
            tool_fn = mcp._tool_manager._tools["agent_outlook_fix"].fn
            result = await tool_fn(html=_VALID_HTML, ctx=MagicMock(), issues="vml, ghost_tables")
            assert isinstance(result, str)


# ── Accessibility ──


class TestAccessibilityTool:
    @pytest.mark.anyio
    async def test_accessibility_happy_path(self) -> None:
        with patch("app.ai.agents.accessibility.service.get_accessibility_service") as mock_get:
            svc = AsyncMock()
            svc.process = AsyncMock(
                return_value=_mock_response(
                    alt_text_warnings=["Image missing alt"],
                    qa_passed=None,
                    qa_results=None,
                    decisions=None,
                    plan=None,
                )
            )
            mock_get.return_value = svc

            mcp = FastMCP("test")
            _register_agents(mcp)
            tool_fn = mcp._tool_manager._tools["agent_accessibility"].fn
            result = await tool_fn(html=_VALID_HTML, ctx=MagicMock())
            assert "Accessibility" in result

    @pytest.mark.anyio
    async def test_accessibility_html_too_short(self) -> None:
        mcp = FastMCP("test")
        _register_agents(mcp)
        tool_fn = mcp._tool_manager._tools["agent_accessibility"].fn
        result = await tool_fn(html="<p>tiny</p>", ctx=MagicMock())
        assert "too short" in result.lower()


# ── Code Reviewer ──


class TestCodeReviewTool:
    @pytest.mark.anyio
    async def test_code_review_happy_path(self) -> None:
        with patch("app.ai.agents.code_reviewer.service.get_code_review_service") as mock_get:
            svc = AsyncMock()
            svc.process = AsyncMock(
                return_value=_mock_response(
                    issues=[{"rule": "redundant-mso", "severity": "warning", "message": "Found"}],
                    summary="1 issue found",
                    qa_passed=None,
                    qa_results=None,
                    decisions=None,
                    actionability_warnings=[],
                )
            )
            mock_get.return_value = svc

            mcp = FastMCP("test")
            _register_agents(mcp)
            tool_fn = mcp._tool_manager._tools["agent_code_review"].fn
            result = await tool_fn(html=_VALID_HTML, ctx=MagicMock())
            assert "Code Review" in result


# ── Personalisation ──


class TestPersonaliseTool:
    @pytest.mark.anyio
    async def test_personalise_happy_path(self) -> None:
        with patch("app.ai.agents.personalisation.service.get_personalisation_service") as mock_get:
            svc = AsyncMock()
            svc.process = AsyncMock(
                return_value=_mock_response(
                    platform="braze",
                    tags_injected=["{{first_name}}"],
                    syntax_warnings=[],
                    qa_passed=None,
                    qa_results=None,
                    decisions=None,
                    plan=None,
                )
            )
            mock_get.return_value = svc

            mcp = FastMCP("test")
            _register_agents(mcp)
            tool_fn = mcp._tool_manager._tools["agent_personalise"].fn
            result = await tool_fn(
                html=_VALID_HTML,
                platform="braze",
                requirements="Add first name greeting with fallback to 'there'",
                ctx=MagicMock(),
            )
            assert "Personalisation" in result

    @pytest.mark.anyio
    async def test_personalise_invalid_platform(self) -> None:
        mcp = FastMCP("test")
        _register_agents(mcp)
        tool_fn = mcp._tool_manager._tools["agent_personalise"].fn
        result = await tool_fn(
            html=_VALID_HTML,
            platform="sendgrid",
            requirements="Add personalization",
            ctx=MagicMock(),
        )
        assert "Invalid platform" in result

    @pytest.mark.anyio
    async def test_personalise_short_requirements(self) -> None:
        mcp = FastMCP("test")
        _register_agents(mcp)
        tool_fn = mcp._tool_manager._tools["agent_personalise"].fn
        result = await tool_fn(
            html=_VALID_HTML,
            platform="braze",
            requirements="hi",
            ctx=MagicMock(),
        )
        assert "too short" in result.lower()


# ── Innovation ──


class TestInnovateTool:
    @pytest.mark.anyio
    async def test_innovate_happy_path(self) -> None:
        with patch("app.ai.agents.innovation.service.get_innovation_service") as mock_get:
            svc = AsyncMock()
            svc.process = AsyncMock(
                return_value=_mock_response(
                    html="",
                    prototype="<div>accordion</div>",
                    feasibility="Good for Gmail, partial elsewhere",
                    client_coverage=0.65,
                    risk_level="medium",
                    recommendation="test_further",
                    fallback_html="<div>static</div>",
                )
            )
            mock_get.return_value = svc

            mcp = FastMCP("test")
            _register_agents(mcp)
            tool_fn = mcp._tool_manager._tools["agent_innovate"].fn
            result = await tool_fn(
                technique="CSS-only accordion for FAQ section with smooth transitions",
                ctx=MagicMock(),
            )
            assert "Innovation" in result

    @pytest.mark.anyio
    async def test_innovate_technique_too_short(self) -> None:
        mcp = FastMCP("test")
        _register_agents(mcp)
        tool_fn = mcp._tool_manager._tools["agent_innovate"].fn
        result = await tool_fn(technique="hi", ctx=MagicMock())
        assert "too short" in result.lower()


# ── Knowledge ──


def _mock_db_ctx() -> MagicMock:
    """Create a mock async context manager for get_db_context."""
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


class TestKnowledgeTool:
    @pytest.mark.anyio
    async def test_knowledge_happy_path(self) -> None:
        with (
            patch("app.ai.agents.knowledge.service.get_knowledge_agent_service") as mock_get,
            patch("app.core.database.get_db_context", return_value=_mock_db_ctx()),
            patch("app.knowledge.services.search.SearchService"),
        ):
            svc = AsyncMock()
            svc.process = AsyncMock(
                return_value=_mock_response(
                    html="",
                    answer="Gmail strips media queries because...",
                    sources=[],
                )
            )
            mock_get.return_value = svc

            mcp = FastMCP("test")
            _register_agents(mcp)
            tool_fn = mcp._tool_manager._tools["agent_knowledge"].fn
            result = await tool_fn(
                question="Why does Gmail strip media queries from email HTML?",
                ctx=MagicMock(),
            )
            assert "Knowledge" in result

    @pytest.mark.anyio
    async def test_knowledge_question_too_short(self) -> None:
        mcp = FastMCP("test")
        _register_agents(mcp)
        tool_fn = mcp._tool_manager._tools["agent_knowledge"].fn
        result = await tool_fn(question="hi", ctx=MagicMock())
        assert "too short" in result.lower()


# ── Error Handling ──


class TestAgentToolErrors:
    @pytest.mark.anyio
    async def test_service_error_no_stack_trace(self) -> None:
        """Service exceptions return generic message, no internal details."""
        with patch("app.ai.agents.dark_mode.service.get_dark_mode_service") as mock_get:
            svc = AsyncMock()
            svc.process = AsyncMock(side_effect=RuntimeError("DB connection refused"))
            mock_get.return_value = svc

            mcp = FastMCP("test")
            _register_agents(mcp)
            tool_fn = mcp._tool_manager._tools["agent_dark_mode"].fn
            result = await tool_fn(html=_VALID_HTML, ctx=MagicMock())
            assert "internal error" in result.lower()
            assert "DB connection refused" not in result

    @pytest.mark.anyio
    @patch("app.mcp.tools.agents.logger")
    async def test_service_error_logs_tool_name(self, mock_logger: MagicMock) -> None:
        """Service errors log with tool name for debugging."""
        with patch("app.ai.agents.outlook_fixer.service.get_outlook_fixer_service") as mock_get:
            svc = AsyncMock()
            svc.process = AsyncMock(side_effect=RuntimeError("Timeout"))
            mock_get.return_value = svc

            mcp = FastMCP("test")
            _register_agents(mcp)
            tool_fn = mcp._tool_manager._tools["agent_outlook_fix"].fn
            await tool_fn(html=_VALID_HTML, ctx=MagicMock())
            mock_logger.exception.assert_called_once()
            call_kwargs = mock_logger.exception.call_args
            assert call_kwargs[1]["tool"] == "agent_outlook_fix"


# ── Resource ──


class TestAgentListResource:
    def test_hub_agents_resource_returns_all_9(self) -> None:
        """hub://agents resource lists all 9 agents."""
        import json

        mcp = FastMCP("test")
        from app.mcp.resources import register_resources

        register_resources(mcp)
        resources: Any = mcp._resource_manager._resources
        result = json.loads(resources["hub://agents"].fn())
        assert result["count"] == 9
        names = {a["name"] for a in result["agents"]}
        assert names == {
            "scaffolder",
            "dark_mode",
            "content",
            "outlook_fixer",
            "accessibility",
            "code_reviewer",
            "personalisation",
            "innovation",
            "knowledge",
        }

    def test_hub_agents_resource_has_tool_names(self) -> None:
        """Each agent entry has a tool name matching agent_* pattern."""
        import json

        mcp = FastMCP("test")
        from app.mcp.resources import register_resources

        register_resources(mcp)
        resources: Any = mcp._resource_manager._resources
        result = json.loads(resources["hub://agents"].fn())
        for agent in result["agents"]:
            assert agent["tool"].startswith("agent_"), (
                f"Tool name should start with 'agent_': {agent}"
            )
            assert "type" in agent
            assert "description" in agent


# ── Tool Registration ──


class TestAgentToolRegistration:
    def test_all_9_agent_tools_registered(self) -> None:
        """All 9 agent tools are registered on the MCP server."""
        mcp = FastMCP("test")
        _register_agents(mcp)
        tools = set(mcp._tool_manager._tools)
        expected = {
            "agent_scaffold",
            "agent_dark_mode",
            "agent_content",
            "agent_outlook_fix",
            "agent_accessibility",
            "agent_code_review",
            "agent_personalise",
            "agent_innovate",
            "agent_knowledge",
        }
        assert expected.issubset(tools), f"Missing agent tools: {expected - tools}"

    def test_agent_tool_descriptions_substantive(self) -> None:
        """Agent tool descriptions are 30+ words (MCP best practice)."""
        mcp = FastMCP("test")
        _register_agents(mcp)
        for name, tool in mcp._tool_manager._tools.items():
            desc = tool.description or ""
            word_count = len(desc.split())
            assert word_count >= 30, (
                f"Tool '{name}' description too short ({word_count} words). "
                "Agent tool descriptions should teach LLMs about email constraints."
            )
