"""MCP tool execution tests with mocked backend services."""
# pyright: reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.fastmcp import FastMCP

# ── Helpers ──


def _register_qa(mcp: FastMCP) -> None:
    from app.mcp.tools.qa import register_qa_tools

    register_qa_tools(mcp)


def _register_knowledge(mcp: FastMCP) -> None:
    from app.mcp.tools.knowledge import register_knowledge_tools

    register_knowledge_tools(mcp)


def _register_email(mcp: FastMCP) -> None:
    from app.mcp.tools.email import register_email_tools

    register_email_tools(mcp)


def _register_rendering(mcp: FastMCP) -> None:
    from app.mcp.tools.rendering import register_rendering_tools

    register_rendering_tools(mcp)


def _register_ai(mcp: FastMCP) -> None:
    from app.mcp.tools.ai import register_ai_tools

    register_ai_tools(mcp)


def _mock_db_ctx(*, side_effect: Exception | None = None) -> MagicMock:
    ctx = MagicMock()
    if side_effect:
        ctx.__aenter__ = AsyncMock(side_effect=side_effect)
    else:
        ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# ── QA Tool Tests ──


class TestQAToolExecution:
    """Test QA tool category with mocked services."""

    @pytest.mark.anyio
    async def test_qa_check_valid_html(self) -> None:
        """Valid HTML returns formatted QA report with score."""
        mock_result = MagicMock()
        mock_result.model_dump.return_value = {
            "overall_score": 95,
            "passed": 11,
            "total": 11,
            "failed": 0,
            "checks": [],
        }

        with (
            patch("app.qa_engine.service.QAEngineService") as MockQA,
            patch("app.core.database.get_db_context", return_value=_mock_db_ctx()),
        ):
            MockQA.return_value.run_checks = AsyncMock(return_value=mock_result)
            mcp = FastMCP("test")
            _register_qa(mcp)
            tool_fn = mcp._tool_manager._tools["qa_check"].fn
            ctx = MagicMock()
            result = await tool_fn(
                html="<html><body>Hello</body></html>",
                ctx=ctx,
                target_clients=None,
                skip_checks=None,
            )
            assert "95/100" in result or "score" in result.lower()

    @pytest.mark.anyio
    async def test_qa_check_empty_html_returns_error(self) -> None:
        """Empty HTML returns validation error."""
        mcp = FastMCP("test")
        _register_qa(mcp)
        tool_fn = mcp._tool_manager._tools["qa_check"].fn
        ctx = MagicMock()
        result = await tool_fn(html="   ", ctx=ctx, target_clients=None, skip_checks=None)
        assert "empty" in result.lower()

    @pytest.mark.anyio
    async def test_qa_check_oversized_html_returns_error(self) -> None:
        """HTML exceeding 500KB returns size error."""
        mcp = FastMCP("test")
        _register_qa(mcp)
        tool_fn = mcp._tool_manager._tools["qa_check"].fn
        ctx = MagicMock()
        result = await tool_fn(html="x" * 600_000, ctx=ctx, target_clients=None, skip_checks=None)
        assert "too large" in result.lower()

    @pytest.mark.anyio
    async def test_production_readiness_calls_multiple_services(self) -> None:
        """Production readiness tool calls QA, deliverability, Gmail, Outlook."""
        mock_qa_result = MagicMock()
        mock_qa_result.model_dump.return_value = {
            "overall_score": 90,
            "passed": 10,
            "total": 11,
            "failed": 1,
            "checks": [],
        }

        mock_gmail_result = MagicMock()
        mock_gmail_result.model_dump.return_value = {
            "summary": "Summer sale",
            "category": "Promotions",
        }

        mock_outlook_result = MagicMock()
        mock_outlook_result.model_dump.return_value = {"dependencies": []}

        with (
            patch("app.qa_engine.service.QAEngineService") as MockQA,
            patch("app.core.database.get_db_context", return_value=_mock_db_ctx()),
            patch(
                "app.qa_engine.checks.deliverability.get_detailed_result",
                return_value=(85, True, [], None),
            ),
            patch("app.qa_engine.gmail_intelligence.predictor.GmailSummaryPredictor") as MockGmail,
            patch(
                "app.qa_engine.outlook_analyzer.detector.OutlookDependencyDetector"
            ) as MockOutlook,
        ):
            MockQA.return_value.run_checks = AsyncMock(return_value=mock_qa_result)
            MockGmail.return_value.predict = AsyncMock(return_value=mock_gmail_result)
            MockOutlook.return_value.analyze = MagicMock(return_value=mock_outlook_result)

            mcp = FastMCP("test")
            _register_qa(mcp)
            tool_fn = mcp._tool_manager._tools["email_production_readiness"].fn
            ctx = AsyncMock()
            result = await tool_fn(
                html="<html><body>Hello</body></html>",
                ctx=ctx,
                subject="Test",
                from_name="Sender",
            )
            assert "QA Score" in result or "Deliverability" in result

    @pytest.mark.anyio
    async def test_chaos_test_returns_resilience_score(self) -> None:
        """Chaos test returns formatted resilience result."""
        mock_result = MagicMock()
        mock_result.model_dump.return_value = {
            "resilience_score": 82,
            "profiles_passed": 6,
            "profiles_total": 8,
        }

        with patch("app.qa_engine.chaos.engine.ChaosEngine") as MockChaos:
            MockChaos.return_value.run_chaos_test = AsyncMock(return_value=mock_result)

            mcp = FastMCP("test")
            _register_qa(mcp)
            tool_fn = mcp._tool_manager._tools["chaos_test"].fn
            ctx = MagicMock()
            result = await tool_fn(
                html="<html><body>Hello</body></html>",
                ctx=ctx,
                profiles=None,
            )
            assert isinstance(result, str)
            assert len(result) > 0

    @pytest.mark.anyio
    async def test_outlook_analyze_returns_dependencies(self) -> None:
        """Outlook analyzer returns formatted dependency report."""
        mock_analysis = MagicMock()
        mock_analysis.model_dump.return_value = {
            "dependencies": [{"type": "VML", "severity": "high"}],
        }

        with patch(
            "app.qa_engine.outlook_analyzer.detector.OutlookDependencyDetector"
        ) as MockDetector:
            MockDetector.return_value.analyze = MagicMock(return_value=mock_analysis)

            mcp = FastMCP("test")
            _register_qa(mcp)
            tool_fn = mcp._tool_manager._tools["outlook_analyze"].fn
            ctx = MagicMock()
            result = await tool_fn(
                html="<html><body>Hello</body></html>",
                ctx=ctx,
                target="audit_only",
            )
            assert isinstance(result, str)
            assert len(result) > 0


# ── Knowledge Tool Tests ──


class TestKnowledgeToolExecution:
    """Test knowledge tool category with mocked services."""

    @pytest.mark.anyio
    async def test_knowledge_search_formats_results(self) -> None:
        """Knowledge search returns formatted results with relevance."""
        mock_item = MagicMock()
        mock_item.model_dump.return_value = {
            "title": "CSS Grid in Email",
            "score": 0.85,
            "domain": "compatibility",
            "content": "Guide",
        }
        mock_results = MagicMock()
        mock_results.results = [mock_item]

        with (
            patch("app.core.database.get_db_context", return_value=_mock_db_ctx()),
            patch("app.knowledge.services.search.SearchService") as MockKS,
        ):
            MockKS.return_value.search_routed = AsyncMock(return_value=mock_results)

            mcp = FastMCP("test")
            _register_knowledge(mcp)
            tool_fn = mcp._tool_manager._tools["knowledge_search"].fn
            ctx = MagicMock()
            result = await tool_fn(query="CSS grid email", ctx=ctx, domain=None, limit=5)
            assert "CSS Grid" in result or "85%" in result

    @pytest.mark.anyio
    async def test_knowledge_search_empty_results(self) -> None:
        """Empty results returns guidance message."""
        mock_results = MagicMock()
        mock_results.results = []

        with (
            patch("app.core.database.get_db_context", return_value=_mock_db_ctx()),
            patch("app.knowledge.services.search.SearchService") as MockKS,
        ):
            MockKS.return_value.search_routed = AsyncMock(return_value=mock_results)

            mcp = FastMCP("test")
            _register_knowledge(mcp)
            tool_fn = mcp._tool_manager._tools["knowledge_search"].fn
            ctx = MagicMock()
            result = await tool_fn(query="nonexistent", ctx=ctx, domain=None, limit=5)
            assert "No results found" in result

    @pytest.mark.anyio
    async def test_css_support_check_returns_matrix(self) -> None:
        """CSS support check returns client support matrix."""
        mock_result = MagicMock()
        mock_result.model_dump.return_value = {
            "property": "flex",
            "clients": [
                {"name": "Gmail", "supported": True, "partial": False, "notes": "Supported"},
            ],
        }

        with patch("app.knowledge.ontology.structured_query.OntologyQueryEngine") as MockEngine:
            MockEngine.return_value.query_property_support = MagicMock(return_value=mock_result)

            mcp = FastMCP("test")
            _register_knowledge(mcp)
            tool_fn = mcp._tool_manager._tools["css_support_check"].fn
            ctx = MagicMock()
            result = await tool_fn(css_property="flex", ctx=ctx, clients=None)
            assert "supported" in result.lower() or "Gmail" in result

    @pytest.mark.anyio
    async def test_safe_css_alternatives_returns_fallbacks(self) -> None:
        """Safe CSS alternatives returns fallback suggestions."""
        mock_alt = MagicMock()
        mock_alt.model_dump.return_value = {
            "title": "margin-based spacing",
            "score": 0.9,
            "domain": "compatibility",
            "content": "Use margin instead of gap",
        }

        with patch("app.knowledge.ontology.structured_query.OntologyQueryEngine") as MockEngine:
            MockEngine.return_value.find_safe_alternatives = MagicMock(return_value=[mock_alt])

            mcp = FastMCP("test")
            _register_knowledge(mcp)
            tool_fn = mcp._tool_manager._tools["safe_css_alternatives"].fn
            ctx = MagicMock()
            result = await tool_fn(css_property="gap", ctx=ctx, target_clients=None)
            assert isinstance(result, str)
            assert len(result) > 0


# ── Email Tool Tests ──


class TestEmailToolExecution:
    """Test email engine tool category."""

    @pytest.mark.anyio
    async def test_css_optimize_shows_size_reduction(self) -> None:
        """CSS optimize shows compilation stats."""
        mock_result = MagicMock()
        mock_result.model_dump.return_value = {
            "original_size": 10000,
            "compiled_size": 6000,
            "conversions": [],
            "removed_properties": [],
            "compiled_html": "<html>compiled</html>",
        }

        with patch("app.email_engine.css_compiler.compiler.EmailCSSCompiler") as MockCompiler:
            MockCompiler.return_value.compile = MagicMock(return_value=mock_result)

            mcp = FastMCP("test")
            _register_email(mcp)
            tool_fn = mcp._tool_manager._tools["css_optimize"].fn
            ctx = MagicMock()
            result = await tool_fn(
                html="<html><body>Hello</body></html>",
                ctx=ctx,
                target_clients=None,
            )
            assert "40%" in result or "reduction" in result.lower()

    @pytest.mark.anyio
    async def test_schema_markup_injection(self) -> None:
        """Schema markup tool injects JSON-LD."""
        mock_intent = MagicMock()
        mock_intent.intent_type = "promotional"

        mock_inject_result = MagicMock()
        mock_inject_result.model_dump.return_value = {
            "intent_type": "promotional",
            "html": "<html>with schema</html>",
        }

        with (
            patch(
                "app.email_engine.schema_markup.classifier.EmailIntentClassifier"
            ) as MockClassifier,
            patch("app.email_engine.schema_markup.injector.SchemaMarkupInjector") as MockInjector,
        ):
            MockClassifier.return_value.classify = MagicMock(return_value=mock_intent)
            MockInjector.return_value.inject = MagicMock(return_value=mock_inject_result)

            mcp = FastMCP("test")
            _register_email(mcp)
            tool_fn = mcp._tool_manager._tools["inject_schema_markup"].fn
            ctx = MagicMock()
            result = await tool_fn(
                html="<html><body>Hello</body></html>",
                ctx=ctx,
                subject="Sale",
            )
            assert isinstance(result, str)
            assert "promotional" in result.lower() or "Schema" in result


# ── Rendering Tool Tests ──


class TestRenderingToolExecution:
    """Test rendering tool category."""

    @pytest.mark.anyio
    async def test_visual_check_disabled_returns_message(self) -> None:
        """Screenshots disabled returns informative message."""
        with patch("app.core.config.get_settings") as mock_settings:
            mock_settings.return_value.rendering.screenshots_enabled = False

            mcp = FastMCP("test")
            _register_rendering(mcp)
            tool_fn = mcp._tool_manager._tools["email_visual_check"].fn
            ctx = MagicMock()
            result = await tool_fn(
                html="<html><body>Hello</body></html>",
                ctx=ctx,
                clients=None,
            )
            assert "not enabled" in result.lower()

    @pytest.mark.anyio
    async def test_visual_diff_disabled_returns_message(self) -> None:
        """Visual diff disabled returns pending message."""
        with patch("app.core.config.get_settings") as mock_settings:
            mock_settings.return_value.rendering.visual_diff_enabled = False

            mcp = FastMCP("test")
            _register_rendering(mcp)
            tool_fn = mcp._tool_manager._tools["visual_diff"].fn
            ctx = MagicMock()
            result = await tool_fn(
                current_html="<html>new</html>",
                baseline_html="<html>old</html>",
                ctx=ctx,
                client="gmail",
            )
            assert "not enabled" in result.lower()


# ── AI Tool Tests ──


class TestAIToolExecution:
    """Test AI tool category."""

    @pytest.mark.anyio
    async def test_deliverability_score_returns_dimensions(self) -> None:
        """Deliverability score returns dimension breakdown."""
        with patch("app.qa_engine.checks.deliverability.get_detailed_result") as mock_detail:
            mock_detail.return_value = (85, True, [], None)

            mcp = FastMCP("test")
            _register_ai(mcp)
            tool_fn = mcp._tool_manager._tools["deliverability_score"].fn
            ctx = MagicMock()
            result = await tool_fn(
                html="<html><body>Hello</body></html>",
                ctx=ctx,
            )
            assert "85" in result or "Deliverability" in result

    @pytest.mark.anyio
    async def test_bimi_check_valid_domain(self) -> None:
        """BIMI check with valid domain returns readiness report."""
        mock_result = MagicMock()
        mock_result.model_dump.return_value = {
            "dmarc_found": True,
            "bimi_found": False,
            "svg_valid": False,
        }

        with patch("app.qa_engine.bimi.checker.BIMIReadinessChecker") as MockChecker:
            MockChecker.return_value.check_domain = AsyncMock(return_value=mock_result)

            mcp = FastMCP("test")
            _register_ai(mcp)
            tool_fn = mcp._tool_manager._tools["bimi_check"].fn
            ctx = MagicMock()
            result = await tool_fn(domain="example.com", ctx=ctx)
            assert "BIMI" in result

    @pytest.mark.anyio
    async def test_bimi_check_invalid_domain(self) -> None:
        """Invalid domain format returns validation error."""
        mcp = FastMCP("test")
        _register_ai(mcp)
        tool_fn = mcp._tool_manager._tools["bimi_check"].fn
        ctx = MagicMock()
        result = await tool_fn(domain="not a domain!!", ctx=ctx)
        assert "Invalid domain" in result

    @pytest.mark.anyio
    async def test_cost_status_returns_budget_info(self) -> None:
        """Cost status returns budget info."""
        mock_report = MagicMock()
        mock_report.model_dump.return_value = {
            "status": "OK",
            "total_spend_gbp": 12.5,
            "remaining_gbp": 87.5,
        }

        with (
            patch("app.ai.cost_governor.CostGovernor") as MockGov,
            patch("app.core.config.get_settings") as mock_settings,
        ):
            mock_settings.return_value.ai.monthly_budget_gbp = 100.0
            mock_settings.return_value.ai.budget_warning_threshold = 0.8
            MockGov.return_value.get_report = AsyncMock(return_value=mock_report)

            mcp = FastMCP("test")
            _register_ai(mcp)
            tool_fn = mcp._tool_manager._tools["ai_cost_status"].fn
            ctx = MagicMock()
            result = await tool_fn(ctx=ctx)
            assert "Cost" in result or "OK" in result


# ── Error Handling Tests ──


class TestToolErrorHandling:
    """Test that tool errors are handled gracefully."""

    @pytest.mark.anyio
    async def test_tool_exception_returns_generic_message(self) -> None:
        """Service exception returns generic error, no stack trace."""
        with patch(
            "app.core.database.get_db_context",
            return_value=_mock_db_ctx(side_effect=RuntimeError("DB connection refused")),
        ):
            mcp = FastMCP("test")
            _register_qa(mcp)
            tool_fn = mcp._tool_manager._tools["qa_check"].fn
            ctx = MagicMock()
            result = await tool_fn(
                html="<html><body>Hello</body></html>",
                ctx=ctx,
                target_clients=None,
                skip_checks=None,
            )
            assert "internal error" in result.lower()
            assert "DB connection refused" not in result

    @pytest.mark.anyio
    @patch("app.mcp.tools.qa.logger")
    async def test_tool_exception_logs_details(self, mock_logger: MagicMock) -> None:
        """Service exceptions are logged with tool name."""
        with patch(
            "app.core.database.get_db_context",
            return_value=_mock_db_ctx(side_effect=RuntimeError("DB down")),
        ):
            mcp = FastMCP("test")
            _register_qa(mcp)
            tool_fn = mcp._tool_manager._tools["qa_check"].fn
            ctx = MagicMock()
            await tool_fn(
                html="<html><body>Hello</body></html>",
                ctx=ctx,
                target_clients=None,
                skip_checks=None,
            )
            mock_logger.exception.assert_called_once()
            call_kwargs = mock_logger.exception.call_args
            assert call_kwargs[1]["tool"] == "qa_check"
